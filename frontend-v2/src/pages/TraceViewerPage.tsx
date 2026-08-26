import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  Bot,
  Boxes,
  ChevronDown,
  ChevronRight,
  Code2,
  Database,
  FileJson,
  GitBranch,
  ListTree,
  Loader2,
  RefreshCw,
  Save,
  Settings2,
  Sigma,
  Workflow,
} from 'lucide-react';
import { getTrace, getTraceArtifact, listTraces } from '@/services/api';
import type { TraceArtifact, TraceDetail, TraceNode, TraceRunSummary } from '@/types';

const typeLabels: Record<string, string> = {
  user_input: '用户输入',
  config_snapshot: '配置快照',
  planning_prompt: '方向拆分提示词',
  planning_output: '方向拆分输出',
  direction: '研究方向',
  round: '轮次',
  task: '任务',
  mutation_prompt: '变异提示词',
  mutation_output: '变异输出',
  crossover_prompt: '交叉提示词',
  crossover_output: '交叉输出',
  hypothesis: '研究假设',
  experiment: '因子公式',
  factor: '候选因子',
  formula_attempt: '公式校验',
  factor_values: '因子值',
  evaluation: '评价结果',
  feedback: '结果反馈',
  saved_factors: '保存入库',
};

const previewLabels: Record<string, string> = {
  actor: '执行者',
  status: '状态',
  input: '输入',
  userPrompt: '用户提示词',
  rawOutput: '原始输出',
  研究方向: '研究方向',
  研究假设: '研究假设',
  观察: '观察',
  理由: '理由',
  沉淀知识: '沉淀知识',
  约束: '约束',
  因子名称: '因子名称',
  因子公式: '因子公式',
  因子描述: '因子描述',
  生命周期: '生命周期',
  指标: '指标',
  保存位置: '保存位置',
  因子值文件: '因子值文件',
};

const statusLabels: Record<string, string> = {
  completed: '完成',
  running: '运行中',
  failed: '失败',
  cancelled: '已停止',
  success: '成功',
  unknown: '未知',
};

const nodeOrder: Record<string, number> = {
  user_input: 0,
  config_snapshot: 1,
  planning_prompt: 2,
  planning_output: 3,
  direction: 4,
  round: 5,
  task: 6,
  mutation_prompt: 7,
  mutation_output: 8,
  crossover_prompt: 9,
  crossover_output: 10,
  hypothesis: 11,
  experiment: 12,
  factor: 13,
  formula_attempt: 14,
  factor_values: 15,
  evaluation: 16,
  feedback: 17,
  saved_factors: 18,
};

const formatTime = (value?: string) => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
};

const shortRunId = (runId: string) => runId.replace('run_', '');

const asText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'number') return Number.isFinite(value) ? value.toFixed(Math.abs(value) < 1 ? 4 : 3) : '--';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
};

const iconFor = (node: TraceNode) => {
  if (node.kind === 'agent') return Bot;
  if (node.kind === 'factor') return Sigma;
  if (node.kind === 'evaluation') return Boxes;
  if (node.kind === 'storage') return Save;
  if (node.type === 'config_snapshot') return Settings2;
  if (node.type === 'factor_values') return Database;
  if (node.type === 'formula_attempt') return Code2;
  return FileJson;
};

const colorFor = (node: TraceNode) => {
  if (node.status === 'failed') return 'border-red-300 bg-red-50 text-red-700';
  if (node.kind === 'agent') return 'border-blue-200 bg-blue-50 text-blue-800';
  if (node.kind === 'factor') return 'border-violet-200 bg-violet-50 text-violet-800';
  if (node.kind === 'evaluation') return 'border-amber-200 bg-amber-50 text-amber-800';
  if (node.kind === 'storage') return 'border-slate-300 bg-slate-50 text-slate-800';
  return 'border-emerald-200 bg-emerald-50 text-emerald-800';
};

const NodeButton: React.FC<{
  node: TraceNode;
  selected: boolean;
  onClick: () => void;
  depth?: number;
}> = ({ node, selected, onClick, depth = 0 }) => {
  const Icon = iconFor(node);
  return (
    <button
      onClick={onClick}
      className={`group relative w-full border px-3 py-2 text-left transition-all hover:-translate-y-0.5 hover:shadow-md ${colorFor(node)} ${
        selected ? 'ring-2 ring-primary/50' : ''
      }`}
      style={{ marginLeft: depth ? depth * 10 : undefined, width: depth ? `calc(100% - ${depth * 10}px)` : undefined }}
    >
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold">{typeLabels[node.type] || node.label}</span>
            {node.phase && <span className="shrink-0 border border-current/20 px-1.5 py-0.5 text-[10px]">{node.phase}</span>}
          </div>
          <div className="mt-1 line-clamp-2 text-xs opacity-80">{node.preview?.因子名称 || node.preview?.研究假设 || node.preview?.因子公式 || node.direction_text || node.label}</div>
        </div>
      </div>
    </button>
  );
};

