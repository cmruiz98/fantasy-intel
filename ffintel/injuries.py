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
              "DNP": 0.3, "LIMITED": 0.1, "SNAPS DOWN": 0.1, "RETURNED": 0.05, "NEWS": 0.0, "HEALTHY": 0.0}
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
    mild: bool = False            # e.g. "minor sprain", "hoping to play": likely plays
    designated: bool = True       # carries a real status (feed, report, roster) or in-game evidence
    absence: bool = False         # text says outright that he will miss time
    timeline: bool = False        # explicit return date or "out X weeks": definitive, not a stale status


# ---------------------------------------------------------------- text reading
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "a couple": 2, "couple": 2, "a few": 3, "few": 3, "several": 4, "multiple": 3}
NEGATION = re.compile(r"(avoid|avoided|ruled out an?|no sign of|not an?|not (?:expected|believed|likely|going) to(?: \w+)?|negative|clean|isn't|is not|no structural|won't)\W+(?:\w+\W+){0,2}$", re.I)
POSITIVE = re.compile(r"\b(cleared|gained clearance|will play|expected to play|full(?:y)? participat|full practice|"
                      r"no injury designation|removed from (?:the )?injury report|activated|will suit up|suited up|"
                      r"returns? to practice fully|good to go|shed(?: the)? (?:questionable|doubtful)|"
                      r"upgraded to (?:full|active)|not on (?:the|his team's|[A-Z][a-z]+'s) (?:final )?injury report|"
                      r"practiced (?:in )?full|full participant|without (?:an )?injury designation|"
                      r"no (?:game )?designation|will start|is starting|expected to start|will be active|"
                      r"should be able to go|has been activated)\b", re.I)
MILD = re.compile(r"\b(minor|hop(?:es|eful|ing) to play|expects? to play|expected to play|optimistic|"
                  r"day[- ]to[- ]day|should be (?:ready|fine|good|available)|not (?:expected|believed) to (?:miss|be serious)|"
                  r"avoided (?:a )?(?:serious|major|significant|long[- ]term)|no structural damage|precaution(?:ary)?|"
                  r"good chance (?:to|of) play|on track to play|trending toward (?:being able to )?play(?:ing)?|likely to play|"
                  r"seen practicing|back at practice|returned to practice|"
                  r"nothing serious|isn't serious|not serious|won't miss|will not miss)\b", re.I)
# (pattern, expected games out, label), checked against text that is about this player.
# Timelines are typical recoveries for an NFL skill player; anything that ends a season
# in practice is 99. A specific timeline in the text ("out 2-4 weeks") overrides these
# whenever it is longer, and "avoided"/"no" negations and past-tense history are ignored.
INJURY_TYPES = [
    (r"\b(?:acl|anterior cruciate)\b(?![- ](?:sprain|scare))", 99.0, "ACL injury (season-ending)"),
    (r"\bachilles\b(?! (?:tendinitis|tendonitis|soreness|tightness))", 99.0, "Achilles injury (season-ending)"),
    (r"\b(?:torn|tore|ruptured?) (?:his )?(?:pec|pectoral|patellar|patella tendon|quad(?:riceps)? tendon)", 99.0, "tendon tear (season-ending)"),
    (r"\blisfranc\b", 10.0, "Lisfranc injury"),
    (r"\b(?:fractured?|broken) (?:leg|fibula|tibia|ankle|femur)\b|\b(?:leg|fibula|tibia|ankle) fracture", 8.0, "leg/ankle fracture"),
    (r"\b(?:fractured?|broken) (?:collarbone|clavicle)|\b(?:collarbone|clavicle) fracture", 7.0, "collarbone fracture"),
    (r"\btightrope\b", 6.0, "tightrope ankle surgery"),
    (r"\b(?:torn|tore) (?:his )?meniscus|meniscus (?:surgery|repair)", 5.0, "meniscus surgery"),
    (r"\bpcl\b", 4.0, "PCL injury"),
    (r"\bmcl\b", 3.0, "MCL sprain"),
    (r"\bturf toe\b", 3.0, "turf toe"),
    (r"\bsports hernia|core muscle surgery", 4.0, "core muscle surgery"),
]
ABSENCE = re.compile(r"\b(will miss|expected to miss|set to miss|could miss|likely to miss|ruled out|won't play|will not play|"
                     r"sidelined|shelved|placed [\w.'()/ -]{0,45}?on (?:injured reserve|ir)|(?:landed|moved|headed) (?:on|to) (?:injured reserve|ir)|"
                     r"season[- ]ending|out for the (?:season|year)|out (?:for )?(?:\d+|one|two|three|four|five|six|several|multiple) weeks|"
                     r"week[- ]to[- ]week|undergo(?:ing)? surgery|will have surgery|(?:suffered|sustained) a (?:torn|fractured|broken))\b", re.I)
