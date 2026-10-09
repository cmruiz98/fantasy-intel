"""Vegas lines: each team's implied points for the week ahead.

Implied team total = over/under / 2 - own spread / 2. A team favored by 7 in a game
with a 45 total is expected to score 26, its opponent 19.

How it is used, measured on 2022-25 (fit on 2022-24, checked on 2025):
  * A player's weekly projection is scaled by (this week's implied total / his team's
    average implied total this season) ** elasticity. Relative to the team's own average,
    so a good offense is not credited twice (its players' projections already reflect it).
  * Elasticity: QB 0.5, RB 0.4, WR 0.4, TE 0.6 (best fit; 2025 error fell at every position).
  * Once Vegas is used, the old defense-vs-position matchup factor added nothing (it made
    2025 errors slightly worse), so it is only a fallback for games with no line yet.
  * Lines already price in part of a backup-QB downgrade (about 25% of the drop for WRs,
    50% for TEs, 60% for RBs in first games after a QB change), so the separate QB
    adjustment is trimmed by that share when a line is posted.
Lines come from ESPN's scoreboard (DraftKings, updated live) and nflverse as a fallback.
"""
import pandas as pd

from . import injuries

ELASTICITY = {"QB": 0.5, "RB": 0.4, "WR": 0.4, "TE": 0.6}
QB_OVERLAP = {"QB": 0.0, "RB": 0.6, "WR": 0.25, "TE": 0.5}
FACTOR_RANGE = (0.80, 1.20)
LEAGUE_AVG = 22.5   # typical implied team total
PRIOR_GAMES = 2     # a team's average implied total starts here and moves with its lines
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={week}&dates={season}"
ESPN_TEAM = {"WSH": "WAS", "LAR": "LA", "JAC": "JAX"}


def _implied(total, home_spread):
    """home_spread: points from the home team's view (negative = home favored)."""
    return total / 2 - home_spread / 2, total / 2 + home_spread / 2


def espn_lines(season: int, week: int) -> dict:
    data = injuries.espn_json(SCOREBOARD.format(week=week, season=season))
    out = {}
    for e in data.get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        teams = {c.get("homeAway"): ESPN_TEAM.get(c["team"]["abbreviation"], c["team"]["abbreviation"])
                 for c in comp.get("competitors", [])}
        odds = [o for o in (comp.get("odds") or []) if o.get("overUnder") is not None and o.get("spread") is not None]
        if not odds or "home" not in teams or "away" not in teams:
            continue
        o = min(odds, key=lambda x: (x.get("provider") or {}).get("priority", 99))
        total, hs = float(o["overUnder"]), float(o["spread"])
        h, a = _implied(total, hs)
        prov = (o.get("provider") or {}).get("name", "ESPN")
        out[teams["home"]] = {"implied": h, "total": total, "spread": hs, "opp": teams["away"], "source": prov}
        out[teams["away"]] = {"implied": a, "total": total, "spread": -hs, "opp": teams["home"], "source": prov}
    return out


def nflverse_lines(sched: pd.DataFrame, season: int) -> pd.DataFrame:
    """Every game's implied totals this season (nflverse spread_line: positive = home favored)."""
    s = sched[(sched.season == season) & (sched.game_type == "REG")].dropna(subset=["total_line", "spread_line"])
    rows = []
    for g in s.itertuples():
        h, a = _implied(g.total_line, -g.spread_line)
        rows.append((int(g.week), g.home_team, h, g.total_line, -g.spread_line, g.away_team))
        rows.append((int(g.week), g.away_team, a, g.total_line, g.spread_line, g.home_team))
    return pd.DataFrame(rows, columns=["week", "team", "implied", "total", "spread", "opp"])


def lines_for_week(sched: pd.DataFrame, season: int, plan_week: int) -> tuple[dict, dict, str]:
    """({team: line for plan week}, {team: average implied total this season}, status)."""
    nv = nflverse_lines(sched, season)
    status = ""
    try:
        live = espn_lines(season, plan_week)
        status = f"{len(live) // 2} games (ESPN/DraftKings)"
    except Exception as e:
        live = {}
        status = f"ESPN unavailable ({type(e).__name__}); "
    s = sched[(sched.season == season) & (sched.game_type == "REG") & (sched.week == plan_week)]
    played = set(s[s.result.notna()].home_team) | set(s[s.result.notna()].away_team)
    live = {t: ln for t, ln in live.items() if t not in played}  # Thursday's game is over: no line to use
    wk = nv[(nv.week == plan_week) & ~nv.team.isin(played)]
    for r in wk.itertuples():
        if r.team not in live:
            live[r.team] = {"implied": r.implied, "total": r.total, "spread": r.spread, "opp": r.opp, "source": "nflverse"}
    if not status.endswith("(ESPN/DraftKings)"):
        status += f"{len(wk) // 2} games (nflverse)"
    past = nv[nv.week < plan_week]
    agg = past.groupby("team").implied.agg(["sum", "count"])
    avg = {t: (r["sum"] + LEAGUE_AVG * PRIOR_GAMES) / (r["count"] + PRIOR_GAMES) for t, r in agg.iterrows()}
    for t in live:
        avg.setdefault(t, LEAGUE_AVG)
    for t, ln in live.items():
        ln["implied"] = round(ln["implied"], 1)
        ln["team_avg"] = round(avg[t], 1)
    return live, avg, status


def factor(position: str, line: dict | None) -> float | None:
    """Multiplier on a player's weekly projection, or None when there is no line."""
    if not line or position not in ELASTICITY:
        return None
    f = (line["implied"] / max(line["team_avg"], 10)) ** ELASTICITY[position]
    return float(min(max(f, FACTOR_RANGE[0]), FACTOR_RANGE[1]))
