"""ESPN fantasy league connection (private leagues via espn_s2 + SWID cookies)."""
import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests

from . import config

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
    projections: dict = field(default_factory=dict)  # gsis_id -> ESPN ROS points
    ownership: dict = field(default_factory=dict)    # gsis_id -> (pct owned, pct change)
    waiver_status: dict = field(default_factory=dict)  # gsis_id -> FREEAGENT / WAIVERS
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
    r = s.get(url, params=[("view", v) for v in ("mTeam", "mRoster", "mSettings", "mStatus")], timeout=60)
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
    rec_pts = config.DEFAULT_REC_PTS
    for item in st.get("scoringSettings", {}).get("scoringItems", []):
        if item.get("statId") == 53:
            rec_pts = float(item.get("points", rec_pts))

    swid = (config.SWID if config.SWID.startswith("{") else "{" + config.SWID + "}").upper()
    teams, rosters, my_id = {}, {}, None
    for t in data.get("teams", []):
        tid = int(t["id"])
        nm = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        rec = t.get("record", {}).get("overall", {})
        teams[tid] = {"name": nm, "abbrev": t.get("abbrev", ""),
                      "record": f"{rec.get('wins', 0)}-{rec.get('losses', 0)}" + (f"-{rec['ties']}" if rec.get("ties") else ""),
                      "points_for": round(rec.get("pointsFor", 0), 1)}
        owners = [o.upper() for o in t.get("owners", [])]
        if config.SWID and swid in owners:
            my_id = tid
        entries = []
        for e in t.get("roster", {}).get("entries", []):
            pl = e.get("playerPoolEntry", {}).get("player", {})
            eid = int(e.get("playerId", pl.get("id", 0)))
            entries.append({"player_id": idmap.get(eid), "espn_id": eid, "name": pl.get("fullName", ""),
                            "pos": POS.get(pl.get("defaultPositionId"), "?"),
                            "slot": SLOT.get(e.get("lineupSlotId"), "BN")})
        rosters[tid] = entries
    if config.MY_TEAM_ID:
        my_id = int(config.MY_TEAM_ID)

    league = League(name=st.get("name", f"League {config.LEAGUE_ID}"), teams=teams, rosters=rosters,
                    my_team_id=my_id, n_teams=len(teams) or config.DEFAULT_TEAMS, lineup=lineup, rec_pts=rec_pts)
    try:
        _player_pool(s, url, league, idmap, season, week)
    except Exception as ex:  # rosters still usable without it
        league.error = f"ESPN player pool unavailable: {ex}"
    return league


def _player_pool(s, url, league, idmap, season, week):
    flt = {"players": {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
        "filterSlotIds": {"value": [0, 2, 4, 6]},
        "limit": 1500,
        "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
        "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": [f"00{season}", f"10{season}"]},
    }}
    r = s.get(url, params={"view": "kona_player_info", "scoringPeriodId": week},
              headers={"x-fantasy-filter": json.dumps(flt)}, timeout=90)
    r.raise_for_status()
    for p in r.json().get("players", []):
        pl = p.get("player", {})
        gid = idmap.get(int(pl.get("id", 0)))
        if not gid:
            continue
        inj = INJ.get(pl.get("injuryStatus", ""))
        if inj:
            league.injuries[gid] = (inj, pl.get("injuryStatus", "").replace("_", " ").title())
        own = pl.get("ownership", {})
        league.ownership[gid] = (round(own.get("percentOwned", 0), 1), round(own.get("percentChange", 0), 1))
        league.waiver_status[gid] = p.get("status", "")
        proj = act = None
        for stt in pl.get("stats", []):
            if stt.get("seasonId") != season or stt.get("statSplitTypeId") != 0:
                continue
            if stt.get("statSourceId") == 1:
                proj = stt.get("appliedTotal")
            elif stt.get("statSourceId") == 0:
                act = stt.get("appliedTotal")
        if proj is not None:
            league.projections[gid] = max(0.0, proj - (act or 0))


def mock(df: pd.DataFrame, seed: int = 7) -> League:
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
    teams = {t: {"name": f"Demo Team {t}", "abbrev": f"T{t}", "record": "1-1", "points_for": 0} for t in rosters}
    teams[1]["name"] = "Demo: My Team"
    return League(name="Demo league (mock data)", teams=teams, rosters=rosters, my_team_id=1, n_teams=12,
                  lineup=dict(config.DEFAULT_LINEUP), rec_pts=0.5, mock=True)