# a timeline number only counts when the clause is about missing time
TIMELINE_CTX = re.compile(r"(miss|out\b|sidelined|shelved|recover|return|rehab|timeline|week[- ]to[- ]week|"
                          r"expected to be|could be|will be|placed|injur|sprain|strain|tear|surgery)", re.I)
HISTORY_CTX = re.compile(r"(offseason|last (?:year|season)|previous(?:ly)?|in the past|recovered from|returned from|"
                         r"back from|fully healed|a year ago|college)", re.I)
NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:['\-][A-Za-z]+)?\s+[A-Z][a-zA-Z.'\-]+\b")


def _clip(sent: str, full_name: str) -> str:
    """The part of one sentence that is about this player.

    "Coach Ben Johnson said Swift will play" -> "Swift will play" (a name before him is
    attribution or a teammate: start at him). "Jefferson is fine, but Addison will miss
    two weeks" -> "Jefferson is fine, but " (a name after him starts someone else's news).
    """
    last = full_name.split()[-1]
    low, at = sent.lower(), -1
    for key in (full_name.lower(), last.lower()):
        at = low.find(key)
        if at >= 0:
            break
    if at < 0:
        at = 0
    def other(m):
        n = m.group(0)
        return last.lower() not in n.lower() and full_name.lower() not in n.lower() and \
            not re.match(r"(Week|Thursday|Friday|Sunday|Monday|Wednesday|Tuesday|Saturday|NFL Network|ESPN)\b", n)
    before = [m for m in NAME_RE.finditer(sent) if m.end() <= at and other(m)]
    after = [m.start() for m in NAME_RE.finditer(sent) if m.start() > at and other(m)]
    start = at if before else 0
    end = min(after) if after else len(sent)
    return sent[start:end]


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
        kept.append(_clip(sent, full_name))
    return " ".join(k for k in kept if k.strip())


def _neg(text, start):
    seg = re.split(r"[.;]", text[max(0, start - 40):start])[-1]  # same clause only
    return bool(NEGATION.search(seg))


