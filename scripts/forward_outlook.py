"""Forward outlook (T+1) and out-of-sample scoring of the model's own forecasts.

Every other page in this project is retrospective: it reports what the regime
model said, what weights the optimiser chose, and what the backtest returned.
That leaves the question the dashboard exists to answer -- *what does the model
do next month?* -- unanswered, and it leaves the harder question unanswered
too: *when the model made a forecast, was it right?*

This module does both, and the second half is the part that matters.

## What is forecast, and from what

The forecast is not a separate model. It is the *decision the pipeline already
makes for the next month*, exposed instead of discarded. For a decision month
`T`, using only information available at the close of `T-1`:

  - factor expected returns: the same exponentially-decayed trailing mean the
    optimiser uses (`ER_WINDOW` months, halflife `ER_HALFLIFE`)
  - regime probabilities: the walk-forward GMM posteriors for `T`
  - portfolio volatility: `sqrt(w' cov w)` from the trailing covariance
  - expected turnover: the grid-search weights' distance from `T-1`'s weights
  - expected sector tilt: the target book the weights imply

## Why the scoring half is the point

A panel that prints a number is a display feature. A panel that reports its own
historical accuracy -- including the months it was wrong -- is a validated
forecasting system, and that is the difference between a project that reports
numbers and one that can be held to account.

Scoring is done strictly out of sample: for each month the forecast is rebuilt
from information available *before* that month and compared with what actually
happened. No forecast is ever compared against a period it was trained on, and
the realised outcome is never an input to the forecast.

Reported measures:

  hit rate          share of months where the predicted factor-return sign
                    matched the realised sign
  MAE               mean absolute error per factor sleeve, in monthly return
  information coef. correlation between predicted and realised factor returns,
                    pooled across sleeves; this is the standard measure of
                    whether a signal carries information at all
  calibration       among months assigned a given confidence bucket, the share
                    whose outcome fell on the predicted side. A model that says
                    70% should be right about 70% of the time; a bucket where it
                    is right 95% of the time is over-confident and this reports
                    that rather than hiding it.

Where the sample is too small to support a claim, the measure is reported as
`null` with the count that blocked it. A statistic computed from four
observations is worse than no statistic, because it looks like evidence.
"""

from __future__ import annotations

import math

import numpy as np

FACTORS = ("Momentum", "Value", "Quality", "Low Volatility")
FKEYS = ("momentum", "value", "quality", "low_volatility")

# Minimum observations before a measure is published. Chosen so that a hit
# rate quoted to two decimal places is backed by enough months to be worth
# quoting: below this, a single month moves the figure by more than its own
# reported precision.
MIN_OBS_HIT_RATE = 24
MIN_OBS_CORR = 24
MIN_BUCKET = 8


def _round(x, n=6):
    if x is None:
        return None
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return round(float(x), n)


def _sign(x) -> int:
    if x is None:
        return 0
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def decayed_trailing_mean(series: list[float], window: int, halflife: float) -> float | None:
    """Exponentially-decayed mean of the most recent `window` observations.

    Identical in form to the weighting the allocation optimiser applies, so the
    forecast is the optimiser's own input rather than a second, parallel
    estimator that could disagree with it.
    """
    vals = [float(v) for v in series[-window:] if v is not None]
    if not vals:
        return None
    ages = np.arange(len(vals) - 1, -1, -1, dtype=float)  # 0 = most recent
    decay = 0.5 ** (ages / halflife)
    decay = decay / decay.sum()
    return float(np.dot(decay, vals))


