import { Card, StatCard, Table, DecisionBadge, ProgressBar } from "@/components/UI";
import { StackedAreaChart, LineChart, BarChart } from "@/components/Charts";
import {
  getFactorAllocations,
  getAllocationDecisions,
  getLatestAllocation,
  formatPercent,
  formatNumber,
  getFactorColor,
  getRegimeColor,
} from "@/lib/data";
import { PieChart, TrendingUp, Activity, Target, RotateCw } from "lucide-react";
import type { FactorName } from "@/types";

const FACTORS: FactorName[] = ["Momentum", "Value", "Quality", "Low Volatility"];
const FACTOR_KEYS = ["momentum_weight", "value_weight", "quality_weight", "low_volatility_weight"];

export function AllocationPage() {
  const allocations = getFactorAllocations();
  const decisions = getAllocationDecisions();
  const latest = getLatestAllocation();

  if (allocations.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <p className="text-sm">No allocation data available.</p>
      </div>
    );
  }

  const xLabels = allocations.map((a) => a.month);
  const stackData = FACTORS.map((f, i) => ({
    label: f,
    values: allocations.map((a) => (a as any)[FACTOR_KEYS[i]]),
  }));

  const expRetData = [
    { label: "Expected Return", values: allocations.map((a) => a.expected_return) },
    { label: "Expected Risk", values: allocations.map((a) => a.expected_risk) },
  ];

  const turnoverData = allocations.map((a) => ({
    label: a.month,
    value: a.turnover,
    color: "#f59e0b",
  }));

  const redundancyData = allocations.map((a) => ({
    label: a.month,
    value: a.redundancy_score,
    color: "#8b5cf6",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Allocation Dashboard</h2>
        <p className="text-sm text-slate-500 mt-1">
          Dynamic factor allocation via grid-search optimization with decision gate
        </p>
      </div>

      {/* Latest Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Latest Expected Return"
          value={latest ? formatPercent(latest.expected_return) : "—"}
          subvalue="Monthly forecast"
          icon={<TrendingUp className="w-5 h-5" />}
          color={latest && latest.expected_return >= 0 ? "green" : "red"}
        />
        <StatCard
          label="Latest Expected Risk"
          value={latest ? formatPercent(latest.expected_risk) : "—"}
          subvalue="Portfolio volatility"
          icon={<Activity className="w-5 h-5" />}
          color="amber"
        />
        <StatCard
          label="Latest Turnover"
          value={latest ? formatPercent(latest.turnover) : "—"}
          subvalue="Weight change"
          icon={<RotateCw className="w-5 h-5" />}
          color="slate"
        />
        <StatCard
          label="Optimizer Status"
          value={latest?.optimizer_status?.replace("grid_search_", "Grid ") || "—"}
          subvalue="5% increments"
          icon={<Target className="w-5 h-5" />}
          color="blue"
        />
      </div>

      {/* Latest Weights */}
      <Card title="Latest Factor Weights" subtitle={`Optimized allocation — ${latest?.month}`}>
        <div className="space-y-3 max-w-md">
          {FACTORS.map((f, i) => (
            <div key={f} className="flex items-center justify-between">
              <div className="flex items-center gap-2 w-32">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: getFactorColor(f) }} />
                <span className="text-sm text-slate-700">{f}</span>
              </div>
              <div className="flex items-center gap-3 flex-1 ml-4">
                <div className="flex-1">
                  <ProgressBar value={(latest as any)?.[FACTOR_KEYS[i]] || 0} color={getFactorColor(f)} />
                </div>
                <span className="text-sm font-medium text-slate-700 tabular-nums w-14 text-right">
                  {latest ? formatPercent((latest as any)[FACTOR_KEYS[i]]) : "—"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Stacked Area */}
      <Card title="Factor Weights Over Time" subtitle="Dynamic allocation across regimes">
        <StackedAreaChart
          data={stackData}
          xLabels={xLabels}
          colors={["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b"]}
          height={300}
        />
      </Card>

      {/* Expected Return / Risk */}
      <Card title="Expected Return vs Risk" subtitle="Optimizer forecasted metrics">
        <LineChart
          data={expRetData}
          xLabels={xLabels}
          colors={["#3b82f6", "#f59e0b"]}
          yFormat={(v) => formatPercent(v, 1)}
          height={250}
        />
      </Card>

      {/* Turnover + Redundancy */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Turnover Over Time" subtitle="Monthly weight change cost">
          <BarChart
            data={turnoverData.slice(-24)}
            yFormat={(v) => formatPercent(v, 0)}
            height={220}
          />
        </Card>
        <Card title="Redundancy Score" subtitle="Factor correlation overlap penalty">
          <BarChart
            data={redundancyData.slice(-24)}
            yFormat={(v) => formatPercent(v, 0)}
            height={220}
          />
        </Card>
      </div>

      {/* Decision History */}
      <Card title="Allocation Decision History" subtitle="REBALANCE / RETAIN / DEFENSIVE gate decisions">
        <Table
          columns={[
            { key: "month", label: "Month" },
            { key: "decision", label: "Decision" },
            { key: "reason", label: "Reason" },
            { key: "expected_utility_delta", label: "Utility Δ", align: "right" },
            { key: "regime_confidence", label: "Confidence", align: "right" },
            { key: "transition_risk", label: "Trans. Risk", align: "right" },
            { key: "news_stress_score", label: "News Stress", align: "right" },
            { key: "risk_event_count", label: "Risk Events", align: "right" },
            { key: "news_evidence", label: "News Evidence" },
          ]}
          data={decisions.map((d) => ({
            month: d.month,
            decision: <DecisionBadge decision={d.decision} />,
            reason: d.reason,
            expected_utility_delta: formatNumber(d.expected_utility_delta, 4),
            regime_confidence: formatPercent(d.regime_confidence),
            transition_risk: formatPercent(d.transition_risk),
            news_stress_score: formatPercent(d.news_stress_score ?? 0),
            risk_event_count: formatNumber(d.risk_event_count ?? 0, 0),
            news_evidence: d.supporting_news?.length
              ? `${d.supporting_news.length} stories`
              : "No matched stories",
          }))}
          maxHeight="400px"
        />
      </Card>
    </div>
  );
}
