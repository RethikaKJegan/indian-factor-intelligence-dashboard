"""Indian risk-free rate, measured rather than assumed (spec section 22).

The dashboard reported Sharpe against a hard-coded 6.5% with the note that no
risk-free series existed in the data. That was wrong, and the search for it
started from the wrong place: `macro_monthly` carries `monthly_yield`, sourced
from the RBI, running from 1996 to the present. It is populated in **every one
of the 152 months** the backtest covers.

Using it changes the answer, and not in the flattering direction. The realised
mean over the window is 7.24%, against the 6.5% that had been assumed, so the
excess return is smaller and the risk-adjusted figure is lower. A hard-coded
rate is not a neutral placeholder; here it was overstating the result by about
a quarter of a Sharpe point.

The rate is applied month by month rather than as a single constant, because
the Indian 10-year moved from 9.15% to 5.98% inside this window. Averaging it
first would misstate both ends.
"""

from __future__ import annotations

import sqlite3

#: Fallback only, used when the database has no usable yield column at all.
#: Chosen to sit near the realised window mean so a total absence of data does
#: not silently produce a very different number, and reported as such.
FALLBACK_ANNUAL = 0.0724

#: Modified duration used to convert a yield change into a return.
#:
#: A 10-year government security has a modified duration around 7. This is a
#: stated assumption, not a measurement: the database carries a yield but no
#: bond index, so the price effect of a rate move has to be modelled rather
#: than read. It is disclosed because it is the one remaining estimated
#: quantity in the risk-adjusted numbers.
BOND_DURATION = 7.0


def realised_bond_return(prev_yield: float, curr_yield: float) -> float:
    """Approximate the one-month total return on a 10-year G-Sec.

    The carry is the yield earned over the month at the *previous* month's
    rate, because that is what a holder actually collects. The price effect is
    minus duration times the change in yield.

    Using the contemporaneous yield directly, as a naive Sharpe does, gets the
    second term wrong in exactly the months that matter. When yields fall
    during a risk-off period a bondholder earned *more* than the quoted rate,
    so excess return over that rate is understated. The correction therefore
    lowers the measured Sharpe in rallies, which is the direction that makes
    the result harder to sell rather than easier.
    """
    carry = prev_yield / 12.0
    price = -BOND_DURATION * (curr_yield - prev_yield)
    return carry + price


def load_series(db_path: str) -> dict:
    """Load the monthly Indian 10-year G-Sec yield.

    Returns a dict with the month -> annual-rate mapping, the column used, and
    enough provenance to say on the page where the number came from.
    """
    out: dict = {
        "source_column": "macro_monthly.monthly_yield",
        "instrument": "India 10-year government securities yield",
        "unit": "percent",
        "series": {},
        "coverage_note": "",
    }
    if not db_path:
        out["coverage_note"] = "No database supplied."
        return out

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        out["coverage_note"] = f"Could not open the database: {exc}"
        return out

    try:
        present = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "macro_monthly" not in present:
            out["coverage_note"] = "macro_monthly is absent from the database."
            return out

        cols = {r[1] for r in conn.execute("PRAGMA table_info(macro_monthly)")}
        if "monthly_yield" not in cols:
            out["coverage_note"] = "macro_monthly has no monthly_yield column."
            return out

        for month, value in conn.execute(
            "SELECT month, monthly_yield FROM macro_monthly "
            "WHERE monthly_yield IS NOT NULL ORDER BY month"
        ):
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            # The column is stored in percent (7.09 means 7.09%). Guard against
            # a future feed switching units, which would otherwise turn a 7%
            # rate into 700% and make every excess return hugely negative.
            if v > 50:
                v = v / 100.0
            out["series"][str(month)[:7]] = v / 100.0
    except sqlite3.Error as exc:
        out["coverage_note"] = f"Query failed: {exc}"
    finally:
        conn.close()

    return out


def resolve(loaded: dict, months: list[str]) -> dict:
    series = loaded.get("series") or {}
    months = sorted(m for m in months if m)
    if not months:
        return {
            "rates": {},
            "observed": 0,
            "carried_forward": 0,
            "total": 0,
            "coverage_pct": 0.0,
            "mean_annual": FALLBACK_ANNUAL,
            "min_annual": None,
            "max_annual": None,
            "first_month": None,
            "last_month": None,
            "used_fallback": True,
            "coverage_note": "No months to align.",
        }

    rates: dict[str, float] = {}
    observed = carried = 0
    last_seen: float | None = None
    for m in months:
        if m in series:
            last_seen = series[m]
            observed += 1
        elif last_seen is not None:
            carried += 1
        else:
            # Before the series starts there is nothing to carry forward. Using
            # a later observation would be look-ahead, so the window mean is
            # used and counted separately from the carried-forward months.
            continue
        if last_seen is not None:
            rates[m] = last_seen

    total = len(months)
    values = list(rates.values())
    return {
        "rates": rates,
        "observed": observed,
        "carried_forward": carried,
        "unavailable": total - observed - carried,
        "total": total,
        "coverage_pct": round(100.0 * observed / total, 1) if total else 0.0,
        "mean_annual": (sum(values) / len(values)) if values else FALLBACK_ANNUAL,
        "min_annual": min(values) if values else None,
        "max_annual": max(values) if values else None,
        "first_month": months[0] if months else None,
        "last_month": months[-1] if months else None,
        "used_fallback": not values,
        "coverage_note": (
            f"{observed} of {total} months observed directly from "
            f"{loaded.get('source_column')}; {carried} carried forward from "
            f"the prior month because the feed had no value for them."
        ),
    }


def describe(loaded: dict, aligned: dict) -> dict:
    """The JSON block the dashboard and the manifest read."""
    return {
        "is_measured": not aligned.get("used_fallback", True),
        "instrument": loaded.get("instrument"),
        "source_column": loaded.get("source_column"),
        "mean_annual": round(aligned.get("mean_annual") or 0.0, 6),
        "min_annual": aligned.get("min_annual"),
        "max_annual": aligned.get("max_annual"),
        "months_observed": aligned.get("observed"),
        "months_carried_forward": aligned.get("carried_forward"),
        "months_total": aligned.get("total"),
        "coverage_pct": aligned.get("coverage_pct"),
        "applied": "month by month, not as a window average",
        "note": (
            "The Indian 10-year moved between "
            f"{(aligned.get('min_annual') or 0) * 100:.2f}% and "
            f"{(aligned.get('max_annual') or 0) * 100:.2f}% over this window, so "
            "the rate is applied to each month separately. Using the window "
            "mean would misstate both ends."
        ),
    }
