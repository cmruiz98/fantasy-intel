"""Settings, read from environment variables (GitHub Secrets in the cloud)."""
import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("FF_CACHE_DIR", ROOT / "data_cache"))
SITE = Path(os.environ.get("FF_SITE_DIR", ROOT / "site"))


def current_season() -> int:
    today = dt.date.today()
    # NFL season "belongs" to the year it kicks off; Jan/Feb games are last season.
    return today.year if today.month >= 3 else today.year - 1


SEASON = int(os.environ.get("FF_SEASON") or current_season())
HISTORY_SEASONS = [SEASON - 3, SEASON - 2, SEASON - 1]

# ESPN league
LEAGUE_ID = os.environ.get("ESPN_LEAGUE_ID") or "68383424"
ESPN_S2 = os.environ.get("ESPN_S2", "").strip()
SWID = os.environ.get("ESPN_SWID", "").strip()
MY_TEAM_ID = os.environ.get("ESPN_TEAM_ID", "").strip()  # optional override
MOCK_LEAGUE = os.environ.get("FF_MOCK_LEAGUE", "") == "1"  # offline testing

# Defaults used if ESPN settings can't be read
DEFAULT_TEAMS = 12
DEFAULT_REC_PTS = 0.5
DEFAULT_LINEUP = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1}
LAST_FANTASY_WEEK = int(os.environ.get("FF_LAST_WEEK", "17"))

POSITIONS = ["QB", "RB", "WR", "TE"]
