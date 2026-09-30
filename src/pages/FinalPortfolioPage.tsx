import { AlertTriangle } from "lucide-react";
import { Badge, Card, Table } from "@/components/UI";
import { formatPercent } from "@/lib/data";
import {
  buildTradePlan,
  formatCurrency,
  getCurrentSectorExposure,
  getDecisionSnapshot,
  loadUserCash,
  loadUserHoldings,
} from "@/lib/product";

export function FinalPortfolioPage() {
  const preview = buildTradePlan(loadUserHoldings(), loadUserCash());
  const { decision, risk } = getDecisionSnapshot();
  const isRetain = (decision?.decision || "RETAIN") === "RETAIN";
  const rows = preview.rows
    .filter((row) => row.currentQuantity + row.finalTradeQuantity > 0)
    .sort(
      (a, b) =>
        (b.currentQuantity + b.finalTradeQuantity) * b.latestPrice -
        (a.currentQuantity + a.finalTradeQuantity) * a.latestPrice
    );

  const tableRows = rows.slice(0, 80).map((row) => {
    const finalQty = row.currentQuantity + row.finalTradeQuantity;
    const finalValue = finalQty * row.latestPrice;
    return {
      stock: <span className="font-semibold text-slate-900">{row.symbol}</span>,
      quantity: `${finalQty} shares`,
      value: formatCurrency(finalValue),
      weight: formatPercent(finalValue / Math.max(preview.investedAfter, 1), 2),
      sector: row.sector,
      reason: row.factorReason,
    };
  });

  const sectorRows = getCurrentSectorExposure()
    .slice(0, 10)
    .map((sector) => ({
      sector: sector.sector,
      weight: formatPercent(sector.weight, 1),
      stocks: sector.stock_count,
    }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Final Portfolio</h2>
        <p className="mt-1 text-sm text-slate-500">
          Expected portfolio state after the monthly decision gate and today&apos;s execution guardrail.
        </p>
      </div>

      <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
        <p className="font-semibold">
          Monthly decision: {decision?.decision || "RETAIN"} · Today&apos;s guardrail: {risk.executionMode}
        </p>
        <p className="mt-1">
          {isRetain
            ? "Because the monthly decision is RETAIN, this page shows your saved holdings with no automatic rebalance applied. Raw model targets remain visible only in research/trust views."
            : "This page shows your portfolio after executing only the trades allowed by the monthly decision and daily risk overlay."}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Summary label="Final value" value={formatCurrency(preview.portfolioValue)} />
        <Summary label="Invested after" value={formatCurrency(preview.investedAfter)} />
        <Summary label="Cash left" value={formatCurrency(preview.cashAfter)} />
        <Summary label="Stocks held" value={String(preview.stockCountAfter)} />
      </div>

      <Card title="Portfolio Receipt" subtitle="Plain-English summary after trades">
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-lg bg-slate-50 p-4">
            <p className="text-xs text-slate-500">Largest holding</p>
            <p className="mt-1 text-lg font-bold text-slate-900">
              {preview.largestHolding?.symbol || "—"}
            </p>
            <p className="text-xs text-slate-500">
              {preview.largestHolding
                ? formatCurrency(
                    (preview.largestHolding.currentQuantity + preview.largestHolding.finalTradeQuantity) *
                      preview.largestHolding.latestPrice
                  )
                : "No holding"}
            </p>
          </div>
          <div className="rounded-lg bg-slate-50 p-4">
            <p className="text-xs text-slate-500">Largest sector</p>
            <p className="mt-1 text-lg font-bold text-slate-900">
              {preview.largestSector?.sector || "—"}
            </p>
            <p className="text-xs text-slate-500">
              {preview.largestSector ? formatPercent(preview.largestSector.weight, 1) : "No sector"}
            </p>
          </div>
          <div className="rounded-lg bg-slate-50 p-4">
            <p className="text-xs text-slate-500">Portfolio changes</p>
            <p className="mt-1 text-lg font-bold text-slate-900">
              {preview.newStocks} new / {preview.fullExits} exits
            </p>
            <p className="text-xs text-slate-500">After overlay and tiny-trade filter</p>
          </div>
        </div>
      </Card>

      {preview.warnings.length > 0 && (
        <Card title="Warnings" subtitle="These are practical execution warnings, not decorative stats">
          <div className="space-y-2">
            {preview.warnings.map((warning) => (
              <div key={warning} className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{warning}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_0.8fr]">
        <Card
          title={isRetain ? "Current Saved Holdings" : "Final Holdings"}
          subtitle={isRetain ? "No automatic rebalance is applied while decision is RETAIN" : "Top positions after today's executable plan"}
        >
          <Table
            maxHeight="620px"
            columns={[
              { key: "stock", label: "Stock" },
              { key: "quantity", label: "Quantity", align: "right" },
              { key: "value", label: "Value", align: "right" },
              { key: "weight", label: "Weight", align: "right" },
              { key: "sector", label: "Sector" },
              { key: "reason", label: "Reason" },
            ]}
            data={tableRows}
          />
        </Card>

        <Card
          title={isRetain ? "Raw Target Sector Exposure" : "Target Sector Exposure"}
          subtitle={isRetain ? "Transparency only; not an executable allocation while decision is RETAIN" : "Model target sector view"}
        >
          <Table
            maxHeight="620px"
            columns={[
              { key: "sector", label: "Sector" },
              { key: "weight", label: "Weight", align: "right" },
              { key: "stocks", label: "Stocks", align: "right" },
            ]}
            data={sectorRows}
          />
          <div className="mt-4">
            <Badge color="slate">189-stock model universe</Badge>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-bold text-slate-900">{value}</p>
    </div>
  );
}
