import { Card, StatCard, RegimeBadge, Table, Badge } from "@/components/UI";
import { LineChart, Heatmap, BarChart } from "@/components/Charts";
import {
  getRegimePredictions,
  getRegimeTransitionMatrix,
  getRegimePerformance,
  formatPercent,
  getRegimeColor,
} from "@/lib/data";
import { Gauge, Activity, AlertTriangle, BarChart3 } from "lucide-react";

const REGIME_LABELS = [
  "Bull / Expansion",
  "Bear / Stress",
  "Sideways / Neutral",
  "Recovery",
  "High Volatility / Risk-Off",
];

export function RegimePage() {
  const regimes = getRegimePredictions();
  const transitions = getRegimeTransitionMatrix();
  const perf = getRegimePerformance();

  if (regimes.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <p className="text-sm">No regime data available.</p>
      </div>
    );
  }

  const xLabels = regimes.map((r) => r.month);
  const probData = [
    { label: "Bull", values: regimes.map((r) => r.prob_bull_expansion) },
    { label: "Bear", values: regimes.map((r) => r.prob_bear_stress) },
    { label: "Sideways", values: regimes.map((r) => r.prob_sideways_neutral) },
    { label: "Recovery", values: regimes.map((r) => r.prob_recovery) },
    { label: "High Vol", values: regimes.map((r) => r.prob_high_vol_risk_off) },
  ];

  const confData = [
    { label: "Confidence", values: regimes.map((r) => r.regime_confidence) },
    { label: "Transition Risk", values: regimes.map((r) => r.transition_risk) },
  ];

  // Transition matrix heatmap
  const matrix: number[][] = REGIME_LABELS.map((from) =>
    REGIME_LABELS.map((to) => {
      const cell = transitions.find(
        (t) => t.from_regime === from && t.to_regime === to
      );
      return cell ? cell.probability : 0;
    })
  );

  const shortLabels = REGIME_LABELS.map((l) =>
    l.replace(" / ", "/").replace("Expansion", "Exp").replace("Stress", "Str").replace("Neutral", "Neu").replace("Risk-Off", "Risk")
  );

  // Regime counts
  const counts: Record<string, number> = {};
  regimes.forEach((r) => {
    counts[r.regime_label] = (counts[r.regime_label] || 0) + 1;
  });

  const latest = regimes[regimes.length - 1];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Regime Dashboard</h2>
        <p className="text-sm text-slate-500 mt-1">
          GMM-5 model regime detection with probability vectors and transition analysis
        </p>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Latest Regime"
          value={<RegimeBadge regime={latest.regime_label} />}
          subvalue={latest.month}
          icon={<Gauge className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Confidence"
          value={formatPercent(latest.regime_confidence)}
          subvalue={latest.regime_confidence > 0.7 ? "High" : "Moderate"}
          icon={<Activity className="w-5 h-5" />}
          color={latest.regime_confidence > 0.7 ? "green" : "amber"}
        />
        <StatCard
          label="Transition Risk"
          value={formatPercent(latest.transition_risk)}
          subvalue={latest.transition_risk > 0.5 ? "Elevated" : "Stable"}
          icon={<AlertTriangle className="w-5 h-5" />}
          color={latest.transition_risk > 0.5 ? "red" : "green"}
        />
        <StatCard
          label="Total Months"
          value={regimes.length}
          subvalue={`${counts["Bull / Expansion"] || 0} Bull, ${counts["Bear / Stress"] || 0} Bear`}
          icon={<BarChart3 className="w-5 h-5" />}
          color="slate"
        />
      </div>

      {/* Probability Chart */}
      <Card title="Regime Probability Timeline" subtitle="GMM cluster probabilities over time">
        <LineChart
          data={probData}
          xLabels={xLabels}
          colors={["#10b981", "#ef4444", "#6b7280", "#3b82f6", "#f59e0b"]}
          yFormat={(v) => formatPercent(v, 0)}
          height={300}
        />
      </Card>

      {/* Confidence + Transition Risk */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Regime Confidence" subtitle="Model confidence and transition risk over time">
          <LineChart
            data={confData}
            xLabels={xLabels}
            colors={["#3b82f6", "#f59e0b"]}
            yFormat={(v) => formatPercent(v, 0)}
            height={250}
          />
        </Card>

        <Card title="Regime Frequency" subtitle="Distribution of regimes across all months">
          <BarChart
            data={REGIME_LABELS.map((l) => ({
              label: l.replace(" / ", "/").slice(0, 15),
              value: counts[l] || 0,
              color: getRegimeColor(l),
            }))}
            yFormat={(v) => v.toFixed(0)}
            height={250}
          />
        </Card>
      </div>

      {/* Transition Matrix + Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Regime Transition Matrix" subtitle="Probability of transitioning from one regime to another">
          <Heatmap
            rows={shortLabels}
            cols={shortLabels}
            values={matrix}
            cellFormat={(v) => v.toFixed(2)}
          />
        </Card>

        <Card title="Performance by Regime" subtitle="Dynamic strategy returns in each regime">
          <Table
            columns={[
              { key: "regime_label", label: "Regime" },
              { key: "freq", label: "Months", align: "right" },
              { key: "avg_return", label: "Avg Return", align: "right" },
              { key: "best_month", label: "Best", align: "right" },
              { key: "worst_month", label: "Worst", align: "right" },
            ]}
            data={perf.map((p) => ({
              ...p,
              avg_return: formatPercent(p.avg_return),
              best_month: formatPercent(p.best_month),
              worst_month: formatPercent(p.worst_month),
            }))}
            maxHeight="300px"
          />
        </Card>
      </div>

      {/* Full Regime History */}
      <Card title="Full Regime History" subtitle="All regime predictions">
        <Table
          columns={[
            { key: "month", label: "Month" },
            { key: "regime_label", label: "Regime" },
            { key: "regime_cluster", label: "Cluster", align: "center" },
            { key: "regime_confidence", label: "Confidence", align: "right" },
            { key: "transition_risk", label: "Trans. Risk", align: "right" },
            { key: "model_version", label: "Model" },
          ]}
          data={regimes.map((r) => ({
            ...r,
            regime_confidence: formatPercent(r.regime_confidence),
            transition_risk: formatPercent(r.transition_risk),
          }))}
          maxHeight="400px"
        />
      </Card>
    </div>
  );
}
