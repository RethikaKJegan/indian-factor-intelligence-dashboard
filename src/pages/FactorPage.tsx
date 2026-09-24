import { Card, StatCard, Table, Badge } from "@/components/UI";
import { LineChart, BarChart, Heatmap } from "@/components/Charts";
import {
  getTopStocksByFactor,
  getFactorReturns,
  getLatestDiagnostics,
  getFactorDiagnostics,
  formatPercent,
  formatNumber,
  getFactorColor,
} from "@/lib/data";
import { Layers, TrendingUp, Activity, Grid3x3 } from "lucide-react";
import type { FactorName } from "@/types";

const FACTORS: FactorName[] = ["Momentum", "Value", "Quality", "Low Volatility"];

export function FactorPage() {
  const factorReturns = getFactorReturns();
  const latestDiag = getLatestDiagnostics();
  const allDiag = getFactorDiagnostics();

  if (factorReturns.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <p className="text-sm">No factor data available.</p>
      </div>
    );
  }

  const xLabels = factorReturns.map((f) => f.month);
  const frData = [
    { label: "Momentum", values: factorReturns.map((f) => f.momentum_return) },
    { label: "Value", values: factorReturns.map((f) => f.value_return) },
    { label: "Quality", values: factorReturns.map((f) => f.quality_return) },
    { label: "Low Vol", values: factorReturns.map((f) => f.low_volatility_return) },
  ];

  // Cumulative returns
  const cumData = FACTORS.map((f, i) => {
    const key = ["momentum_return", "value_return", "quality_return", "low_volatility_return"][i];
    let cum = 0;
    return {
      label: f,
      values: factorReturns.map((fr) => {
        cum *= 1 + (fr as any)[key];
        cum += (fr as any)[key];
        return cum;
      }),
    };
  });

  // Correlation matrix
  let corrMatrix: number[][] = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
  let corrLabels = ["Mom", "Val", "Qual", "LowVol"];
  if (latestDiag?.correlation_matrix) {
    const cm = latestDiag.correlation_matrix;
    const keys = ["momentum", "value", "quality", "low_volatility"];
    corrMatrix = keys.map((k1) => keys.map((k2) => cm[k1]?.[k2] ?? 0));
  }

  // Risk diagnostics
  const riskData = allDiag.map((d) => ({
    label: d.month,
    value: d.redundancy_score,
    color: "#f59e0b",
  }));

  const effFactorsData = allDiag.map((d) => ({
    label: d.month,
    value: d.effective_independent_factors,
    color: "#3b82f6",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Factor Dashboard</h2>
        <p className="text-sm text-slate-500 mt-1">
          Four-factor model: Momentum, Value, Quality, Low Volatility — Top 10 per factor
        </p>
      </div>

      {/* Top Stocks by Factor */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {FACTORS.map((factor) => {
          const topStocks = getTopStocksByFactor(factor);
          return (
            <Card key={factor} title={`Top 10 — ${factor}`} subtitle="Latest month selected stocks">
              <Table
                columns={[
                  { key: "rank", label: "#", align: "center", width: "40px" },
                  { key: "symbol", label: "Symbol" },
                  { key: "factor_score", label: "Score", align: "right" },
                ]}
                data={topStocks.map((s) => ({
                  rank: s.factor_rank,
                  symbol: s.symbol,
                  factor_score: formatNumber(s.factor_score, 3),
                }))}
                maxHeight="280px"
              />
            </Card>
          );
        })}
      </div>

      {/* Factor Returns Chart */}
      <Card title="Factor Monthly Returns" subtitle="Next-month returns of factor baskets">
        <LineChart
          data={frData}
          xLabels={xLabels}
          colors={["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b"]}
          yFormat={(v) => formatPercent(v, 1)}
          height={280}
        />
      </Card>

      {/* Cumulative Returns */}
      <Card title="Cumulative Factor Returns" subtitle="Growth of 1 unit invested in each factor">
        <LineChart
          data={cumData}
          xLabels={xLabels}
          colors={["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b"]}
          yFormat={(v) => formatNumber(v, 1)}
          height={280}
        />
      </Card>

      {/* Diagnostics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Factor Correlation Matrix" subtitle="Latest month inter-factor correlations">
          <Heatmap
            rows={corrLabels}
            cols={corrLabels}
            values={corrMatrix}
            cellFormat={(v) => v.toFixed(2)}
          />
        </Card>

        <div className="space-y-6">
          <Card title="Risk Diagnostics" subtitle="Latest month factor risk metrics">
            <div className="grid grid-cols-2 gap-4">
              <StatCard
                label="Max Eigenvalue Share"
                value={latestDiag ? formatPercent(latestDiag.max_eigenvalue_share) : "—"}
                subvalue="Concentration of risk"
                icon={<Activity className="w-5 h-5" />}
                color="amber"
              />
              <StatCard
                label="Effective Factors"
                value={latestDiag ? formatNumber(latestDiag.effective_independent_factors) : "—"}
                subvalue="Independent signals"
                icon={<Layers className="w-5 h-5" />}
                color="blue"
              />
              <StatCard
                label="Risk Concentration"
                value={latestDiag ? formatPercent(latestDiag.risk_concentration_score) : "—"}
                subvalue="Portfolio risk focus"
                icon={<Grid3x3 className="w-5 h-5" />}
                color="red"
              />
              <StatCard
                label="Redundancy Score"
                value={latestDiag ? formatPercent(latestDiag.redundancy_score) : "—"}
                subvalue="Factor overlap"
                icon={<TrendingUp className="w-5 h-5" />}
                color="amber"
              />
            </div>
          </Card>
        </div>
      </div>

      {/* Redundancy over time */}
      <Card title="Redundancy Score Over Time" subtitle="Higher values indicate more factor overlap">
        <BarChart
          data={riskData.slice(-24)}
          yFormat={(v) => formatPercent(v, 0)}
          height={250}
        />
      </Card>
    </div>
  );
}
