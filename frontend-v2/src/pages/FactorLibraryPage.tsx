import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Check, Code, Database, Download, ExternalLink, RefreshCw, Search, ShieldCheck, X } from 'lucide-react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { getEvaluationArtifact, getFactorDetail, getFactors } from '@/services/api';
import type { Factor } from '@/types';

type StatusFilter = 'all' | 'not_evaluated' | 'passed' | 'failed' | 'duplicate_suspected' | 'archived';
const labels: Record<string, string> = { not_evaluated: '未评估', passed: '通过', failed: '未通过', lookahead_rejected: '防未来拒绝', data_error: '可重试错误', duplicate_suspected: '疑似重复', duplicate_rejected: '已归档' };
const number = (value: unknown, digits = 3) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--';
const statusOf = (factor: Factor) => factor.lifecycle?.status === 'duplicate_rejected' ? 'archived' : factor.lifecycle?.status === 'duplicate_suspected' ? 'duplicate_suspected' : factor.evaluationStatus || 'not_evaluated';

const Metric: React.FC<{ label: string; value: unknown; passed?: boolean }> = ({ label, value, passed }) => (
  <div className="border-l-2 border-border py-1 pl-3"><div className="flex items-center gap-1 text-xs text-muted-foreground">{passed === true ? <Check className="h-3 w-3 text-emerald-500" /> : passed === false ? <X className="h-3 w-3 text-red-500" /> : null}{label}</div><div className="mt-1 font-mono text-base font-semibold">{number(value)}</div></div>
);

const ArtifactChart: React.FC<{ title: string; path?: string; kind: 'ic' | 'groups' | 'excess' | 'decay' }> = ({ title, path, kind }) => {
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  useEffect(() => {
    if (!path) { setRows([]); return; }
    getEvaluationArtifact(path).then((response) => setRows((response.data?.rows || []).map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, key === 'date' ? value : Number(value)]))))).catch(() => setRows([]));
  }, [path]);
  if (!path) return null;
  const xKey = kind === 'decay' ? 'lag' : 'date';
  const keys = kind === 'groups' ? ['G0', 'G9'] : kind === 'excess' ? ['head_net_return', 'benchmark_net_return', 'excess_return'] : kind === 'decay' ? ['ic', 'rank_ic'] : ['ic', 'rank_ic'];
  const colors = ['#22c55e', '#ef4444', '#3b82f6'];
  return <div className="border-t border-border pt-4"><h4 className="mb-3 text-sm font-medium">{title}</h4>{rows.length ? <div className="h-56"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows}><XAxis dataKey={xKey} tick={{ fontSize: 10 }} minTickGap={40} /><YAxis tick={{ fontSize: 10 }} width={48} /><Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 12 }} />{keys.map((key, index) => <Line key={key} type="monotone" dataKey={key} dot={false} stroke={colors[index]} strokeWidth={1.5} connectNulls />)}</LineChart></ResponsiveContainer></div> : <p className="text-sm text-muted-foreground">产物暂无可读数据</p>}</div>;
};

