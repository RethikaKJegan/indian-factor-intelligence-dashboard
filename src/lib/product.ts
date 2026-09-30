import type {
  AllocationDecision,
  BacktestSummary,
  FactorAllocation,
  PortfolioTarget,
  StockPricePoint,
} from "@/types";
import {
  formatPercent,
  getBacktestSummary,
  getEodRefreshStatus,
  getLatestAllocation,
  getLatestDecision,
  getLatestRegime,
  getNewsDailyFeatures,
  getPortfolioTargets,
  getRebalanceTrades,
  getSectorExposure,
  getStocks,
  getStockPrices,
} from "@/lib/data";

export interface UserHolding {
  symbol: string;
  quantity: number;
  avgPrice?: number;
}

export const excludedSymbols = [
  "ENRIN",
  "GROWW",
  "HDFCLIFE",
  "ICICIAMC",
  "ICICIGI",
  "LENSKART",
  "LGEINDIA",
  "MCX",
  "SBILIFE",
  "TATACAP",
  "TMCV",
];

export interface RiskAssessment {
  status: "Normal" | "Caution" | "Danger" | "Extreme";
  score: number;
  executionMode: "Full Execute" | "Stagger Buys" | "Pause New Buys" | "Defensive";
  triggers: string[];
  summary: string;
}

export interface TradePlanRow {
  symbol: string;
  currentQuantity: number;
  targetQuantity: number;
  monthlyTradeQuantity: number;
  finalTradeQuantity: number;
  latestPrice: number;
  currentValue: number;
  targetValue: number;
  tradeValue: number;
  targetWeight: number;
  action: "BUY" | "ADD" | "SELL" | "REDUCE" | "HOLD" | "PAUSED" | "IGNORED";
  reason: string;
  factorReason: string;
  sector: string;
}

export interface PortfolioPreview {
  rows: TradePlanRow[];
  portfolioValue: number;
  investedAfter: number;
  cashAfter: number;
  stockCountAfter: number;
  newStocks: number;
  fullExits: number;
  largestHolding: TradePlanRow | null;
  largestSector: { sector: string; weight: number } | null;
  warnings: string[];
}

export interface CashDeploymentRow {
  symbol: string;
  quantity: number;
  latestPrice: number;
  buyValue: number;
  modelValue: number;
  modelWeight: number;
  reason: string;
}

export interface CashDeploymentPlan {
  rows: CashDeploymentRow[];
  totalUsed: number;
  cashLeft: number;
  minimumNeeded: number;
  minimumNeededSymbol: string | null;
  action: "Deploy" | "Stagger" | "Wait";
  message: string;
}

const HOLDINGS_KEY = "nifty200_user_holdings_v2";
const CASH_KEY = "nifty200_user_cash_v2";

export const demoHoldings: UserHolding[] = [
  { symbol: "PFC", quantity: 10 },
  { symbol: "BAJFINANCE", quantity: 4 },
  { symbol: "AMBUJACEM", quantity: 20 },
  { symbol: "BSE", quantity: 3 },
  { symbol: "ALKEM", quantity: 0 },
];

export function loadUserHoldings(): UserHolding[] {
  try {
    const raw = localStorage.getItem(HOLDINGS_KEY);
    if (!raw) return [];
    const rows = JSON.parse(raw) as UserHolding[];
    return sanitizeHoldings(rows);
  } catch {
    return [];
  }
}

export function saveUserHoldings(rows: UserHolding[]): void {
  localStorage.setItem(HOLDINGS_KEY, JSON.stringify(sanitizeHoldings(rows)));
}

export function loadUserCash(): number {
  const raw = localStorage.getItem(CASH_KEY);
  const parsed = raw ? Number(raw) : 0;
  return Number.isFinite(parsed) ? parsed : 0;
}

export function saveUserCash(cash: number): void {
  localStorage.setItem(CASH_KEY, String(Number.isFinite(cash) ? cash : 0));
}

export function clearUserPortfolio(): void {
  localStorage.removeItem(HOLDINGS_KEY);
  localStorage.removeItem(CASH_KEY);
}

