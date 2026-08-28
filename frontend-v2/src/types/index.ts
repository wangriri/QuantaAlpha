// Task status
export type TaskStatus = 'idle' | 'running' | 'completed' | 'failed' | 'cancelled';
export type PromptPack = 'zh_quant_v1' | 'en_default';

// Execution phase
export type ExecutionPhase =
  | 'parsing'      // Parsing requirements
  | 'planning'     // Planning direction
  | 'evolving'     // Evolving
  | 'backtesting'  // Backtesting
  | 'analyzing'    // Analyzing results
  | 'completed';   // Completed

// Factor quality level
export type FactorQuality = 'high' | 'medium' | 'low';
export type EvaluationStatus = 'not_evaluated' | 'passed' | 'failed' | 'lookahead_rejected' | 'data_error' | 'running';

export interface EvaluationMetrics {
  ic?: number;
  ic_abs?: number;
  icir?: number;
  rank_ic?: number;
  rank_icir?: number;
  icir_annualized_reference?: number;
  rank_icir_annualized_reference?: number;
  long_short_spread?: number;
  excess_sharpe?: number;
  portfolio?: { rebalance_period_days?: number; rebalance_days?: number; return_days?: number };
  half_life?: number | null;
  valid_days?: number;
  head_group_return_gross?: number;
  tail_group_return_gross?: number;
  coverage?: { valid_days?: number; expected_days?: number; day_ratio?: number; median_stock_count?: number; min_stock_count?: number; max_stock_count?: number };
}

// Task configuration
export interface TaskConfig {
  // Basic configuration
  userInput: string;
  /** When true, use options in "Settings -> Mining Direction" (selected/random), ignoring input box content */
  useCustomMiningDirection?: boolean;
  numDirections?: number;
  maxRounds?: number;
  maxLoops?: number;
  factorsPerHypothesis?: number;
  librarySuffix?: string;

  // LLM configuration
  apiKey?: string;
  apiUrl?: string;
  modelName?: string;

  // Backtest configuration
  market?: 'csi300' | 'csi500' | 'sp500';
  startDate?: string;
  endDate?: string;

  // Advanced configuration
  parallelExecution?: boolean;
  qualityGateEnabled?: boolean;
  backtestTimeout?: number;
  promptPack?: PromptPack;
  traceRunId?: string;
}

// Real-time metrics
export interface RealtimeMetrics {
  // IC metrics
  ic: number;
  icir: number;
  rankIc: number;
  rankIcir: number;
  
  // Optional factor name if available (e.g. best factor)
  factorName?: string;
  
  // Top 10 factors list
  top10Factors?: Array<{
    factorName: string;
    factorExpression: string;
    rankIc: number;
    rankIcir: number;
    ic: number;
    icir: number;
    annualReturn?: number;
    sharpeRatio?: number;
    maxDrawdown?: number;
    calmarRatio?: number;
    cumulativeCurve?: Array<{date: string, value: number}>;
  }>;

  // Return metrics
  annualReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;

  // Factor statistics
  totalFactors: number;
  highQualityFactors: number;
  mediumQualityFactors: number;
  lowQualityFactors: number;
}

// Execution progress
export interface ExecutionProgress {
  phase: ExecutionPhase;
  currentRound: number;
  totalRounds: number;
  progress: number; // 0-100
  message: string;
  timestamp: string;
}

// Log entry
export interface LogEntry {
  id: string;
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'success';
  message: string;
}

// Factor information
export interface Factor {
  factorId: string;
  factorName: string;
  factorExpression: string;
  factorDescription: string;
  quality: FactorQuality;
  evaluationStatus?: EvaluationStatus;
  directionMultiplier?: number;
  trainingMetrics?: EvaluationMetrics;
  validationMetrics?: EvaluationMetrics;
  gateResults?: Record<string, { passed?: boolean; value?: number; threshold?: number }>;
  artifacts?: Record<string, string>;
  lifecycle?: { status?: string; active?: boolean; reason?: string };
  oosStatus?: string;
  subperiods?: Record<string, EvaluationMetrics>;
  lookaheadAudit?: Record<string, any>;

  // Backtest metrics
  ic: number;
  icir: number;
  rankIc: number;
  rankIcir: number;

  // Metadata
  round: number;
  direction: string;
  createdAt: string;
}

export type TacticalLabel = '战术进攻型' | '高风险爆发型' | '稳健候选型' | '暂无战术价值' | '数据不足';

export interface TacticalConfig {
  enabled: boolean;
  min_training_months: number;
  min_validation_months: number;
  min_trading_days_per_month: number;
  strong_best_month_quantile: number;
  burst_month_quantile: number;
  high_volatility_quantile: number;
  severe_loss_quantile: number;
  severe_drawdown_quantile: number;
  min_positive_month_ratio: number;
  min_burst_month_count: number;
  high_return_correlation_threshold: number;
  duplicate_return_correlation_threshold: number;
  min_return_correlation_overlap: number;
  return_correlation_group_size: number;
  return_correlation_group_avg_threshold: number;
  max_return_correlation_groups: number;
}

