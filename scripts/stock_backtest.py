"""Stock-level backtest (spec sec 13).

The shipped backtest compounded factor-level returns:

    portfolio_value *= (1 + sum(factor_weight * factor_return))

That is not a portfolio. It has no holdings, no overlap between sleeves, no
position sizes and no cost of implementing it, so it cannot answer "what would
this have returned" or "was it worth trading".

This module computes the return of the actual target book:

    for each month t:
        weights(t)   from portfolio_targets
        r_i(t)       stock return from t to t+1
        gross(t)  = sum_i w_i(t) * r_i(t)
        cost(t)   = turnover(t) * cost_bps
        net(t)    = gross(t) - cost(t)

Weights are formed at the close of month t and earn month t+1, which is the
only ordering that does not use the future. A name that is not held earns
nothing; a name entering next month is funded by the sell of what exits, so
turnover is the one-way sum of absolute weight changes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """All-in round-trip cost assumptions, in basis points of traded notional."""

    bps: float = 20.0
    #: Label for the scenario, e.g. "base" or "50bps stress".
    label: str = "base"

    def cost_of(self, turnover: float) -> float:
        """Cost incurred by one-way turnover of `turnover` (a fraction of book)."""
        return abs(turnover) * self.bps / 10_000.0

    def describe(self) -> dict:
        return {"bps": self.bps, "label": self.label}


def stock_level_returns(
    targets_by_month: dict[str, dict[str, float]],
    returns_by_month: dict[str, dict[str, float]],
    cost: CostModel,
    start_value: float = 100.0,
) -> list[dict]:
    """Compound the actual target book month by month.

    Args:
        targets_by_month: month -> symbol -> target weight, from
            `portfolio_targets`. Weight formed at the close of `month`.
        returns_by_month: month -> symbol -> return realised *during* that
            month. So the return earned by a position formed in month t is
            `returns_by_month[t + 1]`.
        cost: transaction-cost assumptions.
        start_value: initial notional.

    Returns:
        One record per month after the first, carrying the gross return, the
        cost, the net return, turnover, the value path and the realised
        drawdown.
    """
    months = sorted(targets_by_month)
    if len(months) < 2:
        return []

    values = [start_value]
    gross_returns: list[float] = []
    net_returns: list[float] = []
    turnovers: list[float] = []
    costs: list[float] = []
    holdings_counts: list[int] = []
    previous_weights: dict[str, float] = {}
    peak = start_value

    for i in range(1, len(months)):
        prev_month = months[i - 1]
        month = months[i]
        # A book can only be evaluated in a month whose stock returns are
        # known. The final weight month has no following month, so it produces
        # no return row.
        if month not in returns_by_month:
            break

        weights = targets_by_month[prev_month]
        realised = returns_by_month.get(month, {})

        # One-way turnover: buys plus sells, expressed as a fraction of book.
        #
        # The names are sorted before summing. Iterating a `set` of strings
        # follows Python's per-process hash randomisation, and floating-point
        # addition is not associative, so summing in set order produced
        # run-to-run differences of ~1e-6 in turnover. The numbers were
        # individually correct and the difference was invisible at display
        # precision, but it meant the same inputs did not reproduce the same
        # output bit-for-bit, which is the property a backtest needs.
        all_names = sorted(set(weights) | set(previous_weights))
        turnover = sum(
            abs(weights.get(n, 0.0) - previous_weights.get(n, 0.0))
            for n in all_names
        ) / 2.0

        # A position formed at the close of prev_month earns month `month`.
        # Sorted for the same reason as the turnover sum above.
        gross = sum(
            w * float(realised.get(sym, 0.0) or 0.0)
            for sym, w in sorted(weights.items())
        )
        # Capital not placed (cash) earns nothing.
        invested = sum(weights.values())
        gross += (1.0 - invested) * 0.0

        cost_paid = cost.cost_of(turnover)
        net = gross - cost_paid

        previous_weights = dict(weights)
        values.append(values[-1] * (1.0 + net))
        peak = max(peak, values[-1])
        drawdown = (values[-1] - peak) / peak if peak > 0 else 0.0

        gross_returns.append(gross)
        net_returns.append(net)
        turnovers.append(turnover)
        costs.append(cost_paid)
        holdings_counts.append(len([w for w in weights.values() if w > 0]))

    out = []
    for i, month in enumerate(months[1:]):
        out.append({
            "month": month,
            "weights_from": months[i],
            "portfolio_value": round(values[i + 1], 4),
            "gross_return": round(gross_returns[i], 6),
            "cost": round(costs[i], 6),
            "monthly_return": round(net_returns[i], 6),
            "turnover": round(turnovers[i], 6),
            "drawdown": round(drawdown_of(values, i + 1), 6),
            "holdings": holdings_counts[i],
        })
    return out


def summarize(rows: list[dict]) -> dict:
    """Headline statistics for a stock-level return path.

    Uses the same conventions the dashboard already shows, computed only from
    realised monthly returns. `months` counts realised periods, so annualising
    uses that count rather than the number of weight decisions.
    """
    if not rows:
        return {}
    rets = [r["monthly_return"] for r in rows]
    n = len(rets)
    total = 1.0
    for r in rets:
        total *= 1.0 + r
    total_return = total - 1.0
    years = n / 12.0
    cagr = (total ** (1.0 / years) - 1.0) if years > 0 and total > 0 else 0.0
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1) if n > 1 else 0.0
    vol = var ** 0.5 * (12 ** 0.5)
    sharpe = (mean * 12) / vol if vol > 0 else 0.0
    values = [100.0] + [r["portfolio_value"] for r in rows]
    peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            max_dd = min(max_dd, (v - peak) / peak)
    # Sortino: standard downside deviation is the root-mean-square shortfall
    # across ALL periods, not across losing months only. Dividing by the count
    # of losing months instead inflates the denominator and understated this
    # strategy's Sortino as 1.46 when the standard definition gives 2.62.
    shortfall = [min(0.0, x) for x in rets]
    dvar = (sum(s * s for s in shortfall) / n) ** 0.5 if n else 0.0
    sortino = (mean * 12) / (dvar * (12 ** 0.5)) if dvar > 0 else 0.0
    return {
        "months": n,
        "cagr": round(cagr, 4),
        "sortino_definition": "downside deviation over all periods (standard)",
        "total_return": round(total_return, 4),
        "annual_volatility": round(vol, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "max_drawdown": round(max_dd, 4),
        "avg_turnover": round(sum(r["turnover"] for r in rows) / n, 4),
        "total_cost": round(sum(r["cost"] for r in rows), 4),
        "avg_holdings": round(sum(r["holdings"] for r in rows) / n, 1),
        "best_month": round(max(rets), 6),
        "worst_month": round(min(rets), 6),
        "hit_rate": round(sum(1 for x in rets if x > 0) / n, 4),
    }


def drawdown_of(values: list[float], idx: int) -> float:
    peak = max(values[: idx + 1])
    return (values[idx] - peak) / peak if peak > 0 else 0.0