def build_forecast(alloc: dict, regime: dict, diagnostics: dict, target_weights: dict | None = None) -> dict:
    """Assemble the T+1 outlook for one decision month from already-computed state."""
    weights = {
        "Momentum": float(alloc.get("momentum_weight") or 0.0),
        "Value": float(alloc.get("value_weight") or 0.0),
        "Quality": float(alloc.get("quality_weight") or 0.0),
        "Low Volatility": float(alloc.get("low_volatility_weight") or 0.0),
    }

    er = {
        f: alloc.get(f"er_{k}") for f, k in zip(FACTORS, FKEYS)
    }
    er = {f: (None if v is None else float(v)) for f, v in er.items()}

    probs = {}
    for label, key in (
        ("Bull / Expansion", "prob_bull_expansion"),
        ("Bear / Stress", "prob_bear_stress"),
        ("Sideways / Neutral", "prob_sideways_neutral"),
        ("Recovery", "prob_recovery"),
        ("High Volatility / Risk-Off", "prob_high_vol_risk_off"),
    ):
        v = regime.get(key)
        probs[label] = None if v is None else round(float(v), 4)

    exp_risk = alloc.get("expected_risk")
    turnover = alloc.get("turnover")
    news_stress = alloc.get("news_stress_score")

    # A single dominant regime probability is the honest summary of a GMM
    # posterior when the clusters do not separate cleanly. Reporting the top
    # label alone would present a hard call as a certainty the model does not
    # have, so the margin over the runner-up is published alongside it.
    live = {k: v for k, v in probs.items() if v is not None}
    top_label = top_prob = margin = None
    if live:
        ordered = sorted(live.items(), key=lambda kv: -kv[1])
        top_label, top_prob = ordered[0]
        margin = round(ordered[0][1] - ordered[1][1], 4) if len(ordered) > 1 else top_prob

    sector_tilt = None
    if target_weights:
        agg: dict[str, float] = {}
        for sym, w in target_weights.items():
            sec = (w or {}).get("sector") if isinstance(w, dict) else None
            if sec:
                agg[sec] = agg.get(sec, 0.0) + float((w or {}).get("weight") or 0.0)
        if agg:
            sector_tilt = dict(sorted(agg.items(), key=lambda kv: -kv[1])[:8])

    return {
        "month": alloc.get("month"),
        "horizon": "T+1 (next rebalance month)",
        "factor_weights": {k: round(v, 4) for k, v in weights.items()},
        "expected_factor_returns": {f: _round(v) for f, v in er.items()},
        "expected_portfolio_return": _round(alloc.get("expected_return")),
        "expected_volatility": _round(exp_risk),
        "expected_turnover": _round(turnover),
        "regime_probabilities": probs,
        "regime_top_label": top_label,
        "regime_top_probability": _round(top_prob, 4),
        "regime_margin_over_runner_up": margin,
        "news_stress_score": _round(news_stress),
        "decision": alloc.get("decision"),
        "sector_tilt_top": sector_tilt,
        "method": (
            "Expected factor returns are an exponentially-decayed mean of the "
            "trailing factor returns the optimiser itself uses. Nothing here is "
            "fitted to the outcome month."
        ),
    }