def text_severity(text: str) -> tuple[float, str] | None:
    """Best guess of games missed from injury news text; None if nothing found."""
    if not text:
        return None
    t = text.lower()
    best = None

    def clause(m):
        return re.split(r"[.;!?]", t[max(0, m.start() - 70):m.start()])[-1]

    def take(g, label, m, need_ctx=False):
        nonlocal best
        if m is not None and _neg(t, m.start()):
            return
        after = re.split(r"[.;!?]", t[m.end():m.end() + 45])[0] if m is not None else ""
        if m is not None and (HISTORY_CTX.search(clause(m)) or HISTORY_CTX.search(after)):
            return  # "had offseason surgery", "returned from a torn ACL last year"
        if need_ctx and m is not None and not TIMELINE_CTX.search(clause(m) + t[m.end():m.end() + 25]):
            return  # "over the past two weeks" is a stat line, not a timeline
        if best is None or g > best[0]:
            best = (g, label)

    for pat in (r"season[- ]ending", r"out for the (?:season|year|rest of the season)", r"torn (?:acl|achilles)",
                r"(?:acl|achilles) (?:tear|rupture)", r"ruptured achilles"):
        m = re.search(pat, t)
        if m:
            take(99.0, "season-ending", m)
    # Injury types with well-known recovery times. Feeds often give only the body part and
    # procedure ("Knee - ACL: Surgery"), never the words "season-ending".
    for pat, g, label in INJURY_TYPES:
        m = re.search(pat, t)
        if m:
            take(g, label, m)
    m = re.search(r"placed [\w.'()/ -]{0,45}?on (?:injured reserve|ir)\b|(?:landed|moved|headed) (?:on|to) (?:injured reserve|ir)\b|\bon injured reserve\b", t)
    if m:
        take(4.0, "injured reserve", m)
    spans = []
    for m in re.finditer(r"(\d+|one|two|three|four|five|six|seven|eight)\s*(?:-|to|or)\s*(\d+|two|three|four|five|six|seven|eight|ten|twelve)\s*weeks", t):
        a, b = (int(WORDNUM.get(x, x)) for x in m.groups())
        spans.append(m.span())
        take((a + b) / 2, f"{m.group(0)}", m, need_ctx=True)
    for m in re.finditer(r"\b(\d+|one|two|three|four|five|six|a couple|couple|a few|few|several|multiple)\s+(?:more\s+)?weeks", t):
        if any(a <= m.start() < b for a, b in spans):
            continue  # part of a range already counted
        w = m.group(1)
        n = int(w) if w.isdigit() else WORDNUM.get(w, 2)
        take(float(n), m.group(0), m, need_ctx=True)
    for pat, g, label in ((r"week[- ]to[- ]week", 2.0, "week-to-week"), (r"high[- ]ankle", 2.5, "high-ankle sprain"),
                          (r"\bsurgery\b", 4.0, "surgery"),
                          (r"\bfractured?\b|\bbroken (?:leg|arm|hand|foot|ankle|collarbone|clavicle|rib|ribs|finger|thumb|wrist|bone|fibula|tibia|fibula|toe|jaw|nose|back)\b", 4.0, "fracture"),
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


def early_exits(pbp: pd.DataFrame, cur: pd.DataFrame, already: set) -> list[Signal]:
    """Starters who vanished from a game early without an injury being logged.

    The play-by-play does not always record injuries. A regular who plays a fraction of his
    usual snaps and is never involved in a play after the first half almost always got hurt
    (Jefferson in week 3: 12% of snaps, last touch in the first quarter).
    """
    out = []
    if pbp.empty or cur.empty or "snap_pct" not in cur:
        return out
    c = cur.dropna(subset=["snap_pct"]).sort_values("week")
    last_week = int(c.week.max())
    p = pbp[(pbp.season_type == "REG") & (pbp.week == last_week)]
    touch = pd.concat([p[["game_id", "qtr", "time", col]].rename(columns={col: "pid"})
                       for col in ("receiver_player_id", "rusher_player_id", "passer_player_id") if col in p])
    touch = touch.dropna(subset=["pid"]).sort_values(["qtr", "time"], ascending=[True, False])
    last_touch = touch.groupby("pid").tail(1).set_index("pid")
    for pid, g in c.groupby("player_id"):
        if pid in already or len(g) < 2 or int(g.week.iloc[-1]) != last_week:
            continue
        usual, now = g.iloc[:-1].snap_pct.mean(), g.iloc[-1].snap_pct
        if usual < 0.6 or now > 0.45 * usual:
            continue
        lt = last_touch.loc[pid] if pid in last_touch.index else None
        if lt is None or float(lt.qtr) <= 2:
            when = f"after Q{int(lt.qtr)} {lt.time}" if lt is not None else "early"
            out.append(Signal(pid, "LEFT GAME", 1.0,
                              f"Played {now:.0%} of snaps in week {last_week} (usually {usual:.0%}) and had no touches "
                              f"{when}. Likely left injured; the injury was not logged.",
                              "Snap counts + play-by-play", "", last_week, p_miss=0.4))
    return out


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
    """Latest official report per player, plus practice participation.

    Teams file practice participation Wednesday-Thursday and game designations (Out,
    Doubtful, Questionable) with Friday's final report. Until a team's final report is in
    the data, "limited" or "no game status" means nothing has been decided yet. It is NOT a
    clean bill of health, and a fresher designation from beat reporters or ESPN must win.
    """
    out = []
    if inj.empty:
        return out
    final_filed = set(map(tuple, inj[inj.report_status.notna()][["team", "week"]].drop_duplicates().values.tolist()))
    latest = inj.sort_values("week").groupby("gsis_id").tail(1)
    for r in latest.itertuples(index=False):
        injury = r.report_primary_injury if pd.notna(r.report_primary_injury) else r.practice_primary_injury
        when = report_dates.get((r.team, int(r.week)), "")
        practice_when = ""
        if when:  # practice-only reports come out a day or two before the final report
            practice_when = (pd.Timestamp(when) - pd.Timedelta(hours=22)).isoformat()
        st = str(r.report_status).upper() if pd.notna(r.report_status) else ""
        practice = str(r.practice_status) if pd.notna(r.practice_status) else ""
        final = (r.team, r.week) in final_filed
        if st in BASE_GAMES:
            out.append(Signal(r.gsis_id, st, BASE_GAMES[st], f"{injury}: {st.title()} for week {r.week}"
                              + (f" ({practice.lower()})" if practice else ""), "Official injury report", when, int(r.week)))
        elif final and practice:
            # on the final report with no game designation: he's playing
            out.append(Signal(r.gsis_id, "HEALTHY", 0.0, f"{injury}: {practice.lower()}, no game designation (week {r.week})",
                              "Official injury report", when, int(r.week), positive=True))
        elif "Did Not" in practice and "Not injury" not in str(injury):
            out.append(Signal(r.gsis_id, "DNP", BASE_GAMES["DNP"], f"{injury}: did not practice (week {r.week})",
                              "Practice report", practice_when, int(r.week)))
        elif "Not injury" in str(injury):
            continue  # rest days aren't injuries
        elif "Full" in practice:
            out.append(Signal(r.gsis_id, "HEALTHY", 0.0, f"{injury}: full practice (week {r.week})",
                              "Practice report", practice_when, int(r.week), positive=True))
        elif "Limited" in practice:
            out.append(Signal(r.gsis_id, "LIMITED", BASE_GAMES["LIMITED"], f"{injury}: limited in practice (week {r.week}); "
                              "game status comes with Friday's final report", "Practice report", practice_when,
                              int(r.week), mild=True))
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
            raw_status = str(it.get("status") or (it.get("type") or {}).get("description") or "").strip().lower()
            status = _status(it.get("status")) or _status((it.get("type") or {}).get("description"))
            if raw_status == "active":
                # ESPN lists healthy players too; "Active" is a clean bill of health
                pos_active = True
                status = None
            else:
                pos_active = False
            details = it.get("details") or {}
            body = " ".join(str(details.get(k, "")) for k in ("side", "type", "detail") if details.get(k)).strip()
            comment = it.get("longComment") or it.get("shortComment") or ""
            mine = about_player(comment, ath.get("displayName", ""))
            if status and body:  # ESPN's structured injury fields ("Knee", "ACL", "Surgery") describe him
                mine = f"{body}. {mine}"
            games = BASE_GAMES.get(status, 0.0) if status else 0.0
            sev = text_severity(mine)  # only what the blurb says about HIM
            absence = bool(ABSENCE.search(mine))
            if not status and not absence:
                sev = None  # a write-up with no designation is commentary, not an injury
            elif sev and not status:
                sev = (min(sev[0], 2.0), sev[1])
            if sev and sev[0] > games:
                games = sev[0]
            label = status or ("SEASON" if games >= 99 else "OUT" if games >= 1 else
                               "QUESTIONABLE" if games >= 0.3 else "NEWS")
            timeline = bool(sev and sev[0] >= 1 and absence)
            if details.get("returnDate") and status:
                g = _games_from_return(details["returnDate"], tabbr, game_dates)
                if g is not None and status in ("OUT", "IR", "PUP", "SUSPENSION", "SEASON") and g >= 1:
                    games = max(g, games)  # never let a return date shrink a stated timeline
                    timeline = True
            positive = bool(POSITIVE.search(mine or comment)) or (pos_active and not absence)
            mild = bool(MILD.search(mine)) and not positive
            if positive and not status:
                games, label = 0.0, "NEWS"  # the write-up says he is fine
            elif mild and games < 1.5:
                games = min(games, 0.3) if games else 0.25
                label = status if status in ("QUESTIONABLE", "OUT", "DOUBTFUL") else "QUESTIONABLE"
            if games <= 0 and not status and not positive:
                continue  # a blurb about a healthy player, not an injury
            detail = (f"{body}. " if body else "") + (comment[:260] if comment else (status or "").title())
            if details.get("returnDate"):
                detail += f" (ESPN return estimate: {details['returnDate'][:10]})"
            out.append(Signal(pid, label, games, detail, "ESPN injury desk", it.get("date", ""),
                              positive=positive, mild=mild, designated=bool(status) or pos_active, absence=absence,
                              timeline=timeline and not positive and not mild))
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
        body_txt = " ".join(str(p.get(k) or "") for k in ("injury_body_part", "injury_notes"))
        sev = text_severity(body_txt)
        if sev and sev[0] > games:
            games = sev[0]
        mild = bool(MILD.search(notes)) and games < 1.5
        timeline = bool(sev and sev[0] >= 1 and ABSENCE.search(notes)) and not mild
        upd = p.get("news_updated")
        when = dt.datetime.fromtimestamp(upd / 1000, dt.timezone.utc).isoformat() if upd else ""
        body = p.get("injury_body_part") or ""
        out.append(Signal(pid, "SEASON" if games >= 99 else status, games,
                          f"{body}{': ' if body and notes else ''}{notes}".strip() or status.title(),
                          "Sleeper", when, mild=mild, timeline=timeline))
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
            mine = about_player(text, c.get("description", "")) if c.get("description") else text
            if not mine.strip():
                continue
            sev = text_severity(mine)
            pos = bool(POSITIVE.search(mine)) and not sev
            games = sev[0] if sev else 0.0
            mild = bool(MILD.search(mine)) and games < 1.5
            if games < 0.3 and not pos and not mild:
                continue  # mentions an injury topic but says nothing about him missing time
            if mild:
                games = min(games, 0.3) if games else 0.25
            label = "SEASON" if games >= 99 else ("NEWS" if games < 0.3 else ("OUT" if games >= 1 else "QUESTIONABLE"))
            out.append(Signal(pid, label, games, a.get("headline", "")[:200], "ESPN news", pub,
                              positive=pos, mild=mild, designated=False,
                              absence=bool(ABSENCE.search(mine)),
                              timeline=bool(ABSENCE.search(mine)) and games >= 1 and not mild))
    return out


INJURY_WORDS = re.compile(r"injur|hurt|ankle|knee|hamstring|groin|concussion|mri|surgery|out for|ruled out|"
                          r"week-to-week|\bir\b|injured reserve|torn|sprain|strain|fracture|questionable|doubtful|"
                          r"cleared|activated|return", re.I)


ROTOWORLD = "https://www.nbcsports.com/fantasy/football/player-news"
ROTO_PAGES = 8   # 10 blurbs a page; 8 pages cover about the last day
ROTO_TEAM = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX", "ARZ": "ARI", "NOR": "NO", "GBP": "GB", "KCC": "KC",
             "NEP": "NE", "SFO": "SF", "TBB": "TB", "LVR": "LV"}
