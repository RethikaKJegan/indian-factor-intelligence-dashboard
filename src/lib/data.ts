import regimesData from "@/data/regime_predictions.json";
import basketsData from "@/data/factor_baskets.json";
import factorReturnsData from "@/data/factor_returns.json";
import factorDiagnosticsData from "@/data/factor_diagnostics.json";
import allocationsData from "@/data/factor_allocations.json";
import decisionsData from "@/data/allocation_decisions.json";
import portfolioTargetsData from "@/data/portfolio_targets.json";
import rebalanceTradesData from "@/data/rebalance_trades.json";
import signalEventsData from "@/data/stock_signal_events.json";
import stockPricesData from "@/data/stock_prices.json";
import backtestPortfolioData from "@/data/backtest_portfolio.json";
import backtestSummaryData from "@/data/backtest_summary.json";
import marketIndexData from "@/data/market_index.json";
import macroData from "@/data/macro_monthly.json";
import newsFeaturesData from "@/data/news_features.json";
import newsDailyData from "@/data/news_features_daily.json";
import newsArticlesData from "@/data/news_articles_raw.json";
import sectorIndexData from "@/data/sector_index.json";
import stocksData from "@/data/stocks.json";
import dataInventoryData from "@/data/data_inventory.json";
import langGraphRunReportData from "@/data/langgraph_run_report.json";
import eodRefreshStatusData from "@/data/eod_refresh_status.json";

import type {
  RegimePrediction,
  FactorBasketEntry,
  FactorReturn,
  FactorDiagnostics,
  FactorAllocation,
  AllocationDecision,
  PortfolioTarget,
  RebalanceTrade,
  StockSignalEvent,
  StockPricePoint,
  BacktestPortfolioPoint,
  BacktestSummary,
  MarketIndexPoint,
  MacroPoint,
  NewsFeature,
  NewsDailyFeature,
  NewsArticle,
  StockMeta,
  DataInventory,
  OverviewData,
  FactorName,
  SectorExposure,
  FactorExposure,
  RegimeTransitionCell,
  RegimePerformance,
  SignalType,
  LangGraphRunReport,
  EodRefreshStatus,
} from "@/types";

const regimes = regimesData as RegimePrediction[];
const baskets = basketsData as FactorBasketEntry[];
const factorReturns = factorReturnsData as FactorReturn[];
const factorDiagnostics = factorDiagnosticsData as FactorDiagnostics[];
const allocations = allocationsData as FactorAllocation[];
const decisions = decisionsData as AllocationDecision[];
const portfolioTargets = portfolioTargetsData as PortfolioTarget[];
const rebalanceTrades = rebalanceTradesData as RebalanceTrade[];
const signalEvents = signalEventsData as StockSignalEvent[];
const stockPrices = stockPricesData as StockPricePoint[];
const backtestPortfolio = backtestPortfolioData as BacktestPortfolioPoint[];
const backtestSummary = backtestSummaryData as BacktestSummary[];
const marketIndex = marketIndexData as MarketIndexPoint[];
const macro = macroData as MacroPoint[];
const newsFeatures = newsFeaturesData as NewsFeature[];
const newsDailyFeatures = newsDailyData as NewsDailyFeature[];
const newsArticles = newsArticlesData as NewsArticle[];
const sectorIndex = sectorIndexData as any[];
const stocks = stocksData as StockMeta[];
const dataInventory = dataInventoryData as DataInventory[];
const langGraphRunReport = langGraphRunReportData as LangGraphRunReport;
const eodRefreshStatus = eodRefreshStatusData as EodRefreshStatus;

export function getRegimePredictions(): RegimePrediction[] {
  return regimes;
}

export function getLatestRegime(): RegimePrediction | null {
  return regimes.length > 0 ? regimes[regimes.length - 1] : null;
}

export function getFactorBaskets(month?: string): FactorBasketEntry[] {
  if (month) return baskets.filter((b) => b.month === month);
  return baskets;
}

export function getTopStocksByFactor(
  factor: FactorName,
  month?: string,
  k = 10
): FactorBasketEntry[] {
  const m = month || (baskets.length > 0 ? baskets[baskets.length - 1].month : "");
  return baskets
    .filter((b) => b.factor_name === factor && b.month === m && b.selected_flag)
    .sort((a, b) => a.factor_rank - b.factor_rank)
    .slice(0, k);
}

export function getFactorReturns(): FactorReturn[] {
  return factorReturns;
}

export function getFactorDiagnostics(): FactorDiagnostics[] {
  return factorDiagnostics;
}

export function getLatestDiagnostics(): FactorDiagnostics | null {
  return factorDiagnostics.length > 0
    ? factorDiagnostics[factorDiagnostics.length - 1]
    : null;
}

