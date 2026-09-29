import { Card, StatCard, RegimeBadge, Table } from "@/components/UI";
import { LineChart, Heatmap, BarChart } from "@/components/Charts";
import {
  getRegimePredictions,
  getRegimeTransitionMatrix,
  getRegimePerformance,
  formatPercent,
  getRegimeColor,
  newestFirst,
} from "@/lib/data";
import { REGIME_LABELS } from "@/types";
import { downloadCsv } from "@/lib/csv";
import { Gauge, Activity, AlertTriangle, BarChart3, Download } from "lucide-react";

const SHORT_LABEL: Record<string, string> = {
  "Bull / Expansion": "Bull/Exp",
  "Bear / Stress": "Bear/Str",
  "Sideways / Neutral": "Sideways/Neu",
  Recovery: "Recovery",
  "High Volatility / Risk-Off": "HighVol/Risk",
  Unscored: "Unscored",
};

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
  // Diagnostic carried on the newest record only.
  const separation = [...regimes].reverse().find((r) => r.cluster_separation)?.cluster_separation;

  /**
   * Warm-up months the walk-forward model could not score.
   *
   * The history spans 153 months but the model only emits an opinion for the
   * months after its first training window. Reporting "153 months" implied 153
   * model judgements; the scored count is stated so the reader can see the
   * difference, and the charts below leave the unscored months blank instead
   * of drawing them as zero.
   */
  const scoredCount = regimes.filter((r) => !r.is_warmup).length;
  const warmupCount = regimes.length - scoredCount;

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

  const shortLabels = REGIME_LABELS.map((l) => SHORT_LABEL[l] ?? l);

  const exportRegimes = () =>
    downloadCsv("regime_history", newestFirst(regimes), [
      { key: "month" },
      { key: "regime_label", label: "regime" },
      { key: "regime_cluster", label: "cluster" },
      { key: "regime_confidence", label: "confidence" },
      { key: "transition_risk", label: "transition_risk" },
      { key: "prob_bull_expansion", label: "prob_bull_expansion" },
      { key: "prob_bear_stress", label: "prob_bear_stress" },
      { key: "prob_sideways_neutral", label: "prob_sideways_neutral" },
      { key: "prob_recovery", label: "prob_recovery" },
      { key: "prob_high_vol_risk_off", label: "prob_high_vol_risk_off" },
      { key: "news_sentiment", label: "news_sentiment" },
      { key: "negative_news_ratio", label: "negative_news_ratio" },
      { key: "risk_event_count", label: "risk_event_count" },
      { key: "news_stress_score", label: "news_stress_score" },
      { key: "model_version", label: "model_version" },
    ]);

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
          subvalue={
            latest.regime_confidence === null
              ? "No model output"
              : latest.regime_confidence > 0.7
              ? "High"
              : "Moderate"
          }
          icon={<Activity className="w-5 h-5" />}
          color={
            latest.regime_confidence === null
              ? "slate"
              : latest.regime_confidence > 0.7
              ? "green"
              : "amber"
          }
        />
        <StatCard
          label="Transition Risk"
          value={formatPercent(latest.transition_risk)}
          subvalue={
            latest.transition_risk === null
              ? "No model output"
              : latest.transition_risk > 0.5
              ? "Elevated"
              : "Stable"
          }
          icon={<AlertTriangle className="w-5 h-5" />}
          color={
            latest.transition_risk !== null && latest.transition_risk > 0.5
              ? "red"
              : "green"
          }
        />
        <StatCard
          label="Months Scored"
          value={scoredCount}
          subvalue={
            warmupCount > 0
              ? `${warmupCount} of ${regimes.length} unscored (warm-up)`
              : `${counts["Bull / Expansion"] || 0} Bull, ${counts["Bear / Stress"] || 0} Bear`
          }
          icon={<BarChart3 className="w-5 h-5" />}
          color="slate"
        />
      </div>

      {separation && (
        <div
          className={`rounded-xl border px-4 py-3 text-sm ${
            separation.clusters_separate_returns
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : "border-amber-200 bg-amber-50 text-amber-900"
          }`}
        >
          <p className="font-semibold">
            {separation.clusters_separate_returns
              ? "Regimes separate forward returns"
              : "Regimes do not separate forward returns"}
          </p>
          <p className="mt-1">
            Across {separation.observations} scored months, the mean next-month index
            return differs between the {separation.groups} clusters by F ={" "}
            {separation.f_statistic} (5% critical ≈ {separation.f_critical_approx}).
            {separation.clusters_separate_returns
              ? " That is above the threshold, so the clustering carries some forward-looking information."
              : " That is below the threshold, so on this sample the regime labels are descriptive groupings rather than a validated forecast. They classify the past; they do not reliably predict the next month."}
          </p>
        </div>
      )}

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
      <Card
        title="Full Regime History"
        subtitle={`All regime predictions, newest first (${regimes.length} months)`}
        action={
          <button
            onClick={exportRegimes}
            className="flex items-center gap-1.5 rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        }
      >
        <Table
          columns={[
            { key: "month", label: "Month" },
            { key: "regime_label", label: "Regime" },
            { key: "regime_cluster", label: "Cluster", align: "center" },
            { key: "regime_confidence", label: "Confidence", align: "right" },
            { key: "transition_risk", label: "Trans. Risk", align: "right" },
            { key: "model_version", label: "Model" },
          ]}
          data={newestFirst(regimes).map((r) => ({
            month: r.month,
            regime_label: r.regime_label,
            regime_cluster: r.regime_cluster === null ? "—" : r.regime_cluster,
            regime_confidence: formatPercent(r.regime_confidence),
            transition_risk: formatPercent(r.transition_risk),
            model_version: r.model_version,
          }))}
          maxHeight="400px"
        />
      </Card>
    </div>
  );
}
