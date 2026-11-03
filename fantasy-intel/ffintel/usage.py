"""Weekly player usage: points, snaps, shares, red-zone work and expected points (xFP)."""
import numpy as np
import pandas as pd

from . import sources

AIR_BINS = [-np.inf, 0, 5, 10, 15, 20, 30, np.inf]
TGT_ZONE_BINS = [0, 5, 10, 20, 100]
RUSH_ZONE_BINS = [0, 2, 5, 10, 20, 50, 100]


def _plays(p: pd.DataFrame) -> pd.DataFrame:
    if p.empty:
        return p
    p = p[(p.season_type == "REG") & (p.two_point_attempt.fillna(0) == 0)].copy()
    p["tgt_bucket"] = pd.cut(p.air_yards, AIR_BINS, right=False).astype(str) + "|" + \
        pd.cut(p.yardline_100, TGT_ZONE_BINS).astype(str)
    p["rush_bucket"] = pd.cut(p.yardline_100, RUSH_ZONE_BINS).astype(str)
    return p


def _targets(p):
    t = p[(p.play_type == "pass") & p.receiver_player_id.notna()].copy()
    t["catch"] = t.complete_pass.fillna(0)
    t["yds"] = t.receiving_yards.fillna(0)
    t["td"] = ((t.pass_touchdown == 1) & (t.td_player_id == t.receiver_player_id)).astype(int)
    return t


def _rushes(p):
    r = p[(p.play_type == "run") & p.rusher_player_id.notna()].copy()
    r["yds"] = r.rushing_yards.fillna(0)
    r["td"] = ((r.rush_touchdown == 1) & (r.td_player_id == r.rusher_player_id)).astype(int)
    return r


class XFPModel:
    """League-average fantasy value of each opportunity, learned from past seasons.

    A 25-yard target in the end zone is worth far more than a checkdown; a carry at
    the 2 is worth far more than one at midfield. Summing these tells us what a
    player's workload *should* produce, which is steadier than actual points.
    """

    def __init__(self, hist_pbp: pd.DataFrame):
        p = _plays(hist_pbp)
        t, r = _targets(p), _rushes(p)
        self.tgt = t.groupby("tgt_bucket")[["catch", "yds", "td"]].mean()
        self.tgt_default = t[["catch", "yds", "td"]].mean()
        self.rush = r.groupby("rush_bucket")[["yds", "td"]].mean()
        self.rush_default = r[["yds", "td"]].mean()

    def target_value(self, buckets: pd.Series, rec_pts: float) -> pd.Series:
        v = self.tgt.catch * rec_pts + self.tgt.yds * 0.1 + self.tgt.td * 6
        d = self.tgt_default
        return buckets.map(v).fillna(d.catch * rec_pts + d.yds * 0.1 + d.td * 6)

    def rush_value(self, buckets: pd.Series) -> pd.Series:
        v = self.rush.yds * 0.1 + self.rush.td * 6
        d = self.rush_default
        return buckets.map(v).fillna(d.yds * 0.1 + d.td * 6)


