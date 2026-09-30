import { useMemo, useState } from "react";
import { Badge, Card, SignalBadge, Table } from "@/components/UI";
import {
  assessDailyRisk,
  buildCashDeploymentPlan,
  buildDeterministicExplanation,
  buildTradePlan,
  clearUserPortfolio,
  downloadTextFile,
  formatCurrency,
  getLatestPrice,
  loadUserCash,
  loadUserHoldings,
  parseHoldingsCsv,
  parseHoldingsText,
  saveUserCash,
  saveUserHoldings,
  tradePlanToCsv,
  type UserHolding,
} from "@/lib/product";

type TradeMode = "fresh" | "rebalance";

function getHoldingInputIssues(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line, index) => ({ line: line.trim(), lineNumber: index + 1 }))
    .filter(({ line }) => line.length > 0)
    .flatMap(({ line, lineNumber }) => {
      const [symbolRaw, qtyRaw] = line.split(/[,\t ]+/);
      const issues: string[] = [];
      if (!symbolRaw) issues.push(`Line ${lineNumber}: missing symbol.`);
      if (!qtyRaw || !Number.isFinite(Number(qtyRaw))) {
        issues.push(`Line ${lineNumber}: quantity must be a number, for example ${symbolRaw || "PFC"},3.`);
      }
      return issues;
    });
}

function holdingsToText(rows: UserHolding[]): string {
  return rows.map((row) => `${row.symbol},${row.quantity}${row.avgPrice ? `,${row.avgPrice}` : ""}`).join("\n");
}

function createBlankHoldingRows(rows: UserHolding[]): UserHolding[] {
  return rows.length ? rows : [{ symbol: "", quantity: 0, avgPrice: undefined }];
}

