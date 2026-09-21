"""Our own player ratings.

How a projection is built (points per game, rest of season):
  1. PRIOR  - what the player has done historically: last three seasons weighted
              50/33/17, counting only games where he played a real role. Rookies get
              a prior from how past rookies at their position and draft round did.
  2. NOW    - this season, blending actual points with expected points (xFP) from
              the player's workload. xFP is steadier than box scores, so a star with a
              normal workload and a quiet stat line barely moves.
  3. BLEND  - the two are combined like a credibility-weighted average. The prior
              counts as K "phantom games" (more for proven players), so two weeks
              can't erase three seasons. If his snap share has clearly changed, the
              prior is trusted less, because a real role change should move fast.
              K was tuned on the 2025 season: this blend beat history alone, this
              season alone, and usage alone at predicting the rest of the year.
Then injuries, byes and the schedule turn points-per-game into rest-of-season points.
"""
import numpy as np
import pandas as pd

from . import config, injuries

BASE_K = {"QB": 6.0, "RB": 4.0, "WR": 5.0, "TE": 5.0}
SEASON_WEIGHTS = [0.17, 0.33, 0.5]  # oldest -> newest history season
AGE_DECLINE = {"RB": (27, 0.05), "WR": (29, 0.035), "TE": (30, 0.03), "QB": (35, 0.03)}
REAL_GAME_SNAP = 0.20
STAR_DEPTH = {"QB": 8, "RB": 10, "WR": 12, "TE": 6}


def _real_games(w: pd.DataFrame) -> pd.DataFrame:
    return w[(w.snap_pct.isna()) | (w.snap_pct >= REAL_GAME_SNAP)]


