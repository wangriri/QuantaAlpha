import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  Boxes,
  CheckCircle2,
  FileText,
  GitBranch,
  Layers3,
  Loader2,
  RefreshCw,
  Search,
  Share2,
} from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { getPromptFlow } from '@/services/api';
import type { PromptFlowEdge, PromptFlowKey, PromptFlowNode, PromptFlowPack } from '@/services/api';

const NODE_W = 230;
const NODE_H = 122;
const STAGE_STYLES: Record<string, string> = {
  planning: 'border-blue-200 bg-blue-50/90 text-blue-900',
  hypothesis: 'border-emerald-200 bg-emerald-50/90 text-emerald-900',
  factor: 'border-violet-200 bg-violet-50/90 text-violet-900',
  eval: 'border-amber-200 bg-amber-50/90 text-amber-900',
  evolution: 'border-rose-200 bg-rose-50/90 text-rose-900',
};
const EDGE_COLORS: Record<string, string> = {
  blue: '#2563eb',
  green: '#059669',
  orange: '#d97706',
  purple: '#7c3aed',
  slate: '#64748b',
};

const sourceLabel = (item: PromptFlowKey) => {
  if (item.missing) return '未找到';
  return item.shared ? '共享文件' : '版本专属';
};

const sourceVariant = (item: PromptFlowKey) => {
  if (item.missing) return 'destructive' as const;
  return item.shared ? 'outline' as const : 'success' as const;
};

const edgePath = (edge: PromptFlowEdge, nodeMap: Map<string, PromptFlowNode>) => {
  const from = nodeMap.get(edge.from);
  const to = nodeMap.get(edge.to);
  if (!from || !to) return '';
  const sx = from.x + NODE_W;
  const sy = from.y + NODE_H / 2;
  const tx = to.x;
  const ty = to.y + NODE_H / 2;
  const midX = sx + (tx - sx) / 2;

  if (edge.from === 'expr_retry' && edge.to === 'factor_expr') {
    const right = Math.max(from.x + NODE_W, to.x + NODE_W) + 60;
    return `M ${from.x + NODE_W} ${from.y + 40} L ${right} ${from.y + 40} L ${right} ${to.y + 86} L ${to.x + NODE_W} ${to.y + 86}`;
  }
  if (edge.from === 'feedback' && edge.to === 'history') {
    return `M ${from.x} ${from.y + NODE_H / 2} L ${to.x - 80} ${from.y + NODE_H / 2} L ${to.x - 80} ${to.y + NODE_H / 2} L ${to.x} ${to.y + NODE_H / 2}`;
  }
  if (edge.from === 'mutation' && edge.to === 'hypothesis') {
    return `M ${from.x + NODE_W / 2} ${from.y} L ${from.x + NODE_W / 2} 560 L ${to.x + NODE_W / 2} 560 L ${to.x + NODE_W / 2} ${to.y + NODE_H}`;
  }
  if (edge.from === 'crossover' && edge.to === 'hypothesis') {
    const right = from.x + NODE_W + 80;
    return `M ${from.x + NODE_W / 2} ${from.y} L ${right} ${from.y - 80} L ${right} 88 L ${to.x + NODE_W / 2} 88 L ${to.x + NODE_W / 2} ${to.y}`;
  }
  if (Math.abs(tx - sx) < 40) {
    return `M ${sx} ${sy} L ${sx + 55} ${sy} L ${sx + 55} ${ty} L ${tx} ${ty}`;
  }
  return `M ${sx} ${sy} C ${midX} ${sy}, ${midX} ${ty}, ${tx} ${ty}`;
};

