"""Injury intelligence: every availability signal we can find, merged per player.

Official NFL designations only come out Wednesday-Friday, so a player hurt on Sunday
looks healthy for days. To close that gap we read, in order of speed:

  1. Play-by-play (within hours of the game): "X was injured during the play",
     "X has returned to the game", and whether he ever took another snap.
  2. Snap counts: a starter whose snap share collapsed in his last game.
  3. ESPN's live injury feed: status, return date and the news desk's comment.
  4. Sleeper's player feed: injury status, body part and notes.
  5. ESPN NFL news headlines that mention a player alongside injury words.
  6. Your ESPN league's injury designations.
  7. The official injury report and practice participation (nflverse).
  8. NFL roster moves: IR, PUP, NFI, suspensions, exempt lists.

Each becomes a Signal with an estimate of games missed. Stale signals are dropped
(an in-game injury is superseded once the next practice report is out; a roster
IR flag is ignored if the player just played), then the most serious remaining
signal sets the status, and every signal is kept for the dashboard.
"""
import datetime as dt
import math
import re
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import sources

ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
ESPN_NEWS = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=150"
SLEEPER_PLAYERS = "https://api.sleeper.app/v1/players/nfl"
# ESPN's CDN rejects plain script requests from cloud servers, so ask like a browser
# and fall back to the mirror host if the first one refuses.
ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.espn.com/nfl/injuries",
    "Origin": "https://www.espn.com",
}
ESPN_MIRROR = {"site.api.espn.com": "site.web.api.espn.com"}
RSS_FEEDS = [("CBS Sports", "https://www.cbssports.com/rss/headlines/nfl/"),
             ("ESPN", "https://www.espn.com/espn/rss/nfl/news")]


def espn_json(url: str):
    """GET an ESPN endpoint, retrying on the mirror host; errors name the status code."""
    last = None
    urls = [url] + [url.replace(h, m) for h, m in ESPN_MIRROR.items() if h in url]
    for u in urls:
        try:
            r = sources.SESSION.get(u, headers=ESPN_HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code} from {u.split('/')[2]}"
        except Exception as e:
            last = f"{type(e).__name__} from {u.split('/')[2]}"
    raise RuntimeError(last or "no response")

# Expected games missed per status when nothing more specific is known
BASE_GAMES = {"SEASON": 99.0, "IR": 4.0, "PUP": 4.0, "NFI": 4.0, "SUSPENSION": 2.0, "UNAVAILABLE": 2.0,
              "OUT": 1.0, "DOUBTFUL": 0.8, "LEFT GAME": 1.0, "INACTIVE": 0.6, "QUESTIONABLE": 0.25,
              "DNP": 0.3, "SNAPS DOWN": 0.1, "RETURNED": 0.05, "NEWS": 0.0, "HEALTHY": 0.0}
SEVERITY = list(BASE_GAMES)  # most severe first


@dataclass
class Signal:
    player_id: str
    status: str
    games: float          # expected games missed from the next game on
    detail: str
    source: str
    when: str             # ISO timestamp (UTC) of the information
    week: int | None = None
    positive: bool = False  # e.g. "full practice", "will play"
    p_miss: float | None = None  # chance he misses the next game (default: min(games, 1))


# ---------------------------------------------------------------- text reading
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "a couple": 2, "couple": 2, "a few": 3, "few": 3, "several": 4, "multiple": 3}
NEGATION = re.compile(r"(avoid|avoided|ruled out an?|no sign of|not an?|not (?:expected|believed|likely|going) to(?: \w+)?|negative|clean|isn't|is not|no structural|won't)\W+(?:\w+\W+){0,2}$", re.I)
POSITIVE = re.compile(r"\b(cleared|gained clearance|will play|expected to play|full(?:y)? participat|full practice|"
                      r"no injury designation|removed from (?:the )?injury report|activated|will suit up|suited up|"
                      r"returns? to practice fully|good to go|shed(?: the)? (?:questionable|doubtful)|"
                      r"upgraded to (?:full|active))\b", re.I)
NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:['\-][A-Za-z]+)?\s+[A-Z][a-zA-Z.'\-]+\b")


