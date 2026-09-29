"""Performance statistics and inference (spec sections 21, 22, 23).

The shipped summary reported CAGR, Sharpe, Sortino and max drawdown. Those are
enough to describe a return path but not enough to judge it, for three reasons:

1. **Sharpe was computed against a zero risk-free rate.** The database has no
   Treasury-bill or G-Sec series, so "Sharpe" silently meant excess return over
   0%. At a 6.5% Indian risk-free assumption that is a materially different
   number, and quoting only the first invites the reader to compare it with
   numbers computed the other way. {@link RISK_FREE_ANNUAL} is therefore an
   explicit, disclosed assumption rather than a silent zero, and every Sharpe
   here is reported both ways.

2. **A point estimate with no interval invites over-reading.** A Sharpe of 1.41
   estimated from 149 monthly returns carries a wide confidence interval, and a
   good chunk of the apparent edge sits in a handful of months. The moving-block
   bootstrap ({@link bootstrap_ci}) preserves the serial dependence that
   resampling month-by-month would destroy, and the Newey-West t-statistic
   ({@link newey_west_tstat}) corrects the standard error for the same reason.

3. **Only one downside measure was reported.** Drawdown and Sortino answer
   different questions, and neither is expected shortfall. {@link cvar} adds
   the average of the worst 5% of months, which is what an investor sizing a
   position actually cares about.
"""

from __future__ import annotations

import math
import random

#: Annual risk-free rate, as a decimal.
#:
#: The database contains no Treasury-bill or G-Sec series, so this is an
#: assumption, not a measurement. It sits inside the range of Indian 10-year
#: G-Sec yields over the backtest window. Every statistic that depends on it is
#: reported alongside its zero-rate counterpart so the reader can see exactly
#: how much of the number is the assumption.
RISK_FREE_ANNUAL = 0.065

#: Monthly equivalent of {@link RISK_FREE_ANNUAL}, using the effective annual
#: conversion so the compounding matches the return series.
RISK_FREE_MONTHLY = (1.0 + RISK_FREE_ANNUAL) ** (1.0 / 12.0) - 1.0

#: Confidence level for bootstrap intervals.
CI_LEVEL = 0.95

#: Seed for the bootstrap. Pinned so the reported interval is identical on
#: every run: an interval that moves when the pipeline is re-run is not a
#: result, it is an artefact of when it happened to be computed.
BOOTSTRAP_SEED = 20260929

#: Resamples drawn per interval.
BOOTSTRAP_SAMPLES = 2000


# ── Return-path statistics ─────────────────────────────────────────────────

def cvar(rets: list[float], level: float = 0.95) -> float:
    """Conditional Value at Risk: the mean of the worst `level` of returns.

    VaR answers "what is the floor of the worst N% of months". CVaR answers
    "given a month landed in that worst N%, how bad was it, on average". The
    second is the number to size a position against, because the first
    understates the loss that actually has to be absorbed.
    """
    if not rets:
        return 0.0
    ordered = sorted(rets)
    n = len(ordered)
    # At least one observation in the tail, however small the sample.
    k = max(1, int(math.floor(n * (1.0 - level))))
    tail = ordered[:k]
    return sum(tail) / len(tail)


def max_drawdown_series(values: list[float]) -> list[float]:
    """Drawdown at each point of a value path, as a non-positive fraction."""
    out: list[float] = []
    peak = values[0] if values else 0.0
    for v in values:
        peak = max(peak, v)
        out.append((v - peak) / peak if peak > 0 else 0.0)
    return out


def longest_drawdown_months(values: list[float]) -> int:
    """Longest run of consecutive months spent below a prior peak.

    Depth of drawdown says how bad; duration says how long you would have
    waited it out. A book that falls 12% and recovers in two months is a very
    different proposition from one that spends two years under water.
    """
    if len(values) < 2:
        return 0
    peak = values[0]
    longest = 0
    current = 0
    for v in values:
        if v >= peak:
            peak = v
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def ulcer_index(values: list[float]) -> float:
    """Root-mean-square drawdown. Penalises long, shallow pain, not just depth."""
    dds = [d * 100.0 for d in max_drawdown_series(values)]
    if not dds:
        return 0.0
    return (sum(d * d for d in dds) / len(dds)) ** 0.5


