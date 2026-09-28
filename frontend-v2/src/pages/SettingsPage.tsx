import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Settings, Save, RotateCcw, Eye, EyeOff, Check, X, AlertCircle, Loader2, Database, Sliders, Box, Cpu, Compass, Shuffle, Bot, BarChart3 } from 'lucide-react';
import { getSystemConfig, getProviderModels, updateSystemConfig, healthCheck, getEvaluationConfig, updateEvaluationConfig, getDailyFeatures } from '@/services/api';
import type { DailyFeatureMetadata, EvaluationConfig, LlmModuleRoute, PromptPackOption } from '@/services/api';
import { REFERENCE_MINING_DIRECTIONS, getDirectionLabel, type MiningDirectionItem } from '@/utils/miningDirections';
import type { PromptPack } from '@/types';

interface SystemConfig {
  // LLM
  apiKey: string;
  apiUrl: string;
  modelName: string;
  // Qlib
  qlibDataPath: string;
  resultsDir: string;
  // Parameters
  defaultNumDirections: number;
  defaultMaxRounds: number;
  defaultMaxLoops: number;
  defaultFactorsPerHypothesis: number;
  defaultMarket: 'csi300' | 'csi500' | 'sp500';
  // Advanced
  parallelExecution: boolean;
  qualityGateEnabled: boolean;
  backtestTimeout: number;
  defaultLibrarySuffix: string;
  promptPack: PromptPack;
  llmModuleRoutes: LlmModuleRoute[];
  // Mining direction: use selected directions / random
  miningDirectionMode: 'selected' | 'random';
  selectedMiningDirectionIndices: number[];
}

const DEFAULT_LLM_MODULE_ROUTES: LlmModuleRoute[] = [
  {
    tag: 'AlphaAgentHypothesis2FactorExpression',
    label: '因子表达式生成',
    description: '把研究假设转成因子描述、公式和 DSL 表达式。',
    modelName: 'gpt-5.5',
    apiUrl: 'https://www.yihean.net:3443/v1',
    apiKey: '',
  },
  {
    tag: 'FactorCodeEvaluator',
    label: '因子代码评价器',
    description: '检查因子表达式/代码实现是否和定义一致。',
    modelName: 'gpt-5.5',
    apiUrl: 'https://www.yihean.net:3443/v1',
    apiKey: '',
  },
];

const DEFAULT_CONFIG: SystemConfig = {
  apiKey: '',
  apiUrl: 'https://api.deepseek.com',
  modelName: '',
  qlibDataPath: '/Users/wangjiayi/Downloads/QuantaAlpha/data/qlib/cn_data',
  resultsDir: '/Users/wangjiayi/Downloads/QuantaAlpha/data/results',
  defaultNumDirections: 1,
  defaultMaxRounds: 1,
  defaultMaxLoops: 1,
  defaultFactorsPerHypothesis: 3,
  defaultMarket: 'csi300',
  parallelExecution: false,
  qualityGateEnabled: false,
  backtestTimeout: 600,
  defaultLibrarySuffix: '',
  promptPack: 'zh_quant_v1',
  llmModuleRoutes: DEFAULT_LLM_MODULE_ROUTES,
  miningDirectionMode: 'selected',
  selectedMiningDirectionIndices: [0],
};

const parseNumberField = (value: string, fallback: number) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
};

type SettingsTab = 'api' | 'data' | 'features' | 'params' | 'evaluation' | 'directions';

const DEFAULT_EVALUATION_CONFIG: EvaluationConfig = {
  trainingStart: '2023-01-01', trainingEnd: '2025-06-30', validationStart: '2025-07-01', validationEnd: '2025-12-31',
  icThreshold: 0.03, icirThreshold: 0.5, spreadThreshold: 0.30, excessSharpeThreshold: 1.0,
  groupCount: 10, rebalancePeriodDays: 3, feeThrough2023: 0.0007, feeFrom2024: 0.00035, oosStatus: 'sealed', engine: 'oto_single_factor_v1',
};

const CUSTOM_MODEL_VALUE = '__custom_model__';

