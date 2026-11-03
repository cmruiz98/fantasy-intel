"""Team defenses (D/ST) and kickers: fantasy points, metrics, and week-by-week projections.

Points are computed from nflverse team box scores with ESPN's standard scoring, so they
exist for every team and season (history included) and don't depend on ESPN being
reachable. When your league is connected, the projections are rescaled so their average
matches what ESPN actually credited D/STs and kickers in YOUR league's scoring.

ESPN standard D/ST: sack 1, interception 2, fumble recovery 2, defensive or return TD 6,
safety 2, blocked kick 2; points allowed 0: +5, 1-6: +4, 7-13: +3, 14-17: +1, 18-27: 0,
28-34: -1, 35-45: -3, 46+: -5; yards allowed <100: +5, 100-199: +3, 200-299: +2,
300-349: 0, 350-399: -1, 400-449: -3, 450-499: -5, 500-549: -6, 550+: -7.
ESPN standard kicker: FG 0-39 yds 3, 40-49 4, 50+ 5, missed FG -1, PAT 1, missed PAT -1.

Projection for a given week (fit on 2023-24, checked on 2025; see the coefficients below):
  D/ST = intercept + a * his D/ST points per game so far (shrunk toward average early on)
         + b * points per game opposing D/STs have scored against this week's opponent
         + c * (opponent's Vegas implied total, when a line is posted)
  K    = intercept + a * his team's kicker points per game so far
         + b * points per game kickers have scored against this week's opponent's defense
         + c * (own Vegas implied total, when a line is posted)
"""
import numpy as np
import pandas as pd

from . import config, sources

PA_TIERS = [(0, 5), (6, 4), (13, 3), (17, 1), (27, 0), (34, -1), (45, -3), (999, -5)]
YA_TIERS = [(99, 5), (199, 3), (299, 2), (349, 0), (399, -1), (449, -3), (499, -5), (549, -6), (99999, -7)]
SHRINK_GAMES = 4   # a team's own rate starts this many "average" games deep
TEAM_NAMES = {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills", "CAR": "Panthers", "CHI": "Bears",
    "CIN": "Bengals", "CLE": "Browns", "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
    "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs", "LA": "Rams", "LAC": "Chargers",
    "LV": "Raiders", "MIA": "Dolphins", "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
    "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks", "SF": "49ers", "TB": "Buccaneers",
    "TEN": "Titans", "WAS": "Commanders"}
# ESPN proTeamId -> nflverse abbreviation (D/ST "players" are teams)
ESPN_PRO_TEAM = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB",
                 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LA", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO",
                 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB",
                 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"}

# Fitted by measure() on 2023-24 team-weeks (weeks 4+), checked on 2025 (mean absolute error):
#   D/ST with a line 4.28, without 4.41, his own average alone 4.66, league average 4.71
#   K    with a line 3.84, without 3.86, his own average alone 3.91, league average 3.90
# With a line, the opponent's implied total does most of the work for a defense (-0.62 points
# per point the opponent is expected to score). Weeks without a line use the second model.
DST_COEF = {"const": 3.777, "own": 0.017, "opp": 0.152, "vegas": -0.616, "vegas_mean": 22.0}
DST_COEF_NL = {"const": -2.13, "own": 0.46, "opp": 0.937, "vegas": 0.0, "vegas_mean": 22.0}
K_COEF = {"const": 5.7, "own": 0.177, "opp": 0.087, "vegas": 0.195, "vegas_mean": 22.0}
K_COEF_NL = {"const": 3.325, "own": 0.36, "opp": 0.191, "vegas": 0.0, "vegas_mean": 22.0}
# weekly standard deviation around the projection (2025 residuals), for the playoff simulation
DST_SD, K_SD = 5.5, 4.8


def dst_id(team: str) -> str:
    return f"DST_{team}"


def _tier(v, tiers):
    for cap, pts in tiers:
        if v <= cap:
            return pts
    return tiers[-1][1]