const SectionShell: React.FC<{
  title: string;
  subtitle?: string;
  badge?: string;
  collapsed: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}> = ({ title, subtitle, badge, collapsed, onToggle, children }) => (
  <section className="border border-border bg-background/70">
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center justify-between gap-3 border-b border-border bg-secondary/50 px-4 py-3 text-left transition-colors hover:bg-secondary"
    >
      <div className="flex min-w-0 items-center gap-2">
        {collapsed ? <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <ListTree className="h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{title}</div>
          {subtitle && <div className="mt-0.5 truncate text-xs text-muted-foreground">{subtitle}</div>}
        </div>
      </div>
      {badge && <span className="shrink-0 border border-border bg-background px-2 py-1 text-xs text-muted-foreground">{badge}</span>}
    </button>
    {!collapsed && <div className="p-4">{children}</div>}
  </section>
);

const DetailValue: React.FC<{ value: unknown }> = ({ value }) => {
  const text = asText(value);
  const isBlock = text.length > 120 || text.includes('\n');
  return isBlock ? (
    <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap border border-border bg-muted/40 p-3 text-xs leading-5">{text}</pre>
  ) : (
    <div className="mt-1 break-words text-sm leading-6">{text}</div>
  );
};

export const TraceViewerPage: React.FC<{ activeRunId?: string }> = ({ activeRunId }) => {
  const [runs, setRuns] = useState<TraceRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [selectedRoundId, setSelectedRoundId] = useState<string>('all');
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [artifact, setArtifact] = useState<TraceArtifact | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  const toggleSection = useCallback((id: string) => {
    setCollapsedSections((current) => ({ ...current, [id]: !current[id] }));
  }, []);

  const loadRuns = useCallback(async () => {
    setLoadingRuns(true);
    setError('');
    try {
      const response = await listTraces();
      const nextRuns = response.data?.runs || [];
      setRuns(nextRuns);
      const remembered = activeRunId || localStorage.getItem('quantaalpha_trace_run_id') || '';
      const preferred = nextRuns.find((run) => run.runId === remembered)?.runId || nextRuns[0]?.runId || '';
      setSelectedRunId((current) => current || preferred);
    } catch (err: any) {
      setError(err.message || '无法读取运行轨迹列表');
    } finally {
      setLoadingRuns(false);
    }
  }, [activeRunId]);

  const loadDetail = useCallback(async (runId: string) => {
    if (!runId) return;
    setLoadingDetail(true);
    setError('');
    try {
      const response = await getTrace(runId);
      const trace = response.data || null;
      setDetail(trace);
      const firstNode = trace?.nodes.find((node) => node.type === 'user_input') || trace?.nodes[0];
      setSelectedNodeId((current) => trace?.nodes.some((node) => node.id === current) ? current : firstNode?.id || '');
      localStorage.setItem('quantaalpha_trace_run_id', runId);
    } catch (err: any) {
      setError(err.message || '无法读取运行轨迹详情');
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => { loadRuns(); }, [loadRuns]);
  useEffect(() => { if (selectedRunId) loadDetail(selectedRunId); }, [selectedRunId, loadDetail]);

  const selectedNode = useMemo(
    () => detail?.nodes.find((node) => node.id === selectedNodeId) || null,
    [detail, selectedNodeId],
  );

  useEffect(() => {
    const path = selectedNode?.path;
    if (!detail || !selectedRunId || !path) {
      setArtifact(null);
      return;
    }
    getTraceArtifact(selectedRunId, path)
      .then((response) => setArtifact(response.data || null))
      .catch(() => setArtifact(null));
  }, [detail, selectedRunId, selectedNode?.path]);

  const planningNodes = useMemo(
    () => (detail?.nodes || [])
      .filter((node) => !node.id.includes('.round_') || ['user_input', 'config_snapshot', 'planning_prompt', 'planning_output', 'direction'].includes(node.type))
      .sort((a, b) => (nodeOrder[a.type] ?? 99) - (nodeOrder[b.type] ?? 99) || a.id.localeCompare(b.id)),
    [detail],
  );

  const roundGroups = useMemo(() => {
    const nodes = detail?.nodes || [];
    const rounds = nodes
      .filter((node) => node.type === 'round')
      .sort((a, b) => Number(a.round_idx ?? 0) - Number(b.round_idx ?? 0));
    return rounds.map((round) => {
      const tasks = nodes
        .filter((node) => node.type === 'task' && node.id.startsWith(`${round.id}.`))
        .sort((a, b) => a.id.localeCompare(b.id));
      return {
        round,
        tasks: tasks.map((task) => ({
          task,
          children: nodes
            .filter((node) => node.id.startsWith(`${task.id}.`) && node.id !== task.id)
            .sort((a, b) => (nodeOrder[a.type] ?? 99) - (nodeOrder[b.type] ?? 99) || a.id.localeCompare(b.id)),
        })),
      };
    });
  }, [detail]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.runId === selectedRunId) || detail?.summary || null,
    [detail?.summary, runs, selectedRunId],
  );

  const visibleRoundGroups = useMemo(
    () => selectedRoundId === 'all' ? roundGroups : roundGroups.filter((group) => group.round.id === selectedRoundId),
    [roundGroups, selectedRoundId],
  );

  const selectedRoundLabel = useMemo(() => {
    if (selectedRoundId === 'all') return '全部轮次';
    const group = roundGroups.find((item) => item.round.id === selectedRoundId);
    return group?.round.label || '选择轮次';
  }, [roundGroups, selectedRoundId]);

  useEffect(() => {
    if (selectedRoundId === 'all') return;
    if (!roundGroups.some((group) => group.round.id === selectedRoundId)) {
      setSelectedRoundId('all');
    }
  }, [roundGroups, selectedRoundId]);

  return (
    <div className="grid min-h-[calc(100vh-8rem)] grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
      <main className="min-w-0 space-y-4">
        {error && <div className="flex items-center gap-2 border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700"><AlertCircle className="h-4 w-4" />{error}</div>}
        <section className="glass border border-border p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="flex items-center gap-2 text-xl font-bold"><Workflow className="h-5 w-5 text-primary" />挖掘过程</h1>
              <p className="mt-1 text-xs text-muted-foreground">按文件还原 Agent 思考轨迹</p>
              <h2 className="mt-3 break-words text-2xl font-bold">{detail?.summary.researchTopic || '运行轨迹详情'}</h2>
            </div>
            <div className="flex flex-col gap-2 text-xs md:min-w-[360px]">
              <label className="space-y-1">
                <span className="font-medium text-muted-foreground">运行</span>
                <select
                  value={selectedRunId}
                  onChange={(event) => {
                    setSelectedRunId(event.target.value);
                    setSelectedRoundId('all');
                    setSelectedNodeId('');
                  }}
                  className="h-10 w-full border border-border bg-background px-3 font-mono text-xs outline-none focus:border-primary"
                >
                  {runs.map((run) => (
                    <option key={run.runId} value={run.runId}>
                      {shortRunId(run.runId)} · {statusLabels[run.status] || run.status} · {run.roundCount}轮/{run.taskCount}任务/{run.factorCount}因子
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="font-medium text-muted-foreground">轮次</span>
                <select
                  value={selectedRoundId}
                  onChange={(event) => setSelectedRoundId(event.target.value)}
                  className="h-10 w-full border border-border bg-background px-3 text-xs outline-none focus:border-primary"
                >
                  <option value="all">全部轮次</option>
                  {roundGroups.map(({ round, tasks }) => (
                    <option key={round.id} value={round.id}>
                      {round.label} · {tasks.length} 个任务
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <span className="flex items-center gap-1 border border-border bg-background px-3 py-2">
              <GitBranch className="h-3.5 w-3.5" />{selectedRun?.runId || '未选择运行'}
            </span>
            <span className="border border-border bg-background px-3 py-2">当前轮次：{selectedRoundLabel}</span>
            <span className="border border-border bg-background px-3 py-2">状态：{statusLabels[detail?.summary.status || ''] || detail?.summary.status || '--'}</span>
            <span className="border border-border bg-background px-3 py-2">Prompt：{detail?.summary.promptPack || '--'}</span>
            <span className="border border-border bg-background px-3 py-2">更新：{formatTime(detail?.summary.updatedAt)}</span>
            <button onClick={() => { loadRuns(); selectedRunId && loadDetail(selectedRunId); }} className="border border-primary/30 bg-primary/10 px-3 py-2 text-primary">
              {loadingDetail || loadingRuns ? <Loader2 className="inline h-3.5 w-3.5 animate-spin" /> : <><RefreshCw className="mr-1 inline h-3.5 w-3.5" />刷新</>}
              </button>
          </div>
          {detail && !detail.summary.graphComplete && (
            <div className="mt-3 border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              这次运行的 run_graph 不完整，页面已从事件流和目录文件兜底重建。
            </div>
          )}
        </section>

        <section className="space-y-4">
          <SectionShell
            title="入口与方向拆分"
            subtitle="用户输入、配置快照、Planning Agent 提示词和拆分后的研究方向"
            badge={`${planningNodes.length} 个节点`}
            collapsed={!!collapsedSections.planning}
            onToggle={() => toggleSection('planning')}
          >
            <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
              {planningNodes.map((node) => (
                <NodeButton key={node.id} node={node} selected={node.id === selectedNodeId} onClick={() => setSelectedNodeId(node.id)} />
              ))}
            </div>
          </SectionShell>

          {visibleRoundGroups.map(({ round, tasks }) => (
            <SectionShell
              key={round.id}
              title={round.label}
              subtitle={round.preview?.研究方向 || round.direction_text || `Round ${round.round_idx ?? '--'} ${round.phase || ''}`}
              badge={`${tasks.length} 个任务`}
              collapsed={!!collapsedSections[round.id]}
              onToggle={() => toggleSection(round.id)}
            >
              <div className="border-l-2 border-primary/20 pl-4">
                <NodeButton node={round} selected={round.id === selectedNodeId} onClick={() => setSelectedNodeId(round.id)} />
              </div>
              <div className="mt-4 space-y-3">
                {tasks.map(({ task, children }) => (
                  <SectionShell
                    key={task.id}
                    title={task.label}
                    subtitle={task.preview?.研究方向 || task.direction_text || '任务下包含假设、公式、候选因子、校验和评价节点'}
                    badge={`${children.length} 个子节点`}
                    collapsed={!!collapsedSections[task.id]}
                    onToggle={() => toggleSection(task.id)}
                  >
                    <div className="border-l-2 border-border pl-4">
                      <NodeButton node={task} selected={task.id === selectedNodeId} onClick={() => setSelectedNodeId(task.id)} />
                      <div className="mt-3 space-y-2">
                        {children.map((node) => (
                          <NodeButton key={node.id} node={node} depth={1} selected={node.id === selectedNodeId} onClick={() => setSelectedNodeId(node.id)} />
                        ))}
                      </div>
                    </div>
                  </SectionShell>
                ))}
              </div>
            </SectionShell>
          ))}

          {!visibleRoundGroups.length && !loadingDetail && (
            <div className="border border-dashed border-border p-6 text-sm text-muted-foreground">当前运行没有可展示的轮次节点。</div>
          )}

          {loadingDetail && <div className="flex items-center justify-center border border-border p-10 text-sm text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" />正在读取运行轨迹</div>}
        </section>
      </main>

      <aside className="glass h-fit max-h-[calc(100vh-7rem)] overflow-y-auto border border-border p-4 xl:sticky xl:top-28">
        {selectedNode ? (
          <div className="space-y-5">
            <div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{typeLabels[selectedNode.type] || selectedNode.type}</span>
                <span>/</span>
                <span>{selectedNode.status || '--'}</span>
              </div>
              <h3 className="mt-1 break-words text-xl font-semibold">{selectedNode.label}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{selectedNode.explanation}</p>
            </div>

            <section>
              <h4 className="mb-2 text-sm font-semibold">关键输入 / 输出</h4>
              {selectedNode.preview && Object.keys(selectedNode.preview).length ? (
                <div className="space-y-3">
                  {Object.entries(selectedNode.preview).map(([key, value]) => (
                    <div key={key} className="border-t border-border pt-3">
                      <div className="text-xs font-medium text-muted-foreground">{previewLabels[key] || key}</div>
                      <DetailValue value={value} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="border border-dashed border-border p-3 text-sm text-muted-foreground">这个节点暂无可摘要字段，请展开原始文件查看。</div>
              )}
            </section>

            <section>
              <h4 className="mb-2 text-sm font-semibold">文件位置</h4>
              <code className="block break-all border-y border-border py-2 text-xs text-muted-foreground">{selectedNode.path || '--'}</code>
            </section>

            <details open className="border border-border">
              <summary className="cursor-pointer bg-secondary/60 px-3 py-2 text-sm font-semibold">原始文件内容</summary>
              <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap p-3 text-xs leading-5">
                {artifact ? JSON.stringify(artifact.content, null, 2) : '无法读取或该节点没有独立文件。'}
              </pre>
            </details>
          </div>
        ) : (
          <div className="border border-dashed border-border p-5 text-sm text-muted-foreground">点击中间任意节点查看细节。</div>
        )}
      </aside>
    </div>
  );
};
