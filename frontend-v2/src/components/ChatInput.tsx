import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Square, Compass, Bot, ChevronDown, Check } from 'lucide-react';
import { TaskConfig, type PromptPack } from '@/types';
import { getSystemConfig, type PromptPackOption } from '@/services/api';

interface ChatInputProps {
  onSubmit: (config: TaskConfig) => void;
  onStop?: () => void;
  isRunning?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSubmit, onStop, isRunning = false }) => {
  const [input, setInput] = useState('');
  const [useCustomMiningDirection, setUseCustomMiningDirection] = useState(false);
  const [promptPacks, setPromptPacks] = useState<PromptPackOption[]>([
    {
      name: 'zh_quant_v1',
      label: '中文优化版',
      version: '2026-08-20',
      outputLanguage: 'zh-CN',
      strictJson: true,
      description: '',
      planningPromptFile: '',
      factorPromptFile: '',
    },
    {
      name: 'en_default',
      label: '英文原版',
      version: 'pre-zh-prompt-optimization',
      outputLanguage: 'en',
      strictJson: false,
      description: '',
      planningPromptFile: '',
      factorPromptFile: '',
    },
  ]);
  const [promptPack, setPromptPack] = useState<PromptPack>(() => {
    const saved = localStorage.getItem('quantaalpha_config');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (typeof parsed.promptPack === 'string' && parsed.promptPack.trim()) {
          return parsed.promptPack;
        }
      } catch {}
    }
    return 'zh_quant_v1';
  });
  const [config] = useState<Partial<TaskConfig>>({
    librarySuffix: '',
  });
  const [isPromptMenuOpen, setIsPromptMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const promptMenuRef = useRef<HTMLDivElement>(null);

  const persistPromptPack = (nextPromptPack: PromptPack) => {
    try {
      const saved = localStorage.getItem('quantaalpha_config');
      const parsed = saved ? JSON.parse(saved) : {};
      localStorage.setItem(
        'quantaalpha_config',
        JSON.stringify({
          ...parsed,
          promptPack: nextPromptPack,
        }),
      );
    } catch {
      localStorage.setItem('quantaalpha_config', JSON.stringify({ promptPack: nextPromptPack }));
    }
  };

  const examplePrompts = [
    '💹 挖掘动量类因子，关注短期反转和成交量配合',
    '💰 探索价值成长组合，考虑行业中性化',
    '📊 基于技术指标构建因子，重点RSI和MACD',
  ];

  const handleSubmit = () => {
    if (isRunning) return;
    const suffix = config.librarySuffix?.trim() || undefined;
    onSubmit({
      userInput: input.trim(),
      useCustomMiningDirection,
      promptPack,
      ...config,
      librarySuffix: suffix,
    } as TaskConfig);
  };

  const updatePromptPack = (nextPromptPack: PromptPack) => {
    if (isRunning) return;
    setPromptPack(nextPromptPack);
    setIsPromptMenuOpen(false);
    persistPromptPack(nextPromptPack);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  useEffect(() => {
    let cancelled = false;
    getSystemConfig()
      .then((resp) => {
        if (cancelled) return;
        const packs = resp.data?.promptPacks || [];
        if (packs.length) {
          setPromptPacks(packs);
          if (!packs.some((pack) => pack.name === promptPack)) {
            const fallback = resp.data?.experimentConfig?.promptPack || packs[0].name;
            setPromptPack(fallback);
            persistPromptPack(fallback);
          }
        }
      })
      .catch(() => {
        // Keep local fallback options when backend config is temporarily unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!promptMenuRef.current?.contains(event.target as Node)) {
        setIsPromptMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, []);

  const currentPromptPack = promptPacks.find((pack) => pack.name === promptPack);

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 pb-6">
      <div className="container mx-auto px-6">
        
        {/* Example Prompts */}
        {!input && !isRunning && (
          <div className="flex flex-wrap justify-center gap-2 mb-3 overflow-x-auto pb-2 scrollbar-hide">
            {examplePrompts.map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => setInput(prompt)}
                className="glass rounded-xl px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:scale-105 transition-all whitespace-nowrap flex items-center gap-2 card-hover"
              >
                <Sparkles className="h-3 w-3" />
                {prompt}
              </button>
            ))}
          </div>
        )}

        {/* Main Input */}
        <div className="gradient-border">
          <div className="gradient-border-content">
            <div className="glass-strong rounded-xl p-4">
              {/* Icon bar: Custom mining direction etc. */}
              <div className="flex items-center gap-1 mb-3">
                <button
                  type="button"
                  onClick={() => setUseCustomMiningDirection((v) => !v)}
                  disabled={isRunning}
                  title={useCustomMiningDirection ? '使用设置中的挖掘方向（已开）' : '使用设置中的挖掘方向（点击开启）'}
                  className={`p-2 rounded-lg transition-all ${
                    useCustomMiningDirection
                      ? 'bg-primary/15 text-primary ring-1 ring-primary/30'
                      : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
                  }`}
                >
                  <Compass className="h-4 w-4" />
                </button>
                <span
                  className={`text-xs ml-1 ${
                    useCustomMiningDirection ? 'text-primary font-medium' : 'text-muted-foreground'
                  }`}
                >
                  自选挖掘方向
                </span>
                <div className="relative ml-3" ref={promptMenuRef}>
                  <button
                    type="button"
                    disabled={isRunning}
                    onClick={() => setIsPromptMenuOpen((open) => !open)}
                    title={currentPromptPack?.description || '选择本次挖掘使用的 prompt 版本'}
                    className={`group flex h-8 items-center gap-2 rounded-lg border px-2.5 text-xs font-medium transition-all ${
                      isRunning
                        ? 'border-border bg-secondary/30 text-muted-foreground opacity-60 cursor-not-allowed'
                        : 'border-primary/25 bg-primary/10 text-primary shadow-sm hover:-translate-y-0.5 hover:border-primary/40 hover:bg-primary/15 hover:shadow-md'
                    }`}
                  >
                    <span className="flex h-5 w-5 items-center justify-center rounded-md bg-background/80 shadow-sm">
                      <Bot className="h-3.5 w-3.5" />
                    </span>
                    <span className="max-w-[120px] truncate">{currentPromptPack?.label || promptPack}</span>
                    <ChevronDown
                      className={`h-3.5 w-3.5 transition-transform ${isPromptMenuOpen ? 'rotate-180' : ''}`}
                    />
                  </button>

                  {isPromptMenuOpen && !isRunning && (
                    <div className="absolute bottom-full left-0 z-50 mb-2 w-80 overflow-hidden rounded-xl border border-border/70 bg-background/95 p-1.5 shadow-2xl shadow-primary/10 backdrop-blur-xl">
                      <div className="px-2 py-1.5 text-[11px] font-medium text-muted-foreground">
                        Prompt 版本
                      </div>
                      <div className="max-h-72 overflow-y-auto">
                        {promptPacks.map((pack) => {
                          const selected = pack.name === promptPack;
                          return (
                            <button
                              key={pack.name}
                              type="button"
                              onClick={() => updatePromptPack(pack.name)}
                              className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-all ${
                                selected
                                  ? 'bg-primary/10 text-primary'
                                  : 'text-foreground hover:bg-secondary/60'
                              }`}
                            >
                              <span
                                className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md border ${
                                  selected
                                    ? 'border-primary bg-primary text-primary-foreground'
                                    : 'border-border bg-background'
                                }`}
                              >
                                {selected && <Check className="h-3.5 w-3.5" />}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="flex items-center gap-2">
                                  <span className="truncate text-sm font-semibold">{pack.label || pack.name}</span>
                                  {pack.outputLanguage && (
                                    <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                                      {pack.outputLanguage}
                                    </span>
                                  )}
                                </span>
                                <span className="mt-0.5 block truncate font-mono text-[11px] text-muted-foreground">
                                  {pack.name}
                                  {pack.version ? ` · ${pack.version}` : ''}
                                </span>
                                {pack.description && (
                                  <span className="mt-1 line-clamp-2 block text-[11px] leading-4 text-muted-foreground">
                                    {pack.description}
                                  </span>
                                )}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={
                      isRunning
                        ? '实验运行中...可以切换到其他页面，任务不会中断'
                        : useCustomMiningDirection
                        ? '已开启自选挖掘方向，将使用「设置 → 挖掘方向」中的选项'
                        : '描述因子挖掘需求，或开启「自选挖掘方向」使用设置中的方向 (Shift+Enter 换行，Enter 发送)'
                    }
                    disabled={isRunning}
                    className="w-full bg-transparent text-base placeholder:text-muted-foreground focus:outline-none resize-none"
                    rows={1}
                    style={{ maxHeight: '120px' }}
                  />
                </div>

                <div className="flex items-center gap-2">
                  {isRunning && onStop ? (
                    <button
                      onClick={onStop}
                      className="flex h-10 items-center gap-2 rounded-lg bg-red-500 px-3 text-sm font-medium text-white transition-all hover:scale-105 hover:bg-red-600 active:scale-95"
                      title="中断实验"
                    >
                      <Square className="h-5 w-5" />
                      停止
                    </button>
                  ) : (
                    <button
                      onClick={handleSubmit}
                      disabled={isRunning}
                      className="p-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:scale-105 active:scale-95"
                      title="发送 (Enter)"
                    >
                      <Send className="h-5 w-5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
