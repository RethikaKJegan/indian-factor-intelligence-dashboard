"""Diagnose structural fundamental-coverage holes, not just the count of Nones.

`factor_coverage_withheld` reported 11,313 withheld score-months, which is a
symptom. The cause is that some symbols have a full price history and
fundamentals rows but *no* populated metric in any month -- and in this dataset
that is every bank. HDFCBANK, AXISBANK, BANKBARODA, CANBK and the rest have
153 months of rows and 0 months of values.

That is not missing data in the usual sense. A bank genuinely does not report
the fields the Value and Quality factors are built from: there is no comparable
revenue line, and leverage is meaningless for a deposit-taking balance sheet.
So the two fundamental factors are structurally blind to the whole financial
services sector, which is a large slice of the index. A count of withheld
scores does not say that. A list of which symbols are structurally excluded,
and for which reason, does.
"""
from __future__ import annotations

import sqlite3

#: Metrics the factor engine consumes. A symbol needs at least one of these in
#: at least one month to be measurable at all.
FOUNDATIONAL_METRICS = (
    "monthly_pe",
    "earnings_yield_ttm",
    "debt_equity",
    "profit_margin",
    "earnings_growth",
    "revenue_growth",
)

#: Sectors whose reporting conventions make these metrics non-comparable. A
#: bank's balance sheet is not an industrial's: deposits are not debt in the
#: sense debt/equity assumes, and there is no revenue line to grow.
STRUCTURALLY_EXCLUDED = {
    "banking", "financial services", "finance", "nbfc", "insurance",
    "financial services ",
}


def analyse(db_path: str, months: list[str] | None = None) -> dict:
    """Classify every symbol as measured, partially covered, or structurally out."""
    if not db_path or not months:
        return {"available": False, "symbols": [], "summary": {}}

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"available": False, "error": str(exc), "symbols": []}

    try:
        present = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "fundamentals_monthly" not in present:
            return {"available": False, "error": "fundamentals_monthly absent",
                    "symbols": []}

        lo, hi = min(months), max(months)
        has_any = " OR ".join(f"{m} IS NOT NULL" for m in FOUNDATIONAL_METRICS)
        rows = conn.execute(
            f"SELECT symbol, "
            f"       MAX(sector), "
            f"       COUNT(*), "
            f"       SUM(CASE WHEN {has_any} THEN 1 ELSE 0 END) "
            f"FROM fundamentals_monthly "
            f"WHERE month BETWEEN ? AND ? "
            f"GROUP BY symbol",
            (lo, hi),
        ).fetchall()
    except sqlite3.Error as exc:
        return {"available": False, "error": str(exc), "symbols": []}
    finally:
        conn.close()

    out: list[dict] = []
    for symbol, sector, total, with_metric in rows:
        total = total or 0
        with_metric = with_metric or 0
        sector_s = (sector or "").strip()
        sec_key = sector_s.lower()
        structural = any(k in sec_key for k in STRUCTURALLY_EXCLUDED)
        if with_metric == 0:
            classification = "structurally_excluded" if structural else "unexplained_gap"
            reason = (
                f"Reports on {sector_s} conventions, so none of the metrics the "
                "fundamental factors use is comparable. Not a data outage."
                if structural
                else "Has fundamental rows but no populated metric in any month. "
                     "The ingestion path is not filling these symbols, which is "
                     "a gap rather than an economic fact."
            )
        elif with_metric < total * 0.5:
            classification = "sparse"
            reason = (
                f"Metrics present in only {with_metric} of {total} months, so "
                "the coverage rule withholds the score in most months."
            )
        else:
            classification = "measured"
            reason = f"Metrics present in {with_metric} of {total} months."

        out.append({
            "symbol": symbol,
            "sector": sector_s or "Unknown",
            "months_with_rows": total,
            "months_with_any_metric": with_metric,
            "coverage_pct": round(100.0 * with_metric / total, 1) if total else 0.0,
            "classification": classification,
            "reason": reason,
        })

    by_class: dict[str, int] = {}
    for r in out:
        by_class[r["classification"]] = by_class.get(r["classification"], 0) + 1

    structural = [r for r in out if r["classification"] == "structurally_excluded"]
    unexplained = [r for r in out if r["classification"] == "unexplained_gap"]

    return {
        "available": True,
        "window": {"from": lo, "to": hi},
        "summary": {
            "total_symbols": len(out),
            "by_classification": by_class,
            "structural_sector_exposure_pct": round(
                100.0 * len(structural) / len(out), 1
            ) if out else 0.0,
        },
        "structurally_excluded_sectors": sorted({r["sector"] for r in structural}),
        "unexplained": [r["symbol"] for r in unexplained],
        "symbols": sorted(out, key=lambda r: (r["classification"], r["symbol"])),
        "note": (
            "These symbols are excluded from the Value and Quality factors, not "
            "from the universe. Momentum and Low Volatility are price-based and "
            "still cover them. The count of withheld score-months is a symptom; "
            "this is the cause."
        ),
    }
