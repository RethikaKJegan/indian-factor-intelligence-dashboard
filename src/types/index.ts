export type RegimeLabel =
  | "Bull / Expansion"
  | "Bear / Stress"
  | "Sideways / Neutral"
  | "Recovery"
  | "High Volatility / Risk-Off";

export type FactorName = "Momentum" | "Value" | "Quality" | "Low Volatility";

export type SignalType = "BUY" | "ADD" | "HOLD" | "REDUCE" | "SELL";

export type DecisionType = "REBALANCE" | "RETAIN" | "DEFENSIVE";

export type StrategyName =
  | "Dynamic Regime Factor Allocation"
  | "Static 25/25/25/25"
  | "Nifty 200 Buy & Hold";

export interface RegimePrediction {
  month: string;
  regime_label: RegimeLabel;
  regime_cluster: number;
  regime_confidence: number;
  transition_risk: number;
  prob_bull_expansion: number;
  prob_bear_stress: number;
  prob_sideways_neutral: number;
  prob_recovery: number;
  prob_high_vol_risk_off: number;
  model_version: string;
  news_sentiment?: number;
  negative_news_ratio?: number;
  risk_event_count?: number;
  news_confidence?: number;
  news_stress_score?: number;
}

export interface FactorBasketEntry {
  month: string;
  factor_name: FactorName;
  symbol: string;
  factor_score: number;
  factor_rank: number;
  selected_flag: boolean;
}

export interface FactorReturn {
  month: string;
  momentum_return: number;
  value_return: number;
  quality_return: number;
  low_volatility_return: number;
}

export interface FactorDiagnostics {
  month: string;
  regime_label: RegimeLabel;
  expected_returns: Record<FactorName, number>;
  covariance_matrix: Record<string, Record<string, number>>;
  correlation_matrix: Record<string, Record<string, number>>;
  max_eigenvalue_share: number;
  effective_independent_factors: number;
  risk_concentration_score: number;
  redundancy_score: number;
}

export interface FactorAllocation {
  month: string;
  regime_label: RegimeLabel;
  regime_confidence: number;
  transition_risk: number;
  momentum_weight: number;
  value_weight: number;
  quality_weight: number;
  low_volatility_weight: number;
  expected_return: number;
  expected_risk: number;
  turnover: number;
  redundancy_score: number;
  optimizer_status: string;
  news_sentiment?: number;
  negative_news_ratio?: number;
  risk_event_count?: number;
  news_confidence?: number;
  news_stress_score?: number;
}

export interface AllocationDecision {
  month: string;
  decision: DecisionType;
  reason: string;
  previous_allocation: Record<FactorName, number>;
  recommended_allocation: Record<FactorName, number>;
  expected_utility_delta: number;
  transition_risk: number;
  regime_confidence: number;
  news_sentiment?: number;
  negative_news_ratio?: number;
  risk_event_count?: number;
  news_confidence?: number;
  news_stress_score?: number;
  supporting_news?: NewsArticle[];
}

export interface PortfolioTarget {
  month: string;
  symbol: string;
  target_weight: number;
  factor_sources: string[];
  combined_score: number;
  regime_label: RegimeLabel;
  allocation_method: string;
}

export interface RebalanceTrade {
  month: string;
  symbol: string;
  signal_type: SignalType;
  old_weight: number;
  new_weight: number;
  weight_change: number;
  signal_price: number;
  regime_label: RegimeLabel;
  regime_confidence: number;
  transition_risk: number;
  primary_factor: FactorName;
  reason: string;
}

export interface StockSignalEvent {
  date: string;
  month: string;
  symbol: string;
  signal_type: SignalType;
  signal_price: number;
  old_weight: number;
  new_weight: number;
  weight_change: number;
  regime: RegimeLabel;
  regime_confidence: number;
  transition_risk: number;
  primary_factor: FactorName;
  factor_score: number;
  reason: string;
}

export interface StockPricePoint {
  month: string;
  symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adjusted_close: number;
  volume: number;
}

