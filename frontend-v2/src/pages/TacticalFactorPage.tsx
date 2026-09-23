import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertCircle, ChevronDown, Flame, Loader2, RefreshCw, RotateCcw, Save, Search, Settings2, ShieldCheck, X, Zap } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { analyzeTacticalFactors, getSavedTacticalGroupTest, getTacticalConfig, listFactorLibraries, listTacticalGroupTests, testTacticalFactorGroup, updateTacticalConfig } from '@/services/api';
import type { TacticalAnalyzeResponse, TacticalConfig, TacticalFactorResult, TacticalGroupStrategyPeriod, TacticalGroupTestResponse, TacticalGroupTestSummary, TacticalLabel, TacticalPeriodResult, TacticalReturnCorrelationGroup } from '@/types';

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

const correlation = (value: unknown, digits = 3) => (
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--'
);

const groupKey = (factorIds: string[]) => factorIds.slice().sort().join('|');

const finiteNumber = (value: unknown): number | null => (
  typeof value === 'number' && Number.isFinite(value) ? value : null
);

const dateTime = (value?: string | null) => {
  if (!value) return '--';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
};

const sampleGroupsByCorrelation = (
  groups: TacticalReturnCorrelationGroup[],
  bucketCount: number,
  perBucket: number,
) => {
  const valid = groups
    .filter((group) => finiteNumber(group.averageCorrelation) !== null)
    .sort((left, right) => left.averageCorrelation - right.averageCorrelation);
  if (!valid.length) return [];
  const buckets = Math.max(1, Math.round(bucketCount));
  const take = Math.max(1, Math.round(perBucket));
  const min = valid[0].averageCorrelation;
  const max = valid[valid.length - 1].averageCorrelation;
  const width = max === min ? 1 : (max - min) / buckets;
  const selected = new Map<string, TacticalReturnCorrelationGroup>();

  for (let bucket = 0; bucket < buckets; bucket += 1) {
    const start = min + width * bucket;
    const end = bucket === buckets - 1 ? max + 1e-12 : min + width * (bucket + 1);
    const rows = valid.filter((group) => group.averageCorrelation >= start && group.averageCorrelation < end);
    if (!rows.length) continue;
    const step = rows.length <= take ? 1 : (rows.length - 1) / Math.max(1, take - 1);
    for (let index = 0; index < Math.min(take, rows.length); index += 1) {
      const row = rows[Math.round(index * step)];
      selected.set(groupKey(row.factorIds), row);
    }
  }
  return Array.from(selected.values()).sort((left, right) => right.averageCorrelation - left.averageCorrelation);
};

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
  percentDigits?: number;
  onChange: (value: number) => void;
}> = ({ label, value, min, max, step = 1, percentInput, percentDigits = 0, onChange }) => (
  <label className="grid gap-1.5">
    <span className="text-xs text-muted-foreground">{label}</span>
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={percentInput ? number(value * 100, percentDigits) : value}
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

const StrategyMonthlyCharts: React.FC<{ period: TacticalGroupStrategyPeriod }> = ({ period }) => {
  if (!period.monthly.length) return <div className="border-y border-border py-8 text-center text-sm text-muted-foreground">暂无组合月度数据</div>;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="border-y border-border py-4">
        <h4 className="mb-3 text-sm font-medium">组合月度超额</h4>
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={period.monthly}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} minTickGap={24} />
              <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(value) => percent(value, 1)} />
              <Tooltip contentStyle={chartTooltipStyle} labelStyle={chartLabelStyle} itemStyle={chartItemStyle} formatter={(value) => [percent(value, 1), '组合月度超额']} />
              <Bar dataKey="monthly_excess" radius={[3, 3, 0, 0]}>
                {period.monthly.map((row) => <Cell key={row.month} fill={row.monthly_excess >= 0 ? '#10b981' : '#ef4444'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="border-y border-border py-4">
        <h4 className="mb-3 text-sm font-medium">组合累计月度超额</h4>
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={period.monthly}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} minTickGap={24} />
              <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(value) => percent(value, 1)} />
              <Tooltip contentStyle={chartTooltipStyle} labelStyle={chartLabelStyle} itemStyle={chartItemStyle} formatter={(value) => [percent(value, 1), '组合累计月度超额']} />
              <Line type="monotone" dataKey="cumulative_excess" stroke="#2563eb" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

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

const GroupTestModal: React.FC<{
  result: TacticalGroupTestResponse;
  period: 'training' | 'validation';
  onPeriodChange: (period: 'training' | 'validation') => void;
  onClose: () => void;
}> = ({ result, period, onPeriodChange, onClose }) => {
  const selectedPeriod = result.strategy[period];
  const metrics = selectedPeriod.metrics;
  const deltas = selectedPeriod.comparison.deltas;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-md border border-border bg-background shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-start justify-between border-b border-border bg-background px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold">组合进一步测试</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              因子值相关度与五因子等权评分模型回测{result.saved ? ` · 已保存 ${dateTime(result.updatedAt || result.savedAt)}` : ''}
            </p>
          </div>
          <Button variant="ghost" onClick={onClose} title="关闭"><X className="h-4 w-4" /></Button>
        </div>
        <div className="space-y-6 p-5">
          <section className="grid gap-3 md:grid-cols-4">
            <Metric label="组合平均收益相关" value={correlation(result.groupMetrics?.averageCorrelation)} />
            <Metric label="因子值平均 Pearson" value={correlation(result.factorValueCorrelation.averagePearson)} />
            <Metric label="因子值平均 Spearman" value={correlation(result.factorValueCorrelation.averageSpearman)} />
            <Metric label="最低 Pearson" value={correlation(result.factorValueCorrelation.minPearson)} />
            <Metric label="两两组合数" value={result.factorValueCorrelation.pairCount} />
          </section>

          <section className="border-y border-border py-4">
            <h3 className="mb-3 text-sm font-medium">组合因子</h3>
            <div className="grid gap-2 md:grid-cols-2">
              {result.factorNames.map((name, index) => <div key={result.factorIds[index]} className="truncate text-sm" title={name}>{index + 1}. {name}</div>)}
            </div>
          </section>

          <section className="border-y border-border py-4">
            <h3 className="mb-3 text-sm font-medium">因子值两两相关</h3>
            <div className="max-h-60 overflow-y-auto divide-y divide-border">
              {result.factorValueCorrelation.pairs.map((pair) => (
                <div key={`${pair.factorId}-${pair.peerFactorId}`} className="grid gap-2 py-2 text-sm md:grid-cols-[minmax(0,1fr)_100px_100px_120px] md:items-center">
                  <div className="min-w-0">
                    <div className="truncate">{pair.factorName}</div>
                    <div className="truncate text-muted-foreground">vs {pair.peerFactorName}</div>
                  </div>
                  <div className="font-mono">P {correlation(pair.pearson)}</div>
                  <div className="font-mono">S {correlation(pair.spearman)}</div>
                  <div className="text-xs text-muted-foreground">{pair.overlapDays} 日 · 中位 {number(pair.medianStocks, 0)} 股</div>
                </div>
              ))}
            </div>
          </section>

          <section>
            <div className="mb-4 flex flex-wrap gap-1 rounded-md bg-secondary/60 p-1">
              <button onClick={() => onPeriodChange('training')} className={`rounded px-3 py-2 text-sm ${period === 'training' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'}`}>训练期</button>
              <button onClick={() => onPeriodChange('validation')} className={`rounded px-3 py-2 text-sm ${period === 'validation' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'}`}>验证期</button>
            </div>
            <div className="grid gap-4 md:grid-cols-4">
              <Metric label="组合累计超额" value={percent(metrics.total_excess)} />
              <Metric label="组合平均月超额" value={percent(metrics.mean_monthly_excess)} />
              <Metric label="组合最大月度回撤" value={percent(metrics.max_monthly_drawdown)} />
              <Metric label="组合超额 Sharpe" value={number(metrics.excess_sharpe)} />
            </div>
          </section>

          <StrategyMonthlyCharts period={selectedPeriod} />

          <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="overflow-x-auto border-y border-border">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 font-medium">成员因子</th>
                    <th className="px-2 py-2 font-medium">累计超额</th>
                    <th className="px-2 py-2 font-medium">平均月超额</th>
                    <th className="px-2 py-2 font-medium">最大月度回撤</th>
                    <th className="px-2 py-2 font-medium">月度波动</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {selectedPeriod.components.map((component) => (
                    <tr key={component.factorId}>
                      <td className="max-w-xs truncate px-2 py-2" title={component.factorName}>{component.factorName}</td>
                      <td className="px-2 py-2 font-mono">{percent(component.metrics.total_excess)}</td>
                      <td className="px-2 py-2 font-mono">{percent(component.metrics.mean_monthly_excess)}</td>
                      <td className="px-2 py-2 font-mono">{percent(component.metrics.max_monthly_drawdown)}</td>
                      <td className="px-2 py-2 font-mono">{percent(component.metrics.monthly_excess_std)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-y border-border py-4">
              <h3 className="mb-3 text-sm font-medium">组合相对成员平均</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span>累计超额</span><span className="font-mono">{percent(deltas.total_excess)}</span></div>
                <div className="flex justify-between"><span>平均月超额</span><span className="font-mono">{percent(deltas.mean_monthly_excess)}</span></div>
                <div className="flex justify-between"><span>月度波动</span><span className="font-mono">{percent(deltas.monthly_excess_std)}</span></div>
                <div className="flex justify-between"><span>最大月度回撤</span><span className="font-mono">{percent(deltas.max_monthly_drawdown)}</span></div>
                <div className="flex justify-between"><span>超额 Sharpe</span><span className="font-mono">{number(deltas.excess_sharpe)}</span></div>
              </div>
              <div className="mt-4 space-y-2">
                {selectedPeriod.comparison.summary.map((item) => <div key={item} className="border-l-2 border-border pl-3 text-sm">{item}</div>)}
              </div>
            </div>
          </section>

          <section className="border-y border-border py-4">
            <h3 className="mb-3 text-sm font-medium">回测口径与防未来</h3>
            <div className="grid gap-2 text-sm md:grid-cols-2">
              <div>{result.strategy.method.formula}</div>
              <div>{result.strategy.method.selection}</div>
              <div>训练期 {result.strategy.alignment.trainingPeriod.join(' ~ ')}</div>
              <div>验证期 {result.strategy.alignment.validationPeriod.join(' ~ ')}</div>
              <div>因子滞后 {result.strategy.alignment.factorLagTradingDays} 个交易日</div>
              <div>防未来检查：{result.strategy.alignment.factorBeforeEntry && result.strategy.alignment.entryBeforeExit ? '通过' : '异常'}</div>
            </div>
          </section>
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
  const [groupTest, setGroupTest] = useState<TacticalGroupTestResponse | null>(null);
  const [savedGroupTests, setSavedGroupTests] = useState<Record<string, TacticalGroupTestSummary>>({});
  const [detailPeriod, setDetailPeriod] = useState<'training' | 'validation'>('training');
  const [groupTestPeriod, setGroupTestPeriod] = useState<'training' | 'validation'>('training');
  const [testingGroupKey, setTestingGroupKey] = useState('');
  const [sampling, setSampling] = useState(false);
  const [samplingProgress, setSamplingProgress] = useState('');
  const [sampleBucketCount, setSampleBucketCount] = useState(5);
  const [samplePerBucket, setSamplePerBucket] = useState(1);
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

  const loadSavedGroupTests = useCallback(async (library: string) => {
    if (!library) {
      setSavedGroupTests({});
      return;
    }
    try {
      const response = await listTacticalGroupTests(library);
      const tests = response.data?.tests || [];
      setSavedGroupTests(Object.fromEntries(tests.map((item) => [groupKey(item.factorIds), item])));
    } catch {
      setSavedGroupTests({});
    }
  }, []);

  useEffect(() => {
    loadBase().catch(() => undefined);
  }, [loadBase]);

  useEffect(() => {
    loadSavedGroupTests(selectedLibrary).catch(() => undefined);
  }, [loadSavedGroupTests, selectedLibrary]);

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

  const runGroupTest = async (group: TacticalReturnCorrelationGroup) => {
    if (!selectedLibrary) return;
    const key = groupKey(group.factorIds);
    setTestingGroupKey(key);
    setError('');
    try {
      const response = await testTacticalFactorGroup(selectedLibrary, group.factorIds, {
        averageCorrelation: group.averageCorrelation,
        minPairCorrelation: group.minPairCorrelation,
        minOverlapDays: group.minOverlapDays,
      });
      if (response.data) {
        setGroupTest(response.data);
        setGroupTestPeriod('training');
        await loadSavedGroupTests(selectedLibrary);
      }
    } catch {
      setError('组合进一步测试失败，请确认这组因子都有 result.h5、评估产物和市场缓存。');
    } finally {
      setTestingGroupKey('');
    }
  };

  const sampleAndTestGroups = async () => {
    if (!selectedLibrary || !trainingReturnCorrelation?.groups?.length) return;
    const samples = sampleGroupsByCorrelation(trainingReturnCorrelation.groups, sampleBucketCount, samplePerBucket);
    if (!samples.length) {
      setError('当前没有可抽样的因子组合。');
      return;
    }
    setSampling(true);
    setError('');
    try {
      for (let index = 0; index < samples.length; index += 1) {
        const group = samples[index];
        const key = groupKey(group.factorIds);
        setTestingGroupKey(key);
        setSamplingProgress(`${index + 1}/${samples.length} · 平均相关 ${correlation(group.averageCorrelation)}`);
        await testTacticalFactorGroup(selectedLibrary, group.factorIds, {
          averageCorrelation: group.averageCorrelation,
          minPairCorrelation: group.minPairCorrelation,
          minOverlapDays: group.minOverlapDays,
        });
      }
      await loadSavedGroupTests(selectedLibrary);
    } catch {
      setError('相关度分桶抽样测试中断，请检查这组因子的 result.h5、评估产物和市场缓存。已完成的组合会保留在已保存列表里。');
      await loadSavedGroupTests(selectedLibrary);
    } finally {
      setTestingGroupKey('');
      setSampling(false);
      setSamplingProgress('');
    }
  };

  const viewSavedGroupTest = async (summary: TacticalGroupTestSummary) => {
    if (!selectedLibrary) return;
    const key = groupKey(summary.factorIds);
    setTestingGroupKey(key);
    setError('');
    try {
      const response = await getSavedTacticalGroupTest(selectedLibrary, summary.factorIds);
      if (response.data) {
        setGroupTest({
          ...response.data,
          groupMetrics: {
            ...(response.data.groupMetrics || {}),
            ...(summary.groupMetrics || {}),
            averageCorrelation: summary.averageCorrelation ?? summary.groupMetrics?.averageCorrelation ?? response.data.groupMetrics?.averageCorrelation,
            minPairCorrelation: summary.minPairCorrelation ?? summary.groupMetrics?.minPairCorrelation ?? response.data.groupMetrics?.minPairCorrelation,
            minOverlapDays: summary.minOverlapDays ?? summary.groupMetrics?.minOverlapDays ?? response.data.groupMetrics?.minOverlapDays,
          },
        });
        setGroupTestPeriod('training');
      }
    } catch {
      setError('读取已保存的组合测试失败，可能是保存文件已被移动或损坏。');
      await loadSavedGroupTests(selectedLibrary);
    } finally {
      setTestingGroupKey('');
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
  const trainingReturnCorrelation = summary?.returnCorrelation?.training;
  const selectedPeriod = selected && detailPeriod === 'validation' && selected.validation ? selected.validation : selected?.training;
  const groupMetricsByKey = Object.fromEntries((trainingReturnCorrelation?.groups || []).map((group) => [groupKey(group.factorIds), {
    averageCorrelation: group.averageCorrelation,
    minPairCorrelation: group.minPairCorrelation,
    minOverlapDays: group.minOverlapDays,
  }]));
  const savedGroupList = Object.values(savedGroupTests).map((item) => {
    const fallback = groupMetricsByKey[groupKey(item.factorIds)] || {};
    return {
      ...item,
      groupMetrics: { ...fallback, ...(item.groupMetrics || {}) },
      averageCorrelation: item.averageCorrelation ?? item.groupMetrics?.averageCorrelation ?? fallback.averageCorrelation,
      minPairCorrelation: item.minPairCorrelation ?? item.groupMetrics?.minPairCorrelation ?? fallback.minPairCorrelation,
      minOverlapDays: item.minOverlapDays ?? item.groupMetrics?.minOverlapDays ?? fallback.minOverlapDays,
    };
  });
  const savedComparisonData = savedGroupList
    .filter((item) => finiteNumber(item.averageCorrelation ?? item.groupMetrics?.averageCorrelation) !== null)
    .map((item, index) => ({
      key: item.key,
      name: item.factorNames.length ? item.factorNames.join(' / ') : `组合 ${index + 1}`,
      averageCorrelation: item.averageCorrelation ?? item.groupMetrics?.averageCorrelation,
      trainingTotalExcessDelta: item.trainingTotalExcessDelta,
      validationTotalExcessDelta: item.validationTotalExcessDelta,
      trainingMeanMonthlyExcessDelta: item.trainingMeanMonthlyExcessDelta,
      validationMeanMonthlyExcessDelta: item.validationMeanMonthlyExcessDelta,
    }))
    .sort((left, right) => Number(left.averageCorrelation) - Number(right.averageCorrelation));

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
            <ConfigNumber label="收益高相关阈值" value={draft.high_return_correlation_threshold} min={0} max={100} step={0.1} percentInput percentDigits={1} onChange={(value) => updateDraft('high_return_correlation_threshold', value)} />
            <ConfigNumber label="近似重复阈值" value={draft.duplicate_return_correlation_threshold} min={0} max={100} step={0.01} percentInput percentDigits={2} onChange={(value) => updateDraft('duplicate_return_correlation_threshold', value)} />
            <ConfigNumber label="相关最少重叠日" value={draft.min_return_correlation_overlap} min={2} max={5000} onChange={(value) => updateDraft('min_return_correlation_overlap', Math.round(value))} />
            <ConfigNumber label="组合因子数" value={draft.return_correlation_group_size} min={2} max={10} onChange={(value) => updateDraft('return_correlation_group_size', Math.round(value))} />
            <ConfigNumber label="组合平均相关阈值" value={draft.return_correlation_group_avg_threshold} min={0} max={100} step={0.1} percentInput percentDigits={1} onChange={(value) => updateDraft('return_correlation_group_avg_threshold', value)} />
            <ConfigNumber label="最多组合数" value={draft.max_return_correlation_groups} min={1} max={500} onChange={(value) => updateDraft('max_return_correlation_groups', Math.round(value))} />
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

      {summary && <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <SummaryTile label="已分析" value={summary.analyzed} />
        <SummaryTile label="战术进攻型" value={summary.labels['战术进攻型'] || 0} accent="text-warning" />
        <SummaryTile label="高风险爆发型" value={summary.labels['高风险爆发型'] || 0} accent="text-red-500" />
        <SummaryTile label="数据不足" value={summary.labels['数据不足'] || 0} />
        <SummaryTile label="高相关收益对" value={trainingReturnCorrelation?.highPairCount || 0} accent="text-blue-600" />
        <SummaryTile label="近似重复对" value={trainingReturnCorrelation?.duplicateLikePairCount || 0} accent="text-red-500" />
        <SummaryTile label="高相关组合" value={trainingReturnCorrelation?.groups?.length || 0} accent="text-blue-600" />
        <SummaryTile label="跳过" value={summary.skipped} />
      </div>}

      {savedGroupList.length > 0 && <Card className="glass">
        <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Save className="h-4 w-4" />已保存组合测试</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {savedComparisonData.length > 0 && <div className="border-y border-border py-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h4 className="text-sm font-medium">相关度与组合提升对比</h4>
              <span className="text-xs text-muted-foreground">横轴：组合平均收益相关度；纵轴：组合累计超额相对成员平均的提升</span>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 12, right: 18, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    type="number"
                    dataKey="averageCorrelation"
                    name="平均相关"
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={(value) => correlation(value, 2)}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="trainingTotalExcessDelta"
                    name="训练提升"
                    tickFormatter={(value) => percent(value, 1)}
                    tick={{ fontSize: 11 }}
                  />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    contentStyle={chartTooltipStyle}
                    labelStyle={chartLabelStyle}
                    itemStyle={chartItemStyle}
                    formatter={(value: unknown, name: unknown) => [
                      typeof value === 'number' ? percent(value, 2) : String(value ?? '--'),
                      String(name ?? ''),
                    ]}
                    labelFormatter={(_, payload) => {
                      const row = payload?.[0]?.payload;
                      return row ? `平均相关 ${correlation(row.averageCorrelation)} · ${row.name}` : '';
                    }}
                  />
                  <Scatter name="训练累计超额提升" data={savedComparisonData.filter((item) => finiteNumber(item.trainingTotalExcessDelta) !== null)} fill="#2563eb" />
                  <Scatter name="验证累计超额提升" data={savedComparisonData.filter((item) => finiteNumber(item.validationTotalExcessDelta) !== null).map((item) => ({ ...item, trainingTotalExcessDelta: item.validationTotalExcessDelta }))} fill="#f97316" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>}
          <div className="max-h-72 space-y-3 overflow-y-auto">
            {savedGroupList.map((item, index) => (
              <div key={item.key} className="grid gap-3 border-l-2 border-border pl-3 text-sm lg:grid-cols-[minmax(0,1fr)_320px_auto] lg:items-center">
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <Badge variant="outline">已保存 {index + 1}</Badge>
                    <span className="font-mono text-xs">平均相关 {correlation(item.averageCorrelation ?? item.groupMetrics?.averageCorrelation)}</span>
                    <span className="text-xs text-muted-foreground">更新于 {dateTime(item.updatedAt || item.savedAt)}</span>
                  </div>
                  <div className="truncate" title={item.factorNames.join(' / ')}>{item.factorNames.join(' / ')}</div>
                </div>
                <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                  <span>P {correlation(item.averagePearson)}</span>
                  <span>S {correlation(item.averageSpearman)}</span>
                  <span>训练 {percent(item.trainingTotalExcess)}</span>
                  <span>验证 {percent(item.validationTotalExcess)}</span>
                  <span>训练提升 {percent(item.trainingTotalExcessDelta)}</span>
                  <span>验证提升 {percent(item.validationTotalExcessDelta)}</span>
                </div>
                <Button variant="outline" onClick={() => viewSavedGroupTest(item)} disabled={Boolean(testingGroupKey)} title="查看已保存结果">
                  {testingGroupKey === groupKey(item.factorIds) ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Activity className="mr-2 h-4 w-4" />}
                  查看结果
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>}

      {trainingReturnCorrelation && (trainingReturnCorrelation.highPairCount > 0 || Boolean(trainingReturnCorrelation.groups?.length)) && <Card className="glass">
        <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Activity className="h-4 w-4" />收益相关度诊断</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 text-sm md:grid-cols-3">
            <Metric label="高相关阈值" value={correlation(trainingReturnCorrelation.threshold)} />
            <Metric label="近似重复阈值" value={correlation(trainingReturnCorrelation.duplicateThreshold, 4)} />
            <Metric label="最少重叠交易日" value={trainingReturnCorrelation.minOverlapDays} />
            <Metric label={`${trainingReturnCorrelation.groupSize} 因子组合`} value={`${trainingReturnCorrelation.groups?.length || 0} 组`} />
            <Metric label="组合平均相关阈值" value={correlation(trainingReturnCorrelation.groupAvgThreshold)} />
            <Metric label="正年化候选因子" value={trainingReturnCorrelation.groupEligibleFactorCount ?? 0} />
            <Metric label="非正年化已排除" value={trainingReturnCorrelation.groupExcludedNonPositiveAnnualizedCount ?? 0} />
          </div>
          {Boolean(trainingReturnCorrelation.groups?.length) && <div className="grid gap-3 border-y border-border py-4 lg:grid-cols-[1fr_160px_160px_auto] lg:items-end">
            <div>
              <h4 className="text-sm font-medium">按组合平均相关度抽样测试</h4>
              <p className="mt-1 text-xs text-muted-foreground">把当前组合按平均收益相关度从低到高分桶，每桶抽样后自动做进一步测试并保存。</p>
            </div>
            <ConfigNumber label="相关度分桶数" value={sampleBucketCount} min={1} max={20} onChange={(value) => setSampleBucketCount(Math.round(value))} />
            <ConfigNumber label="每桶抽样组数" value={samplePerBucket} min={1} max={20} onChange={(value) => setSamplePerBucket(Math.round(value))} />
            <Button variant="outline" onClick={sampleAndTestGroups} disabled={sampling || Boolean(testingGroupKey)} title="按相关度分桶抽样并测试">
              {sampling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Activity className="mr-2 h-4 w-4" />}
              {sampling ? samplingProgress || '抽样测试中' : '抽样并测试'}
            </Button>
          </div>}
          <div className="max-h-64 overflow-y-auto divide-y divide-border border-y border-border">
            {trainingReturnCorrelation.pairs.length ? trainingReturnCorrelation.pairs.map((pair) => (
              <div key={`${pair.factorId}-${pair.peerFactorId}`} className="grid gap-2 px-2 py-3 text-sm md:grid-cols-[minmax(0,1fr)_120px_110px] md:items-center">
                <div className="min-w-0">
                  <div className="truncate font-medium">{pair.factorName}</div>
                  <div className="truncate text-muted-foreground">vs {pair.peerFactorName}</div>
                </div>
                <div className="font-mono">相关 {correlation(pair.correlation)}</div>
                <Badge variant={pair.duplicateLike ? 'destructive' : 'outline'}>{pair.duplicateLike ? '近似重复' : `${pair.overlapDays} 日重叠`}</Badge>
              </div>
            )) : <div className="px-2 py-6 text-sm text-muted-foreground">没有达到两两高相关阈值的因子对</div>}
          </div>
          <div className="border-y border-border py-3">
            <h4 className="mb-3 text-sm font-medium">高相关因子组合</h4>
            {trainingReturnCorrelation.groups?.length ? (
              <div className="space-y-3">
                {trainingReturnCorrelation.groups.map((group, index) => {
                  const saved = savedGroupTests[groupKey(group.factorIds)];
                  const isTesting = testingGroupKey === groupKey(group.factorIds);
                  return (
                  <div key={group.factorIds.join('-')} className="border-l-2 border-border pl-3">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">组合 {index + 1}</Badge>
                        {saved && <Badge variant="success">已保存</Badge>}
                        <span className="font-mono text-sm">平均相关 {correlation(group.averageCorrelation)}</span>
                        <span className="text-xs text-muted-foreground">最低两两相关 {correlation(group.minPairCorrelation)} · 最少重叠 {group.minOverlapDays ?? '--'} 日 · 成员单因子年化超额均为正</span>
                        {saved && <span className="text-xs text-muted-foreground">更新于 {dateTime(saved.updatedAt || saved.savedAt)}</span>}
                      </div>
                      <Button variant="outline" onClick={() => saved ? viewSavedGroupTest(saved) : runGroupTest(group)} disabled={Boolean(testingGroupKey)} title={saved ? '查看已保存结果' : '进一步测试这个组合'}>
                        {isTesting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Activity className="mr-2 h-4 w-4" />}
                        {saved ? '查看结果' : '测试组合'}
                      </Button>
                    </div>
                    <div className="grid gap-1 text-sm md:grid-cols-2">
                      {group.factorNames.map((name, factorIndex) => (
                        <div key={`${group.factorIds[factorIndex]}-${factorIndex}`} className="truncate" title={name}>{factorIndex + 1}. {name}</div>
                      ))}
                    </div>
                  </div>
                )})}
              </div>
            ) : <p className="text-sm text-muted-foreground">没有找到满足平均相关阈值的因子组合</p>}
          </div>
        </CardContent>
      </Card>}

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
        <table className="w-full min-w-[1240px] text-left text-sm">
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
              <th className="px-3 py-3 font-medium">收益相关</th>
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
                <td className="px-3 py-3">
                  {factor.training.returnCorrelation?.maxCorrelation ? (
                    <div className="max-w-[160px]">
                      <div className="font-mono">{correlation(factor.training.returnCorrelation.maxCorrelation)}</div>
                      <div className="truncate text-xs text-muted-foreground" title={factor.training.returnCorrelation.maxPeerFactorName || ''}>
                        {factor.training.returnCorrelation.duplicateLikeCount ? '近似重复：' : '相似：'}{factor.training.returnCorrelation.maxPeerFactorName}
                      </div>
                    </div>
                  ) : <span className="text-xs text-muted-foreground">--</span>}
                </td>
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
              <Metric label="最高收益相关" value={correlation(selectedPeriod.returnCorrelation?.maxCorrelation)} />
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
                <div className="border-y border-border py-4">
                  <h4 className="mb-3 text-sm font-medium">收益相关因子</h4>
                  {selectedPeriod.returnCorrelation?.peers.length ? <div className="max-h-56 overflow-y-auto divide-y divide-border">
                    {selectedPeriod.returnCorrelation.peers.map((peer) => (
                      <div key={peer.factorId} className="py-2 text-sm">
                        <div className="flex items-start justify-between gap-3">
                          <span className="min-w-0 truncate" title={peer.factorName}>{peer.factorName}</span>
                          <span className="font-mono">{correlation(peer.correlation)}</span>
                        </div>
                        <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                          <span>{peer.overlapDays} 个重叠交易日</span>
                          {peer.duplicateLike && <Badge variant="destructive">近似重复</Badge>}
                        </div>
                      </div>
                    ))}
                  </div> : <p className="text-sm text-muted-foreground">未发现高相关收益路径</p>}
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

      {groupTest && <GroupTestModal result={groupTest} period={groupTestPeriod} onPeriodChange={setGroupTestPeriod} onClose={() => setGroupTest(null)} />}
    </div>
  );
};
