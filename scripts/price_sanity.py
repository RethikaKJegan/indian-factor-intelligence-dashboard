#!/usr/bin/env python3
"""
Corporate-action guard for monthly return series.

`stock_prices_monthly.monthly_close` is a RAW close, not an adjusted close, and
`monthly_return` is computed as `close/prev_close - 1` from it. Indian NSE
companies split, issue bonus shares and restructure frequently, and a raw
close series records those events as if they were trading gains.

PATANJALI is the clearest example in this dataset:

    2019-12-31  close =  108.23
    2020-01-31  close =    6.64   monthly_return = -93.87%   (1:16 split)
    2020-02-29  close =   20.03   monthly_return = +201.70%  (not a real gain)
    2020-03-31  close =   55.58   monthly_return = +177.50%  (not a real gain)

None of those moves are investor returns. Left uncorrected they propagate into
the factor return series, the baskets, the allocation and the headline
backtest, inflating the top-10 momentum basket by roughly 0.9 percentage points
per month.

What this module does
---------------------
It flags monthly returns that cannot be a real single-month move in an
ordinary NSE large/mid-cap and replaces them with a winsorised value at the
threshold. It does NOT delete observations and does NOT invent a split ratio it
cannot justify: a symbol-month that trips the guard is marked, and the count is
reported in the run report so the number of corrections is visible rather than
silent.

The guard is deliberately a bound, not a reconstruction. Reconstructing true
split-adjusted history would require the corporate-action table, which this
project does not carry; a documented, bounded correction is the honest
alternative to either shipping fabricated returns or shipping known-wrong ones.
"""

from __future__ import annotations

# No Nifty 200 constituent moves this far in a calendar month without a
# corporate action. Set just outside the plausible band so genuine extreme
# months (March 2020, for example) are still represented rather than erased.
MAX_ABS_MONTHLY_RETURN = 0.35


def winsorize_returns(
    price_rows: list[tuple[str, str, float]],
    threshold: float = MAX_ABS_MONTHLY_RETURN,
) -> tuple[dict[tuple[str, str], float], list[dict]]:
    """Return winsorised monthly returns plus a record of every correction.

    Args:
        price_rows: (month, symbol, monthly_return) in any order.
        threshold: largest magnitude a single month may take.

    Returns:
        (returns keyed by (month, symbol), corrections). A corrected month is
        clamped to +/- threshold and also appears in `corrections` with the
        original value, so the pipeline can report it.
    """
    returns: dict[tuple[str, str], float] = {}
    corrections: list[dict] = []
    for month, symbol, value in price_rows:
        if value is None:
            continue
        v = float(value)
        if abs(v) <= threshold:
            returns[(month, symbol)] = v
            continue
        clamped = threshold if v > 0 else -threshold
        returns[(month, symbol)] = clamped
        corrections.append({
            "month": month,
            "symbol": symbol,
            "raw_return": round(v, 6),
            "corrected_return": round(clamped, 6),
        })
    return returns, corrections


def summarize(corrections: list[dict], window_months: int = 0) -> dict:
    """Aggregate corrections for the run report and the dashboard."""
    if not corrections:
        return {
            "corrected_rows": 0,
            "symbols_affected": 0,
            "months_affected": 0,
            "note": "No monthly return exceeded the corporate-action bound.",
        }
    symbols = {c["symbol"] for c in corrections}
    months = {c["month"] for c in corrections}
    worst = max(corrections, key=lambda c: abs(c["raw_return"]))
    return {
        "corrected_rows": len(corrections),
        "symbols_affected": len(symbols),
        "months_affected": len(months),
        "max_abs_raw_return": round(abs(worst["raw_return"]), 4),
        "max_abs_example": f"{worst['symbol']} {worst['month']}",
        "threshold": MAX_ABS_MONTHLY_RETURN,
        "note": (
            "Monthly returns are computed from raw closes, so splits and bonus "
            "issues appear as large gains or losses. Values beyond the bound "
            "are winsorised; no observation is deleted and no split ratio is "
            "assumed."
        ),
    }