export function getFactorAllocations(): FactorAllocation[] {
  return allocations;
}

export function getLatestAllocation(): FactorAllocation | null {
  return allocations.length > 0 ? allocations[allocations.length - 1] : null;
}

export function getAllocationDecisions(): AllocationDecision[] {
  return decisions;
}

export function getLatestDecision(): AllocationDecision | null {
  return decisions.length > 0 ? decisions[decisions.length - 1] : null;
}

export function getPortfolioTargets(month?: string): PortfolioTarget[] {
  if (month) return portfolioTargets.filter((p) => p.month === month);
  const latestMonth =
    portfolioTargets.length > 0
      ? portfolioTargets[portfolioTargets.length - 1].month
      : "";
  return portfolioTargets.filter((p) => p.month === latestMonth);
}

export function getRebalanceTrades(month?: string): RebalanceTrade[] {
  if (month) return rebalanceTrades.filter((t) => t.month === month);
  return rebalanceTrades;
}

export function getLatestRebalanceTrades(): RebalanceTrade[] {
  if (rebalanceTrades.length === 0) return [];
  const latestMonth = rebalanceTrades[rebalanceTrades.length - 1].month;
  return rebalanceTrades.filter((t) => t.month === latestMonth);
}

export function getSignalEvents(symbol?: string): StockSignalEvent[] {
  if (symbol) return signalEvents.filter((s) => s.symbol === symbol);
  return signalEvents;
}

export function getStockPrices(symbol: string): StockPricePoint[] {
  return stockPrices.filter((p) => p.symbol === symbol);
}

export function getStockSymbols(): string[] {
  const symbolSet = new Set<string>();
  stockPrices.forEach((p) => symbolSet.add(p.symbol));
  baskets.forEach((b) => symbolSet.add(b.symbol));
  return Array.from(symbolSet).sort();
}

export function getStocks(): StockMeta[] {
  return stocks;
}

export function getBacktestPortfolio(): BacktestPortfolioPoint[] {
  return backtestPortfolio;
}

export function getBacktestSummary(): BacktestSummary[] {
  return backtestSummary;
}

export function getMarketIndex(indexName?: string): MarketIndexPoint[] {
  if (indexName)
    return marketIndex.filter((m) =>
      m.index_name.toLowerCase().includes(indexName.toLowerCase())
    );
  return marketIndex;
}

export function getMacroData(): MacroPoint[] {
  return macro;
}

export function getNewsFeatures(): NewsFeature[] {
  return newsFeatures;
}

export function getNewsDailyFeatures(): NewsDailyFeature[] {
  return newsDailyFeatures;
}

export function getNewsArticles(limit?: number): NewsArticle[] {
  const rows = [...newsArticles].sort((a, b) => b.published_at.localeCompare(a.published_at));
  return typeof limit === "number" ? rows.slice(0, limit) : rows;
}

export function getNewsArticlesByMonth(month: string, limit = 12): NewsArticle[] {
  return getNewsArticles().filter((a) => a.month === month).slice(0, limit);
}

export function getSectorIndex(): any[] {
  return sectorIndex;
}

export function getDataInventory(): DataInventory[] {
  return dataInventory;
}

export function getLangGraphRunReport(): LangGraphRunReport {
  return langGraphRunReport;
}

export function getEodRefreshStatus(): EodRefreshStatus {
  return eodRefreshStatus;
}

export function getOverviewData(): OverviewData | null {
  const latestRegime = getLatestRegime();
  const latestAlloc = getLatestAllocation();
  const latestDec = getLatestDecision();
  const summaries = getBacktestSummary();
  const dynSummary = summaries.find(
    (s) => s.strategy_name === "Dynamic Regime Factor Allocation"
  );
  const targets = getPortfolioTargets();

  if (!latestRegime || !latestAlloc) return null;

  return {
    latest_month: latestRegime.month,
    regime_label: latestRegime.regime_label,
    regime_confidence: latestRegime.regime_confidence,
    transition_risk: latestRegime.transition_risk,
    latest_decision: latestDec?.decision ?? ("RETAIN" as any),
    decision_reason: latestDec?.reason ?? "",
    factor_allocations: {
      Momentum: latestAlloc.momentum_weight,
      Value: latestAlloc.value_weight,
      Quality: latestAlloc.quality_weight,
      "Low Volatility": latestAlloc.low_volatility_weight,
    },
    portfolio_value: dynSummary?.total_return
      ? 100 * (1 + dynSummary.total_return)
      : 100,
    monthly_return:
      backtestPortfolio.length > 0
        ? backtestPortfolio[backtestPortfolio.length - 1].monthly_return
        : 0,
    max_drawdown: dynSummary?.max_drawdown ?? 0,
    sharpe: dynSummary?.sharpe ?? 0,
    cagr: dynSummary?.cagr ?? 0,
    total_return: dynSummary?.total_return ?? 0,
    annual_volatility: dynSummary?.annual_volatility ?? 0,
    stock_count: targets.length,
  };
}

