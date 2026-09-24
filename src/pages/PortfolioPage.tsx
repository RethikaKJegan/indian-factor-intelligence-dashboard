import { Card, StatCard, Table, SignalBadge, RegimeBadge, ProgressBar } from "@/components/UI";
import { DonutChart, BarChart } from "@/components/Charts";
import {
  getPortfolioTargets,
  getLatestRebalanceTrades,
  getSectorExposure,
  getFactorExposure,
  getLatestAllocation,
  formatPercent,
  formatNumber,
  getFactorColor,
  getRegimeColor,
} from "@/lib/data";
import { Briefcase, TrendingUp, RotateCw, Layers, PieChart } from "lucide-react";
import type { FactorName } from "@/types";

const FACTORS: FactorName[] = ["Momentum", "Value", "Quality", "Low Volatility"];

export function PortfolioPage() {
  const targets = getPortfolioTargets();
  const trades = getLatestRebalanceTrades();
  const latestAlloc = getLatestAllocation();
  const sectorExposure = getSectorExposure(targets);
  const factorExposure = getFactorExposure(targets);

  if (targets.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <p className="text-sm">No portfolio data available.</p>
      </div>
    );
  }

  const buyCount = trades.filter((t) => t.signal_type === "BUY").length;
  const sellCount = trades.filter((t) => t.signal_type === "SELL").length;
  const addCount = trades.filter((t) => t.signal_type === "ADD").length;
  const reduceCount = trades.filter((t) => t.signal_type === "REDUCE").length;

  const sectorData = sectorExposure.slice(0, 8).map((s) => ({
    label: s.sector.slice(0, 12),
    value: s.weight,
    color: getRegimeColor(s.sector),
  }));

  const factorData = factorExposure.map((f) => ({
    label: f.factor,
    value: f.weight,
    color: getFactorColor(f.factor),
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Portfolio Dashboard</h2>
        <p className="text-sm text-slate-500 mt-1">
          Current target portfolio with rebalance signals and sector/factor exposure
        </p>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Positions"
          value={targets.length}
          subvalue="Active stocks"
          icon={<Briefcase className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="BUY Signals"
          value={buyCount}
          subvalue="New additions"
          icon={<TrendingUp className="w-5 h-5" />}
          color="green"
        />
        <StatCard
          label="SELL Signals"
          value={sellCount}
          subvalue="Full exits"
          icon={<TrendingUp className="w-5 h-5" />}
          color="red"
        />
        <StatCard
          label="Rebalance Count"
          value={trades.length}
          subvalue={`${addCount} ADD, ${reduceCount} REDUCE`}
          icon={<RotateCw className="w-5 h-5" />}
          color="amber"
        />
      </div>

      {/* Portfolio Table + Sector Donut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Current Target Portfolio" subtitle={`${targets.length} positions — ${targets[0]?.month || ""}`} className="lg:col-span-2">
          <Table
            columns={[
              { key: "symbol", label: "Symbol" },
              { key: "target_weight", label: "Weight", align: "right" },
              { key: "combined_score", label: "Score", align: "right" },
              { key: "factor_sources", label: "Factors" },
              { key: "regime_label", label: "Regime" },
            ]}
            data={targets
              .sort((a, b) => b.target_weight - a.target_weight)
              .map((t) => ({
                symbol: t.symbol,
                target_weight: formatPercent(t.target_weight),
                combined_score: formatNumber(t.combined_score, 3),
                factor_sources: t.factor_sources.join(", "),
                regime_label: <RegimeBadge regime={t.regime_label} />,
              }))}
            maxHeight="450px"
          />
        </Card>

        <Card title="Sector Exposure" subtitle="Weight by sector">
          <DonutChart
            data={sectorData}
            centerLabel="Sectors"
            centerValue={String(sectorExposure.length)}
          />
        </Card>
      </div>

      {/* Factor Exposure + Rebalance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Factor Exposure" subtitle="Aggregated factor weights in portfolio">
          <div className="space-y-3 max-w-md">
            {FACTORS.map((f) => {
              const exp = factorExposure.find((e) => e.factor === f);
              return (
                <div key={f} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 w-32">
                    <div className="w-2.5 h-2.5 rounded-sm" style={{ background: getFactorColor(f) }} />
                    <span className="text-sm text-slate-700">{f}</span>
                  </div>
                  <div className="flex items-center gap-3 flex-1 ml-4">
                    <div className="flex-1">
                      <ProgressBar value={exp?.weight || 0} color={getFactorColor(f)} />
                    </div>
                    <span className="text-sm font-medium text-slate-700 tabular-nums w-14 text-right">
                      {exp ? formatPercent(exp.weight) : "—"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          {latestAlloc && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <p className="text-xs text-slate-500 mb-2">Latest turnover: {formatPercent(latestAlloc.turnover)}</p>
            </div>
          )}
        </Card>

        <Card title="Latest Rebalance Trades" subtitle={`${trades.length} signals this month`}>
          <Table
            columns={[
              { key: "symbol", label: "Symbol" },
              { key: "signal_type", label: "Signal" },
              { key: "old_weight", label: "Old", align: "right" },
              { key: "new_weight", label: "New", align: "right" },
              { key: "primary_factor", label: "Factor" },
            ]}
            data={trades
              .filter((t) => t.signal_type !== "HOLD")
              .map((t) => ({
                symbol: t.symbol,
                signal_type: <SignalBadge signal={t.signal_type} />,
                old_weight: formatPercent(t.old_weight),
                new_weight: formatPercent(t.new_weight),
                primary_factor: t.primary_factor,
              }))}
            maxHeight="450px"
          />
        </Card>
      </div>

      {/* Sector Breakdown Bar */}
      <Card title="Sector Weight Breakdown" subtitle="Top sectors by portfolio weight">
        <BarChart
          data={sectorExposure.slice(0, 10).map((s) => ({
            label: s.sector.slice(0, 15),
            value: s.weight,
            color: "#3b82f6",
          }))}
          yFormat={(v) => formatPercent(v, 1)}
          height={250}
        />
      </Card>
    </div>
  );
}