export const FactorLibraryPage: React.FC = () => {
  const [factors, setFactors] = useState<Factor[]>([]);
  const [libraries, setLibraries] = useState<string[]>([]);
  const [library, setLibrary] = useState(localStorage.getItem('quantaalpha_active_library') || '');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [selected, setSelected] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await getFactors({ library: library || undefined, limit: 500 });
      setFactors(response.data?.factors || []); setLibraries(response.data?.libraries || []);
      if (!library && response.data?.libraries?.[0]) setLibrary(response.data.libraries[0]);
    } catch { setError('无法读取因子库，请检查后端服务。'); }
    finally { setLoading(false); }
  }, [library]);
  useEffect(() => { load(); }, [load]);

  const counts = useMemo(() => factors.reduce<Record<string, number>>((out, factor) => { const key = statusOf(factor); out[key] = (out[key] || 0) + 1; return out; }, {}), [factors]);
  const visible = useMemo(() => factors.filter((factor) => {
    const matchStatus = filter === 'all' || (filter === 'failed' ? ['failed', 'lookahead_rejected', 'data_error'].includes(statusOf(factor)) : statusOf(factor) === filter);
    const query = search.toLowerCase();
    return matchStatus && (!query || `${factor.factorName} ${factor.factorExpression} ${factor.factorDescription}`.toLowerCase().includes(query));
  }), [factors, filter, search]);

  const select = async (factor: Factor) => {
    try { const response = await getFactorDetail(factor.factorId); setSelected({ ...factor, ...(response.data?.factor || {}) }); }
    catch { setSelected(factor); }
  };
  const exportLibrary = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(factors, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `factors_${new Date().toISOString().slice(0, 10)}.json`; anchor.click(); URL.revokeObjectURL(url);
  };

  const evaluation = selected?.evaluation_v2 || {};
  const training = evaluation.training || selected?.trainingMetrics || {};
  const validation = evaluation.validation || selected?.validationMetrics || {};
  const gates = evaluation.gate_results || selected?.gateResults || {};
  const artifacts = evaluation.artifacts || selected?.artifacts || {};

  return <div className="space-y-5 animate-fade-in-up">
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><h1 className="flex items-center gap-3 text-3xl font-bold"><Database className="h-8 w-8 text-primary" />因子库</h1><p className="mt-1 text-sm text-muted-foreground">evaluation_v2 指标、生命周期和审计产物</p></div><div className="flex gap-2"><select value={library} onChange={(event) => { setLibrary(event.target.value); localStorage.setItem('quantaalpha_active_library', event.target.value); }} className="max-w-64 rounded-md border border-input bg-background px-3 py-2 text-sm">{libraries.map((item) => <option key={item}>{item}</option>)}</select><Button variant="outline" onClick={load} title="刷新"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /></Button><Button variant="outline" onClick={exportLibrary} title="导出"><Download className="h-4 w-4" /></Button></div></div>
    {error && <div className="flex items-center gap-2 border border-red-500/30 px-4 py-3 text-sm text-red-500"><AlertCircle className="h-4 w-4" />{error}</div>}

    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{([['全部', factors.length], ['未评估', counts.not_evaluated || 0], ['通过', counts.passed || 0], ['未通过', (counts.failed || 0) + (counts.lookahead_rejected || 0) + (counts.data_error || 0)], ['已归档', counts.archived || 0]] as const).map(([label, value]) => <div key={label} className="border-y border-border px-2 py-3"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-2xl font-semibold">{value}</div></div>)}</div>

    <Card className="glass"><CardContent className="flex flex-col gap-3 p-4 lg:flex-row"><div className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索名称、表达式或描述" className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm" /></div><div className="flex flex-wrap gap-1">{([['all', '全部'], ['not_evaluated', '未评估'], ['passed', '通过'], ['failed', '未通过'], ['duplicate_suspected', '疑似重复'], ['archived', '已归档']] as const).map(([key, label]) => <button key={key} onClick={() => setFilter(key)} className={`rounded px-3 py-2 text-xs ${filter === key ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>{label}</button>)}</div></CardContent></Card>

    <div className="overflow-x-auto border-y border-border"><table className="w-full min-w-[900px] text-left text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-3 font-medium">因子</th><th className="px-3 py-3 font-medium">状态</th><th className="px-3 py-3 font-medium">方向</th><th className="px-3 py-3 font-medium">IC</th><th className="px-3 py-3 font-medium">ICIR</th><th className="px-3 py-3 font-medium">收益差</th><th className="px-3 py-3 font-medium">超额 Sharpe</th></tr></thead><tbody className="divide-y divide-border">{visible.map((factor) => <tr key={factor.factorId} onClick={() => select(factor)} className="cursor-pointer hover:bg-secondary/30"><td className="max-w-sm px-3 py-3"><div className="truncate font-medium" title={factor.factorName}>{factor.factorName}</div><div className="mt-1 truncate font-mono text-xs text-muted-foreground">{factor.factorExpression}</div></td><td className="px-3 py-3"><Badge variant="outline">{labels[statusOf(factor)] || statusOf(factor)}</Badge></td><td className="px-3 py-3 font-mono">{factor.directionMultiplier === -1 ? '-1' : factor.directionMultiplier === 1 ? '+1' : '--'}</td><td className="px-3 py-3 font-mono">{number(factor.trainingMetrics?.ic ?? factor.ic, 4)}</td><td className="px-3 py-3 font-mono">{number(factor.trainingMetrics?.icir ?? factor.icir)}</td><td className="px-3 py-3 font-mono">{number(factor.trainingMetrics?.long_short_spread)}</td><td className="px-3 py-3 font-mono">{number(factor.trainingMetrics?.excess_sharpe)}</td></tr>)}</tbody></table>{!visible.length && <div className="py-14 text-center text-sm text-muted-foreground">没有符合条件的因子</div>}</div>

    {selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelected(null)}><div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-md border border-border bg-background shadow-2xl" onClick={(event) => event.stopPropagation()}><div className="sticky top-0 z-10 flex items-start justify-between border-b border-border bg-background px-5 py-4"><div className="min-w-0"><h2 className="break-words text-xl font-semibold">{selected.factorName || selected.factor_name}</h2><div className="mt-2 flex flex-wrap gap-2"><Badge variant="outline">{labels[evaluation.status || selected.evaluationStatus || 'not_evaluated']}</Badge><Badge variant="outline">方向 {evaluation.direction_multiplier === -1 ? '-1' : '+1'}</Badge><Badge variant="outline"><ShieldCheck className="mr-1 h-3 w-3" />2026 {evaluation.oos_status || selected.oosStatus || 'sealed'}</Badge></div></div><Button variant="ghost" onClick={() => setSelected(null)} title="关闭"><X className="h-4 w-4" /></Button></div>
      <div className="space-y-6 p-5">
        <section><h3 className="mb-3 text-sm font-medium">四项训练门槛</h3><div className="grid grid-cols-2 gap-4 md:grid-cols-4"><Metric label="|IC|" value={gates.ic?.value ?? training.ic_abs} passed={gates.ic?.passed} /><Metric label="ICIR" value={gates.icir?.value ?? training.icir} passed={gates.icir?.passed} /><Metric label="G9-G0 算术收益差" value={gates.long_short_spread?.value ?? training.long_short_spread} passed={gates.long_short_spread?.passed} /><Metric label="头组超额 Sharpe" value={gates.excess_sharpe?.value ?? training.excess_sharpe} passed={gates.excess_sharpe?.passed} /></div></section>
        <section className="grid gap-4 md:grid-cols-2"><div><h3 className="mb-3 text-sm font-medium">训练 / 验证</h3><div className="overflow-hidden border-y border-border text-sm"><div className="grid grid-cols-3 px-2 py-2 text-xs text-muted-foreground"><span>区间</span><span>IC</span><span>超额 Sharpe</span></div><div className="grid grid-cols-3 border-t border-border px-2 py-2"><span>训练</span><span>{number(training.ic, 4)}</span><span>{number(training.excess_sharpe)}</span></div><div className="grid grid-cols-3 border-t border-border px-2 py-2"><span>2025H2</span><span>{number(validation.ic, 4)}</span><span>{number(validation.excess_sharpe)}</span></div>{Object.entries(evaluation.subperiods || selected.subperiods || {}).map(([name, metrics]: [string, any]) => <div key={name} className="grid grid-cols-3 border-t border-border px-2 py-2"><span>{name}</span><span>{number(metrics.ic, 4)}</span><span>{number(metrics.excess_sharpe)}</span></div>)}</div></div><div><h3 className="mb-3 text-sm font-medium">时间与防未来审计</h3><div className="space-y-2 text-sm"><div className="flex justify-between"><span className="text-muted-foreground">因子早于开仓</span><span>{evaluation.alignment?.factor_before_entry ? '通过' : '未通过'}</span></div><div className="flex justify-between"><span className="text-muted-foreground">开仓早于退出</span><span>{evaluation.alignment?.entry_before_exit ? '通过' : '未通过'}</span></div><div className="flex justify-between"><span className="text-muted-foreground">静态检查</span><span>{evaluation.lookahead_audit?.static?.status || '--'}</span></div><div className="flex justify-between"><span className="text-muted-foreground">截断重算</span><span>{evaluation.lookahead_audit?.truncation?.status || '--'}</span></div><div className="flex justify-between"><span className="text-muted-foreground">有效日 / 预期日</span><span>{training.coverage?.valid_days ?? '--'} / {training.coverage?.expected_days ?? '--'}</span></div></div></div></section>
        <section><h3 className="mb-2 flex items-center gap-2 text-sm font-medium"><Code className="h-4 w-4" />因子表达式</h3><code className="block break-all border-y border-border py-3 text-xs">{selected.factorExpression || selected.factor_expression}</code></section>
        <ArtifactChart title="训练期每日 IC" path={artifacts.training_daily_ic} kind="ic" /><ArtifactChart title="IC 衰减与半衰期" path={artifacts.ic_decay} kind="decay" /><ArtifactChart title="十分组累计收益（G0 低值，G9 高值）" path={artifacts.training_group_cumulative} kind="groups" /><ArtifactChart title="头组、等权基线与超额收益" path={artifacts.training_excess_returns} kind="excess" />
        <section><h3 className="mb-2 text-sm font-medium">产物文件</h3><div className="grid gap-2 md:grid-cols-2">{Object.entries(artifacts).map(([name, path]) => <div key={name} className="flex min-w-0 items-center gap-2 border-b border-border py-2 text-xs"><ExternalLink className="h-3.5 w-3.5 shrink-0" /><span className="shrink-0 text-muted-foreground">{name}</span><span className="truncate font-mono" title={String(path)}>{String(path)}</span></div>)}</div></section>
      </div></div></div>}
  </div>;
};
