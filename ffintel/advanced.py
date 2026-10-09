"""Advanced receiving and rushing stats from PlayerProfiler's free player pages.

Adds what the public play-by-play can't measure: routes run and route participation
(the share of his team's dropbacks he ran a route on), targets per route run, yards per
route run, first-read target share, separation, slot rate, and for backs opportunity
share and weighted opportunities.

These are shown on the dashboard and used in waiver and trade explanations ("runs a route
on 92% of dropbacks, up from 61% two weeks ago"). They don't change projections: they
exist for the current season only, so there is no history to measure how much weight
they deserve, and the projection's snap and target data already capture most of the role.

One page per player, refreshed about weekly (PlayerProfiler updates advanced numbers
mid-week). Fetched free; if PlayerProfiler blocks GitHub's servers, a few pages per run
go through Firecrawl, capped at PP_FIRECRAWL_MONTHLY credits a month.
"""
import io
import json
import re
import time

import pandas as pd

from . import config, web

BASE = "https://www.playerprofiler.com/nfl/{slug}/"
PER_RUN = 45                 # pages fetched per run (free)
PP_FIRECRAWL_PER_RUN = 4
PP_FIRECRAWL_MONTHLY = 200
REFRESH_DAYS = 6
TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}
FIELDS = {  # dashboard key: (PlayerProfiler label, kind)
    "routes_pg": ("Routes Run", "per_game"),
    "route_pct": ("Route Participation", "pct"),
    "tprr": ("Target Rate", "pct"),
    "yprr": ("Yards Per Route Run", "num"),
    "fr_share": ("First Read Target Share", "pct"),
    "separation": ("Target Separation", "num"),
    "slot_rate": ("Slot Snaps", "paren_pct"),
    "catchable": ("Catchable Target Rate", "pct"),
    "opp_share": ("Opportunity Share", "pct"),
    "wopp_pg": ("Weighted Opportunities", "per_game"),
    "pp_xfp_pg": ("Expected Fantasy Points Per Game", "num"),
}


def slug(name: str) -> str:
    n = re.sub(r"\b(Jr|Sr|II|III|IV|V)\b\.?", "", str(name))
    n = re.sub(r"[.'’]", "", n).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-")


def _num(s):
    m = re.search(r"-?\d+(?:\.\d+)?", str(s))
    return float(m.group(0)) if m else None


def _value(raw, kind):
    raw = str(raw)
    if raw.strip() in ("--", "-", "nan", ""):
        return None
    if kind == "pct":
        return _num(raw)
    if kind == "num":
        return _num(raw)
    if kind == "per_game":
        m = re.search(r"\(([\d.]+) p/g\)", raw)
        return float(m.group(1)) if m else None
    if kind == "paren_pct":
        m = re.search(r"\(([\d.]+)% rate\)", raw)
        return float(m.group(1)) if m else None
    return None


MISMATCH = {"mismatch": True}


def parse(html: str, season: int, team: str, pos: str) -> dict | None:
    """Stats dict, or None if the page isn't this player or has no current-season data."""
    m = re.search(r'View ([A-Za-z0-9 .]+?) (QB|RB|WR|TE) ', html)
    if not m or m.group(1) != TEAM_NAMES.get(team) or m.group(2) != pos:
        return MISMATCH  # same name, different player (or moved teams since PlayerProfiler updated)
    if "<table" not in html:
        return None
    tables = pd.read_html(io.StringIO(html))
    if not tables:
        return None
    first = tables[0]
    if str(first.iloc[0, 0]).strip() != str(season):
        return None  # no games this season yet
    flat = {}
    for t in tables:
        if t.shape[0] == 2:
            for c in t.columns:
                flat[re.sub(r"\s+", " ", str(c)).strip()] = t.iloc[0][c]
    out = {}
    for key, (label, kind) in FIELDS.items():
        col = next((c for c in flat if c == label or c.startswith(label + " ")), None)
        if col is not None:
            v = _value(flat[col], kind)
            if v is not None:
                out[key] = v
    # weekly route participation (WR/TE tables have "Routes: 21 (55.3% rate)")
    for t in tables:
        cols = [re.sub(r"\s+", " ", str(c)) for c in t.columns]
        rc = next((i for i, c in enumerate(cols) if c.startswith("Routes")), None)
        wc = next((i for i, c in enumerate(cols) if c.startswith("Week")), None)
        if rc is None or wc is None:
            continue
        wk = []
        for _, r in t.iterrows():
            w = _num(r.iloc[wc])
            p = re.search(r"\(([\d.]+)% rate\)", str(r.iloc[rc]))
            if w is not None and p:
                wk.append((int(w), float(p.group(1))))
        if wk:
            out["route_weeks"] = wk[-6:]
        break
    return out or None