DESIGNATED = re.compile(r"\b(?:is|was|been|remains|listed as|considered|labeled) (?:officially )?(?:questionable|doubtful|out)\b|"
                        r"\bruled out\b|placed [\w.'()/ -]{0,45}?on (?:injured reserve|ir)\b|\bdid not practice\b|"
                        r"\bdnp\b|\bsat out practice\b|\bmissed practice\b|\blimited (?:in |at )?practice\b|"
                        r"\blogged a limited\b|\binactive\b|\bwill not play\b|\bwon't play\b|\bwill miss\b", re.I)
PRACTICE_DNP = re.compile(r"\b(did not practice|dnp|sat out practice|missed practice|no practice)\b", re.I)
PRACTICE_LTD = re.compile(r"\b(limited (?:in |at )?practice|logged a limited|limited session|limited participant|was limited|"
                          r"limited (?:on|in) (?:mon|tues|wednes|thurs|fri|satur|sun)day)\b", re.I)


def _subject_text(text: str, full_name: str) -> str:
    """Sentences of a single-player blurb that are about him: his name or a leading he/his,
    cut off where another player's name starts."""
    last = full_name.split()[-1].lower() if full_name else ""
    kept = []
    for sent in re.split(r"(?<=[.!?])\s+", text or ""):
        low = sent.lower()
        if last not in low and not re.match(r"(he|his|him)\b", low):
            continue
        kept.append(_clip(sent, full_name))
    return " ".join(kept)