export function sanitizeHoldings(rows: UserHolding[]): UserHolding[] {
  const bySymbol = new Map<string, UserHolding>();
  for (const row of rows) {
    const symbol = String(row.symbol || "").trim().toUpperCase().replace(/-(EQ|BE|SM|BZ)$/i, "");
    const quantity = Number(row.quantity);
    if (!symbol || !Number.isFinite(quantity) || quantity < 0) continue;
    const existing = bySymbol.get(symbol);
    bySymbol.set(symbol, {
      symbol,
      quantity: (existing?.quantity || 0) + quantity,
      avgPrice: row.avgPrice,
    });
  }
  return Array.from(bySymbol.values()).sort((a, b) => a.symbol.localeCompare(b.symbol));
}

export function parseHoldingsText(text: string): UserHolding[] {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const rows = lines
    .map((line) => {
      const [symbolRaw, qtyRaw, avgRaw] = line.split(/[,\t ]+/);
      return {
        symbol: symbolRaw,
        quantity: Number(qtyRaw),
        avgPrice: avgRaw ? Number(avgRaw) : undefined,
      };
    })
    .filter((row) => row.symbol && Number.isFinite(row.quantity));
  return sanitizeHoldings(rows);
}

export function parseHoldingsCsv(text: string): UserHolding[] {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length === 0) return [];

  const splitLine = (line: string) => line.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/).map((cell) => cell.replace(/^"|"$/g, "").trim());
  const header = splitLine(lines[0]).map((cell) => cell.toLowerCase().replace(/[^a-z0-9]/g, ""));
  const symbolIndex = header.findIndex((cell) =>
    ["symbol", "tradingsymbol", "ticker", "scrip", "stock", "instrument", "instrumentname"].includes(cell)
  );
  const qtyIndex = header.findIndex((cell) => ["quantity", "qty", "holdingqty", "shares", "netqty"].includes(cell));
  const avgIndex = header.findIndex((cell) => ["avgprice", "averageprice", "avgcost", "costprice"].includes(cell));

  const dataLines = symbolIndex >= 0 && qtyIndex >= 0 ? lines.slice(1) : lines;
  const fallbackSymbolIndex = symbolIndex >= 0 ? symbolIndex : 0;
  const fallbackQtyIndex = qtyIndex >= 0 ? qtyIndex : 1;

  return sanitizeHoldings(
    dataLines.map((line) => {
      const cells = splitLine(line);
      return {
        symbol: cells[fallbackSymbolIndex],
        quantity: Number(String(cells[fallbackQtyIndex] || "").replace(/,/g, "")),
        avgPrice: avgIndex >= 0 ? Number(String(cells[avgIndex] || "").replace(/,/g, "")) : undefined,
      };
    })
  );
}

export function getLatestPrice(symbol: string): number {
  const rows = getStockPrices(symbol);
  if (rows.length === 0) return 0;
  const latest = rows[rows.length - 1];
  return latest.adjusted_close || latest.close || 0;
}

