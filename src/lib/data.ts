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

let regimes: RegimePrediction[] = [];
let baskets: FactorBasketEntry[] = [];
let factorReturns: FactorReturn[] = [];
let factorDiagnostics: FactorDiagnostics[] = [];
let allocations: FactorAllocation[] = [];
let decisions: AllocationDecision[] = [];
let portfolioTargets: PortfolioTarget[] = [];
let rebalanceTrades: RebalanceTrade[] = [];
let signalEvents: StockSignalEvent[] = [];
let stockPrices: StockPricePoint[] = [];
let backtestPortfolio: BacktestPortfolioPoint[] = [];
let backtestSummary: BacktestSummary[] = [];
let marketIndex: MarketIndexPoint[] = [];
let macro: MacroPoint[] = [];
let newsFeatures: NewsFeature[] = [];
let newsDailyFeatures: NewsDailyFeature[] = [];
let newsArticles: NewsArticle[] = [];
let sectorIndex: any[] = [];
let stocks: StockMeta[] = [];
let dataInventory: DataInventory[] = [];
let langGraphRunReport: LangGraphRunReport = {
  orchestration: "",
  nodes: [],
  conditional_routes: [],
  human_approval_required: false,
  warnings: [],
  llm_explanation: "",
};
let eodRefreshStatus: EodRefreshStatus = {
  run_id: null,
  requested_date: null,
  resolved_date: null,
  status: "not_loaded",
  stock_rows: 0,
  index_rows: 0,
  message: "Dashboard data has not loaded yet.",
  started_at: null,
  finished_at: null,
};
let dashboardDataLoaded = false;

const DATA_BASE = "/data";

async function fetchDataFile<T>(name: string): Promise<T> {
  const res = await fetch(`${DATA_BASE}/${name}.json`, { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`Failed to load ${name}.json (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function loadDashboardData(): Promise<void> {
  const [
    regimesJson,
    basketsJson,
    factorReturnsJson,
    factorDiagnosticsJson,
    allocationsJson,
    decisionsJson,
    portfolioTargetsJson,
    rebalanceTradesJson,
    signalEventsJson,
    stockPricesJson,
    backtestPortfolioJson,
    backtestSummaryJson,
    marketIndexJson,
    macroJson,
    newsFeaturesJson,
    newsDailyJson,
    newsArticlesJson,
    sectorIndexJson,
    stocksJson,
    dataInventoryJson,
    langGraphJson,
    eodStatusJson,
  ] = await Promise.all([
    fetchDataFile<RegimePrediction[]>("regime_predictions"),
    fetchDataFile<FactorBasketEntry[]>("factor_baskets"),
    fetchDataFile<FactorReturn[]>("factor_returns"),
    fetchDataFile<FactorDiagnostics[]>("factor_diagnostics"),
    fetchDataFile<FactorAllocation[]>("factor_allocations"),
    fetchDataFile<AllocationDecision[]>("allocation_decisions"),
    fetchDataFile<PortfolioTarget[]>("portfolio_targets"),
    fetchDataFile<RebalanceTrade[]>("rebalance_trades"),
    fetchDataFile<StockSignalEvent[]>("stock_signal_events"),
    fetchDataFile<StockPricePoint[]>("stock_prices"),
    fetchDataFile<BacktestPortfolioPoint[]>("backtest_portfolio"),
    fetchDataFile<BacktestSummary[]>("backtest_summary"),
    fetchDataFile<MarketIndexPoint[]>("market_index"),
    fetchDataFile<MacroPoint[]>("macro_monthly"),
    fetchDataFile<NewsFeature[]>("news_features"),
    fetchDataFile<NewsDailyFeature[]>("news_features_daily"),
    fetchDataFile<NewsArticle[]>("news_articles_raw"),
    fetchDataFile<any[]>("sector_index"),
    fetchDataFile<StockMeta[]>("stocks"),
    fetchDataFile<DataInventory[]>("data_inventory"),
    fetchDataFile<LangGraphRunReport>("langgraph_run_report"),
    fetchDataFile<EodRefreshStatus>("eod_refresh_status"),
  ]);

  regimes = regimesJson;
  baskets = basketsJson;
  factorReturns = factorReturnsJson;
  factorDiagnostics = factorDiagnosticsJson;
  allocations = allocationsJson;
  decisions = decisionsJson;
  portfolioTargets = portfolioTargetsJson;
  rebalanceTrades = rebalanceTradesJson;
  signalEvents = signalEventsJson;
  stockPrices = stockPricesJson;
  backtestPortfolio = backtestPortfolioJson;
  backtestSummary = backtestSummaryJson;
  marketIndex = marketIndexJson;
  macro = macroJson;
  newsFeatures = newsFeaturesJson;
  newsDailyFeatures = newsDailyJson;
  newsArticles = newsArticlesJson;
  sectorIndex = sectorIndexJson;
  stocks = stocksJson;
  dataInventory = dataInventoryJson;
  langGraphRunReport = langGraphJson;
  eodRefreshStatus = eodStatusJson;
  dashboardDataLoaded = true;
}

export function isDashboardDataLoaded(): boolean {
  return dashboardDataLoaded;
}

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



