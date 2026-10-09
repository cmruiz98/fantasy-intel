# Fantasy Intel

A fantasy football engine that refreshes itself all season and publishes a dashboard
you can open on your phone:

- **Every usage metric**: fantasy points, snap %, target share, air-yards share, WOPR,
  red-zone targets and share, end-zone targets, red-zone and inside-10 carries,
  touches, receptions, yards, TDs, and expected fantasy points (xFP) from workload.
- **Injury and availability watch** from nine sources, fastest first: play-by-play
  (who got hurt mid-game and whether he returned, within hours of the final whistle),
  snap-count collapses, Rotoworld/NBC player news (beat reporters, press conferences and
  practice notes, each citing the reporter), ESPN's injury desk (status, return date, news comment),
  Sleeper's injury feed, ESPN news headlines, your league's ESPN designations, the
  official injury and practice reports, and NFL roster moves (IR, PUP, suspensions).
  News is read for timelines ("2-4 weeks", "season-ending", "week-to-week") and turned
  into expected games missed. It also shows who stepped in for each injured starter.
- **Vegas lines**: each team's implied total for the week scales weekly projections
  (measured on 2022-25; it beat the old defense-matchup factor at every position).
- **Depth charts** from Ourlads and ESPN: who's next in line, who just moved up or down,
  and which backup is the real handcuff.
- **Advanced stats** from PlayerProfiler: routes run, route participation, targets and
  yards per route run, first-read share, separation.
- **Its own rankings**, built on three seasons of history plus this season, with a
  guardrail so a proven star isn't written off after one bad week.
- **Consensus comparison**: FantasyPros rest-of-season and weekly consensus (100+
  experts) plus ESPN projections, blended into one market rating. Players where the
  two disagree are flagged overvalued or undervalued.
- **Your league**: lineup start/sit, waiver targets with drop suggestions, buy-low
  and sell-high lists, and specific trade offers that help you but still look fair
  to the other manager.

It runs free on GitHub: every 2 hours all week, every 30 minutes during Sunday games,
and during Thursday, Sunday and Monday night games.

---

## One-time setup (about 10 minutes)

