# Fantasy Intel

A fantasy football engine that refreshes itself all season and publishes a dashboard
you can open on your phone:

- **Every usage metric**: fantasy points, snap %, target share, air-yards share, WOPR,
  red-zone targets and share, end-zone targets, red-zone and inside-10 carries,
  touches, receptions, yards, TDs, and expected fantasy points (xFP) from workload.
- **Injury and availability watch** from eight sources, fastest first: play-by-play
  (who got hurt mid-game and whether he returned, within hours of the final whistle),
  snap-count collapses, ESPN's injury desk (status, return date, news comment),
  Sleeper's injury feed, ESPN news headlines, your league's ESPN designations, the
  official injury and practice reports, and NFL roster moves (IR, PUP, suspensions).
  News is read for timelines ("2-4 weeks", "season-ending", "week-to-week") and turned
  into expected games missed. It also shows who stepped in for each injured starter.
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
| **My team** | Power rank, weakest positions, lineup changes for the coming week, full roster with our rank vs consensus |
| **Waivers** | Best pickups for *your* roster, how much each improves your lineup, who to drop, why (rising snaps, target share, red-zone work, ESPN add trend) |
| **Trades** | Concrete offers, plus buy-low targets on other rosters and sell-high candidates on yours |
| **Value board** | Every over/undervalued player league-wide, plus stars on the guardrail list |
| **Rankings** | All players, filter by position, switch column sets (projection, usage, red zone, production), free agents only; tap anyone for a full breakdown |
| **Injuries** | Everyone relevant with a status, how likely they play, and games expected missed |
| **How it works** | The method in plain English |

## Tuning

Most knobs are near the top of `ffintel/model.py` and `ffintel/consensus.py`:

- `BASE_K`: how many "phantom games" history is worth. Higher = slower to react.
- `STAR_DEPTH`: how deep at each position counts as a proven star.
- `SEASON_WEIGHTS`: weight on each of the last three seasons.
- `BASE_GAMES` in injuries.py: expected games missed for each injury status.
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
- nflverse (play-by-play, weekly player stats, snap counts, injury reports, rosters, schedules)
- FantasyPros expert consensus via DynastyProcess
- ESPN Fantasy API (your league, injury designations, ownership trends, projections)
- ESPN injury desk and NFL news feeds, Sleeper player feed (injury status and notes)

Kickers and D/ST aren't rated; stream those as usual.