def about_player(text: str, full_name: str) -> str:
    """Keep only the parts of a write-up that are about this player.

    Injury blurbs routinely describe teammates ("...with Jordan Addison expected to
    miss multiple weeks"), and reading those as news about the subject is how a
    healthy player ends up projected for zero.
    """
    if not text or not full_name:
        return ""
    last = full_name.split()[-1]
    kept = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if last.lower() not in sent.lower():
            continue
        others = [n for n in NAME_RE.findall(sent) if last not in n and full_name not in n]
        if others:  # trim the sentence where it starts talking about someone else
            cut = min(sent.find(n) for n in others)
            sent = sent[:cut]
        kept.append(sent)
    return " ".join(kept)


def _neg(text, start):
    seg = re.split(r"[.;]", text[max(0, start - 40):start])[-1]  # same clause only
    return bool(NEGATION.search(seg))


def text_severity(text: str) -> tuple[float, str] | None:
    """Best guess of games missed from injury news text; None if nothing found."""
    if not text:
        return None
    t = text.lower()
    best = None

    def take(g, label, m):
        nonlocal best
        if m is not None and _neg(t, m.start()):
            return
        if best is None or g > best[0]:
            best = (g, label)

    for pat in (r"season[- ]ending", r"out for the (?:season|year|rest of the season)", r"torn (?:acl|achilles)",
                r"(?:acl|achilles) (?:tear|rupture)", r"ruptured", r"broken (?:leg|fibula|tibia)"):
        m = re.search(pat, t)
        if m:
            take(99.0, "season-ending", m)
    m = re.search(r"(?:placed|landed|moved|headed) (?:him )?(?:on|to) (?:injured reserve|ir)\b|\bon injured reserve\b", t)
    if m:
        take(4.0, "injured reserve", m)
    spans = []
    for m in re.finditer(r"(\d+|one|two|three|four|five|six|seven|eight)\s*(?:-|to|or)\s*(\d+|two|three|four|five|six|seven|eight|ten|twelve)\s*weeks", t):
        a, b = (int(WORDNUM.get(x, x)) for x in m.groups())
        spans.append(m.span())
        take((a + b) / 2, f"{m.group(0)}", m)
    for m in re.finditer(r"\b(\d+|one|two|three|four|five|six|a couple|couple|a few|few|several|multiple)\s+(?:more\s+)?weeks", t):
        if any(a <= m.start() < b for a, b in spans):
            continue  # part of a range already counted
        w = m.group(1)
        n = int(w) if w.isdigit() else WORDNUM.get(w, 2)
        take(float(n), m.group(0), m)
    for pat, g, label in ((r"week[- ]to[- ]week", 2.0, "week-to-week"), (r"high[- ]ankle", 2.5, "high-ankle sprain"),
                          (r"\bsurgery\b", 4.0, "surgery"), (r"\bfracture|\bbroken\b", 4.0, "fracture"),
                          (r"concussion", 1.0, "concussion protocol"), (r"ruled out|will not play|won't play|will miss", 1.0, "ruled out"),
                          (r"(?:undergo|undergoing|will have|scheduled for|awaiting|set for|pending)(?: an?)? mri|mri (?:is )?(?:scheduled|pending)", 0.5, "awaiting MRI"), (r"\bdoubtful\b", 0.8, "doubtful"),
                          (r"day[- ]to[- ]day|game[- ]time decision|\bquestionable\b", 0.3, "day-to-day"),
                          (r"sit out|will not practice|did not practice|miss(?:ed|ing)? (?:today's |wednesday's |thursday's |friday's )?practice|"
                           r"limited (?:in|at) practice", 0.3, "practice absence")):
        m = re.search(pat, t)
        if m:
            take(g, label, m)
    return best


# ---------------------------------------------------------------- 1. play-by-play
INJ_RE = re.compile(r"\b([A-Z]{2,3})-(\d{1,2})-([A-Z][\w.'\-]*?\.?[A-Z][\w'\-]+(?: (?:Jr|Sr|II|III|IV)\.?)?) was injured during the play")
RET_RE = re.compile(r"Injury Update: ([A-Z]{2,3})-(\d{1,2})-([A-Z][\w.'\-]*?\.?[A-Z][\w'\-]+(?: (?:Jr|Sr|II|III|IV)\.?)?) has returned")