### 1. Create the repo
1. Sign in at github.com (a free account is fine).
2. Click **+ → New repository**. Name it `fantasy-intel`, choose **Public**, and click **Create repository**.
   (GitHub Pages is only free for public repos. The page URL isn't listed anywhere and
   is marked "don't index" for search engines, but anyone who has the link can open it.
   It shows player data and your league's team names, nothing else.)
3. On the new repo page click **uploading an existing file**, drag in **everything
   inside** the unzipped `fantasy-intel` folder (including the `.github` folder), and click
   **Commit changes**.
   - If the `.github` folder doesn't upload (some browsers hide it): click
     **Add file → Create new file**, type `.github/workflows/update.yml` as the name,
     paste in the contents of that file, and commit.

### 2. Get your two ESPN cookies (your league is private)
1. On a computer, log in at fantasy.espn.com and open your league.
2. Open developer tools: **F12** on Windows, **Cmd+Option+I** on a Mac.
   - Chrome/Edge: **Application** tab → **Cookies** → `https://fantasy.espn.com`
   - Safari: enable the Develop menu first (Settings → Advanced), then **Storage** tab → **Cookies**
   - Firefox: **Storage** tab → **Cookies**
3. Copy the values of **`espn_s2`** (a long string) and **`SWID`** (looks like `{XXXXXXXX-XXXX-...}`, keep the braces).

These act like your ESPN login for reading the league. Keep them private: they go in
GitHub Secrets, which are encrypted and never shown on the dashboard. They usually last
about a year; if the dashboard says ESPN refused access, repeat this step.

### 3. Add them as secrets
In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Name | Value |
|---|---|
| `ESPN_S2` | the espn_s2 value |
| `ESPN_SWID` | the SWID value, with braces |
| `ESPN_LEAGUE_ID` | `68383424` (optional, already the default) |
| `ESPN_TEAM_ID` | optional: only if the dashboard says it can't find your team; it will list the team numbers |
| `FIRECRAWL_API_KEY` | optional but recommended: your Firecrawl key (starts with `fc-`). Only used when a site blocks GitHub's servers |

**About Firecrawl.** Ourlads, Rotoworld and PlayerProfiler are all fetched directly first, which
is free. Some sites block cloud servers like GitHub's; with this key set, a blocked page is
fetched through Firecrawl instead (one credit per page). Usage is capped at 800 credits a
month by default (the free plan has 1,000), 40 per run, and 200 a month for PlayerProfiler;
set a `FIRECRAWL_MONTHLY_BUDGET` secret to change the monthly cap. The Sources card on the
Injuries tab shows how each page arrived and the month's credit count. Without the key,
everything still works whenever the sites answer directly, and the last good copy is used
when they don't.

### 4. Turn on the website
**Settings → Pages →** under **Build and deployment**, set **Source** to **GitHub Actions**.

### 5. Run it
**Actions** tab → if asked, click **I understand my workflows, go ahead and enable them** →
**Update fantasy intel** → **Run workflow**. It takes 3-5 minutes. When it finishes, your
dashboard is at:

`https://<your-github-username>.github.io/fantasy-intel/`

Bookmark it or add it to your phone's home screen. From then on it updates on its own.
Hit **Run workflow** any time you want a refresh right now (say, right after inactives
come out on Sunday).

---

## Using the dashboard

| Tab | What it's for |
|---|---|
| **Team** | Any team in the league (yours first): position strengths, projected lineup in fantasy order (QB, RB, RB, WR, WR, TE, FLEX, D/ST, K, then bench), injury watch, buy-low/sell-high, and for your team the lineup changes vs your ESPN lineup |
| **Waivers** | Best pickups for *your* roster, how much each improves your lineup, who to drop, why (rising snaps, target share, red-zone work, ESPN add trend) |
| **Trades** | Your needs and surplus, every team's position ranks and fit with you, and trade ideas that fix a need on both sides (lineup plus handcuff value, judged by our numbers for you and consensus for them), plus buy-low and sell-high lists |
| **Trade analyzer** | Build any trade yourself: pick two teams and any players on each side, and see what each team gains or loses in rest-of-season starting-lineup points (by our numbers and by consensus), plus both teams' projected lineups after the trade |
| **Value board** | Every over/undervalued player league-wide, plus stars on the guardrail list |
| **Rankings** | All players, filter by position, switch column sets (projection, usage, red zone, production, advanced routes, this week's game and Vegas total), free agents only; tap anyone for a full breakdown |
| **Injuries** | Everyone relevant with a status, how likely they play, and games expected missed; who stepped in; depth chart moves; QB changes; where every feed came from |
| **How it works** | The method in plain English |

## Tuning

Most knobs are near the top of `ffintel/model.py` and `ffintel/consensus.py`:

- `BASE_K`: how many "phantom games" history is worth. Higher = slower to react.
- `STAR_DEPTH`: how deep at each position counts as a proven star.
- `SEASON_WEIGHTS`: weight on each of the last three seasons.
- `PRESEASON_K` / `PRESEASON_FADE`: how much your league's draft board counts early in
  the season, and how fast it fades (default: ~5 games of evidence in week 1, gone by week 8).
- `ROLE_FULL` / `OPP_FULL`: the snap share and weekly touches+targets that count as a
  full starter's role. Players below it keep only that fraction of their value above
  replacement, which is what keeps no-role players out of the waiver list.
- `INJURY_TYPES` in injuries.py: typical games missed by injury (ACL, Achilles, Lisfranc,
  fractures, MCL, ...), used when a feed names the injury without a timeline.
- `BASE_GAMES`, `PENDING_P`, `REPORT_P` in injuries.py: games missed per status, chance to
  miss the next game while this week's report is pending, and once it's filed.
- `RB1_MISS_RATE` / `HANDCUFF_SHARE` in model.py: how often starting RBs miss games (16%) and
  how much of the starter's output the handcuff produces when he does (75%), both from 2023-25.
- `QB_ELASTICITY` / `QB_FACTOR_RANGE` in model.py: how hard a backup QB hits his receivers
  (0.55, measured from 2023-25 backup starts) and the floor/ceiling on that adjustment.
- `ELASTICITY` / `QB_OVERLAP` / `FACTOR_RANGE` in vegas.py: how hard the Vegas team total
  moves weekly projections (QB 0.5, RB 0.4, WR 0.4, TE 0.6, measured on 2022-25), how much
  of a backup-QB downgrade the line already prices in, and the ±20% cap.
- `PER_RUN`, `REFRESH_DAYS`, `PP_FIRECRAWL_MONTHLY` in advanced.py: how many PlayerProfiler
  pages to refresh per run, how often, and the Firecrawl cap for them.
- `RUN_CAP`, `LOW_PRIORITY_SHARE` in web.py: Firecrawl credits per run, and the share of the
  month's budget after which only the most important pages use Firecrawl.
- `WEIGHTS` in consensus.py: how much each outside source counts.

## Running on your own computer (optional)

```
pip install -r requirements.txt
export ESPN_S2="..."  ESPN_SWID="{...}"
python -m ffintel.run
open site/index.html
```

`FF_MOCK_LEAGUE=1 python -m ffintel.run` builds a demo with a made-up league, handy
for testing without ESPN.

## Data sources
- nflverse (play-by-play, weekly player stats, snap counts, injury reports, rosters, schedules
  and betting lines, ESPN depth chart snapshots)
- ESPN scoreboard (DraftKings lines), Ourlads depth charts, Rotoworld/NBC player news,
  PlayerProfiler advanced stats (fetched directly, Firecrawl as a fallback)
- FantasyPros expert consensus via DynastyProcess
- ESPN Fantasy API (your league, injury designations, ownership trends, projections)
- ESPN injury desk and NFL news feeds, Sleeper player feed (injury status and notes)

Kickers and D/ST aren't rated; stream those as usual.
