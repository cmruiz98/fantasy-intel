"""Playoff odds: simulate the rest of your league's regular season thousands of times.

For every remaining matchup week, each team's expected score is its best lineup that week
(every slot your league starts, D/ST and kicker included) from week-by-week projections:
byes, injuries, quarterback changes, the Vegas total when a line is posted, and for
defenses and kickers the opponent they face that week. Each simulated week draws every
starter's score around his projection with the spread real players show (2022-25, by
position and scoring level), so a lineup full of boom-or-bust players is riskier than a
steady one. A team-level factor is drawn once per simulated season (sd 7%) for what no
projection knows yet: future injuries, breakouts, role changes.

Weeks already played count as they finished; a week in progress uses ESPN's live score and
live projection. Then standings are built the way ESPN seeds your league: record first,
then the tiebreaker your league uses (total points by default), division winners
guaranteed a spot if your league has divisions. Teams beyond the playoff bracket's
power of two get first-round byes (6 teams -> the top 2).
"""
import math

import numpy as np

SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "OP", "D/ST", "K"]
FITS = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "FLEX": {"RB", "WR", "TE"},
        "OP": {"QB", "RB", "WR", "TE"}, "D/ST": {"D/ST"}, "K": {"K"}}
# weekly standard deviation of a player's points around his own level: a + b * level
# (fit on every 2023-25 player-season with 8+ games, half-PPR)
SD_FIT = {"QB": (6.60, 0.063), "RB": (3.37, 0.299), "WR": (2.76, 0.372), "TE": (1.74, 0.473)}
UNIT_SD = {"D/ST": 5.5, "K": 4.8}
TEAM_SD = 0.07     # season-long uncertainty in each team's level
SIMS = 20000


def player_sd(pos, mean, scale=1.0):
    if pos in UNIT_SD:
        return UNIT_SD[pos] * scale if mean > 0 else 0.0
    a, b = SD_FIT.get(pos, (3.0, 0.35))
    return a + b * mean if mean > 0 else 0.0


def best_lineup(rows, slots, w):
    """(expected points, variance, starters) for week index w."""
    pool = sorted(rows, key=lambda r: -(r["wk"][w] if w < len(r["wk"]) else 0))
    used, mean, var, starters = set(), 0.0, 0.0, []
    for slot in SLOT_ORDER:
        for _ in range(int(slots.get(slot, 0) or 0)):
            for r in pool:
                if r["id"] not in used and r["pos"] in FITS[slot]:
                    v = r["wk"][w] if w < len(r["wk"]) else 0.0
                    used.add(r["id"])
                    mean += v
                    var += player_sd(r["pos"], v, r.get("scale", 1.0)) ** 2
                    starters.append((slot, r["id"], round(v, 1)))
                    break
    return mean, var, starters


def _seed(wins, pf, team_ids, n_playoff, divisions, h2h_rule):
    """Order of finish for one simulated season (indices into team_ids)."""
    key = [(-wins[i], -pf[i]) for i in range(len(team_ids))]
    order = sorted(range(len(team_ids)), key=lambda i: key[i])
    if divisions:
        winners = []
        for d in set(divisions.values()):
            members = [i for i in order if divisions.get(team_ids[i]) == d]
            if members:
                winners.append(members[0])
        rest = [i for i in order if i not in winners]
        made = winners + rest[:max(n_playoff - len(winners), 0)]
        made = sorted(made, key=lambda i: key[i])
        return made + [i for i in order if i not in made]
    return order