export interface TacticalPeriodMetrics {
  valid_months: number;
  mean_monthly_excess?: number | null;
  monthly_excess_std?: number | null;
  best_month_excess?: number | null;
  worst_month_excess?: number | null;
  max_monthly_drawdown?: number | null;
  positive_month_ratio?: number | null;
  burst_month_count?: number;
  burst_month_ratio?: number | null;
  recent_3m_excess?: number | null;
  annualized_excess_return?: number | null;
  daily_excess_count?: number;
  best_month_percentile?: number | null;
  volatility_percentile?: number | null;
  worst_month_percentile?: number | null;
  drawdown_percentile?: number | null;
}

export interface TacticalMonthlyPoint {
  month: string;
  monthly_excess: number;
  trading_days: number;
  cumulative_excess: number;
  is_burst?: boolean;
}

export interface TacticalPeriodResult {
  label: TacticalLabel;
  score: number;
  metrics: TacticalPeriodMetrics;
  monthly: TacticalMonthlyPoint[];
  burstMonths: TacticalMonthlyPoint[];
  reasons: string[];
  thresholds: Record<string, number | null>;
  returnCorrelation: TacticalFactorReturnCorrelation;
}

export interface TacticalReturnCorrelationPeer {
  factorId: string;
  factorName: string;
  correlation: number;
  overlapDays: number;
  maxAbsDiff?: number | null;
  duplicateLike: boolean;
}

export interface TacticalFactorReturnCorrelation {
  maxCorrelation?: number | null;
  maxPeerFactorId?: string | null;
  maxPeerFactorName?: string | null;
  highCorrelationCount: number;
  duplicateLikeCount: number;
  peers: TacticalReturnCorrelationPeer[];
}

export interface TacticalReturnCorrelationPair {
  period: 'training' | 'validation' | string;
  factorId: string;
  factorName: string;
  peerFactorId: string;
  peerFactorName: string;
  correlation: number;
  overlapDays: number;
  maxAbsDiff?: number | null;
  duplicateLike: boolean;
}

export interface TacticalReturnCorrelationSummary {
  threshold: number;
  duplicateThreshold: number;
  minOverlapDays: number;
  highPairCount: number;
  duplicateLikePairCount: number;
  maxCorrelation?: number | null;
  pairs: TacticalReturnCorrelationPair[];
  groups: TacticalReturnCorrelationGroup[];
  groupSize: number;
  groupAvgThreshold: number;
  groupPositiveAnnualizedFilter?: boolean;
  groupEligibleFactorCount?: number;
  groupExcludedNonPositiveAnnualizedCount?: number;
}

export interface TacticalReturnCorrelationGroup {
  period: 'training' | 'validation' | string;
  factorIds: string[];
  factorNames: string[];
  averageCorrelation: number;
  minPairCorrelation?: number | null;
  minOverlapDays?: number | null;
  pairCount: number;
  pairs: Array<{
    factorId: string;
    peerFactorId: string;
    factorName: string;
    peerFactorName: string;
    correlation: number;
    overlapDays: number;
  }>;
}

export interface TacticalGroupFactorValueCorrelation {
  groupSize: number;
  pairCount: number;
  averagePearson?: number | null;
  averageSpearman?: number | null;
  minPearson?: number | null;
  minSpearman?: number | null;
  pairs: Array<{
    factorId: string;
    factorName: string;
    peerFactorId: string;
    peerFactorName: string;
    pearson?: number | null;
    spearman?: number | null;
    overlapDays: number;
    medianStocks?: number | null;
  }>;
}

export interface TacticalGroupReturnMetrics {
  valid_months: number;
  total_excess?: number | null;
  mean_monthly_excess?: number | null;
  monthly_excess_std?: number | null;
  best_month_excess?: number | null;
  worst_month_excess?: number | null;
  max_monthly_drawdown?: number | null;
  excess_sharpe?: number | null;
}

export interface TacticalGroupComponentResult {
  factorId: string;
  factorName: string;
  metrics: TacticalGroupReturnMetrics;
  monthly: TacticalMonthlyPoint[];
}

export interface TacticalGroupStrategyPeriod {
  metrics: TacticalGroupReturnMetrics;
  evaluationMetrics: Record<string, any>;
  monthly: TacticalMonthlyPoint[];
  components: TacticalGroupComponentResult[];
  comparison: {
    componentAverage: TacticalGroupReturnMetrics;
    deltas: Record<string, number | null>;
    summary: string[];
  };
}