const PromptNode: React.FC<{
  node: PromptFlowNode;
  selected: boolean;
  pack?: PromptFlowPack;
  onSelect: () => void;
}> = ({ node, selected, pack, onSelect }) => {
  const missingCount = node.keys.filter((key) => pack?.keys[key]?.missing).length;
  return (
    <button
      onClick={onSelect}
      className={`absolute rounded-[18px] border bg-white p-[14px] text-left shadow-[0_10px_22px_rgba(15,23,42,0.08)] transition-all hover:-translate-y-0.5 hover:shadow-[0_14px_28px_rgba(15,23,42,0.12)] ${
        STAGE_STYLES[node.stage] || STAGE_STYLES.eval
      } ${selected ? 'ring-2 ring-primary/70 ring-offset-2' : ''}`}
      style={{ left: node.x, top: node.y, width: NODE_W, minHeight: NODE_H }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[15px] font-bold leading-tight">{node.title}</div>
          <div className="mt-1 text-[11px] font-medium opacity-70">{node.stageLabel}</div>
        </div>
        {missingCount > 0 ? (
          <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
        ) : (
          <CheckCircle2 className="h-4 w-4 shrink-0 opacity-60" />
        )}
      </div>
      <div className="mt-2 line-clamp-2 text-xs leading-5 opacity-80">{node.short}</div>
      <div className="mt-2 flex items-center gap-2 text-[11px] opacity-70">
        <FileText className="h-3.5 w-3.5" />
        <span>{node.keys.length} 个 prompt key</span>
      </div>
    </button>
  );
};

export const PromptManagerPage: React.FC = () => {
  const [nodes, setNodes] = useState<PromptFlowNode[]>([]);
  const [edges, setEdges] = useState<PromptFlowEdge[]>([]);
  const [packs, setPacks] = useState<PromptFlowPack[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [selectedPackName, setSelectedPackName] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState('planning');
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await getPromptFlow();
      if (!resp.success || !resp.data) throw new Error(resp.message || 'Prompt 数据加载失败');
      const data = resp.data;
      setNodes(data.nodes);
      setEdges(data.edges);
      setPacks(data.packs);
      setNotes(data.notes || []);
      setSelectedPackName((current) => current || data.activePack || data.packs[0]?.name || '');
      setSelectedNodeId((current) => current || data.nodes[0]?.id || 'planning');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Prompt 数据加载失败');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const selectedPack = useMemo(
    () => packs.find((pack) => pack.name === selectedPackName) || packs[0],
    [packs, selectedPackName],
  );
  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) || nodes[0],
    [nodes, selectedNodeId],
  );
  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const canvasWidth = 1600;
  const canvasHeight = 1600;
  const visibleKeys = useMemo(() => {
    if (!selectedPack || !selectedNode) return [];
    const normalized = query.trim().toLowerCase();
    return selectedNode.keys
      .map((key) => selectedPack.keys[key])
      .filter((item): item is PromptFlowKey => Boolean(item))
      .filter((item) => {
        if (!normalized) return true;
        return [item.key, item.file, item.reader, item.stage, item.role, item.value]
          .some((value) => String(value || '').toLowerCase().includes(normalized));
      });
  }, [selectedNode, selectedPack, query]);

  if (isLoading) {
    return (
      <div className="flex min-h-[520px] items-center justify-center">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>正在读取 Prompt 版本...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 overflow-x-auto pb-4">
      {error && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="flex items-center gap-3 p-4 text-sm text-destructive">
            <AlertCircle className="h-5 w-5" />
            {error}
          </CardContent>
        </Card>
      )}

      <div className="grid min-w-[1240px] gap-5 xl:grid-cols-[minmax(860px,1.2fr)_minmax(360px,0.8fr)]">
        <Card className="glass-strong overflow-hidden">
          <CardHeader className="border-b border-border/70 bg-white/70 px-[22px] py-[18px]">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Layers3 className="h-4 w-4" />
                  Prompt Pack Flow
                </div>
                <CardTitle className="mt-2 flex items-center gap-2 text-[22px]">
                  <GitBranch className="h-5 w-5 text-primary" />
                  Prompt管理
                </CardTitle>
                <p className="mt-2 max-w-3xl text-[13px] leading-6 text-muted-foreground">
                  按运行顺序查看每个 Prompt 版本的节点、文件来源和完整内容。共享节点会单独标注，方便判断哪些环节会随版本切换。
                </p>
                {selectedPack && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Badge variant="default">{selectedPack.label || selectedPack.name}</Badge>
                    <Badge variant={selectedPack.active ? 'success' : 'outline'}>
                      {selectedPack.active ? '当前启用' : '可选版本'}
                    </Badge>
                    {selectedPack.version && <Badge variant="outline">{selectedPack.version}</Badge>}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <select
                  value={selectedPack?.name || ''}
                  onChange={(event) => setSelectedPackName(event.target.value)}
                  className="h-10 w-[220px] rounded-md border border-input bg-white px-3 text-sm shadow-sm outline-none focus:ring-2 focus:ring-primary/30"
                >
                  {packs.map((pack) => (
                    <option key={pack.name} value={pack.name}>
                      {pack.label || pack.name}
                    </option>
                  ))}
                </select>
                <Button variant="outline" size="sm" onClick={loadData}>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  刷新
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="relative h-[calc(100vh-230px)] min-h-[620px] overflow-auto bg-gradient-to-br from-white via-blue-50/30 to-violet-50/30 p-5">
              <div
                className="relative rounded-[20px] bg-white/70"
                style={{
                  width: canvasWidth,
                  minWidth: canvasWidth,
                  height: canvasHeight,
                  backgroundImage:
                    'linear-gradient(to right, rgba(148,163,184,0.16) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.16) 1px, transparent 1px), linear-gradient(180deg, rgba(255,255,255,0.72), rgba(248,250,252,0.84))',
                  backgroundSize: '34px 34px, 34px 34px, auto',
                }}
              >
                <svg className="absolute inset-0 pointer-events-none" width={canvasWidth} height={canvasHeight}>
                  <defs>
                    {Object.entries(EDGE_COLORS).map(([name, color]) => (
                      <marker key={name} id={`prompt-arrow-${name}`} markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
                        <path d="M0,0 L0,6 L8,3 z" fill={color} />
                      </marker>
                    ))}
                  </defs>
                  {edges.map((edge, idx) => {
                    const colorName = edge.colorClass || 'slate';
                    const color = EDGE_COLORS[colorName] || EDGE_COLORS.slate;
                    const path = edgePath(edge, nodeMap);
                    const from = nodeMap.get(edge.from);
                    const to = nodeMap.get(edge.to);
                    const labelX = from && to ? (from.x + to.x + NODE_W) / 2 : 0;
                    const labelY = from && to ? (from.y + to.y + NODE_H) / 2 - 8 : 0;
                    return (
                      <g key={`${edge.from}-${edge.to}-${idx}`}>
                        <path
                          d={path}
                          fill="none"
                          stroke={color}
                          strokeWidth="2"
                          strokeDasharray={edge.dashed ? '7 6' : undefined}
                          markerEnd={`url(#prompt-arrow-${colorName in EDGE_COLORS ? colorName : 'slate'})`}
                          opacity={0.72}
                        />
                        {edge.label && (
                          <text x={labelX} y={labelY} fill={color} fontSize="11" fontWeight="600">
                            {edge.label}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>
                {nodes.map((node) => (
                  <PromptNode
                    key={node.id}
                    node={node}
                    pack={selectedPack}
                    selected={selectedNode?.id === node.id}
                    onSelect={() => setSelectedNodeId(node.id)}
                  />
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="glass-strong overflow-hidden">
          <CardHeader className="border-b border-border/70 bg-white/70 px-[22px] py-[18px]">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-[22px]">
                  <Share2 className="h-5 w-5 text-primary" />
                  节点详情
                </CardTitle>
                {selectedNode && <p className="mt-2 text-[13px] leading-6 text-muted-foreground">{selectedNode.long}</p>}
              </div>
            </div>
            <div className="relative mt-4">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索 key、文件、内容"
                className="h-9 w-full rounded-md border border-input bg-white pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </CardHeader>
          <CardContent className="h-[calc(100vh-230px)] min-h-[620px] space-y-4 overflow-auto p-5">
            {notes.length > 0 && (
              <div className="rounded-lg border border-blue-100 bg-blue-50/70 p-3 text-xs leading-5 text-blue-900">
                {notes.map((note) => <div key={note}>{note}</div>)}
              </div>
            )}
            {visibleKeys.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">没有匹配的 prompt key</div>
            ) : (
              visibleKeys.map((item) => (
                <div key={item.key} className="rounded-lg border border-border bg-white/85 p-4 shadow-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="rounded bg-secondary px-2 py-1 text-xs font-semibold">{item.key}</code>
                    <Badge variant={sourceVariant(item)}>{sourceLabel(item)}</Badge>
                  </div>
                  <div className="mt-3 grid gap-1 text-xs text-muted-foreground">
                    <span>文件：<code>{item.file}</code></span>
                    <span>读取：<code>{item.reader}</code></span>
                    <span>阶段：{item.stage}</span>
                    <span>职责：{item.role}</span>
                  </div>
                  <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg border bg-slate-950 p-4 text-xs leading-5 text-slate-50">
                    {item.missing ? '该版本或共享文件中没有找到这个 key。' : item.value}
                  </pre>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="glass-strong">
        <CardContent className="flex flex-wrap items-center gap-3 p-4 text-sm text-muted-foreground">
          <Boxes className="h-4 w-4 text-primary" />
          <span>当前共读取 {packs.length} 个 Prompt Pack，{nodes.length} 个流程节点。</span>
        </CardContent>
      </Card>
    </div>
  );
};
