import { Card, StatCard, RegimeBadge, DecisionBadge, Badge, Table, ProgressBar } from "@/components/UI";
import { DonutChart, LineChart } from "@/components/Charts";
import {
  getOverviewData,
  getRegimePredictions,
  getBacktestSummary,
  getBacktestPortfolio,
  getLatestAllocation,
  formatPercent,
  formatNumber,
  getRegimeColor,
  getFactorColor,
} from "@/lib/data";
import { Gauge, TrendingUp, Shield, Target, Activity, AlertTriangle, Briefcase, BarChart3 } from "lucide-react";
import type { FactorName } from "@/types";

export function OverviewPage() {
  const overview = getOverviewData();
  const regimes = getRegimePredictions();
  const summaries = getBacktestSummary();
  const btPortfolio = getBacktestPortfolio();
  const latestAlloc = getLatestAllocation();

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

  const dynSummary = summaries.find((s) => s.strategy_name === "Dynamic Regime Factor Allocation");
  const benchSummary = summaries.find((s) => s.strategy_name === "Nifty 200 Buy & Hold");
  const staticSummary = summaries.find((s) => s.strategy_name === "Static 25/25/25/25");

  const factorAllocData = (Object.entries(overview.factor_allocations) as [FactorName, number][])
    .map(([factor, weight]) => ({
      label: factor,
      value: weight,
      color: getFactorColor(factor),
    }));

  const equityCurve = btPortfolio.filter((b) => b.strategy_name === "Dynamic Regime Factor Allocation");
  const benchCurve = btPortfolio.filter((b) => b.strategy_name === "Nifty 200 Buy & Hold");
  const xLabels = equityCurve.map((b) => b.month);

  const recentRegimes = regimes.slice(-12);

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
          subvalue={overview.transition_risk > 0.5 ? "Elevated" : "Low"}
          icon={<AlertTriangle className="w-5 h-5" />}
          color={overview.transition_risk > 0.5 ? "red" : "green"}
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

        <Card title="Equity Curve" subtitle="Dynamic strategy vs Nifty 200 benchmark" className="lg:col-span-2">
          <LineChart
            data={[
              { label: "Dynamic", values: equityCurve.map((b) => b.portfolio_value) },
              { label: "Nifty 200 B&H", values: benchCurve.map((b) => b.portfolio_value) },
            ]}
            xLabels={xLabels}
            colors={["#3b82f6", "#10b981"]}
            yFormat={(v) => v.toFixed(0)}
            height={280}
          />
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
              ...r,
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
              strategy_name: s.strategy_name.replace("Dynamic Regime Factor Allocation", "Dynamic").replace("Nifty 200 Buy & Hold", "Benchmark"),
              cagr: formatPercent(s.cagr),
              sharpe: formatNumber(s.sharpe),
              max_drawdown: formatPercent(s.max_drawdown),
              calmar: formatNumber(s.calmar),
            }))}
            maxHeight="320px"
          />
        </Card>
      </div>
    </div>
  );
}