export interface TacticalGroupTestResponse {
  library: string;
  factorIds: string[];
  factorNames: string[];
  saved?: boolean;
  savedAt?: string | null;
  updatedAt?: string | null;
  groupMetrics?: {
    averageCorrelation?: number | null;
    minPairCorrelation?: number | null;
    minOverlapDays?: number | null;
  };
  factorValueCorrelation: TacticalGroupFactorValueCorrelation;
  strategy: {
    method: Record<string, string>;
    alignment: {
      factorLagTradingDays: number;
      factorBeforeEntry: boolean;
      entryBeforeExit: boolean;
      trainingPeriod: string[];
      validationPeriod: string[];
      oosStatus: string;
    };
    training: TacticalGroupStrategyPeriod;
    validation: TacticalGroupStrategyPeriod;
  };
}

export interface TacticalGroupTestSummary {
  key: string;
  library: string;
  factorIds: string[];
  factorNames: string[];
  savedAt?: string | null;
  updatedAt?: string | null;
  groupMetrics?: {
    averageCorrelation?: number | null;
    minPairCorrelation?: number | null;
    minOverlapDays?: number | null;
  };
  averageCorrelation?: number | null;
  minPairCorrelation?: number | null;
  minOverlapDays?: number | null;
  averagePearson?: number | null;
  averageSpearman?: number | null;
  trainingTotalExcess?: number | null;
  validationTotalExcess?: number | null;
  trainingTotalExcessDelta?: number | null;
  trainingMeanMonthlyExcessDelta?: number | null;
  trainingDrawdownDelta?: number | null;
  trainingSharpeDelta?: number | null;
  validationTotalExcessDelta?: number | null;
  validationMeanMonthlyExcessDelta?: number | null;
  validationDrawdownDelta?: number | null;
  validationSharpeDelta?: number | null;
}

export interface TacticalFactorResult {
  factorId: string;
  factorName: string;
  factorExpression: string;
  factorDescription: string;
  evaluationStatus: EvaluationStatus | string;
  training: TacticalPeriodResult;
  validation?: TacticalPeriodResult | null;
}

export interface TacticalAnalyzeResponse {
  library: string;
  summary: {
    total: number;
    analyzed: number;
    skipped: number;
    labels: Record<TacticalLabel | string, number>;
    thresholds: Record<string, Record<string, unknown>>;
    returnCorrelation?: Record<string, TacticalReturnCorrelationSummary>;
    skippedFactors?: Array<{ factorId: string; reason: string }>;
  };
  factors: TacticalFactorResult[];
}

// Backtest result
export interface BacktestResult {
  // Overall metrics
  metrics: RealtimeMetrics;

  // Time series data
  equityCurve: TimeSeriesData[];
  drawdownCurve: TimeSeriesData[];
  icTimeSeries: TimeSeriesData[];

  // Factor list
  factors: Factor[];

  // Quality distribution
  qualityDistribution: {
    high: number;
    medium: number;
    low: number;
  };
}

// Time series data point
export interface TimeSeriesData {
  date: string;
  value: number;
}

// Task information
export interface Task {
  taskId: string;
  status: TaskStatus;
  config: TaskConfig;
  progress: ExecutionProgress;
  metrics?: RealtimeMetrics;
  result?: BacktestResult;
  logs: LogEntry[];
  traceRunId?: string;
  traceDir?: string;
  createdAt: string;
  updatedAt: string;
}

export interface TraceRunSummary {
  runId: string;
  status: string;
  researchTopic?: string;
  startedAt?: string;
  endedAt?: string;
  updatedAt?: string;
  promptPack?: string;
  roundCount: number;
  taskCount: number;
  factorCount: number;
  traceDir: string;
  graphComplete?: boolean;
}

export interface TraceNode {
  id: string;
  type: string;
  label: string;
  path?: string;
  status?: string;
  phase?: string;
  round_idx?: number;
  kind?: 'agent' | 'program' | 'factor' | 'evaluation' | 'attempt' | 'storage';
  explanation?: string;
  preview?: Record<string, any>;
  direction_text?: string;
}

export interface TraceEdge {
  from: string;
  to: string;
  type: string;
}

export interface TraceDetail {
  summary: TraceRunSummary;
  nodes: TraceNode[];
  edges: TraceEdge[];
  rounds: any[];
  tasks: any[];
  factors: any[];
  timeline: any[];
}

export interface TraceArtifact {
  runId: string;
  path: string;
  kind: 'json' | 'jsonl' | 'yaml' | 'text';
  content: any;
  updatedAt?: string;
}

// API Response
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// WebSocket message type
export type WsMessageType =
  | 'progress'
  | 'metrics'
  | 'log'
  | 'result'
  | 'error'
  | 'trace';

// WebSocket message
export interface WsMessage {
  type: WsMessageType;
  taskId: string;
  data: any;
  timestamp: string;
}
