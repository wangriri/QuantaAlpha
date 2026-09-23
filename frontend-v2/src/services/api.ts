/**
 * QuantaAlpha API Service
 *
 * Centralized API client for communicating with the FastAPI backend.
 * Uses fetch (no extra dependency) with the Vite proxy (/api -> localhost:8000).
 */

import type {
  ApiResponse,
  Factor,
  PromptPack,
  Task,
  TacticalAnalyzeResponse,
  TacticalConfig,
  TraceArtifact,
  TraceDetail,
  TraceRunSummary,
  WsMessage,
} from '@/types';

// ========================== HTTP Helpers ==========================

const BASE = ''; // Vite proxy handles /api -> backend

async function request<T = any>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers as any },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API Error ${res.status}: ${text}`);
  }
  return res.json();
}

// ========================== Mining API ==========================

export interface MiningStartParams {
  direction: string;
  numDirections?: number;
  maxRounds?: number;
  maxLoops?: number;
  factorsPerHypothesis?: number;
  librarySuffix?: string;
  qualityGateEnabled?: boolean;
  parallelEnabled?: boolean;
  backtestTimeout?: number;
  promptPack?: PromptPack;
}

export async function startMining(params: MiningStartParams) {
  return request<{ taskId: string; task: Task }>('/api/v1/mining/start', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getMiningStatus(taskId: string) {
  return request<{ task: Task }>(`/api/v1/mining/${taskId}`);
}

export async function cancelMining(taskId: string) {
  return request(`/api/v1/mining/${taskId}`, { method: 'DELETE' });
}

export async function listTasks() {
  return request<{ tasks: Task[] }>('/api/v1/mining/tasks/list');
}

// ========================== Run Trace API ==========================

export async function listTraces() {
  return request<{ runs: TraceRunSummary[] }>('/api/v1/traces');
}

export async function getTrace(runId: string) {
  return request<TraceDetail>(`/api/v1/traces/${encodeURIComponent(runId)}`);
}

export async function getTraceArtifact(runId: string, path: string) {
  return request<TraceArtifact>(
    `/api/v1/traces/${encodeURIComponent(runId)}/artifact?path=${encodeURIComponent(path)}`
  );
}

// ========================== Factor API ==========================

export interface FactorListParams {
  quality?: string;
  search?: string;
  limit?: number;
  offset?: number;
  library?: string;
}

export interface FactorListResponse {
  factors: Factor[];
  total: number;
  limit: number;
  offset: number;
  metadata?: any;
  libraries?: string[];
}

export async function getFactors(params: FactorListParams = {}) {
  const qs = new URLSearchParams();
  if (params.quality) qs.set('quality', params.quality);
  if (params.search) qs.set('search', params.search);
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  if (params.library) qs.set('library', params.library);
  return request<FactorListResponse>(`/api/v1/factors?${qs.toString()}`);
}

export async function getFactorDetail(factorId: string, library?: string) {
  const qs = new URLSearchParams();
  if (library) qs.set('library', library);
  return request<{ factor: any }>(`/api/v1/factors/${factorId}${qs.toString() ? `?${qs.toString()}` : ''}`);
}

export async function listFactorLibraries() {
  return request<{ libraries: string[] }>('/api/v1/factors/libraries');
}

export interface LibraryCleanupItem {
  path: string;
  name: string;
  kind: 'file' | 'dir';
  category: string;
  sizeBytes: number;
  sizeText: string;
}

export interface LibraryCleanupPlan {
  library: string;
  suffix?: string | null;
  items: LibraryCleanupItem[];
  totalSizeBytes: number;
  totalSizeText: string;
}

export interface LibraryCleanupResult {
  library: string;
  deleted: LibraryCleanupItem[];
  failed: Array<{ path: string; error: string }>;
  deletedSizeBytes: number;
  deletedSizeText: string;
  libraries: string[];
}

export async function previewLibraryCleanup(library: string) {
  return request<LibraryCleanupPlan>(`/api/v1/factors/libraries/${encodeURIComponent(library)}/cleanup-preview`);
}

export async function deleteFactorLibrary(library: string) {
  return request<LibraryCleanupResult>(`/api/v1/factors/libraries/${encodeURIComponent(library)}?confirm=true`, {
    method: 'DELETE',
  });
}

// ========================== Factor Cache API ==========================

export interface CacheStatusResponse {
  total: number;
  h5_cached: number;
  md5_cached: number;
  need_compute: number;
  factors: Array<{
    factor_id: string;
    factor_name: string;
    status: 'h5_cached' | 'md5_cached' | 'need_compute';
  }>;
}

export interface WarmCacheResponse {
  total: number;
  synced: number;
  skipped: number;
  failed: number;
}

export async function getCacheStatus(library?: string) {
  const qs = new URLSearchParams();
  if (library) qs.set('library', library);
  return request<CacheStatusResponse>(`/api/v1/factors/cache-status?${qs.toString()}`);
}

export async function warmCache(library?: string) {
  const qs = new URLSearchParams();
  if (library) qs.set('library', library);
  return request<WarmCacheResponse>(`/api/v1/factors/warm-cache?${qs.toString()}`, {
    method: 'POST',
  });
}

// ========================== Single-factor Evaluation API ==========================

export interface EvaluationStartParams {
  factorJson: string;
  mode?: 'unevaluated' | 'all' | 'specified';
  factorIds?: string[];
  refreshMarketCache?: boolean;
  configPath?: string;
}

export async function startEvaluation(params: EvaluationStartParams) {
  return request<{ taskId: string; task: Task }>('/api/v1/evaluations/start', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getEvaluationStatus(taskId: string) {
  return request<{ task: Task }>(`/api/v1/evaluations/${taskId}`);
}

export async function cancelEvaluation(taskId: string) {
  return request(`/api/v1/evaluations/${taskId}`, { method: 'DELETE' });
}

export interface EvaluationConfig {
  trainingStart: string;
  trainingEnd: string;
  validationStart: string;
  validationEnd: string;
  icThreshold: number;
  icirThreshold: number;
  spreadThreshold: number;
  excessSharpeThreshold: number;
  groupCount: number;
  rebalancePeriodDays: number;
  feeThrough2023: number;
  feeFrom2024: number;
  oosStatus: string;
  engine: string;
}

export async function getEvaluationConfig() {
  return request<{ config: EvaluationConfig }>('/api/v1/evaluation/config');
}

export async function updateEvaluationConfig(update: Partial<EvaluationConfig>) {
  return request<{ config: EvaluationConfig }>('/api/v1/evaluation/config', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}

export async function getEvaluationArtifact(path: string) {
  return request<{ rows: Record<string, string>[]; name: string }>(`/api/v1/evaluation/artifact?path=${encodeURIComponent(path)}`);
}

// ========================== Tactical Factor API ==========================

export async function getTacticalConfig() {
  return request<{ config: TacticalConfig; defaults: TacticalConfig }>('/api/v1/tactical/config');
}

export async function updateTacticalConfig(update: Partial<TacticalConfig>) {
  return request<{ config: TacticalConfig }>('/api/v1/tactical/config', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}

export async function analyzeTacticalFactors(library: string) {
  return request<TacticalAnalyzeResponse>('/api/v1/tactical/analyze', {
    method: 'POST',
    body: JSON.stringify({ library }),
  });
}

export async function listDedupReports() {
  return request<{ reports: any[] }>('/api/v1/dedup/reports');
}

export async function generateDedupReport(factorJson: string) {
  return request<{ report: any }>('/api/v1/dedup/reports', {
    method: 'POST',
    body: JSON.stringify({ factorJson }),
  });
}

export async function getDedupReport(reportId: string) {
  return request<{ report: any }>(`/api/v1/dedup/reports/${reportId}`);
}

export async function archiveDuplicateFactors(reportId: string, factorIds: string[]) {
  return request(`/api/v1/dedup/reports/${reportId}/archive`, {
    method: 'POST',
    body: JSON.stringify({ factorIds }),
  });
}

// ========================== System Config API ==========================

export interface ExperimentDefaults {
  defaultNumDirections: number;
  defaultMaxRounds: number;
  defaultMaxLoops: number;
  defaultFactorsPerHypothesis: number;
  defaultMarket: 'csi300' | 'csi500' | 'sp500';
  parallelExecution: boolean;
  qualityGateEnabled: boolean;
  backtestTimeout: number;
  defaultLibrarySuffix: string;
  promptPack: PromptPack;
}

export interface PromptPackOption {
  name: string;
  label: string;
  version: string;
  outputLanguage: string;
  strictJson: boolean;
  description: string;
  planningPromptFile: string;
  factorPromptFile: string;
  evolutionPromptFile?: string;
  factorFeedbackPromptFile?: string;
  coderPromptFile?: string;
  qaPromptFile?: string;
}

export interface LlmModuleRoute {
  tag: string;
  label: string;
  description: string;
  modelName: string;
  apiUrl: string;
  apiKey: string;
  hasApiKey?: boolean;
}

export interface SystemConfigResponse {
  env: Record<string, string>;
  experimentConfig: ExperimentDefaults;
  promptPacks: PromptPackOption[];
  llmModuleRoutes: LlmModuleRoute[];
  experimentYaml: string;
  factorLibraries: string[];
}

export async function getSystemConfig() {
  return request<SystemConfigResponse>(
    '/api/v1/system/config'
  );
}

export async function getProviderModels(baseUrl: string, apiKey?: string, signal?: AbortSignal) {
  const response = await fetch(`${BASE}/api/v1/system/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ baseUrl, apiKey }),
    signal,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : '获取模型列表失败，请检查后端服务后重试');
  }
  return payload as ApiResponse<{ models: string[]; fetchedAt: string }>;

}

