import { Card, StatCard, Badge, RegimeBadge, DecisionBadge } from "@/components/UI";
import { getEodRefreshStatus, getLangGraphRunReport, formatNumber, formatPercent } from "@/lib/data";
import { Activity, AlertTriangle, CheckCircle, DatabaseZap, GitBranch, Newspaper, ShieldCheck } from "lucide-react";

function valueOrDash(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return formatNumber(value, Math.abs(value) < 1 ? 4 : 2);
  return String(value);
}

export function ModelReportPage() {
  const report = getLangGraphRunReport();
  const eod = getEodRefreshStatus();
  const snapshot = report.latest_snapshot ?? {};
  const regime = snapshot.latest_regime ?? {};
  const allocation = snapshot.latest_allocation ?? {};
  const decision = snapshot.latest_decision ?? {};
  const news = snapshot.latest_news_features ?? {};
  const warningCount = report.warnings?.length ?? 0;
  const groqOk = report.llm_explanation && !report.llm_explanation.toLowerCase().includes("fallback");
  const eodOk = eod.status === "ok";

  const allocationRows = [
    ["Momentum", allocation.momentum_weight],
    ["Value", allocation.value_weight],
    ["Quality", allocation.quality_weight],
    ["Low Volatility", allocation.low_volatility_weight],
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">LangGraph Model Report</h2>
        <p className="text-sm text-slate-500 mt-1">
          Latest orchestration run, node status, approval flag, news-aware decision context, and explanation output
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Orchestration"
          value={report.orchestration || "—"}
          subvalue={`${report.nodes?.length ?? 0} graph nodes`}
          icon={<GitBranch className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Human Approval"
          value={report.human_approval_required ? "Required" : "Not Required"}
          subvalue={report.human_approval_required ? "Review before live rebalance" : "No approval flag"}
          icon={report.human_approval_required ? <AlertTriangle className="w-5 h-5" /> : <ShieldCheck className="w-5 h-5" />}
          color={report.human_approval_required ? "amber" : "green"}
        />
        <StatCard
          label="Warnings"
          value={warningCount}
          subvalue={warningCount ? "Needs review" : "No warnings"}
          icon={warningCount ? <AlertTriangle className="w-5 h-5" /> : <CheckCircle className="w-5 h-5" />}
          color={warningCount ? "red" : "green"}
        />
        <StatCard
          label="Latest EOD Refresh"
          value={eodOk ? "Updated" : eod.status}
          subvalue={eod.resolved_date ? `Data date ${eod.resolved_date}` : "No fresh EOD yet"}
          icon={<DatabaseZap className="w-5 h-5" />}
          color={eodOk ? "green" : eod.status === "failed" ? "red" : "amber"}
        />
      </div>

      <Card title="Daily NSE EOD Refresh" subtitle="Real market-data refresh status before LangGraph model run">
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <Metric label="Status" value={String(eod.status ?? "—")} />
          <Metric label="Requested" value={valueOrDash(eod.requested_date)} />
          <Metric label="Resolved EOD" value={valueOrDash(eod.resolved_date)} />
          <Metric label="Stock Rows" value={formatNumber(eod.stock_rows ?? 0, 0)} />
          <Metric label="Index Rows" value={formatNumber(eod.index_rows ?? 0, 0)} />
          <Metric label="Factor Rows" value={formatNumber(eod.updated_factor_score_rows ?? 0, 0)} />
        </div>
        <div className={`mt-4 rounded-lg border px-3 py-2 text-sm ${eodOk ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
          {eod.message}
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card title="Latest Decision Snapshot" subtitle="Final state passed out of the graph">
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-500">Month</span>
              <span className="text-sm font-semibold text-slate-900">{valueOrDash(decision.month || regime.month)}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-500">Regime</span>
              {regime.regime_label ? <RegimeBadge regime={String(regime.regime_label)} /> : <span className="text-sm">—</span>}
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-500">Decision Gate</span>
              {decision.decision ? <DecisionBadge decision={String(decision.decision)} /> : <span className="text-sm">—</span>}
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-500">Regime Confidence</span>
              <span className="text-sm font-semibold text-slate-900">{formatPercent(Number(regime.regime_confidence ?? decision.regime_confidence ?? 0))}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-500">Transition Risk</span>
              <span className="text-sm font-semibold text-slate-900">{formatPercent(Number(decision.transition_risk ?? regime.transition_risk ?? 0))}</span>
            </div>
            <div className="rounded-lg bg-slate-50 border border-slate-100 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">Reason</div>
              <p className="text-sm text-slate-700">{valueOrDash(decision.reason)}</p>
            </div>
          </div>
        </Card>

        <Card title="News Evidence In Model" subtitle="Latest monthly news features included in regime/allocation">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Sentiment" value={valueOrDash(news.sentiment_score ?? regime.news_sentiment)} />
              <Metric label="Negative Ratio" value={formatPercent(Number(news.negative_ratio ?? regime.negative_news_ratio ?? 0))} />
              <Metric label="Risk Events" value={valueOrDash(news.risk_event_count ?? regime.risk_event_count)} />
              <Metric label="Confidence" value={formatPercent(Number(news.news_confidence ?? regime.news_confidence ?? 0))} />
            </div>
            <div className="rounded-lg bg-purple-50 border border-purple-100 p-3">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-purple-700 mb-1">
                <Newspaper className="w-3.5 h-3.5" />
                News Stress Score
              </div>
              <p className="text-2xl font-bold text-purple-900">
                {formatPercent(Number(decision.news_stress_score ?? allocation.news_stress_score ?? regime.news_stress_score ?? 0))}
              </p>
            </div>
          </div>
        </Card>

        <Card title="Recommended Factor Weights" subtitle={String(allocation.optimizer_status ?? "Latest allocation")}>
          <div className="space-y-3">
            {allocationRows.map(([name, weight]) => (
              <div key={String(name)}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-600">{name}</span>
                  <span className="font-semibold text-slate-900">{formatPercent(Number(weight ?? 0))}</span>
                </div>
                <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                  <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.max(0, Math.min(100, Number(weight ?? 0) * 100))}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card title="Graph Nodes" subtitle="Actual LangGraph StateGraph execution order">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {(report.nodes ?? []).map((node, idx) => (
              <div key={node} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center">{idx + 1}</span>
                <span className="text-sm font-medium text-slate-700">{node}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Routes And Warnings" subtitle="Branching paths, data failure recovery, and review flags">
          <div className="space-y-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Conditional Routes</div>
              <div className="flex flex-wrap gap-2">
                {(report.conditional_routes ?? []).map((route) => (
                  <Badge key={route} color="blue">{route}</Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Warnings</div>
              {warningCount ? (
                <div className="space-y-2">
                  {report.warnings.map((warning) => (
                    <div key={warning} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                      {warning}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                  No warnings in the latest graph run.
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>

      <Card title="Explanation Agent Output" subtitle="Groq explanation when available; deterministic fallback when API access fails">
        <div className="mb-3 flex items-center gap-2">
          <Badge color={groqOk ? "green" : "slate"}>{groqOk ? "Groq OK" : "Fallback"}</Badge>
          <span className="text-xs text-slate-500">{groqOk ? "API explanation generated" : "Deterministic report used"}</span>
        </div>
        <div className="rounded-lg bg-slate-950 p-4 text-sm leading-6 text-slate-100 whitespace-pre-wrap">
          {report.llm_explanation || "No explanation generated yet. Run scripts/run_langgraph_pipeline.py to refresh this report."}
        </div>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-bold text-slate-900">{value}</div>
    </div>
  );
}