def team_weeks(seasons) -> pd.DataFrame:
    """One row per team-game: D/ST and kicker fantasy points plus the components."""
    sched = sources.schedule()
    rows = []
    for s in seasons:
        t = sources.team_stats(s)
        if t is None or t.empty:
            continue
        t = t[t.season_type == "REG"].copy()
        g = sched[(sched.season == s) & (sched.game_type == "REG") & sched.result.notna()]
        score = {}
        for r in g.itertuples(index=False):
            score[(r.home_team, int(r.week))] = (float(r.home_score), float(r.away_score), 1)
            score[(r.away_team, int(r.week))] = (float(r.away_score), float(r.home_score), 0)
        opp_off = t.set_index(["team", "week"])
        for r in t.itertuples(index=False):
            key = (r.team, int(r.week))
            if key not in score:
                continue
            pf, pa, home = score[key]
            o = opp_off.loc[(r.opponent_team, int(r.week))] if (r.opponent_team, int(r.week)) in opp_off.index else None
            ya = np.nan
            if o is not None:
                ya = float(o.passing_yards or 0) - float(o.sack_yards_lost or 0) + float(o.rushing_yards or 0)
            n = lambda x: float(x) if pd.notna(x) else 0.0
            sacks, ints = n(r.def_sacks), n(r.def_interceptions)
            fr = n(r.fumble_recovery_opp)
            tds = n(r.def_tds) + n(r.special_teams_tds)
            saf = n(r.def_safeties)
            blocks = n(r.def_punt_blocks) + n(r.def_fg_blocks)
            dst = sacks + 2 * ints + 2 * fr + 6 * tds + 2 * saf + 2 * blocks + _tier(pa, PA_TIERS) \
                + (_tier(ya, YA_TIERS) if pd.notna(ya) else 0)
            fg = {b: n(getattr(r, f"fg_made_{b}")) for b in ("0_19", "20_29", "30_39", "40_49", "50_59")}
            fg60 = n(r.fg_made_60_)
            k = 3 * (fg["0_19"] + fg["20_29"] + fg["30_39"]) + 4 * fg["40_49"] + 5 * (fg["50_59"] + fg60) \
                - n(r.fg_missed) + n(r.pat_made) - n(r.pat_missed)
            rows.append({"season": s, "week": int(r.week), "team": r.team, "opp": r.opponent_team, "home": home,
                         "points_for": pf, "points_allowed": pa, "yards_allowed": ya,
                         "sacks": sacks, "ints": ints, "fum_rec": fr, "def_td": tds, "safeties": saf,
                         "blocks": blocks, "qb_hits": n(r.def_qb_hits), "dst_pts": dst,
                         "fg_made": n(r.fg_made), "fg_att": n(r.fg_att), "fg_40_49": fg["40_49"],
                         "fg_50": fg["50_59"] + fg60, "fg_att_50": fg["50_59"] + fg60 + n(r.fg_missed_50_59) + n(r.fg_missed_60_),
                         "fg_long": n(r.fg_long), "pat_made": n(r.pat_made), "pat_att": n(r.pat_att), "k_pts": k})
    return pd.DataFrame(rows)


def _to_date(tw: pd.DataFrame) -> pd.DataFrame:
    """Per team-week: the team's own and its opponent's averages over PRIOR weeks of the season,
    shrunk toward the league average (so week-1 numbers aren't wild)."""
    tw = tw.sort_values(["season", "team", "week"]).copy()
    lg = tw.groupby("season")[["dst_pts", "k_pts"]].transform("mean")
    g = tw.groupby(["season", "team"])
    for col, name in (("dst_pts", "own_dst"), ("k_pts", "own_k")):
        s = g[col].transform(lambda x: x.shift().cumsum())
        c = g[col].transform(lambda x: x.shift().notna().cumsum())
        tw[name] = (s.fillna(0) + SHRINK_GAMES * lg[col]) / (c + SHRINK_GAMES)
    # what each team's OFFENSE gives up: D/ST and K points scored against it
    allowed = tw[["season", "week", "opp", "dst_pts", "k_pts"]].rename(columns={"opp": "team"}).sort_values(["season", "team", "week"])
    ga = allowed.groupby(["season", "team"])
    for col, name in (("dst_pts", "off_gives_dst"), ("k_pts", "def_gives_k")):
        s = ga[col].transform(lambda x: x.shift().cumsum())
        c = ga[col].transform(lambda x: x.shift().notna().cumsum())
        allowed[name] = (s.fillna(0) + SHRINK_GAMES * allowed.groupby("season")[col].transform("mean")) / (c + SHRINK_GAMES)
    tw = tw.merge(allowed[["season", "week", "team", "off_gives_dst", "def_gives_k"]].rename(columns={"team": "opp"}),
                  on=["season", "week", "opp"], how="left")
    return tw


