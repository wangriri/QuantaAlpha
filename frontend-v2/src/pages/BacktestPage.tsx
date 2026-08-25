import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Archive, BarChart3, Check, ChevronDown, FileSearch, Loader2, Play, RefreshCw, ShieldCheck, Square, X } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { useTaskContext } from '@/context/TaskContext';
import { archiveDuplicateFactors, generateDedupReport, getDedupReport, getEvaluationConfig, getFactors, listDedupReports, listFactorLibraries } from '@/services/api';
import type { EvaluationConfig } from '@/services/api';
import type { Factor } from '@/types';

type EvaluationMode = 'unevaluated' | 'all' | 'specified';

const statusLabel: Record<string, string> = {
  not_evaluated: '未评估', passed: '通过', failed: '未通过', lookahead_rejected: '防未来拒绝',
  data_error: '可重试错误', duplicate_suspected: '疑似重复', duplicate_rejected: '已归档',
};
const formatNumber = (value: unknown, digits = 3) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--';

const Gate: React.FC<{ label: string; passed?: boolean; value?: number; threshold?: number; percent?: boolean }> = ({ label, passed, value, threshold, percent }) => (
  <div className="min-w-0 border-l-2 border-border py-1 pl-3">
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      {passed === true ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : passed === false ? <X className="h-3.5 w-3.5 text-red-500" /> : null}<span>{label}</span>
    </div>
    <div className="mt-1 text-lg font-semibold">
      {formatNumber(percent && typeof value === 'number' ? value * 100 : value)}{percent && typeof value === 'number' ? '%' : ''}
      {typeof threshold === 'number' && <span className="ml-2 text-xs font-normal text-muted-foreground">门槛 {percent ? `${(threshold * 100).toFixed(0)}%` : threshold}</span>}
    </div>
  </div>
);

