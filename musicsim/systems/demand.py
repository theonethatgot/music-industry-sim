"""Hit formation and consumption (daily, vectorised per market).

Listener state per song x segment: awareness A, cumulative impressions C, engaged
share E (derived from a mere-exposure liking curve with fatigue), single buyers BS.
Albums: casual buyers BA and fan buyers BF per segment.
Exposure channels are kept separate and summed into impressions; purchases are
rationed by each segment's music budget (shared wallet) and by retail stock.
"""
from __future__ import annotations

import numpy as np

from ..core import rng
from ..tables import BUFFER_DAYS, CHANNELS
from .creative import craft_score


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


# ---------------------------------------------------------------- appeal ----
def song_appeal(world, market: str, rec, act) -> np.ndarray:
    cfg = world.config
    rt = world.markets[market]
    style = np.array(rec.style, dtype=float)
    taste = rt.taste_match(style, cfg["appeal.taste_sigma"])
    craft = craft_score(world, rec)
    craft_f = cfg["appeal.craft_low"] + (cfg["appeal.craft_high"] - cfg["appeal.craft_low"]) * craft
    novelty = 1.0 + cfg["appeal.novelty_weight"] * rt.novelty * (rec.attrs["signature"] - 0.5)
    access = 0.85 + 0.3 * rec.attrs["accessibility"] * (1 - rt.novelty * 0.5)
    rec_g = np.array(act.recognition.get(market, [0.0] * rt.G))
    app_g = np.array(act.appeal.get(market, [0.5] * rt.G))
    fan_g = np.array(act.fandom.get(market, [0.0] * rt.G))
    act_term = 1.0 + cfg["appeal.act_appeal_weight"] * (app_g - 0.5) * rec_g + cfg["appeal.fandom_weight"] * fan_g
    shock = rec.reception.get(market, 0.0)
    return np.clip(np.power(taste, 0.8) * craft_f * novelty * access * act_term * np.exp(shock), 0, 3)


def draw_reception(world, market: str, rec) -> float:
    cfg = world.config
    if market not in rec.reception:
        t = rng.student_t(world.seed, cfg["listener.reception_df"], "reception", rec.id, market)
        rec.reception[market] = round(float(t * cfg["listener.reception_sigma"]), 5)
    return rec.reception[market]