def rotoworld_feed(nidx: dict) -> list[Signal]:
    """Rotoworld/NBC player news: blurbs written from beat reporters, coaches' press
    conferences and practice reports, usually within minutes. Each blurb is about one
    player and cites the reporter. Fetched free; Firecrawl only if NBC blocks us."""
    from bs4 import BeautifulSoup
    from . import web

    out, seen = [], set()
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    pages_ok = 0
    for n in range(1, ROTO_PAGES + 1):
        url = ROTOWORLD if n == 1 else f"{ROTOWORLD}?p={n}"
        html = web.get_html(f"rotoworld_p{n}", url, "Rotoworld news", max_age_h=1.5 if n <= 3 else 4,
                            valid=lambda h: "PlayerNewsPost-headline" in h,
                            priority="normal" if n == 1 else "low", fc_every_h=3 if n == 1 else 8,
                            stale_days=1, category=f"rotoworld{n}",
                            category_cap=None if n <= 3 else 0)  # pages 4-8: free fetch only
        if html is None:
            if n == 1:
                raise RuntimeError("NBC player news unreachable")
            break
        pages_ok += 1
        for p in BeautifulSoup(html, "lxml").select("div.PlayerNewsPost"):
            def txt(sel):
                el = p.select_one(sel)
                return el.get_text(" ", strip=True) if el else ""
            first, last = txt(".PlayerNewsPost-firstName"), txt(".PlayerNewsPost-lastName")
            name = f"{first} {last}".strip() or txt(".PlayerNewsPost-name")
            team = txt(".PlayerNewsPost-team-abbr")
            team = ROTO_TEAM.get(team, team)
            head, body = txt(".PlayerNewsPost-headline"), txt(".PlayerNewsPost-analysis")
            kind = txt(".PlayerNewsPost-type")
            d = p.select_one(".PlayerNewsPost-date")
            when = d.get("data-date") if d is not None else ""
            src = p.select_one(".PlayerNewsPost-source a")
            reporter = src.get_text(" ", strip=True) if src is not None else ""
            key = (name, head)
            if not name or not head or key in seen:
                continue
            seen.add(key)
            try:
                if pd.Timestamp(when) < cutoff:
                    continue
            except Exception:
                pass
            pid = nidx.get((_norm(name), team)) or nidx.get((_norm(name), None))
            if not pid:
                continue
            text = f"{head} {body}"
            mine = _subject_text(text, name)
            if kind not in ("Injury", "Transaction") and not INJURY_WORDS.search(mine):
                continue
            hmine = _subject_text(head, name) or head
            sev = text_severity(mine)
            positive = bool(POSITIVE.search(hmine)) or (bool(POSITIVE.search(mine)) and not sev)
            mild = bool(MILD.search(mine)) and not positive
            designated = bool(DESIGNATED.search(hmine))
            absence = bool(ABSENCE.search(mine))
            games = sev[0] if sev else 0.0
            low = hmine.lower()
            if re.search(r"\bruled out\b|\bis out\b|will not play|won't play|will miss|\binactive\b", low):
                status, games = ("OUT", max(games, 1.0))
            elif "doubtful" in low:
                status, games = "DOUBTFUL", max(games, 0.8)
            elif "questionable" in low:
                status, games = "QUESTIONABLE", max(games, 0.25)
            elif re.search(r"(injured reserve|\bir\b)", low) and re.search(r"placed|landed|moved|headed|to ir|on ir", low) \
                    and not POSITIVE.search(low):
                status, games = "IR", max(games, 4.0)
            elif PRACTICE_DNP.search(hmine):
                status, games = "DNP", max(games, 0.3)
            elif PRACTICE_LTD.search(hmine):
                status, games = "QUESTIONABLE", max(min(games, 0.3), 0.15)
                mild = True
            else:
                status = None  # nothing explicit in the headline: label from the text below
            if positive:
                status, games = "NEWS", 0.0
            elif mild and games < 1.5:
                games = min(games, 0.3) if games else 0.25
            if status is None:
                status = "SEASON" if games >= 99 else "OUT" if games >= 1 else "QUESTIONABLE" if games >= 0.25 else "NEWS"
            if games <= 0 and not positive and not mild:
                continue
            detail = head + (f" (via {reporter})" if reporter else "")
            wk = re.search(r"\bWeek (\d{1,2})\b", head)
            week = int(wk.group(1)) if wk and status in ("OUT", "DOUBTFUL", "QUESTIONABLE") \
                and not re.search(r"to return|return to", head, re.I) else None  # in-game updates aren't a game call
            out.append(Signal(pid, status, games, detail[:240], "Rotoworld (beat reporters)", when, week,
                              positive=positive, mild=mild, designated=designated or positive,
                              absence=absence, timeline=absence and games >= 1 and not mild))
    return out


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
                mild = bool(MILD.search(text)) and games < 1.5
                if games < 0.3 and not pos and not mild:
                    continue  # injury-flavoured headline, no actual availability news
                if mild:
                    games = min(games, 0.3) if games else 0.25
                status = "SEASON" if games >= 99 else ("NEWS" if games < 0.3 else
                                                      ("OUT" if games >= 1 else "QUESTIONABLE"))
                out.append(Signal(pid, status, games, title[:200], f"{label} news", when,
                                  positive=pos and not sev, mild=mild, designated=False,
                                  absence=bool(ABSENCE.search(text)),
                                  timeline=bool(ABSENCE.search(text)) and games >= 1 and not mild))
    if errors and not out:
        raise RuntimeError("; ".join(errors))
    return out