export function assessDailyRisk(): RiskAssessment {
  const allocation = getLatestAllocation();
  const eod = getEodRefreshStatus();
  const latestDailyNews = [...getNewsDailyFeatures()].sort((a, b) => b.date.localeCompare(a.date))[0];
  const triggers: string[] = [];
  let score = 0;

  if (allocation && allocation.turnover >= 0.9) {
    score += 2;
    triggers.push(`Large monthly change: ${formatPercent(allocation.turnover, 0)} of weights are changing.`);
  } else if (allocation && allocation.turnover >= 0.6) {
    score += 1;
    triggers.push(`Meaningful monthly change: ${formatPercent(allocation.turnover, 0)} turnover.`);
  }

  if (allocation && allocation.regime_confidence < 0.45) {
    score += 2;
    triggers.push("Model confidence is low.");
  } else if (allocation && allocation.regime_confidence < 0.6) {
    score += 1;
    triggers.push("Model confidence is moderate.");
  }

  const newsStress = allocation?.news_stress_score ?? latestDailyNews?.negative_ratio ?? 0;
  if (newsStress >= 0.8) {
    score += 2;
    triggers.push(`News stress is high at ${formatPercent(newsStress, 0)}.`);
  } else if (newsStress >= 0.6) {
    score += 1;
    triggers.push(`News stress is elevated at ${formatPercent(newsStress, 0)}.`);
  }

  if (eod.status && !["ok", "not_loaded"].includes(eod.status)) {
    score += 1;
    triggers.push(`Data refresh status is ${eod.status}.`);
  }

  let status: RiskAssessment["status"] = "Normal";
  if (score >= 6) status = "Extreme";
  else if (score >= 4) status = "Danger";
  else if (score >= 2) status = "Caution";

  const executionMode =
    status === "Normal"
      ? "Full Execute"
      : status === "Caution"
      ? "Stagger Buys"
      : status === "Danger"
      ? "Pause New Buys"
      : "Defensive";

  const summary =
    status === "Normal"
      ? "Execute the monthly plan normally."
      : status === "Caution"
      ? "Execute sells and reductions, but stagger new buys."
      : status === "Danger"
      ? "Pause new buys today; execute only risk-reducing trades."
      : "Use defensive execution only; pause buys and review exposure.";

  return {
    status,
    score,
    executionMode,
    triggers: triggers.length ? triggers : ["No major EOD risk triggers breached."],
    summary,
  };
}

