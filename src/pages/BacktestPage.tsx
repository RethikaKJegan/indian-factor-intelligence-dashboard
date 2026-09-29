import { Card, Table, RegimeBadge } from "@/components/UI";
import { LineChart, Heatmap, BarChart } from "@/components/Charts";
import { BacktestReliability } from "@/components/BacktestReliability";
import {
  getBacktestPortfolio,
  getBacktestSummary,
  getRegimePerformance,
  formatPercent,
  formatNumber,
} from "@/lib/data";

/**
 * Strategies shown on the curve and drawdown charts, in draw order.
 *
 * The stock-level book is listed here too but is rendered from its own month
 * index (it starts one month later, because a book formed at the close of
 * month t is first evaluated in t+1). The chart builders below align on the
 * month label rather than on array position, so the differing lengths do not
 * shift a series onto the wrong months.
 */
const STRATEGIES = [
  "Dynamic Regime Factor Allocation",
  "Static 25/25/25/25",
  "Nifty 200 Buy & Hold",
  "Universe Equal-Weight",
];
const STRATEGY_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"];

/**
 * Display names keyed by full strategy name, never by array position. A
 * strategy missing from the backtest output must not shift another
 * strategy's label onto its numbers.
 */
const STRATEGY_SHORT: Record<string, string> = {
  "Dynamic Regime Factor Allocation": "Dynamic",
  "Static 25/25/25/25": "Static 25/25",
  "Nifty 200 Buy & Hold": "Nifty 200",
  "Universe Equal-Weight": "Universe EW",
};

const shortName = (full: string) => STRATEGY_SHORT[full] ?? full;

/**
 * What each strategy actually does, so the benchmark is not a mystery and the
 * comparison is interpretable.
 */
const STRATEGY_BLURB: Record<string, string> = {
  "Dynamic Regime Factor Allocation":
    "Weights the four factors each month from the regime and trailing factor returns.",
  "Static 25/25/25/25":
    "Equal 25% in every factor every month. No timing, no regime input. The control.",
  "Nifty 200 Buy & Hold":
    "100% in the Nifty 200 price index, bought once and held. Cap-weighted and price-only, so dividends are excluded.",
  "Universe Equal-Weight":
    "Every stock in the 189-name universe, equal weight, rebalanced monthly. No factors at all. This is the baseline the factor layer has to beat, and beating it is the point.",
};