def league_signals(league_injuries: dict) -> list[Signal]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return [Signal(pid, st, BASE_GAMES.get(st, 0.0), detail, "Your ESPN league", now)
            for pid, (st, detail) in (league_injuries or {}).items()]


# ---------------------------------------------------------------- merge
def _ts(s):
    """Parse a timestamp to UTC; None when missing. (NaT is truthy and never compares, so it must not leak.)"""
    if not s:
        return None
    try:
        t = pd.Timestamp(s)
    except Exception:
        return None
    if pd.isna(t):
        return None
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


OFFICIAL = ("Official injury report", "Practice report")
LONG_STATUSES = {"SEASON", "IR", "PUP", "NFI", "SUSPENSION", "UNAVAILABLE"}
GAME_STATUSES = {"OUT", "DOUBTFUL", "QUESTIONABLE", "DNP", "LIMITED", "LEFT GAME", "INACTIVE", "SNAPS DOWN"}
# Chance he misses the NEXT game when a live feed still shows a status but this week's
# official report is not out yet. Early in the week that status usually describes the game
# just played, and most players listed "Out" for one game are back within a week or two.
PENDING_P = {"OUT": 0.55, "DOUBTFUL": 0.4, "QUESTIONABLE": 0.2, "LEFT GAME": 0.5, "INACTIVE": 0.45,
             "DNP": 0.3, "LIMITED": 0.1, "SNAPS DOWN": 0.1}