export function buildTradePlan(
  holdings: UserHolding[],
  cash = 0,
  minimumTradeValue = 1000
): PortfolioPreview {
  const targets = getPortfolioTargets();
  const stocks = getStocks();
  const decision = getLatestDecision();
  const rebalanceApproved = decision?.decision === "REBALANCE" || decision?.decision === "DEFENSIVE";
  const targetMap = new Map(targets.map((target) => [target.symbol, target]));
  const holdingMap = new Map(sanitizeHoldings(holdings).map((holding) => [holding.symbol, holding]));
  const symbols = Array.from(new Set([...targetMap.keys(), ...holdingMap.keys()])).sort();
  const risk = assessDailyRisk();

  const holdingsValue = Array.from(holdingMap.values()).reduce(
    (sum, holding) => sum + holding.quantity * getLatestPrice(holding.symbol),
    0
  );
  const portfolioValue = holdingsValue + cash;

  const rows = symbols.map((symbol) => {
    const holding = holdingMap.get(symbol);
    const target = targetMap.get(symbol);
    const latestPrice = getLatestPrice(symbol);
    const currentQuantity = holding?.quantity || 0;
    const currentValue = currentQuantity * latestPrice;
    const targetWeight = target?.target_weight || 0;
    const targetValue = portfolioValue * targetWeight;
    const targetQuantity = latestPrice > 0 ? Math.floor(targetValue / latestPrice) : 0;
    const monthlyTradeQuantity = targetQuantity - currentQuantity;
    let finalTradeQuantity = rebalanceApproved ? monthlyTradeQuantity : 0;

    if (rebalanceApproved && monthlyTradeQuantity > 0 && risk.status === "Caution") {
      finalTradeQuantity = Math.floor(monthlyTradeQuantity * 0.5);
    }
    if (rebalanceApproved && monthlyTradeQuantity > 0 && ["Danger", "Extreme"].includes(risk.status)) {
      finalTradeQuantity = 0;
    }
    if (Math.abs(finalTradeQuantity * latestPrice) > 0 && Math.abs(finalTradeQuantity * latestPrice) < minimumTradeValue) {
      finalTradeQuantity = 0;
    }

    const tradeValue = Math.abs(finalTradeQuantity * latestPrice);
    let action: TradePlanRow["action"] = "HOLD";
    if (!rebalanceApproved && monthlyTradeQuantity !== 0) action = "HOLD";
    else if (monthlyTradeQuantity > 0 && finalTradeQuantity === 0 && risk.status !== "Normal") action = "PAUSED";
    else if (monthlyTradeQuantity !== 0 && finalTradeQuantity === 0) action = "IGNORED";
    else if (finalTradeQuantity > 0 && currentQuantity === 0) action = "BUY";
    else if (finalTradeQuantity > 0) action = "ADD";
    else if (finalTradeQuantity < 0 && targetQuantity === 0) action = "SELL";
    else if (finalTradeQuantity < 0) action = "REDUCE";

    const sector = stocks.find((stock) => stock.symbol === symbol)?.sector || "Unknown";
    const factorReason = target?.factor_sources?.join(", ") || "Not in current target";
    const reason =
      !rebalanceApproved && monthlyTradeQuantity !== 0
        ? "Monthly rebalance gate did not pass; shown for transparency only."
        : action === "PAUSED"
        ? "New buy paused by daily risk overlay."
        : action === "IGNORED"
        ? "Trade is below the minimum practical trade value."
        : target
        ? `Selected by ${factorReason}.`
        : "Removed from the current target portfolio.";

    return {
      symbol,
      currentQuantity,
      targetQuantity,
      monthlyTradeQuantity,
      finalTradeQuantity,
      latestPrice,
      currentValue,
      targetValue,
      tradeValue,
      targetWeight,
      action,
      reason,
      factorReason,
      sector,
    };
  });

  const cashLimitedSymbols = new Set<string>();
  if (rebalanceApproved) {
    let cashAvailableForBuys =
      cash +
      rows
        .filter((row) => row.finalTradeQuantity < 0)
        .reduce((sum, row) => sum + Math.abs(row.finalTradeQuantity) * row.latestPrice, 0);

    for (const row of rows) {
      if (row.finalTradeQuantity <= 0) continue;
      const wantedQuantity = row.finalTradeQuantity;
      const affordableQuantity = row.latestPrice > 0 ? Math.floor(cashAvailableForBuys / row.latestPrice) : 0;
      const cappedQuantity = Math.min(wantedQuantity, affordableQuantity);
      if (cappedQuantity < wantedQuantity) {
        cashLimitedSymbols.add(row.symbol);
        row.finalTradeQuantity = cappedQuantity;
      }
      cashAvailableForBuys -= Math.max(0, row.finalTradeQuantity) * row.latestPrice;
      row.tradeValue = Math.abs(row.finalTradeQuantity * row.latestPrice);

      if (row.finalTradeQuantity === 0) {
        row.action = "PAUSED";
        row.reason = "Not enough cash available after sells/reductions.";
      } else if (cashLimitedSymbols.has(row.symbol)) {
        row.reason = `Partially sized because cash is limited. ${row.reason}`;
      }
    }
  }

  const investedAfter = rows.reduce((sum, row) => {
    const finalQuantity = row.currentQuantity + row.finalTradeQuantity;
    return sum + finalQuantity * row.latestPrice;
  }, 0);
  const cashAfter = portfolioValue - investedAfter;
  const stockCountAfter = rows.filter((row) => row.currentQuantity + row.finalTradeQuantity > 0).length;
  const newStocks = rows.filter((row) => row.currentQuantity === 0 && row.currentQuantity + row.finalTradeQuantity > 0).length;
  const fullExits = rows.filter((row) => row.currentQuantity > 0 && row.currentQuantity + row.finalTradeQuantity === 0).length;
  const largestHolding =
    [...rows].sort(
      (a, b) =>
        (b.currentQuantity + b.finalTradeQuantity) * b.latestPrice -
        (a.currentQuantity + a.finalTradeQuantity) * a.latestPrice
    )[0] || null;

  const sectorWeights = new Map<string, number>();
  for (const row of rows) {
    const value = (row.currentQuantity + row.finalTradeQuantity) * row.latestPrice;
    if (value <= 0) continue;
    sectorWeights.set(row.sector, (sectorWeights.get(row.sector) || 0) + value / Math.max(investedAfter, 1));
  }
  const largestSectorEntry = Array.from(sectorWeights.entries()).sort((a, b) => b[1] - a[1])[0] || null;

  const warnings: string[] = [];
  if (risk.status !== "Normal") warnings.push(risk.summary);
  if (stockCountAfter > 45) warnings.push("The portfolio has many positions; small accounts may face tiny trade sizes.");
  if (cashAfter < 0) warnings.push("The plan needs more cash than available after rounding.");
  if (cashLimitedSymbols.size > 0) {
    warnings.push("Some buy trades were reduced or paused because available cash is not enough.");
  }
  if (largestSectorEntry && largestSectorEntry[1] > 0.25) {
    warnings.push(`${largestSectorEntry[0]} is a large sector exposure at ${formatPercent(largestSectorEntry[1], 1)}.`);
  }

  return {
    rows,
    portfolioValue,
    investedAfter,
    cashAfter,
    stockCountAfter,
    newStocks,
    fullExits,
    largestHolding,
    largestSector: largestSectorEntry
      ? { sector: largestSectorEntry[0], weight: largestSectorEntry[1] }
      : null,
    warnings,
  };
}