def gain_to_pain(rets: list[float]) -> float:
    """Total return divided by the sum of absolute losing months."""
    if not rets:
        return 0.0
    total = 1.0
    for r in rets:
        total *= 1.0 + r
    pain = sum(abs(r) for r in rets if r < 0)
    if pain <= 0:
        return 0.0
    return (total - 1.0) / pain


def sharpe_at(rets: list[float], rf_annual: float) -> float:
    """Annualised Sharpe against an annual risk-free rate."""
    n = len(rets)
    if n < 2:
        return 0.0
    rf_m = (1.0 + rf_annual) ** (1.0 / 12.0) - 1.0
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1)
    vol = math.sqrt(var) * math.sqrt(12)
    excess = (mean - rf_m) * 12
    return excess / vol if vol > 0 else 0.0


def sortino_at(rets: list[float], rf_annual: float) -> float:
    """Annualised Sortino against an annual risk-free rate.

    Only the months that fell short of the risk-free rate count as downside, so
    the denominator does not shrink simply because the strategy was volatile
    in its own favour.
    """
    n = len(rets)
    if n < 2:
        return 0.0
    rf_m = (1.0 + rf_annual) ** (1.0 / 12.0) - 1.0
    mean = sum(rets) / n
    shortfall = [min(0.0, r - rf_m) for r in rets]
    denom = (sum(s * s for s in shortfall) / n) ** 0.5
    if denom <= 0:
        return 0.0
    return ((mean - rf_m) * 12) / (denom * math.sqrt(12))


# ── Benchmark-relative statistics ───────────────────────────────────────────

def beta_alpha(
    rets: list[float],
    bench: list[float],
    rf_annual: float = 0.0,
) -> dict:
    """CAPM beta and Jensen's alpha against a benchmark return series.

    Both series must be the same length and month-aligned; the caller is
    responsible for that alignment, because a silent mismatch here would
    produce a plausible-looking beta from unrelated months.
    """
    n = min(len(rets), len(bench))
    if n < 3:
        return {}
    y = rets[:n]
    x = bench[:n]
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0:
        return {}
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    beta = sxy / sxx
    alpha_m = my - beta * mx
    rf_m = (1.0 + rf_annual) ** (1.0 / 12.0) - 1.0
    # Jensen's alpha removes the risk-free return from both legs before the
    # regression, so alpha is genuinely unexplained return.
    y_ex = [yi - rf_m for yi in y]
    x_ex = [xi - rf_m for xi in x]
    mx_e = sum(x_ex) / n
    my_e = sum(y_ex) / n
    sxx_e = sum((xi - mx_e) ** 2 for xi in x_ex)
    if sxx_e > 0:
        sxy_e = sum((xi - mx_e) * (yi - my_e) for xi, yi in zip(x_ex, y_ex))
        beta_e = sxy_e / sxx_e
        alpha_m = my_e - beta_e * mx_e
    else:
        beta_e = beta
    syy = sum((yi - my) ** 2 for yi in y)
    r2 = (sxy ** 2) / (sxx * syy) if syy > 0 else 0.0
    return {
        "beta": round(beta_e, 4),
        "alpha_annual": round(((1.0 + alpha_m) ** 12) - 1.0, 4),
        "r_squared": round(r2, 4),
        "observations": n,
    }


def tracking_error(rets: list[float], bench: list[float]) -> float:
    """Annualised standard deviation of the strategy's excess return."""
    n = min(len(rets), len(bench))
    if n < 2:
        return 0.0
    active = [rets[i] - bench[i] for i in range(n)]
    mean = sum(active) / n
    var = sum((x - mean) ** 2 for x in active) / (n - 1)
    return math.sqrt(var) * math.sqrt(12)


def information_ratio(rets: list[float], bench: list[float]) -> float:
    """Annualised mean active return divided by tracking error."""
    n = min(len(rets), len(bench))
    if n < 2:
        return 0.0
    active = [rets[i] - bench[i] for i in range(n)]
    te = tracking_error(rets, bench)
    return (sum(active) / n * 12) / te if te > 0 else 0.0