def _abbr_index(season: int, players: pd.DataFrame) -> dict:
    """(team, 'C.Williams') -> gsis id, from this season's box scores plus rosters."""
    idx = {}
    st = sources.weekly_stats(season)
    if not st.empty:
        for pid, name, team in st[["player_id", "player_name", "team"]].drop_duplicates().itertuples(index=False):
            idx[(team, name)] = pid
    rest = players[players.latest_team.notna() & players.jersey_number.notna()]
    for pid, team, num in rest[["gsis_id", "latest_team", "jersey_number"]].itertuples(index=False):
        idx.setdefault((team, int(num)), pid)
    return idx


def in_game(pbp: pd.DataFrame, players: pd.DataFrame, season: int, skill: set):
    """In-game injuries from the most recent games.

    Returns (signals, short_games, fill_ins):
      short_games: {(player_id, week)} games cut short by injury (excluded from scoring averages)
      fill_ins:    list of {injured, injured_id, team, fill_in, fill_in_id, share}
    """
    if pbp.empty or "desc" not in pbp:
        return [], set(), []
    idx = _abbr_index(season, players)
    p = pbp[(pbp.season_type == "REG")].copy()
    p = p.sort_values(["game_id", "play_id"])
    signals, short, fills = [], set(), []

    def ident(team, num, name):
        return idx.get((team, name)) or idx.get((team, int(num)))

    for gid, g in p.groupby("game_id", sort=False):
        descs = g.desc.fillna("").tolist()
        play_ids = g.play_id.tolist()
        week = int(g.week.iloc[0])
        gdate = str(g.game_date.iloc[0]) if "game_date" in g else ""
        for i, d in enumerate(descs):
            for m in INJ_RE.finditer(d):
                team, num, name = m.groups()
                pid = ident(team, num, name)
                if not pid or pid not in skill:
                    continue
                token = f"{num}-{name}"
                later = descs[i + 1:]
                returned = any(RET_RE.search(x) and token in x for x in later)
                back_on_field = any(token in x and "was injured" not in x.split(token)[-1][:30]
                                    and "Injury Update" not in x for x in later)
                qtr = g.qtr.iloc[i] if "qtr" in g else None
                clock = g.time.iloc[i] if "time" in g else ""
                when = f"Q{int(qtr)} {clock}" if qtr == qtr and qtr is not None else ""
                if returned or back_on_field:
                    signals.append(Signal(pid, "RETURNED", BASE_GAMES["RETURNED"],
                                          f"Injured in week {week} ({when}) but returned to the game",
                                          "Play-by-play", gdate, week))
                else:
                    short.add((pid, week))
                    remaining = len(later)
                    signals.append(Signal(pid, "LEFT GAME", BASE_GAMES["LEFT GAME"],
                                          f"Injured in week {week} ({when}) and did not return"
                                          + (f"; {remaining} plays left without him" if remaining else "")
                                          + ". Severity unknown until the next injury report.",
                                          "Play-by-play", gdate, week, p_miss=0.5))
                    fills.extend(_fill_in(g.iloc[i + 1:], pid, team, players))
    # keep only each player's latest game signal
    latest = {}
    for s in signals:
        if s.player_id not in latest or (s.week or 0) >= (latest[s.player_id].week or 0):
            latest[s.player_id] = s
    return list(latest.values()), short, fills


def _fill_in(after: pd.DataFrame, injured_id, team, players):
    """Who took the injured player's work for the rest of that game."""
    pos = players.set_index("gsis_id").position.get(injured_id)
    if after.empty or pos is None:
        return []
    a = after[after.posteam == team]
    if pos == "QB":
        col = "passer_player_id"
    elif pos == "RB":
        col = "rusher_player_id"
    else:
        col = "receiver_player_id"
    if col not in a or a[col].dropna().empty:
        return []
    ppos = players.set_index("gsis_id").position
    counts = a[col].dropna().value_counts()
    counts = counts[[ppos.get(i) == pos for i in counts.index]]
    counts = counts[counts.index != injured_id]
    if counts.empty:
        return []
    top = counts.index[0]
    if pos != "QB" and (counts.iloc[0] < 5 or counts.iloc[0] / counts.sum() < 0.4):
        return []  # no clear replacement
    names = players.set_index("gsis_id").display_name
    return [{"injured_id": injured_id, "injured": names.get(injured_id, ""), "team": team,
             "fill_in_id": top, "fill_in": names.get(top, ""), "position": pos,
             "plays": int(counts.iloc[0]), "share": round(float(counts.iloc[0] / counts.sum()), 2)}]


