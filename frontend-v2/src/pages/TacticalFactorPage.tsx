import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertCircle, ChevronDown, Flame, Loader2, RefreshCw, RotateCcw, Save, Search, Settings2, ShieldCheck, X, Zap } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { analyzeTacticalFactors, getTacticalConfig, listFactorLibraries, updateTacticalConfig } from '@/services/api';
import type { TacticalAnalyzeResponse, TacticalConfig, TacticalFactorResult, TacticalLabel, TacticalPeriodResult } from '@/types';

type LabelFilter = 'all' | TacticalLabel;

const tacticalLabels: TacticalLabel[] = ['战术进攻型', '高风险爆发型', '稳健候选型', '暂无战术价值', '数据不足'];
const statusLabel: Record<string, string> = {
  not_evaluated: '未评估',
  passed: '通过',
  failed: '未通过',
  lookahead_rejected: '防未来拒绝',
  data_error: '可重试错误',
  running: '运行中',
};

const labelBadgeVariant = (label: string) => {
  if (label === '战术进攻型') return 'warning';
  if (label === '高风险爆发型') return 'destructive';
  if (label === '稳健候选型') return 'success';
  return 'outline';
};

const number = (value: unknown, digits = 3) => (
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--'
);

const percent = (value: unknown, digits = 1) => (
  typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : '--'
);

const chartTooltipStyle = {
  background: '#ffffff',
  border: '1px solid #cbd5e1',
  borderRadius: 6,
  boxShadow: '0 12px 28px rgba(15, 23, 42, 0.16)',
  color: '#0f172a',
  fontSize: 12,
};

const chartLabelStyle = {
  color: '#0f172a',
  fontWeight: 600,
};

const chartItemStyle = {
  color: '#0f172a',
};

const ConfigNumber: React.FC<{
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  percentInput?: boolean;
  onChange: (value: number) => void;
}> = ({ label, value, min, max, step = 1, percentInput, onChange }) => (
  <label className="grid gap-1.5">
    <span className="text-xs text-muted-foreground">{label}</span>
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={percentInput ? number(value * 100, 0) : value}
      onChange={(event) => {
        const next = Number(event.target.value);
        if (Number.isFinite(next)) onChange(percentInput ? next / 100 : next);
      }}
      className="h-10 rounded-md border border-input bg-background px-3 font-mono text-sm"
    />
  </label>
);

const Metric: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="border-l-2 border-border py-1 pl-3">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className="mt-1 font-mono text-base font-semibold">{value}</div>
  </div>
);

const SummaryTile: React.FC<{ label: string; value: number; accent?: string }> = ({ label, value, accent }) => (
  <div className="border-y border-border px-3 py-4">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className={`mt-1 text-2xl font-semibold ${accent || ''}`}>{value}</div>
  </div>
);

