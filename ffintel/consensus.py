"""Composite market rating from outside rankings, and our own vs. the market.

Sources (each converted to a positional rank, then averaged with weights):
  - FantasyPros rest-of-season consensus  (aggregates 100+ experts from ESPN, CBS,
    Yahoo, NFL.com, PFF, The Athletic, etc.)                         weight 0.60
  - ESPN's projections (from your league): its current points per game
    (this week's projection) times the games each player has left    weight 0.25
  - FantasyPros weekly consensus (skipped for players on bye or out)  weight 0.15
Missing sources are skipped and the remaining weights re-normalised.
"""
import numpy as np
import pandas as pd

from . import sources

WEIGHTS = {"fp_ros": 0.60, "espn": 0.25, "fp_week": 0.15}


def fantasypros_ranks() -> pd.DataFrame:
    try:
        e = sources.fantasypros_ecr()
        ids = sources.player_ids()[["fantasypros_id", "gsis_id"]].dropna()
    except Exception as ex:  # keep running without it
        print("FantasyPros consensus unavailable:", ex)
        return pd.DataFrame(columns=["player_id"])
    ids["fantasypros_id"] = pd.to_numeric(ids.fantasypros_id, errors="coerce")
    e["id"] = pd.to_numeric(e["id"], errors="coerce")
    out = []
    for label, prefix in (("fp_ros", "redraft-"), ("fp_week", "weekly-")):
        sub = e[e.page_type.isin([prefix + p for p in ("qb", "rb", "wr", "te")])]
        sub = sub[["id", "ecr", "sd", "best", "worst", "player_owned_espn", "scrape_date"]].rename(
            columns={"ecr": label, "sd": f"{label}_sd", "best": f"{label}_best", "worst": f"{label}_worst",
                     "player_owned_espn": f"{label}_own", "scrape_date": f"{label}_date"})
        out.append(sub)
    dyn = e[e.page_type.isin(["dynasty-" + p for p in ("qb", "rb", "wr", "te")])][["id", "ecr"]].rename(
        columns={"ecr": "fp_dyn"})
    m = out[0].merge(out[1], on="id", how="outer").merge(dyn, on="id", how="outer")
    m = m.merge(ids, left_on="id", right_on="fantasypros_id").rename(columns={"gsis_id": "player_id"})
    return m.drop(columns=["id", "fantasypros_id"]).drop_duplicates("player_id")


def composite(df: pd.DataFrame, espn_proj: dict | None) -> pd.DataFrame:
    """Adds consensus rank, market-implied value and the over/under verdict."""
    df = df.copy()
    fp = fantasypros_ranks()
    df = df.merge(fp, on="player_id", how="left")
    # ESPN: its current points-per-game view times the games he has left (byes, injuries)
    df["espn_rate"] = df.player_id.map(espn_proj or {})
    df["espn_proj"] = df.espn_rate * df.ros_games.fillna(0)
    # a WEEKLY rank says nothing about the rest of the season for a player on bye or
    # sitting out this week (FantasyPros ranks them ~90th), so skip it for them
    if "fp_week" in df:
        absent = df.on_bye.fillna(False).astype(bool) | (df.play_prob.fillna(1) < 0.5)
        df.loc[absent, "fp_week"] = np.nan
    # re-rank each source within position among our player universe so scales match
    for src in ("fp_ros", "fp_week"):
        if src in df:
            df[src + "_r"] = df.groupby("position")[src].rank(method="min")
    df["espn_r"] = df.groupby("position").espn_proj.rank(ascending=False, method="min")

    num = np.zeros(len(df))
    den = np.zeros(len(df))
    for src, w in WEIGHTS.items():
        col = src + "_r"
        if col in df:
            v = df[col].values
            ok = ~np.isnan(v)
            num[ok] += w * v[ok]
            den[ok] += w
    df["consensus_pos_rank_raw"] = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    df["consensus_sources"] = [sum(pd.notna(r.get(s + "_r")) for s in WEIGHTS) for _, r in df.iterrows()]
    df["consensus_pos_rank"] = df.groupby("position").consensus_pos_rank_raw.rank(method="first")

    # own positional rank by rest-of-season points (injuries and byes included)
    df["own_pos_rank"] = df.groupby("position").ros_points.rank(ascending=False, method="first")

    # translate the market's rank into points using our own curve at that rank
    implied = np.full(len(df), np.nan)
    for pos, grp in df.groupby("position"):
        curve = np.sort(grp.ros_points.values)[::-1]
        idx = grp.index
        r = grp.consensus_pos_rank.values
        ok = ~np.isnan(r)
        implied[df.index.get_indexer(idx[ok])] = np.interp(r[ok], np.arange(1, len(curve) + 1), curve)
    df["market_ros_points"] = implied
    df["value_gap"] = df.ros_points - df.market_ros_points
    games = df.ros_games.clip(lower=1)
    df["gap_ppg"] = df.value_gap / games
    df["rank_gap"] = df.consensus_pos_rank - df.own_pos_rank  # + means we like him more

    depth = df.position.map({"QB": 20, "TE": 18}).fillna(45)  # fantasy-relevant range
    relevant = (df.own_pos_rank <= depth) | (df.consensus_pos_rank <= depth)
    big_rank_move = df.rank_gap.abs() >= np.maximum(3, 0.25 * np.fmin(df.own_pos_rank, df.consensus_pos_rank))
    df["verdict"] = np.select(
        [relevant & (df.gap_ppg >= 1.5) & big_rank_move & (df.rank_gap > 0),
         relevant & (df.gap_ppg <= -1.5) & big_rank_move & (df.rank_gap < 0)],
        ["Undervalued", "Overvalued"], "")

    # Star guardrail: never call a proven star "overvalued" off a slow start alone.
    # Only a structural reason (injury, lost snaps, new team) can do that.
    snap_drop = (df.get("l2_snap") < df.get("last_season_snap") - 0.10).fillna(False)
    moved = (df.last_team.notna() & (df.last_team != df.team)) if "last_team" in df else False
    structural = df.inj_status.notna() | (df.role_change != 0) | snap_drop | moved
    guard = df.star & (df.verdict == "Overvalued") & ~structural
    df.loc[guard, "verdict"] = ""
    df["note"] = np.where(guard, "Star guardrail: slow start, but role and health look normal", "")
    df.loc[df.star & (df.verdict == "Overvalued") & structural, "note"] = "Proven star, but something structural changed"
    hurt = df.inj_status.isin(["LEFT GAME", "OUT", "IR", "SEASON", "DOUBTFUL", "PUP"])
    df.loc[(df.verdict == "Overvalued") & hurt, "note"] = "Mostly injury: the consensus may not have priced it in yet"
    return df
