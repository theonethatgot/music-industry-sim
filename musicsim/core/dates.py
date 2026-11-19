"""Calendar helpers. The simulation clock is a datetime.date advanced one day at a time."""
from __future__ import annotations

import datetime as dt
import re

Date = dt.date


def parse(s) -> Date:
    if isinstance(s, dt.date):
        return s
    return dt.date.fromisoformat(str(s))


def iso(d: Date) -> str:
    return d.isoformat()


def in_window(d: Date, start, end) -> bool:
    """Inclusive validity check; None means open-ended."""
    if start is not None and d < parse(start):
        return False
    if end is not None and d > parse(end):
        return False
    return True


def year_frac(d: Date) -> float:
    start = dt.date(d.year, 1, 1)
    return d.year + (d - start).days / 365.25


_DUR = re.compile(r"^\s*(\d+)\s*([dwmy])\s*$")


def parse_duration(s: str) -> int:
    """'3d' | '2w' | '4m' | '1y' -> days."""
    m = _DUR.match(str(s))
    if not m:
        raise ValueError(f"bad duration {s!r}; use e.g. 3d, 2w, 4m")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"d": 1, "w": 7, "m": 30, "y": 365}[unit]


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def next_weekday(d: Date, weekday: str) -> Date:
    target = WEEKDAYS.index(weekday)
    return d + dt.timedelta(days=(target - d.weekday()) % 7)


def interp_series(series: dict, d: Date) -> float:
    """Linear interpolation over a {year: value} mapping (clamped at the ends)."""
    pts = sorted((float(k), float(v)) for k, v in series.items())
    x = year_frac(d)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]