export async function updateSystemConfig(update: Record<string, unknown>) {
  return request('/api/v1/system/config', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}

// ========================== Prompt Flow API ==========================

export interface PromptFlowNode {
  id: string;
  title: string;
  stage: string;
  stageLabel: string;
  short: string;
  long: string;
  x: number;
  y: number;
  keys: string[];
}

export interface PromptFlowEdge {
  from: string;
  to: string;
  label?: string;
  colorClass?: 'blue' | 'green' | 'orange' | 'purple' | 'slate' | string;
  dashed?: boolean;
}

export interface PromptFlowKey {
  key: string;
  file: string;
  reader: string;
  stage: string;
  role: string;
  value: string;
  shared: boolean;
  missing: boolean;
  sourceType: 'pack' | 'shared';
}

export interface PromptFlowPack extends PromptPackOption {
  active: boolean;
  files: Record<string, string>;
  keys: Record<string, PromptFlowKey>;
}

export interface PromptFlowResponse {
  nodes: PromptFlowNode[];
  edges: PromptFlowEdge[];
  packs: PromptFlowPack[];
  activePack: string;
  notes: string[];
}

export async function getPromptFlow() {
  return request<PromptFlowResponse>('/api/v1/prompts/flow');
}

// ========================== Health Check ==========================

export async function healthCheck() {
  return request<{ status: string; timestamp: string }>('/api/health');
}

// ========================== WebSocket ==========================

export type WsCallback = (msg: WsMessage) => void;

export function connectMiningWs(
  taskId: string,
  onMessage: WsCallback,
  onClose?: () => void,
  onError?: (e: Event) => void
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/mining/${taskId}`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log(`[WS] Connected to ${taskId}`);
  };

  ws.onmessage = (event) => {
    try {
      const msg: WsMessage = JSON.parse(event.data);
      onMessage(msg);
    } catch (e) {
      console.warn('[WS] Failed to parse message:', event.data);
    }
  };

  ws.onclose = () => {
    console.log(`[WS] Disconnected from ${taskId}`);
    onClose?.();
  };

  ws.onerror = (e) => {
    console.error('[WS] Error:', e);
    onError?.(e);
  };

  // Heartbeat every 30s
  const heartbeat = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send('ping');
    } else {
      clearInterval(heartbeat);
    }
  }, 30000);

  return ws;
}