export interface BacktestPortfolioPoint {
  month: string;
  strategy_name: StrategyName;
  portfolio_value: number;
  monthly_return: number;
  drawdown: number;
  turnover: number;
  regime_label: RegimeLabel;
}

export interface BacktestSummary {
  strategy_name: StrategyName;
  cagr: number;
  total_return: number;
  annual_volatility: number;
  sharpe: number;
  max_drawdown: number;
  calmar: number;
  avg_turnover: number;
  best_month: number;
  worst_month: number;
}

export interface MarketIndexPoint {
  month: string;
  index_name: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  return: number | null;
  drawdown: number | null;
}

export interface MacroPoint {
  month: string;
  cpi: number | null;
  repo_rate: number | null;
  ten_year_yield: number | null;
  usd_inr: number | null;
  crude_oil: number | null;
  india_vix: number | null;
  fii_net: number | null;
  dii_net: number | null;
}

export interface NewsFeature {
  month: string;
  sentiment_score: number | null;
  negative_ratio: number | null;
  article_count: number | null;
  risk_event_count: number | null;
  news_confidence?: number | null;
}

export interface NewsDailyFeature {
  date: string;
  sentiment_score: number;
  negative_ratio: number;
  article_count: number;
  risk_event_count: number;
  news_confidence: number;
}

export interface NewsArticle {
  article_id: string;
  source: string;
  title: string;
  summary: string;
  url: string;
  published_at: string;
  published_date: string;
  month: string;
  sentiment: number;
  risk_event_count: number;
  is_negative: boolean;
  feed_url: string;
}

export interface SectorExposure {
  sector: string;
  weight: number;
  stock_count: number;
}

export interface FactorExposure {
  factor: FactorName;
  weight: number;
}

export interface OverviewData {
  latest_month: string;
  regime_label: RegimeLabel;
  regime_confidence: number;
  transition_risk: number;
  latest_decision: DecisionType;
  decision_reason: string;
  factor_allocations: Record<FactorName, number>;
  portfolio_value: number;
  monthly_return: number;
  max_drawdown: number;
  sharpe: number;
  cagr: number;
  total_return: number;
  annual_volatility: number;
  stock_count: number;
}

export interface DataInventory {
  table_name?: string;
  row_count?: number;
  column_count?: number;
  date_range?: string;
  description?: string;
  folder?: string;
  file_name?: string;
  file_type?: string;
  bytes?: number;
  rows?: number;
  columns?: string;
  sheet_names?: string | null;
  date_column_guess?: string | null;
  symbol_column_guess?: string | null;
  detected_dataset_type?: string;
  issues?: string;
}

export interface StockMeta {
  symbol: string;
  name: string;
  sector: string;
}

export interface RegimeTransitionCell {
  from_regime: RegimeLabel;
  to_regime: RegimeLabel;
  count: number;
  probability: number;
}

export interface RegimePerformance {
  regime_label: RegimeLabel;
  avg_return: number;
  freq: number;
  best_month: number;
  worst_month: number;
}

export interface LangGraphRunReport {
  orchestration: string;
  nodes: string[];
  conditional_routes: string[];
  human_approval_required: boolean;
  warnings: string[];
  llm_explanation: string;
  latest_snapshot?: {
    latest_regime?: Partial<RegimePrediction>;
    latest_allocation?: Partial<FactorAllocation>;
    latest_decision?: Partial<AllocationDecision>;
    latest_news_features?: Record<string, unknown>;
    warnings?: string[];
    human_approval_required?: boolean;
  };
}

export interface EodRefreshStatus {
  run_id: string | null;
  requested_date: string | null;
  resolved_date: string | null;
  status: "not_run" | "running" | "ok" | "no_data" | "failed" | string;
  stock_rows: number;
  index_rows: number;
  updated_stock_monthly_rows?: number;
  updated_market_monthly_rows?: number;
  updated_factor_score_rows?: number;
  updated_regime_feature_rows?: number;
  message: string;
  started_at: string | null;
  finished_at: string | null;
}