REPORT_P = {"OUT": 1.0, "DOUBTFUL": 0.8, "QUESTIONABLE": 0.25, "DNP": 0.3}


def combine(signals: list[Signal], report_weeks: dict, player_team: dict, last_played: dict,
            team_last_week: dict | None = None, plan_week: int | None = None,
            practice_weeks: dict | None = None) -> pd.DataFrame:
    """One row per player: headline status, chance to play next game, games expected missed.

    The rules, in order of authority:
      1. This week's official report (for the game about to be played) is the final word,
         and a team that has filed one without listing him means he is fine.
      2. Multi-week information (IR, "out 4-6 weeks", season-ending) holds until something
         newer says he has been cleared or activated.
      3. Otherwise the NEWEST short-term information wins. A status on a live feed before the
         week's report is out usually describes the last game, so it counts as "pending"
         rather than a certain absence, and newer mild news ("minor", "hoping to play")
         caps the risk.
    """
    team_last_week = team_last_week or {}
    practice_weeks = practice_weeks or {}
    by = {}
    for s in signals:
        by.setdefault(s.player_id, []).append(s)
    rows = []
    for pid, sigs in by.items():
        team = player_team.get(pid)
        tlw = team_last_week.get(team, 0)
        live = []
        for s in sigs:
            if s.status in ("LEFT GAME", "RETURNED", "SNAPS DOWN") and s.week is not None \
                    and report_weeks.get(team, 0) > s.week:
                continue  # superseded by a later game-status report
            if s.source in OFFICIAL and s.week is not None and last_played.get(pid, 0) >= s.week:
                continue  # a report for a game he then played is resolved
            live.append(s)
        if not live:
            continue
        # Nobody gets marked injured on commentary alone: there must be a real designation
        # (ESPN, Sleeper, official report, your league, roster move) or in-game evidence,
        # or text that says outright he will miss time.
        live = [s for s in live if s.designated or s.absence or s.positive or s.mild]
        if not any(s.designated or s.absence for s in live if s.games > 0):
            continue

        report_filed = plan_week is not None and practice_weeks.get(team, 0) >= plan_week
        # only the FINAL report (game designations) is the last word; practice participation
        # earlier in the week competes on recency with beat reporters and ESPN
        this_week = [s for s in live if s.source == "Official injury report" and s.week == plan_week]
        practice_now = [s for s in live if s.source == "Practice report" and s.week == plan_week]
        past_official = [s for s in live if s.source in OFFICIAL and s.week is not None
                         and (plan_week is None or s.week < plan_week) and s.games > 0]
        good = [s for s in live if (s.positive or s.mild) and _ts(s.when) is not None]
        newest_good = max(good, key=lambda s: _ts(s.when)) if good else None
        long = [s for s in live if (s.games >= 1.5 or s.status in LONG_STATUSES or (s.timeline and s.games >= 1))
                and not s.mild]
        short = [s for s in live if s not in long and (s.source not in OFFICIAL or s in practice_now)
                 and s.status in GAME_STATUSES and s.games > 0]

        # --- 2. multi-week
        lt, lt_head = 0.0, None
        for s in long:
            ts = _ts(s.when)
            overridden = newest_good is not None and ts is not None and _ts(newest_good.when) > ts \
                and (newest_good.positive or s.status not in ("IR", "PUP", "NFI", "SEASON", "SUSPENSION"))
            if not overridden and s.games > lt:
                lt, lt_head = s.games, s
        # --- 1 & 3. the next game
        note, head = "", None
        if this_week:
            head = max(this_week, key=lambda s: REPORT_P.get(s.status, 0))
            p = 0.0 if head.positive else REPORT_P.get(head.status, head.p_miss if head.p_miss is not None else min(head.games, 1))
        elif report_filed and not past_official and not practice_now:
            p, head = 0.0, None  # team filed this week's report and he is not on it: he's fine
        else:
            cands = short + past_official
            # a dated call on THIS week's game ("questionable for Week 5") beats feeds that only
            # carry a current status with no date of their own
            calls = [s for s in cands if s.source not in OFFICIAL and s.week is not None and s.week == plan_week
                     and s.week > tlw and s.status in ("OUT", "DOUBTFUL", "QUESTIONABLE")]
            if calls:
                cands = calls
            if cands:
                head = max(cands, key=lambda s: (_ts(s.when) or pd.Timestamp(0, tz="UTC"), s.games))
                game_call = head.source not in OFFICIAL and head.week is not None and head.week == plan_week \
                    and head.week > tlw and head.status in ("OUT", "DOUBTFUL", "QUESTIONABLE")
                if head.status == "LEFT GAME" and head.p_miss is not None:
                    p = head.p_miss
                elif game_call:  # "ruled out for Week 5" / "questionable for Week 5": a call on THIS game
                    p = REPORT_P[head.status]
                else:
                    p = PENDING_P.get(head.status, min(head.games, 1.0))
                if head in past_official:  # he sat out the last game with this
                    p = 0.6 if last_played.get(pid, 0) < (head.week or 0) else p
                note = "" if game_call else " This week's final injury report is not out yet."
            else:
                p = 0.0
            if newest_good is not None and (head is None or (_ts(head.when) or pd.Timestamp(0, tz="UTC"))
                                            <= _ts(newest_good.when)):
                cap = 0.1 if newest_good.positive else 0.3
                if p > cap or head is None or (newest_good.positive and p >= cap):
                    p, head, note = min(p, cap) if head else (0.0 if newest_good.positive else 0.25), \
                        newest_good, ""
        if lt >= 1:
            p = 1.0
        games = max(lt, p)
        if games <= 0.02 and not good:
            continue
        top = lt_head if lt >= 1 else head
        if top is None:
            top = newest_good or live[0]
        status = top.status
        if top is newest_good and newest_good is not None:
            status = "CLEARED" if newest_good.positive else ("LIMITED" if newest_good.status == "LIMITED" else "QUESTIONABLE")
        elif lt >= 1 and status in ("QUESTIONABLE", "DOUBTFUL", "LIMITED", "DNP", "TBD"):
            status = "OUT"  # the text behind a game-day tag says he'll miss time
        elif (top in short or top in past_official) and not this_week and lt < 1 \
                and top.status in ("OUT", "DOUBTFUL", "INACTIVE") and p < 0.8:
            status = "TBD"  # last game's status; this week's is not known yet
        if games <= 0.02 and status not in ("CLEARED",):
            continue
        sig_list = sorted((asdict(s) for s in live), key=lambda d: str(d["when"]), reverse=True)
        detail = top.detail.strip()
        if note and top is head and lt < 1:  # "report pending" only matters for game-to-game statuses
            detail = (detail if detail.endswith((".", "!", "?")) else detail + ".") + note
        rows.append({"player_id": pid, "inj_status": status or None,
                     "inj_detail": detail, "inj_source": top.source,
                     "exp_missed_raw": round(games, 2), "p_miss_next": round(min(p, 1.0), 2),
                     "inj_updated": max((str(s.when) for s in live), default=""),
                     "inj_signals": [{k: v for k, v in d.items() if k != "player_id"} for d in sig_list]})
    return pd.DataFrame(rows, columns=["player_id", "inj_status", "inj_detail", "inj_source", "exp_missed_raw",
                                       "p_miss_next", "inj_updated", "inj_signals"])