def fetch(df: pd.DataFrame, priority_ids: list) -> dict:
    """{player_id: stats} for the given players, most important first.

    Pages are cached for REFRESH_DAYS; up to PER_RUN are refreshed each run, so a full
    sweep of rostered players and top free agents takes a few runs early in the week.
    """
    rows = df.set_index("player_id")
    slug_p = config.CACHE / "pp_slugs.json"
    try:
        known = json.loads(slug_p.read_text())
    except Exception:
        known = {}
    out, fetched, fc_start = {}, 0, web.STATUS.get("PlayerProfiler", {}).get("firecrawl", 0)
    for pid in priority_ids:
        if pid not in rows.index:
            continue
        r = rows.loc[pid]
        if r.position not in ("RB", "WR", "TE") or not isinstance(r.team, str):
            continue
        base = slug(r["name"])
        # Same-name players get "-2", "-3" on PlayerProfiler (Marvin Harrison Jr. is marvin-harrison-2)
        cands = [known[pid]] if pid in known else [base, f"{base}-2", f"{base}-3"]
        for sl in cands:
            key = f"pp_{sl}"
            when = web.fetched_at(key)
            due = when is None or (pd.Timestamp.now(tz="UTC") - pd.Timestamp(when)).days >= REFRESH_DAYS
            if due and fetched >= PER_RUN:
                html = web.read_saved(key)  # not this run: saved copy if any
            else:
                fc_used = web.STATUS.get("PlayerProfiler", {}).get("firecrawl", 0) - fc_start
                html = web.get_html(key, BASE.format(slug=sl), "PlayerProfiler",
                                    max_age_h=REFRESH_DAYS * 24,
                                    valid=lambda h: "Fantasy Football Stats" in h and "PlayerProfiler" in h,
                                    priority="low", stale_days=21, category="playerprofiler",
                                    category_cap=PP_FIRECRAWL_MONTHLY if fc_used < PP_FIRECRAWL_PER_RUN else 0)
                if due:
                    fetched += 1
                    time.sleep(0.4)  # be polite
            if not html:
                break
            try:
                st = parse(html, config.SEASON, r.team, r.position)
            except Exception:
                st = None
            if st is MISMATCH:
                continue  # someone else with his name: try the next address
            known[pid] = sl
            if st:
                st["pp_url"] = BASE.format(slug=sl)
                st["pp_updated"] = web.fetched_at(key)
                out[pid] = st
            break
    try:
        slug_p.write_text(json.dumps(known))
    except Exception:
        pass
    return out


def reasons(st: dict | None, pos: str) -> list[str]:
    """Plain-English notes for waiver/trade explanations."""
    if not st:
        return []
    out = []
    wk = st.get("route_weeks") or []
    rp = st.get("route_pct")
    if pos in ("WR", "TE") and len(wk) >= 3:
        recent = sum(p for _, p in wk[-2:]) / 2
        before = sum(p for _, p in wk[:-2]) / max(len(wk) - 2, 1)
        if recent >= before + 15 and recent >= 60:
            out.append(f"routes up: {recent:.0f}% of dropbacks the last two games (was {before:.0f}%)")
        elif recent <= before - 20:
            out.append(f"routes down: {recent:.0f}% of dropbacks the last two games (was {before:.0f}%)")
    if pos in ("WR", "TE") and rp is not None and rp >= 80 and not any(o.startswith("routes up") for o in out):
        out.append(f"runs a route on {rp:.0f}% of dropbacks")
    if st.get("tprr") is not None and st["tprr"] >= (24 if pos == "WR" else 22 if pos == "TE" else 99):
        out.append(f"earns a target on {st['tprr']:.0f}% of routes")
    if st.get("yprr") is not None and st["yprr"] >= (2.3 if pos == "WR" else 2.0 if pos == "TE" else 99):
        out.append(f"{st['yprr']:.2f} yards per route run")
    if pos == "RB" and st.get("opp_share") is not None and st["opp_share"] >= 60:
        out.append(f"{st['opp_share']:.0f}% of his team's RB opportunities")
    return out
