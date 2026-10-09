"""Fetching web pages: free first, Firecrawl only when a site blocks us.

Ourlads, NBC Sports (Rotoworld) and PlayerProfiler all serve their pages to a plain
request, so that is always tried first and costs nothing. Some sites block traffic
from cloud servers such as GitHub's (ESPN did), and that is what Firecrawl is for: it
fetches the same page through a real browser. Each Firecrawl page costs one credit,
so usage is metered against a monthly budget (FIRECRAWL_MONTHLY_BUDGET, default 800
of the free plan's 1,000), with a smaller cap per run, and low-priority pages only
use Firecrawl while most of the month's budget is left.

Every page is saved, so if both routes fail the last good copy is used (for a few days).
"""
import datetime as dt
import gzip
import json
import time

import requests

from . import config

FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"
BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
RUN_CAP = 40          # most Firecrawl credits one run may spend
LOW_PRIORITY_SHARE = 0.6  # low-priority pages stop using Firecrawl past 60% of the month's budget

STATUS: dict = {}     # label -> {"direct": n, "firecrawl": n, "saved": n, "failed": n, "note": str}
_spent_this_run = 0
_session = requests.Session()
_session.headers.update(BROWSER)


def _dir():
    d = config.CACHE / "web"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ledger_path():
    return config.CACHE / "firecrawl_ledger.json"


def _month():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def credits_used(category: str | None = None) -> int:
    try:
        key = _month() + (f":{category}" if category else "")
        return int(json.loads(_ledger_path().read_text()).get(key, 0))
    except Exception:
        return 0


def _add_credits(n: int, category: str | None = None):
    global _spent_this_run
    _spent_this_run += n
    try:
        led = json.loads(_ledger_path().read_text())
    except Exception:
        led = {}
    led[_month()] = int(led.get(_month(), 0)) + n
    if category:
        led[f"{_month()}:{category}"] = int(led.get(f"{_month()}:{category}", 0)) + n
    _ledger_path().parent.mkdir(parents=True, exist_ok=True)
    _ledger_path().write_text(json.dumps(led))


def firecrawl_allowed(priority: str = "normal", category: str | None = None, category_cap: int | None = None) -> bool:
    if not config.FIRECRAWL_API_KEY:
        return False
    if category and category_cap is not None and credits_used(category) >= category_cap:
        return False
    used, budget = credits_used(), config.FIRECRAWL_MONTHLY_BUDGET
    if _spent_this_run >= RUN_CAP or used >= budget:
        return False
    if priority == "low" and used >= LOW_PRIORITY_SHARE * budget:
        return False
    return True


def _note(label, kind, msg=""):
    s = STATUS.setdefault(label, {"direct": 0, "firecrawl": 0, "cached": 0, "saved": 0, "failed": 0, "note": ""})
    s[kind] += 1
    if msg:
        s["note"] = msg


def _firecrawl(url: str, fresh_ms: int, wait_ms: int, category: str | None = None) -> str:
    r = requests.post(FIRECRAWL_URL, timeout=150,
                      headers={"Authorization": f"Bearer {config.FIRECRAWL_API_KEY}"},
                      json={"url": url, "formats": ["rawHtml"], "onlyMainContent": False,
                            "maxAge": fresh_ms, "waitFor": wait_ms, "timeout": 90000})
    try:
        j = r.json()
    except Exception:
        j = {}
    if r.status_code == 402:
        raise RuntimeError("Firecrawl credits used up for this month")
    if r.status_code == 401:
        raise RuntimeError("Firecrawl key rejected (check the FIRECRAWL_API_KEY secret)")
    if not r.ok or not j.get("success", True):
        raise RuntimeError(f"Firecrawl HTTP {r.status_code}: {str(j.get('error', ''))[:120]}")
    data = j.get("data") or {}
    _add_credits(int((data.get("metadata") or {}).get("creditsUsed") or 1), category)
    return data.get("rawHtml") or data.get("html") or ""