# ---------------------------------------------------------------- 2. snap collapse
def snap_collapse(cur: pd.DataFrame, already: set) -> list[Signal]:
    out = []
    if cur.empty or "snap_pct" not in cur:
        return out
    c = cur.dropna(subset=["snap_pct"]).sort_values("week")
    for pid, g in c.groupby("player_id"):
        if len(g) < 2 or pid in already:
            continue
        last, prev = g.iloc[-1], g.iloc[:-1].snap_pct.mean()
        if prev >= 0.6 and last.snap_pct < 0.5 * prev:
            out.append(Signal(pid, "SNAPS DOWN", BASE_GAMES["SNAPS DOWN"],
                              f"Played {last.snap_pct:.0%} of snaps in week {int(last.week)} (usually {prev:.0%}): "
                              "possible injury or benching", "Snap counts", "", int(last.week)))
    return out


# ---------------------------------------------------------------- 7/8. official + rosters
def roster_signals(players: pd.DataFrame, played_last: set) -> list[Signal]:
    out = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for pid, desc, status in players[["gsis_id", "ngs_status_short_description", "status"]].itertuples(index=False):
        if pid in played_last:
            continue  # roster file lags; a player who just played isn't on a reserve list
        desc = str(desc or "")
        if desc.startswith("R/I"):
            out.append(Signal(pid, "IR", BASE_GAMES["IR"], "Injured reserve", "NFL roster", now))
        elif desc == "R/PUP":
            out.append(Signal(pid, "PUP", BASE_GAMES["PUP"], "PUP list", "NFL roster", now))
        elif desc.startswith("R/NFI"):
            out.append(Signal(pid, "NFI", BASE_GAMES["NFI"], "Non-football injury list", "NFL roster", now))
        elif status == "SUS":
            out.append(Signal(pid, "SUSPENSION", BASE_GAMES["SUSPENSION"], "Suspended", "NFL roster", now))
        elif status in ("EXE", "RSN", "NWT"):
            out.append(Signal(pid, "UNAVAILABLE", BASE_GAMES["UNAVAILABLE"], "Not with team / exempt list", "NFL roster", now))
    return out


def report_signals(inj: pd.DataFrame, report_dates: dict) -> list[Signal]:
    """Latest official report per player, plus practice participation."""
    out = []
    if inj.empty:
        return out
    latest = inj.sort_values("week").groupby("gsis_id").tail(1)
    for r in latest.itertuples(index=False):
        injury = r.report_primary_injury if pd.notna(r.report_primary_injury) else r.practice_primary_injury
        when = report_dates.get((r.team, int(r.week)), "")
        st = str(r.report_status).upper() if pd.notna(r.report_status) else ""
        practice = str(r.practice_status) if pd.notna(r.practice_status) else ""
        if st in BASE_GAMES:
            out.append(Signal(r.gsis_id, st, BASE_GAMES[st], f"{injury}: {st.title()} for week {r.week}"
                              + (f" ({practice.lower()})" if practice else ""), "Official injury report", when, int(r.week)))
        elif "Did Not" in practice and "Not injury" not in str(injury):
            out.append(Signal(r.gsis_id, "DNP", BASE_GAMES["DNP"], f"{injury}: did not practice (week {r.week})",
                              "Practice report", when, int(r.week)))
        elif "Full" in practice or (practice and not st):
            out.append(Signal(r.gsis_id, "HEALTHY", 0.0, f"{injury}: {practice.lower() or 'no game status'} (week {r.week})",
                              "Official injury report", when, int(r.week), positive=True))
    return out


# ---------------------------------------------------------------- 3-6. live feeds
def _norm(name: str) -> str:
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(name).lower())
    return re.sub(r"[^a-z]", "", n)


def name_index(players: pd.DataFrame) -> dict:
    idx = {}
    for pid, name, team in players[["gsis_id", "display_name", "latest_team"]].itertuples(index=False):
        idx.setdefault((_norm(name), team), pid)
        idx.setdefault((_norm(name), None), pid)
    return idx


