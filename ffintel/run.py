"""Full refresh: download data -> rate players -> compare to consensus -> advise -> build site."""
import datetime as dt
import json
import math
import sys
import traceback

import numpy as np
import pandas as pd

from . import advisor, config, consensus, espn, injuries, model, report, sources, usage


def log(*a):
    print(f"[{dt.datetime.now():%H:%M:%S}]", *a, flush=True)


def clean(o):
    """Make numpy/pandas values JSON-safe."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 3)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if o is None or isinstance(o, (str, bool, int)):
        return o
    try:
        if pd.isna(o):
            return None
    except (TypeError, ValueError):
        pass
    return o


PLAYER_COLS = ["player_id", "name", "position", "team", "age", "headshot", "games", "all_games", "proj_ppg",
               "prior_ppg", "prior_source", "prior_weight_games", "current_weight", "cur_ppg", "cur_xfp",
               "l3_ppg", "weekly_pts", "trend", "role_change", "pts_total", "snap_pct", "l2_snap",
               "target_share", "l3_tshare", "air_yards_share", "wopr", "targets", "receptions", "rec_yds",
               "carries", "rush_yds", "pass_yds", "pass_tds", "ints", "tds", "touches", "rz_targets",
               "ez_targets", "rz_carries", "i10_carries", "rz_tgt_share", "rz_rush_share", "xfp_total",
               "inj_status", "inj_detail", "inj_source", "inj_updated", "inj_signals", "fill_in_for", "play_prob", "exp_missed", "ros_games", "ros_points",
               "opponent", "matchup", "week_proj", "vor_ppg", "ros_value", "pos_rank", "ovr_rank",
               "own_pos_rank", "consensus_pos_rank", "consensus_sources", "fp_ros", "fp_week", "espn_proj",
               "fp_ros_best", "fp_ros_worst", "market_ros_points", "value_gap", "gap_ppg", "rank_gap",
               "verdict", "note", "star", "owner", "owner_name", "pct_owned", "pct_change"]


def main():
    season = config.SEASON
    log(f"Season {season}")
    players = sources.players()
    try:
        ids = sources.player_ids()
    except Exception as e:
        log("ID map unavailable:", e)
        ids = None
    sched = sources.schedule()
    cur_week, rem = model.remaining_schedule(sched, season)
    plan_week = rem["plan_week"]
    log(f"Current week {cur_week}; planning lineups for week {plan_week}")

    league, league_error = None, ""
    if config.MOCK_LEAGUE:
        pass
    else:
        try:
            league = espn.fetch(players, ids, season, plan_week)
            log(f"ESPN league '{league.name}': {league.n_teams} teams, my team id {league.my_team_id}")
            if league.error:
                log(league.error)
        except Exception as e:
            league_error = str(e)
            log("ESPN league unavailable:", e)
    rec_pts = league.rec_pts if league else config.DEFAULT_REC_PTS

    log("Fitting expected-points model on past seasons")
    hist_pbp = pd.concat([sources.pbp(s) for s in config.HISTORY_SEASONS], ignore_index=True)
    xfp = usage.XFPModel(hist_pbp)
    del hist_pbp

    log("Building weekly usage tables")
    hist = pd.concat([usage.weekly_table(s, xfp, rec_pts, players) for s in config.HISTORY_SEASONS],
                     ignore_index=True)
    cur = usage.weekly_table(season, xfp, rec_pts, players)
    log(f"Current season rows: {len(cur)}; history rows: {len(hist)}")

    inj = sources.injuries(season)
    log("Gathering injury signals")
    skill = set(players[players.position.isin(config.POSITIONS)].gsis_id)
    sig, short_games, fill_ins = injuries.in_game(sources.pbp(season), players, season, skill)
    log(f"  play-by-play: {sum(s.status == 'LEFT GAME' for s in sig)} left games injured, "
        f"{sum(s.status == 'RETURNED' for s in sig)} returned")
    feed_status = {"Play-by-play": f"{len(sig)} in-game injuries"}
    espn_ids = espn._id_map(players, ids)
    nidx = injuries.name_index(players)
    game_dates = model.team_game_dates(sched, season)
    for label, fn in (("ESPN injury desk", lambda: injuries.espn_feed(espn_ids, nidx, game_dates)),
                      ("Sleeper", lambda: injuries.sleeper_feed(ids, nidx)),
                      ("ESPN news", lambda: injuries.news_feed(espn_ids, nidx)),
                      ("News wires", lambda: injuries.rss_feed(injuries.unique_names(players)))):
        try:
            got = fn()
            sig += got
            feed_status[label] = f"{len(got)} players"
            log(f"  {label}: {len(got)} signals")
        except Exception as e:
            feed_status[label] = f"unavailable ({e if isinstance(e, RuntimeError) else type(e).__name__})"
            log(f"  {label} unavailable: {e}")
    if league:
        sig += injuries.league_signals(league.injuries)
        feed_status["Your ESPN league"] = f"{len(league.injuries)} players"
    df, meta = model.build_ratings(cur, hist, players, sched, inj, sig, short_games)
    names = dict(zip(players.gsis_id, players.display_name))
    rated = dict(zip(df.player_id, df.proj_ppg))
    fill_ins = [f for f in fill_ins if f["injured_id"] in rated]
    df["fill_in_for"] = df.player_id.map({f["fill_in_id"]: f["injured"] for f in fill_ins})

    if config.MOCK_LEAGUE:
        league = espn.mock(df)
    teams = league.n_teams if league else config.DEFAULT_TEAMS
    lineup = league.lineup if league else config.DEFAULT_LINEUP
    df, repl = model.add_value(df, teams, lineup)
    df = consensus.composite(df, league.projections if league else None)
    log(f"Rated {len(df)} players; {(df.verdict != '').sum()} flagged over/undervalued")

    weeks_left = max(1, config.LAST_FANTASY_WEEK - plan_week + 1)
    out = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "season": season, "week": cur_week, "plan_week": plan_week, "weeks_left": weeks_left, "rec_pts": rec_pts,
           "replacement": repl, "lineup": lineup, "teams": teams,
           "data_through_week": int(cur.week.max()) if len(cur) else 0,
           "league": None, "league_error": league_error,
           "injury_feeds": feed_status, "fill_ins": fill_ins}

    if league and league.my_team_id:
        adv = advisor.Advisor(df, league, weeks_left)
        df = adv.df.reset_index(drop=True)
        names = {k: v["name"] for k, v in league.teams.items()}
        df["owner_name"] = df.owner.map(names)
        df["pct_owned"] = df.player_id.map(lambda p: league.ownership.get(p, (None, None))[0])
        df["pct_change"] = df.player_id.map(lambda p: league.ownership.get(p, (None, None))[1])
        log("Building waiver and trade advice")
        out["league"] = {
            "name": league.name, "mock": league.mock, "my_team": league.teams[league.my_team_id]["name"],
            "team": adv.my_team(), "waivers": adv.waivers(), "trades": adv.trade_lists(),
            "trade_ideas": adv.trade_ideas(), "note": league.error}
    elif league:
        listing = ", ".join(f"{k} = {v['name']}" for k, v in league.teams.items())
        out["league_error"] = ("Connected to ESPN but couldn't tell which team is yours. "
                               f"Set the ESPN_TEAM_ID secret to your team's number: {listing}")
        log(out["league_error"])

    for c in PLAYER_COLS:
        if c not in df:
            df[c] = None
    df = df.sort_values("ros_value", ascending=False)
    out["players"] = df[PLAYER_COLS].to_dict("records")
    if out["league"]:
        keep = set(PLAYER_COLS) | {"espn_slot", "start_this_week", "core_starter", "lineup_note", "gain_week",
                                    "score", "drop", "waiver_status", "why", "owner_name", "ros_ppw", "mkt_ppw"}
        L = out["league"]
        L["team"]["players"] = [{k: v for k, v in p.items() if k in keep} for p in L["team"]["players"]]
        L["waivers"] = [{k: v for k, v in p.items() if k in keep} for p in L["waivers"]]
        for k in ("buy_low", "sell_high"):
            L["trades"][k] = [{k2: v for k2, v in p.items() if k2 in keep} for p in L["trades"][k]]

    out = clean(out)
    config.SITE.mkdir(parents=True, exist_ok=True)
    (config.SITE / "data.json").write_text(json.dumps(out))
    df[PLAYER_COLS].to_csv(config.SITE / "rankings.csv", index=False)
    (config.SITE / "index.html").write_text(report.render(out))
    log(f"Wrote {config.SITE / 'index.html'}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