def get_html(key: str, url: str, label: str, max_age_h: float, valid, priority: str = "normal",
             stale_days: float = 4, wait_ms: int = 0, fc_every_h: float | None = None,
             category: str | None = None, category_cap: int | None = None) -> str | None:
    """Page HTML from the saved copy (if fresh), a plain request, or Firecrawl, in that order.

    `valid(html)` must confirm the page has the content we came for: a site that blocks
    bots usually answers 200 with a challenge page, which must not count as success.
    `fc_every_h`: when the plain request fails, only spend a Firecrawl credit if the saved
    copy is at least this old (defaults to max_age_h). Free retries happen every run.
    """
    d = _dir()
    page, meta_p = d / f"{key}.html.gz", d / f"{key}.json"  # gzipped: keeps GitHub's cache small
    meta = {}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text())
        except Exception:
            meta = {}
    age_h = (time.time() - meta.get("fetched", 0)) / 3600 if meta else 1e9
    if page.exists() and age_h < max_age_h:
        _note(label, "cached")
        return _read(page)

    def save(html, via):
        page.write_bytes(gzip.compress(html.encode("utf-8", "replace"), 6))
        meta_p.write_text(json.dumps({"fetched": time.time(), "via": via, "url": url}))
        _note(label, via)
        return html

    err = ""
    try:
        r = _session.get(url, timeout=30)
        if r.ok and valid(r.text):
            return save(r.text, "direct")
        if r.status_code in (404, 410):
            return None  # no such page: nothing to retry, and not worth a Firecrawl credit
        err = f"HTTP {r.status_code}" if not r.ok else "blocked or changed page"
    except Exception as e:
        err = type(e).__name__
    fc_due = not page.exists() or age_h >= (fc_every_h if fc_every_h is not None else max_age_h)
    if fc_due and firecrawl_allowed(priority, category, category_cap):
        try:
            html = _firecrawl(url, int(max_age_h * 3600 * 1000 / 2), wait_ms, category)
            if valid(html):
                return save(html, "firecrawl")
            err += "; Firecrawl page unreadable"
        except Exception as e:
            err += f"; {e}"
    elif config.FIRECRAWL_API_KEY and fc_due:
        err += "; Firecrawl budget held back"
    if page.exists() and age_h < stale_days * 24:
        _note(label, "saved", f"using saved copy ({err})")
        return _read(page)
    _note(label, "failed", err)
    return None


def _read(path) -> str:
    return gzip.decompress(path.read_bytes()).decode("utf-8", "replace")


def read_saved(key: str) -> str | None:
    """Last saved copy of a page, whatever its age (None if never fetched)."""
    p = _dir() / f"{key}.html.gz"
    try:
        return _read(p) if p.exists() else None
    except Exception:
        return None


def fetched_at(key: str) -> str | None:
    try:
        t = json.loads((_dir() / f"{key}.json").read_text())["fetched"]
        return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="minutes")
    except Exception:
        return None


def summary() -> dict:
    """Short status per source for the dashboard's Sources card."""
    out = {}
    for label, s in STATUS.items():
        parts = []
        if s["direct"]:
            parts.append(f"{s['direct']} page{'s' if s['direct'] > 1 else ''} direct")
        if s["firecrawl"]:
            parts.append(f"{s['firecrawl']} via Firecrawl")
        if s["cached"]:
            parts.append(f"{s['cached']} recent (not due yet)")
        if s["saved"]:
            parts.append(f"{s['saved']} from saved copy")
        if s["failed"]:
            parts.append(f"{s['failed']} failed")
        txt = ", ".join(parts) or "up to date"
        if s["note"] and (s["failed"] or s["saved"]):
            txt += f" ({s['note']})"
        out[label] = txt
    if config.FIRECRAWL_API_KEY:
        out["Firecrawl credits"] = f"{credits_used()} of {config.FIRECRAWL_MONTHLY_BUDGET} used this month"
    return out
