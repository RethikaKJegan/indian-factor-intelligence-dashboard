import { useState, useMemo } from "react";
import { Card, Table, SignalBadge, RegimeBadge, EmptyState } from "@/components/UI";
import {
  getStockSymbols,
  getStockPrices,
  getSignalEvents,
  formatPercent,
  formatNumber,
  getSignalColor,
} from "@/lib/data";
import { CandlestickChart, Search } from "lucide-react";
import type { SignalType, StockPricePoint, StockSignalEvent } from "@/types";

const SIGNAL_ORDER: SignalType[] = ["BUY", "ADD", "REDUCE", "SELL"];
type RangePreset = "1Y" | "3Y" | "5Y" | "All" | "Custom";
type DensityMode = "all" | "buy_sell" | "latest_25";

export function SignalsPage() {
  const symbols = getStockSymbols();
  const [selectedSymbol, setSelectedSymbol] = useState<string>(symbols[0] || "");
  const [search, setSearch] = useState("");
  const [rangePreset, setRangePreset] = useState<RangePreset>("3Y");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [density, setDensity] = useState<DensityMode>("buy_sell");
  const [signalFilters, setSignalFilters] = useState<Record<SignalType, boolean>>({
    BUY: true,
    ADD: false,
    HOLD: false,
    REDUCE: false,
    SELL: true,
  });

  const filteredSymbols = useMemo(
    () => symbols.filter((s) => s.toLowerCase().includes(search.toLowerCase())).slice(0, 100),
    [symbols, search]
  );

  const prices = getStockPrices(selectedSymbol);
  const signals = getSignalEvents(selectedSymbol);
  const months = useMemo(
    () => Array.from(new Set(prices.map((p) => p.month.slice(0, 7)))).sort(),
    [prices]
  );
  const range = useMemo(() => {
    const first = months[0] ?? "";
    const last = months[months.length - 1] ?? "";
    if (rangePreset === "Custom") {
      const from = customFrom || first;
      const to = customTo || last;
      return from <= to ? { from, to } : { from: to, to: from };
    }
    if (rangePreset === "All") return { from: first, to: last };
    const count = rangePreset === "1Y" ? 12 : rangePreset === "3Y" ? 36 : 60;
    return { from: months[Math.max(0, months.length - count)] ?? first, to: last };
  }, [months, rangePreset, customFrom, customTo]);

  const filteredPrices = useMemo(
    () => prices.filter((p) => p.month.slice(0, 7) >= range.from && p.month.slice(0, 7) <= range.to),
    [prices, range]
  );

  const filteredSignals = useMemo(() => {
    const allowed = density === "buy_sell"
      ? new Set<SignalType>(["BUY", "SELL"])
      : new Set(SIGNAL_ORDER.filter((s) => signalFilters[s]));
    let rows = signals
      .filter((s) => s.month.slice(0, 7) >= range.from && s.month.slice(0, 7) <= range.to)
      .filter((s) => allowed.has(s.signal_type));
    if (density === "latest_25") rows = rows.slice(-25);
    return rows;
  }, [signals, range, density, signalFilters]);

  if (symbols.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <EmptyState message="No stock data available. Run the pipeline to generate signals." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Stock Signal Chart</h2>
        <p className="text-sm text-slate-500 mt-1">
          Monthly positional portfolio signals overlaid on price history
        </p>
      </div>

      <Card>
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
          <div className="flex items-center gap-2 flex-1">
            <Search className="w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search symbol..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <select
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 min-w-[200px]"
          >
            {filteredSymbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </Card>

      <Card title="Chart Controls" subtitle="Zoom the positional signal history and choose which rebalance actions appear on the chart">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.2fr_1fr] gap-4">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-2">Quick Range</div>
            <div className="flex flex-wrap gap-2">
              {(["1Y", "3Y", "5Y", "All"] as RangePreset[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setRangePreset(r)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium ${rangePreset === r ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-2">Custom Range</div>
            <div className="grid grid-cols-2 gap-2">
              <select
                value={customFrom || months[0] || ""}
                onChange={(e) => {
                  setCustomFrom(e.target.value);
                  setRangePreset("Custom");
                }}
                className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {months.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <select
                value={customTo || months[months.length - 1] || ""}
                onChange={(e) => {
                  setCustomTo(e.target.value);
                  setRangePreset("Custom");
                }}
                className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {months.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-2">Density</div>
            <select
              value={density}
              onChange={(e) => setDensity(e.target.value as DensityMode)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="buy_sell">BUY + SELL only</option>
              <option value="all">Show selected actions</option>
              <option value="latest_25">Latest 25 selected actions</option>
            </select>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-slate-100">
          {SIGNAL_ORDER.map((sig) => (
            <button
              key={sig}
              onClick={() => setSignalFilters((prev) => ({ ...prev, [sig]: !prev[sig] }))}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${signalFilters[sig] ? "text-white border-transparent" : "text-slate-600 border-slate-200 bg-white"}`}
              style={signalFilters[sig] ? { background: getSignalColor(sig) } : undefined}
            >
              {sig}
            </button>
          ))}
        </div>
      </Card>

      <Card title={`${selectedSymbol} — Price & Signals`} subtitle={`${filteredPrices.length} months, ${filteredSignals.length} visible signals (${range.from} to ${range.to})`}>
        {filteredPrices.length > 0 ? (
          <>
            <SignalPriceChart symbol={selectedSymbol} prices={filteredPrices} signals={filteredSignals} height={430} />
            <div className="flex flex-wrap gap-4 justify-center mt-4 pt-4 border-t border-slate-100">
              {SIGNAL_ORDER.map((sig) => (
                <div key={sig} className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ background: getSignalColor(sig) }}
                  />
                  <span className="text-xs text-slate-600">{sig}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <EmptyState message={`No price data for ${selectedSymbol}`} icon={<CandlestickChart className="w-8 h-8 text-slate-300" />} />
        )}
      </Card>

      <Card title={`${selectedSymbol} — Signal History`} subtitle="Monthly positional portfolio signals">
        {filteredSignals.length > 0 ? (
          <Table
            columns={[
              { key: "month", label: "Month" },
              { key: "signal_type", label: "Signal" },
              { key: "signal_price", label: "Price", align: "right" },
              { key: "old_weight", label: "Old Wt", align: "right" },
              { key: "new_weight", label: "New Wt", align: "right" },
              { key: "weight_change", label: "Change", align: "right" },
              { key: "regime", label: "Regime" },
              { key: "primary_factor", label: "Factor" },
              { key: "reason", label: "Reason" },
            ]}
            data={filteredSignals.map((s) => ({
              month: s.month,
              signal_type: <SignalBadge signal={s.signal_type} />,
              signal_price: formatNumber(s.signal_price),
              old_weight: formatPercent(s.old_weight),
              new_weight: formatPercent(s.new_weight),
              weight_change: `${s.weight_change >= 0 ? "+" : ""}${formatPercent(s.weight_change)}`,
              regime: <RegimeBadge regime={s.regime} />,
              primary_factor: s.primary_factor,
              reason: s.reason,
            }))}
            maxHeight="400px"
          />
        ) : (
          <EmptyState message={`No signals for ${selectedSymbol}`} />
        )}
      </Card>
    </div>
  );
}

function SignalPriceChart({
  symbol,
  prices,
  signals,
  height = 420,
}: {
  symbol: string;
  prices: StockPricePoint[];
  signals: StockSignalEvent[];
  height?: number;
}) {
  const width = 1000;
  const pad = { top: 38, right: 76, bottom: 54, left: 68 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  const priceRows = prices.map((p) => ({
    month: p.month.slice(0, 7),
    close: Number(p.adjusted_close || p.close || 0),
  })).filter((p) => Number.isFinite(p.close) && p.close > 0);

  if (!priceRows.length) {
    return <div className="flex items-center justify-center text-sm text-slate-500" style={{ height }}>No chart data</div>;
  }

  const monthIndex = new Map(priceRows.map((p, i) => [p.month, i]));
  const signalRows = signals
    .filter((s) => SIGNAL_ORDER.includes(s.signal_type) && monthIndex.has(s.month.slice(0, 7)))
    .map((s, i) => ({ ...s, monthKey: s.month.slice(0, 7), rowOffset: i % 4 }));

  const allValues = [
    ...priceRows.map((p) => p.close),
    ...signalRows.map((s) => Number(s.signal_price || 0)).filter((v) => v > 0),
  ];
  const minY = Math.min(...allValues);
  const maxY = Math.max(...allValues);
  const yRange = maxY - minY || 1;
  const yPad = yRange * 0.16;
  const yMin = Math.max(0, minY - yPad);
  const yMax = maxY + yPad;
  const xStep = chartW / Math.max(1, priceRows.length - 1);

  const xForIndex = (i: number) => pad.left + i * xStep;
  const yForValue = (v: number) => pad.top + chartH - ((v - yMin) / (yMax - yMin)) * chartH;
  const points = priceRows.map((p, i) => `${xForIndex(i)},${yForValue(p.close)}`).join(" ");

  const yTicks = 5;
  const yTickValues = Array.from({ length: yTicks + 1 }, (_, i) => yMin + ((yMax - yMin) * i) / yTicks);
  const xTickSkip = Math.max(1, Math.ceil(priceRows.length / 10));
  const firstMonth = priceRows[0]?.month ?? "";
  const lastMonth = priceRows[priceRows.length - 1]?.month ?? "";

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto min-w-[760px]" preserveAspectRatio="xMidYMid meet">
        <rect x={0} y={0} width={width} height={height} rx={10} fill="#ffffff" />
        <text x={pad.left} y={22} className="fill-slate-900 text-[15px] font-bold">{symbol} Signal Chart</text>
        <text x={width - pad.right} y={22} textAnchor="end" className="fill-slate-500 text-[12px]">{firstMonth} to {lastMonth}</text>

        {yTickValues.map((v, i) => {
          const y = yForValue(v);
          return (
            <g key={i}>
              <line x1={pad.left} y1={y} x2={pad.left + chartW} y2={y} stroke="#e2e8f0" strokeWidth={1} strokeDasharray="3,4" />
              <text x={pad.left - 10} y={y + 4} textAnchor="end" className="fill-slate-400 text-[10px]">{v.toFixed(0)}</text>
              <text x={pad.left + chartW + 10} y={y + 4} className="fill-slate-400 text-[10px]">{v.toFixed(0)}</text>
            </g>
          );
        })}

        {priceRows.map((p, i) => {
          if (i % xTickSkip !== 0 && i !== priceRows.length - 1) return null;
          const x = xForIndex(i);
          return <text key={p.month} x={x} y={pad.top + chartH + 28} textAnchor="middle" className="fill-slate-400 text-[10px]">{p.month}</text>;
        })}

        <polyline points={points} fill="none" stroke="#2563eb" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />

        {signalRows.map((s, idx) => {
          const priceIdx = monthIndex.get(s.monthKey) ?? 0;
          const x = xForIndex(priceIdx);
          const signalPrice = Number(s.signal_price || priceRows[priceIdx]?.close || 0);
          const y = yForValue(signalPrice);
          const color = getSignalColor(s.signal_type);
          const isSellish = s.signal_type === "SELL" || s.signal_type === "REDUCE";
          const labelW = s.signal_type === "REDUCE" ? 72 : 52;
          const labelH = 26;
          const stagger = s.rowOffset * 15;
          const labelY = isSellish ? Math.max(pad.top + 4, y - 44 - stagger) : Math.min(pad.top + chartH - labelH - 4, y + 18 + stagger);
          const labelX = Math.min(Math.max(pad.left + 2, x - labelW / 2), pad.left + chartW - labelW - 2);
          const pointerY = isSellish ? labelY + labelH : labelY;

          return (
            <g key={`${s.month}-${s.signal_type}-${idx}`}>
              <line x1={x} y1={y} x2={x} y2={pointerY} stroke={color} strokeWidth={1.4} opacity={0.9} />
              <circle cx={x} cy={y} r={4} fill={color} stroke="#fff" strokeWidth={1.5} />
              <rect x={labelX} y={labelY} width={labelW} height={labelH} rx={5} fill={color} filter="drop-shadow(0 2px 3px rgba(15,23,42,0.22))" />
              <text x={labelX + labelW / 2} y={labelY + 17} textAnchor="middle" className="fill-white text-[11px] font-bold">{s.signal_type}</text>
              <title>{`${s.signal_type} ${s.symbol} @ ${formatNumber(signalPrice)} on ${s.month} | ${s.reason}`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