export function BacktestPage() {
  const btPortfolio = getBacktestPortfolio();
  const summaries = getBacktestSummary();
  const regimePerf = getRegimePerformance();

  if (btPortfolio.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <p className="text-sm">No backtest data available.</p>
      </div>
    );
  }

  // Equity curves
  const dynCurve = btPortfolio.filter((b) => b.strategy_name === STRATEGIES[0]);
  const xLabels = dynCurve.map((b) => b.month);

  /**
   * Align every series to the shared month axis before plotting.
   *
   * Strategies are not guaranteed to cover the same months: the stock-level
   * book starts one month later, and a strategy can be absent from a run
   * entirely. Mapping straight to `.map()` would therefore plot one series'
   * values against another series' months. Indexing by month label and
   * emitting `null` for a gap lets the chart break the line there instead.
   */
  const aligned = (sname: string, pick: (b: (typeof btPortfolio)[number]) => number) => {
    const byMonth = new Map(
      btPortfolio.filter((b) => b.strategy_name === sname).map((b) => [b.month, pick(b)]),
    );
    return xLabels.map((m) => {
      const v = byMonth.get(m);
      return v == null || Number.isNaN(v) ? null : v;
    });
  };

  const equityData = STRATEGIES.map((sname) => ({
    label: shortName(sname),
    values: aligned(sname, (b) => b.portfolio_value),
  }));

  // Drawdown
  const drawdownData = STRATEGIES.map((sname) => ({
    label: shortName(sname),
    values: aligned(sname, (b) => b.drawdown),
  }));

  // Monthly returns heatmap for Dynamic
  const dynReturns = btPortfolio.filter((b) => b.strategy_name === STRATEGIES[0]);

  // Group by year for heatmap
  const yearMonths: Record<string, { [key: string]: number }> = {};
  dynReturns.forEach((b) => {
    const year = b.month.slice(0, 4);
    const mon = b.month.slice(5, 7);
    if (!yearMonths[year]) yearMonths[year] = {};
    yearMonths[year][mon] = b.monthly_return;
  });

  const years = Object.keys(yearMonths).sort();
  const monthLabels = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const heatRows = years;
  const heatCols = monthNames;
  const heatValues = years.map((y) =>
    // `null` marks "no backtest row for this month"; a real 0.0% month must
    // stay 0 so it is not confused with missing data.
    monthLabels.map((m) => yearMonths[y]?.[m] ?? null)
  );

  // Regime performance bar
  const regimePerfData = regimePerf.map((r) => ({
    label: r.regime_label.replace(" / ", "/").slice(0, 15),
    value: r.avg_return,
    color: r.avg_return >= 0 ? "#10b981" : "#ef4444",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Backtest Dashboard</h2>
        <p className="text-sm text-slate-500 mt-1">
          Dynamic vs Static vs Benchmark — Monthly backtest with 0.10% transaction costs
        </p>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {summaries.map((s) => (
          <Card key={s.strategy_name} title={shortName(s.strategy_name)}>
            <p className="mb-3 text-xs text-slate-500">
              {STRATEGY_BLURB[s.strategy_name] ?? ""}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-[10px] text-slate-500 uppercase">CAGR</p>
                <p className={`text-lg font-bold ${s.cagr >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                  {formatPercent(s.cagr)}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Total Return</p>
                <p className={`text-lg font-bold ${s.total_return >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                  {formatPercent(s.total_return)}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Sharpe</p>
                <p className="text-sm font-semibold text-slate-700">{formatNumber(s.sharpe)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Max DD</p>
                <p className="text-sm font-semibold text-red-600">{formatPercent(s.max_drawdown)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Calmar</p>
                <p className="text-sm font-semibold text-slate-700">{formatNumber(s.calmar)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Volatility</p>
                <p className="text-sm font-semibold text-amber-600">{formatPercent(s.annual_volatility)}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Equity Curve */}
      <Card title="Equity Curve Comparison" subtitle="Growth of 100 across strategies">
        <LineChart
          data={equityData}
          xLabels={xLabels}
          colors={STRATEGY_COLORS}
          yFormat={(v) => v.toFixed(0)}
          height={300}
        />
      </Card>

      {/* Drawdown */}
      <Card title="Drawdown Comparison" subtitle="Peak-to-trough decline over time">
        <LineChart
          data={drawdownData}
          xLabels={xLabels}
          colors={STRATEGY_COLORS}
          yFormat={(v) => formatPercent(v, 0)}
          height={250}
        />
      </Card>

      {/* Monthly Returns Heatmap */}
      <Card title="Monthly Returns Heatmap — Dynamic Strategy" subtitle="Green = positive, Red = negative">
        <Heatmap
          rows={heatRows}
          cols={heatCols}
          values={heatValues}
          cellFormat={(v) => formatPercent(v, 1)}
          colorScale={(v) => {
            // Missing cells are handled by Heatmap itself, so 0 here is a
            // genuine flat month and gets a neutral (not "no data") shade.
            if (v === 0) return "#e2e8f0";
            if (v > 0.05) return "#10b981";
            if (v > 0.02) return "#86efac";
            if (v > 0) return "#d1fae5";
            if (v > -0.02) return "#fde68a";
            if (v > -0.05) return "#fca5a5";
            return "#ef4444";
          }}
        />
      </Card>

      {/* Performance by Regime */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Performance by Regime" subtitle="Dynamic strategy average returns in each regime">
          <BarChart
            data={regimePerfData}
            yFormat={(v) => formatPercent(v, 1)}
            height={250}
          />
        </Card>

        <Card title="Trade History" subtitle="Latest month rebalance activity">
          <Table
            columns={[
              { key: "month", label: "Month" },
              { key: "strategy_name", label: "Strategy" },
              { key: "portfolio_value", label: "Value", align: "right" },
              { key: "monthly_return", label: "Return", align: "right" },
              { key: "drawdown", label: "Drawdown", align: "right" },
              { key: "regime_label", label: "Regime" },
            ]}
            data={btPortfolio
              .filter((b) => b.strategy_name === STRATEGIES[0])
              .slice(-20)
              .reverse()
              .map((b) => ({
                month: b.month,
                strategy_name: "Dynamic",
                portfolio_value: formatNumber(b.portfolio_value, 0),
                monthly_return: `${b.monthly_return >= 0 ? "+" : ""}${formatPercent(b.monthly_return)}`,
                drawdown: formatPercent(b.drawdown),
                regime_label: <RegimeBadge regime={b.regime_label} />,
              }))}
            maxHeight="300px"
          />
        </Card>
      </div>

      {/* Full Summary Table */}
      <Card title="Complete Performance Summary" subtitle="All strategies, all metrics">
        <Table
          columns={[
            { key: "strategy_name", label: "Strategy" },
            { key: "cagr", label: "CAGR", align: "right" },
            { key: "total_return", label: "Total Return", align: "right" },
            { key: "annual_volatility", label: "Volatility", align: "right" },
            { key: "sharpe", label: "Sharpe", align: "right" },
            { key: "max_drawdown", label: "Max DD", align: "right" },
            { key: "calmar", label: "Calmar", align: "right" },
            { key: "avg_turnover", label: "Avg Turnover", align: "right" },
            { key: "best_month", label: "Best", align: "right" },
            { key: "worst_month", label: "Worst", align: "right" },
          ]}
          data={summaries.map((s) => ({
            strategy_name: shortName(s.strategy_name),
            cagr: formatPercent(s.cagr),
            total_return: formatPercent(s.total_return),
            annual_volatility: formatPercent(s.annual_volatility),
            sharpe: formatNumber(s.sharpe),
            max_drawdown: formatPercent(s.max_drawdown),
            calmar: formatNumber(s.calmar),
            avg_turnover: formatPercent(s.avg_turnover),
            best_month: formatPercent(s.best_month),
            worst_month: formatPercent(s.worst_month),
          }))}
          maxHeight="200px"
        />
      </Card>

      <BacktestReliability />
    </div>
  );
}