def history_priors(hist: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Weighted historical points-per-game for every player with history."""
    if hist.empty:
        return pd.DataFrame(columns=["player_id"])
    h = _real_games(hist)
    seasons = sorted(h.season.unique())
    wmap = dict(zip(seasons, SEASON_WEIGHTS[-len(seasons):]))
    g = h.groupby(["player_id", "season"]).agg(
        games=("points", "size"), ppg=("points", "mean"), xfpg=("xfp", "mean"),
        snap=("snap_pct", "mean"), team=("team", "last"), pos=("position", "last")).reset_index()
    g["w"] = g.season.map(wmap) * g.games
    g["wppg"] = g.w * g.ppg
    g["wxfp"] = g.w * g.xfpg
    agg = g.groupby("player_id").agg(w=("w", "sum"), wppg=("wppg", "sum"), wxfp=("wxfp", "sum")).reset_index()
    agg["prior_ppg"] = agg.wppg / agg.w
    agg["prior_xfp"] = agg.wxfp / agg.w
    agg["prior_games_eff"] = agg.w / sum(wmap.values())  # ~ games of evidence
    last = g.sort_values("season").groupby("player_id").tail(1)
    agg = agg.merge(last[["player_id", "season", "ppg", "snap", "team", "games"]].rename(columns={
        "season": "last_season", "ppg": "last_season_ppg", "snap": "last_season_snap",
        "team": "last_team", "games": "last_season_games"}), on="player_id")
    return agg[["player_id", "prior_ppg", "prior_xfp", "prior_games_eff", "last_season",
                "last_season_ppg", "last_season_snap", "last_team", "last_season_games"]]


def rookie_priors(hist: pd.DataFrame, players: pd.DataFrame) -> dict:
    """Average first-season PPG by position and draft-round bucket."""
    def bucket(r):
        if pd.isna(r):
            return "UDFA"
        r = int(r)
        return "R1" if r == 1 else "R2" if r == 2 else "R3-4" if r <= 4 else "R5+"

    out = {}
    if hist.empty:
        return out
    p = players[["gsis_id", "rookie_season", "draft_round"]].rename(columns={"gsis_id": "player_id"})
    h = _real_games(hist).merge(p, on="player_id")
    h = h[h.season == h.rookie_season]
    g = h.groupby(["player_id", "position", "draft_round"], dropna=False).agg(
        games=("points", "size"), ppg=("points", "mean")).reset_index()
    g = g[g.games >= 3]
    g["b"] = g.draft_round.map(bucket)
    for (pos, b), grp in g.groupby(["position", "b"]):
        out[(pos, b)] = float(grp.ppg.median())
    out["_bucket"] = bucket
    return out


def season_to_date(cur: pd.DataFrame, short_games: set = frozenset()) -> pd.DataFrame:
    if cur.empty:
        return pd.DataFrame(columns=["player_id"])
    c = cur.sort_values("week")
    real = _real_games(c)
    if short_games:  # games he left injured say little about his true scoring rate
        keep = [(p, w) not in short_games for p, w in zip(real.player_id, real.week)]
        real = real[keep]
    base = real.groupby("player_id").agg(
        games=("points", "size"), cur_ppg=("points", "mean"), cur_xfp=("xfp", "mean")).reset_index()
    tot = c.groupby("player_id").agg(
        name=("name", "last"), position=("position", "last"), team=("team", "last"),
        headshot=("headshot_url", "last"), all_games=("points", "size"),
        pts_total=("points", "sum"), snap_pct=("snap_pct", "mean"), target_share=("target_share", "mean"),
        air_yards_share=("air_yards_share", "mean"), wopr=("wopr", "mean"),
        targets=("targets", "sum"), receptions=("receptions", "sum"), rec_yds=("receiving_yards", "sum"),
        carries=("carries", "sum"), rush_yds=("rushing_yards", "sum"), pass_yds=("passing_yards", "sum"),
        pass_tds=("passing_tds", "sum"), ints=("passing_interceptions", "sum"), tds=("total_tds", "sum"),
        touches=("touches", "sum"), rz_targets=("rz_targets", "sum"), ez_targets=("ez_targets", "sum"),
        rz_carries=("rz_carries", "sum"), i10_carries=("i10_carries", "sum"),
        rz_tgt_share=("rz_tgt_share", "mean"), rz_rush_share=("rz_rush_share", "mean"),
        xfp_total=("xfp", "sum"), last_week=("week", "max")).reset_index()
    last3 = c.groupby("player_id").tail(3).groupby("player_id").agg(
        l3_ppg=("points", "mean"), l3_snap=("snap_pct", "mean"), l3_tshare=("target_share", "mean"),
        l3_xfp=("xfp", "mean")).reset_index()
    last2 = c.groupby("player_id").tail(2).groupby("player_id").agg(l2_snap=("snap_pct", "mean")).reset_index()
    weekly = c.groupby("player_id").points.apply(lambda s: [round(float(x), 1) for x in s]).rename("weekly_pts")
    out = tot.merge(base, on="player_id", how="left").merge(last3, on="player_id", how="left") \
             .merge(last2, on="player_id", how="left").merge(weekly.reset_index(), on="player_id", how="left")
    out["games"] = out.games.fillna(0)
    return out


def remaining_schedule(sched: pd.DataFrame, season: int):
    """Current NFL week, the week to plan lineups for, and each team's remaining games.

    Once most of a week's games are final (e.g. only Monday night is left), lineup
    advice looks ahead to next week, while rest-of-season totals still count the
    games left this week.
    """
    s = sched[(sched.season == season) & (sched.game_type == "REG")]
    if s.empty:
        return 1, {"plan_week": 1, "weeks": {}, "opp": {}}
    unplayed = s[s.result.isna()]
    cur_week = int(unplayed.week.min()) if len(unplayed) else int(s.week.max()) + 1
    this = s[s.week == cur_week]
    done_share = this.result.notna().mean() if len(this) else 1
    plan_week = cur_week + 1 if done_share >= 0.75 else cur_week
    rem = unplayed[unplayed.week <= config.LAST_FANTASY_WEEK]
    weeks, opp = {}, {}
    for _, g in rem.iterrows():
        for t, o in ((g.home_team, g.away_team), (g.away_team, g.home_team)):
            weeks.setdefault(t, []).append(int(g.week))
            if int(g.week) == plan_week:
                opp[t] = o
    return cur_week, {"plan_week": plan_week, "weeks": weeks, "opp": opp}


def report_dates(sched: pd.DataFrame, season: int) -> dict:
    """(team, week) -> approximate time of that week's final injury report (2 days pre-game)."""
    s = sched[(sched.season == season) & (sched.game_type == "REG")]
    out = {}
    for g in s.itertuples(index=False):
        t = (pd.Timestamp(g.gameday) - pd.Timedelta(days=2)).tz_localize("America/New_York").replace(hour=16)
        out[(g.home_team, int(g.week))] = out[(g.away_team, int(g.week))] = t.isoformat()
    return out


def team_game_dates(sched: pd.DataFrame, season: int) -> dict:
    s = sched[(sched.season == season) & (sched.game_type == "REG")]
    out = {}
    for g in s.itertuples(index=False):
        for t in (g.home_team, g.away_team):
            out.setdefault(t, []).append(pd.Timestamp(g.gameday))
    return out


def matchup_factors(cur: pd.DataFrame, hist_last: pd.DataFrame) -> dict:
    """Points allowed to each position by each defense vs league average (shrunk)."""
    frames = [f for f in (hist_last, cur) if not f.empty]
    if not frames:
        return {}
    a = pd.concat(frames)
    a = a[a.opponent_team.notna()]
    by = a.groupby(["opponent_team", "position", "season", "week"]).points.sum().reset_index()
    d = by.groupby(["opponent_team", "position"]).points.agg(["mean", "size"]).reset_index()
    lg = by.groupby("position").points.mean()
    out = {}
    for _, r in d.iterrows():
        raw = r["mean"] / lg[r.position]
        shrink = r["size"] / (r["size"] + 8)
        out[(r.opponent_team, r.position)] = float(np.clip(1 + (raw - 1) * shrink, 0.85, 1.15))
    return out


def age_factor(pos, age):
    if pd.isna(age) or pos not in AGE_DECLINE:
        return 1.0
    start, rate = AGE_DECLINE[pos]
    return max(0.7, 1 - rate * max(0.0, age - start))


def build_ratings(cur, hist, players, sched, inj, extra_signals=None, short_games=frozenset()) -> tuple[pd.DataFrame, dict]:
    season = config.SEASON
    cur_week, rem = remaining_schedule(sched, season)
    priors = history_priors(hist, players)
    rookies = rookie_priors(hist, players)
    std = season_to_date(cur, short_games)

    p = players[["gsis_id", "display_name", "position", "latest_team", "birth_date", "draft_round",
                 "rookie_season", "espn_id", "status", "headshot"]].rename(
        columns={"gsis_id": "player_id"})
    p = p[p.position.isin(config.POSITIONS)]
    # universe: anyone who played this season, or active with recent history
    ids = set(std.player_id) | set(priors[priors.last_season >= season - 1].player_id)
    ids |= set(p[(p.rookie_season == season) & (p.status == "ACT") & (p.draft_round.notna())].player_id)
    df = p[p.player_id.isin(ids)].merge(std.drop(columns=["position"]), on="player_id", how="left") \
                                 .merge(priors, on="player_id", how="left")
    df = df[(df.status != "RET") & (df.status != "CUT") | df.all_games.notna()]
    df["name"] = df.name.fillna(df.display_name)
    df["team"] = df.team.fillna(df.latest_team)
    df["headshot"] = df.headshot_x.fillna(df.headshot_y) if "headshot_x" in df else df.get("headshot")
    df["age"] = (pd.Timestamp.today() - pd.to_datetime(df.birth_date, errors="coerce")).dt.days / 365.25
    df["games"] = df.games.fillna(0)

    # ---- prior
    bucket = rookies.get("_bucket")
    def rookie_prior(r):
        if bucket is None:
            return np.nan
        return rookies.get((r.position, bucket(r.draft_round)), np.nan)
    no_hist = df.prior_ppg.isna()
    df.loc[no_hist, "prior_ppg"] = df[no_hist].apply(rookie_prior, axis=1)
    df["prior_source"] = np.where(no_hist, "rookie/draft-capital baseline", "3-season history")
    df["prior_games_eff"] = df.prior_games_eff.fillna(0)
    df["prior_ppg"] = df.prior_ppg * [age_factor(pp, a) for pp, a in zip(df.position, df.age)]
    df["prior_ppg"] = df.prior_ppg.fillna(df.groupby("position").cur_ppg.transform(lambda s: s.quantile(0.2)))
    df["prior_ppg"] = df.prior_ppg.fillna(2.0)

    # proven stars: top of the position (see STAR_DEPTH) by historical PPG at the position with a real sample
    proven = df.prior_games_eff >= 10
    prank = df[proven & ~no_hist].groupby("position").prior_ppg.rank(ascending=False, method="first")
    df["star"] = False
    df.loc[prank.index, "star"] = prank <= df.loc[prank.index, "position"].map(STAR_DEPTH)

    # (A bigger prior just for stars was tested on 2025 and made projections slightly
    # worse, so stars get protection at the verdict stage instead; see consensus.py.)
    base_k = df.position.map(BASE_K)
    reliability = np.clip(df.prior_games_eff / 12, 0.35, 1.0)
    reliability = np.where(no_hist, 0.4, reliability)
    k = base_k * reliability
    # new team -> history is less relevant
    moved = df.last_team.notna() & df.team.notna() & (df.last_team != df.team)
    k = np.where(moved, k * 0.7, k)
    # role change: snap share moved >15 points vs last season -> trust current more
    role_delta = (df.l2_snap - df.last_season_snap) * 100
    df["role_change"] = np.where(role_delta.abs() >= 15, np.sign(role_delta), 0)
    k = np.where(df.role_change != 0, k * 0.5, k)
    df["prior_weight_games"] = np.round(k, 1)

    # ---- now
    skill = df.position != "QB"
    rate = np.where(skill, 0.5 * df.cur_ppg + 0.5 * df.cur_xfp, df.cur_ppg)
    n = df.games.values
    rate = np.where(n > 0, rate, 0)
    # Healthy scratches count as zero-point games: a backup who isn't playing
    # shouldn't coast on a rookie or old-team prior. Games missed injured don't count.
    team_games = cur.groupby("team").week.nunique() if len(cur) else pd.Series(dtype=float)
    hurt_weeks = {}
    if not inj.empty:
        o = inj[inj.report_status.isin(["Out", "Doubtful"])]
        hurt_weeks = o.groupby("gsis_id").week.nunique().to_dict()
    reserve = players.ngs_status_short_description.astype(str).str.match(r"R/(I|Inj|PUP|NFI)")
    on_reserve = set(players[reserve].gsis_id)
    dnp = (df.team.map(team_games).fillna(0) - df.all_games.fillna(0)
           - df.player_id.map(hurt_weeks).fillna(0)).clip(lower=0)
    dnp = np.where(df.player_id.isin(on_reserve), 0, dnp)
    df["healthy_dnp"] = dnp
    rate = np.where(n + dnp > 0, rate * n / np.maximum(n + dnp, 1e-9), 0)
    n = n + dnp
    df["proj_ppg"] = (k * df.prior_ppg + n * rate) / (k + n)
    df["current_weight"] = np.round(n / (k + n), 2)

    # ---- injuries & schedule
    team_last = cur.groupby("team").week.max() if len(cur) else pd.Series(dtype=float)
    df["team_last_week"] = df.team.map(team_last)
    played_last = set(df[df.last_week.notna() & (df.last_week >= df.team_last_week)].player_id)
    regular = (df.prior_ppg >= df.position.map({"QB": 14, "RB": 8, "WR": 8, "TE": 6})) & (df.prior_games_eff >= 6)
    missed_last = set(df[regular & df.team_last_week.notna() &
                         (df.last_week.isna() | (df.last_week < df.team_last_week))].player_id)
    signals = list(extra_signals or [])
    signals += injuries.roster_signals(players, played_last)
    signals += injuries.report_signals(inj, report_dates(sched, season))
    now = pd.Timestamp.now(tz="UTC").isoformat()
    for pid in missed_last:
        signals.append(injuries.Signal(pid, "INACTIVE", injuries.BASE_GAMES["INACTIVE"],
                                       "Did not play in his team's last game", "Box scores", now,
                                       int(df.loc[df.player_id == pid, "team_last_week"].iloc[0])))
    flagged = {s.player_id for s in signals if s.status in ("LEFT GAME", "RETURNED")}
    signals += injuries.snap_collapse(cur, flagged)
    universe = set(df.player_id)
    signals = [s for s in signals if s.player_id in universe]
    final = inj[inj.report_status.notna()] if not inj.empty else inj
    report_weeks = final.groupby("team").week.max().to_dict() if len(final) else {}
    last_played = dict(zip(df.player_id, df.last_week.fillna(0)))
    inj_df = injuries.combine(signals, report_weeks, dict(zip(df.player_id, df.team)), last_played,
                              team_last.to_dict())
    df = df.merge(inj_df, on="player_id", how="left")
    weeks = rem.get("weeks", {})
    df["rem_weeks"] = df.team.map(lambda t: len(weeks.get(t, [])))
    plan_week = rem.get("plan_week", cur_week)
    df["plays_this_week"] = df.team.map(lambda t: plan_week in weeks.get(t, []))
    missed = df.exp_missed_raw.fillna(0)
    df["exp_missed"] = np.minimum(missed, df.rem_weeks)
    df["play_prob"] = np.where(df.plays_this_week, 1 - df.p_miss_next.fillna(0).clip(0, 1), 0.0)
    df["ros_games"] = (df.rem_weeks - df.exp_missed).clip(lower=0)
    df["ros_points"] = df.proj_ppg * df.ros_games

    hist_last = hist[hist.season == season - 1] if not hist.empty else hist
    mf = matchup_factors(cur, hist_last)
    opp = rem.get("opp", {})
    df["opponent"] = df.team.map(opp)
    df["matchup"] = [mf.get((o, pp), 1.0) if isinstance(o, str) else 1.0 for o, pp in zip(df.opponent, df.position)]
    df["week_proj"] = df.proj_ppg * df.matchup * df.play_prob

    df["trend"] = np.select([df.l3_ppg > df.proj_ppg * 1.2, df.l3_ppg < df.proj_ppg * 0.8], ["up", "down"], "")
    df = df.drop(columns=[c for c in ["display_name", "latest_team", "headshot_x", "headshot_y",
                                      "birth_date", "status"] if c in df.columns])
    df = df[df.proj_ppg.notna()]
    meta = {"season": season, "week": cur_week, "plan_week": plan_week}
    return df.reset_index(drop=True), meta


def replacement_levels(df: pd.DataFrame, teams: int, lineup: dict, col="proj_ppg") -> dict:
    """PPG of the best player left after every team fills its starting lineup."""
    pool = df[df.ros_games > 0].sort_values(col, ascending=False)
    taken = set()
    for pos in config.POSITIONS:
        n = teams * lineup.get(pos, 0)
        taken |= set(pool[pool.position == pos].head(n).player_id)
    flex = teams * lineup.get("FLEX", 0)
    rest = pool[~pool.player_id.isin(taken) & pool.position.isin(["RB", "WR", "TE"])]
    taken |= set(rest.head(flex).player_id)
    sf = teams * lineup.get("OP", 0)
    rest = pool[~pool.player_id.isin(taken)]
    taken |= set(rest.head(sf).player_id)
    out = {}
    for pos in config.POSITIONS:
        left = pool[(pool.position == pos) & ~pool.player_id.isin(taken)]
        out[pos] = float(left[col].head(3).mean()) if len(left) else 0.0
    return out


def add_value(df: pd.DataFrame, teams: int, lineup: dict) -> tuple[pd.DataFrame, dict]:
    repl = replacement_levels(df, teams, lineup)
    df = df.copy()
    df["vor_ppg"] = df.proj_ppg - df.position.map(repl)
    df["ros_value"] = df.vor_ppg * df.ros_games
    df["pos_rank"] = df.groupby("position").proj_ppg.rank(ascending=False, method="first").astype(int)
    df["ovr_rank"] = df.ros_value.rank(ascending=False, method="first").astype(int)
    return df, repl