ESPN_TEAM = {"WSH": "WAS", "LAR": "LA", "JAC": "JAX"}
STATUS_MAP = {"out": "OUT", "doubtful": "DOUBTFUL", "questionable": "QUESTIONABLE", "injured reserve": "IR",
              "ir": "IR", "physically unable to perform": "PUP", "pup": "PUP", "suspension": "SUSPENSION",
              "sus": "SUSPENSION", "day-to-day": "QUESTIONABLE", "dnr": "UNAVAILABLE", "na": None, "cov": "OUT",
              "injured_reserve": "IR", "out for season": "SEASON"}


def _status(raw):
    return STATUS_MAP.get(str(raw or "").strip().lower().replace("injury_status_", "").replace("_", " "))


def _games_from_return(return_date: str, team: str, game_dates: dict) -> float | None:
    try:
        rd = pd.Timestamp(return_date[:10])
    except Exception:
        return None
    dates = game_dates.get(team, [])
    today = pd.Timestamp.today().normalize()
    return float(sum(1 for d in dates if today <= d < rd))


def espn_feed(espn_idmap: dict, nidx: dict, game_dates: dict) -> list[Signal]:
    data = espn_json(ESPN_INJURIES)
    out = []
    for team in data.get("injuries", []):
        for it in team.get("injuries", []):
            ath = it.get("athlete", {}) or {}
            eid = ath.get("id")
            if not eid:
                for link in ath.get("links", []) or []:
                    m = re.search(r"/id/(\d+)", link.get("href", ""))
                    if m:
                        eid = m.group(1)
                        break
            pid = espn_idmap.get(int(eid)) if eid and str(eid).isdigit() else None
            tabbr = ESPN_TEAM.get((ath.get("team") or {}).get("abbreviation", ""), (ath.get("team") or {}).get("abbreviation"))
            pid = pid or nidx.get((_norm(ath.get("displayName", "")), tabbr)) or nidx.get((_norm(ath.get("displayName", "")), None))
            if not pid:
                continue
            status = _status(it.get("status")) or _status((it.get("type") or {}).get("description"))
            details = it.get("details") or {}
            body = " ".join(str(details.get(k, "")) for k in ("side", "type", "detail") if details.get(k)).strip()
            comment = it.get("longComment") or it.get("shortComment") or ""
            mine = about_player(comment, ath.get("displayName", ""))
            games = BASE_GAMES.get(status, 0.0) if status else 0.0
            sev = text_severity(mine)  # only what the blurb says about HIM
            if sev and not status:
                sev = (min(sev[0], 2.0), sev[1])  # no designation: don't over-read a write-up
            if sev and sev[0] > games:
                games = sev[0]
            label = status or ("SEASON" if games >= 99 else "OUT" if games >= 1 else
                               "QUESTIONABLE" if games >= 0.3 else "NEWS")
            if details.get("returnDate"):
                g = _games_from_return(details["returnDate"], tabbr, game_dates)
                if g is not None and status in ("OUT", "IR", "PUP", "SUSPENSION", None, "SEASON"):
                    games = max(g, games if label == "SEASON" else 0)
            positive = bool(POSITIVE.search(mine or comment))
            if positive and not status:
                games, label = 0.0, "NEWS"  # the write-up says he is fine
            if games <= 0 and not status and not positive:
                continue  # a blurb about a healthy player, not an injury
            detail = (f"{body}. " if body else "") + (comment[:260] if comment else (status or "").title())
            if details.get("returnDate"):
                detail += f" (ESPN return estimate: {details['returnDate'][:10]})"
            out.append(Signal(pid, label, games, detail, "ESPN injury desk", it.get("date", ""),
                              positive=positive))
    return out


def sleeper_feed(ids: pd.DataFrame, nidx: dict) -> list[Signal]:
    r = sources.SESSION.get(SLEEPER_PLAYERS, timeout=60)
    r.raise_for_status()
    smap = {}
    if ids is not None and "sleeper_id" in ids:
        for sid, gid in ids[["sleeper_id", "gsis_id"]].dropna().itertuples(index=False):
            smap[str(sid).split(".")[0]] = gid
    out = []
    for sid, p in r.json().items():
        if p.get("position") not in ("QB", "RB", "WR", "TE"):
            continue
        status = _status(p.get("injury_status"))
        if not status:
            continue
        pid = smap.get(str(sid)) or nidx.get((_norm(p.get("full_name", "")), p.get("team")))
        if not pid:
            continue
        notes = p.get("injury_notes") or ""
        games = BASE_GAMES.get(status, 0.0)
        sev = text_severity(notes)
        if sev and sev[0] > games:
            games = sev[0]
        upd = p.get("news_updated")
        when = dt.datetime.fromtimestamp(upd / 1000, dt.timezone.utc).isoformat() if upd else ""
        body = p.get("injury_body_part") or ""
        out.append(Signal(pid, "SEASON" if games >= 99 else status, games,
                          f"{body}{': ' if body and notes else ''}{notes}".strip() or status.title(),
                          "Sleeper", when))
    return out


