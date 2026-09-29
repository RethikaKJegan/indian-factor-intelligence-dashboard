import { Card, StatCard, RegimeBadge, DecisionBadge, Table, ProgressBar } from "@/components/UI";
import { DonutChart, LineChart } from "@/components/Charts";
import { ForwardOutlookPanel } from "@/components/ForwardOutlook";
import {
  getOverviewData,
  getRegimePredictions,
  getBacktestSummary,
  getBacktestPortfolio,
  formatPercent,
  formatNumber,
  getFactorColor,
  newestFirst,
} from "@/lib/data";
import { Gauge, TrendingUp, Shield, Target, Activity, AlertTriangle, Briefcase, BarChart3 } from "lucide-react";
import type { FactorName } from "@/types";

/**
 * Short labels for the strategy comparison table, keyed by exact name.
 *
 * "Universe Equal-Weight" is labelled as a baseline rather than a strategy:
 * it is the number the factor layer is measured against, and reading it as a
 * fourth model would hide that it contains no factor logic at all.
 */
const OVERVIEW_STRATEGY_LABEL: Record<string, string> = {
  "Dynamic Regime Factor Allocation": "Dynamic",
  "Static 25/25/25/25": "Static 25/25",
  "Nifty 200 Buy & Hold": "Nifty 200",
  "Universe Equal-Weight": "Universe EW (baseline)",
  "Stock-Level Constrained Portfolio": "Stock-level",
};