export function getRegimeTransitionMatrix(): RegimeTransitionCell[] {
  const regimeSeq = regimes.map((r) => r.regime_label);
  const transitions: Record<string, number> = {};
  const regimeCounts: Record<string, number> = {};

  for (let i = 0; i < regimeSeq.length - 1; i++) {
    const from = regimeSeq[i];
    const to = regimeSeq[i + 1];
    const key = `${from}|${to}`;
    transitions[key] = (transitions[key] || 0) + 1;
    regimeCounts[from] = (regimeCounts[from] || 0) + 1;
  }

  const labels = [
    "Bull / Expansion",
    "Bear / Stress",
    "Sideways / Neutral",
    "Recovery",
    "High Volatility / Risk-Off",
  ];
  const cells: RegimeTransitionCell[] = [];
  for (const from of labels) {
    for (const to of labels) {
      const key = `${from}|${to}`;
      const count = transitions[key] || 0;
      const total = regimeCounts[from] || 0;
      cells.push({
        from_regime: from as any,
        to_regime: to as any,
        count,
        probability: total > 0 ? count / total : 0,
      });
    }
  }
  return cells;
}

export function getRegimePerformance(): RegimePerformance[] {
  const btDyn = backtestPortfolio.filter(
    (b) => b.strategy_name === "Dynamic Regime Factor Allocation"
  );
  const byRegime: Record<string, number[]> = {};
  for (const b of btDyn) {
    if (!byRegime[b.regime_label]) byRegime[b.regime_label] = [];
    byRegime[b.regime_label].push(b.monthly_return);
  }
  const result: RegimePerformance[] = [];
  for (const [label, rets] of Object.entries(byRegime)) {
    result.push({
      regime_label: label as any,
      avg_return: rets.reduce((a, b) => a + b, 0) / rets.length,
      freq: rets.length,
      best_month: Math.max(...rets),
      worst_month: Math.min(...rets),
    });
  }
  return result;
}

export function getSectorExposure(
  targets: PortfolioTarget[]
): SectorExposure[] {
  const bySector: Record<string, { weight: number; count: number }> = {};
  for (const t of targets) {
    const stock = stocks.find((s) => s.symbol === t.symbol);
    const sector = stock?.sector || "Unknown";
    if (!bySector[sector]) bySector[sector] = { weight: 0, count: 0 };
    bySector[sector].weight += t.target_weight;
    bySector[sector].count += 1;
  }
  return Object.entries(bySector)
    .map(([sector, v]) => ({
      sector,
      weight: v.weight,
      stock_count: v.count,
    }))
    .sort((a, b) => b.weight - a.weight);
}

export function getFactorExposure(
  targets: PortfolioTarget[]
): FactorExposure[] {
  const byFactor: Record<string, number> = {};
  for (const t of targets) {
    for (const f of t.factor_sources) {
      byFactor[f] = (byFactor[f] || 0) + t.target_weight;
    }
  }
  return (Object.entries(byFactor) as [FactorName, number][])
    .map(([factor, weight]) => ({ factor, weight }))
    .sort((a, b) => b.weight - a.weight);
}

export function getMonthlyReturns(
  strategy: string
): { month: string; return: number }[] {
  return backtestPortfolio
    .filter((b) => b.strategy_name === strategy)
    .map((b) => ({ month: b.month, return: b.monthly_return }));
}

export function getSignalColor(sig: SignalType): string {
  switch (sig) {
    case "BUY":
      return "#10b981";
    case "ADD":
      return "#3b82f6";
    case "REDUCE":
      return "#f59e0b";
    case "SELL":
      return "#ef4444";
    case "HOLD":
      return "#6b7280";
    default:
      return "#6b7280";
  }
}

export function getRegimeColor(regime: string): string {
  switch (regime) {
    case "Bull / Expansion":
      return "#10b981";
    case "Bear / Stress":
      return "#ef4444";
    case "Sideways / Neutral":
      return "#6b7280";
    case "Recovery":
      return "#3b82f6";
    case "High Volatility / Risk-Off":
      return "#f59e0b";
    default:
      return "#6b7280";
  }
}

export function getFactorColor(factor: string): string {
  switch (factor) {
    case "Momentum":
      return "#3b82f6";
    case "Value":
      return "#10b981";
    case "Quality":
      return "#8b5cf6";
    case "Low Volatility":
      return "#f59e0b";
    default:
      return "#6b7280";
  }
}

export function formatPercent(v: number, digits = 2): string {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function formatNumber(v: number, digits = 2): string {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return v.toFixed(digits);
}