# ----------------------------------------------------------- daily step ----
def daily_step(world, market: str):
    cfg = world.config
    L = cfg.tree["listener"]
    K = cfg.tree["consumption"]
    rt = world.markets[market]
    T = world.tables[market]
    AT = world.albums[market]
    d = world.date
    day = d.toordinal()
    slot = day % BUFFER_DAYS
    N = rt.population(d)

    # clear today's buffer slot
    if T.n:
        T.view("u_single")[:, :, slot] = 0.0
        T.view("aud")[:, :, slot] = 0.0
    if AT.n:
        AT.view("u_album")[:, :, slot] = 0.0

    act_rows = np.nonzero(T.active & (T.released <= day))[0] if T.n else np.array([], dtype=int)
    single_units = np.zeros((len(act_rows), rt.G))
    if len(act_rows):
        r = act_rows
        A = T.view("A")[r]
        C = T.view("C")[r]
        E_prev = T.view("E")[r]
        # --- exposure channels (impressions per capita today) --------------------
        spins = rt.rot_spins[T.view("radio_tier")[r]] * T.view("radio_share")[r]   # (n,F) station-weighted
        I_radio = spins @ (rt.format_reach * rt.listen_share)              # (n,G)
        aud = spins * rt.format_audience(d) * rt.listen_share              # persons reached (n,F)
        plays = rt.rot_plays[T.view("video_tier")[r]]                      # (n,V)
        I_video = plays @ (rt.channel_reach * rt.view_share)
        I_tv = np.zeros_like(I_radio)
        today = d.isoformat()
        for item in world.schedule:
            if item.get("kind") == "tv" and item["date"] == today and item.get("market") == market:
                i = T.index.get(item["song"])
                if i is not None:
                    pos = np.nonzero(r == i)[0]
                    if len(pos):
                        I_tv[pos[0]] += np.array(item["impressions"])
        age = day - T.view("released")[r]
        fresh = (age >= 0) & (age < 7)
        I_fans = T.view("fanvec")[r] * L["fan_impressions"] / 7.0 * fresh[:, None]
        talk = T.view("talk")[r]
        contagion = E_prev + L["wom_nonlinear"] * E_prev ** 2
        I_wom = L["wom_k"] * talk[:, None] * (contagion @ rt.contacts.T)
        vis = T.view("vis")[r]
        I_vis = L["chart_visibility"] * vis[:, None] * (0.5 + rt.conformity)[None, :]
        I = I_radio + I_video + I_tv + I_fans + I_wom + I_vis

        # --- first exposure is limited by each channel's actual reach ----------------
        # (a station's playlist can only reach that station's listeners)
        log_miss = np.zeros_like(I_radio)
        q_radio = 1 - np.exp(-spins * rt.listen_share * L["aware_k"])        # (n,F) per listener
        for f in range(rt.F):
            log_miss += np.log1p(-rt.format_reach[f][None, :] * q_radio[:, f:f + 1])
        q_video = 1 - np.exp(-plays * rt.view_share * L["aware_k"])
        for v in range(rt.V):
            log_miss += np.log1p(-np.minimum(0.999, rt.channel_reach[v][None, :] * q_video[:, v:v + 1]))
        log_miss += np.log1p(-np.minimum(0.999, I_tv / max(1e-9, rt.tv_exposures)))
        log_miss += np.log1p(-np.minimum(0.999, T.view("fanvec")[r] * fresh[:, None] / 3.0))
        log_miss += -(I_wom + I_vis) * L["aware_k"]
        P_new = 1 - np.exp(log_miss)

        # --- awareness, liking, engagement ----------------------------------------
        A_new = A + (1 - A) * P_new
        C_new = C + I
        x = C_new / np.maximum(A_new, 1e-9)
        hook = T.view("hook")[r][:, None]
        depth = T.view("depth")[r][:, None]
        base = L["hook_floor"] + (1 - L["hook_floor"]) * hook
        tau = L["tau_base"] + L["tau_span"] * depth
        grow = (1 - base) * (1 - np.exp(-x / tau))
        peak = L["peak_base"] + L["peak_span"] * depth
        burn = L["burn_base"] + L["burn_span"] * depth
        fatigue = np.exp(-np.maximum(0.0, x - peak) / burn)
        social = 1 + L["social_proof"] * vis[:, None] * rt.conformity[None, :]
        like = T.view("appeal")[r] * (base + grow) * fatigue * social
        E = A_new * _sigmoid((like - L["engage_threshold"]) / L["engage_spread"])
        T.view("A")[r] = A_new
        T.view("C")[r] = C_new
        T.view("E")[r] = E
        T.view("aud")[r, :, slot] = aud
        wk = T.view("wk_imp")
        for ci, Ich in enumerate((I_radio, I_video, I_tv, I_fans, I_wom, I_vis)):
            wk[r, ci] += (Ich * N).sum(axis=1)
        popE = (E * N).sum(axis=1) / N.sum()
        T.view("peakE")[r] = np.maximum(T.view("peakE")[r], popE)

        # --- single purchases ---------------------------------------------------
        avail = T.view("commercial")[r].astype(float) * rt.singles_market(d)
        target = E * rt.single_prop[None, :] * avail[:, None]
        gap = np.maximum(0.0, target - T.view("BS")[r])
        single_units = gap * K["single_rate"] * N[None, :]

        # retire songs nobody engages with any more
        old = age > L["retire_after_days"]
        dead = old & (E.max(axis=1) < L["retire_engaged_below"]) & (T.view("radio_tier")[r].max(axis=1) == 0)
        if dead.any():
            T.view("active")[r[dead]] = False

    # --- album purchases --------------------------------------------------------
    alb_rows = np.nonzero(AT.active & (AT.released <= day))[0] if AT.n else np.array([], dtype=int)
    casual_units = np.zeros((len(alb_rows), rt.G))
    fan_units = np.zeros((len(alb_rows), rt.G))
    if len(alb_rows):
        Erows = T.view("E") if T.n else np.zeros((0, rt.G))
        for k, a in enumerate(alb_rows):
            focus = [T.index[s] for s in AT.focus[a] if s in T.index]
            if focus:
                Ef = Erows[focus]
                interest = 1 - np.prod(1 - Ef * K["album_value_tracks"], axis=0)
            else:
                interest = np.zeros(rt.G)
            value = AT.view("value")[a]
            interest = np.maximum(interest, AT.view("interest")[a] * K["album_interest_memory"])
            AT.view("interest")[a] = interest
            target = interest * rt.album_prop * value
            casual_units[k] = np.maximum(0.0, target - AT.view("BA")[a]) * K["album_rate"] * N
            fan_target = AT.view("fanvec")[a] * K["fan_album_buy"]
            fan_units[k] = np.maximum(0.0, fan_target - AT.view("BF")[a]) * (1.0 / K["fan_urgency_days"]) * N

    # --- shared wallet: ration by segment budget --------------------------------
    p_single = rt.price("single", d)
    p_album = rt.price("album", d)
    desire = single_units.sum(axis=0) * p_single + (casual_units + fan_units).sum(axis=0) * p_album
    cap = rt.daily_budget(d) * K["wallet_slack"]
    scale = np.where(desire > cap, cap / np.maximum(desire, 1e-9), 1.0)
    single_units *= scale[None, :]
    casual_units *= scale[None, :]
    fan_units *= scale[None, :]

    # --- retail stock -------------------------------------------------------------
    if len(act_rows):
        for k, i in enumerate(act_rows):
            rid = world.recordings[T.ids[i]].single_release
            rel = world.releases.get(rid) if rid else None
            tot = single_units[k].sum()
            if rel is None or tot <= 0:
                continue
            if tot > rel.stock:
                single_units[k] *= rel.stock / tot
                tot = rel.stock
                rel.stockout_days += 1
            rel.stock -= tot
            rel.sold += tot
        T.view("BS")[act_rows] += single_units / N[None, :]
        T.view("u_single")[act_rows, :, slot] = single_units
    if len(alb_rows):
        for k, a in enumerate(alb_rows):
            rel = world.releases[AT.ids[a]]
            tot = casual_units[k].sum() + fan_units[k].sum()
            if tot <= 0:
                continue
            if tot > rel.stock:
                rel.stockout_days += 1
                f = rel.stock / tot
                casual_units[k] *= f
                fan_units[k] *= f
                tot = rel.stock
            rel.stock -= tot
            rel.sold += tot
        AT.view("BA")[alb_rows] += casual_units / N[None, :]
        AT.view("BF")[alb_rows] += fan_units / N[None, :]
        AT.view("u_album")[alb_rows, :, slot] = casual_units + fan_units
        # albums whose demand has dried up stop being simulated
        for k, a in enumerate(alb_rows):
            if day - AT.view("released")[a] > 540 and (casual_units[k].sum() + fan_units[k].sum()) < 1:
                AT.view("active")[a] = False


# ---------------------------------------------------------- window sums ----
def window_slots(end_day: int, days: int) -> list[int]:
    return [(end_day - k) % BUFFER_DAYS for k in range(days)]


def song_units(world, market, end_day, days, segments=None) -> np.ndarray:
    T = world.tables[market]
    if not T.n:
        return np.zeros(0)
    u = T.view("u_single")[:, :, window_slots(end_day, days)].sum(axis=2)    # (n,G)
    if segments is not None:
        u = u[:, segments]
    return u.sum(axis=1)


def song_audience(world, market, end_day, days, formats=None) -> np.ndarray:
    T = world.tables[market]
    if not T.n:
        return np.zeros(0)
    a = T.view("aud")[:, :, window_slots(end_day, days)].sum(axis=2)        # (n,F)
    if formats is not None:
        a = a[:, formats]
    return a.sum(axis=1)


def album_units(world, market, end_day, days, segments=None) -> np.ndarray:
    AT = world.albums[market]
    if not AT.n:
        return np.zeros(0)
    u = AT.view("u_album")[:, :, window_slots(end_day, days)].sum(axis=2)
    if segments is not None:
        u = u[:, segments]
    return u.sum(axis=1)


CHANNEL_NAMES = CHANNELS
