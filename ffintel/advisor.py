"""Waiver and trade recommendations for your ESPN team."""
import itertools

import numpy as np
import pandas as pd

LINEUP_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "OP"]
ELIGIBLE = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
            "FLEX": {"RB", "WR", "TE"}, "OP": {"QB", "RB", "WR", "TE"}}


def best_lineup(rows: list[dict], lineup: dict, col: str) -> tuple[float, set]:
    """Greedy optimal lineup (exact for standard ESPN slot structures)."""
    pool = sorted(rows, key=lambda r: -(r.get(col) or 0))
    used, total = set(), 0.0
    for slot in LINEUP_ORDER:
        for _ in range(lineup.get(slot, 0)):
            for r in pool:
                if r["player_id"] not in used and r["position"] in ELIGIBLE[slot]:
                    used.add(r["player_id"])
                    total += r.get(col) or 0
                    break
    return total, used


class Advisor:
    def __init__(self, df: pd.DataFrame, league, weeks_left: int):
        self.league = league
        self.weeks_left = max(weeks_left, 1)
        df = df.copy()
        df["ros_ppw"] = df.ros_points / self.weeks_left
        df["mkt_ppw"] = df.market_ros_points.fillna(df.ros_points) / self.weeks_left
        self.df = df.set_index("player_id", drop=False)
        self.owner = {}
        for tid, entries in league.rosters.items():
            for e in entries:
                if e["player_id"]:
                    self.owner[e["player_id"]] = tid
        self.df["owner"] = self.df.player_id.map(self.owner)

    def roster_rows(self, tid) -> list[dict]:
        ids = [e["player_id"] for e in self.league.rosters.get(tid, []) if e["player_id"] in self.df.index]
        return self.df.loc[ids].to_dict("records")

    def lineup_value(self, rows, col="ros_ppw"):
        return best_lineup(rows, self.league.lineup, col)[0]

    # ------------------------------------------------------------------ my team
    def my_team(self) -> dict:
        tid = self.league.my_team_id
        rows = self.roster_rows(tid)
        _, ros_starters = best_lineup(rows, self.league.lineup, "ros_ppw")
        _, wk_starters = best_lineup(rows, self.league.lineup, "week_proj")
        slot = {e["player_id"]: e["slot"] for e in self.league.rosters.get(tid, [])}
        for r in rows:
            r["espn_slot"] = slot.get(r["player_id"], "")
            r["start_this_week"] = r["player_id"] in wk_starters
            r["core_starter"] = r["player_id"] in ros_starters
            # lineup advice: ESPN slot vs our optimal
            benched = r["espn_slot"] in ("BN", "IR")
            if r["start_this_week"] and benched:
                r["lineup_note"] = "Start"
            elif not r["start_this_week"] and not benched and r["espn_slot"]:
                r["lineup_note"] = "Bench"
            else:
                r["lineup_note"] = ""
        strength = self.team_strengths()
        return {"team_id": tid, "players": rows, "strength": strength,
                "needs": self.needs(tid, strength)}

    def team_strengths(self) -> list[dict]:
        out = []
        for tid, t in self.league.teams.items():
            rows = self.roster_rows(tid)
            v, starters = best_lineup(rows, self.league.lineup, "ros_ppw")
            pos = {}
            for r in rows:
                if r["player_id"] in starters:
                    pos[r["position"]] = pos.get(r["position"], 0) + r["ros_ppw"]
            out.append({"team_id": tid, "name": t["name"], "record": t.get("record", ""),
                        "lineup_ppw": round(v, 1), **{f"{p}_ppw": round(pos.get(p, 0), 1) for p in ("QB", "RB", "WR", "TE")}})
        out.sort(key=lambda x: -x["lineup_ppw"])
        for i, o in enumerate(out):
            o["power_rank"] = i + 1
        return out

    def needs(self, tid, strength) -> list[dict]:
        s = pd.DataFrame(strength)
        me = s[s.team_id == tid]
        if me.empty:
            return []
        me = me.iloc[0]
        out = []
        for p in ("QB", "RB", "WR", "TE"):
            col = f"{p}_ppw"
            rank = int((s[col] > me[col]).sum() + 1)
            out.append({"position": p, "my_ppw": me[col], "league_avg": round(s[col].mean(), 1), "rank": rank})
        out.sort(key=lambda x: -x["rank"])
        return out

    # ------------------------------------------------------------------ waivers
    def waivers(self, limit=25) -> list[dict]:
        tid = self.league.my_team_id
        mine = self.roster_rows(tid)
        base = self.lineup_value(mine)
        _, starters = best_lineup(mine, self.league.lineup, "ros_ppw")
        droppable = sorted([r for r in mine if r["player_id"] not in starters], key=lambda r: r["ros_value"])
        drop = droppable[0] if droppable else None
        fa = self.df[self.df.owner.isna() & (self.df.ros_games > 0)]
        # A pickup needs a reason to score: real recent usage, a role that is growing,
        # or a job he just inherited from an injured starter.
        recent_work = (fa.touches.fillna(0) + fa.targets.fillna(0)) / fa.all_games.clip(lower=1)
        has_role = (fa.role_share.fillna(0) >= 0.3) | (recent_work >= 4)
        inherits = fa.fill_in_for.notna() | (fa.role_change == 1)
        unseen = fa.all_games.fillna(0) == 0  # hasn't played yet: judged on history alone
        fa = fa[has_role | inherits | (unseen & fa.inj_status.isna())]
        fa = fa.sort_values("ros_value", ascending=False).head(120)
        out = []
        for r in fa.to_dict("records"):
            new = [x for x in mine if not drop or x["player_id"] != drop["player_id"]] + [r]
            gain_week = self.lineup_value(new) - base
            depth = max(0.0, r["ros_value"] - (drop["ros_value"] if drop else 0))
            score = gain_week * self.weeks_left + 0.35 * depth
            own = self.league.ownership.get(r["player_id"], (None, None))
            reasons = []
            if r.get("role_share"):
                reasons.append(f"{r['role_share']:.0%} of snaps")
            if gain_week > 0.2:
                reasons.append(f"+{gain_week:.1f} pts/wk to your lineup")
            if r.get("l2_snap") and r.get("snap_pct") and r["l2_snap"] - r["snap_pct"] >= 0.08:
                reasons.append("snap share rising")
            if r.get("role_change") == 1:
                reasons.append("bigger role than last year")
            if (r.get("l3_tshare") or 0) >= 0.2:
                reasons.append(f"{r['l3_tshare']:.0%} target share last 3")
            if (r.get("rz_carries") or 0) + (r.get("rz_targets") or 0) >= 4:
                reasons.append("red-zone work")
            if own[1] and own[1] >= 3:
                reasons.append(f"trending +{own[1]:.0f}% on ESPN")
            if r.get("verdict") == "Undervalued":
                reasons.append("we rate him above consensus")
            if isinstance(r.get("fill_in_for"), str):
                reasons.insert(0, f"took over for injured {r['fill_in_for']}")
            out.append({**r, "gain_week": round(gain_week, 2), "score": round(score, 1),
                        "drop": drop["name"] if drop else "", "pct_owned": own[0], "pct_change": own[1],
                        "waiver_status": self.league.waiver_status.get(r["player_id"], ""),
                        "why": "; ".join(reasons)})
        out.sort(key=lambda x: -x["score"])
        return out[:limit]

    # ------------------------------------------------------------------ trades
    def trade_lists(self) -> dict:
        tid = self.league.my_team_id
        d = self.df
        buy = d[(d.owner.notna()) & (d.owner != tid) & (d.verdict == "Undervalued")].sort_values("value_gap", ascending=False)
        sell = d[(d.owner == tid) & (d.verdict == "Overvalued")].sort_values("value_gap")
        names = {k: v["name"] for k, v in self.league.teams.items()}
        buy = buy.assign(owner_name=buy.owner.map(names))
        return {"buy_low": buy.head(20).to_dict("records"), "sell_high": sell.to_dict("records")}

    def trade_ideas(self, limit=15) -> list[dict]:
        tid = self.league.my_team_id
        mine = self.roster_rows(tid)
        my_base = self.lineup_value(mine)
        ideas = []
        give_pool = [r for r in mine if r["ros_games"] > 0]
        for other in self.league.teams:
            if other == tid:
                continue
            theirs = self.roster_rows(other)
            their_base_mkt = self.lineup_value(theirs, "mkt_ppw")
            targets = [r for r in theirs if r["ros_value"] > 0]
            for get in targets:
                for n_give in (1, 2):
                    for give in itertools.combinations(give_pool, n_give):
                        give_ids = {g["player_id"] for g in give}
                        give_mkt = sorted((g["mkt_ppw"] for g in give), reverse=True)
                        # a second player is worth less to them (roster spot, depth)
                        offered = give_mkt[0] + (0.5 * give_mkt[1] if n_give == 2 else 0)
                        balance = offered / max(get["mkt_ppw"], 0.1)
                        if balance < 0.92:
                            continue  # they'd reject: market says they're losing value
                        if balance > 1.35:
                            continue  # we'd be overpaying by market standards
                        if n_give == 2 and give_mkt[1] > 0.9 * get["mkt_ppw"]:
                            continue  # not a consolidation
                        my_new = [r for r in mine if r["player_id"] not in give_ids] + [get]
                        my_gain = self.lineup_value(my_new) - my_base
                        if my_gain < 0.4:
                            continue
                        their_new = [r for r in theirs if r["player_id"] != get["player_id"]] + list(give)
                        their_gain_mkt = self.lineup_value(their_new, "mkt_ppw") - their_base_mkt
                        if their_gain_mkt < -1.0:
                            continue  # hurts their lineup too much to be accepted
                        ideas.append({
                            "team": self.league.teams[other]["name"],
                            "give": [g["name"] for g in give], "get": get["name"],
                            "give_pos": [g["position"] for g in give], "get_pos": get["position"],
                            "my_gain_week": round(my_gain, 2), "my_gain_ros": round(my_gain * self.weeks_left, 1),
                            "their_gain_week_mkt": round(their_gain_mkt, 2),
                            "market_balance": round(offered / max(get["mkt_ppw"], 0.1), 2),
                            "get_verdict": get.get("verdict", ""),
                            "give_verdicts": [g.get("verdict", "") for g in give],
                        })
        # best for us, with a small penalty for overpaying relative to market
        ideas.sort(key=lambda x: -(x["my_gain_ros"] - 20 * max(0, x["market_balance"] - 1)))
        # keep variety: one idea per target player
        seen, out = {}, []
        for i in ideas:
            if seen.get(i["get"], 0) >= 1:
                continue
            seen[i["get"]] = seen.get(i["get"], 0) + 1
            out.append(i)
            if len(out) >= limit:
                break
        return out
