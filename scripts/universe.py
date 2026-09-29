#!/usr/bin/env python3
"""
Universe coverage policy for the Nifty 200 modeling universe.

The canonical index list has 200 members, but the modeling universe is
whatever the local database can actually support. This module owns that
decision so it is defined in exactly one place and is auditable, instead of
being a silent hardcoded set inside the pipeline.

Two symbols can be dropped from modeling, for two different reasons:

1. No fundamentals history.
   NSE's `corporates-financial-results` API returns an empty list for these
   tickers, so no P/E, margin, growth or leverage series can be built.
   Without those, the Value and Quality factors cannot be scored at all.

2. No usable price history.
   These are recent NSE listings. They have far less than the ~24 months of
   monthly closes required to compute 3/6/12-month momentum, 6/12-month
   volatility and 12-month drawdown, so Momentum and Low Volatility cannot
   be scored without inventing pre-listing data.

Both are properties of the upstream sources, not of the model. This module
verifies them against the database on every run and emits a machine-readable
report to `public/data/universe_coverage.json`, so the dashboard can state
the real number and the reason instead of hardcoding one.

Adding a symbol back is a data problem, not a code problem: supply NSE
fundamentals and/or enough price history, then the next pipeline run picks it
up automatically. `assert_no_stale_exclusions` makes that explicit.
"""

from __future__ import annotations

# Canonical Nifty 200 size, used for reporting coverage.
NIFTY_200_SIZE = 200

# Minimum monthly closes before the price-derived factors are meaningful.
# The longest lookback in the factor set is 12-month momentum, which skips
# the most recent month, so 13 closes are the minimum needed to produce the
# first score. The database's own burn-in behaves the same way: the first
# three months of every symbol are NULL for momentum.
MIN_PRICE_MONTHS = 13

# A symbol needs at least this many months of fundamentals to be scored on
# the Value and Quality factors, which are built from trailing-twelve-month
# filing metrics.
MIN_FUNDAMENTAL_MONTHS = 12


# Baseline: symbols known to be unsupportable from the NSE sources, with the
# concrete upstream reason. This is documentation and a fallback for symbols
# that never reached the database at all -- it is not what decides the
# exclusion set. The database does: `excluded_symbols` is computed from
# measured coverage on every run, so a symbol here that later becomes
# supportable is restored without a code change. `assert_no_stale_exclusions`
# reports such symbols so the list can be trimmed.
BASELINE_EXCLUSIONS: dict[str, str] = {
    # NSE exposes no corporate financial-results rows for these tickers, so
    # Value/Quality cannot be computed.
    "HDFCLIFE": "no NSE fundamentals history",
    "ICICIAMC": "no NSE fundamentals history",
    "ICICIGI": "no NSE fundamentals history",
    "MCX": "no NSE fundamentals history",
    "SBILIFE": "no NSE fundamentals history",
    # Listed too recently to have the price history the factors require.
    "ENRIN": "insufficient price history (recent listing)",
    "GROWW": "insufficient price history (recent listing)",
    "LENSKART": "insufficient price history (recent listing)",
    "LGEINDIA": "insufficient price history (recent listing)",
    "TATACAP": "insufficient price history (recent listing)",
    "TMCV": "insufficient price history (recent listing)",
}


def assess_coverage(
    price_months: dict[str, int],
    fundamental_months: dict[str, int],
) -> dict[str, dict]:
    """Classify every symbol seen in the database as usable or excluded.

    Args:
        price_months: symbol -> count of distinct months of price history.
        fundamental_months: symbol -> count of distinct months of fundamentals.

    Returns:
        symbol -> {"eligible": bool, "reason": str, "price_months": int,
        "fundamental_months": int}. A symbol is eligible only if it clears
        both minimums.
    """
    coverage: dict[str, dict] = {}
    # Symbols in the canonical list but entirely absent from the database are
    # still classified, so the coverage report accounts for the whole index
    # rather than only the part that survived ingestion.
    for symbol in set(price_months) | set(fundamental_months) | set(BASELINE_EXCLUSIONS):
        n_price = int(price_months.get(symbol, 0))
        n_fund = int(fundamental_months.get(symbol, 0))
        # A symbol with no rows at all failed ingestion, so the measured
        # counts cannot say which side failed. Report the documented
        # upstream reason instead of guessing from two zeroes.
        if n_price == 0 and n_fund == 0:
            reason = BASELINE_EXCLUSIONS.get(symbol, "no data ingested from upstream sources")
            reasons = [reason]
        else:
            reasons = []
            if n_fund < MIN_FUNDAMENTAL_MONTHS:
                reasons.append("no NSE fundamentals history")
            if n_price < MIN_PRICE_MONTHS:
                reasons.append("insufficient price history (recent listing)")
        coverage[symbol] = {
            "eligible": not reasons,
            "reason": "; ".join(reasons),
            "price_months": n_price,
            "fundamental_months": n_fund,
        }
    return coverage


def excluded_symbols(coverage: dict[str, dict]) -> set[str]:
    """Return the set of symbols that must be dropped from modeling."""
    return {s for s, c in coverage.items() if not c["eligible"]}


def build_report(coverage: dict[str, dict], index_size: int = NIFTY_200_SIZE) -> dict:
    """Build the JSON payload written to `public/data/universe_coverage.json`."""
    excluded = excluded_symbols(coverage)
    eligible = sorted(s for s, c in coverage.items() if c["eligible"])
    reasons = {
        s: coverage[s]["reason"]
        for s in sorted(excluded)
        if coverage[s]["reason"]
    }
    return {
        "index_name": "Nifty 200",
        "index_size": index_size,
        "modeling_universe_size": len(eligible),
        "excluded_count": len(excluded),
        "excluded_symbols": reasons,
        "min_price_months_required": MIN_PRICE_MONTHS,
        "min_fundamental_months_required": MIN_FUNDAMENTAL_MONTHS,
        "note": (
            "Symbols are dropped only when the upstream NSE sources cannot "
            "support the factor set: no fundamentals history, or too little "
            "price history to score momentum and volatility. No price or "
            "fundamental values are imputed."
        ),
    }


def assert_no_stale_exclusions(coverage: dict[str, dict]) -> list[str]:
    """Report baseline exclusions that the database can now support.

    A non-empty result means the database has caught up for those symbols and
    the baseline list in this module should be trimmed. This is advisory: the
    database always wins, because `excluded_symbols` is computed from measured
    coverage rather than from the baseline.
    """
    return sorted(s for s in BASELINE_EXCLUSIONS if coverage.get(s, {}).get("eligible"))