def simulate(league, rows_by_team: dict, plan_week: int, sims: int = SIMS, seed: int = 11) -> dict:
    """rows_by_team: team_id -> [{"id", "pos", "wk": [points for plan_week, plan_week+1, ...], "scale"}]."""
    rng = np.random.default_rng(seed)
    teams = sorted(league.teams)
    idx = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    slots = league.slots_full or {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "D/ST": 1, "K": 1}
    rec = league.records or {}
    wins0 = np.array([rec.get(t, {}).get("w", 0) + 0.5 * rec.get(t, {}).get("t", 0) for t in teams], float)
    pf0 = np.array([rec.get(t, {}).get("pf", 0.0) for t in teams], float)

    games = [m for m in league.schedule if m["week"] <= league.reg_weeks and m["winner"] == "UNDECIDED"]
    weeks = sorted({max(m["week"], plan_week) for m in games})
    # expected score and variance of every team in every remaining week
    proj = {}
    lineups = {}
    for t in teams:
        rows = rows_by_team.get(t, [])
        for w in weeks:
            wi = w - plan_week
            if wi < 0:
                continue
            mu, var, st = best_lineup(rows, slots, wi)
            proj[(t, w)] = (mu, var)
            lineups[(t, w)] = st
    # season-long level of each team, one draw per simulated season
    level = np.exp(rng.normal(0, TEAM_SD, size=(sims, T)) - TEAM_SD ** 2 / 2)
    wins, pf = np.tile(wins0, (sims, 1)), np.tile(pf0, (sims, 1))
    game_info = []
    for m in games:
        h, a, w = idx[m["home"]], idx[m["away"]], m["week"]
        live = m.get("live") or {}
        if w < plan_week and len(live) == 2:
            # in progress: ESPN's live score and live projection; only what's left is uncertain
            (hc, hp), (ac, ap) = live["home"], live["away"]
            sh, sa = max(2.0, 0.45 * max(hp - hc, 0)), max(2.0, 0.45 * max(ap - ac, 0))
            hs, as_ = rng.normal(hp, sh, sims), rng.normal(ap, sa, sims)
            mh, vh, ma, va = hp, sh ** 2, ap, sa ** 2
        else:
            pw = max(w, plan_week)  # a week in progress without live data: next week's lineup stands in
            mh, vh = proj.get((m["home"], pw), (0.0, 0.0))
            ma, va = proj.get((m["away"], pw), (0.0, 0.0))
            hs = rng.normal(mh * level[:, h], math.sqrt(vh))
            as_ = rng.normal(ma * level[:, a], math.sqrt(va))
        hw = (hs > as_).astype(float) + 0.5 * (hs == as_)
        wins[:, h] += hw
        wins[:, a] += 1 - hw
        pf[:, h] += hs
        pf[:, a] += as_
        game_info.append((m, h, a, mh, vh, ma, va, hw))

    n_play = min(league.playoff_teams, T)
    pow2 = 1 << max(0, (n_play - 1).bit_length())
    n_bye = pow2 - n_play if n_play > 2 else 0
    made = np.zeros((sims, T), bool)
    bye = np.zeros((sims, T), bool)
    seedpos = np.zeros((sims, T), int)
    divs = league.divisions or {}
    h2h = "H2H" in (league.seeding_rule or "").upper()
    for s in range(sims):
        order = _seed(wins[s], pf[s], teams, n_play, divs, h2h)
        for pos_, i in enumerate(order):
            seedpos[s, i] = pos_ + 1
        made[s, order[:n_play]] = True
        bye[s, order[:n_bye]] = True

    out = {"sims": sims, "playoff_teams": n_play, "byes": n_bye, "reg_weeks": league.reg_weeks,
           "seeding_rule": league.seeding_rule, "divisions": bool(divs), "weeks_left": len(weeks), "teams": {}}
    for t in teams:
        i = idx[t]
        sched = []
        for m, h, a, mh, vh, ma, va, hw in game_info:
            if i not in (h, a):
                continue
            me_home = i == h
            opp = m["away"] if me_home else m["home"]
            p_win = float(hw.mean() if me_home else 1 - hw.mean())
            w_mask = hw == 1 if me_home else hw == 0
            # how much this game moves his playoff odds
            lev = float(made[w_mask, i].mean() - made[~w_mask, i].mean()) if 0 < w_mask.mean() < 1 else 0.0
            sched.append({"week": m["week"], "opp": opp, "p_win": round(p_win, 3),
                          "my_proj": round(mh if me_home else ma, 1), "opp_proj": round(ma if me_home else mh, 1),
                          "swing": round(lev, 3), "live": bool(m.get("live")) and m["week"] < plan_week})
        w_final = wins[:, i]
        out["teams"][t] = {
            "playoff_pct": round(float(made[:, i].mean()), 4),
            "bye_pct": round(float(bye[:, i].mean()), 4) if n_bye else None,
            "first_pct": round(float((seedpos[:, i] == 1).mean()), 4),
            "last_pct": round(float((seedpos[:, i] == T).mean()), 4),
            "avg_seed": round(float(seedpos[:, i].mean()), 2),
            "proj_wins": round(float(w_final.mean()), 2),
            "proj_losses": round(float(len(sched) + sum(rec.get(t, {}).get(k, 0) for k in ("w", "l", "t")) - w_final.mean()), 2),
            "proj_pf": round(float(pf[:, i].mean()), 1),
            "wins_dist": [round(float((np.round(w_final) == k).mean()), 3) for k in range(0, league.reg_weeks + 1)],
            "ppw": round(float(np.mean([proj[(t, w)][0] for w in weeks if (t, w) in proj])) if weeks else 0.0, 1),
            "sos": round(float(np.mean([g["opp_proj"] for g in sched])) if sched else 0.0, 1),
            "schedule": sched,
            "clinched": bool(made[:, i].all()), "eliminated": bool(not made[:, i].any()),
        }
    out["lineups"] = {f"{t}|{w}": st for (t, w), st in lineups.items() if w == plan_week}
    return out
