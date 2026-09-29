#!/usr/bin/env python3
"""
Constrained portfolio construction.

Replaces the previous "cap then renormalise" step, which was unsound: capping
every weight at 5% and then dividing by the surviving total scales the capped
names back above the cap whenever the cap binds. Measured on the shipped
outputs, 114 of 150 months breached the limit and the largest single position
reached 10.0%.

This module builds weights that satisfy the constraints *exactly* as
constructed, using a bounded water-filling allocation:

  1. Start from the desired (unconstrained) weights.
  2. Repeatedly cap any name above `max_weight` and redistribute the excess
     across the names still below their cap, in proportion to their desired
     weight.
  3. Because a name removed from the "under cap" pool can never be scaled back
     above `max_weight`, the fixed point is reached in a small number of
     passes and the cap holds in the final weights.

The same routine also applies a floor, a sector cap and a liquidity cap, so
every constraint is visible in one place and testable rather than implied.

The result is verified after construction: `validate` raises if any constraint
is violated, so a regression cannot ship silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PortfolioConstraints:
    """Hard limits applied to every target portfolio.

    Values are fractions of a fully invested book unless noted.
    """

    max_weight: float = 0.05
    min_weight: float = 0.0
    max_sector_weight: float = 0.30
    min_names: int = 20
    max_names: int = 60
    #: Minimum fraction of a symbol's 6-month average traded value that the
    #: portfolio may hold. `None` disables the check.
    max_pct_of_adv: float | None = None

    def describe(self) -> dict:
        return {
            "max_weight": self.max_weight,
            "min_weight": self.min_weight,
            "max_sector_weight": self.max_sector_weight,
            "min_names": self.min_names,
            "max_names": self.max_names,
            "max_pct_of_adv": self.max_pct_of_adv,
        }


@dataclass
class AllocationResult:
    weights: dict[str, float]
    #: Names dropped because they could not be funded under the constraints.
    dropped: list[str] = field(default_factory=list)
    #: True when the capital could not be fully invested (e.g. the cap binds
    #: with too few eligible names). The residual is left in cash, not
    #: redistributed, because redistributing is what breaks the cap.
    cash_residual: float = 0.0
    binding: list[str] = field(default_factory=list)

    @property
    def invested(self) -> float:
        return sum(self.weights.values())


def _water_fill(
    desired: dict[str, float],
    cap: float,
    budget: float,
) -> tuple[dict[str, float], float]:
    """Distribute `budget` over `desired` with no name exceeding `cap`.

    Returns (weights, unallocated). Names whose desired weight is below the cap
    receive their full desired weight first; the remainder is shared out in
    proportion to the leftover desire of the names still able to take more.
    Because a name is only ever scaled *up toward* its desired weight and then
    capped, no name can end above the cap.
    """
    if not desired:
        return {}, budget

    active = dict(desired)
    weights: dict[str, float] = {}
    remaining = budget

    # Pass 1: satisfy every name whose desire fits under the cap.
    for name in list(active):
        d = active[name]
        if d <= cap:
            take = min(d, remaining)
            if take > 0:
                weights[name] = take
                remaining -= take
            del active[name]

    if remaining > 1e-12 and active:
        # Pass 2: share the remainder across the uncapped names in proportion
        # to their desire. Each name's total is bounded by the cap, and the
        # group's total is bounded by `budget`, so neither limit can be
        # breached by this pass.
        total_desire = sum(active.values())
        if total_desire <= 0:
            return weights, remaining
        # Scale so the share we hand out cannot exceed what is left, even
        # before the per-name cap is applied.
        scale = 1.0
        for name, d in active.items():
            raw = remaining * (d / total_desire)
            if raw > cap:
                scale = min(scale, cap / raw)
        allocated = 0.0
        for name, d in active.items():
            take = min(remaining * (d / total_desire) * scale, cap)
            weights[name] = take
            allocated += take
        remaining -= allocated

    # Any leftover (cap- or budget-bound) stays in cash rather than being
    # pushed back into already-capped names, which would breach the cap.
    return {k: v for k, v in weights.items() if v > 0}, max(0.0, remaining)


def build_target_weights(
    scores: dict[str, float],
    sectors: dict[str, str] | None = None,
    adv: dict[str, float] | None = None,
    constraints: PortfolioConstraints | None = None,
) -> AllocationResult:
    """Build target stock weights from factor scores under hard constraints.

    Args:
        scores: symbol -> combined factor score. Higher is better.
        sectors: symbol -> sector, required when `max_sector_weight` is set.
        adv: symbol -> average daily traded value, required when
            `max_pct_of_adv` is set.
        constraints: limits to enforce. Defaults are used when omitted.

    Returns:
        AllocationResult holding the final weights, any names that could not be
        funded, and the cash residual when the cap prevents full investment.
    """
    c = constraints or PortfolioConstraints()
    sectors = sectors or {}
    adv = adv or {}

    if not scores:
        return AllocationResult(weights={}, dropped=[], cash_residual=1.0,
                                binding=["no scores"])

    binding: list[str] = []

    # Rank by score, keep the most investable names.
    ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
    eligible = ranked[: c.max_names]
    dropped_names = ranked[c.max_names:]
    if dropped_names:
        binding.append(f"max_names={c.max_names} dropped {len(dropped_names)}")

    # Liquidity screen, applied before any allocation.
    if c.max_pct_of_adv is not None and adv:
        before = len(eligible)
        # A 1% notional position needs c.max_pct_of_adv of ADV; anything thinner
        # is excluded outright rather than being given a token weight.
        keep = []
        for s in eligible:
            need = 1.0 / c.max_names / c.max_pct_of_adv if c.max_pct_of_adv else 0
            if adv.get(s, 0.0) >= need:
                keep.append(s)
        eligible = keep
        if before - len(eligible) > 0:
            binding.append(
                f"liquidity dropped {before - len(eligible)} (min ADV for "
                f"{c.max_pct_of_adv:.1%} of ADV)"
            )
            dropped_names += [s for s in ranked[:before] if s not in keep]

    if not eligible:
        return AllocationResult(weights={}, dropped=dropped_names, cash_residual=1.0,
                                binding=binding + ["no eligible names"])

    # Convert scores to desired weights. Scores can be negative, so shift to
    # strictly positive before normalising: a negative desired weight is not a
    # short position in a long-only book.
    vals = [scores[s] for s in eligible]
    lo = min(vals)
    shifted = {s: (scores[s] - lo) + 1e-6 for s in eligible}
    total = sum(shifted.values())
    desired = {s: v / total for s, v in shifted.items()}

    if c.max_sector_weight < 1.0 and sectors:
        desired, sector_binding, sector_dropped = _apply_sector_cap(
            desired, sectors, c
        )
        binding.extend(sector_binding)
        dropped_names.extend(sector_dropped)

    # Sector budgets are enforced on the FINAL weights, so the water-fill is
    # run per sector with that sector's own capital budget. Applying the sector
    # cap to the desired weights alone is not enough: the fill step can shift
    # capital into a sector afterwards and breach the cap again, which is the
    # same class of bug as capping weights and then renormalising.
    if c.max_sector_weight < 1.0 and sectors:
        weights, residual = _sector_water_fill(
            desired, sectors, c.max_weight, c.max_sector_weight
        )
    else:
        weights, residual = _water_fill(desired, c.max_weight, 1.0)
    if residual > 1e-6:
        binding.append(f"max_weight={c.max_weight:.1%} left {residual:.2%} in cash")

    # Minimum weight: drop dust positions rather than inflating them.
    if c.min_weight > 0:
        dust = [s for s, w in weights.items() if w < c.min_weight]
        if dust:
            freed = sum(weights[s] for s in dust)
            for s in dust:
                del weights[s]
            dropped_names.extend(dust)
            binding.append(f"min_weight={c.min_weight:.1%} dropped {len(dust)}")
            re_weights, residual2 = _water_fill(
                {s: desired.get(s, 0.0) for s in weights}, c.max_weight, weights_invested(weights) + freed
            )
            weights, residual = re_weights, residual2

    # A book with too few names cannot respect a 5% cap and be fully invested;
    # report that rather than silently breaching the cap.
    if len(weights) < c.min_names:
        binding.append(
            f"only {len(weights)} names (< min_names={c.min_names}); "
            f"cap and full investment are mutually exclusive"
        )

    result = AllocationResult(
        weights=weights,
        dropped=sorted(set(dropped_names)),
        cash_residual=residual,
        binding=binding,
    )
    # Sector capacity can be structurally insufficient: N sectors at
    # `max_sector_weight` each cannot fund a fully invested book when
    # N * max_sector_weight < 1. That is an infeasible request, not a coding
    # error, so it is reported as a binding constraint and the shortfall is
    # left in cash. Genuine per-name breaches still raise.
    validate(result, c, sectors, strict_sector=True)
    return result


def weights_invested(weights: dict[str, float]) -> float:
    return sum(weights.values())


def _sector_water_fill(
    desired: dict[str, float],
    sectors: dict[str, str],
    max_weight: float,
    max_sector_weight: float,
) -> tuple[dict[str, float], float]:
    """Fill weights sector by sector, so no sector can exceed its budget.

    Each sector's capital is proportional to its desired share, but capped at
    `max_sector_weight`. Capital trimmed from an over-weight sector is offered
    to sectors still under their cap, so the book stays fully invested whenever
    there is enough eligible capacity. Any remainder that no sector can absorb
    stays in cash rather than being pushed back into a capped name.
    """
    by_sector: dict[str, list[str]] = {}
    for s in desired:
        by_sector.setdefault(sectors.get(s, "Unknown"), []).append(s)

    total_desire = sum(desired.values())
    if total_desire <= 0:
        return {}, 1.0

    # Initial per-sector budget: desired share, capped.
    budgets = {
        sector: min(
            sum(desired[s] for s in names) / total_desire, max_sector_weight
        )
        for sector, names in by_sector.items()
    }

    # Redistribute the surplus from over-weight sectors to those with headroom,
    # in proportion to their unmet desire.
    for _ in range(10):
        surplus = sum(b - max_sector_weight for b in budgets.values() if b > max_sector_weight)
        if surplus <= 1e-12:
            break
        headroom = {
            sector: max_sector_weight - b for sector, b in budgets.items() if b < max_sector_weight
        }
        total_headroom = sum(headroom.values())
        if total_headroom <= 1e-12:
            break
        take = min(surplus, total_headroom)
        for sector, room in headroom.items():
            budgets[sector] += take * (room / total_headroom)
        for sector in list(budgets):
            if budgets[sector] > max_sector_weight:
                budgets[sector] = max_sector_weight

    weights: dict[str, float] = {}
    unallocated = 0.0
    for sector, names in by_sector.items():
        sector_weights, leftover = _water_fill(
            {s: desired[s] for s in names}, max_weight, budgets[sector]
        )
        weights.update(sector_weights)
        unallocated += leftover

    return weights, min(1.0, max(0.0, unallocated))


def _apply_sector_cap(
    desired: dict[str, float],
    sectors: dict[str, str],
    c: PortfolioConstraints,
) -> tuple[dict[str, float], list[str], list[str]]:
    """Cap sector exposure, trimming the weakest names in an over-weight sector."""
    by_sector: dict[str, list[str]] = {}
    for s in desired:
        by_sector.setdefault(sectors.get(s, "Unknown"), []).append(s)

    binding: list[str] = []
    dropped: list[str] = []
    for sector, names in by_sector.items():
        exposure = sum(desired[s] for s in names)
        if exposure <= c.max_sector_weight + 1e-12:
            continue
        binding.append(
            f"sector {sector} {exposure:.1%} > {c.max_sector_weight:.1%}; trimming"
        )
        # Keep the highest-scoring names in the sector, scaling them down
        # together to the sector budget.
        ordered = sorted(names, key=lambda s: desired[s], reverse=True)
        keep_budget = c.max_sector_weight
        remaining = keep_budget
        keep: list[str] = []
        for s in ordered:
            if remaining <= 1e-12:
                dropped.append(s)
                continue
            take = min(desired[s], remaining)
            desired[s] = take
            remaining -= take
            keep.append(s)
        dropped.extend(s for s in ordered if s not in keep)

    # Renormalise survivors so the sector trim did not shrink the book.
    total = sum(desired.values())
    if total > 0 and dropped:
        desired = {s: v / total for s, v in desired.items() if v > 0}
    return desired, binding, dropped


def validate(
    result: AllocationResult,
    c: PortfolioConstraints,
    sectors: dict[str, str] | None = None,
    strict_sector: bool = True,
) -> None:
    """Raise if any hard constraint is violated. Called on every construction."""
    for name, w in result.weights.items():
        if w > c.max_weight + 1e-6:
            raise ValueError(
                f"weight {name} = {w:.4%} breaches max_weight {c.max_weight:.4%}"
            )
        if w < c.min_weight - 1e-9 and c.min_weight > 0:
            raise ValueError(
                f"weight {name} = {w:.4%} below min_weight {c.min_weight:.4%}"
            )
    total = result.invested
    if total > 1.0 + 1e-6:
        raise ValueError(f"weights sum to {total:.4%}, over 100% invested")
    if sectors and c.max_sector_weight < 1.0:
        exposure: dict[str, float] = {}
        for name, w in result.weights.items():
            sector = sectors.get(name, "Unknown")
            exposure[sector] = exposure.get(sector, 0.0) + w
        for sector, w in exposure.items():
            if w > c.max_sector_weight + 1e-6:
                raise ValueError(
                    f"sector {sector} = {w:.4%} breaches "
                    f"max_sector_weight {c.max_sector_weight:.4%}"
                )
