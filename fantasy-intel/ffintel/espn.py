"""ESPN fantasy league connection (private leagues via espn_s2 + SWID cookies)."""
import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests

from . import config, dstk

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{lid}"
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
SLOT = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "FLEX", 3: "FLEX", 5: "FLEX", 7: "OP",
        16: "D/ST", 17: "K", 20: "BN", 21: "IR"}
INJ = {"INJURY_RESERVE": "IR", "OUT": "OUT", "DOUBTFUL": "DOUBTFUL",
       "QUESTIONABLE": "QUESTIONABLE", "SUSPENSION": "SUSPENSION"}


@dataclass
class League:
    name: str
    teams: dict                      # team_id -> {"name", "abbrev", "record"}
    rosters: dict                    # team_id -> list of dicts (player_id, espn_id, name, pos, slot)
    my_team_id: int | None
    n_teams: int
    lineup: dict
    rec_pts: float
    injuries: dict = field(default_factory=dict)   # gsis_id -> (status, detail)
    projections: dict = field(default_factory=dict)  # gsis_id -> ESPN's current points per game
    ownership: dict = field(default_factory=dict)    # gsis_id -> (pct owned, pct change)
    draft_ranks: dict = field(default_factory=dict)  # gsis_id -> ESPN preseason draft rank
    slots_full: dict = field(default_factory=dict)   # every starting slot incl. D/ST and K
    espn_week_proj: dict = field(default_factory=dict)  # espn_id -> ESPN projection for the coming week
    drafted: dict = field(default_factory=dict)      # gsis_id -> overall pick in YOUR draft
    waiver_status: dict = field(default_factory=dict)  # gsis_id -> FREEAGENT / WAIVERS
    # schedule and standings, for the playoff simulation
    schedule: list = field(default_factory=list)     # {"week", "home", "away", "home_pts", "away_pts", "winner", "live"}
    reg_weeks: int = 14                              # matchup periods in the regular season
    playoff_teams: int = 6
    seeding_rule: str = "TOTAL_POINTS_SCORED"        # ESPN's tiebreaker after record
    divisions: dict = field(default_factory=dict)    # team_id -> division id (empty = no divisions)
    division_names: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)      # team_id -> {"w", "l", "t", "pf", "pa"}
    current_period: int = 1
    units: dict = field(default_factory=dict)        # D/ST and K weekly points in your league's scoring
    mock: bool = False
    error: str = ""


def _id_map(players: pd.DataFrame, ids: pd.DataFrame | None) -> dict:
    m = {}
    frames = [players[["espn_id", "gsis_id"]]]
    if ids is not None and len(ids):
        frames.append(ids[["espn_id", "gsis_id"]])
    for f in frames:
        for e, g in f.dropna().itertuples(index=False):
            try:
                m.setdefault(int(float(e)), g)
            except ValueError:
                pass
    return m


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 fantasy-intel"
    if config.ESPN_S2 and config.SWID:
        swid = config.SWID if config.SWID.startswith("{") else "{" + config.SWID + "}"
        s.cookies.set("espn_s2", config.ESPN_S2)
        s.cookies.set("SWID", swid)
    return s