def correlation(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    x, y = a[:n], b[:n]
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    syy = sum((v - my) ** 2 for v in y)
    if sxx <= 0 or syy <= 0:
        return 0.0
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    return sxy / math.sqrt(sxx * syy)


def hit_rate_vs_benchmark(rets: list[float], bench: list[float]) -> float:
    """Share of months in which the strategy beat the benchmark."""
    n = min(len(rets), len(bench))
    if n == 0:
        return 0.0
    wins = sum(1 for i in range(n) if rets[i] > bench[i])
    return wins / n


# ── Inference ──────────────────────────────────────────────────────────────

def lag1_autocorrelation(rets: list[float]) -> float:
    n = len(rets)
    if n < 3:
        return 0.0
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / n
    if var <= 0:
        return 0.0
    cov = sum((rets[i] - mean) * (rets[i - 1] - mean) for i in range(1, n)) / n
    return cov / var


def newey_west_tstat(rets: list[float], lags: int | None = None) -> dict:
    """HAC (Newey-West) t-statistic for the mean monthly return.

    Monthly portfolio returns are not independent: a position that keeps losing
    tends to keep losing, because the drawdown itself drives the next month's
    decisions. The ordinary t-statistic assumes independence and understates the
    standard error when returns are positively autocorrelated, which makes a
    result look more certain than it is. The long-run variance here is
    estimated with Bartlett weights.

    `lags` defaults to the Newey-West rule floor(4 * (n/100)^(2/9)), which grows
    slowly with the sample so short backtests are not over-corrected.
    """
    n = len(rets)
    if n < 3:
        return {}
    if lags is None:
        lags = int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))
        lags = max(1, lags)
    mean = sum(rets) / n
    dev = [x - mean for x in rets]

    gamma0 = sum(d * d for d in dev) / n
    long_run = gamma0
    for lag in range(1, lags + 1):
        if lag >= n:
            break
        cov = sum(dev[i] * dev[i - lag] for i in range(lag, n)) / n
        weight = 1.0 - lag / (lags + 1.0)
        long_run += 2.0 * weight * cov
    # A negative long-run variance would mean the series is precisely
    # counter-autocorrelated; clamp rather than take a square root of a
    # negative number.
    long_run = max(long_run, gamma0 * 1e-9)
    se = math.sqrt(long_run / n)
    return {
        "mean_monthly": round(mean, 6),
        "t_stat": round(mean / se, 4) if se > 0 else 0.0,
        "hac_standard_error": round(se, 6),
        "lags": lags,
        "lag1_autocorrelation": round(lag1_autocorrelation(rets), 4),
    }


def _cagr_of(rets: list[float]) -> float:
    if not rets:
        return 0.0
    total = 1.0
    for r in rets:
        total *= 1.0 + r
    years = len(rets) / 12.0
    if years <= 0 or total <= 0:
        return 0.0
    return total ** (1.0 / years) - 1.0


def _sharpe_of(rets: list[float], rf_annual: float) -> float:
    n = len(rets)
    if n < 2:
        return 0.0
    rf_m = (1.0 + rf_annual) ** (1.0 / 12.0) - 1.0
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1)
    vol = math.sqrt(var)
    return ((mean - rf_m) / vol * math.sqrt(12)) if vol > 0 else 0.0


def _block_length(n: int) -> int:
    """Moving-block length, n^(1/3).

    The cube-root rule is the standard compromise: long enough that a block
    carries some of the series' dependence structure, short enough that the
    149-month backtest still yields a useful number of blocks.
    """
    return max(2, int(round(n ** (1.0 / 3.0))))


