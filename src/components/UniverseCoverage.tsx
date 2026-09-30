import { Badge, Card, Table } from "@/components/UI";
import { excludedSymbols } from "@/lib/product";

export function UniverseCoverage({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="flex flex-wrap gap-2">
        <Badge color="green">189 usable stocks</Badge>
        <Badge color="amber">11 excluded symbols</Badge>
        <Badge color="slate">Current clean universe</Badge>
      </div>
    );
  }

  return (
    <Card title="Universe Coverage" subtitle="Model coverage and exclusions">
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg bg-emerald-50 p-3">
          <p className="text-xs text-emerald-700">Usable model universe</p>
          <p className="mt-1 text-xl font-bold text-emerald-950">189</p>
        </div>
        <div className="rounded-lg bg-amber-50 p-3">
          <p className="text-xs text-amber-700">Excluded symbols</p>
          <p className="mt-1 text-xl font-bold text-amber-950">11</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs text-slate-600">Source universe</p>
          <p className="mt-1 text-xl font-bold text-slate-950">Nifty 200</p>
        </div>
      </div>
      <p className="mb-4 text-sm leading-6 text-slate-600">
        The excluded names are not used in model targets or backtests until enough reliable historical price and
        fundamental data exists. A latest fundamentals row alone is not enough for model inclusion.
      </p>
      <Table
        maxHeight="260px"
        columns={[
          { key: "symbol", label: "Symbol" },
          { key: "reason", label: "Reason" },
        ]}
        data={excludedSymbols.map((symbol) => ({
          symbol,
          reason: "Incomplete or unreliable historical price/fundamental coverage",
        }))}
      />
    </Card>
  );
}
