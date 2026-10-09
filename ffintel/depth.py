"""Depth charts: who starts, who is next in line, and who just moved up or down.

Two sources:
  * Ourlads (all 32 teams on one page, kept by hand and usually updated a day or two
    after every game and again on transactions). Primary when available.
  * ESPN's depth charts, snapshotted twice a day by nflverse. Backup, and the history
    used to spot moves when there is no earlier Ourlads copy.

Moves are only ever measured within one source (Ourlads now vs Ourlads a few days ago,
ESPN now vs ESPN a week ago) because the two often order backups differently, and
comparing across them would invent promotions. A move is shown only if the current
primary chart agrees with where the player landed.
"""
import datetime as dt
import re

import pandas as pd
from bs4 import BeautifulSoup

from . import config, injuries, sources, web

OURLADS = "https://www.ourlads.com/nfldepthcharts/depthcharts.aspx"
OURLADS_TEAM = {"ARZ": "ARI", "LAR": "LA"}
OURLADS_POS = {"QB": "QB", "RB": "RB", "LWR": "WR", "RWR": "WR", "SWR": "WR", "TE": "TE"}
POSITIONS = ("QB", "RB", "WR", "TE")
STATUS: dict = {}


def _clean_name(raw: str) -> str:
    """'Odunze, Rome 24/1' -> 'Rome Odunze'; 'RAYMOND, KALIF U/Det' -> 'Kalif Raymond'."""
    t = raw.strip()
    t = re.sub(r"\s+(?:\d{2}/\d{1,2}|[A-Z]{1,3}\d{2}|[A-Z]{1,2}/[A-Za-z]{2,4}|\d{2}/[A-Z]+)$", "", t)
    if "," in t:
        last, first = [x.strip() for x in t.split(",", 1)]
        t = f"{first} {last}"
    if t.isupper():
        t = t.title()
    return t


def _last_name_index(players: pd.DataFrame) -> dict:
    """(normalized last name, team, position) -> id, only when exactly one player fits.
    Catches nicknames ("Hollywood Brown", "Joshua Palmer") that the full-name lookup misses."""
    p = players[players.position.isin(POSITIONS) & players.latest_team.notna() & (players.status == "ACT")]
    last = p.display_name.map(lambda n: injuries._norm(str(n).split()[-1]) if str(n).split() else "")
    keys = list(zip(last, p.latest_team, p.position))
    counts = pd.Series(keys).value_counts()
    return {k: pid for k, pid in zip(keys, p.gsis_id) if counts.get(k, 0) == 1}


def ourlads(nidx: dict, players: pd.DataFrame | None = None) -> pd.DataFrame:
    html = web.get_html("ourlads", OURLADS, "Ourlads depth charts", max_age_h=8,
                        valid=lambda h: "Offense - " in h and h.count("nfldepthcharts/player/") > 500)
    if not html:
        return pd.DataFrame()
    soup = BeautifulSoup(html, "lxml")
    updated = {}
    for h in soup.find_all("h2"):
        code = (h.get("class") or [""])[0]
        m = re.search(r"Updated:\s*([\d/]+\s+[\d:]+\s*[AP]M)", h.get_text(" ", strip=True))
        if code and m:
            try:
                updated[OURLADS_TEAM.get(code, code)] = pd.Timestamp(
                    dt.datetime.strptime(m.group(1).replace("  ", " "), "%m/%d/%Y %I:%M%p")).tz_localize(
                    "America/New_York").tz_convert("UTC").isoformat()
            except Exception:
                pass
    lni = _last_name_index(players) if players is not None else {}
    rows, section = [], None
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        text = tr.get_text(" ", strip=True)
        if not tds or not tds[0].find("b"):
            m = re.match(r"(Offense|Defense|Special Teams|Practice Squad|Reserves)\b", text)
            if m:
                section = m.group(1)
            continue
        if section != "Offense" or len(tds) < 4:
            continue
        team = OURLADS_TEAM.get(tds[0].get_text(strip=True), tds[0].get_text(strip=True))
        slot = tds[1].get_text(strip=True)
        pos = OURLADS_POS.get(slot)
        if not pos:
            continue
        depth = 0
        for td in tds[2:]:
            a = td.find("a")
            if a is None:
                continue
            raw = a.get_text(" ", strip=True)
            if not raw:
                continue
            depth += 1
            name = _clean_name(raw)
            pid = nidx.get((injuries._norm(name), team)) or nidx.get((injuries._norm(name), None))
            if pid is None and lni:
                parts = name.split()
                pid = lni.get((injuries._norm(parts[-1]) if parts else "", team, pos))
            rows.append({"team": team, "pos": pos, "slot": slot, "depth": depth, "name": name,
                         "player_id": pid, "updated": updated.get(team)})
    df = pd.DataFrame(rows)
    STATUS["Ourlads"] = f"{df.team.nunique() if len(df) else 0} teams"
    return df