def pbp_usage(p_raw: pd.DataFrame, xfp: XFPModel, rec_pts: float) -> pd.DataFrame:
    """Per player-week red-zone usage, team shares and expected points."""
    if p_raw.empty:
        return pd.DataFrame()
    p = _plays(p_raw)
    t, r = _targets(p), _rushes(p)
    t["rz"] = (t.yardline_100 <= 20).astype(int)
    t["ez"] = (t.air_yards >= t.yardline_100).astype(int)
    t["xfp"] = xfp.target_value(t.tgt_bucket, rec_pts)
    r["rz"] = (r.yardline_100 <= 20).astype(int)
    r["i10"] = (r.yardline_100 <= 10).astype(int)
    r["xfp"] = xfp.rush_value(r.rush_bucket)

    key = ["season", "week", "posteam"]
    tt = t.groupby(key).agg(team_tgts=("xfp", "size"), team_rz_tgts=("rz", "sum")).reset_index()
    tr = r.groupby(key).agg(team_rush=("xfp", "size"), team_rz_rush=("rz", "sum")).reset_index()

    pt = t.groupby(key + ["receiver_player_id"]).agg(
        pbp_targets=("xfp", "size"), rz_targets=("rz", "sum"), ez_targets=("ez", "sum"),
        xfp_rec=("xfp", "sum")).reset_index().rename(columns={"receiver_player_id": "player_id"})
    pr = r.groupby(key + ["rusher_player_id"]).agg(
        pbp_carries=("xfp", "size"), rz_carries=("rz", "sum"), i10_carries=("i10", "sum"),
        xfp_rush=("xfp", "sum")).reset_index().rename(columns={"rusher_player_id": "player_id"})

    u = pt.merge(pr, on=key + ["player_id"], how="outer").fillna(0)
    u = u.merge(tt, on=key, how="left").merge(tr, on=key, how="left")
    u["rz_tgt_share"] = u.rz_targets / u.team_rz_tgts.replace(0, np.nan)
    u["rz_rush_share"] = u.rz_carries / u.team_rz_rush.replace(0, np.nan)
    u["xfp"] = u.xfp_rec + u.xfp_rush
    return u.drop(columns=["posteam"])


def weekly_table(season: int, xfp: XFPModel, rec_pts: float, players: pd.DataFrame) -> pd.DataFrame:
    """One row per player-week with every usage metric we track."""
    s = sources.weekly_stats(season)
    if s.empty:
        return pd.DataFrame()
    s = s[(s.season_type == "REG") & s.position.isin(["QB", "RB", "WR", "TE"])].copy()
    s["points"] = s.fantasy_points.fillna(0) + rec_pts * s.receptions.fillna(0)
    s["touches"] = s.carries.fillna(0) + s.receptions.fillna(0)
    s["total_tds"] = s[["passing_tds", "rushing_tds", "receiving_tds"]].fillna(0).sum(axis=1)
    keep = ["player_id", "player_display_name", "position", "team", "opponent_team", "season",
            "week", "points", "completions", "attempts", "passing_yards", "passing_tds",
            "passing_interceptions", "carries", "rushing_yards", "rushing_tds", "targets",
            "receptions", "receiving_yards", "receiving_tds", "receiving_air_yards",
            "target_share", "air_yards_share", "wopr", "touches", "total_tds", "headshot_url"]
    s = s[keep].rename(columns={"player_display_name": "name"})

    snaps = sources.snap_counts(season)
    if not snaps.empty:
        pfr = players[["pfr_id", "gsis_id"]].dropna().drop_duplicates("pfr_id")
        snaps = snaps[snaps.game_type == "REG"].merge(pfr, left_on="pfr_player_id", right_on="pfr_id")
        snaps = snaps.groupby(["gsis_id", "week"]).agg(snap_pct=("offense_pct", "max"),
                                                       snaps=("offense_snaps", "max")).reset_index()
        s = s.merge(snaps.rename(columns={"gsis_id": "player_id"}), on=["player_id", "week"], how="left")
    else:
        s["snap_pct"], s["snaps"] = np.nan, np.nan

    u = pbp_usage(sources.pbp(season), xfp, rec_pts)
    if not u.empty:
        s = s.merge(u.drop(columns=["season"]), on=["player_id", "week"], how="left")
    for c in ["rz_targets", "ez_targets", "rz_carries", "i10_carries", "xfp", "xfp_rec", "xfp_rush"]:
        if c not in s:
            s[c] = 0.0
        s[c] = s[c].fillna(0)
    # QBs: expected points from their rushing plus actual passing (passing xFP is noisy)
    qb = s.position == "QB"
    s.loc[qb, "xfp"] = s.loc[qb, "xfp_rush"] + (s.loc[qb, "points"] - s.loc[qb, "rushing_yards"].fillna(0) * 0.1
                                                 - s.loc[qb, "rushing_tds"].fillna(0) * 6)
    return s