function ModeButton({
  active,
  title,
  description,
  onClick,
}: {
  active: boolean;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl border p-4 text-left shadow-sm transition ${
        active ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white hover:bg-slate-50"
      }`}
    >
      <p className="text-sm font-bold text-slate-950">{title}</p>
      <p className="mt-1 text-xs leading-5 text-slate-600">{description}</p>
    </button>
  );
}

export function TradePlanPage() {
  const [mode, setMode] = useState<TradeMode>("fresh");
  const [holdingsText, setHoldingsText] = useState(() => holdingsToText(loadUserHoldings()));
  const [bulkEntryText, setBulkEntryText] = useState("");
  const [cashText, setCashText] = useState(() => String(loadUserCash()));
  const [minimumTradeText, setMinimumTradeText] = useState("1000");
  const [basketText, setBasketText] = useState("");
  const [filter, setFilter] = useState("ALL");

  const holdings = useMemo(() => parseHoldingsText(holdingsText), [holdingsText]);
  const hasHoldings = holdings.length > 0;
  const manualRows = createBlankHoldingRows(holdings);
  const cash = Number(cashText) || 0;
  const minimumTradeValue = Number(minimumTradeText) || 0;
  const holdingIssues = getHoldingInputIssues(holdingsText);
  const basketSymbols = useMemo(
    () => basketText.split(/[\s,]+/).map((symbol) => symbol.trim()).filter(Boolean),
    [basketText]
  );

  const preview = buildTradePlan(holdings, cash, minimumTradeValue);
  const cashPlan = buildCashDeploymentPlan(cash, basketSymbols, minimumTradeValue);
  const explanation = buildDeterministicExplanation(assessDailyRisk(), preview.rows);
  const executableRows = preview.rows.filter((row) => row.finalTradeQuantity !== 0);

  const holdingCards = holdings.map((holding) => {
    const latestPrice = getLatestPrice(holding.symbol);
    const avgPrice = holding.avgPrice || 0;
    const invested = avgPrice > 0 ? holding.quantity * avgPrice : 0;
    const currentValue = holding.quantity * latestPrice;
    const pnl = invested > 0 ? currentValue - invested : 0;
    const pnlPct = invested > 0 ? pnl / invested : 0;
    return { ...holding, latestPrice, avgPrice, invested, currentValue, pnl, pnlPct };
  });

  const cashPlanRows = cashPlan.rows.map((row) => ({
    stock: <span className="font-semibold text-slate-900">{row.symbol}</span>,
    buy: `Buy ${row.quantity}`,
    price: formatCurrency(row.latestPrice),
    value: formatCurrency(row.buyValue),
    reason: row.reason,
  }));

  const tableRows = hasHoldings ? preview.rows
    .filter((row) => (filter === "ALL" ? true : row.action === filter))
    .sort((a, b) => {
      const order = { SELL: 0, REDUCE: 1, BUY: 2, ADD: 3, PAUSED: 4, IGNORED: 5, HOLD: 6 };
      return (order[a.action] ?? 9) - (order[b.action] ?? 9) || b.tradeValue - a.tradeValue;
    })
    .map((row) => ({
      stock: <span className="font-semibold text-slate-900">{row.symbol}</span>,
      youHave: `${row.currentQuantity} shares`,
      modelWants: `${row.targetQuantity} shares`,
      finalToday:
        row.finalTradeQuantity > 0
          ? `Buy ${row.finalTradeQuantity}`
          : row.finalTradeQuantity < 0
          ? `Sell ${Math.abs(row.finalTradeQuantity)}`
          : row.action === "PAUSED"
          ? "Buy 0 today"
          : "No trade",
      action:
        row.action === "PAUSED" || row.action === "IGNORED" ? (
          <Badge color={row.action === "PAUSED" ? "amber" : "slate"}>{row.action}</Badge>
        ) : (
          <SignalBadge signal={row.action} />
        ),
      targetValue: formatCurrency(row.targetValue),
      todayValue: formatCurrency(row.tradeValue),
      reason: row.reason,
    })) : [];

  const handleSave = () => {
    saveUserHoldings(holdings);
    saveUserCash(cash);
  };

  const updateManualRow = (index: number, patch: Partial<UserHolding>) => {
    const next = createBlankHoldingRows(holdings).map((row, rowIndex) =>
      rowIndex === index ? { ...row, ...patch } : row
    );
    setHoldingsText(holdingsToText(next));
  };

  const addManualRow = () => {
    setHoldingsText(holdingsToText([...holdings, { symbol: "", quantity: 0, avgPrice: undefined }]));
  };

  const loadBulkHoldings = () => {
    const pasted = parseHoldingsText(bulkEntryText);
    if (pasted.length === 0) return;
    setHoldingsText(holdingsToText(pasted));
  };

  const removeManualRow = (index: number) => {
    const next = createBlankHoldingRows(holdings).filter((_, rowIndex) => rowIndex !== index);
    setHoldingsText(holdingsToText(next));
  };

  const handleReset = () => {
    clearUserPortfolio();
    setHoldingsText("");
    setBulkEntryText("");
    setCashText("0");
  };

  const handleExport = () => {
    downloadTextFile("personalized_trade_plan.csv", tradePlanToCsv(preview.rows));
  };

  const handleCopy = async () => {
    const text = executableRows
      .map((row) =>
        row.finalTradeQuantity > 0
          ? `${row.symbol}: BUY ${row.finalTradeQuantity} shares`
          : `${row.symbol}: SELL ${Math.abs(row.finalTradeQuantity)} shares`
      )
      .join("\n");
    await navigator.clipboard.writeText(text || "No executable trades today.");
  };

  const handleImportFile = async (file: File | null) => {
    if (!file) return;
    const text = await file.text();
    const imported = parseHoldingsCsv(text);
    setHoldingsText(holdingsToText(imported));
    setMode("rebalance");
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Trade Plan</h2>
        <p className="mt-1 text-sm text-slate-500">Turn cash or holdings into exact trade quantities.</p>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <ModeButton
          active={mode === "fresh"}
          title="I want to invest fresh money"
          description="Enter cash. Get buy, stagger, or wait."
          onClick={() => setMode("fresh")}
        />
        <ModeButton
          active={mode === "rebalance"}
          title="I already hold stocks"
          description="Import holdings. Get sell, reduce, hold, or buy."
          onClick={() => setMode("rebalance")}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[430px_1fr]">
        <Card
          title={mode === "fresh" ? "Fresh Investment Setup" : "Your Holdings"}
          subtitle={mode === "fresh" ? "New cash" : "Owned stocks"}
        >
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs font-medium text-slate-600">
              {mode === "fresh" ? "Amount to invest" : "Free cash available"}
              <input
                value={cashText}
                onChange={(event) => setCashText(event.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="50000"
              />
            </label>
            <label className="text-xs font-medium text-slate-600">
              Min trade value
              <input
                value={minimumTradeText}
                onChange={(event) => setMinimumTradeText(event.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
          </div>

          {mode === "fresh" && (
            <div className="mt-5 space-y-4">
              <div className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900">
                Enter cash. The model decides buy, stagger, or wait.
              </div>
              <label className="block text-xs font-semibold text-slate-700">
                Optional watchlist
                <textarea
                  value={basketText}
                  onChange={(event) => setBasketText(event.target.value)}
                  className="mt-1 h-24 w-full rounded-lg border border-slate-300 p-3 font-mono text-xs outline-none focus:border-blue-500"
                  placeholder={"Leave blank for model basket\nor type: PFC IRFC IDEA"}
                />
                <span className="mt-2 block text-xs leading-5 text-slate-500">
                  Blank = model basket. Type symbols to restrict buys.
                </span>
              </label>
              <button
                onClick={handleSave}
                className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Save Amount
              </button>
            </div>
          )}

          {mode === "rebalance" && (
            <div className="mt-5 space-y-5">
              <div>
                <label className="block rounded-lg border border-dashed border-blue-300 bg-blue-50 p-4 text-center text-sm font-semibold text-blue-700 hover:bg-blue-100">
                  Import broker holdings CSV
                  <input type="file" accept=".csv,text/csv" className="hidden" onChange={(event) => handleImportFile(event.target.files?.[0] || null)} />
                </label>
                <p className="mt-2 text-xs text-slate-500">Accepts symbol/instrument, qty, avg price columns.</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white">
                <div className="border-b border-slate-100 px-4 py-3">
                  <p className="text-sm font-semibold text-slate-900">Paste many holdings</p>
                  <p className="mt-1 text-xs text-slate-500">One row per stock: PFC,10,420</p>
                </div>
                <div className="p-4">
                  <textarea
                    value={bulkEntryText}
                    onChange={(event) => setBulkEntryText(event.target.value)}
                    className="h-28 w-full rounded-lg border border-slate-300 p-3 font-mono text-xs outline-none focus:border-blue-500"
                    placeholder={"PFC,10,420\nBAJFINANCE,4,950\nAMBUJACEM,20"}
                  />
                  <button
                    onClick={loadBulkHoldings}
                    type="button"
                    className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    Load pasted holdings
                  </button>
                </div>
              </div>

              {holdingCards.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-slate-900">Current portfolio</p>
                    <Badge color="slate">{holdingCards.length} holdings</Badge>
                  </div>
                  <div className="max-h-[360px] space-y-3 overflow-auto pr-1">
                    {holdingCards.map((holding) => (
                      <div key={holding.symbol} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-base font-bold text-slate-950">{holding.symbol}</p>
                            <p className="mt-0.5 text-xs text-slate-500">NSE equity holding</p>
                          </div>
                          <div className="text-right">
                            <p className="text-lg font-bold text-slate-950">{formatCurrency(holding.currentValue)}</p>
                            {holding.invested > 0 ? (
                              <p className={`text-xs font-semibold ${holding.pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                                {holding.pnl >= 0 ? "+" : ""}
                                {formatCurrency(holding.pnl)} ({(holding.pnlPct * 100).toFixed(2)}%)
                              </p>
                            ) : (
                              <p className="text-xs text-slate-400">Avg price not added</p>
                            )}
                          </div>
                        </div>
                        <div className="mt-4 grid grid-cols-4 gap-3 text-xs">
                          <div>
                            <p className="text-slate-500">Qty</p>
                            <p className="mt-1 text-base font-bold text-slate-900">{holding.quantity}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">LTP</p>
                            <p className="mt-1 font-bold text-slate-900">{formatCurrency(holding.latestPrice)}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">Avg</p>
                            <p className="mt-1 font-bold text-slate-900">
                              {holding.avgPrice > 0 ? formatCurrency(holding.avgPrice) : "Not set"}
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500">Invested</p>
                            <p className="mt-1 font-bold text-slate-900">
                              {holding.invested > 0 ? formatCurrency(holding.invested) : "Not set"}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-slate-200 bg-white">
                <div className="border-b border-slate-100 px-4 py-3">
                  <p className="text-sm font-semibold text-slate-900">Edit holdings</p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[380px] text-sm">
                    <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                      <tr>
                        <th className="px-3 py-2 text-left">Symbol</th>
                        <th className="px-3 py-2 text-right">Qty</th>
                        <th className="px-3 py-2 text-right">Avg Price</th>
                        <th className="px-3 py-2 text-center"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {manualRows.map((row, index) => (
                        <tr key={`${row.symbol}-${index}`} className="border-t border-slate-100">
                          <td className="px-3 py-2">
                            <input
                              value={row.symbol}
                              onChange={(event) => updateManualRow(index, { symbol: event.target.value.toUpperCase() })}
                              className="w-full rounded-md border border-slate-300 px-2 py-2 text-sm font-semibold uppercase"
                              placeholder="PFC"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              value={row.quantity || ""}
                              onChange={(event) => updateManualRow(index, { quantity: Number(event.target.value) || 0 })}
                              className="w-full rounded-md border border-slate-300 px-2 py-2 text-right text-sm font-semibold"
                              placeholder="10"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              value={row.avgPrice || ""}
                              onChange={(event) => updateManualRow(index, { avgPrice: Number(event.target.value) || undefined })}
                              className="w-full rounded-md border border-slate-300 px-2 py-2 text-right text-sm font-semibold"
                              placeholder="420"
                            />
                          </td>
                          <td className="px-3 py-2 text-center">
                            <button
                              onClick={() => removeManualRow(index)}
                              className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                              type="button"
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button
                  onClick={addManualRow}
                  type="button"
                  className="m-3 w-[calc(100%-1.5rem)] rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Add holding row
                </button>
              </div>

              {holdingIssues.length > 0 && (
                <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs leading-5 text-red-700">
                  <p className="font-semibold">Fix these holding rows before saving</p>
                  {holdingIssues.slice(0, 4).map((issue) => <p key={issue}>{issue}</p>)}
                </div>
              )}

              <button
                onClick={handleSave}
                disabled={holdingIssues.length > 0}
                className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                Save Holdings
              </button>
              <button
                onClick={handleReset}
                className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Reset saved portfolio
              </button>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          {mode === "fresh" ? (
            <>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Today&apos;s action</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">{cashPlan.action}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Amount entered</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">{formatCurrency(cash)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Used for buys</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">{formatCurrency(cashPlan.totalUsed)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Leftover cash</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">{formatCurrency(cashPlan.cashLeft)}</p>
                </div>
              </div>

              <Card
                title="Fresh Money Recommendation"
                subtitle="Exact shares to buy, or a clear wait/stagger instruction when risk is high."
              >
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Today&apos;s action</p>
                      <p className="mt-1 text-2xl font-bold text-slate-950">{cashPlan.action}</p>
                    </div>
                    <Badge color={cashPlan.rows.length > 0 ? "green" : "amber"}>
                      {cashPlan.rows.length > 0 ? `${cashPlan.rows.length} buys ready` : "No buy order"}
                    </Badge>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-slate-700">{cashPlan.message}</p>
                  {cashPlan.rows.length === 0 && cashPlan.minimumNeededSymbol && (
                    <p className="mt-3 text-xs leading-5 text-slate-500">
                      Smallest practical target currently needs around {formatCurrency(cashPlan.minimumNeeded)} for{" "}
                      {cashPlan.minimumNeededSymbol}.
                    </p>
                  )}
                </div>
                <div className="mt-4">
                  <Table
                    maxHeight="360px"
                    columns={[
                      { key: "stock", label: "Stock" },
                      { key: "buy", label: "Suggested Buy", align: "right" },
                      { key: "price", label: "Latest Price", align: "right" },
                      { key: "value", label: "Buy Value", align: "right" },
                      { key: "reason", label: "Reason" },
                    ]}
                    data={cashPlanRows}
                  />
                </div>
              </Card>
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Portfolio value</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">{formatCurrency(preview.portfolioValue)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Executable trades</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">{executableRows.length}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Paused / ignored</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">
                    {preview.rows.filter((row) => ["PAUSED", "IGNORED"].includes(row.action)).length}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs text-slate-500">Cash after plan</p>
                  <p className="mt-1 text-lg font-bold text-slate-900">{formatCurrency(preview.cashAfter)}</p>
                </div>
              </div>

              {!hasHoldings && (
                <div className="rounded-xl border border-blue-100 bg-blue-50 p-5 text-sm text-blue-900">
                  Import or paste holdings to generate your personal trade plan.
                </div>
              )}

              {hasHoldings && preview.warnings.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                  {preview.warnings.slice(0, 2).map((warning) => <p key={warning}>{warning}</p>)}
                </div>
              )}

              {hasHoldings && <Card title="Why This Plan">
                <p className="text-sm leading-6 text-slate-700">{explanation}</p>
              </Card>}

              <Card
                title="Personalized Rebalance Trades"
                subtitle={hasHoldings ? "Your exact action list" : "Waiting for your holdings"}
                action={
                  <select value={filter} onChange={(event) => setFilter(event.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                    {["ALL", "BUY", "ADD", "SELL", "REDUCE", "PAUSED", "IGNORED", "HOLD"].map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                }
              >
                <Table
                  maxHeight="620px"
                  columns={[
                    { key: "stock", label: "Stock" },
                    { key: "youHave", label: "You Have", align: "right" },
                    { key: "modelWants", label: "Model Wants", align: "right" },
                    { key: "finalToday", label: "Final Today", align: "right" },
                    { key: "action", label: "Action", align: "center" },
                    { key: "targetValue", label: "Model Value", align: "right" },
                    { key: "todayValue", label: "Today Value", align: "right" },
                    { key: "reason", label: "Reason" },
                  ]}
                  data={tableRows}
                />
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button onClick={handleExport} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                    Export CSV
                  </button>
                  <button onClick={handleCopy} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                    Copy Trades
                  </button>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
