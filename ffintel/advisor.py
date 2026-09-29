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

    def team_value(self, rows, col="ros_ppw"):
        """Starting lineup points per week plus handcuff insurance."""
        from .model import handcuff_bonus
        return self.lineup_value(rows, col) + handcuff_bonus(rows, self.league.lineup, col, self.weeks_left)[0]

    def pos_strength(self, rows, col="ros_ppw"):
        """Points per week each position contributes to the best lineup (FLEX credited to its player's position)."""
        _, used = best_lineup(rows, self.league.lineup, col)
        out = {p: 0.0 for p in ("QB", "RB", "WR", "TE")}
        for r in rows:
            if r["player_id"] in used and r["position"] in out:
                out[r["position"]] += r.get(col) or 0
        return out

    def league_ranks(self, strengths: dict) -> dict:
        """strengths: team_id -> {pos: ppw}. Returns team_id -> {pos: rank} (1 = best)."""
        ranks = {t: {} for t in strengths}
        for pos in ("QB", "RB", "WR", "TE"):
            order = sorted(strengths, key=lambda t: -strengths[t][pos])
            for i, t in enumerate(order):
                ranks[t][pos] = i + 1
        return ranks

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
    def available_now(self, rows):
        """Players who can actually help you in the coming week."""
        return [r for r in rows if (r.get("exp_missed") or 0) < 1 and (r.get("play_prob") or 0) >= 0.5]

    def waivers(self, limit=25, stashes=False) -> list[dict]:
        tid = self.league.my_team_id
        mine = self.roster_rows(tid)
        base = self.team_value(mine)
        _, starters = best_lineup(mine, self.league.lineup, "ros_ppw")
        # the drop is whoever costs your TEAM least to lose, so a handcuff to your own starter is protected
        bench = [r for r in mine if r["player_id"] not in starters]
        cost = {r["player_id"]: base - self.team_value([x for x in mine if x["player_id"] != r["player_id"]]) for r in bench}
        droppable = sorted(bench, key=lambda r: (cost[r["player_id"]], r["ros_value"]))
        drop = droppable[0] if droppable else None
        fa = self.df[self.df.owner.isna() & (self.df.ros_games > 0)]
        # A pickup needs a reason to score: real recent usage, a role that is growing,
        # or a job he just inherited from an injured starter.
        recent_work = (fa.touches.fillna(0) + fa.targets.fillna(0)) / fa.all_games.clip(lower=1)
        has_role = (fa.role_share.fillna(0) >= 0.3) | (recent_work >= 4)
        inherits = fa.fill_in_for.notna() | (fa.role_change == 1)
        unseen = fa.all_games.fillna(0) == 0  # hasn't played yet: judged on history alone
        fa = fa[has_role | inherits | (unseen & fa.inj_status.isna())]
        # Players who won't play for a while are stashes, not this week's pickups.
        hurt = (fa.exp_missed.fillna(0) >= 1) | (fa.play_prob.fillna(1) < 0.5)
        fa = fa[hurt] if stashes else fa[~hurt]
        fa = fa.sort_values("ros_value", ascending=False).head(60 if stashes else 120)
        out = []
        for r in fa.to_dict("records"):
            new = [x for x in mine if not drop or x["player_id"] != drop["player_id"]] + [r]
            gain_week = self.team_value(new) - base
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
            if r.get("hc_of") and r.get("hc_of") in {x["player_id"] for x in mine}:
                reasons.insert(0, f"handcuff to your {r.get('hc_of_name')}")
            elif isinstance(r.get("hc_of_name"), str):
                reasons.append(f"backup to {r['hc_of_name']}")
            if stashes:
                reasons.append(f"out ~{r['exp_missed']:.0f} more game{'s' if (r['exp_missed'] or 0) >= 1.5 else ''}")
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
        """Trades that fix a need on BOTH sides.

        Every candidate (1-for-1, 2-for-1, 1-for-2) is scored by what it does to each
        team's best lineup plus handcuff insurance, not by player values in isolation:
          - for you, with this app's projections;
          - for them, with consensus projections (how they will see it) AND ours.
        An idea is kept only if it improves your team and does not look like a loss to
        them in their own lineup. Ideas that fill their weak spot with your surplus (and
        vice versa) rank highest, and each comes with the reason in plain words.
        """
        me = self.league.my_team_id
        mine = self.roster_rows(me)
        strengths = {t: self.pos_strength(self.roster_rows(t)) for t in self.league.teams}
        ranks = self.league_ranks(strengths)
        n = len(self.league.teams)
        my_base = self.team_value(mine)
        _, my_start = best_lineup(mine, self.league.lineup, "ros_ppw")
        give_pool = [r for r in mine if r["ros_games"] > 0 and (r.get("ros_value") or -99) > -60]
        ideas = []
        for other in self.league.teams:
            if other == me:
                continue
            theirs = self.roster_rows(other)
            t_base_ours, t_base_mkt = self.team_value(theirs), self.team_value(theirs, "mkt_ppw")
            targets = [r for r in theirs if r["ros_games"] > 0 and (r.get("ros_value") or -99) > -40]
            packages = [((g,), (t,)) for t in targets for g in give_pool]  # 1-for-1 first
            packages += [(g2, (t,)) for t in targets for g2 in itertools.combinations(give_pool, 2)]
            packages += [((g,), t2) for g in give_pool for t2 in itertools.combinations(targets, 2)]
            single = {}  # best 1-for-1 results, to reject packages with pointless extras
            for give, get in packages:
                gi, ge = {x["player_id"] for x in give}, {x["player_id"] for x in get}
                my_new = [r for r in mine if r["player_id"] not in gi] + list(get)
                my_gain = self.team_value(my_new) - my_base
                if my_gain < 0.3:
                    continue
                their_new = [r for r in theirs if r["player_id"] not in ge] + list(give)
                t_mkt = self.team_value(their_new, "mkt_ppw") - t_base_mkt
                if len(give) == 1 and len(get) == 1:
                    single[(give[0]["player_id"], get[0]["player_id"])] = (my_gain, t_mkt)
                if t_mkt < -0.15:
                    continue  # by consensus it weakens their lineup: they'd say no
                if len(get) == 2:
                    # both players must matter to you; otherwise the second is just filler
                    best1 = max((single.get((give[0]["player_id"], x["player_id"]), (-9, -9))[0] for x in get), default=-9)
                    if my_gain < best1 + 0.3:
                        continue
                if len(give) == 2:
                    # don't throw in a second player they didn't need to say yes
                    if any(single.get((x["player_id"], get[0]["player_id"]), (-9, -9))[1] >= -0.15 for x in give):
                        continue
                t_ours = self.team_value(their_new) - t_base_ours
                ideas.append({"other": other, "give": give, "get": get, "my_gain": my_gain,
                              "t_mkt": t_mkt, "t_ours": t_ours, "my_new": my_new, "their_new": their_new})
        # prefer trades both sides like; avoid near-duplicates
        for i in ideas:
            i["score"] = i["my_gain"] + 0.4 * max(i["t_mkt"], 0) + 0.2 * max(i["t_ours"], 0)
        ideas.sort(key=lambda i: -i["score"])
        # re-rank the strongest candidates by need fit: a trade that fixes a weak spot on
        # BOTH sides is the kind that actually gets accepted
        shortlist = []
        for i in ideas[:150]:
            e = self._explain(i, strengths, ranks, n)
            bonus = 0.6 * e["fills_their_need"] + 0.3 * e["fills_my_need"]
            shortlist.append((i["score"] + bonus, i, e))
        shortlist.sort(key=lambda x: -x[0])
        out, seen_player, per_give, per_team = [], {}, {}, {}
        for _, i, e in shortlist:
            gets = [x["player_id"] for x in i["get"]]
            gk = tuple(sorted(x["player_id"] for x in i["give"]))
            if any(seen_player.get(g, 0) >= 1 for g in gets) or per_give.get(gk, 0) >= 2 \
                    or per_team.get(i["other"], 0) >= 3:
                continue  # variety: each target once, few repeats of the same offer or partner
            for g in gets:
                seen_player[g] = seen_player.get(g, 0) + 1
            per_give[gk] = per_give.get(gk, 0) + 1
            per_team[i["other"]] = per_team.get(i["other"], 0) + 1
            out.append(e)
            if len(out) >= limit:
                break
        return out

    def _explain(self, i, strengths, ranks, n):
        me, other = self.league.my_team_id, i["other"]
        after_me, after_them = self.pos_strength(i["my_new"]), self.pos_strength(i["their_new"])
        # league ranks after the trade (other teams unchanged)
        def rank_after(team, after):
            s2 = dict(strengths)
            s2[team] = after
            if team == me:
                s2[other] = after_them
            else:
                s2[me] = after_me
            return self.league_ranks(s2)[team]
        r_me, r_them = rank_after(me, after_me), rank_after(other, after_them)
        def moves(before, after):
            return [f"{p} {ord_(before[p])} → {ord_(after[p])}" for p in ("QB", "RB", "WR", "TE") if before[p] != after[p]]
        me_moves, them_moves = moves(ranks[me], r_me), moves(ranks[other], r_them)
        # the story: which need each side fills
        gain_pos = [p for p in ("QB", "RB", "WR", "TE") if r_me[p] < ranks[me][p]]
        their_gain_pos = [p for p in ("QB", "RB", "WR", "TE") if r_them[p] < ranks[other][p]]
        fills_their_need = any(ranks[other][p] > n * 2 / 3 for p in their_gain_pos)
        fills_my_need = any(ranks[me][p] > n * 2 / 3 for p in gain_pos)
        parts = []
        if gain_pos:
            parts.append(f"You upgrade {', '.join(gain_pos)} ({'; '.join(m for m in me_moves if m.split()[0] in gain_pos)})")
        if their_gain_pos:
            parts.append(f"they fill a need at {', '.join(their_gain_pos)} ({'; '.join(m for m in them_moves if m.split()[0] in their_gain_pos)})")
        hc = [x for x in i["get"] if x.get("hc_of") in {r["player_id"] for r in i["my_new"]}]
        if hc:
            parts.append(f"{hc[0]['name']} is the handcuff to your {hc[0]['hc_of_name']}")
        if len(i["give"]) == 2:
            parts.append("you consolidate two pieces into one, so you'll have a roster spot to fill")
        elif len(i["get"]) == 2:
            parts.append("you take on an extra player, so you'll need to drop someone")
        teams = self.league.teams
        return {
            "team": teams[other]["name"], "team_id": other,
            "give": [x["name"] for x in i["give"]], "give_ids": [x["player_id"] for x in i["give"]],
            "give_pos": [x["position"] for x in i["give"]],
            "get": [x["name"] for x in i["get"]], "get_ids": [x["player_id"] for x in i["get"]],
            "get_pos": [x["position"] for x in i["get"]],
            "my_gain_week": round(i["my_gain"], 2), "my_gain_ros": round(i["my_gain"] * self.weeks_left, 1),
            "their_gain_week_mkt": round(i["t_mkt"], 2), "their_gain_week": round(i["t_ours"], 2),
            "their_gain_ros_mkt": round(i["t_mkt"] * self.weeks_left, 1),
            "why": "; ".join(parts) + "." if parts else "",
            "my_moves": me_moves, "their_moves": them_moves,
            "get_verdicts": [x.get("verdict", "") for x in i["get"]],
            "fills_their_need": fills_their_need, "fills_my_need": fills_my_need,
        }

    def partners(self) -> list[dict]:
        """Each team's needs and surpluses, and how well they line up with yours."""
        me = self.league.my_team_id
        strengths = {t: self.pos_strength(self.roster_rows(t)) for t in self.league.teams}
        ranks = self.league_ranks(strengths)
        n = len(self.league.teams)
        def profile(t):
            rows = self.roster_rows(t)
            _, used = best_lineup(rows, self.league.lineup, "ros_ppw")
            needs = [p for p in ("QB", "RB", "WR", "TE") if ranks[t][p] > n * 2 / 3]
            # surplus: bench players who would start on the other team
            bench = [r for r in rows if r["player_id"] not in used and (r.get("ros_games") or 0) > 0]
            return rows, used, needs, bench
        m_rows, m_used, m_needs, m_bench = profile(me)
        my_floor = {p: min([r["ros_ppw"] for r in m_rows if r["player_id"] in m_used and r["position"] == p], default=0)
                    for p in ("QB", "RB", "WR", "TE")}
        out = []
        for t in self.league.teams:
            if t == me:
                continue
            rows, used, needs, bench = profile(t)
            floor = {p: min([r["ros_ppw"] for r in rows if r["player_id"] in used and r["position"] == p], default=0)
                     for p in ("QB", "RB", "WR", "TE")}
            they_have = sorted({r["position"] for r in bench if r["ros_ppw"] > my_floor.get(r["position"], 0) + 0.5})
            you_have = sorted({r["position"] for r in m_bench if r["ros_ppw"] > floor.get(r["position"], 0) + 0.5})
            match_mine = [p for p in m_needs if p in they_have]
            match_theirs = [p for p in needs if p in you_have]
            out.append({"team_id": t, "team": self.league.teams[t]["name"], "needs": needs,
                        "surplus": they_have, "you_can_offer": you_have,
                        "fills_your_need": match_mine, "you_fill_their_need": match_theirs,
                        "fit": len(match_mine) + len(match_theirs) + 0.5 * bool(match_mine and match_theirs),
                        "ranks": ranks[t]})
        out.sort(key=lambda x: -x["fit"])
        # your surplus: bench players who would start for at least a third of the league
        floors = {t: {p: min([r["ros_ppw"] for r in self.roster_rows(t) if r["player_id"] in
                              best_lineup(self.roster_rows(t), self.league.lineup, "ros_ppw")[1] and r["position"] == p], default=0)
                      for p in ("QB", "RB", "WR", "TE")} for t in self.league.teams if t != me}
        my_surplus = sorted({r["position"] for r in m_bench
                             if sum(r["ros_ppw"] > f[r["position"]] for f in floors.values()) >= len(floors) / 3})
        return {"mine": {"needs": m_needs, "ranks": ranks[me], "surplus": my_surplus}, "teams": out}


def ord_(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