def news_feed(espn_idmap: dict, nidx: dict) -> list[Signal]:
    data = espn_json(ESPN_NEWS)
    out = []
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    for a in data.get("articles", []):
        text = f"{a.get('headline', '')}. {a.get('description', '')}"
        if not re.search(r"injur|hurt|ankle|knee|hamstring|concussion|mri|surgery|out for|ruled out|week-to-week|"
                         r"\bir\b|torn|sprain|strain|fracture|questionable|doubtful|cleared|return", text, re.I):
            continue
        pub = a.get("published", "")
        try:
            if pd.Timestamp(pub) < cutoff:
                continue
        except Exception:
            pass
        athletes = [c for c in a.get("categories", []) if c.get("type") == "athlete"]
        for c in athletes[:2]:  # the article's main subjects
            pid = espn_idmap.get(int(c.get("athleteId", 0) or 0)) or nidx.get((_norm(c.get("description", "")), None))
            if not pid:
                continue
            sev = text_severity(text)
            pos = bool(POSITIVE.search(text))
            games = sev[0] if sev else 0.0
            if games < 0.3 and not pos:
                continue  # mentions an injury topic but says nothing about him missing time
            label = "SEASON" if games >= 99 else ("NEWS" if games < 0.3 else ("OUT" if games >= 1 else "QUESTIONABLE"))
            out.append(Signal(pid, label, games, a.get("headline", "")[:200], "ESPN news", pub,
                              positive=pos and not sev))
    return out


INJURY_WORDS = re.compile(r"injur|hurt|ankle|knee|hamstring|groin|concussion|mri|surgery|out for|ruled out|"
                          r"week-to-week|\bir\b|injured reserve|torn|sprain|strain|fracture|questionable|doubtful|"
                          r"cleared|activated|return", re.I)


def unique_names(players: pd.DataFrame, positions=("QB", "RB", "WR", "TE")) -> dict:
    """Full name -> gsis id, only for names that belong to exactly one skill player."""
    p = players[players.position.isin(positions) & players.latest_team.notna()]
    counts = p.display_name.value_counts()
    return {n: pid for n, pid in zip(p.display_name, p.gsis_id) if counts.get(n, 0) == 1 and len(n.split()) >= 2}


def rss_feed(names: dict) -> list[Signal]:
    """Injury news from public RSS feeds: a backup for when ESPN's API refuses us."""
    import xml.etree.ElementTree as ET

    out, errors = [], []
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    for label, url in RSS_FEEDS:
        try:
            r = sources.SESSION.get(url, headers=ESPN_HEADERS, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}")
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "").strip()
            text = f"{title}. {desc}"
            if not INJURY_WORDS.search(text):
                continue
            when = item.findtext("pubDate") or ""
            try:
                ts = pd.Timestamp(when)
                if ts.tz is None:
                    ts = ts.tz_localize("UTC")
                if ts < cutoff:
                    continue
                when = ts.isoformat()
            except Exception:
                when = pd.Timestamp.now(tz="UTC").isoformat()
            # only the headline's subject: a teammate named in the body isn't the injured one
            for name, pid in names.items():
                if name not in title:
                    continue
                sev = text_severity(text)
                games = sev[0] if sev else 0.0
                pos = bool(POSITIVE.search(text))
                if games < 0.3 and not pos:
                    continue  # injury-flavoured headline, no actual availability news
                status = "SEASON" if games >= 99 else ("NEWS" if games < 0.3 else
                                                      ("OUT" if games >= 1 else "QUESTIONABLE"))
                out.append(Signal(pid, status, games, title[:200], f"{label} news", when,
                                  positive=bool(POSITIVE.search(text)) and not sev))
    if errors and not out:
        raise RuntimeError("; ".join(errors))
    return out


