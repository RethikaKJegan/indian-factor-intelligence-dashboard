"""Download monthly bhavcopy snapshots to build a point-in-time universe.

The survivorship problem in this project is specific and measurable: the
database holds today's Nifty 200 members with a full price history each, and
nothing that has since left the index. No symbol's series ends early, so there
is no attrition to detect -- the bias is entirely composition drift, and the only
way to see it is to know what actually traded at each point in time.

A bhavcopy is the complete list of everything that traded on one day. Taking
the last trading day of each month across the archive gives a monthly
point-in-time universe that can be diffed against the current index list, and
prices for any symbol the database happens to be missing.

The archive reaches back to roughly 2020; before that the files 404. That
covers about half the backtest window, and the limit is reported rather than
papered over.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}

BAV = ("https://nsearchives.nseindia.com/products/content/"
       "sec_bhavdata_full_{d:%d%m%Y}.csv")

WEEKEND = (5, 6)  # Saturday, Sunday


def _fetch(url: str, timeout: int = 30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


def month_end_dates(start: dt.date, end: dt.date) -> list[dt.date]:
    """Last weekday of each month in range, stepping back for non-trading days."""
    out: list[dt.date] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        if m == 12:
            ny, nm = y + 1, 1
            last = dt.date(y, 12, 31)
        else:
            ny, nm = y, m + 1
            last = dt.date(ny, nm, 1) - dt.timedelta(days=1)
        d = last
        while d.weekday() in WEEKEND:
            d -= dt.timedelta(days=1)
        if start <= d <= end:
            out.append(d)
        y, m = ny, nm
    return out


def fetch_months(
    cache_dir: Path,
    start: dt.date,
    end: dt.date,
    sleep: float = 0.35,
    progress=None,
) -> dict:
    """Fetch one bhavcopy per month into `cache_dir`, skipping cached files."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    got, missed, failed = {}, [], []
    dates = month_end_dates(start, end)
    for i, d in enumerate(dates, 1):
        p = cache_dir / f"bhav_{d:%Y-%m}.csv"
        if p.exists() and p.stat().st_size > 1000:
            got[str(d)[:7]] = p
            continue
        body = None
        # Step back up to 6 days: month ends are often holidays.
        probe = d
        for _ in range(6):
            body = _fetch(BAV.format(d=probe))
            if body:
                break
            probe -= dt.timedelta(days=1)
        if body:
            p.write_bytes(body)
            got[str(d)[:7]] = p
        else:
            failed.append(str(d)[:7])
        if progress and i % 10 == 0:
            progress(i, len(dates), len(got), failed)
        time.sleep(sleep)

    archive_floor = min(got) if got else None
    return {
        "cached": {k: str(v) for k, v in sorted(got.items())},
        "failed_months": failed,
        "count": len(got),
        "archive_floor": archive_floor,
        "requested_from": start.isoformat(),
        "requested_to": end.isoformat(),
    }


def parse_symbols(path: Path) -> set[str]:
    """Symbols present in one bhavcopy, equity series only."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    out: set[str] = set()
    for line in text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        sym, series = parts[0].strip(), parts[1].strip()
        if sym and series in ("EQ", "BE", "SM", "IL"):
            out.add(sym)
    return out


def build_universe(cache_dir: Path, result: dict) -> dict:
    """month -> sorted symbols actually trading at that month end."""
    monthly: dict[str, list[str]] = {}
    for month, path in result["cached"].items():
        monthly[month] = sorted(parse_symbols(Path(path)))
    return monthly


def first_and_last_traded(monthly: dict[str, list[str]]) -> tuple[dict, dict]:
    """Collapse the month x symbol matrix to two per-symbol lookups.

    The full matrix is roughly 2 MB and encodes exactly one fact per symbol:
    when it first and last appeared. Eligibility at a month is
    `first_traded[s] <= month`, so the two maps are sufficient, and the
    committed artifact shrinks to about 150 KB.
    """
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for month in sorted(monthly):
        for sym in monthly[month]:
            first.setdefault(sym, month)
            last[sym] = month
    return first, last


def write_artifact(
    out_path: Path,
    monthly: dict[str, list[str]],
    failed_months: list[str],
    requested_from: str,
    requested_to: str,
) -> dict:
    """Write the compact point-in-time artifact consumed by `point_in_time.py`."""
    first, last = first_and_last_traded(monthly)
    months = sorted(monthly)
    payload = {
        "source": (
            "NSE daily bhavcopy (sec_bhavdata_full), one file per month taken at "
            "the last trading day. The bhavcopy lists every symbol that traded "
            "that day, so it measures the trading universe directly rather than "
            "inferring it from today's index membership."
        ),
        "archive_floor": months[0] if months else None,
        "archive_ceiling": months[-1] if months else None,
        "months_covered": len(months),
        "symbols_observed": len(first),
        "failed_months": sorted(failed_months),
        "requested_from": requested_from,
        "requested_to": requested_to,
        "first_traded": first,
        "last_traded": last,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return payload