def espn_snapshots(season: int) -> pd.DataFrame:
    d = sources.depth_charts(season)
    if d.empty:
        return d
    d = d[d.pos_abb.isin(POSITIONS)].copy()
    d["dt"] = pd.to_datetime(d.dt, utc=True)
    d = d.rename(columns={"pos_abb": "pos", "pos_rank": "depth", "gsis_id": "player_id", "player_name": "name"})
    d["slot"] = d.pos + d.pos_slot.astype(str)
    return d[["dt", "team", "pos", "slot", "depth", "name", "player_id"]]


def _order(chart: pd.DataFrame) -> pd.DataFrame:
    """One row per player and position: his depth level (1 = starter) and order in line."""
    if chart.empty:
        return chart
    c = chart.dropna(subset=["player_id"]).sort_values(["team", "pos", "depth", "slot"])
    c = c.drop_duplicates(["team", "pos", "player_id"])  # best spot if listed twice
    c["order"] = c.groupby(["team", "pos"]).cumcount() + 1
    return c


def _label(pos, depth, order):
    if pos == "WR":
        return "WR starter" if depth == 1 else f"WR backup (#{order})"
    return f"{pos}{order}"


def build(season: int, nidx: dict, players: pd.DataFrame) -> tuple[pd.DataFrame, list, dict]:
    """(current chart, moves, status). Chart columns: player_id, team, pos, depth, order, label, source."""
    now = pd.Timestamp.now(tz="UTC")
    try:
        ol = ourlads(nidx, players)
    except Exception as e:
        ol = pd.DataFrame()
        STATUS["Ourlads"] = f"unavailable ({type(e).__name__})"
    try:
        es = espn_snapshots(season)
    except Exception as e:
        es = pd.DataFrame()
        STATUS["ESPN depth charts"] = f"unavailable ({type(e).__name__})"
    es_now = pd.DataFrame()
    if len(es):
        latest = es.dt.max()
        es_now = _order(es[es.dt == latest].copy())
        STATUS["ESPN depth charts"] = f"{es_now.team.nunique()} teams (as of {latest:%b %d})"
    ol_now = _order(ol) if len(ol) else pd.DataFrame()

    # primary: Ourlads per team when it has the team and was updated in the last 10 days
    frames = []
    fresh_ol = set()
    if len(ol_now):
        upd = pd.to_datetime(ol_now.groupby("team").updated.first(), utc=True, errors="coerce")
        fresh_ol = {t for t, u in upd.items() if pd.notna(u) and (now - u).days <= 10}
        frames.append(ol_now[ol_now.team.isin(fresh_ol)].assign(source="Ourlads"))
    if len(es_now):
        frames.append(es_now[~es_now.team.isin(fresh_ol)].assign(source="ESPN", updated=str(es.dt.max().isoformat())))
    chart = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["team", "pos", "slot", "depth", "order", "name", "player_id", "source", "updated"])
    if len(chart):
        pos_of = dict(zip(players.gsis_id, players.position))
        ok = [pos_of.get(pid) == pos or (pos == "RB" and pos_of.get(pid) == "FB")
              for pid, pos in zip(chart.player_id, chart.pos)]
        chart = chart[ok].copy()  # a name matched to the wrong player (different position) is dropped
        chart["order"] = chart.sort_values(["team", "pos", "depth", "slot"]).groupby(["team", "pos"]).cumcount() + 1
        chart["label"] = [_label(p, d, o) for p, d, o in zip(chart.pos, chart.depth, chart.order)]

    moves = []
    cur_key = {(r.player_id, r.pos): r for r in chart.itertuples()} if len(chart) else {}

    def compare(now_c, before_c, source, since):
        if now_c.empty or before_c.empty:
            return
        b = {(r.player_id, r.pos): r for r in before_c.itertuples()}
        for r in now_c.itertuples():
            old = b.get((r.player_id, r.pos))
            if old is None or r.pos not in POSITIONS:
                continue
            if r.team != old.team:
                continue  # trades/signings show up elsewhere
            o_lab, n_lab = _label(r.pos, old.depth, old.order), _label(r.pos, r.depth, r.order)
            up = (r.pos == "WR" and old.depth > 1 and r.depth == 1) or \
                 (r.pos != "WR" and r.order < old.order and r.order <= 2)
            down = (r.pos == "WR" and old.depth == 1 and r.depth > 1) or \
                   (r.pos != "WR" and r.order > old.order and old.order == 1)
            if not (up or down):
                continue
            cur = cur_key.get((r.player_id, r.pos))
            if cur is None or _label(cur.pos, cur.depth, cur.order) != n_lab:
                continue  # the primary chart doesn't agree
            moves.append({"player_id": r.player_id, "name": r.name, "team": r.team, "pos": r.pos,
                          "from": o_lab, "to": n_lab, "direction": "up" if up else "down",
                          "source": source, "since": since})

    # Ourlads vs our own saved copy from 3-10 days ago
    hist_p = config.CACHE / "ourlads_history.parquet"
    try:
        hist = pd.read_parquet(hist_p) if hist_p.exists() else pd.DataFrame()
    except Exception:
        hist = pd.DataFrame()
    if len(ol_now):
        snap = ol_now[["team", "pos", "slot", "depth", "order", "name", "player_id"]].assign(
            snap=now.normalize().isoformat())
        hist = pd.concat([hist[hist.snap != snap.snap.iloc[0]] if len(hist) else hist, snap], ignore_index=True)
        hist = hist[pd.to_datetime(hist.snap, utc=True) >= now - pd.Timedelta(days=21)]
        try:
            hist.to_parquet(hist_p, index=False)
        except Exception:
            pass
        snaps = sorted(pd.to_datetime(hist.snap.unique(), utc=True))
        older = [s for s in snaps if pd.Timedelta(days=3) <= now - s <= pd.Timedelta(days=10)]
        if older:
            s0 = older[-1]
            compare(ol_now, hist[pd.to_datetime(hist.snap, utc=True) == s0], "Ourlads", s0.isoformat())
    # ESPN now vs ~7 days ago
    if len(es):
        target = es.dt.max() - pd.Timedelta(days=7)
        cand = sorted(t for t in es.dt.unique() if t <= target + pd.Timedelta(days=1))
        if cand:
            s0 = cand[-1]
            compare(es_now, _order(es[es.dt == s0].copy()), "ESPN", pd.Timestamp(s0).isoformat())
    seen, uniq = set(), []
    for m in sorted(moves, key=lambda m: m["source"] != "Ourlads"):
        if (m["player_id"], m["pos"]) not in seen:
            seen.add((m["player_id"], m["pos"]))
            uniq.append(m)
    return chart, uniq, dict(STATUS)


def next_up(chart: pd.DataFrame, team: str, pos: str, skip: set) -> str | None:
    """First player in line at a position who isn't in `skip` (injured / the starter)."""
    if chart is None or chart.empty:
        return None
    c = chart[(chart.team == team) & (chart.pos == pos)].sort_values("order")
    for pid in c.player_id:
        if pid not in skip:
            return pid
    return None