export const SettingsPage: React.FC = () => {
  const [config, setConfig] = useState<SystemConfig>(DEFAULT_CONFIG);
  const [evaluationConfig, setEvaluationConfig] = useState<EvaluationConfig>(DEFAULT_EVALUATION_CONFIG);
  const [activeTab, setActiveTab] = useState<SettingsTab>('api');
  const [showApiKey, setShowApiKey] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [factorLibraries, setFactorLibraries] = useState<string[]>([]);
  const [promptPacks, setPromptPacks] = useState<PromptPackOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dailyFeatures, setDailyFeatures] = useState<DailyFeatureMetadata | null>(null);
  const [dailyFeaturesLoading, setDailyFeaturesLoading] = useState(false);
  const [dailyFeaturesError, setDailyFeaturesError] = useState<string | null>(null);
  const [featureSearch, setFeatureSearch] = useState('');

  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelsUpdatedAt, setModelsUpdatedAt] = useState<string | null>(null);
  const [modelsRefresh, setModelsRefresh] = useState(0);

  useEffect(() => {
    if (isLoading) return;
    const controller = new AbortController();
    setModels([]);
    setModelsError(null);
    setModelsUpdatedAt(null);
    setModelsLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const key = config.apiKey.trim();
        const response = await getProviderModels(
          config.apiUrl,
          key && !key.includes('...') && key !== '***' ? key : undefined,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (!response.success || !response.data) throw new Error(response.message || '获取模型列表失败');
        setModels(response.data.models);
        setModelsUpdatedAt(response.data.fetchedAt);
      } catch (err: unknown) {
        if (!controller.signal.aborted) setModelsError(err instanceof Error ? err.message : '获取模型列表失败');
      } finally {
        if (!controller.signal.aborted) setModelsLoading(false);
      }
    }, 600);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [isLoading, config.apiUrl, config.apiKey, modelsRefresh]);

  // Load config from backend on mount
  useEffect(() => {
    loadConfig();
  }, []);

  useEffect(() => {
    if (activeTab === 'features' && !dailyFeatures && !dailyFeaturesLoading) {
      loadDailyFeatures();
    }
  }, [activeTab, dailyFeatures, dailyFeaturesLoading]);

  const loadConfig = async () => {
    setIsLoading(true);
    setError(null);

    // Check backend health
    try {
      await healthCheck();
      setBackendStatus('online');
    } catch {
      setBackendStatus('offline');
    }

    // Load config
    try {
      const resp = await getSystemConfig();
      if (resp.success && resp.data) {
        const env = resp.data.env || {};
        const saved = localStorage.getItem('quantaalpha_config');
        let miningDirectionMode = DEFAULT_CONFIG.miningDirectionMode;
        let selectedMiningDirectionIndices = DEFAULT_CONFIG.selectedMiningDirectionIndices;
        if (saved) {
          try {
            const parsed = JSON.parse(saved);
            if (parsed.miningDirectionMode) miningDirectionMode = parsed.miningDirectionMode;
            if (Array.isArray(parsed.selectedMiningDirectionIndices)) selectedMiningDirectionIndices = parsed.selectedMiningDirectionIndices;
          } catch { /* use defaults */ }
        }
        const experimentConfig = resp.data.experimentConfig || {};
        setConfig({
          apiKey: env.OPENAI_API_KEY || '',
          apiUrl: env.OPENAI_BASE_URL || DEFAULT_CONFIG.apiUrl,
          modelName: env.CHAT_MODEL || DEFAULT_CONFIG.modelName,
          qlibDataPath: env.QLIB_DATA_DIR || '',
          resultsDir: env.DATA_RESULTS_DIR || '',
          defaultNumDirections: experimentConfig.defaultNumDirections ?? DEFAULT_CONFIG.defaultNumDirections,
          defaultMaxRounds: experimentConfig.defaultMaxRounds ?? DEFAULT_CONFIG.defaultMaxRounds,
          defaultMaxLoops: experimentConfig.defaultMaxLoops ?? DEFAULT_CONFIG.defaultMaxLoops,
          defaultFactorsPerHypothesis: experimentConfig.defaultFactorsPerHypothesis ?? DEFAULT_CONFIG.defaultFactorsPerHypothesis,
          defaultMarket: experimentConfig.defaultMarket ?? DEFAULT_CONFIG.defaultMarket,
          parallelExecution: experimentConfig.parallelExecution ?? DEFAULT_CONFIG.parallelExecution,
          qualityGateEnabled: experimentConfig.qualityGateEnabled ?? DEFAULT_CONFIG.qualityGateEnabled,
          backtestTimeout: experimentConfig.backtestTimeout ?? DEFAULT_CONFIG.backtestTimeout,
          defaultLibrarySuffix: experimentConfig.defaultLibrarySuffix ?? DEFAULT_CONFIG.defaultLibrarySuffix,
          promptPack: experimentConfig.promptPack ?? DEFAULT_CONFIG.promptPack,
          llmModuleRoutes: resp.data.llmModuleRoutes?.length ? resp.data.llmModuleRoutes : DEFAULT_CONFIG.llmModuleRoutes,
          miningDirectionMode,
          selectedMiningDirectionIndices,
        });
        setPromptPacks(resp.data.promptPacks || []);
        setFactorLibraries(resp.data.factorLibraries || []);
      }
      const evaluationResponse = await getEvaluationConfig();
      if (evaluationResponse.data?.config) setEvaluationConfig(evaluationResponse.data.config);
    } catch (err: any) {
      console.error('Failed to load config:', err);
      // Fallback to localStorage
      const saved = localStorage.getItem('quantaalpha_config');
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          setConfig({
            ...DEFAULT_CONFIG,
            ...parsed,
            selectedMiningDirectionIndices: Array.isArray(parsed.selectedMiningDirectionIndices)
              ? parsed.selectedMiningDirectionIndices
              : DEFAULT_CONFIG.selectedMiningDirectionIndices,
          });
        } catch {
          // use defaults
        }
      }
      setError('无法从后端加载配置，显示的是本地缓存配置');
    } finally {
      setIsLoading(false);
    }
  };

  const loadDailyFeatures = async () => {
    setDailyFeaturesLoading(true);
    setDailyFeaturesError(null);
    try {
      const response = await getDailyFeatures();
      if (!response.success || !response.data) throw new Error(response.message || '读取特征数据失败');
      setDailyFeatures(response.data);
    } catch (err: unknown) {
      setDailyFeaturesError(err instanceof Error ? err.message : '读取特征数据失败');
    } finally {
      setDailyFeaturesLoading(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);

    // Always save to localStorage as backup
    localStorage.setItem('quantaalpha_config', JSON.stringify(config));

    // Try to save to backend
    try {
      const update: Record<string, unknown> = {};
      if (config.apiKey && !config.apiKey.includes('...')) {
        update.OPENAI_API_KEY = config.apiKey;
      }
      if (config.apiUrl) update.OPENAI_BASE_URL = config.apiUrl;
      if (config.modelName) {
        update.CHAT_MODEL = config.modelName;
        update.REASONING_MODEL = config.modelName;
      }
      if (config.qlibDataPath) update.QLIB_DATA_DIR = config.qlibDataPath;
      if (config.resultsDir) update.DATA_RESULTS_DIR = config.resultsDir;
      update.DEFAULT_LIBRARY_SUFFIX = config.defaultLibrarySuffix;
      update.defaultNumDirections = config.defaultNumDirections;
      update.defaultMaxRounds = config.defaultMaxRounds;
      update.defaultMaxLoops = config.defaultMaxLoops;
      update.defaultFactorsPerHypothesis = config.defaultFactorsPerHypothesis;
      update.defaultMarket = config.defaultMarket;
      update.parallelExecution = config.parallelExecution;
      update.qualityGateEnabled = config.qualityGateEnabled;
      update.backtestTimeout = config.backtestTimeout;
      update.promptPack = config.promptPack;
      update.llmModuleRoutes = config.llmModuleRoutes;

      if (Object.keys(update).length > 0) {
        await updateSystemConfig(update);
      }
      await updateEvaluationConfig(evaluationConfig);
    } catch (err: any) {
      console.warn('Failed to save to backend, saved locally:', err);
    }

    setIsSaved(true);
    setIsDirty(false);
    setIsSaving(false);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const handleReset = () => {
    if (confirm('确定要重置为默认配置吗？')) {
      loadConfig();
      setIsDirty(false);
    }
  };

  const updateConfigField = (key: keyof SystemConfig, value: any) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    setIsDirty(true);
  };

  const updateModuleRouteField = (tag: string, key: keyof LlmModuleRoute, value: string) => {
    setConfig((prev) => ({
      ...prev,
      llmModuleRoutes: prev.llmModuleRoutes.map((route) => (
        route.tag === tag ? { ...route, [key]: value } : route
      )),
    }));
    setIsDirty(true);
  };

  const updateEvaluationField = <K extends keyof EvaluationConfig>(key: K, value: EvaluationConfig[K]) => {
    setEvaluationConfig((previous) => ({ ...previous, [key]: value }));
    setIsDirty(true);
  };

  const isCustomModel = !models.includes(config.modelName);
  const filteredDailyFeatures = useMemo(() => {
    const keyword = featureSearch.trim().toLowerCase();
    const features = dailyFeatures?.features || [];
    if (!keyword) return features;
    return features.filter((feature) => (
      feature.name.toLowerCase().includes(keyword)
      || feature.category.toLowerCase().includes(keyword)
      || feature.description.toLowerCase().includes(keyword)
    ));
  }, [dailyFeatures, featureSearch]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <span className="ml-3 text-muted-foreground">加载配置中...</span>
      </div>
    );
  }

  const TabButton = ({ id, label, icon: Icon }: { id: SettingsTab; label: string; icon: any }) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
        activeTab === id
          ? 'bg-primary text-primary-foreground shadow-lg scale-105'
          : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
      }`}
    >
      <Icon className="h-4 w-4" />
      <span className="font-medium">{label}</span>
    </button>
  );

  return (
    <div className="space-y-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Settings className="h-8 w-8 text-primary" />
            系统配置
          </h1>
          <p className="text-muted-foreground mt-1">
            管理 API 连接、数据源及实验参数
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={handleReset}>
            <RotateCcw className="h-4 w-4 mr-2" />
            重置
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={!isDirty || isSaving}>
            {isSaving ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            保存配置
          </Button>
        </div>
      </div>

      {/* Status Banners */}
      {isSaved && (
        <div className="glass rounded-lg p-4 flex items-center gap-3 bg-success/10 border-success/50 animate-fade-in-down">
          <Check className="h-5 w-5 text-success" />
          <span className="text-success">配置已保存</span>
        </div>
      )}
      {isDirty && !isSaved && (
        <div className="glass rounded-lg p-4 flex items-center gap-3 bg-warning/10 border-warning/50 animate-fade-in-down">
          <X className="h-5 w-5 text-warning" />
          <span className="text-warning">有未保存的更改</span>
        </div>
      )}
      {error && (
        <div className="glass rounded-lg p-4 flex items-center gap-3 bg-warning/10 border-warning/50">
          <AlertCircle className="h-5 w-5 text-warning flex-shrink-0" />
          <span className="text-sm text-warning">{error}</span>
        </div>
      )}

      {/* Tabs Navigation */}
      <div className="flex gap-2 p-1 bg-secondary/20 rounded-xl w-fit flex-wrap">
        <TabButton id="api" label="配置 API" icon={Cpu} />
        <TabButton id="data" label="数据路径" icon={Database} />
        <TabButton id="features" label="特征数据" icon={BarChart3} />
        <TabButton id="params" label="默认参数" icon={Sliders} />
        <TabButton id="evaluation" label="评估规则" icon={BarChart3} />
        <TabButton id="directions" label="挖掘方向" icon={Compass} />
      </div>

      {/* Tab Content */}
      <div className="grid grid-cols-1 gap-6">
        
        {/* API Configuration Tab */}
        {activeTab === 'api' && (
          <Card className="glass card-hover animate-fade-in-up">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                🤖 LLM 模型配置
                <Badge variant="default">核心</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <label className="block text-sm font-medium mb-2">
                  API Key <span className="text-destructive">*</span>
                </label>
                <div className="flex gap-2">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={config.apiKey}
                    onChange={(e) => updateConfigField('apiKey', e.target.value)}
                    placeholder="sk-..."
                    className="flex-1 rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                  <Button
                    variant="outline"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="px-3"
                  >
                    {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  支持 OpenAI 兼容格式的 API Key（如 DashScope, DeepSeek 等）
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">API Base URL</label>
                <input
                  type="text"
                  value={config.apiUrl}
                  onChange={(e) => updateConfigField('apiUrl', e.target.value)}
                  placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
                  className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  LLM 服务端点地址
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">模型名称</label>
                <select
                  value={isCustomModel ? CUSTOM_MODEL_VALUE : config.modelName}
                  onChange={(e) => {
                    if (e.target.value === CUSTOM_MODEL_VALUE) {
                      updateConfigField('modelName', '');
                      return;
                    }
                    updateConfigField('modelName', e.target.value);
                  }}
                  className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                >
                  {models.map((model) => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                  <option value={CUSTOM_MODEL_VALUE}>自定义模型 ID</option>
                </select>
                {isCustomModel && (
                  <input
                    type="text"
                    value={config.modelName}
                    onChange={(e) => updateConfigField('modelName', e.target.value.trim())}
                    placeholder="输入模型 ID，例如 deepseek-flash"
                    className="mt-3 w-full rounded-lg border border-input bg-background px-4 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                )}
                <div className="flex items-center gap-3 mt-3">
                  <Button type="button" variant="outline" disabled={modelsLoading}
                    onClick={() => setModelsRefresh((value) => value + 1)}>
                    {modelsLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RotateCcw className="h-4 w-4 mr-2" />}
                    {modelsLoading ? '获取模型中…' : '刷新模型列表'}
                  </Button>
                  {modelsUpdatedAt && <span className="text-xs text-muted-foreground">
                    {models.length} 个模型 · {new Date(modelsUpdatedAt).toLocaleTimeString()} 更新
                  </span>}
                </div>
                {modelsError && <p role="alert" className="text-xs text-destructive mt-2">{modelsError}</p>}
                <p className="text-xs text-muted-foreground mt-2">
                  从当前 API 服务实时获取。已配置的模型会保留，也可手动输入模型 ID。
                  列表反映服务返回的模型，具体调用权限及对话能力以服务商为准。
                </p>
                <datalist id="llm-model-options">
                  {models.map((model) => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
              </div>

              <div className="border-t border-border/50 pt-5">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <div>
                    <h3 className="text-sm font-semibold">模块单独模型配置</h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      仅影响指定 LLM 节点；留空时继承上方全局模型/API 配置。
                    </p>
                  </div>
                  <Badge variant="outline">QA_CHAT_*_MAP</Badge>
                </div>
                <div className="space-y-4">
                  {config.llmModuleRoutes.map((route) => (
                    <div key={route.tag} className="rounded-lg border border-border/60 bg-background/60 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-medium">{route.label}</div>
                          <div className="mt-1 text-xs font-mono text-muted-foreground">{route.tag}</div>
                          <p className="mt-2 text-xs text-muted-foreground">{route.description}</p>
                        </div>
                        {route.modelName && <Badge variant="default">{route.modelName}</Badge>}
                      </div>
                      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          <label className="block text-xs font-medium mb-2">模块模型</label>
                          <input
                            type="text"
                            list="llm-model-options"
                            value={route.modelName}
                            onChange={(e) => updateModuleRouteField(route.tag, 'modelName', e.target.value.trim())}
                            placeholder={config.modelName || '继承全局模型'}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium mb-2">模块 API Base URL</label>
                          <input
                            type="text"
                            value={route.apiUrl}
                            onChange={(e) => updateModuleRouteField(route.tag, 'apiUrl', e.target.value)}
                            placeholder={config.apiUrl || '继承全局 API URL'}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium mb-2">模块 API Key</label>
                          <input
                            type={showApiKey ? 'text' : 'password'}
                            value={route.apiKey}
                            onChange={(e) => updateModuleRouteField(route.tag, 'apiKey', e.target.value)}
                            placeholder={route.hasApiKey ? '已配置，留空则清除模块 Key' : '继承全局 API Key'}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-3">提示词模式</label>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {(promptPacks.length ? promptPacks : [
                    { name: 'zh_quant_v1', label: '中文优化版', version: '2026-08-20', outputLanguage: 'zh-CN', strictJson: true, description: '', planningPromptFile: '', factorPromptFile: '' },
                    { name: 'en_default', label: '英文原版', version: 'pre-zh-prompt-optimization', outputLanguage: 'en', strictJson: false, description: '', planningPromptFile: '', factorPromptFile: '' },
                  ]).map((pack) => {
                    const selected = config.promptPack === pack.name;
                    return (
                      <button
                        key={pack.name}
                        type="button"
                        onClick={() => updateConfigField('promptPack', pack.name)}
                        className={`group rounded-xl border p-4 text-left transition-all ${
                          selected
                            ? 'border-primary/50 bg-primary/10 text-primary shadow-sm'
                            : 'border-border/60 bg-background/60 text-foreground hover:-translate-y-0.5 hover:border-primary/30 hover:bg-secondary/30 hover:shadow-md'
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <div
                            className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg ${
                              selected ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'
                            }`}
                          >
                            {selected ? <Check className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <div className="truncate font-semibold">{pack.label || pack.name}</div>
                              {pack.outputLanguage && (
                                <span className="rounded-md bg-background/80 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                                  {pack.outputLanguage}
                                </span>
                              )}
                            </div>
                            <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
                              {pack.name}
                              {pack.version ? ` · ${pack.version}` : ''}
                            </div>
                            {pack.description && (
                              <div className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                                {pack.description}
                              </div>
                            )}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Connection Status */}
              <div className="pt-4 border-t border-border/50">
                <div className="flex items-center gap-3">
                  <div
                    className={`h-3 w-3 rounded-full ${
                      backendStatus === 'online'
                        ? 'bg-success animate-pulse'
                        : backendStatus === 'offline'
                        ? 'bg-destructive'
                        : 'bg-warning animate-pulse'
                    }`}
                  />
                  <span className="text-sm">
                    后端连接状态：
                    {backendStatus === 'online' ? <span className="text-success font-medium">已连接</span> : 
                     backendStatus === 'offline' ? <span className="text-destructive font-medium">未连接</span> : 
                     '检测中...'}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Data Path Configuration Tab */}
        {activeTab === 'data' && (
          <Card className="glass card-hover animate-fade-in-up">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                📊 数据存储路径
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Qlib 数据目录 <span className="text-destructive">*</span>
                </label>
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={config.qlibDataPath}
                    onChange={(e) => updateConfigField('qlibDataPath', e.target.value)}
                    placeholder="/path/to/qlib/cn_data"
                    className="flex-1 rounded-lg border border-input bg-background px-4 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1 ml-6">
                  需包含 calendars/, features/, instruments/ 等 Qlib 标准数据子目录
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  实验结果输出目录
                </label>
                <div className="flex items-center gap-2">
                  <Box className="h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={config.resultsDir}
                    onChange={(e) => updateConfigField('resultsDir', e.target.value)}
                    placeholder="/path/to/results"
                    className="flex-1 rounded-lg border border-input bg-background px-4 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1 ml-6">
                  用于存放挖掘出的因子、回测报告及日志文件
                </p>
              </div>

              {factorLibraries.length > 0 && (
                <div className="bg-secondary/20 rounded-lg p-4 mt-4">
                  <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                    <Check className="h-4 w-4 text-success" />
                    已识别的因子库
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {factorLibraries.map((lib, idx) => (
                      <Badge key={idx} variant="outline" className="bg-background/50">
                        {lib}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Daily Feature Metadata Tab */}
        {activeTab === 'features' && (
          <Card className="glass card-hover animate-fade-in-up">
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Database className="h-5 w-5 text-primary" />
                    当前特征数据
                  </CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    从 daily_pv.h5 实时读取列名和数据概览；文件更新后刷新即可同步。
                  </p>
                </div>
                <Button variant="outline" onClick={loadDailyFeatures} disabled={dailyFeaturesLoading}>
                  {dailyFeaturesLoading ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <RotateCcw className="h-4 w-4 mr-2" />
                  )}
                  刷新
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              {dailyFeaturesLoading && !dailyFeatures && (
                <div className="flex items-center justify-center rounded-lg border border-border/60 bg-secondary/10 py-10 text-muted-foreground">
                  <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                  正在读取 daily_pv.h5 元数据...
                </div>
              )}

              {dailyFeaturesError && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
                  {dailyFeaturesError}
                </div>
              )}

              {dailyFeatures && !dailyFeatures.exists && (
                <div className="rounded-lg border border-warning/30 bg-warning/10 p-4">
                  <div className="font-medium text-warning">未找到 daily_pv.h5</div>
                  <div className="mt-2 break-all font-mono text-xs text-muted-foreground">{dailyFeatures.path}</div>
                </div>
              )}

              {dailyFeatures?.exists && (
                <>
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                      <div className="text-xs text-muted-foreground">特征列数</div>
                      <div className="mt-1 text-2xl font-semibold">{dailyFeatures.featureCount}</div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                      <div className="text-xs text-muted-foreground">样本行数</div>
                      <div className="mt-1 text-2xl font-semibold">{dailyFeatures.rowCount?.toLocaleString()}</div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                      <div className="text-xs text-muted-foreground">股票数</div>
                      <div className="mt-1 text-2xl font-semibold">{dailyFeatures.instrumentCount?.toLocaleString()}</div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                      <div className="text-xs text-muted-foreground">文件大小</div>
                      <div className="mt-1 text-2xl font-semibold">{dailyFeatures.sizeText}</div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border/60 bg-secondary/10 p-4">
                    <div className="grid gap-3 text-sm md:grid-cols-2">
                      <div>
                        <span className="text-muted-foreground">时间范围：</span>
                        <span className="font-medium">{dailyFeatures.dateMin} 至 {dailyFeatures.dateMax}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">更新时间：</span>
                        <span className="font-medium">
                          {dailyFeatures.modifiedAt ? new Date(dailyFeatures.modifiedAt).toLocaleString() : '--'}
                        </span>
                      </div>
                      <div className="md:col-span-2">
                        <span className="text-muted-foreground">文件路径：</span>
                        <span className="break-all font-mono text-xs">{dailyFeatures.path}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {Object.entries(dailyFeatures.categories || {}).map(([category, count]) => (
                      <Badge key={category} variant="outline" className="bg-background/60">
                        {category} · {count}
                      </Badge>
                    ))}
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold">特征列表</h3>
                      <p className="mt-1 text-xs text-muted-foreground">
                        当前显示 {filteredDailyFeatures.length} / {dailyFeatures.features.length} 个字段。
                      </p>
                    </div>
                    <input
                      type="search"
                      value={featureSearch}
                      onChange={(event) => setFeatureSearch(event.target.value)}
                      placeholder="搜索变量名、分类或说明"
                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary sm:w-72"
                    />
                  </div>

                  <div className="max-h-[460px] overflow-auto rounded-lg border border-border/60">
                    <table className="w-full min-w-[760px] text-left text-sm">
                      <thead className="sticky top-0 z-10 bg-background/95 text-xs text-muted-foreground backdrop-blur">
                        <tr>
                          <th className="px-4 py-3 font-medium">变量名</th>
                          <th className="px-4 py-3 font-medium">分类</th>
                          <th className="px-4 py-3 font-medium">含义</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/60">
                        {filteredDailyFeatures.map((feature) => (
                          <tr key={feature.name} className="hover:bg-secondary/20">
                            <td className="whitespace-nowrap px-4 py-3 font-mono font-semibold text-primary">{feature.name}</td>
                            <td className="whitespace-nowrap px-4 py-3">
                              <Badge variant="outline">{feature.category}</Badge>
                            </td>
                            <td className="px-4 py-3 text-muted-foreground">
                              {feature.description || '暂无说明'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* Default Parameters Tab */}
        {activeTab === 'params' && (
          <Card className="glass card-hover animate-fade-in-up">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                ⚙️ 实验默认参数
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">并行方向数</label>
                  <input
                    type="number"
                    value={config.defaultNumDirections}
                    onChange={(e) => updateConfigField('defaultNumDirections', parseNumberField(e.target.value, DEFAULT_CONFIG.defaultNumDirections))}
                    min={1}
                    max={10}
                    className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    单次实验同时探索的独立方向数量 (1-10)
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">总进化轮次</label>
                  <input
                    type="number"
                    value={config.defaultMaxRounds}
                    onChange={(e) => updateConfigField('defaultMaxRounds', parseNumberField(e.target.value, DEFAULT_CONFIG.defaultMaxRounds))}
                    min={1}
                    max={20}
                    className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    包含 original 初始轮；例如 3 = original + mutation + crossover
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">最大循环数</label>
                  <input
                    type="number"
                    value={config.defaultMaxLoops}
                    onChange={(e) => updateConfigField('defaultMaxLoops', parseNumberField(e.target.value, DEFAULT_CONFIG.defaultMaxLoops))}
                    min={1}
                    max={50}
                    className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    每条挖掘路径的主循环次数 (1-50)
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">每个假设因子数</label>
                  <input
                    type="number"
                    value={config.defaultFactorsPerHypothesis}
                    onChange={(e) => updateConfigField('defaultFactorsPerHypothesis', parseNumberField(e.target.value, DEFAULT_CONFIG.defaultFactorsPerHypothesis))}
                    min={1}
                    max={20}
                    className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    单个假设生成的候选因子数量 (1-20)
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">默认市场</label>
                  <select
                    value={config.defaultMarket}
                    onChange={(e) => updateConfigField('defaultMarket', e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  >
                    <option value="csi300">CSI 300 (沪深300)</option>
                    <option value="csi500">CSI 500 (中证500)</option>
                    <option value="sp500">S&P 500</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">回测超时 (秒)</label>
                  <input
                    type="number"
                    value={config.backtestTimeout}
                    onChange={(e) => updateConfigField('backtestTimeout', parseNumberField(e.target.value, DEFAULT_CONFIG.backtestTimeout))}
                    min={60}
                    max={3600}
                    className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    单次回测最大执行时间 (秒)
                  </p>
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium mb-2">默认因子库名称后缀</label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground font-mono">all_factors_library_</span>
                    <input
                      type="text"
                      value={config.defaultLibrarySuffix}
                      onChange={(e) => {
                        const val = e.target.value.replace(/[^a-zA-Z0-9_\-]/g, '');
                        updateConfigField('defaultLibrarySuffix', val);
                      }}
                      placeholder="例如 momentum_v1 (留空则无后缀)"
                      className="flex-1 rounded-lg border border-input bg-background px-4 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary transition-all"
                    />
                    <span className="text-sm text-muted-foreground font-mono">.json</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    生成的因子将保存到此文件。支持字母、数字、下划线。
                  </p>
                </div>
              </div>

              <div className="pt-4 border-t border-border/50 space-y-4">
                <h4 className="text-sm font-medium">高级控制</h4>
                
                <label className="flex items-center gap-3 cursor-pointer group p-3 rounded-lg border border-border/50 hover:bg-secondary/20 transition-all">
                  <input
                    type="checkbox"
                    checked={config.parallelExecution}
                    onChange={(e) => updateConfigField('parallelExecution', e.target.checked)}
                    className="h-5 w-5 rounded border-input text-primary focus:ring-primary"
                  />
                  <div className="flex-1">
                    <div className="font-medium group-hover:text-primary transition-colors">
                      启用并行执行
                    </div>
                    <div className="text-xs text-muted-foreground">
                      允许多个挖掘方向同时运行，显著加快实验速度，但会增加系统负载
                    </div>
                  </div>
                </label>

                <label className="flex items-center gap-3 cursor-pointer group p-3 rounded-lg border border-border/50 hover:bg-secondary/20 transition-all">
                  <input
                    type="checkbox"
                    checked={config.qualityGateEnabled}
                    onChange={(e) => updateConfigField('qualityGateEnabled', e.target.checked)}
                    className="h-5 w-5 rounded border-input text-primary focus:ring-primary"
                  />
                  <div className="flex-1">
                    <div className="font-medium group-hover:text-primary transition-colors">
                      启用质量门控
                    </div>
                    <div className="text-xs text-muted-foreground">
                      自动检测并过滤低质量因子，防止其进入下一轮迭代，保证最终结果质量
                    </div>
                  </div>
                </label>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Evaluation Rules Tab */}
        {activeTab === 'evaluation' && (
          <Card className="glass animate-fade-in-up">
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><BarChart3 className="h-5 w-5" />单因子 OTO 评估规则</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">每次运行保存完整配置快照和哈希；方向只由训练期 IC 决定。</p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {([
                  ['trainingStart', '训练开始'], ['trainingEnd', '训练结束'],
                  ['validationStart', '验证开始'], ['validationEnd', '验证结束'],
                ] as const).map(([key, label]) => (
                  <div key={key}><label className="mb-2 block text-sm font-medium">{label}</label><input type="date" value={evaluationConfig[key]} onChange={(event) => updateEvaluationField(key, event.target.value)} className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm" /></div>
                ))}
              </div>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {([
                  ['icThreshold', '绝对 IC 门槛', 0.001], ['icirThreshold', 'ICIR 门槛', 0.05],
                  ['spreadThreshold', '收益差门槛', 0.01], ['excessSharpeThreshold', '超额 Sharpe 门槛', 0.1],
                ] as const).map(([key, label, step]) => (
                  <div key={key}><label className="mb-2 block text-sm font-medium">{label}</label><input type="number" step={step} value={evaluationConfig[key]} onChange={(event) => updateEvaluationField(key, Number(event.target.value))} className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm" /></div>
                ))}
              </div>
              <div className="grid gap-4 border-y border-border py-4 md:grid-cols-4">
                <div><label className="mb-2 block text-sm font-medium">分组数</label><input type="number" min={2} max={20} value={evaluationConfig.groupCount} onChange={(event) => updateEvaluationField('groupCount', Number(event.target.value))} className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm" /></div>
                <div><label className="mb-2 block text-sm font-medium">调仓周期（日）</label><input type="number" min={1} max={252} step={1} value={evaluationConfig.rebalancePeriodDays} onChange={(event) => updateEvaluationField('rebalancePeriodDays', Number(event.target.value))} className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm" /></div>
                <div><label className="mb-2 block text-sm font-medium">2023 及以前费率</label><input type="number" step="0.00005" value={evaluationConfig.feeThrough2023} onChange={(event) => updateEvaluationField('feeThrough2023', Number(event.target.value))} className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm" /></div>
                <div><label className="mb-2 block text-sm font-medium">2024 起费率</label><input type="number" step="0.00005" value={evaluationConfig.feeFrom2024} onChange={(event) => updateEvaluationField('feeFrom2024', Number(event.target.value))} className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm" /></div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm"><span><span className="text-muted-foreground">引擎：</span>{evaluationConfig.engine}</span><Badge variant="outline">2026 样本外：{evaluationConfig.oosStatus === 'sealed' ? '已封存' : evaluationConfig.oosStatus}</Badge></div>
            </CardContent>
          </Card>
        )}

        {/* Mining Direction Tab */}
        {activeTab === 'directions' && (
          <Card className="glass card-hover animate-fade-in-up">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Compass className="h-5 w-5" />
                挖掘方向（参考 Alpha158(20)）
              </CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                选择作为默认参考的挖掘方向；启动任务时可从中选用或随机一条
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <label className="block text-sm font-medium mb-3">使用方式</label>
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="miningDirectionMode"
                      checked={config.miningDirectionMode === 'selected'}
                      onChange={() => updateConfigField('miningDirectionMode', 'selected')}
                      className="h-4 w-4 text-primary focus:ring-primary"
                    />
                    <span>使用下方选中的方向（启动时从选中中取一条或按业务逻辑使用）</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="miningDirectionMode"
                      checked={config.miningDirectionMode === 'random'}
                      onChange={() => updateConfigField('miningDirectionMode', 'random')}
                      className="h-4 w-4 text-primary focus:ring-primary"
                    />
                    <span className="flex items-center gap-1.5">
                      <Shuffle className="h-4 w-4" />
                      随机（从选中方向中随机选一条）
                    </span>
                  </label>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-3">
                  <label className="text-sm font-medium">参考方向（可多选）</label>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        updateConfigField(
                          'selectedMiningDirectionIndices',
                          REFERENCE_MINING_DIRECTIONS.map((_: MiningDirectionItem, i: number) => i)
                        );
                      }}
                    >
                      全选
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => updateConfigField('selectedMiningDirectionIndices', [])}
                    >
                      取消全选
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[320px] overflow-y-auto rounded-lg border border-border/50 bg-secondary/10 p-3">
                  {REFERENCE_MINING_DIRECTIONS.map((item: MiningDirectionItem, idx: number) => {
                    const label = getDirectionLabel(item);
                    return (
                      <label
                        key={idx}
                        className="flex items-center gap-2 p-2 rounded-lg hover:bg-secondary/20 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={config.selectedMiningDirectionIndices.includes(idx)}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...config.selectedMiningDirectionIndices, idx].sort((a, b) => a - b)
                              : config.selectedMiningDirectionIndices.filter((i) => i !== idx);
                            updateConfigField('selectedMiningDirectionIndices', next);
                          }}
                          className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
                        />
                        <span className="text-sm truncate flex-1" title={label}>
                          {label}
                        </span>
                      </label>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  已选 {config.selectedMiningDirectionIndices.length} / {REFERENCE_MINING_DIRECTIONS.length} 项。
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Info Footer */}
      <Card className="glass border-primary/20 bg-primary/5">
        <CardContent className="p-4 flex gap-3">
          <div className="text-xl">💡</div>
          <div className="text-sm text-muted-foreground">
            <p className="mb-1 font-medium text-foreground">配置提示</p>
            <p>所有配置修改后会自动保存至后端环境文件及本地浏览器缓存。涉及 API 或路径的修改，建议在保存后重启相关服务以确保生效。</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