def score_forecasts(forecasts: list[dict], realised_by_month: dict[str, dict]) -> dict:
    """Compare each forecast with what actually happened, out of sample.

    `forecasts` must contain only months whose outcome is known; a month with
    no realised return yet is skipped rather than scored against zero, because
    scoring an unobserved month against 0.0 would manufacture error.
    """
    rows = []
    for f in forecasts:
        m = f.get("month")
        if not m:
            continue
        got = realised_by_month.get(m)
        if not got:
            continue
        er = f.get("expected_factor_returns") or {}
        hit = tot = 0
        abs_err = {fct: [] for fct in FACTORS}
        for fct, key in zip(FACTORS, FKEYS):
            pred = er.get(fct)
            act = got.get(f"{key}_return")
            if pred is None or act is None:
                continue
            sp, sa = _sign(pred), _sign(act)
            # A predicted return of exactly 0.0 carries no directional claim,
            # so counting it as a miss would penalise the model for refusing
            # to forecast. It is excluded from the hit-rate denominator.
            if sp == 0:
                continue
            tot += 1
            if sp == sa:
                hit += 1
            abs_err[fct].append(abs(float(pred) - float(act)))
        rows.append({
            "month": m,
            "hit": hit,
            "scored_sleeves": tot,
            "abs_error": {k: (v[-1] if v else None) for k, v in abs_err.items()},
            "predicted": {fct: er.get(fct) for fct in FACTORS},
            "realised": {fct: got.get(f"{key}_return") for fct, key in zip(FACTORS, FKEYS)},
        })

    n = len(rows)
    scored = sum(r["scored_sleeves"] for r in rows)
    hits = sum(r["hit"] for r in rows)

    out = {
        "months_scored": n,
        "sleeve_observations": scored,
        "hit_rate": _round(hits / scored, 4) if scored >= MIN_OBS_HIT_RATE else None,
        "hit_rate_suppressed_below_months": MIN_OBS_HIT_RATE,
        "mae_by_factor": {},
        "information_coefficient": None,
        "calibration": [],
        "by_month": rows,
    }

    for fct in FACTORS:
        errs = [abs(r["abs_error"][fct]) for r in rows if r["abs_error"].get(fct) is not None]
        out["mae_by_factor"][fct] = {
            "mae": _round(float(np.mean(errs)), 6) if len(errs) >= MIN_OBS_HIT_RATE else None,
            "n": len(errs),
        }

    preds, acts = [], []
    for r in rows:
        for fct in FACTORS:
            p = r["predicted"].get(fct)
            a = r["realised"].get(fct)
            if p is None or a is None:
                continue
            preds.append(float(p))
            acts.append(float(a))
    if len(preds) >= MIN_OBS_CORR:
        if np.std(preds) > 0 and np.std(acts) > 0:
            ic = float(np.corrcoef(preds, acts)[0][1])
            out["information_coefficient"] = {
                "value": _round(ic, 4),
                "n": len(preds),
                "note": (
                    "Near zero means the forecast carries no information about "
                    "realised factor returns. That is a result, not a bug, and "
                    "it is reported rather than omitted."
                ),
            }

    # Calibration: bucket by the confidence the model itself published.
    buckets: dict[str, list[int]] = {}
    for f in forecasts:
        m = f.get("month")
        got = realised_by_month.get(m) if m else None
        if not got:
            continue
        conf = f.get("regime_top_probability")
        if conf is None:
            continue
        er = f.get("expected_factor_returns") or {}
        praw = f.get("expected_portfolio_return")
        ract = got.get("portfolio_return")
        if praw is None or ract is None:
            continue
        b = "0.6-0.8" if conf >= 0.6 else ("0.4-0.6" if conf >= 0.4 else "below 0.4")
        buckets.setdefault(b, []).append(1 if _sign(praw) == _sign(ract) else 0)
    for b, vals in sorted(buckets.items()):
        out["calibration"].append({
            "bucket": b,
            "months": len(vals),
            "hit_rate": _round(sum(vals) / len(vals), 4) if len(vals) >= MIN_BUCKET else None,
            "suppressed_below_months": MIN_BUCKET,
        })

    out["interpretation"] = _interpret(out)
    return out


def _interpret(s: dict) -> str:
    parts = []
    if s["hit_rate"] is not None:
        parts.append(
            f"Directional hit rate {s['hit_rate']*100:.1f}% over {s['sleeve_observations']} "
            f"sleeve-months."
        )
    else:
        parts.append(
            f"Hit rate not reported: fewer than {s['hit_rate_suppressed_below_months']} "
            f"scored sleeve-months ({s['sleeve_observations']} so far)."
        )
    ic = s.get("information_coefficient")
    if ic:
        parts.append(f"Information coefficient {ic['value']:+.3f} (n={ic['n']}).")
    else:
        parts.append("Information coefficient not reported: insufficient or zero-variance sample.")
    return " ".join(parts)
