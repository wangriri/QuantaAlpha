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
