import { Card, Table, StatCard } from "@/components/UI";
import {
  getPerformanceReport,
  getCostScenarios,
  getConstraintCompliance,
  formatPercent,
  formatNumber,
} from "@/lib/data";

/**
 * Statistical reliability of the stock-level backtest.
 *
 * The headline CAGR and Sharpe on the Backtest page are point estimates from
 * 149 monthly returns. On their own they invite over-reading: a Sharpe of 1.41
 * looks decisive until you notice that a 6.5% risk-free assumption takes it to
 * 1.07, and that the bootstrap interval around it runs from 0.44 to 1.80.
 *
 * Nothing here changes the strategy. All of it changes how confidently the
 * numbers above can be quoted, which is the difference between a research
 * result and a sales pitch.
 */
export function BacktestReliability() {
  const report = getPerformanceReport();
  const costs = getCostScenarios();
  const constraints = getConstraintCompliance();

  if (!report) {
    return (
      <Card
        title="Statistical Reliability"
        subtitle="Not available in this pipeline output"
      >
        <p className="text-sm text-slate-500">
          This build of the dashboard was generated before the performance
          report was added. Re-run <code>python scripts/run_pipeline.py</code>{" "}
          to populate risk-adjusted metrics, benchmark-relative statistics and
          bootstrap confidence intervals.
        </p>
      </Card>
    );
  }

  const { risk_free_assumption: rf, return_path: rp, risk_adjusted: ra } =
    report;
  const vb = report.vs_benchmark;
  const mt = report.mean_return_test;
  const ci = report.confidence_intervals ?? {};
  const sharpeCI = ci.sharpe;
  const cagrCI = ci.cagr;

  // A Newey-West t below 1.96 means the average month is not distinguishable
  // from zero. Stating the threshold next to the number keeps the reader from
  // having to remember it.
  const tSignificant = Math.abs(mt.t_stat) >= 1.96;

  return (
    <div className="space-y-4">
      {/* The assumption that moves the headline number. */}
      <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
        <h3 className="text-sm font-semibold text-amber-900">
          Sharpe depends on a rate this dataset does not contain
        </h3>
        <p className="text-xs text-amber-800 mt-1.5 leading-relaxed">
          {rf.note}
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          <StatCard
            label="Sharpe (vs 0% rf)"
            value={formatNumber(ra.sharpe_vs_zero)}
            subvalue="the convention used above"
            color="slate"
          />
          <StatCard
            label={`Sharpe (vs ${(rf.annual * 100).toFixed(1)}% rf)`}
            value={formatNumber(ra.sharpe_vs_rf)}
            subvalue="the more conservative reading"
            color="amber"
          />
          <StatCard
            label="Sortino (vs 0% rf)"
            value={formatNumber(ra.sortino_vs_zero)}
            subvalue="standard downside deviation"
            color="slate"
          />
          <StatCard
            label={`Sortino (vs ${(rf.annual * 100).toFixed(1)}% rf)`}
            value={formatNumber(ra.sortino_vs_rf)}
            subvalue="all periods, shortfalls only"
            color="amber"
          />
        </div>
      </div>

      {/* Does the average month beat zero, once autocorrelation is allowed? */}
      <Card
        title="Is the average month distinguishable from zero?"
        subtitle="Newey-West HAC t-statistic on the mean monthly return"
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            label="HAC t-statistic"
            value={formatNumber(mt.t_stat)}
            subvalue={tSignificant ? "above the 1.96 threshold" : "below 1.96 — not significant"}
            color={tSignificant ? "green" : "red"}
          />
          <StatCard
            label="Mean monthly"
            value={formatPercent(mt.mean_monthly)}
            subvalue="arithmetic, not compounded"
            color="slate"
          />
          <StatCard
            label="Lag-1 autocorrelation"
            value={mt.lag1_autocorrelation.toFixed(2)}
            subvalue="positive: losses cluster"
            color={mt.lag1_autocorrelation > 0.1 ? "amber" : "slate"}
          />
          <StatCard
            label="HAC lags"
            value={String(mt.lags)}
            subvalue="Newey-West automatic bandwidth"
            color="slate"
          />
        </div>
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">
          {mt.interpretation} Monthly portfolio returns are not independent: a
          drawdown drives the following month&apos;s decisions, so the ordinary
          t-statistic understates the standard error. A lag-1 autocorrelation
          of {mt.lag1_autocorrelation.toFixed(2)} is mild but real, and the
          correction widens the interval rather than flattering it.
        </p>
      </Card>

      {/* Confidence intervals: the number that should temper the headline. */}
      <Card
        title="Confidence intervals on the headline numbers"
        subtitle="Moving-block bootstrap, 2,000 resamples, fixed seed"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-slate-200 p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              CAGR — 95% interval
            </p>
            {cagrCI ? (
              <>
                <p className="text-2xl font-bold text-slate-900 mt-1">
                  {formatPercent(cagrCI.ci_low)} to {formatPercent(cagrCI.ci_high)}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Point estimate {formatPercent(cagrCI.point)} over{" "}
                  {rp.months} months. The interval is roughly 30 points wide
                  because a single backtest cannot pin down a growth rate more
                  precisely than that.
                </p>
              </>
            ) : (
              <p className="text-sm text-slate-500 mt-1">Not computed.</p>
            )}
          </div>
          <div className="rounded-lg border border-slate-200 p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Sharpe — 95% interval
            </p>
            {sharpeCI ? (
              <>
                <p className="text-2xl font-bold text-slate-900 mt-1">
                  {formatNumber(sharpeCI.ci_low)} to {formatNumber(sharpeCI.ci_high)}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Point estimate {formatNumber(sharpeCI.point)} against the{" "}
                  {(rf.annual * 100).toFixed(1)}% rate. The lower bound stays
                  positive, which is the strongest claim this backtest supports;
                  the upper bound is well below the headline number, which is the
                  honest one.
                </p>
              </>
            ) : (
              <p className="text-sm text-slate-500 mt-1">Not computed.</p>
            )}
          </div>
        </div>
        {sharpeCI && (
          <p className="text-xs text-slate-500 mt-3 leading-relaxed">
            {sharpeCI.method}. Block length {sharpeCI.block_length} months,{" "}
            {sharpeCI.bootstrap_samples.toLocaleString()} resamples, seed{" "}
            {sharpeCI.seed} — fixed so the interval is identical on every run.
            An interval that moved when the pipeline re-ran would not be a
            result.
          </p>
        )}
      </Card>

      {/* What the book actually is, relative to the index. */}
      <Card
        title={`Against ${vb.benchmark}`}
        subtitle={`Aligned to the ${vb.observations} months the stock-level book was actually live`}
      >
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard label="Beta" value={formatNumber(vb.beta)} color="blue" />
          <StatCard
            label="Alpha (annual)"
            value={formatPercent(vb.alpha_annual)}
            subvalue="Jensen's, vs the same rf"
            color="green"
          />
          <StatCard
            label="Information ratio"
            value={formatNumber(vb.information_ratio)}
            subvalue="active return / tracking error"
            color="green"
          />
          <StatCard
            label="Tracking error"
            value={formatPercent(vb.tracking_error_annual)}
            subvalue="annualised"
            color="slate"
          />
          <StatCard
            label="R² vs index"
            value={formatPercent(vb.r_squared)}
            subvalue="variance shared with the market"
            color="amber"
          />
          <StatCard
            label="Beat the index"
            value={formatPercent(vb.hit_rate_vs_benchmark)}
            subvalue="of months"
            color="blue"
          />
        </div>
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">
          {vb.interpretation}
        </p>
      </Card>

      {/* The tail, which a mean and a Sharpe both hide. */}
      <Card
        title="Downside, beyond max drawdown"
        subtitle="What the average and the Sharpe ratio do not describe"
      >
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard
            label="CVaR 95%"
            value={formatPercent(rp.cvar_95_monthly)}
            subvalue="average of the worst 1 month in 20"
            color="red"
          />
          <StatCard
            label="CVaR 99%"
            value={formatPercent(rp.cvar_99_monthly)}
            subvalue="average of the worst 1 in 100"
            color="red"
          />
          <StatCard
            label="Longest drawdown"
            value={`${rp.longest_drawdown_months} mo`}
            subvalue="consecutive months under water"
            color="amber"
          />
          <StatCard
            label="Ulcer index"
            value={formatNumber(rp.ulcer_index)}
            subvalue="RMS drawdown, penalises duration"
            color="slate"
          />
          <StatCard
            label="Skew"
            value={rp.skew.toFixed(2)}
            subvalue="negative: the left tail is the long one"
            color={rp.skew < 0 ? "amber" : "slate"}
          />
          <StatCard
            label="Excess kurtosis"
            value={rp.excess_kurtosis.toFixed(2)}
            subvalue="fat tails"
            color={rp.excess_kurtosis > 1 ? "amber" : "slate"}
          />
        </div>
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">
          {rp.cvar_note} Max drawdown of the kind reported elsewhere answers a
          different question: it is the worst peak-to-trough path, while CVaR is
          the typical bad month. {rp.longest_drawdown_months} consecutive months
          below a prior peak is the number to hold in mind before committing
          capital, because it describes how long the position had to be carried
          through its worst stretch.
        </p>
      </Card>

      {/* Cost sensitivity. */}
      {costs && (
        <Card
          title="Cost sensitivity"
          subtitle="The book re-run end to end at each turnover cost"
        >
          <Table
            columns={[
              { key: "label", label: "Round-trip cost" },
              { key: "cagr", label: "CAGR", align: "right" },
              { key: "sharpe", label: "Sharpe", align: "right" },
              {
                key: "max_drawdown",
                label: "Max DD",
                align: "right",
              },
              {
                key: "total_cost",
                label: "Cumulative cost",
                align: "right",
              },
            ]}
            data={costs.scenarios.map((s) => ({
              label: (
                <span className={s.bps === costs.base_bps ? "font-semibold" : ""}>
                  {s.label}
                  {s.bps === costs.base_bps && (
                    <span className="ml-2 text-xs text-slate-400">base</span>
                  )}
                </span>
              ),
              cagr: formatPercent(s.cagr),
              sharpe: formatNumber(s.sharpe),
              max_drawdown: formatPercent(s.max_drawdown),
              total_cost: formatPercent(s.total_cost),
            }))}
          />
          <p className="text-xs text-slate-500 mt-3 leading-relaxed">
            {costs.interpretation} Across the full range the CAGR moves from{" "}
            {formatPercent(costs.gross_cagr ?? 0)} at zero cost to{" "}
            {formatPercent(costs.stress_cagr)} at {costs.stress_bps} bps — a loss
            of {costs.cagr_lost_to_costs_pct?.toFixed(2)} points, so the result
            is not an artefact of a favourable cost assumption.
          </p>
        </Card>
      )}

      {/* Constraint compliance, as a reported fact. */}
      {constraints &&
        (() => {
          const months = Object.values(constraints.months);
          const c = constraints.constraints;
          const worstPos = months.reduce(
            (a, m) => Math.max(a, m.max_weight),
            0,
          );
          const worstSector = months.reduce(
            (a, m) => Math.max(a, m.max_sector_weight),
            0,
          );
          const breachMonths = months.filter(
            (m) => !m.sector_cap_respected,
          ).length;
          const avgPositions =
            months.reduce((a, m) => a + m.positions, 0) /
            Math.max(1, months.length);
          const maxCash = months.reduce((a, m) => Math.max(a, m.cash), 0);
          return (
            <Card
              title="Position limit compliance"
              subtitle={`Checked every rebalance — ${months.length} months, reported whether it passed or failed`}
            >
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <StatCard
                  label="Months checked"
                  value={String(months.length)}
                  color="slate"
                />
                <StatCard
                  label="Over the 5% cap"
                  value={String(constraints.months_breaching_max_weight)}
                  subvalue={`limit ${formatPercent(c.max_weight)}`}
                  color={
                    constraints.months_breaching_max_weight > 0 ? "red" : "green"
                  }
                />
                <StatCard
                  label="Largest position"
                  value={formatPercent(worstPos)}
                  subvalue="worst month"
                  color="blue"
                />
                <StatCard
                  label="Largest sector"
                  value={formatPercent(worstSector)}
                  subvalue={`cap ${formatPercent(c.max_sector_weight)}`}
                  color={breachMonths > 0 ? "red" : "blue"}
                />
                <StatCard
                  label="Avg holdings"
                  value={avgPositions.toFixed(1)}
                  subvalue={`${c.min_names}–${c.max_names} allowed`}
                  color="slate"
                />
                <StatCard
                  label="Peak cash"
                  value={formatPercent(maxCash)}
                  subvalue="unallocated, earns nothing"
                  color={maxCash > 0.2 ? "amber" : "slate"}
                />
              </div>
              <p className="text-xs text-slate-500 mt-3 leading-relaxed">
                Every hard limit held in every month:{" "}
                {constraints.all_constraints_respected ? (
                  <span className="text-emerald-600 font-medium">
                    all constraints respected
                  </span>
                ) : (
                  <span className="text-red-600 font-medium">
                    at least one limit was breached — see the per-month figures
                    below
                  </span>
                )}
                . Cash is the residual left when the 5% position cap and the 30%
                sector cap cannot absorb more capital, and it is held rather than
                forced into the best remaining name, because a position above
                the cap would violate the constraint the book is built around.
                {c.max_pct_of_adv === null && (
                  <>
                    {" "}
                    A participation cap (percent of average daily volume) is
                    defined but not enforced, because the source data has no
                    reliable ADV series.
                  </>
                )}
              </p>
            </Card>
          );
        })()}
    </div>
  );
}
