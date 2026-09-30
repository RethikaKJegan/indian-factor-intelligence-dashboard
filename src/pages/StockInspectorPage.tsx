import { useMemo, useState } from "react";
import { Badge, Card, SignalBadge, Table } from "@/components/UI";
import { formatPercent, getSignalEvents, getStockPrices, getStockSymbols } from "@/lib/data";
import { buildTradePlan, excludedSymbols, formatCurrency, loadUserCash, loadUserHoldings } from "@/lib/product";

export function StockInspectorPage() {
  const symbols = getStockSymbols();
  const [symbol, setSymbol] = useState(symbols.includes("PFC") ? "PFC" : symbols[0] || "");
  const normalized = symbol.trim().toUpperCase();
  const preview = buildTradePlan(loadUserHoldings(), loadUserCash());
  const row = preview.rows.find((item) => item.symbol === normalized);
  const signals = useMemo(() => getSignalEvents(normalized).slice(-20).reverse(), [normalized]);
  const prices = getStockPrices(normalized);
  const latestPrice = prices[prices.length - 1]?.adjusted_close || prices[prices.length - 1]?.close || row?.latestPrice || 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Stock Inspector</h2>
        <p className="mt-1 text-sm text-slate-500">
          Search one stock and see the model action, your quantity, and the signal history.
        </p>
      </div>

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-xs font-medium text-slate-600">
            Search symbol
            <input
              list="stock-symbols"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value.toUpperCase())}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
              placeholder="PFC"
            />
          </label>
          <datalist id="stock-symbols">
            {symbols.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <div className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">
            Latest price: <span className="font-semibold text-slate-900">{formatCurrency(latestPrice)}</span>
          </div>
        </div>
      </Card>

      {row ? (
        <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <Card title={`${normalized} Action`} subtitle="Personalized using saved holdings">
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                {row.action === "PAUSED" || row.action === "IGNORED" ? (
                  <Badge color={row.action === "PAUSED" ? "amber" : "slate"}>{row.action}</Badge>
                ) : (
                  <SignalBadge signal={row.action} />
                )}
                <Badge color="slate">{row.sector}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Metric label="You have" value={`${row.currentQuantity} shares`} />
                <Metric label="Model wants" value={`${row.targetQuantity} shares`} />
                <Metric
                  label="Final today"
                  value={
                    row.finalTradeQuantity > 0
                      ? `Buy ${row.finalTradeQuantity}`
                      : row.finalTradeQuantity < 0
                      ? `Sell ${Math.abs(row.finalTradeQuantity)}`
                      : "No trade"
                  }
                />
                <Metric label="Trade value" value={formatCurrency(row.tradeValue)} />
              </div>
              <div className="rounded-lg bg-slate-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Why</p>
                <p className="mt-2 text-sm leading-6 text-slate-700">{row.reason}</p>
                <p className="mt-2 text-xs text-slate-500">Factor source: {row.factorReason}</p>
                <p className="mt-1 text-xs text-slate-500">Target weight: {formatPercent(row.targetWeight, 2)}</p>
              </div>
            </div>
          </Card>

          <Card title="Signal History" subtitle="Latest monthly model actions">
            <Table
              maxHeight="420px"
              columns={[
                { key: "month", label: "Month" },
                { key: "signal", label: "Signal", align: "center" },
                { key: "price", label: "Price", align: "right" },
                { key: "old", label: "Old Wt", align: "right" },
                { key: "new", label: "New Wt", align: "right" },
                { key: "factor", label: "Factor" },
              ]}
              data={signals.map((signal) => ({
                month: signal.month,
                signal: <SignalBadge signal={signal.signal_type} />,
                price: formatCurrency(signal.signal_price),
                old: formatPercent(signal.old_weight, 2),
                new: formatPercent(signal.new_weight, 2),
                factor: signal.primary_factor,
              }))}
            />
          </Card>
        </div>
      ) : (
        <Card title="Unavailable Symbol">
          {excludedSymbols.includes(normalized) ? (
            <div className="space-y-3 text-sm leading-6 text-slate-600">
              <p>
                {normalized} is one of the 11 excluded Nifty 200 symbols. It is not used by the model because reliable
                historical price or fundamental data is incomplete.
              </p>
              <p>
                A latest/current fundamentals row alone is not enough. The stock needs enough monthly price history and
                usable historical fundamentals before it can enter backtests or portfolio targets.
              </p>
            </div>
          ) : (
            <p className="text-sm leading-6 text-slate-600">
              This symbol is not available in the current 189-stock model universe. It may be outside the usable Nifty
              200 modelling set or missing from the shipped data snapshot.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-base font-bold text-slate-900">{value}</p>
    </div>
  );
}
