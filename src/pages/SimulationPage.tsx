import { useEffect, useMemo, useState } from "react";
import { Card, StatCard, RegimeBadge, DecisionBadge, SignalBadge, Table, ProgressBar } from "@/components/UI";
import { LineChart } from "@/components/Charts";
import {
  getRegimePredictions,
  getFactorAllocations,
  getAllocationDecisions,
  getPortfolioTargets,
  getRebalanceTrades,
  getBacktestPortfolio,
  getNewsArticlesByMonth,
  formatPercent,
  getFactorColor,
} from "@/lib/data";
import { Play, Pause, StepForward, RotateCcw, Target, Briefcase, Newspaper, TrendingUp } from "lucide-react";
import type { FactorName } from "@/types";

export function SimulationPage() {
  const regimes = getRegimePredictions();
  const allocations = getFactorAllocations();
  const decisions = getAllocationDecisions();
  const trades = getRebalanceTrades();
  const bt = getBacktestPortfolio().filter((b) => b.strategy_name === "Dynamic Regime Factor Allocation");
  const months = useMemo(() => allocations.map((a) => a.month).sort(), [allocations]);
  const [fromMonth, setFromMonth] = useState(months[0] ?? "");
  const [toMonth, setToMonth] = useState(months[months.length - 1] ?? "");
  const visibleMonths = useMemo(
    () => months.filter((m) => (!fromMonth || m >= fromMonth) && (!toMonth || m <= toMonth)),
    [months, fromMonth, toMonth]
  );
  const [idx, setIdx] = useState(Math.max(0, visibleMonths.length - 1));
  const [playing, setPlaying] = useState(false);
  const month = visibleMonths[idx] ?? visibleMonths[visibleMonths.length - 1] ?? "";

  useEffect(() => {
    if (!playing || visibleMonths.length === 0) return;
    const id = window.setInterval(() => setIdx((v) => (v >= visibleMonths.length - 1 ? 0 : v + 1)), 900);
    return () => window.clearInterval(id);
  }, [playing, visibleMonths.length]);

  useEffect(() => {
    if (visibleMonths.length === 0) {
      setPlaying(false);
      setIdx(0);
      return;
    }
    setIdx((v) => Math.min(Math.max(0, v), visibleMonths.length - 1));
  }, [visibleMonths.length]);

  const regime = regimes.find((r) => r.month.slice(0, 7) === month.slice(0, 7));
  const alloc = allocations.find((a) => a.month.slice(0, 7) === month.slice(0, 7));
  const decision = decisions.find((d) => d.month.slice(0, 7) === month.slice(0, 7));
  const targets = getPortfolioTargets(month).slice(0, 12);
  const monthTrades = trades.filter((t) => t.month.slice(0, 7) === month.slice(0, 7) && t.signal_type !== "HOLD").slice(0, 14);
  const news = getNewsArticlesByMonth(month, 6);
  const decisionNews = decision?.supporting_news?.length ? decision.supporting_news : news;
  const curve = bt.filter((b) => b.month >= fromMonth && b.month <= month);

  const factorRows: [FactorName, number][] = alloc
    ? [
        ["Momentum", alloc.momentum_weight],
        ["Value", alloc.value_weight],
        ["Quality", alloc.quality_weight],
        ["Low Volatility", alloc.low_volatility_weight],
      ]
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Historical Simulation Replay</h2>
        <p className="text-sm text-slate-500 mt-1">Replay month-by-month regime detection, factor allocation, rebalance actions, news evidence, and portfolio path</p>
      </div>

      <Card title="Replay Controls" subtitle={`${fromMonth || months[0] || ""} to ${toMonth || months[months.length - 1] || ""}`}>
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3">
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
              From
              <select
                value={fromMonth}
                onChange={(e) => {
                  const next = e.target.value;
                  setFromMonth(next);
                  if (toMonth && next > toMonth) setToMonth(next);
                  setIdx(0);
                }}
                className="mt-1 w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {months.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
              To
              <select
                value={toMonth}
                onChange={(e) => {
                  const next = e.target.value;
                  setToMonth(next);
                  if (fromMonth && next < fromMonth) setFromMonth(next);
                  setIdx(0);
                }}
                className="mt-1 w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {months.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <button
              className="self-end px-3 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm font-medium"
              onClick={() => {
                setFromMonth(months[0] ?? "");
                setToMonth(months[months.length - 1] ?? "");
                setIdx(Math.max(0, months.length - 1));
              }}
            >
              Full Range
            </button>
          </div>

          <div className="flex flex-col lg:flex-row gap-4 lg:items-center">
            <div className="flex gap-2">
            <button className="px-3 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium flex items-center gap-2" onClick={() => setPlaying((p) => !p)}>
              {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}{playing ? "Pause" : "Play"}
            </button>
            <button className="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm font-medium flex items-center gap-2" onClick={() => setIdx((v) => Math.min(visibleMonths.length - 1, v + 1))}>
              <StepForward className="w-4 h-4" />Next
            </button>
            <button className="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm font-medium flex items-center gap-2" onClick={() => setIdx(0)}>
              <RotateCcw className="w-4 h-4" />Reset
            </button>
            </div>
            <div className="flex-1">
              <input className="w-full" type="range" min={0} max={Math.max(0, visibleMonths.length - 1)} value={Math.min(idx, Math.max(0, visibleMonths.length - 1))} onChange={(e) => setIdx(Number(e.target.value))} />
              <div className="flex justify-between text-xs text-slate-500 mt-1"><span>{visibleMonths[0]}</span><span className="font-semibold text-slate-900">{month}</span><span>{visibleMonths[visibleMonths.length - 1]}</span></div>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Detected Regime" value={regime ? <RegimeBadge regime={regime.regime_label} /> : "--"} subvalue={`Confidence ${formatPercent(regime?.regime_confidence ?? 0)}`} icon={<Target className="w-5 h-5" />} color="blue" />
        <StatCard label="Decision Gate" value={decision ? <DecisionBadge decision={decision.decision} /> : "--"} subvalue={decision?.reason.slice(0, 42) ?? "No decision"} icon={<StepForward className="w-5 h-5" />} color="amber" />
        <StatCard label="Portfolio Value" value={(curve[curve.length - 1]?.portfolio_value ?? 100).toFixed(2)} subvalue="Dynamic strategy" icon={<TrendingUp className="w-5 h-5" />} color="green" />
        <StatCard label="News Evidence" value={decisionNews.length} subvalue={`Stress ${formatPercent(decision?.news_stress_score ?? 0)}`} icon={<Newspaper className="w-5 h-5" />} color="purple" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Factor Allocation" subtitle={`Weights for ${month}`}>
          <div className="space-y-4">
            {factorRows.map(([factor, weight]) => (
              <div key={factor}>
                <div className="flex justify-between text-sm mb-1"><span>{factor}</span><span className="font-semibold">{formatPercent(weight)}</span></div>
                <ProgressBar value={weight} color={getFactorColor(factor)} />
              </div>
            ))}
          </div>
        </Card>
        <Card title="Portfolio Path" subtitle="Dynamic strategy up to selected month" className="lg:col-span-2">
          <LineChart data={[{ label: "Dynamic", values: curve.map((c) => c.portfolio_value) }]} xLabels={curve.map((c) => c.month)} colors={["#3b82f6"]} yFormat={(v) => v.toFixed(0)} height={260} />
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Rebalance Actions" subtitle="BUY / SELL / ADD / REDUCE generated at this month">
          <Table
            columns={[
              { key: "signal_type", label: "Action" },
              { key: "symbol", label: "Stock" },
              { key: "primary_factor", label: "Factor" },
              { key: "new_weight", label: "New Wt", align: "right" },
              { key: "signal_price", label: "Price", align: "right" },
            ]}
            data={monthTrades.map((t) => ({ ...t, signal_type: <SignalBadge signal={t.signal_type} />, new_weight: formatPercent(t.new_weight) }))}
            maxHeight="360px"
          />
        </Card>
        <Card title="Top Target Holdings" subtitle="Highest target weights after rebalance">
          <Table
            columns={[
              { key: "symbol", label: "Stock" },
              { key: "target_weight", label: "Weight", align: "right" },
              { key: "factor_sources", label: "Factors" },
              { key: "combined_score", label: "Score", align: "right" },
            ]}
            data={targets.map((t) => ({ ...t, target_weight: formatPercent(t.target_weight), factor_sources: t.factor_sources.join(", ") }))}
            maxHeight="360px"
          />
        </Card>
      </div>

      <Card title="News Evidence For Selected Month" subtitle="Clickable RSS articles matched to the replay month">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {decisionNews.length === 0 ? <div className="text-sm text-slate-500">No fetched RSS stories for this historical month. Current RSS feeds mainly cover recent dates.</div> : decisionNews.map((a) => (
            <a key={a.article_id} href={a.url} target="_blank" rel="noreferrer" className="rounded-lg border border-slate-200 p-4 hover:border-blue-300 hover:bg-blue-50/40 transition-colors">
              <div className="text-xs text-slate-500 mb-2">{a.source} - {a.published_date}</div>
              <div className="text-sm font-semibold text-slate-900 line-clamp-2">{a.title}</div>
              <div className="text-xs text-slate-500 mt-2 line-clamp-2">{a.summary}</div>
            </a>
          ))}
        </div>
      </Card>
    </div>
  );
}
