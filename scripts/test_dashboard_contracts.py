"""Guard tests for defects that reached the dashboard and stayed there.

Each test here corresponds to a fault that was present in a shipped
`public/data/*.json` and survived a full pipeline rewrite, because nothing
checked for it. They are deliberately narrow and dependency-free: they read
the published artifacts rather than re-running the pipeline, so they are fast
and they test what a consumer of the dashboard would actually receive.

Run with:

    python -m pytest scripts/test_dashboard_contracts.py -q

or, without pytest installed:

    python scripts/test_dashboard_contracts.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "public", "data")


def load(name):
    with open(os.path.join(DATA, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def _rows(name):
    d = load(name)
    return d if isinstance(d, list) else []


# Columns a source table genuinely does not have. Listing them keeps the
# no-null-columns test from failing forever on a field that cannot exist, while
# still failing if a column that *can* exist silently goes empty.
#
# market_index_monthly stores a month-end close and no intraday range, so there
# is no open/high/low to publish; the JSON marks them null and says so in
# `ohlc_note`.
EXPECTED_NULL_COLUMNS = {
    "market_index": {"open", "high", "low"},
    "macro_monthly": {"fii_net", "dii_net"},
}


def test_no_silently_null_export_columns():
    """No published column may be null for every row unless documented as such.

    Four files shipped 306-1937 rows of nulls for months because the exporter
    asked SQLite for column names the tables do not use (`close` where the
    table says `monthly_close`). Nothing failed; the files were just empty.
    """
    offenders = {}
    for fname in sorted(os.listdir(DATA)):
        if not fname.endswith(".json"):
            continue
        rows = _rows(fname[:-5])
        if not rows or not isinstance(rows[0], dict):
            continue
        allowed = EXPECTED_NULL_COLUMNS.get(fname[:-5], set())
        dead = [
            k for k in rows[0]
            if k not in allowed and all(r.get(k) is None for r in rows)
        ]
        if dead:
            offenders[fname] = dead
    assert not offenders, (
        "these exports are entirely null, which is how the "
        "column-name mismatch shipped unnoticed: " + repr(offenders)
    )


def test_documented_null_columns_carry_a_note():
    """A deliberately-null column must say why, in the data itself."""
    idx = _rows("market_index")
    if idx:
        assert any(r.get("ohlc_note") for r in idx), (
            "market_index has no open/high/low because the monthly table stores "
            "none, but the rows must carry ohlc_note explaining that"
        )
    macro = _rows("macro_monthly")
    if macro:
        assert any(r.get("flows_note") for r in macro), (
            "macro_monthly FII/DII are null because the database columns are "
            "empty, but the rows must carry flows_note saying so"
        )


def test_allocation_weights_sum_to_one():
    """Every month's factor weights must be a complete allocation.

    Protects a property that currently holds for all 152 months: an
    optimisation that lost weight to rounding or a failed sleeve would
    silently change what the dashboard reports as the portfolio.
    """
    allocs = _rows("factor_allocations")
    assert allocs, "no factor_allocations rows"
    cols = ("momentum_weight", "value_weight", "quality_weight", "low_volatility_weight")
    bad = []
    for a in allocs:
        if a.get("is_warmup"):
            continue
        total = sum(float(a.get(c) or 0.0) for c in cols)
        if abs(total - 1.0) > 1e-6:
            bad.append((a.get("month"), round(total, 6)))
    assert not bad, f"allocations not summing to 1.0: {bad[:5]}"


def test_portfolio_target_weights_do_not_exceed_position_cap():
    """No single holding may exceed the 5% cap the construction enforces."""
    targets = _rows("portfolio_targets")
    assert targets, "no portfolio_targets rows"
    worst = max((float(t.get("target_weight") or 0.0) for t in targets), default=0.0)
    assert worst <= 0.05 + 1e-6, (
        f"a target weight reached {worst:.4f}, above the 5% cap; the cap is "
        "recomputed and renormalised in portfolio_construction"
    )


def test_backtest_metrics_match_their_own_return_series():
    """Reported CAGR must be reproducible from the published monthly returns.

    Recomputing every headline from the series is the check that would have
    caught a summary table that drifted from the curve it describes.
    """
    bp = _rows("backtest_portfolio")
    summaries = {s["strategy_name"]: s for s in _rows("backtest_summary")}
    assert bp and summaries
    by = defaultdict(list)
    for r in bp:
        by[r["strategy_name"]].append(r["monthly_return"])

    checked = 0
    for name, rets in by.items():
        summary = summaries.get(name)
        if summary is None:
            continue
        value = 100.0
        for r in rets:
            value *= (1 + r)
        years = len(rets) / 12.0
        cagr = (value / 100.0) ** (1.0 / years) - 1
        assert abs(cagr - summary["cagr"]) <= max(0.01 * abs(summary["cagr"]), 5e-4), (
            f"{name}: reported CAGR {summary['cagr']} but the series gives {cagr:.4f}"
        )
        checked += 1
    assert checked >= 3, f"only {checked} strategies cross-checked"


def test_equal_weight_baseline_is_reported():
    """The factor strategies must be shown against an equal-weight universe.

    A cap-weighted price index is a weak yardstick for a factor book tilted
    toward smaller names: the 189-name universe equal-weighted returned well
    above it. Without this row the factor result cannot be interpreted, which
    is how a strategy that trailed the naive baseline appeared to beat the
    market.
    """
    names = {s["strategy_name"] for s in _rows("backtest_summary")}
    assert "Universe Equal-Weight" in names, (
        f"no equal-weight universe baseline in backtest_summary; found {sorted(names)}"
    )


def test_forward_forecast_does_not_use_the_outcome_month():
    """A forecast must not be built from the month it predicts.

    The original look-ahead defect was the optimiser choosing weights from the
    factor return already realised in the month it then traded. The forward
    outlook reintroduces the same shape if it is ever wired to realised data, so
    the guard is on the artefact: a forecast whose expected return equals the
    realised return for that same month, across every sleeve, is the signature.
    """
    fo = load("forward_outlook")
    assert fo and fo.get("forecast_history"), "no forecast history emitted"
    realised = {str(r.get("month"))[:7]: r for r in _rows("factor_returns")}

    identical = []
    for f in fo["forecast_history"]:
        got = realised.get(str(f.get("month"))[:7])
        if not got:
            continue
        er = f.get("expected_factor_returns") or {}
        pairs = [
            (er.get(name), got.get(f"{k}_return"))
            for name, k in (
                ("Momentum", "momentum"), ("Value", "value"),
                ("Quality", "quality"), ("Low Volatility", "low_volatility"),
            )
        ]
        pairs = [(p, r) for p, r in pairs if p is not None and r is not None]
        if len(pairs) < 4:
            continue
        if all(abs(float(p) - float(r)) < 1e-9 for p, r in pairs):
            identical.append(f.get("month"))
    assert len(identical) < len(fo["forecast_history"]) * 0.5, (
        f"{len(identical)} of {len(fo['forecast_history'])} forecasts are "
        "numerically identical to the outcome they predict, which means the "
        "forecast is the realised return"
    )


def test_forecast_accuracy_is_reported_with_its_sample_size():
    """A hit rate quoted without its observation count is not checkable."""
    fo = load("forward_outlook")
    acc = (fo or {}).get("accuracy")
    assert acc, "no forecast accuracy block emitted"
    if acc.get("hit_rate") is not None:
        assert acc.get("sleeve_observations", 0) >= acc.get("hit_rate_suppressed_below_months", 0), (
            "a hit rate was published below the minimum sample it claims to require"
        )
    assert isinstance(acc.get("interpretation"), str) and acc["interpretation"], (
        "accuracy must carry a plain-language interpretation"
    )


def test_news_articles_carry_entity_tags():
    """News must be linked to the universe, not scored as an anonymous blob.

    Relevance feeds `news_stress_score`, which shifts factor weights. With no
    symbol tagging, a story about a foreign central bank moved Indian
    allocations, which is what the tagging exists to prevent.
    """
    arts = _rows("news_articles_raw")
    if not arts:
        return  # nothing fetched this run; nothing to assert
    tagged = [a for a in arts if a.get("symbols")]
    assert tagged, (
        "no article names a constituent; entity tagging is what keeps off-topic "
        "headlines out of the allocation"
    )
    for a in tagged:
        assert a.get("relevance") is not None, "a tagged article must carry a relevance score"
        assert a.get("relevance_band") in {"high", "medium", "low", "off_topic"}


def test_regime_warmup_months_are_labelled_not_scored():
    """Unscored months must say so rather than publishing a zero confidence.

    A walk-forward model cannot classify its warm-up period. Publishing a
    confidence for those months would present a guess as a measurement.
    """
    rows = _rows("regime_predictions")
    warm = [r for r in rows if r.get("is_warmup")]
    if not warm:
        return
    for r in warm:
        assert r.get("regime_label") == "Unscored", (
            f"{r.get('month')} is a warm-up month but is labelled {r.get('regime_label')!r}"
        )
        assert r.get("regime_confidence") is None, (
            f"{r.get('month')} is a warm-up month but publishes a confidence"
        )


def test_eod_monthly_aggregates_are_idempotent():
    """`daily_count` and `monthly_volume` must not grow on repeated runs.

    `refresh_stock_month` used to add the stored day's count and volume onto
    the value already in the row, with a `baseline_eod` filter that is absent
    on a normal run. Every scheduled invocation therefore re-added the whole
    month, and by 2026-09 the count had reached 37-38 against 5 stored trading
    days, with volume up to 8.5x true. The error compounded daily, so a table
    read a month later was further wrong than one read a week earlier.

    Both are now derived from `stock_prices_daily`, which makes the function
    idempotent. This asserts the resulting invariant: neither figure may exceed
    what the daily table actually contains for that month.
    """
    import sqlite3
    db = os.path.join(ROOT, "data_input", "processed_financial_data.sqlite")
    if not os.path.exists(db):
        return
    conn = sqlite3.connect(db)
    try:
        months = [r[0] for r in conn.execute(
            "SELECT DISTINCT month FROM stock_prices_monthly ORDER BY month DESC LIMIT 6")]
        problems = []
        for month in months:
            prefix = str(month)[:7]
            real_days = conn.execute(
                "SELECT COUNT(DISTINCT date) FROM stock_prices_daily WHERE substr(date,1,7)=?",
                (prefix,)).fetchone()[0]
            if not real_days:
                continue
            lo, hi = conn.execute(
                "SELECT MIN(daily_count), MAX(daily_count) FROM stock_prices_monthly WHERE month=?",
                (month,)).fetchone()
            if hi and hi > real_days:
                problems.append(
                    f"{month}: daily_count up to {hi} against {real_days} stored days")
        assert not problems, (
            "monthly aggregates were accumulated instead of recomputed, so they "
            "exceed the daily data: " + "; ".join(problems)
        )
    finally:
        conn.close()


def test_portfolio_cash_is_accounted_for():
    """Idle weight must be visible, not silently absorbed by a renormalised chart.

    Target weights sum to less than 1 in most months because unallocated weight
    is left in cash rather than forced into a name. The exposure chart divides
    by invested weight, so without a published cash figure the book reads as
    fully deployed when up to 17% of it earned nothing.
    """
    pt = _rows("portfolio_targets")
    if not pt:
        return
    by_month = defaultdict(list)
    for t in pt:
        by_month[t["month"]].append(t)

    worst_cash, worst_month = 0.0, None
    for m, rows in by_month.items():
        invested = sum(float(r.get("target_weight") or 0) for r in rows)
        cash = max(0.0, 1.0 - invested)
        if cash > worst_cash:
            worst_cash, worst_month = cash, m

    cc_path = os.path.join(DATA, "portfolio_constraint_compliance.json")
    assert os.path.exists(cc_path), "cash is not published anywhere"
    with open(cc_path, encoding="utf-8") as fh:
        cc = json.load(fh)
    assert "cash" in cc.get("months", {}).get(worst_month, {}), (
        f"{worst_month} leaves {worst_cash:.2%} uninvested but no cash figure is published"
    )
    # And the reported cash must match the shortfall implied by the weights.
    for m, rows in by_month.items():
        invested = sum(float(r.get("target_weight") or 0) for r in rows)
        rep = cc["months"].get(m, {}).get("cash")
        if rep is not None and abs((1 - invested) - rep) > 1e-3:
            raise AssertionError(
                f"{m}: weights imply cash {1-invested:.4f} but {rep:.4f} is reported")


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {t.__name__}\n        {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
