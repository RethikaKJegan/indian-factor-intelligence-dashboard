/**
 * A modelled market regime.
 *
 * `Unscored` marks a month the model could not classify out of sample, because
 * too little history existed to fit the mixture honestly. It is deliberately
 * its own value rather than being folded into "Sideways / Neutral", so a warm-up
 * month is never presented as a real classification.
 */
export type RegimeLabel =
  | "Bull / Expansion"
  | "Bear / Stress"
  | "Sideways / Neutral"
  | "Recovery"
  | "High Volatility / Risk-Off"
  | "Unscored";

/** The five regimes the model can actually assign, in matrix order. */
export const REGIME_LABELS: readonly Exclude<RegimeLabel, "Unscored">[] = [
  "Bull / Expansion",
  "Bear / Stress",
  "Sideways / Neutral",
  "Recovery",
  "High Volatility / Risk-Off",
] as const;

/** One month of an official Nifty sector index. */
export interface SectorIndexPoint {
  month: string;
  index_name: string;
  close: number | null;
  [key: string]: unknown;
}

export type FactorName = "Momentum" | "Value" | "Quality" | "Low Volatility";

export type SignalType = "BUY" | "ADD" | "HOLD" | "REDUCE" | "SELL";

export type DecisionType = "REBALANCE" | "RETAIN" | "DEFENSIVE";

export type StrategyName =
  | "Dynamic Regime Factor Allocation"
  | "Static 25/25/25/25"
  | "Nifty 200 Buy & Hold";

/**
 * A month scored by the regime model.
 *
 * Confidence and cluster probabilities are `null` for warm-up months the model
 * could not score out of sample (`is_warmup: true`). They are null rather than
 * zero so a missing forecast is never read as "no confidence" or "zero
 * probability".
 */