export const BacktestPage: React.FC = () => {
  const { backendAvailable, backtestTask: task, backtestLogs: logs, startBacktestTask, stopBacktestTask } = useTaskContext();
  const [libraries, setLibraries] = useState<string[]>([]);
  const [selectedLibrary, setSelectedLibrary] = useState(localStorage.getItem('quantaalpha_active_library') || '');
  const [factors, setFactors] = useState<Factor[]>([]);
  const [mode, setMode] = useState<EvaluationMode>('unevaluated');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [refreshMarketCache, setRefreshMarketCache] = useState(false);
  const [config, setConfig] = useState<EvaluationConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [reports, setReports] = useState<any[]>([]);
  const [activeReport, setActiveReport] = useState<any | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<string[] | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const loadLibraries = useCallback(async () => {
    const response = await listFactorLibraries();
    const next = response.data?.libraries || [];
    setLibraries(next);
    if (next.length && (!selectedLibrary || !next.includes(selectedLibrary))) setSelectedLibrary(next[0]);
  }, [selectedLibrary]);

  const loadFactors = useCallback(async () => {
    if (!selectedLibrary) return;
    setLoading(true);
    try {
      const response = await getFactors({ library: selectedLibrary, limit: 500 });
      setFactors(response.data?.factors || []);
      setSelectedIds(new Set());
      localStorage.setItem('quantaalpha_active_library', selectedLibrary);
    } finally { setLoading(false); }
  }, [selectedLibrary]);

  const loadReports = useCallback(async () => {
    const response = await listDedupReports();
    setReports(response.data?.reports || []);
  }, []);

  useEffect(() => {
    loadLibraries().catch(() => undefined);
    getEvaluationConfig().then((response) => setConfig(response.data?.config || null)).catch(() => undefined);
    loadReports().catch(() => undefined);
  }, []);
  useEffect(() => { loadFactors().catch(() => undefined); }, [loadFactors]);
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);
  useEffect(() => {
    if (task?.status === 'completed') { loadFactors().catch(() => undefined); loadReports().catch(() => undefined); }
  }, [task?.status]);

  const counts = useMemo(() => factors.reduce<Record<string, number>>((result, factor) => {
    const key = factor.lifecycle?.status === 'duplicate_rejected' ? 'archived' : factor.evaluationStatus || 'not_evaluated';
    result[key] = (result[key] || 0) + 1;
    return result;
  }, {}), [factors]);
  const isRunning = task?.status === 'running';
  const metrics = task?.metrics || {};

  const start = async () => {
    if (!selectedLibrary || (mode === 'specified' && !selectedIds.size)) return;
    setStarting(true);
    try {
      await startBacktestTask({ factorJson: selectedLibrary, mode, factorIds: mode === 'specified' ? Array.from(selectedIds) : undefined, refreshMarketCache });
    } finally { setStarting(false); }
  };

  const openReport = async (reportId: string) => {
    setReportLoading(true);
    try { const response = await getDedupReport(reportId); setActiveReport(response.data?.report || null); }
    finally { setReportLoading(false); }
  };
  const createReport = async () => {
    if (!selectedLibrary) return;
    setReportLoading(true);
    try { const response = await generateDedupReport(selectedLibrary); setActiveReport(response.data?.report || null); await loadReports(); }
    finally { setReportLoading(false); }
  };
  const archiveConfirmed = async () => {
    if (!activeReport || !confirmArchive) return;
    await archiveDuplicateFactors(activeReport.report_id, confirmArchive);
    setConfirmArchive(null);
    await Promise.all([openReport(activeReport.report_id), loadFactors(), loadReports()]);
  };

  return (
    <div className="space-y-5 animate-fade-in-up">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div><h1 className="flex items-center gap-3 text-3xl font-bold"><BarChart3 className="h-8 w-8 text-primary" />因子评估中心</h1><p className="mt-1 text-sm text-muted-foreground">单因子 OTO 评估，训练方向锁定后再进入验证集</p></div>
        <Badge variant="outline"><ShieldCheck className="mr-1 h-3.5 w-3.5" />2026 样本外已封存</Badge>
      </div>

      {backendAvailable === false && <div className="flex items-center gap-2 border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500"><AlertCircle className="h-4 w-4" />后端服务未连接</div>}

      <Card className="glass">
        <CardHeader><CardTitle className="text-base">评估批次</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_minmax(360px,1.3fr)]">
            <div><label className="mb-2 block text-sm font-medium">因子库</label><div className="relative"><select value={selectedLibrary} onChange={(event) => setSelectedLibrary(event.target.value)} disabled={isRunning} className="w-full appearance-none rounded-md border border-input bg-background px-3 py-2.5 pr-9 text-sm">{libraries.map((library) => <option value={library} key={library}>{library}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-muted-foreground" /></div></div>
            <div><label className="mb-2 block text-sm font-medium">评估范围</label><div className="grid grid-cols-3 gap-1 rounded-md bg-secondary/60 p-1">{([['unevaluated', '未评估'], ['specified', '指定因子'], ['all', '全部重评']] as const).map(([value, label]) => <button key={value} onClick={() => setMode(value)} disabled={isRunning} className={`rounded px-3 py-2 text-sm ${mode === value ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'}`}>{label}</button>)}</div></div>
          </div>

          <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground"><span>共 {factors.length}</span><span>未评估 {counts.not_evaluated || 0}</span><span className="text-emerald-500">通过 {counts.passed || 0}</span><span className="text-red-500">未通过 {(counts.failed || 0) + (counts.lookahead_rejected || 0)}</span><span>已归档 {counts.archived || 0}</span></div>

          {mode === 'specified' && <div className="max-h-64 overflow-y-auto border-y border-border">{loading ? <div className="p-4 text-sm text-muted-foreground">加载中...</div> : factors.map((factor) => <label key={factor.factorId} className="grid cursor-pointer grid-cols-[24px_minmax(0,1fr)_110px] items-center gap-2 border-b border-border/60 px-3 py-2.5 last:border-0 hover:bg-secondary/30"><input type="checkbox" checked={selectedIds.has(factor.factorId)} onChange={() => setSelectedIds((current) => { const next = new Set(current); next.has(factor.factorId) ? next.delete(factor.factorId) : next.add(factor.factorId); return next; })} /><span className="truncate text-sm" title={factor.factorName}>{factor.factorName}</span><span className="text-right text-xs text-muted-foreground">{statusLabel[factor.evaluationStatus || 'not_evaluated']}</span></label>)}</div>}

          <div className="grid gap-3 border-y border-border py-4 text-sm md:grid-cols-3"><div><span className="text-muted-foreground">训练：</span>{config ? `${config.trainingStart} 至 ${config.trainingEnd}` : '--'}</div><div><span className="text-muted-foreground">验证：</span>{config ? `${config.validationStart} 至 ${config.validationEnd}` : '--'}</div><div><span className="text-muted-foreground">时间对齐：</span>F(t-1) → open(t) → open(t+1)</div></div>
          <div className="flex flex-wrap items-center justify-between gap-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={refreshMarketCache} onChange={(event) => setRefreshMarketCache(event.target.checked)} disabled={isRunning} />刷新 Mongo 行情缓存</label>{isRunning ? <Button variant="outline" onClick={stopBacktestTask}><Square className="mr-2 h-4 w-4" />取消评估</Button> : <Button variant="primary" onClick={start} disabled={starting || !selectedLibrary || (mode === 'specified' && !selectedIds.size)}>{starting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}启动评估</Button>}</div>
        </CardContent>
      </Card>

      {task && <Card className="glass"><CardHeader><CardTitle className="flex items-center justify-between text-base"><span>批次进度</span><Badge variant={task.status === 'failed' ? 'destructive' : 'outline'}>{task.status === 'running' ? '运行中' : task.status === 'completed' ? '已完成' : task.status === 'cancelled' ? '已取消' : '失败'}</Badge></CardTitle></CardHeader><CardContent className="space-y-4"><div><div className="mb-2 flex justify-between text-sm"><span className="truncate text-muted-foreground">{task.progress?.message}</span><span>{Math.round(task.progress?.progress || 0)}%</span></div><div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full bg-primary transition-all" style={{ width: `${task.progress?.progress || 0}%` }} /></div></div><div className="grid grid-cols-2 gap-4 md:grid-cols-4"><Gate label="总数" value={metrics.total || metrics.totalFactors} /><Gate label="已完成" value={metrics.completed || metrics.completedFactors} /><Gate label="训练通过" value={metrics.passed || metrics.passedFactors} passed={(metrics.passed || metrics.passedFactors) > 0} /><Gate label="未通过/错误" value={metrics.failed || metrics.failedFactors} passed={(metrics.failed || metrics.failedFactors) === 0} /></div>{logs.length > 0 && <div className="max-h-52 overflow-y-auto bg-black/40 p-3 font-mono text-xs">{logs.map((log) => <div key={log.id} className={log.level === 'error' ? 'text-red-400' : 'text-muted-foreground'}>{new Date(log.timestamp).toLocaleTimeString()} {log.message}</div>)}<div ref={logsEndRef} /></div>}</CardContent></Card>}

      <Card className="glass"><CardHeader><CardTitle className="flex items-center justify-between text-base"><span className="flex items-center gap-2"><FileSearch className="h-4 w-4" />重复因子报告</span><Button variant="outline" size="sm" onClick={createReport} disabled={!selectedLibrary || reportLoading}>{reportLoading ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-2 h-3.5 w-3.5" />}生成报告</Button></CardTitle></CardHeader><CardContent>
        {!reports.length ? <p className="text-sm text-muted-foreground">暂无报告。完整实验或批次结束后会自动生成。</p> : <div className="divide-y divide-border border-y border-border">{reports.map((report) => <button key={report.reportId} onClick={() => openReport(report.reportId)} className="grid w-full grid-cols-[minmax(0,1fr)_90px_90px] gap-3 px-2 py-3 text-left text-sm hover:bg-secondary/30"><span className="truncate">{report.library} · {new Date(report.createdAt).toLocaleString()}</span><span>{report.clusterCount} 个重复簇</span><span className="text-right text-muted-foreground">{report.status === 'applied' ? '已处理' : '待确认'}</span></button>)}</div>}
        {activeReport && <div className="mt-5 space-y-3 border-t border-border pt-4"><div className="flex items-center justify-between"><h3 className="font-medium">{activeReport.report_id}</h3><Badge variant="outline">阈值 |ρ| ≥ {activeReport.threshold}</Badge></div>{!activeReport.clusters?.length ? <p className="text-sm text-muted-foreground">当前范围没有达到阈值的重复因子。</p> : activeReport.clusters.map((cluster: any, index: number) => <div key={`${cluster.direction}-${index}`} className="grid gap-3 border-b border-border pb-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"><div><div className="text-xs text-muted-foreground">研究方向</div><div className="truncate text-sm">{cluster.direction}</div></div><div><div className="text-xs text-muted-foreground">推荐保留</div><div className="truncate text-sm text-emerald-500">{cluster.recommended_keep}</div></div>{activeReport.status === 'pending_confirmation' && <Button variant="outline" size="sm" onClick={() => setConfirmArchive(cluster.recommended_archive)}><Archive className="mr-2 h-3.5 w-3.5" />确认归档其余 {cluster.recommended_archive.length} 个</Button>}</div>)}</div>}
      </CardContent></Card>

      {confirmArchive && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"><div className="w-full max-w-lg rounded-md border border-border bg-background p-5 shadow-2xl"><h2 className="text-lg font-semibold">确认归档重复因子</h2><p className="mt-2 text-sm text-muted-foreground">这些因子会被标记为 duplicate_rejected 并移出活跃池，公式、指标和缓存不会删除。</p><div className="mt-4 max-h-40 overflow-y-auto border-y border-border py-2 font-mono text-xs">{confirmArchive.map((id) => <div key={id} className="py-1">{id}</div>)}</div><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setConfirmArchive(null)}>取消</Button><Button variant="primary" onClick={archiveConfirmed}><Archive className="mr-2 h-4 w-4" />确认归档</Button></div></div></div>}
    </div>
  );
};