export function buildCashDeploymentPlan(
  cash: number,
  candidateSymbols: string[] = [],
  minimumTradeValue = 1000
): CashDeploymentPlan {
  const availableCash = Math.max(0, Number.isFinite(cash) ? cash : 0);
  const decision = getLatestDecision();
  const risk = assessDailyRisk();
  const rebalanceApproved = decision?.decision === "REBALANCE" || decision?.decision === "DEFENSIVE";
  const targets = getPortfolioTargets().filter((target) => target.target_weight > 0);
  const normalizedCandidates = candidateSymbols.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean);
  const allowed = normalizedCandidates.length > 0 ? new Set(normalizedCandidates) : null;
  const selectedTargets = targets
    .filter((target) => !allowed || allowed.has(target.symbol))
    .sort((a, b) => b.target_weight - a.target_weight);

  const pricedTargets = selectedTargets
    .map((target) => ({
      target,
      price: getLatestPrice(target.symbol),
    }))
    .filter((row) => row.price > 0);

  const cheapest = [...pricedTargets].sort((a, b) => a.price - b.price)[0];

  if (!rebalanceApproved) {
    return {
      rows: [],
      totalUsed: 0,
      cashLeft: availableCash,
      minimumNeeded: Math.max(cheapest?.price || 0, minimumTradeValue),
      minimumNeededSymbol: cheapest?.target.symbol || null,
      action: "Wait",
      message: "Current monthly decision is RETAIN. Do not deploy fresh cash automatically; keep cash until the rebalance gate approves action.",
    };
  }

  if (risk.status === "Danger" || risk.status === "Extreme") {
    return {
      rows: [],
      totalUsed: 0,
      cashLeft: availableCash,
      minimumNeeded: Math.max(cheapest?.price || 0, minimumTradeValue),
      minimumNeededSymbol: cheapest?.target.symbol || null,
      action: "Wait",
      message: `${risk.status} risk today. Do not add fresh exposure; keep cash and re-check after the next EOD update.`,
    };
  }

  const deploymentCash = risk.status === "Caution" ? availableCash * 0.5 : availableCash;
  const action: CashDeploymentPlan["action"] = risk.status === "Caution" ? "Stagger" : "Deploy";

  if (availableCash <= 0) {
    return {
      rows: [],
      totalUsed: 0,
      cashLeft: availableCash,
      minimumNeeded: cheapest?.price || 0,
      minimumNeededSymbol: cheapest?.target.symbol || null,
      action,
      message: "Enter cash available to see what can actually be bought.",
    };
  }

  if (!cheapest || deploymentCash < cheapest.price || deploymentCash < minimumTradeValue) {
    return {
      rows: [],
      totalUsed: 0,
      cashLeft: availableCash,
      minimumNeeded: Math.max(cheapest?.price || 0, minimumTradeValue),
      minimumNeededSymbol: cheapest?.target.symbol || null,
      action,
      message: cheapest
        ? `Cash is too low to place a practical buy. You need at least ${formatCurrency(Math.max(cheapest.price, minimumTradeValue))} to buy the smallest practical target trade.`
        : "No priced model basket stocks are available for the selected symbols.",
    };
  }

  const weightSum = pricedTargets.reduce((sum, row) => sum + row.target.target_weight, 0) || 1;
  let remainingCash = deploymentCash;
  const rows: CashDeploymentRow[] = [];

  for (const { target, price } of pricedTargets) {
    const modelValue = deploymentCash * (target.target_weight / weightSum);
    const quantity = Math.floor(modelValue / price);
    const buyValue = quantity * price;
    if (quantity <= 0 || buyValue < minimumTradeValue || buyValue > remainingCash) continue;
    rows.push({
      symbol: target.symbol,
      quantity,
      latestPrice: price,
      buyValue,
      modelValue,
      modelWeight: target.target_weight,
      reason: `Sized from available cash using current model basket weight.`,
    });
    remainingCash -= buyValue;
  }

  if (rows.length === 0) {
    return {
      rows: [],
      totalUsed: 0,
      cashLeft: availableCash,
      minimumNeeded: Math.max(cheapest.price, minimumTradeValue),
      minimumNeededSymbol: cheapest.target.symbol,
      action,
      message: `Cash is available, but each model-sized buy is below the minimum trade value of ${formatCurrency(minimumTradeValue)}. Increase cash or lower the minimum trade value.`,
    };
  }

  const totalUsed = rows.reduce((sum, row) => sum + row.buyValue, 0);
  return {
    rows,
    totalUsed,
    cashLeft: availableCash - totalUsed,
    minimumNeeded: Math.max(cheapest.price, minimumTradeValue),
    minimumNeededSymbol: cheapest.target.symbol,
    action,
    message:
      action === "Stagger"
        ? `Daily risk is Caution. Deploy only about half today: buy ${rows.length} stock${rows.length === 1 ? "" : "s"} using ${formatCurrency(totalUsed)} and keep ${formatCurrency(availableCash - totalUsed)} as cash.`
        : `Buy ${rows.length} stock${rows.length === 1 ? "" : "s"} using ${formatCurrency(totalUsed)}. Keep ${formatCurrency(availableCash - totalUsed)} as leftover cash.`,
  };
}