export interface RegimePrediction {
  month: string;
  regime_label: RegimeLabel;
  regime_cluster: number | null;
  regime_confidence: number | null;
  transition_risk: number | null;
  prob_bull_expansion: number | null;
  prob_bear_stress: number | null;
  prob_sideways_neutral: number | null;
  prob_recovery: number | null;
  prob_high_vol_risk_off: number | null;
  model_version: string;
  /** True when the month is warm-up and carries no model output. */
  is_warmup?: boolean;
  /**
   * ANOVA check on the newest record: do the regime clusters actually differ
   * in realised forward returns? Present on the last month only.
   */
  cluster_separation?: {
    f_statistic: number;
    f_critical_approx: number;
    groups: number;
    observations: number;
    clusters_separate_returns: boolean;
  };
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

/** The numeric monthly-return fields of {@link FactorReturn}. */
export type FactorReturnMetric = Exclude<keyof FactorReturn, "month">;

/**
 * Regime-conditional factor diagnostics for one month.
 *
 * The correlation and covariance matrices, and the eigenvalue-derived scores,
 * are `null` when the regime has too few observations in the expanding window
 * to estimate them. They are null rather than a placeholder identity matrix,
 * which would display as a perfect diagonal and imply zero factor redundancy.
 */
export interface FactorDiagnostics {
  month: string;
  regime_label: RegimeLabel;
  /** Observations backing the matrix for this month. */
  observation_count: number;
  expected_returns: Record<FactorName, number>;
  covariance_matrix: Record<string, Record<string, number | null>>;
  correlation_matrix: Record<string, Record<string, number | null>>;
  max_eigenvalue_share: number | null;
  effective_independent_factors: number | null;
  risk_concentration_score: number | null;
  redundancy_score: number | null;
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

/** The four factor weight fields of {@link FactorAllocation}. */
export type FactorWeightKey =
  | "momentum_weight"
  | "value_weight"
  | "quality_weight"
  | "low_volatility_weight";

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
  /** `null` when the latest month is a warm-up month with no model output. */
  regime_confidence: number | null;
  transition_risk: number | null;
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

/**
 * How much of the index the modeling universe actually covers, and why any
 * symbol is missing. Written by the pipeline on every run.
 */
export interface UniverseCoverage {
  index_name: string;
  index_size: number;
  modeling_universe_size: number;
  excluded_count: number;
  /** Symbol -> upstream reason it cannot be modeled. */
  excluded_symbols: Record<string, string>;
  min_price_months_required: number;
  min_fundamental_months_required: number;
  note?: string;
}

/**
 * One rung of the cost ladder. The book is re-run end to end at each cost
 * level, because turnover depends on the weights, not just on the base case.
 */
export interface CostScenario {
  bps: number;
  label: string;
  cagr: number;
  sharpe: number;
  max_drawdown: number;
  total_cost: number;
}

export interface CostScenarioTable {
  scenarios: CostScenario[];
  base_bps: number;
  gross_cagr: number | null;
  base_cagr: number | null;
  stress_bps: number;
  stress_cagr: number;
  /** CAGR points lost between the zero-cost and worst-case rows. */
  cagr_lost_to_costs_pct: number | null;
  interpretation: string;
}

/**
 * A percentile confidence interval from a moving-block bootstrap. Month-by-month
 * resampling would assume independent returns and produce an interval that is
 * too narrow; the block length preserves the real serial dependence.
 */
export interface BootstrapCI {
  statistic: string;
  point: number;
  ci_low: number;
  ci_high: number;
  level: number;
  bootstrap_samples: number;
  block_length: number;
  method: string;
  seed: number;
}

/**
 * Performance statistics and inference for the stock-level book.
 *
 * `sharpe_vs_rf` and `sortino_vs_rf` use a *disclosed assumption* for the
 * Indian risk-free rate, because the source data has no G-Sec series. The
 * `_vs_zero` variants reproduce the original dashboard convention. Both are
 * shown so the reader is never comparing an excess-of-cash number against an
 * excess-of-nothing one.
 */
export interface PerformanceReport {
  risk_free_assumption: {
    annual: number;
    monthly: number;
    is_assumption_not_data: boolean;
    note: string;
  };
  return_path: {
    months: number;
    /** Average return of the worst 5% of months, not a floor. */
    cvar_95_monthly: number;
    cvar_99_monthly: number;
    cvar_note: string;
    longest_drawdown_months: number;
    ulcer_index: number;
    gain_to_pain: number;
    skew: number;
    excess_kurtosis: number;
  };
  risk_adjusted: {
    sharpe_vs_rf: number;
    sharpe_vs_zero: number;
    sortino_vs_rf: number;
    sortino_vs_zero: number;
  };
  vs_benchmark: {
    benchmark: string;
    observations: number;
    beta: number;
    alpha_annual: number;
    r_squared: number;
    tracking_error_annual: number;
    information_ratio: number;
    correlation: number;
    hit_rate_vs_benchmark: number;
    interpretation: string;
  };
  mean_return_test: {
    mean_monthly: number;
    /** HAC t-statistic on the mean return, correcting for autocorrelation. */
    t_stat: number;
    hac_standard_error: number;
    lags: number;
    lag1_autocorrelation: number;
    interpretation: string;
  };
  confidence_intervals: Partial<Record<"sharpe" | "cagr" | "mean", BootstrapCI>>;
  cost_model: { bps: number; label: string };
}

/**
 * One month of the constraint check, written for every rebalance so the
 * compliance claim is a reported fact rather than an internal assertion.
 */
export interface ConstraintMonth {
  positions: number;
  invested: number;
  /** Unallocated weight, which earns nothing rather than being forced into a name. */
  cash: number;
  max_weight: number;
  max_sector_weight: number;
  sector_cap_respected: boolean;
}

export interface PortfolioConstraintCompliance {
  constraints: {
    max_weight: number;
    min_weight: number;
    max_sector_weight: number;
    min_names: number;
    max_names: number;
    /** Not enforced: no reliable ADV data in the source. */
    max_pct_of_adv: number | null;
  };
  months: Record<string, ConstraintMonth>;
  months_breaching_max_weight: number;
  all_constraints_respected: boolean;
}

/** One table the pipeline read, with the window of data it actually consumed. */
export interface ManifestTable {
  present: boolean;
  rows?: number;
  month_min?: string | null;
  month_max?: string | null;
  months?: number;
}

export interface ManifestModule {
  path: string;
  exists: boolean;
  bytes?: number;
  sha256?: string;
}

/**
 * Every constant that changes a result if it is wrong, read from the live
 * modules rather than restated. If `TOP_K` changes in the code, the manifest
 * changes with it, so the two cannot drift apart.
 */
export interface ManifestAssumption {
  name: string;
  value: number | string | Record<string, number> | null;
  unit: string | null;
  controls: string;
  risk_if_wrong: string;
}

/** Whether a pipeline stage gives the same output for the same input. */
export interface ManifestDeterminism {
  stage: string;
  deterministic: boolean;
  basis: string;
}

export interface ManifestCaveat {
  id: string;
  severity: "high" | "medium" | "low";
  statement: string;
  why_not_fixed: string;
  provenance_check?: string;
}

/**
 * What a single run consumed, assumed and could not support.
 *
 * The fingerprint hashes inputs, code and assumptions together, so a later run
 * can tell whether its numbers are even comparable to this one.
 */
export interface ExperimentManifest {
  schema: string;
  run: {
    started_at: string;
    finished_at: string;
    runtime_seconds: number;
    fingerprint: string;
    fingerprint_covers: string[];
    fingerprint_note: string;
  };
  environment: { python: string; platform: string; machine: string };
  inputs: {
    path: string;
    exists: boolean;
    bytes?: number;
    tables: Record<string, ManifestTable>;
  };
  code: { dir: string; modules: ManifestModule[]; note: string };
  assumptions: ManifestAssumption[];
  /** The exact news article set used, hashed. The one input that can move. */
  news_snapshot: {
    path: string;
    fetched_at: string;
    article_count: number;
    content_sha256: string;
  } | null;
  /** "fetched-live" or "replayed". Reported, never inferred. */
  news_mode: "fetched-live" | "replayed" | null;
  data_freshness: DataFreshness | null;
  determinism: ManifestDeterminism[];
  caveats: ManifestCaveat[];
  caveat_summary: { high: number; medium: number; low: number };
}

/** One thing that is wrong, late, or unstated about the data itself. */
export interface FreshnessIssue {
  id: string;
  severity: "high" | "medium" | "low" | "ok";
  detail: string;
}

/**
 * How current the database actually is.
 *
 * A daily job that quietly stops working is worse than one that crashes: the
 * dashboard keeps rendering and the numbers simply stop moving. None of this is
 * visible in a displayed figure, so it has to be measured and shown.
 */
export interface DataFreshness {
  checked_at: string;
  database: string;
  today: string;
  /** The EOD date a healthy refresh should have delivered by now. */
  expected_eod_date: string;
  trading_calendar_note: string;
  status: "current" | "degraded" | "stale" | "unreadable" | "unknown";
  eod: {
    table: string;
    rows: number;
    latest_date: string | null;
    distinct_dates: number;
    trading_days_behind: number | null;
    expected_date: string;
  };
  /** Month label carried by the monthly tables, which runs ahead of the data. */
  newest_month_label: string | null;
  monthly: Record<string, { month_min: string; month_max: string; rows: number }>;
  recent_refresh_runs?: {
    count: number;
    status_counts: Record<string, number>;
    latest_started_at: string | null;
    latest_resolved_date: string | null;
    latest_status: string | null;
    latest_message: string | null;
  };
  issues: FreshnessIssue[];
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




