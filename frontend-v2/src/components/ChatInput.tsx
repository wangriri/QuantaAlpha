import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Square, Compass, Bot } from 'lucide-react';
import { TaskConfig, type PromptPack } from '@/types';

interface ChatInputProps {
  onSubmit: (config: TaskConfig) => void;
  onStop?: () => void;
  isRunning?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSubmit, onStop, isRunning = false }) => {
  const [input, setInput] = useState('');
  const [useCustomMiningDirection, setUseCustomMiningDirection] = useState(false);
  const [promptPack, setPromptPack] = useState<PromptPack>(() => {
    const saved = localStorage.getItem('quantaalpha_config');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.promptPack === 'en_default' || parsed.promptPack === 'zh_quant_v1') {
          return parsed.promptPack;
        }
      } catch {}
    }
    return 'zh_quant_v1';
  });
  const [config] = useState<Partial<TaskConfig>>({
    librarySuffix: '',
  });
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  const togglePromptPack = () => {
    if (isRunning) return;
    setPromptPack((current) => (current === 'zh_quant_v1' ? 'en_default' : 'zh_quant_v1'));
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
                <button
                  type="button"
                  onClick={togglePromptPack}
                  disabled={isRunning}
                  title={
                    promptPack === 'zh_quant_v1'
                      ? '当前使用中文优化版提示词（点击切换英文原版）'
                      : '当前使用英文原版提示词（点击切换中文优化版）'
                  }
                  className={`ml-3 p-2 rounded-lg transition-all ${
                    promptPack === 'zh_quant_v1'
                      ? 'bg-primary/15 text-primary ring-1 ring-primary/30'
                      : 'bg-amber-500/15 text-amber-600 ring-1 ring-amber-500/30'
                  } ${isRunning ? 'opacity-60 cursor-not-allowed' : 'hover:scale-105'}`}
                >
                  <Bot className="h-4 w-4" />
                </button>
                <span
                  className={`text-xs ml-1 font-medium ${
                    promptPack === 'zh_quant_v1' ? 'text-primary' : 'text-amber-600'
                  }`}
                >
                  {promptPack === 'zh_quant_v1' ? '中文优化版' : '英文原版'}
                </span>
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
                      className="p-2.5 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-all hover:scale-105 active:scale-95"
                      title="中断实验"
                    >
                      <Square className="h-5 w-5" />
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
