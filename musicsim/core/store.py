"""SQLite campaign storage: snapshot + append-only event, command, chart and audit logs."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK (id = 1), date TEXT, hash TEXT,
                                     doc TEXT, arrays BLOB);
CREATE TABLE IF NOT EXISTS commands (seq INTEGER PRIMARY KEY, date TEXT, kind TEXT, payload TEXT,
                                     result TEXT, state_hash TEXT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, date TEXT, system TEXT, type TEXT,
                                   entities TEXT, data TEXT, causes TEXT, draws TEXT, public INTEGER);
CREATE INDEX IF NOT EXISTS events_date ON events(date);
CREATE TABLE IF NOT EXISTS chart_runs (chart TEXT, week_end TEXT, issue_date TEXT, name TEXT,
                                       methodology TEXT, entries TEXT, PRIMARY KEY (chart, week_end));
CREATE TABLE IF NOT EXISTS song_weeks (song TEXT, market TEXT, week_end TEXT, data TEXT,
                                       PRIMARY KEY (song, market, week_end));
CREATE TABLE IF NOT EXISTS passes (pass_no INTEGER PRIMARY KEY, date TEXT, packet TEXT);
"""


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.commit()
        self.db.close()

    # meta ---------------------------------------------------------------------
    def set_meta(self, key: str, value):
        self.db.execute("REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))

    def get_meta(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    # snapshot -------------------------------------------------------------------
    def write_snapshot(self, date: str, state_hash: str, doc: dict, arrays_blob: bytes):
        self.db.execute("REPLACE INTO snapshot VALUES (1, ?, ?, ?, ?)",
                        (date, state_hash, json.dumps(doc, default=str), arrays_blob))

    def read_snapshot(self):
        row = self.db.execute("SELECT date, hash, doc, arrays FROM snapshot WHERE id=1").fetchone()
        if not row:
            raise FileNotFoundError("campaign has no snapshot")
        return row[0], row[1], json.loads(row[2]), row[3]

    # logs -------------------------------------------------------------------------
    def append_events(self, events):
        self.db.executemany(
            "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?)",
            [(e.id, e.date, e.system, e.type, json.dumps(e.entities), json.dumps(e.data, default=str),
              json.dumps(e.causes), json.dumps(e.draws), int(e.public)) for e in events])

    def events_between(self, start: str, end: str, public_only=False):
        q = "SELECT id, date, system, type, entities, data, causes, draws, public FROM events " \
            "WHERE date >= ? AND date <= ?"
        if public_only:
            q += " AND public = 1"
        q += " ORDER BY id"
        return [self._ev(r) for r in self.db.execute(q, (start, end))]

    def event(self, eid: int):
        r = self.db.execute("SELECT id, date, system, type, entities, data, causes, draws, public "
                            "FROM events WHERE id=?", (eid,)).fetchone()
        return self._ev(r) if r else None

    def events_for(self, entity: str, limit: int = 50):
        rows = self.db.execute(
            "SELECT id, date, system, type, entities, data, causes, draws, public FROM events "
            "WHERE entities LIKE ? ORDER BY id DESC LIMIT ?", (f'%"{entity}"%', limit)).fetchall()
        return [self._ev(r) for r in rows]

    @staticmethod
    def _ev(r):
        return {"id": r[0], "date": r[1], "system": r[2], "type": r[3], "entities": json.loads(r[4]),
                "data": json.loads(r[5]), "causes": json.loads(r[6]), "draws": json.loads(r[7]),
                "public": bool(r[8])}

    def append_chart_runs(self, runs):
        self.db.executemany("INSERT OR REPLACE INTO chart_runs VALUES (?,?,?,?,?,?)",
                            [(r["chart"], r["week_end"], r["issue_date"], r["name"], r["methodology"],
                              json.dumps(r["entries"])) for r in runs])

    def chart_run(self, chart: str, week_end: str | None = None):
        if week_end:
            r = self.db.execute("SELECT * FROM chart_runs WHERE chart=? AND week_end=?", (chart, week_end)).fetchone()
        else:
            r = self.db.execute("SELECT * FROM chart_runs WHERE chart=? ORDER BY week_end DESC LIMIT 1",
                                (chart,)).fetchone()
        if not r:
            return None
        return {"chart": r[0], "week_end": r[1], "issue_date": r[2], "name": r[3], "methodology": r[4],
                "entries": json.loads(r[5])}

    def append_song_weeks(self, rows):
        self.db.executemany("INSERT OR REPLACE INTO song_weeks VALUES (?,?,?,?)",
                            [(r["song"], r["market"], r["week_end"], json.dumps(r["data"])) for r in rows])

    def song_weeks(self, song: str, market: str | None = None):
        q = "SELECT market, week_end, data FROM song_weeks WHERE song=?"
        args = [song]
        if market:
            q += " AND market=?"
            args.append(market)
        q += " ORDER BY week_end"
        return [{"market": r[0], "week_end": r[1], **json.loads(r[2])} for r in self.db.execute(q, args)]

    def append_command(self, seq: int, date: str, kind: str, payload: dict, result: dict, state_hash: str):
        self.db.execute("INSERT OR REPLACE INTO commands VALUES (?,?,?,?,?,?)",
                        (seq, date, kind, json.dumps(payload), json.dumps(result, default=str), state_hash))

    def commands(self):
        return [{"seq": r[0], "date": r[1], "kind": r[2], "payload": json.loads(r[3]),
                 "result": json.loads(r[4]), "state_hash": r[5]}
                for r in self.db.execute("SELECT * FROM commands ORDER BY seq")]

    def write_pass(self, pass_no: int, date: str, packet: dict):
        self.db.execute("REPLACE INTO passes VALUES (?,?,?)", (pass_no, date, json.dumps(packet, default=str)))

    def read_pass(self, pass_no: int | None = None):
        if pass_no is None:
            r = self.db.execute("SELECT pass_no, packet FROM passes ORDER BY pass_no DESC LIMIT 1").fetchone()
        else:
            r = self.db.execute("SELECT pass_no, packet FROM passes WHERE pass_no=?", (pass_no,)).fetchone()
        return json.loads(r[1]) if r else None

    def commit(self):
        self.db.commit()