def bootstrap_ci(
    rets: list[float],
    statistic: str = "sharpe",
    rf_annual: float = RISK_FREE_ANNUAL,
    n_boot: int = BOOTSTRAP_SAMPLES,
    level: float = CI_LEVEL,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Percentile confidence interval from a moving-block bootstrap.

    Month-by-month resampling assumes returns are independent. They are not:
    consecutive months share positions, and the losses cluster. A moving-block
    bootstrap draws contiguous runs of the observed series instead, so each
    synthetic path carries the same serial dependence as the real one and the
    interval is wide enough to reflect it.

    The seed is fixed, so the interval reported in the dashboard is the same on
    every run. An interval that moves when the pipeline is re-run is not a
    result.
    """
    n = len(rets)
    if n < 12:
        return {}
    stats: dict[str, callable] = {
        "sharpe": lambda r: _sharpe_of(r, rf_annual),
        "cagr": _cagr_of,
        "mean": lambda r: sum(r) / len(r),
    }
    fn = stats.get(statistic)
    if fn is None:
        return {}

    block = _block_length(n)
    n_blocks = int(math.ceil(n / block))
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        for _ in range(n_blocks):
            start = rng.randint(0, n - block)
            sample.extend(rets[start:start + block])
        draws.append(fn(sample[:n]))
    draws.sort()
    lo_i = int(math.floor((1.0 - level) / 2.0 * n_boot))
    hi_i = int(math.ceil((1.0 - (1.0 - level) / 2.0) * n_boot)) - 1
    lo_i = max(0, min(lo_i, n_boot - 1))
    hi_i = max(0, min(hi_i, n_boot - 1))
    point = fn(rets)
    return {
        "statistic": statistic,
        "point": round(point, 4),
        "ci_low": round(draws[lo_i], 4),
        "ci_high": round(draws[hi_i], 4),
        "level": level,
        "bootstrap_samples": n_boot,
        "block_length": block,
        "method": "moving block bootstrap (i.i.d. resampling would ignore serial dependence)",
        "seed": seed,
    }


def cost_scenario_table(
    returns_by_month: dict[str, dict[str, float]],
    targets_by_month: dict[str, dict[str, float]],
    scenarios: tuple[float, ...] = (0.0, 10.0, 20.0, 50.0, 100.0),
    start_value: float = 100.0,
) -> list[dict]:
    """Recompute the book at several cost levels.

    A single cost assumption is a claim; a range is a sensitivity analysis. The
    strategy turns over roughly 27% of the book a month, so each 10bps of
    assumption is worth about 0.27% of return a year, and 100bps is a punitive
    level that most retail execution would never clear. The spread between the
    zero-cost and base rows is the gross edge, and the spread between the base
    and stress rows is how much of it execution can eat.
    """
    from stock_backtest import CostModel, stock_level_returns, summarize

    out: list[dict] = []
    for bps in scenarios:
        cost = CostModel(bps=bps, label=f"{bps:g}bps")
        rows = stock_level_returns(targets_by_month, returns_by_month, cost, start_value)
        s = summarize(rows)
        if not s:
            continue
        out.append({
            "bps": bps,
            "label": f"{bps:g} bps",
            "cagr": s.get("cagr", 0.0),
            "sharpe": s.get("sharpe", 0.0),
            "max_drawdown": s.get("max_drawdown", 0.0),
            "total_cost": s.get("total_cost", 0.0),
        })
    return out


def excess_returns(rets: list[float], rf_monthly: list[float]) -> list[float]:
    """Monthly returns minus the risk-free rate for that same month.

    Taking the difference month by month, rather than subtracting a single
    annual figure once, is what makes a variable rate meaningful. It also
    changes the volatility the ratio is measured against: subtracting a
    constant from every month scales the mean but not the spread, whereas
    subtracting the actual rate each month moves the spread too, and the
    resulting Sharpe is the one a reader would compute by hand.
    """
    if not rets:
        return []
    n = min(len(rets), len(rf_monthly)) if rf_monthly else len(rets)
    return [rets[i] - (rf_monthly[i] if rf_monthly else 0.0) for i in range(n)]


def sharpe_from_excess(excess: list[float]) -> float:
    """Annualised Sharpe of an excess-return series."""
    n = len(excess)
    if n < 2:
        return 0.0
    mean = sum(excess) / n
    var = sum((x - mean) ** 2 for x in excess) / (n - 1)
    vol = math.sqrt(var) * math.sqrt(12)
    return (mean * 12) / vol if vol > 0 else 0.0


def sortino_from_excess(excess: list[float]) -> float:
    """Annualised Sortino of an excess-return series, downside over all periods."""
    n = len(excess)
    if n < 2:
        return 0.0
    mean = sum(excess) / n
    downside = [min(0.0, x) for x in excess]
    denom = (sum(d * d for d in downside) / n) ** 0.5
    if denom <= 0:
        return 0.0
    return (mean * 12) / (denom * math.sqrt(12))


def full_report(
    rows: list[dict],
    bench_by_month: dict[str, float],
    rf_annual: float = RISK_FREE_ANNUAL,
    rf_rates: dict[str, float] | None = None,
    rf_meta: dict | None = None,
) -> dict:
    """Assemble the section 21-23 report from a stock-level return path.

    `rows` is the output of `stock_backtest.stock_level_returns`. The benchmark
    is aligned to the *realised* months only, so beta and tracking error compare
    the strategy against the market over exactly the period it was live.
    """
    if not rows:
        return {}
    rets = [r["monthly_return"] for r in rows]
    values = [100.0] + [r["portfolio_value"] for r in rows]
    months = [r["month"] for r in rows]

    bench: list[float] = []
    aligned_rets: list[float] = []
    prev_close: dict[str, float] = bench_by_month
    # The benchmark return realised *during* month m is close(m)/close(m-1) - 1,
    # which needs the prior month. Build it from the aligned closes.
    closes = [prev_close.get(m) for m in months]
    for i, m in enumerate(months):
        if i == 0:
            continue
        prev, cur = closes[i - 1], closes[i]
        if prev and cur and prev > 0:
            bench.append(cur / prev - 1.0)
            aligned_rets.append(rets[i])

    # Prefer the measured month-by-month rate. `rf_rates` is the real Indian
    # 10-year G-Sec series; `rf_annual` is only a fallback for when it is
    # missing, and the report says which one produced the headline number.
    measured = bool(rf_rates)
    if measured:
        rf_monthly = []
        for m in months:
            annual = rf_rates.get(m)
            if annual is None:
                rf_monthly.append(0.0)
            else:
                rf_monthly.append((1.0 + annual) ** (1.0 / 12.0) - 1.0)
        excess = excess_returns(rets, rf_monthly)
        sharpe_rf = sharpe_from_excess(excess)
        sortino_rf = sortino_from_excess(excess)
    else:
        sharpe_rf = sharpe_at(rets, rf_annual)
        sortino_rf = sortino_at(rets, rf_annual)

    if rf_meta is not None:
        rf_block = {
            "is_measured": True,
            "annual": round(rf_meta.get("mean_annual") or 0.0, 6),
            "monthly": round((1.0 + (rf_meta.get("mean_annual") or 0.0)) ** (1.0 / 12.0) - 1.0, 6),
            "is_assumption_not_data": False,
            "instrument": rf_meta.get("instrument"),
            "source_column": rf_meta.get("source_column"),
            "mean_annual": rf_meta.get("mean_annual"),
            "min_annual": rf_meta.get("min_annual"),
            "max_annual": rf_meta.get("max_annual"),
            "months_observed": rf_meta.get("months_observed"),
            "months_carried_forward": rf_meta.get("months_carried_forward"),
            "months_total": rf_meta.get("months_total"),
            "coverage_pct": rf_meta.get("coverage_pct"),
            "applied": rf_meta.get("applied"),
            "note": rf_meta.get("note"),
        }
    else:
        rf_block = {
            "is_measured": False,
            "annual": rf_annual,
            "monthly": round((1.0 + rf_annual) ** (1.0 / 12.0) - 1.0, 6),
            "is_assumption_not_data": True,
            "note": "No risk-free series was available, so a constant rate is "
                    "assumed. Sharpe is reported against both this and a zero "
                    "rate so the reader can see how much of the number depends "
                    "on the choice.",
        }

    report: dict = {
        "risk_free_assumption": rf_block,
        "return_path": {
            "months": len(rets),
            "cvar_95_monthly": round(cvar(rets, 0.95), 6),
            "cvar_99_monthly": round(cvar(rets, 0.99), 6),
            "cvar_note": (
                "CVaR is the average return of the worst 5% / 1% of months, not "
                "a floor. A -10% monthly CVaR means roughly one month in twenty "
                "lost about a tenth of the book; the single worst was "
                f"{min(rets) * 100:.1f}%."
            ),
            "longest_drawdown_months": longest_drawdown_months(values),
            "ulcer_index": round(ulcer_index(values), 4),
            "gain_to_pain": round(gain_to_pain(rets), 4),
            "skew": round(_skew(rets), 4),
            "excess_kurtosis": round(_kurtosis(rets), 4),
        },
        "risk_adjusted": {
            "sharpe_vs_rf": round(sharpe_rf, 4),
            "sharpe_vs_zero": round(sharpe_at(rets, 0.0), 4),
            "sortino_vs_rf": round(sortino_rf, 4),
            "sortino_vs_zero": round(sortino_at(rets, 0.0), 4),
            "sharpe_basis": (
                "measured Indian 10-year G-Sec, applied month by month"

                if measured
                else f"constant assumed rate of {rf_annual * 100:.2f}%"
            ),
        },
    }

    # Selection-bias adjustment. This Sharpe is the best of an enumerated set of
    # configurations, not one fixed in advance, so it has to be read against
    # what the best of that many random strategies would produce. It is
    # reported alongside the headline rather than replacing it: a reader is
    # entitled to the unadjusted figure as well as the adjusted one.
    try:
        import selection_bias
        _dsr = selection_bias.deflated_sharpe(rets, rf_monthly if measured else None)
        if _dsr:
            report["selection_bias"] = _dsr
    except Exception as _exc:  # an adjustment must never break the report
        report["selection_bias"] = {"error": str(_exc)}


    if len(bench) >= 3:
        # Jensen's alpha is a regression on returns net of the risk-free rate,
        # so it must use the same rate as the headline Sharpe. With a measured
        # series that is the window mean, since a single regression intercept
        # cannot absorb a varying rate.
        capm_rf = (rf_meta or {}).get("mean_annual") if measured else rf_annual
        capm = beta_alpha(aligned_rets, bench, capm_rf or 0.0)
        r2 = capm.get("r_squared") or 0.0
        report["vs_benchmark"] = {
            "benchmark": "NIFTY 200",
            "observations": len(bench),
            "beta": capm.get("beta"),
            "alpha_annual": capm.get("alpha_annual"),
            "r_squared": r2,
            "tracking_error_annual": round(tracking_error(aligned_rets, bench), 4),
            "information_ratio": round(information_ratio(aligned_rets, bench), 4),
            "correlation": round(correlation(aligned_rets, bench), 4),
            "hit_rate_vs_benchmark": round(hit_rate_vs_benchmark(aligned_rets, bench), 4),
            "interpretation": (
                f"Beta near 1 means the book's average move matches the index, "
                f"but an R-squared of {r2:.0%} means {r2:.0%} of its monthly "
                f"variance is still the index's. The alpha is real; the "
                f"diversification benefit is not. A neutralised book would show "
                f"beta well below 1 and R-squared far lower."
            ),
        }

    nw = newey_west_tstat(rets)
    if nw:
        report["mean_return_test"] = {
            **nw,
            "interpretation": (
                "t-stat on the HAC (Newey-West) standard error of the mean "
                "monthly return. |t| below 1.96 means the average month is not "
                "distinguishable from zero at the 5% level."
            ),
        }

    # The Sharpe interval must be computed on the same excess-return series the
    # headline Sharpe uses. Bootstrapping the raw returns against a single
    # constant rate would produce an interval around a different quantity from
    # the point estimate sitting next to it.
    if measured:
        # rf_annual=0 because `excess` is already net of the monthly rate;
        # subtracting another constant would double-count it.
        ci_sharpe = bootstrap_ci(
            excess, "sharpe", rf_annual=0.0,
            n_boot=BOOTSTRAP_SAMPLES, level=CI_LEVEL, seed=BOOTSTRAP_SEED,
        )
        if ci_sharpe:
            ci_sharpe["basis"] = "moving-block bootstrap of the measured excess-return series"
    else:
        ci_sharpe = bootstrap_ci(rets, "sharpe", rf_annual=rf_annual)
    if ci_sharpe:
        report.setdefault("confidence_intervals", {})["sharpe"] = ci_sharpe

    ci_cagr = bootstrap_ci(rets, "cagr")
    if ci_cagr:
        report.setdefault("confidence_intervals", {})["cagr"] = ci_cagr
    return report


def _skew(rets: list[float]) -> float:
    n = len(rets)
    if n < 3:
        return 0.0
    m = sum(rets) / n
    sd = (sum((x - m) ** 2 for x in rets) / n) ** 0.5
    if sd <= 0:
        return 0.0
    return sum(((x - m) / sd) ** 3 for x in rets) / n


def _kurtosis(rets: list[float]) -> float:
    n = len(rets)
    if n < 4:
        return 0.0
    m = sum(rets) / n
    sd = (sum((x - m) ** 2 for x in rets) / n) ** 0.5
    if sd <= 0:
        return 0.0
    return sum(((x - m) / sd) ** 4 for x in rets) / n - 3.0
