import { Card, StatCard, Table, Badge, RegimeBadge } from "@/components/UI";
import { LineChart, Heatmap, BarChart } from "@/components/Charts";
import {
  getBacktestPortfolio,
  getBacktestSummary,
  getRegimePerformance,
  formatPercent,
  formatNumber,
} from "@/lib/data";
import { TrendingUp, Activity, Shield, BarChart3, Award } from "lucide-react";

const STRATEGIES = [
  "Dynamic Regime Factor Allocation",
  "Static 25/25/25/25",
  "Nifty 200 Buy & Hold",
];
const STRATEGY_COLORS = ["#3b82f6", "#8b5cf6", "#10b981"];
const STRATEGY_SHORT = ["Dynamic", "Static 25/25", "Benchmark"];

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

  const equityData = STRATEGIES.map((sname, i) => ({
    label: STRATEGY_SHORT[i],
    values: btPortfolio.filter((b) => b.strategy_name === sname).map((b) => b.portfolio_value),
  }));

  // Drawdown
  const drawdownData = STRATEGIES.map((sname, i) => ({
    label: STRATEGY_SHORT[i],
    values: btPortfolio.filter((b) => b.strategy_name === sname).map((b) => b.drawdown),
  }));

  // Monthly returns heatmap for Dynamic
  const dynReturns = btPortfolio.filter((b) => b.strategy_name === STRATEGIES[0]);
  const months = dynReturns.map((b) => b.month);

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
    monthLabels.map((m) => yearMonths[y]?.[m] ?? 0)
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
        {summaries.map((s, i) => (
          <Card key={s.strategy_name} title={STRATEGY_SHORT[i]}>
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
          cellFormat={(v) => v === 0 ? "—" : formatPercent(v, 1)}
          colorScale={(v) => {
            if (v === 0) return "#f1f5f9";
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
          data={summaries.map((s, i) => ({
            strategy_name: STRATEGY_SHORT[i],
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
    </div>
  );
}