def fetch(players: pd.DataFrame, ids: pd.DataFrame | None, season: int, week: int) -> League:
    s = _session()
    url = BASE.format(season=season, lid=config.LEAGUE_ID)
    r = s.get(url, params=[("view", v) for v in ("mTeam", "mRoster", "mSettings", "mStatus", "mMatchupScore", "mScoreboard")], timeout=60)
    if r.status_code in (401, 403):
        raise PermissionError("ESPN refused access. For a private league set ESPN_S2 and ESPN_SWID "
                              "(see README), and check they haven't expired.")
    r.raise_for_status()
    data = r.json()
    idmap = _id_map(players, ids)

    st = data.get("settings", {})
    slots = st.get("rosterSettings", {}).get("lineupSlotCounts", {})
    lineup = {}
    for k, v in slots.items():
        name = SLOT.get(int(k))
        if name in ("QB", "RB", "WR", "TE", "FLEX", "OP") and v:
            lineup[name] = lineup.get(name, 0) + int(v)
    lineup = lineup or dict(config.DEFAULT_LINEUP)
    slots_full = {}
    for k, v in slots.items():
        name = SLOT.get(int(k))
        if name and name not in ("BN", "IR") and v:
            slots_full[name] = slots_full.get(name, 0) + int(v)
    rec_pts = config.DEFAULT_REC_PTS
    for item in st.get("scoringSettings", {}).get("scoringItems", []):
        if item.get("statId") == 53:
            rec_pts = float(item.get("points", rec_pts))

    swid = (config.SWID if config.SWID.startswith("{") else "{" + config.SWID + "}").upper()
    teams, rosters, my_id = {}, {}, None
    t_records, t_divs = {}, {}
    for t in data.get("teams", []):
        tid = int(t["id"])
        nm = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        rec = t.get("record", {}).get("overall", {})
        records_tmp = {"w": int(rec.get("wins", 0)), "l": int(rec.get("losses", 0)), "t": int(rec.get("ties", 0)),
                       "pf": float(rec.get("pointsFor", 0)), "pa": float(rec.get("pointsAgainst", 0))}
        teams[tid] = {"name": nm, "abbrev": t.get("abbrev", ""),
                      "record": f"{rec.get('wins', 0)}-{rec.get('losses', 0)}" + (f"-{rec['ties']}" if rec.get("ties") else ""),
                      "points_for": round(rec.get("pointsFor", 0), 1)}
        t_records[tid] = records_tmp
        if t.get("divisionId") is not None:
            t_divs[tid] = int(t["divisionId"])
        owners = [o.upper() for o in t.get("owners", [])]
        if config.SWID and swid in owners:
            my_id = tid
        entries = []
        for e in t.get("roster", {}).get("entries", []):
            pl = e.get("playerPoolEntry", {}).get("player", {})
            eid = int(e.get("playerId", pl.get("id", 0)))
            pid = idmap.get(eid)
            if pl.get("defaultPositionId") == 16 or eid < 0:  # team defense: one "player" per NFL team
                pid = dstk.dst_id(dstk.ESPN_PRO_TEAM.get(int(pl.get("proTeamId") or 0), "")) if pl.get("proTeamId") else None
            entries.append({"player_id": pid, "espn_id": eid, "name": pl.get("fullName", ""),
                            "pos": POS.get(pl.get("defaultPositionId"), "?"),
                            "slot": SLOT.get(e.get("lineupSlotId"), "BN")})
        rosters[tid] = entries
    if config.MY_TEAM_ID:
        my_id = int(config.MY_TEAM_ID)
    sch = st.get("scheduleSettings", {}) or {}

    league = League(name=st.get("name", f"League {config.LEAGUE_ID}"), teams=teams, rosters=rosters,
                    my_team_id=my_id, n_teams=len(teams) or config.DEFAULT_TEAMS, lineup=lineup, rec_pts=rec_pts,
                    slots_full=slots_full or {**config.DEFAULT_LINEUP, "D/ST": 1, "K": 1})
    league.records = t_records
    league.reg_weeks = int(sch.get("matchupPeriodCount") or 14)
    league.playoff_teams = int(sch.get("playoffTeamCount") or 6)
    league.seeding_rule = str(sch.get("playoffSeedingRule") or "TOTAL_POINTS_SCORED")
    divs = sch.get("divisions") or []
    if len(divs) > 1 and len(set(t_divs.values())) > 1:
        league.divisions = t_divs
        league.division_names = {int(d.get("id", 0)): d.get("name", f"Division {d.get('id')}") for d in divs}
    league.current_period = int((data.get("status") or {}).get("currentMatchupPeriod") or 1)
    league.schedule = parse_schedule(data.get("schedule") or [])
    try:
        _units(s, url, league, idmap, season)
    except Exception as ex:
        league.error = (league.error + " " if league.error else "") + f"ESPN D/ST and kicker data unavailable: {ex}"
    try:
        _player_pool(s, url, league, idmap, season, week)
    except Exception as ex:  # rosters still usable without it
        league.error = f"ESPN player pool unavailable: {ex}"
    try:
        d = s.get(url, params={"view": "mDraftDetail"}, timeout=60).json()
        for pick in (d.get("draftDetail") or {}).get("picks", []) or []:
            gid = idmap.get(int(pick.get("playerId", 0)))
            if gid:
                league.drafted[gid] = int(pick.get("overallPickNumber", 0))
    except Exception:
        pass  # older leagues or keeper formats may not expose the draft
    return league