def league_signals(league_injuries: dict) -> list[Signal]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return [Signal(pid, st, BASE_GAMES.get(st, 0.0), detail, "Your ESPN league", now)
            for pid, (st, detail) in (league_injuries or {}).items()]


# ---------------------------------------------------------------- merge
def _ts(s):
    try:
        t = pd.Timestamp(s)
        return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    except Exception:
        return None


def combine(signals: list[Signal], report_weeks: dict, player_team: dict, last_played: dict,
            team_last_week: dict | None = None) -> pd.DataFrame:
    """One row per player: headline status, expected games missed, and every signal.

    report_weeks: team -> latest official report week
    last_played:  player_id -> last week he appeared in a box score
    """
    by = {}
    for s in signals:
        by.setdefault(s.player_id, []).append(s)
    rows = []
    for pid, sigs in by.items():
        team = player_team.get(pid)
        live = []
        for s in sigs:
            # an in-game injury is superseded once the team's final (game-status) report for a
            # later week is out; mid-week practice notes alone don't settle it
            if s.status in ("LEFT GAME", "RETURNED", "SNAPS DOWN") and s.week is not None \
                    and report_weeks.get(team, 0) > s.week:
                continue
            # an official status for a game he has since played is resolved
            if s.source in ("Official injury report", "Practice report") and s.week is not None \
                    and last_played.get(pid, 0) >= s.week:
                continue
            # a status for a game already played (he sat it out) carries forward, discounted:
            # roughly 60% of players ruled out one week also miss the next
            if s.source in ("Official injury report", "Practice report") and s.week is not None \
                    and (team_last_week or {}).get(team, 0) >= s.week and s.games > 0:
                missed_it = last_played.get(pid, 0) < s.week
                g = max(s.games * 0.6, 0.6) if missed_it and s.games < 4 else s.games * 0.6
                s = Signal(**{**asdict(s), "games": round(g, 2), "p_miss": min(g, 1.0),
                              "detail": s.detail + (f"; missed the week {s.week} game, next status pending"
                                                    if missed_it else "")})
            live.append(s)
        official_weeks = {s.week for s in live if s.source in ("Official injury report", "Practice report")}
        live = [s for s in live if not (s.status == "INACTIVE" and s.week in official_weeks)]
        if not live:
            continue
        negatives = [s for s in live if s.games > 0]
        games = max((s.games for s in negatives), default=0.0)
        # a newer "cleared / full practice" beats older bad news of short duration
        newest_pos = max((_ts(s.when) for s in live if s.positive and _ts(s.when) is not None), default=None)
        newest_neg = max((_ts(s.when) for s in negatives if _ts(s.when) is not None), default=None)
        cleared = newest_pos is not None and (newest_neg is None or newest_pos > newest_neg) and games <= 1.0
        if cleared:
            games = min(games, 0.1)
        head = sorted(negatives or live, key=lambda s: (-s.games, SEVERITY.index(s.status) if s.status in SEVERITY else 99))[0]
        if cleared and negatives:
            head = max((s for s in live if s.positive and _ts(s.when) is not None), key=lambda s: _ts(s.when))
        status = head.status
        if status in ("HEALTHY", "NEWS") or (cleared and games <= 0.1 and status not in ("RETURNED",)):
            status = "CLEARED" if cleared and negatives else ("" if status == "HEALTHY" else status)
        if games == 0 and not (cleared and negatives):
            continue  # nothing here says he might miss time
        p_miss = max((s.p_miss if s.p_miss is not None else min(s.games, 1.0) for s in negatives), default=0.0)
        if cleared:
            p_miss = min(p_miss, 0.1)
        sig_list = sorted((asdict(s) for s in live), key=lambda d: str(d["when"]), reverse=True)
        rows.append({"player_id": pid, "inj_status": status or None, "inj_detail": head.detail,
                     "inj_source": head.source, "exp_missed_raw": games, "p_miss_next": p_miss,
                     "inj_updated": max((str(s.when) for s in live), default=""),
                     "inj_signals": [{k: v for k, v in d.items() if k not in ("player_id",)} for d in sig_list]})
    return pd.DataFrame(rows, columns=["player_id", "inj_status", "inj_detail", "inj_source", "exp_missed_raw", "p_miss_next",
                                       "inj_updated", "inj_signals"])
