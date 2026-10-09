"""Downloads the public data feeds, with a small on-disk cache.

Current-season files are re-downloaded every run (they change daily during the
season). Past seasons are downloaded once and reused.

Data providers rename and re-compress files without warning (in October 2026
nflverse replaced schedules/games.csv with games.csv.gz and games.parquet, which
stopped every run). So each feed lists several places it might live, in order,
and if none can be reached the last good copy saved from an earlier run is used.
"""
import gzip
import io
import time

import pandas as pd
import requests

from . import config

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
DYNASTYPROCESS = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"
NFLDATA = "https://raw.githubusercontent.com/nflverse/nfldata/master/data"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "fantasy-intel/1.0 (personal fantasy football tool)"

STATUS: dict = {}  # feed name -> which source was used, shown on the dashboard if anything fell back


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


def _read(data: bytes, url: str) -> pd.DataFrame:
    if url.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(data))
    if url.endswith(".gz"):
        data = gzip.decompress(data)
    return pd.read_csv(io.BytesIO(data), low_memory=False)


def _fetch(name: str, urls: list[str], fresh: bool, required: bool = True) -> pd.DataFrame:
    """Try each URL in turn; fall back to the last good saved copy; never crash on a rename."""
    config.CACHE.mkdir(parents=True, exist_ok=True)
    path = config.CACHE / f"{name}.parquet"
    max_age = 60 * 30 if fresh else 60 * 60 * 24 * 30
    if path.exists() and time.time() - path.stat().st_mtime < max_age:
        return pd.read_parquet(path)
    errors = []
    for url in urls:
        try:
            df = _read(_get(url), url)
            if df.empty:
                raise ValueError("empty file")
            df.to_parquet(path, index=False)
            STATUS[name] = "ok" if url == urls[0] else f"ok (from {url.rsplit('/', 1)[-1]})"
            return df
        except Exception as e:
            errors.append(f"{url.rsplit('/', 1)[-1]}: {type(e).__name__}")
    if path.exists():  # stale beats nothing
        STATUS[name] = "using last saved copy (" + "; ".join(errors) + ")"
        print(f"WARNING {name}: all sources failed, using last saved copy. {errors}")
        return pd.read_parquet(path)
    if required:
        raise RuntimeError(f"{name}: no source could be read ({'; '.join(errors)})")
    STATUS[name] = "unavailable"
    return pd.DataFrame()


def _variants(base: str, order=(".csv", ".csv.gz", ".parquet")) -> list[str]:
    """Same file in every format nflverse publishes."""
    return [base + ext for ext in order]


def weekly_stats(season: int) -> pd.DataFrame:
    return _fetch(f"stats_{season}", _variants(f"{NFLVERSE}/stats_player/stats_player_week_{season}"),
                  season == config.SEASON, required=False)


def snap_counts(season: int) -> pd.DataFrame:
    return _fetch(f"snaps_{season}", _variants(f"{NFLVERSE}/snap_counts/snap_counts_{season}"),
                  season == config.SEASON, required=False)


def pbp(season: int) -> pd.DataFrame:
    cols = ["season", "week", "season_type", "posteam", "play_type", "receiver_player_id",
            "rusher_player_id", "passer_player_id", "yardline_100", "air_yards", "complete_pass",
            "receiving_yards", "rushing_yards", "pass_touchdown", "rush_touchdown",
            "two_point_attempt", "qb_scramble", "td_player_id", "game_id", "play_id", "game_date",
            "qtr", "time", "desc"]
    df = _fetch(f"pbp_{season}",
                _variants(f"{NFLVERSE}/pbp/play_by_play_{season}", (".parquet", ".csv.gz", ".csv")),
                season == config.SEASON, required=False)
    return df[[c for c in cols if c in df.columns]] if len(df) else df


def injuries(season: int) -> pd.DataFrame:
    return _fetch(f"injuries_{season}", _variants(f"{NFLVERSE}/injuries/injuries_{season}"),
                  True, required=False)


def players() -> pd.DataFrame:
    return _fetch("players", _variants(f"{NFLVERSE}/players/players"), True)


def schedule() -> pd.DataFrame:
    return _fetch("games", _variants(f"{NFLVERSE}/schedules/games") + [f"{NFLDATA}/games.csv"], True)


def player_ids() -> pd.DataFrame:
    return _fetch("playerids", [f"{DYNASTYPROCESS}/db_playerids.csv"], True)


def fantasypros_ecr() -> pd.DataFrame:
    """FantasyPros expert consensus (itself an average of 100+ experts across sites)."""
    return _fetch("fpecr", [f"{DYNASTYPROCESS}/db_fpecr_latest.csv"], True)


def depth_charts(season: int) -> pd.DataFrame:
    """ESPN depth charts as snapshotted by nflverse (twice a day, with history)."""
    return _fetch(f"depth_{season}",
                  _variants(f"{NFLVERSE}/depth_charts/depth_charts_{season}", (".parquet", ".csv.gz", ".csv")),
                  True, required=False)