def espn_rate(stats: list, season: int, week: int) -> float | None:
    """ESPN's current points-per-game view of a player.

    ESPN's season-long projection barely moves during the year, so "season projection
    minus points scored" is wrong for anyone beating his preseason outlook (Jaxon
    Smith-Njigba had a 211-point projection and 196 actual points after seven games,
    which left ESPN "projecting" 15 more points). Instead use ESPN's projection for the
    coming week; if he's on bye or that week isn't posted, the most recent earlier weekly
    projection; and only if he has none (hurt for weeks), his season projection per game.
    """
    weekly = {}
    season_proj = None
    for stt in stats:
        if stt.get("seasonId") not in (season, None) or stt.get("statSourceId") != 1:
            continue
        if stt.get("statSplitTypeId") == 1 and stt.get("scoringPeriodId"):
            weekly[int(stt["scoringPeriodId"])] = float(stt.get("appliedTotal") or 0)
        elif stt.get("statSplitTypeId") == 0:
            season_proj = float(stt.get("appliedTotal") or 0)
    for w in sorted((w for w in weekly if w <= week), reverse=True):
        if weekly[w] > 0.5:
            return round(weekly[w], 2)
    if season_proj:
        return round(season_proj / 17, 2)
    return None


def parse_schedule(raw: list) -> list:
    """Regular-season matchups: who plays whom each week, and the score once it's final."""
    out = []
    for m in raw:
        if (m.get("playoffTierType") or "NONE") != "NONE":
            continue
        h, a = m.get("home") or {}, m.get("away") or {}
        if not h.get("teamId") or not a.get("teamId"):
            continue  # a bye week in odd-sized leagues
        winner = m.get("winner") or "UNDECIDED"
        live = {}
        for side, t in (("home", h), ("away", a)):
            proj = t.get("totalProjectedPointsLive")
            if proj is not None:
                live[side] = (float(t.get("totalPointsLive") or t.get("totalPoints") or 0), float(proj))
        out.append({"week": int(m.get("matchupPeriodId") or 0), "home": int(h["teamId"]), "away": int(a["teamId"]),
                    "home_pts": float(h.get("totalPoints") or 0), "away_pts": float(a.get("totalPoints") or 0),
                    "winner": winner, "live": live})
    return out


def _units(s, url, league, idmap, season):
    """Every D/ST's and kicker's weekly points in YOUR league's scoring, plus who kicks for whom."""
    flt = {"players": {"filterSlotIds": {"value": [16, 17]}, "limit": 200,
                       "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
                       "filterStatsForTopScoringPeriodIds": {"value": 18, "additionalValue": [f"00{season}"]}}}
    r = s.get(url, params={"view": "kona_player_info"}, headers={"x-fantasy-filter": json.dumps(flt)}, timeout=90)
    r.raise_for_status()
    dst, k = {}, {}
    for p in r.json().get("players", []):
        pl = p.get("player", {})
        team = dstk.ESPN_PRO_TEAM.get(int(pl.get("proTeamId") or 0))
        if not team:
            continue
        pts = {int(x["scoringPeriodId"]): float(x.get("appliedTotal") or 0) for x in pl.get("stats", [])
               if x.get("statSourceId") == 0 and x.get("statSplitTypeId") == 1 and x.get("seasonId") == season
               and x.get("scoringPeriodId")}
        own = pl.get("ownership", {}) or {}
        if pl.get("defaultPositionId") == 16:
            dst[team] = pts
            league.ownership[dstk.dst_id(team)] = (round(own.get("percentOwned", 0), 1), round(own.get("percentChange", 0), 1))
        elif pl.get("defaultPositionId") == 5:
            gid = idmap.get(int(pl.get("id", 0)))
            if gid:
                k[gid] = (team, pts)
                league.ownership[gid] = (round(own.get("percentOwned", 0), 1), round(own.get("percentChange", 0), 1))
    league.units = {"dst": dst, "k": k}


def _player_pool(s, url, league, idmap, season, week):
    flt = {"players": {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
        "filterSlotIds": {"value": [0, 2, 4, 6, 16, 17]},
        "limit": 1500,
        "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
        "filterStatsForTopScoringPeriodIds": {"value": 3, "additionalValue": [f"00{season}", f"10{season}"]},
    }}
    r = s.get(url, params={"view": "kona_player_info", "scoringPeriodId": week},
              headers={"x-fantasy-filter": json.dumps(flt)}, timeout=90)
    r.raise_for_status()
    for p in r.json().get("players", []):
        pl = p.get("player", {})
        eid = int(pl.get("id", 0))
        for stt in pl.get("stats", []):  # ESPN's projection for the coming week (used for K and D/ST)
            if stt.get("statSourceId") == 1 and stt.get("scoringPeriodId") == week and stt.get("statSplitTypeId") == 1:
                league.espn_week_proj[eid] = round(float(stt.get("appliedTotal") or 0), 1)
        gid = idmap.get(eid)
        if not gid:
            continue
        inj = INJ.get(pl.get("injuryStatus", ""))
        if inj:
            league.injuries[gid] = (inj, pl.get("injuryStatus", "").replace("_", " ").title())
        own = pl.get("ownership", {})
        league.ownership[gid] = (round(own.get("percentOwned", 0), 1), round(own.get("percentChange", 0), 1))
        league.waiver_status[gid] = p.get("status", "")
        rate = espn_rate(pl.get("stats", []), season, week)
        if rate is not None:
            league.projections[gid] = rate
        ranks = pl.get("draftRanksByRankType") or {}
        for kind in ("PPR", "STANDARD"):
            r = (ranks.get(kind) or {}).get("rank")
            if r:
                league.draft_ranks[gid] = int(r)
                break