export function OverviewPage() {
  const overview = getOverviewData();
  const regimes = getRegimePredictions();
  const summaries = getBacktestSummary();
  const btPortfolio = getBacktestPortfolio();

  if (!overview) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 mx-auto text-slate-300" />
          <p className="mt-2 text-sm">No data available. Run the pipeline to generate outputs.</p>
        </div>
      </div>
    );
  }

  const factorAllocData = (Object.entries(overview.factor_allocations) as [FactorName, number][])
    .map(([factor, weight]) => ({
      label: factor,
      value: weight,
      color: getFactorColor(factor),
    }));

  const equityCurve = btPortfolio.filter((b) => b.strategy_name === "Dynamic Regime Factor Allocation");
  const benchCurve = btPortfolio.filter((b) => b.strategy_name === "Nifty 200 Buy & Hold");
  const ewCurve = btPortfolio.filter((b) => b.strategy_name === "Universe Equal-Weight");
  const xLabels = equityCurve.map((b) => b.month);

  // Newest first, so the current month is the top row.
  const recentRegimes = newestFirst(regimes).slice(0, 12);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Dashboard Overview</h2>
        <p className="text-sm text-slate-500 mt-1">
          Latest month: {overview.latest_month} — Current regime and portfolio snapshot
        </p>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Current Regime"
          value={<RegimeBadge regime={overview.regime_label} />}
          subvalue={`Confidence: ${formatPercent(overview.regime_confidence)}`}
          icon={<Gauge className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Latest Decision"
          value={<DecisionBadge decision={overview.latest_decision} />}
          subvalue={overview.decision_reason.slice(0, 50) + (overview.decision_reason.length > 50 ? "…" : "")}
          icon={<Target className="w-5 h-5" />}
          color="amber"
        />
        <StatCard
          label="Transition Risk"
          value={formatPercent(overview.transition_risk)}
          subvalue={
            overview.transition_risk === null
              ? "No model output"
              : overview.transition_risk > 0.5
              ? "Elevated"
              : "Low"
          }
          icon={<AlertTriangle className="w-5 h-5" />}
          color={overview.transition_risk !== null && overview.transition_risk > 0.5 ? "red" : "green"}
        />
        <StatCard
          label="Portfolio Stocks"
          value={overview.stock_count}
          subvalue="Active positions"
          icon={<Briefcase className="w-5 h-5" />}
          color="slate"
        />
      </div>

      {/* Performance Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="CAGR"
          value={formatPercent(overview.cagr)}
          subvalue="Annualized return"
          icon={<TrendingUp className="w-5 h-5" />}
          color={overview.cagr >= 0 ? "green" : "red"}
          trend={overview.cagr >= 0 ? "up" : "down"}
        />
        <StatCard
          label="Sharpe Ratio"
          value={formatNumber(overview.sharpe)}
          subvalue="Risk-adjusted return"
          icon={<Activity className="w-5 h-5" />}
          color={overview.sharpe >= 1 ? "green" : "amber"}
        />
        <StatCard
          label="Max Drawdown"
          value={formatPercent(overview.max_drawdown)}
          subvalue="Worst peak-to-trough"
          icon={<Shield className="w-5 h-5" />}
          color="red"
          trend="down"
        />
        <StatCard
          label="Annual Volatility"
          value={formatPercent(overview.annual_volatility)}
          subvalue="Standard deviation"
          icon={<BarChart3 className="w-5 h-5" />}
          color="amber"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Factor Allocation" subtitle={`Latest weights — ${overview.latest_month}`} className="lg:col-span-1">
          <DonutChart
            data={factorAllocData}
            centerLabel="Total"
            centerValue="100%"
          />
          <div className="mt-4 space-y-2">
            {factorAllocData.map((f) => (
              <div key={f.label} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-sm" style={{ background: f.color }} />
                  <span className="text-xs text-slate-700">{f.label}</span>
                </div>
                <div className="flex items-center gap-2 w-32">
                  <div className="flex-1">
                    <ProgressBar value={f.value} color={f.color} />
                  </div>
                  <span className="text-xs font-medium text-slate-700 tabular-nums w-12 text-right">
                    {formatPercent(f.value)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card
          title="Equity Curve"
          subtitle="Dynamic strategy against both benchmarks"
          className="lg:col-span-2"
        >
          <LineChart
            data={[
              { label: "Dynamic", values: equityCurve.map((b) => b.portfolio_value) },
              { label: "Universe EW", values: ewCurve.map((b) => b.portfolio_value) },
              { label: "Nifty 200 B&H", values: benchCurve.map((b) => b.portfolio_value) },
            ]}
            xLabels={xLabels}
            colors={["#3b82f6", "#f59e0b", "#10b981"]}
            yFormat={(v) => v.toFixed(0)}
            height={280}
          />
          <p className="mt-3 text-[11px] text-slate-500 leading-relaxed">
            The cap-weighted Nifty 200 price index is a weak yardstick for a
            factor book tilted toward smaller names. The equal-weight line is the
            same 189-stock universe with no factor logic at all, and it is the
            comparison that actually says whether the factors earned their keep.
          </p>
        </Card>
      </div>

      {/* Recent Regimes + Strategy Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Recent Regime History" subtitle="Last 12 months">
          <Table
            columns={[
              { key: "month", label: "Month" },
              { key: "regime_label", label: "Regime", align: "left" },
              { key: "regime_confidence", label: "Confidence", align: "right" },
              { key: "transition_risk", label: "Trans. Risk", align: "right" },
            ]}
            data={recentRegimes.map((r) => ({
              month: r.month,
              regime_label: r.regime_label,
              regime_confidence: formatPercent(r.regime_confidence),
              transition_risk: formatPercent(r.transition_risk),
            }))}
            maxHeight="320px"
          />
        </Card>

        <Card title="Strategy Comparison" subtitle="Backtest performance summary">
          <Table
            columns={[
              { key: "strategy_name", label: "Strategy" },
              { key: "cagr", label: "CAGR", align: "right" },
              { key: "sharpe", label: "Sharpe", align: "right" },
              { key: "max_drawdown", label: "Max DD", align: "right" },
              { key: "calmar", label: "Calmar", align: "right" },
            ]}
            data={summaries.map((s) => ({
              ...s,
              // Map by exact name. A chained .replace() silently leaves a
              // renamed strategy showing its full internal label.
              strategy_name: OVERVIEW_STRATEGY_LABEL[s.strategy_name] ?? s.strategy_name,
              cagr: formatPercent(s.cagr),
              sharpe: formatNumber(s.sharpe),
              max_drawdown: formatPercent(s.max_drawdown),
              calmar: formatNumber(s.calmar),
            }))}
            maxHeight="320px"
          />
        </Card>
      </div>

      {/* Forward view: what the model expects next, and how it has done before */}
      <ForwardOutlookPanel />
    </div>
  );
}
