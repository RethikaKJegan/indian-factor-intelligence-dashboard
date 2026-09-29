"""Point-in-time universe eligibility, measured against the NSE bhavcopy archive.

The database holds today's Nifty 200 members with a full price history each.
Measured against the archive (2019-09 to 2026-08, 84 month-ends, built by
`nse_universe.py`), that produces two distinct problems, and conflating them
would hide one behind the other:

**Look-forward, and fixable.** 36 of the 189 symbols in the database were not
trading in September 2019. Several are 2024-25 listings carrying a price series
that could not have existed earlier. A backtest that scores, ranks and could
have held a stock before it listed is describing a strategy nobody could run.
`eligible_at` makes eligibility a function of when the stock actually first
traded, so this class of error is impossible rather than disclosed.

**Exclusion, and not fixable here.** 412 symbols traded in September 2019 and
had stopped by August 2026. None are in the database. They are the population a
today-constituent universe cannot contain, and no amount of pipeline work
creates fundamentals for names the database has never seen. What this module
does is make that population a *counted* number, so the residual bias is
reported as a measurement instead of an unstated assumption.

The archive floor is 2019-09, five years after the backtest starts. For months
before it there is no evidence of what traded, and `eligible_at` falls back to
the database. That fallback is the part of the bias this module does not touch,
and it is why the caveat stays HIGH rather than being retired.
"""

from __future__ import annotations

import json
import os

PIT_REL_PATH = "data_input/nse_trading_universe.json"


def load_point_in_time(project_dir: str) -> dict | None:
    """Load the bhavcopy-derived trading record, or None when it is absent.

    The artifact is committed, so a scheduled run has it without fetching
    anything. When it is missing the caller must treat point-in-time gating as
    unavailable rather than assuming it passed.
    """
    path = os.path.join(project_dir, *PIT_REL_PATH.split("/"))
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get("first_traded") else None


def first_traded(pit: dict) -> dict[str, str]:
    return pit.get("first_traded") or {}


def last_traded(pit: dict) -> dict[str, str]:
    return pit.get("last_traded") or {}


def eligible_at(pit: dict, month: str, db_symbols: set[str]) -> set[str]:
    """Symbols in the database that had started trading by `month`.

    Before the archive floor there is no evidence either way, so this returns
    the full database set. That is the unmeasured part of the bias, and the
    caller reports the fraction of the backtest it covers.
    """
    first = first_traded(pit)
    if not first:
        return set(db_symbols)
    floor = min(first.values())
    if month < floor:
        return set(db_symbols)
    return {s for s in db_symbols if first.get(s, floor) <= month}


def assess_survivorship(pit: dict, db_symbols: set[str], backtest_months=None) -> dict:
    """Measure how much of the tradable universe the database is missing."""
    first = first_traded(pit)
    last = last_traded(pit)
    if not first:
        return {"available": False, "reason": "no bhavcopy trading record available"}

    months = sorted(set(first.values()) | set(last.values()))
    floor, ceiling = months[0], months[-1]

    # Names that were trading when the archive opens and were not by the time it
    # closes. Restricted to those the database has never seen, because that is
    # the population a survivorship-biased universe is defined by.
    at_start = {s for s, m in first.items() if m == floor}
    at_end = {s for s, m in last.items() if m == ceiling}
    stopped_absent = (at_start - at_end) - db_symbols

    # Database symbols that did not exist when the archive opens.
    late = {s: first[s] for s in db_symbols if s in first and first[s] > floor}

    # How much of the backtest the gate can actually police. Months before the
    # archive floor fall back to the database, and that fraction is the honest
    # measure of what the look-forward fix covers.
    covered, uncovered = 0, 0
    for m in (backtest_months or []):
        if m < floor:
            uncovered += 1
        else:
            covered += 1
    total = covered + uncovered

    return {
        "available": True,
        "archive_floor": floor,
        "archive_ceiling": ceiling,
        "months_covered": int(pit.get("months_covered") or 0),
        "symbols_observed": len(first),
        "trading_universe_at_archive_start": len(at_start),
        "trading_universe_at_archive_end": len(at_end),
        "stopped_trading_absent_from_db": len(stopped_absent),
        "db_symbols": len(db_symbols),
        "db_symbols_trading_at_archive_start": len(db_symbols & at_start),
        "db_symbols_not_yet_listed_at_archive_start": len(late),
        "db_symbols_not_yet_listed_examples": dict(list(late.items())[:15]),
        "examples_of_excluded_names": sorted(stopped_absent)[:20],
        "backtest_months_gated": covered,
        "backtest_months_ungated": uncovered,
        "backtest_months_gated_pct": round(100.0 * covered / total, 1) if total else 0.0,
        "interpretation": (
            f"{len(stopped_absent)} names traded when the archive opens and had "
            f"stopped by the time it closes, and the database holds none of them. "
            f"That is the population a today-constituent universe cannot contain, "
            f"and it remains uncorrected: it needs fundamentals for names never "
            f"ingested, which is data acquisition rather than calculation. "
            f"Separately, {len(late)} of the {len(db_symbols)} database symbols "
            f"had not begun trading when the archive opens; those are now gated "
            f"out of the {covered} of {total} backtest months the archive covers "
            f"({round(100.0 * covered / total, 1) if total else 0.0}%). The "
            f"remaining {uncovered} months predate the archive and are ungated."
        ),
    }