def mock(df: pd.DataFrame, seed: int = 7, plan_week: int | None = None) -> League:
    """A fake 12-team league drafted from the ratings, for offline testing only."""
    rng = np.random.default_rng(seed)
    pool = df[df.position.isin(["QB", "RB", "WR", "TE"])].copy()
    pool["draft_score"] = pool.ros_points * rng.normal(1, 0.25, len(pool))
    pool = pool.sort_values("draft_score", ascending=False)
    need = {"QB": 2, "RB": 5, "WR": 5, "TE": 2}
    rosters = {t: [] for t in range(1, 13)}
    counts = {t: {p: 0 for p in need} for t in rosters}
    order = [t for rnd in range(14) for t in (range(1, 13) if rnd % 2 == 0 else range(12, 0, -1))]
    avail = list(pool.itertuples())
    for t in order:
        for i, p in enumerate(avail):
            if counts[t][p.position] < need[p.position]:
                rosters[t].append({"player_id": p.player_id, "espn_id": None, "name": p.name,
                                   "pos": p.position, "slot": "BN"})
                counts[t][p.position] += 1
                avail.pop(i)
                break
    nfl = ["BUF", "KC", "BAL", "PHI", "DET", "SF", "DAL", "MIN", "PIT", "DEN", "HOU", "LAC"]
    kickers = ["B. Aubrey", "C. Boswell", "J. Bates", "H. Butker", "K. Fairbairn", "J. Elliott",
               "C. Dicker", "W. Lutz", "T. Bass", "J. Myers", "E. McPherson", "Y. Koo"]
    for t in rosters:
        rosters[t].append({"player_id": dstk.dst_id(nfl[t-1]), "espn_id": -t, "name": f"{nfl[t-1]} D/ST", "pos": "D/ST",
                           "slot": "D/ST", "team": nfl[t-1], "espn_week_proj": round(float(rng.normal(7, 2)), 1)})
        rosters[t].append({"player_id": None, "espn_id": -100 - t, "name": kickers[t-1], "pos": "K", "slot": "K",
                           "team": nfl[t-1], "espn_week_proj": round(float(rng.normal(8, 1.5)), 1)})
    teams = {t: {"name": f"Demo Team {t}", "abbrev": f"T{t}", "record": "0-0", "points_for": 0} for t in rosters}
    teams[1]["name"] = "Demo: My Team"
    lg = League(name="Demo league (mock data)", teams=teams, rosters=rosters, my_team_id=1, n_teams=12,
                lineup=dict(config.DEFAULT_LINEUP), rec_pts=0.5, mock=True,
                slots_full={**config.DEFAULT_LINEUP, "D/ST": 1, "K": 1})
    # round-robin schedule; weeks before `plan_week` already played with random scores
    ids = list(rosters)
    lg.reg_weeks, lg.playoff_teams = 14, 6
    lg.current_period = plan_week or 1
    lg.records = {t: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0} for t in ids}
    rot = ids[1:]
    for w in range(1, lg.reg_weeks + 1):
        r = (w - 1) % (len(ids) - 1)
        order = [ids[0]] + rot[r:] + rot[:r]
        for i in range(len(ids) // 2):
            h, a = order[i], order[-1 - i]
            m = {"week": w, "home": h, "away": a, "home_pts": 0.0, "away_pts": 0.0, "winner": "UNDECIDED", "live": {}}
            if plan_week and w < plan_week:
                hp, ap = float(rng.normal(112, 22)), float(rng.normal(112, 22))
                m.update(home_pts=round(hp, 1), away_pts=round(ap, 1), winner="HOME" if hp > ap else "AWAY")
                for t, mine, theirs in ((h, hp, ap), (a, ap, hp)):
                    lg.records[t]["w" if mine > theirs else "l"] += 1
                    lg.records[t]["pf"] += mine
                    lg.records[t]["pa"] += theirs
            lg.schedule.append(m)
    for t in ids:
        r = lg.records[t]
        teams[t]["record"], teams[t]["points_for"] = f"{r['w']}-{r['l']}", round(r["pf"], 1)
    return lg