export function formatCurrency(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function tradePlanToCsv(rows: TradePlanRow[]): string {
  const headers = [
    "symbol",
    "you_have_qty",
    "model_wants_qty",
    "monthly_trade_qty",
    "final_trade_qty_today",
    "action",
    "latest_price",
    "trade_value",
    "target_weight",
    "reason",
  ];
  const escape = (value: unknown) => {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const body = rows.map((row) =>
    [
      row.symbol,
      row.currentQuantity,
      row.targetQuantity,
      row.monthlyTradeQuantity,
      row.finalTradeQuantity,
      row.action,
      row.latestPrice.toFixed(2),
      row.tradeValue.toFixed(2),
      row.targetWeight.toFixed(6),
      row.reason,
    ]
      .map(escape)
      .join(",")
  );
  return [headers.join(","), ...body].join("\n");
}

export function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function buildDeterministicExplanation(
  risk: RiskAssessment,
  rows: TradePlanRow[]
): string {
  const decision = getLatestDecision();
  const paused = rows.filter((row) => row.action === "PAUSED");
  const executable = rows.filter((row) => row.finalTradeQuantity !== 0);
  const sells = executable.filter((row) => row.finalTradeQuantity < 0);
  const buys = executable.filter((row) => row.finalTradeQuantity > 0);
  const rawChanges = rows.filter((row) => row.monthlyTradeQuantity !== 0);

  if ((decision?.decision || "RETAIN") === "RETAIN") {
    return `The monthly decision is RETAIN, so raw model changes are shown for transparency but no automatic rebalance trades are generated. ${rawChanges.length} rows differ from the raw target, but the rebalance gate did not approve execution.`;
  }

  if (risk.status === "Normal") {
    return `Daily risk is Normal, so the full monthly plan can be executed. The current plan has ${buys.length} buy/add trades and ${sells.length} sell/reduce trades after the minimum-trade filter.`;
  }

  if (risk.status === "Caution") {
    return `Daily risk is Caution. The product keeps sell/reduce trades active and cuts new buys to a staggered quantity. This avoids adding full fresh exposure while still letting you clean up positions the model wants reduced or removed. ${paused.length} trades are paused or ignored today.`;
  }

  if (risk.status === "Danger") {
    return `Daily risk is Danger. New buy trades are paused today, while sell/reduce trades remain executable because they reduce exposure. Re-check after the next EOD update before adding fresh positions.`;
  }

  return `Daily risk is Extreme. The defensive rule pauses new buys and keeps only risk-reducing actions available. This is not a new monthly model portfolio; it is an execution guardrail until risk normalizes.`;
}

export function getDecisionSnapshot(): {
  decision: AllocationDecision | null;
  allocation: FactorAllocation | null;
  risk: RiskAssessment;
  latestMonth: string;
  latestEod: string;
} {
  const decision = getLatestDecision();
  const allocation = getLatestAllocation();
  const regime = getLatestRegime();
  const eod = getEodRefreshStatus();
  return {
    decision,
    allocation,
    risk: assessDailyRisk(),
    latestMonth: regime?.month || decision?.month || allocation?.month || "—",
    latestEod: eod.resolved_date || eod.requested_date || "—",
  };
}

export function getBenchmarkVerdicts(): {
  dynamic: BacktestSummary | undefined;
  staticMix: BacktestSummary | undefined;
  nifty: BacktestSummary | undefined;
  rows: { question: string; answer: string }[];
} {
  const summaries = getBacktestSummary();
  const dynamic = summaries.find((s) => s.strategy_name === "Dynamic Regime Factor Allocation");
  const staticMix = summaries.find((s) => s.strategy_name === "Static 25/25/25/25");
  const nifty = summaries.find((s) => s.strategy_name === "Nifty 200 Buy & Hold");

  return {
    dynamic,
    staticMix,
    nifty,
    rows: [
      {
        question: "Did it beat Nifty 200?",
        answer:
          dynamic && nifty
            ? dynamic.cagr > nifty.cagr
              ? "Yes, on CAGR in this backtest."
              : "No, Nifty 200 did better on CAGR."
            : "Not available",
      },
      {
        question: "Did it beat static factor mix?",
        answer:
          dynamic && staticMix
            ? dynamic.cagr > staticMix.cagr
              ? "Yes, dynamic allocation did better."
              : "No, the simple fixed factor mix did better."
            : "Not available",
      },
      {
        question: "Worst fall from peak",
        answer: dynamic ? formatPercent(dynamic.max_drawdown, 1) : "Not available",
      },
      {
        question: "Blind auto-trading?",
        answer: "No. Review monthly decisions and daily risk status.",
      },
    ],
  };
}

export function scoreBacktestSummary(summary: BacktestSummary): number {
  const returnScore = Math.max(0, summary.cagr) * 25;
  const drawdownScore = Math.max(0, 1 + summary.max_drawdown) * 20;
  const calmarScore = Math.max(0, summary.calmar) * 15;
  const sharpeScore = Math.max(0, summary.sharpe) * 15;
  const turnoverPenalty = Math.max(0, summary.avg_turnover) * 10;
  return returnScore + drawdownScore + calmarScore + sharpeScore - turnoverPenalty;
}

export function getModelComparisonRows() {
  return getBacktestSummary()
    .map((summary) => ({
      strategy: summary.strategy_name,
      score: scoreBacktestSummary(summary),
      cagr: summary.cagr,
      maxDrawdown: summary.max_drawdown,
      sharpe: summary.sharpe,
      calmar: summary.calmar,
      turnover: summary.avg_turnover,
    }))
    .sort((a, b) => b.score - a.score);
}

export function getCurrentSectorExposure() {
  return getSectorExposure(getPortfolioTargets());
}