def _lines(sched: pd.DataFrame) -> pd.DataFrame:
    s = sched[(sched.game_type == "REG")].dropna(subset=["total_line", "spread_line"])
    rows = []
    for g in s.itertuples(index=False):
        h = g.total_line / 2 + g.spread_line / 2
        rows += [(g.season, int(g.week), g.home_team, h, g.total_line - h), (g.season, int(g.week), g.away_team, g.total_line - h, h)]
    return pd.DataFrame(rows, columns=["season", "week", "team", "own_imp", "opp_imp"])


def predict(own, opp, vegas_imp, coef):
    v = np.where(pd.notna(vegas_imp), np.asarray(vegas_imp, dtype=float) - coef["vegas_mean"], 0.0)
    return coef["const"] + coef["own"] * np.asarray(own) + coef["opp"] * np.asarray(opp) + coef["vegas"] * v


def measure():
    """Fit and check the weekly D/ST and K models. Run by hand: python -c 'from ffintel import dstk; dstk.measure()'."""
    tw = _to_date(team_weeks([2023, 2024, 2025]))
    tw = tw.merge(_lines(sources.schedule()), on=["season", "week", "team"], how="left")
    tw = tw[tw.week >= 4]
    tr, te = tw[tw.season < 2025], tw[tw.season == 2025]
    out = {}
    for label, y, own, opp, veg in (("dst", "dst_pts", "own_dst", "off_gives_dst", "opp_imp"),
                                    ("k", "k_pts", "own_k", "def_gives_k", "own_imp")):
        X = np.column_stack([np.ones(len(tr)), tr[own], tr[opp], tr[veg].fillna(22.0) - 22.0])
        b = np.linalg.lstsq(X, tr[y].values, rcond=None)[0]
        coef = {"const": b[0], "own": b[1], "opp": b[2], "vegas": b[3], "vegas_mean": 22.0}
        p = predict(te[own], te[opp], te[veg], coef)
        mae, mae_own = np.mean(np.abs(te[y] - p)), np.mean(np.abs(te[y] - te[own]))
        sd = float(np.std(te[y] - p))
        out[label] = (coef, round(mae, 3), round(mae_own, 3), round(sd, 2))
        print(label, {k: round(v, 3) for k, v in coef.items()}, "2025 MAE", round(mae, 3),
              "vs own average", round(mae_own, 3), "residual SD", round(sd, 2))
    return out


