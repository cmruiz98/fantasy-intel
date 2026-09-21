"""Downloads the public data feeds, with a small on-disk cache.

Current-season files are re-downloaded every run (they change daily during the
season). Past seasons are downloaded once and reused.
"""
import io
import time

import pandas as pd
import requests

from . import config

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
DYNASTYPROCESS = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "fantasy-intel/1.0 (personal fantasy football tool)"


def _get(url: str, retries: int = 3) -> bytes:
    last = None
    for i in range(retries):
        try:
            r = SESSION.get(url, timeout=120)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            r.raise_for_status()
            return r.content
        except FileNotFoundError:
            raise
        except Exception as e:  # network hiccup: back off and retry
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Could not download {url}: {last}")


def _cached(name: str, url: str, fresh: bool) -> bytes:
    config.CACHE.mkdir(parents=True, exist_ok=True)
    path = config.CACHE / name
    max_age = 60 * 30 if fresh else 60 * 60 * 24 * 30
    if path.exists() and time.time() - path.stat().st_mtime < max_age:
        return path.read_bytes()
    try:
        data = _get(url)
    except FileNotFoundError:
        raise
    except Exception:
        if path.exists():  # stale beats nothing
            return path.read_bytes()
        raise
    path.write_bytes(data)
    return data


def _csv(name, url, fresh):
    return pd.read_csv(io.BytesIO(_cached(name, url, fresh)), low_memory=False)


def _parquet(name, url, fresh):
    return pd.read_parquet(io.BytesIO(_cached(name, url, fresh)))


def _optional(fn, *a):
    try:
        return fn(*a)
    except FileNotFoundError:
        return pd.DataFrame()


def weekly_stats(season: int) -> pd.DataFrame:
    fresh = season == config.SEASON
    return _optional(_csv, f"stats_{season}.csv",
                     f"{NFLVERSE}/stats_player/stats_player_week_{season}.csv", fresh)


def snap_counts(season: int) -> pd.DataFrame:
    fresh = season == config.SEASON
    return _optional(_csv, f"snaps_{season}.csv",
                     f"{NFLVERSE}/snap_counts/snap_counts_{season}.csv", fresh)


def pbp(season: int) -> pd.DataFrame:
    fresh = season == config.SEASON
    cols = ["season", "week", "season_type", "posteam", "play_type", "receiver_player_id",
            "rusher_player_id", "passer_player_id", "yardline_100", "air_yards", "complete_pass",
            "receiving_yards", "rushing_yards", "pass_touchdown", "rush_touchdown",
            "two_point_attempt", "qb_scramble", "td_player_id", "game_id", "play_id", "game_date",
            "qtr", "time", "desc"]
    df = _optional(_parquet, f"pbp_{season}.parquet",
                   f"{NFLVERSE}/pbp/play_by_play_{season}.parquet", fresh)
    return df[[c for c in cols if c in df.columns]] if len(df) else df


def injuries(season: int) -> pd.DataFrame:
    return _optional(_csv, f"injuries_{season}.csv",
                     f"{NFLVERSE}/injuries/injuries_{season}.csv", True)


def players() -> pd.DataFrame:
    return _csv("players.csv", f"{NFLVERSE}/players/players.csv", True)


def schedule() -> pd.DataFrame:
    return _csv("games.csv", f"{NFLVERSE}/schedules/games.csv", True)


def player_ids() -> pd.DataFrame:
    return _csv("playerids.csv", f"{DYNASTYPROCESS}/db_playerids.csv", True)


def fantasypros_ecr() -> pd.DataFrame:
    """FantasyPros expert consensus (itself an average of 100+ experts across sites)."""
    return _csv("fpecr.csv", f"{DYNASTYPROCESS}/db_fpecr_latest.csv", True)
