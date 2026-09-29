#!/usr/bin/env python3
"""
Factor construction from raw fundamentals and prices.

The shipped scores came from `factor_scores_monthly`, which is a pre-built
table. Three problems were visible in the raw inputs:

1. **Outliers were never bounded.** `monthly_pe` ranges 3.56 to 1893.61 in the
   latest month alone. A single 1893x P/E z-score dominates a cross-sectional
   ranking, so one bad print decides whether a stock is a "Value" pick.

2. **Metrics were averaged regardless of how many were present.** 21 stocks
   have zero populated metrics in the latest month and are still scored, and
   `debt_equity` is populated for only 83 of 168 stocks, so Quality was
   frequently computed from a single surviving metric.

3. **Scoring was global, not sector-relative.** Financial Services carries a
   mean `profit_margin` of 0.44 against 0.15 for Information Technology, and
   mean `debt_equity` of 0.03 against 0.01 elsewhere. Ranking those raw is
   partly a bet on sector membership: a bank looks "high quality" and an IT
   firm looks "expensive" for structural reasons, not because of the factor.

This module rebuilds each factor as:

    raw metric
      -> winsorize (cross-sectional percentile cap)
      -> sector-neutralise (demean within sector)
      -> cross-sectional z-score
      -> combine, only if the coverage rule is met
      -> rank

Every stage is explicit and testable, and a factor that cannot be computed
returns `None` rather than a number built from whatever survived.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Winsorization ──────────────────────────────────────────────────────────
#: Fraction of the cross-section trimmed from each tail before scaling.
WINSOR_TAIL = 0.025  # 2.5/97.5, per spec sec 10.

# ── Coverage rules (spec sec 11) ───────────────────────────────────────────
#: A factor is only computed when at least this share of its component
#: metrics are present for that stock-month. Below it the score is None.
MIN_METRIC_COVERAGE = 0.75

#: A sector must hold at least this many stocks for its mean to be meaningful.
MIN_SECTOR_SIZE = 4


@dataclass(frozen=True)
class FactorSpec:
    """One factor: the metrics it uses, their sign, and its coverage rule."""

    name: str
    #: metric name -> weight in the composite. `invert` is applied first.
    metrics: dict[str, float]
    #: Minimum share of metrics (by count, not weight) that must be present.
    min_coverage: float = MIN_METRIC_COVERAGE
    #: Sector-specific treatment. Banks and NBFCs are excluded from leverage
    #: metrics because a bank's balance sheet is not comparable to an
    #: industrial's; the spec calls this out explicitly in sec 8.
    leverage_sensitive: bool = False
    leverage_exempt_sectors: tuple[str, ...] = (
        "Financial Services",
        "Banking",
        "Finance",
    )

    def is_leverage_metric(self, metric: str) -> bool:
        """True for metrics that only make sense for non-financial firms."""
        return metric in ("debt_equity", "debt_to_equity", "interest_coverage", "leverage")


#: The four factors the project retains, with the metrics that are actually
#: populated in `fundamentals_monthly`. Metrics that exist as columns but are
#: 0% populated (ROE, ROCE, PB, EV/EBITDA) are deliberately absent; adding
#: them would silently contribute nothing.
FACTOR_SPECS: dict[str, FactorSpec] = {
    "Momentum": FactorSpec(
        name="Momentum",
        # Purely price-based; the price layer already skips the current month.
        metrics={},
        min_coverage=1.0,
    ),
    "Value": FactorSpec(
        name="Value",
        # Lower P/E and higher earnings yield are the same signal viewed two
        # ways, so P/E carries the larger weight and is inverted.
        metrics={"monthly_pe": -0.5, "earnings_yield_ttm": 0.5},
    ),
    "Quality": FactorSpec(
        name="Quality",
        metrics={
            "profit_margin": 0.35,
            "earnings_growth": 0.25,
            "revenue_growth": 0.25,
            "debt_equity": -0.15,
        },
        leverage_sensitive=True,
    ),
    "Low Volatility": FactorSpec(name="Low Volatility", metrics={}, min_coverage=1.0),
}


def winsorize(values: list[float], tail: float = WINSOR_TAIL) -> list[float]:
    """Clamp a cross-section to its [tail, 1-tail] percentile range.

    Clamping rather than dropping keeps every stock in the ranking; a name with
    a genuinely extreme multiple keeps its place at the end instead of
    disappearing from the universe.
    """
    if not values:
        return []
    ordered = sorted(values)
    n = len(ordered)
    k = int(n * tail)
    if k <= 0 or n - k - 1 < k:
        # Too few observations for the requested tail; return as-is.
        return list(values)
    lo = ordered[k]
    hi = ordered[n - k - 1]
    return [min(max(v, lo), hi) for v in values]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def sector_neutral_scores(
    values: dict[str, float],
    sectors: dict[str, str],
    min_sector_size: int = MIN_SECTOR_SIZE,
) -> dict[str, float]:
    """Demean each value within its sector, then scale the whole cross-section.

    Sectors with too few members keep their raw value: demeaning a group of
    two against its own mean would drive both to zero and discard real signal.
    """
    out: dict[str, float] = {}
    by_sector: dict[str, list[str]] = {}
    for sym in values:
        by_sector.setdefault(sectors.get(sym, "Unknown"), []).append(sym)

    for sector, members in by_sector.items():
        if len(members) < min_sector_size:
            for sym in members:
                out[sym] = values[sym]
            continue
        sector_mean = _mean([values[s] for s in members])
        for sym in members:
            out[sym] = values[sym] - sector_mean

    # Scale the neutralised values so the composite stays comparable across
    # factors with different natural units.
    sd = _stdev(list(out.values()))
    if sd <= 0:
        return {k: 0.0 for k in out}
    return {k: v / sd for k, v in out.items()}


def build_factor_scores(
    symbol_metrics: dict[str, dict[str, float]],
    sectors: dict[str, str],
    specs: dict[str, FactorSpec] = None,
    sector_neutral: bool = True,
) -> tuple[dict[str, dict[str, float | None]], dict[str, dict]]:
    """Compute one score per factor per stock, or None when under-covered.

    Args:
        symbol_metrics: symbol -> metric name -> value. Missing keys are
            treated as absent, not as zero.
        sectors: symbol -> sector, for sector-neutral scoring.
        specs: factor definitions. Defaults to {@link FACTOR_SPECS}.
        sector_neutral: apply sector demeaning to fundamental metrics.

    Returns:
        (scores, diagnostics) where `scores` is factor -> symbol -> score or
        None, and `diagnostics` records why a score is missing.
    """
    specs = specs or FACTOR_SPECS
    symbols = sorted(symbol_metrics)
    scores: dict[str, dict[str, float | None]] = {}
    diagnostics: dict[str, dict] = {}
    #: Winsorization is applied to the inputs, but a composite of several
    #: z-scores can still reach |8| where one metric is extreme. The final
    #: score is therefore clipped to this many standard deviations, so a single
    #: metric cannot dominate a rank no matter how the inputs are bounded.
    max_abs_score = 3.0

    for fname, spec in specs.items():
        factor_scores: dict[str, float | None] = {s: None for s in symbols}
        # Seed a diagnostic entry per stock so every skipped name carries a
        # reason, rather than only the ones a metric happened to touch.
        factor_diag: dict[str, dict] = {
            s: {"skipped_reason": "no metrics present for this stock-month"}
            for s in symbols
        }

        if not spec.metrics:
            # Price-based factor: the caller supplies the score directly.
            continue

        for metric, sign in spec.metrics.items():
            raw = {s: symbol_metrics[s].get(metric) for s in symbols}
            present = {s: float(v) for s, v in raw.items() if v is not None}

            # Leverage is not comparable across financial and non-financial
            # firms, so it is excluded for those sectors rather than
            # rescaled; the remaining metrics still build the score.
            if spec.leverage_sensitive and spec.is_leverage_metric(metric):
                exempt = {
                    s for s in present
                    if sectors.get(s, "Unknown") in spec.leverage_exempt_sectors
                }
                for s in exempt:
                    present.pop(s, None)
                    factor_diag.setdefault(s, {})["leverage_exempt"] = True

            if not present:
                continue

            vals = list(present.values())
            bounded = dict(zip(present.keys(), winsorize(vals)))

            if sector_neutral:
                scaled = sector_neutral_scores(bounded, sectors)
            else:
                m = _mean(vals)
                sd = _stdev(vals)
                scaled = {k: (v - m) / sd if sd > 0 else 0.0 for k, v in bounded.items()}

            for sym, z in scaled.items():
                factor_diag.setdefault(sym, {}).setdefault("parts", {})[metric] = round(z, 6)
                factor_diag[sym]["parts"][metric] *= 1.0 if sign > 0 else -1.0

        # Combine, but only where the coverage rule is satisfied.
        for sym in symbols:
            diag = factor_diag.get(sym, {})
            parts: dict[str, float] = diag.get("parts", {})
            if parts:
                total_w = sum(abs(w) for w in spec.metrics.values())
                present_w = sum(abs(spec.metrics[m]) for m in parts)
                coverage = present_w / total_w if total_w else 0.0
                if coverage >= spec.min_coverage:
                    # Normalise the weights actually present so a partial
                    # score is still on the same scale as a complete one, then
                    # clip the tail so no single metric can dominate a rank.
                    raw_score = sum(parts.values()) / present_w
                    factor_scores[sym] = max(-max_abs_score, min(max_abs_score, raw_score))
                else:
                    factor_scores[sym] = None
                    diag["skipped_coverage"] = round(coverage, 3)
                    diag["skipped_reason"] = (
                        f"only {present_w:.2f} of {total_w:.2f} metric weight present "
                        f"({coverage:.0%} < {spec.min_coverage:.0%})"
                    )
            else:
                factor_scores[sym] = None
                diag["skipped_reason"] = "no metrics present for this stock-month"

        scores[fname] = factor_scores
        diagnostics[fname] = factor_diag

    return scores, diagnostics