const MonthlyCharts: React.FC<{ period: TacticalPeriodResult }> = ({ period }) => {
  if (!period.monthly.length) return <div className="border-y border-border py-8 text-center text-sm text-muted-foreground">暂无月度数据</div>;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="border-y border-border py-4">
        <h4 className="mb-3 text-sm font-medium">月度超额</h4>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={period.monthly}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} minTickGap={24} />
              <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(value) => percent(value, 1)} />
              <Tooltip
                contentStyle={chartTooltipStyle}
                labelStyle={chartLabelStyle}
                itemStyle={chartItemStyle}
                formatter={(value) => [percent(value, 1), '月度超额']}
              />
              <Bar dataKey="monthly_excess" radius={[3, 3, 0, 0]}>
                {period.monthly.map((row) => (
                  <Cell key={row.month} fill={row.is_burst ? '#f97316' : row.monthly_excess >= 0 ? '#10b981' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="border-y border-border py-4">
        <h4 className="mb-3 text-sm font-medium">累计月度超额</h4>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={period.monthly}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} minTickGap={24} />
              <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(value) => percent(value, 1)} />
              <Tooltip
                contentStyle={chartTooltipStyle}
                labelStyle={chartLabelStyle}
                itemStyle={chartItemStyle}
                formatter={(value) => [percent(value, 1), '累计月度超额']}
              />
              <Line type="monotone" dataKey="cumulative_excess" stroke="#2563eb" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export const TacticalFactorPage: React.FC = () => {
  const [libraries, setLibraries] = useState<string[]>([]);
  const [selectedLibrary, setSelectedLibrary] = useState(localStorage.getItem('quantaalpha_active_library') || '');
  const [draft, setDraft] = useState<TacticalConfig | null>(null);
  const [defaults, setDefaults] = useState<TacticalConfig | null>(null);
  const [result, setResult] = useState<TacticalAnalyzeResponse | null>(null);
  const [selected, setSelected] = useState<TacticalFactorResult | null>(null);
  const [detailPeriod, setDetailPeriod] = useState<'training' | 'validation'>('training');
  const [labelFilter, setLabelFilter] = useState<LabelFilter>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const loadBase = useCallback(async () => {
    setError('');
    try {
      const [libraryResponse, configResponse] = await Promise.all([listFactorLibraries(), getTacticalConfig()]);
      const nextLibraries = libraryResponse.data?.libraries || [];
      setLibraries(nextLibraries);
      setDraft(configResponse.data?.config || null);
      setDefaults(configResponse.data?.defaults || configResponse.data?.config || null);
      if (nextLibraries.length && (!selectedLibrary || !nextLibraries.includes(selectedLibrary))) {
        setSelectedLibrary(nextLibraries[0]);
        localStorage.setItem('quantaalpha_active_library', nextLibraries[0]);
      }
    } catch {
      setError('无法读取战术因子配置或因子库列表。');
    }
  }, [selectedLibrary]);

  useEffect(() => {
    loadBase().catch(() => undefined);
  }, [loadBase]);

  const updateDraft = <K extends keyof TacticalConfig>(key: K, value: TacticalConfig[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current);
  };

  const saveConfig = async () => {
    if (!draft) return;
    setSaving(true);
    setError('');
    try {
      const response = await updateTacticalConfig(draft);
      setDraft(response.data?.config || draft);
    } catch {
      setError('战术因子配置保存失败。');
    } finally {
      setSaving(false);
    }
  };

  const restoreDefaults = async () => {
    if (!defaults) return;
    setSaving(true);
    setError('');
    try {
      const response = await updateTacticalConfig(defaults);
      setDraft(response.data?.config || defaults);
    } catch {
      setError('恢复默认战术阈值失败。');
    } finally {
      setSaving(false);
    }
  };

  const analyze = async () => {
    if (!selectedLibrary) return;
    setLoading(true);
    setError('');
    setSelected(null);
    try {
      const response = await analyzeTacticalFactors(selectedLibrary);
      setResult(response.data || null);
      localStorage.setItem('quantaalpha_active_library', selectedLibrary);
    } catch {
      setError('战术分析失败，请检查后端服务和评估产物。');
    } finally {
      setLoading(false);
    }
  };

  const visible = useMemo(() => {
    const rows = result?.factors || [];
    const query = search.trim().toLowerCase();
    return rows.filter((factor) => {
      const matchLabel = labelFilter === 'all' || factor.training.label === labelFilter;
      const matchSearch = !query || `${factor.factorName} ${factor.factorExpression} ${factor.factorDescription}`.toLowerCase().includes(query);
      return matchLabel && matchSearch;
    });
  }, [result, labelFilter, search]);

  const summary = result?.summary;
  const selectedPeriod = selected && detailPeriod === 'validation' && selected.validation ? selected.validation : selected?.training;

  return (
    <div className="space-y-5 animate-fade-in-up">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="flex items-center gap-3 text-3xl font-bold"><Flame className="h-8 w-8 text-warning" />战术因子</h1>
          <p className="mt-1 text-sm text-muted-foreground">短期爆发、月度波动与风险分层</p>
        </div>
        <Badge variant="outline"><ShieldCheck className="mr-1 h-3.5 w-3.5" />2026 样本外已封存</Badge>
      </div>

      {error && <div className="flex items-center gap-2 border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500"><AlertCircle className="h-4 w-4" />{error}</div>}

      <Card className="glass">
        <CardContent className="grid gap-4 p-4 lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-end">
          <div>
            <label className="mb-2 block text-sm font-medium">因子库</label>
            <div className="relative">
              <select
                value={selectedLibrary}
                onChange={(event) => setSelectedLibrary(event.target.value)}
                className="w-full appearance-none rounded-md border border-input bg-background px-3 py-2.5 pr-9 text-sm"
              >
                {libraries.map((library) => <option value={library} key={library}>{library}</option>)}
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={loadBase} title="刷新基础数据"><RefreshCw className="mr-2 h-4 w-4" />刷新</Button>
            <Button variant="primary" onClick={analyze} disabled={loading || !selectedLibrary}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Zap className="mr-2 h-4 w-4" />}
              开始战术分析
            </Button>
          </div>
        </CardContent>
      </Card>

      {draft && <Card className="glass">
        <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Settings2 className="h-4 w-4" />战术阈值</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <ConfigNumber label="训练最少月份" value={draft.min_training_months} min={1} max={120} onChange={(value) => updateDraft('min_training_months', Math.round(value))} />
            <ConfigNumber label="验证最少月份" value={draft.min_validation_months} min={1} max={120} onChange={(value) => updateDraft('min_validation_months', Math.round(value))} />
            <ConfigNumber label="每月最少交易日" value={draft.min_trading_days_per_month} min={1} max={31} onChange={(value) => updateDraft('min_trading_days_per_month', Math.round(value))} />
            <ConfigNumber label="最佳单月分位" value={draft.strong_best_month_quantile} min={0} max={100} percentInput onChange={(value) => updateDraft('strong_best_month_quantile', value)} />
            <ConfigNumber label="爆发月份分位" value={draft.burst_month_quantile} min={0} max={100} percentInput onChange={(value) => updateDraft('burst_month_quantile', value)} />
            <ConfigNumber label="高波动分位" value={draft.high_volatility_quantile} min={0} max={100} percentInput onChange={(value) => updateDraft('high_volatility_quantile', value)} />
            <ConfigNumber label="严重亏损分位" value={draft.severe_loss_quantile} min={0} max={100} percentInput onChange={(value) => updateDraft('severe_loss_quantile', value)} />
            <ConfigNumber label="严重回撤分位" value={draft.severe_drawdown_quantile} min={0} max={100} percentInput onChange={(value) => updateDraft('severe_drawdown_quantile', value)} />
            <ConfigNumber label="正收益月份比例" value={draft.min_positive_month_ratio} min={0} max={100} percentInput onChange={(value) => updateDraft('min_positive_month_ratio', value)} />
            <ConfigNumber label="最少爆发月份" value={draft.min_burst_month_count} min={0} max={120} onChange={(value) => updateDraft('min_burst_month_count', Math.round(value))} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={restoreDefaults} disabled={saving || !defaults} title="恢复默认阈值">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}
              恢复默认
            </Button>
            <Button variant="outline" onClick={saveConfig} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}保存阈值</Button>
          </div>
        </CardContent>
      </Card>}

      {summary && <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <SummaryTile label="已分析" value={summary.analyzed} />
        <SummaryTile label="战术进攻型" value={summary.labels['战术进攻型'] || 0} accent="text-warning" />
        <SummaryTile label="高风险爆发型" value={summary.labels['高风险爆发型'] || 0} accent="text-red-500" />
        <SummaryTile label="数据不足" value={summary.labels['数据不足'] || 0} />
        <SummaryTile label="跳过" value={summary.skipped} />
      </div>}

      <Card className="glass">
        <CardContent className="flex flex-col gap-3 p-4 xl:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索因子名称、公式或描述" className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm" />
          </div>
          <div className="flex flex-wrap gap-1">
            <button onClick={() => setLabelFilter('all')} className={`rounded px-3 py-2 text-xs ${labelFilter === 'all' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>全部</button>
            {tacticalLabels.map((label) => (
              <button key={label} onClick={() => setLabelFilter(label)} className={`rounded px-3 py-2 text-xs ${labelFilter === label ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>{label}</button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="overflow-x-auto border-y border-border">
        <table className="w-full min-w-[1120px] text-left text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-3 font-medium">因子</th>
              <th className="px-3 py-3 font-medium">主评估</th>
              <th className="px-3 py-3 font-medium">战术标签</th>
              <th className="px-3 py-3 font-medium">分数</th>
              <th className="px-3 py-3 font-medium">最佳单月</th>
              <th className="px-3 py-3 font-medium">最差单月</th>
              <th className="px-3 py-3 font-medium">月度波动</th>
              <th className="px-3 py-3 font-medium">爆发月份</th>
              <th className="px-3 py-3 font-medium">验证标签</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {visible.map((factor) => (
              <tr key={factor.factorId} onClick={() => { setSelected(factor); setDetailPeriod('training'); }} className="cursor-pointer hover:bg-secondary/30">
                <td className="max-w-sm px-3 py-3">
                  <div className="truncate font-medium" title={factor.factorName}>{factor.factorName}</div>
                  <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{factor.factorExpression}</div>
                </td>
                <td className="px-3 py-3"><Badge variant="outline">{statusLabel[factor.evaluationStatus] || factor.evaluationStatus}</Badge></td>
                <td className="px-3 py-3"><Badge variant={labelBadgeVariant(factor.training.label)}>{factor.training.label}</Badge></td>
                <td className="px-3 py-3 font-mono">{number(factor.training.score)}</td>
                <td className="px-3 py-3 font-mono">{percent(factor.training.metrics.best_month_excess)}</td>
                <td className="px-3 py-3 font-mono">{percent(factor.training.metrics.worst_month_excess)}</td>
                <td className="px-3 py-3 font-mono">{percent(factor.training.metrics.monthly_excess_std)}</td>
                <td className="px-3 py-3 font-mono">{factor.training.metrics.burst_month_count ?? 0}</td>
                <td className="px-3 py-3">{factor.validation ? <Badge variant={labelBadgeVariant(factor.validation.label)}>{factor.validation.label}</Badge> : <span className="text-xs text-muted-foreground">--</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!result && <div className="py-16 text-center text-sm text-muted-foreground">尚未运行战术分析</div>}
        {result && !visible.length && <div className="py-16 text-center text-sm text-muted-foreground">没有符合条件的因子</div>}
      </div>

      {selected && selectedPeriod && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelected(null)}>
        <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-md border border-border bg-background shadow-2xl" onClick={(event) => event.stopPropagation()}>
          <div className="sticky top-0 z-10 flex items-start justify-between border-b border-border bg-background px-5 py-4">
            <div className="min-w-0">
              <h2 className="break-words text-xl font-semibold">{selected.factorName}</h2>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant={labelBadgeVariant(selected.training.label)}>{selected.training.label}</Badge>
                <Badge variant="outline">训练分数 {number(selected.training.score)}</Badge>
                {selected.validation && <Badge variant="outline">验证 {selected.validation.label}</Badge>}
              </div>
            </div>
            <Button variant="ghost" onClick={() => setSelected(null)} title="关闭"><X className="h-4 w-4" /></Button>
          </div>
          <div className="space-y-6 p-5">
            <div className="flex flex-wrap gap-1 rounded-md bg-secondary/60 p-1">
              <button onClick={() => setDetailPeriod('training')} className={`rounded px-3 py-2 text-sm ${detailPeriod === 'training' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'}`}>训练期</button>
              <button onClick={() => setDetailPeriod('validation')} disabled={!selected.validation} className={`rounded px-3 py-2 text-sm disabled:opacity-40 ${detailPeriod === 'validation' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'}`}>验证期</button>
            </div>

            <section className="grid gap-4 md:grid-cols-4">
              <Metric label="最佳单月" value={percent(selectedPeriod.metrics.best_month_excess)} />
              <Metric label="最差单月" value={percent(selectedPeriod.metrics.worst_month_excess)} />
              <Metric label="月度波动" value={percent(selectedPeriod.metrics.monthly_excess_std)} />
              <Metric label="正收益月份" value={percent(selectedPeriod.metrics.positive_month_ratio)} />
            </section>

            <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <MonthlyCharts period={selectedPeriod} />
              <div className="space-y-4">
                <div className="border-y border-border py-4">
                  <h4 className="mb-3 flex items-center gap-2 text-sm font-medium"><Activity className="h-4 w-4" />分类理由</h4>
                  <div className="space-y-2">
                    {selectedPeriod.reasons.map((reason) => <div key={reason} className="border-l-2 border-border pl-3 text-sm">{reason}</div>)}
                  </div>
                </div>
                <div className="border-y border-border py-4">
                  <h4 className="mb-3 text-sm font-medium">爆发月份</h4>
                  {selectedPeriod.burstMonths.length ? <div className="max-h-56 overflow-y-auto divide-y divide-border">
                    <div className="flex justify-between py-1.5 text-xs text-muted-foreground"><span>月份</span><span>月度超额</span></div>
                    {selectedPeriod.burstMonths.map((month) => <div key={month.month} className="flex justify-between py-2 text-sm"><span>{month.month}</span><span className="font-mono text-warning">{percent(month.monthly_excess)}</span></div>)}
                  </div> : <p className="text-sm text-muted-foreground">无</p>}
                </div>
              </div>
            </section>

            <section>
              <h3 className="mb-3 text-sm font-medium">训练 / 验证对比</h3>
              <div className="overflow-hidden border-y border-border text-sm">
                <div className="grid grid-cols-5 px-2 py-2 text-xs text-muted-foreground"><span>区间</span><span>标签</span><span>分数</span><span>最佳单月</span><span>最差单月</span></div>
                <div className="grid grid-cols-5 border-t border-border px-2 py-2"><span>训练</span><span>{selected.training.label}</span><span>{number(selected.training.score)}</span><span>{percent(selected.training.metrics.best_month_excess)}</span><span>{percent(selected.training.metrics.worst_month_excess)}</span></div>
                {selected.validation && <div className="grid grid-cols-5 border-t border-border px-2 py-2"><span>验证</span><span>{selected.validation.label}</span><span>{number(selected.validation.score)}</span><span>{percent(selected.validation.metrics.best_month_excess)}</span><span>{percent(selected.validation.metrics.worst_month_excess)}</span></div>}
              </div>
            </section>

            <section>
              <h3 className="mb-2 text-sm font-medium">因子表达式</h3>
              <code className="block break-all border-y border-border py-3 text-xs">{selected.factorExpression}</code>
            </section>
          </div>
        </div>
      </div>}
    </div>
  );
};