def build(season: int, plan_week: int, rem: dict, lines: dict, players: pd.DataFrame,
          espn_units: dict | None = None, rostered_k: list | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(D/ST + K player rows ready to merge with skill players, per-team metric table).

    espn_units: {"dst": {team: [weekly league points]}, "k": {gsis_id: (team, [weekly league points])}}
    from your ESPN league, used to rescale to your league's scoring and to know who kicks for whom.
    """
    hist = team_weeks([season - 1, season])
    cur = hist[hist.season == season]
    prev = hist[hist.season == season - 1]
    lg_dst = cur.dst_pts.mean() if len(cur) else prev.dst_pts.mean()
    lg_k = cur.k_pts.mean() if len(cur) else prev.k_pts.mean()
    teams = sorted(set(cur.team) | set(prev.team) | set(rem.get("weeks", {}).keys()))

    def rate(col, team, lg):
        c = cur[cur.team == team][col]
        p = prev[prev.team == team][col]
        prior = (p.mean() * len(p) + lg * SHRINK_GAMES) / (len(p) + SHRINK_GAMES) if len(p) else lg
        return float((c.sum() + prior * SHRINK_GAMES) / (len(c) + SHRINK_GAMES)), len(c)

    allowed_dst = cur.groupby("opp").dst_pts.agg(["sum", "count"])
    allowed_k = cur.groupby("opp").k_pts.agg(["sum", "count"])

    def gives(tab, team, lg):
        if team in tab.index:
            r = tab.loc[team]
            return float((r["sum"] + lg * SHRINK_GAMES) / (r["count"] + SHRINK_GAMES))
        return float(lg)

    weeks = list(range(plan_week, config.LAST_FANTASY_WEEK + 1))
    sched = sources.schedule()
    s = sched[(sched.season == season) & (sched.game_type == "REG")]
    opp_of = {}
    for g in s.itertuples(index=False):
        opp_of[(g.home_team, int(g.week))] = g.away_team
        opp_of[(g.away_team, int(g.week))] = g.home_team
    future_lines = _lines(sched)
    future_lines = future_lines[future_lines.season == season].set_index(["team", "week"])

    # scale to the league's scoring if ESPN tells us what it actually credited
    scale_dst = scale_k = 1.0
    if espn_units:
        ours = cur.set_index(["team", "week"])
        a = b = 0.0
        for team, pts in (espn_units.get("dst") or {}).items():
            for w, v in pts.items():
                if (team, w) in ours.index and v is not None:
                    a += v
                    b += float(ours.loc[(team, w), "dst_pts"])
        if b > 50:
            scale_dst = min(max(a / b, 0.5), 2.0)
        a = b = 0.0
        for gid, (team, pts) in (espn_units.get("k") or {}).items():
            for w, v in pts.items():
                if (team, w) in ours.index and v is not None:
                    a += v
                    b += float(ours.loc[(team, w), "k_pts"])
        if b > 50:
            scale_k = min(max(a / b, 0.5), 2.0)

    # who kicked for each team most recently this season (box scores), when ESPN isn't connected
    recent_k = {}
    ws = sources.weekly_stats(season)
    if ws is not None and len(ws) and "fg_att" in ws:
        kk = ws[(ws.position == "K") & ((ws.fg_att.fillna(0) + ws.pat_att.fillna(0)) > 0)].sort_values("week")
        recent_k = kk.groupby("team").player_id.last().to_dict()
    rows, metrics = [], []
    for team in teams:
        own_d, n_d = rate("dst_pts", team, lg_dst)
        own_k, _ = rate("k_pts", team, lg_k)
        wk_d, wk_k, opps = [], [], []
        for w in weeks:
            o = opp_of.get((team, w))
            opps.append(o)
            if o is None:
                wk_d.append(0.0)
                wk_k.append(0.0)
                continue
            if w == plan_week and lines.get(team):
                own_imp, opp_imp = lines[team]["implied"], lines.get(o, {}).get("implied")
            elif (team, w) in future_lines.index:
                own_imp, opp_imp = future_lines.loc[(team, w), "own_imp"], future_lines.loc[(team, w), "opp_imp"]
            else:
                own_imp = opp_imp = np.nan
            d = float(predict([own_d], [gives(allowed_dst, o, lg_dst)], [opp_imp],
                              DST_COEF if pd.notna(opp_imp) else DST_COEF_NL)[0])
            k = float(predict([own_k], [gives(allowed_k, o, lg_k)], [own_imp],
                              K_COEF if pd.notna(own_imp) else K_COEF_NL)[0])
            wk_d.append(round(max(d, 0.0) * scale_dst, 2))
            wk_k.append(round(max(k, 0.0) * scale_k, 2))
        c = cur[cur.team == team]
        g = max(len(c), 1)
        m = {"team": team, "games": len(c),
             "dst_ppg": round(c.dst_pts.mean() * scale_dst, 2) if len(c) else None,
             "sacks_pg": round(c.sacks.sum() / g, 2), "takeaways_pg": round((c.ints.sum() + c.fum_rec.sum()) / g, 2),
             "ints": int(c.ints.sum()), "fum_rec": int(c.fum_rec.sum()), "def_td": int(c.def_td.sum()),
             "safeties": int(c.safeties.sum()), "blocks": int(c.blocks.sum()), "qb_hits_pg": round(c.qb_hits.sum() / g, 1),
             "pa_pg": round(c.points_allowed.mean(), 1) if len(c) else None,
             "ya_pg": round(c.yards_allowed.mean(), 1) if len(c) else None,
             "k_ppg": round(c.k_pts.mean() * scale_k, 2) if len(c) else None,
             "fg_made": int(c.fg_made.sum()), "fg_att": int(c.fg_att.sum()),
             "fg_pct": round(c.fg_made.sum() / c.fg_att.sum(), 3) if c.fg_att.sum() else None,
             "fg_40_49": int(c.fg_40_49.sum()), "fg_50": int(c.fg_50.sum()), "fg_att_50": int(c.fg_att_50.sum()),
             "fg_long": int(c.fg_long.max()) if len(c) else None, "fg_att_pg": round(c.fg_att.sum() / g, 2),
             "pat_made": int(c.pat_made.sum()), "pat_att": int(c.pat_att.sum()),
             "off_gives_dst": round(gives(allowed_dst, team, lg_dst) * scale_dst, 2),
             "def_gives_k": round(gives(allowed_k, team, lg_k) * scale_k, 2)}
        metrics.append(m)
        games_left = sum(1 for o in opps if o is not None)
        name = TEAM_NAMES.get(team, team)
        base = {"team": team, "on_bye": opps[0] is None if opps else True, "opponent": opps[0] if opps else None,
                "rem_weeks": games_left, "ros_games": games_left, "exp_missed": 0.0, "play_prob": 1.0,
                "opps": opps, "metrics": m}
        rows.append({**base, "player_id": dst_id(team), "name": f"{name} D/ST", "position": "D/ST",
                     "proj_ppg": round(own_d * scale_dst, 2), "week_proj": wk_d[0] if wk_d else 0.0,
                     "wk_pts": wk_d, "wk_mkt": wk_d, "ros_points": round(sum(wk_d), 1)})
        kicker = None
        if espn_units and espn_units.get("k"):
            # the team's kicker now = whoever kicked for them most recently
            cand = [(gid, max(p) if p else 0, len(p)) for gid, (t, p) in espn_units["k"].items() if t == team]
            if cand:
                kicker = max(cand, key=lambda x: (x[1], x[2]))[0]
        if kicker is None:
            kicker = recent_k.get(team)
        if kicker:
            kname = players.loc[players.gsis_id == kicker, "display_name"]
            rows.append({**base, "player_id": kicker, "name": kname.iloc[0] if len(kname) else f"{name} K",
                         "position": "K", "proj_ppg": round(own_k * scale_k, 2), "week_proj": wk_k[0] if wk_k else 0.0,
                         "wk_pts": wk_k, "wk_mkt": wk_k, "ros_points": round(sum(wk_k), 1)})
    # a rostered kicker who isn't his team's current kicker (cut, hurt, replaced) projects to zero
    have = {r["player_id"] for r in rows}
    k_team = {gid: t for gid, (t, _) in ((espn_units or {}).get("k") or {}).items()}
    for gid in rostered_k or []:
        if gid in have:
            continue
        team = k_team.get(gid) or (players.loc[players.gsis_id == gid, "latest_team"].iloc[0]
                                   if (players.gsis_id == gid).any() else None)
        kname = players.loc[players.gsis_id == gid, "display_name"]
        n_w = len(range(plan_week, config.LAST_FANTASY_WEEK + 1))
        rows.append({"team": team, "on_bye": False, "opponent": None, "rem_weeks": 0, "ros_games": 0,
                     "exp_missed": 0.0, "play_prob": 0.0, "opps": [], "metrics": None, "player_id": gid,
                     "name": kname.iloc[0] if len(kname) else gid, "position": "K", "proj_ppg": 0.0,
                     "week_proj": 0.0, "wk_pts": [0.0] * n_w, "wk_mkt": [0.0] * n_w, "ros_points": 0.0,
                     "note": "Not his team's current kicker"})
    units = pd.DataFrame(rows)
    met = pd.DataFrame(metrics)
    for pos in ("D/ST", "K"):
        msk = units.position == pos
        units.loc[msk, "own_pos_rank"] = units[msk].ros_points.rank(ascending=False, method="first")
    units["scale"] = np.where(units.position == "D/ST", scale_dst, scale_k)
    return units, met
