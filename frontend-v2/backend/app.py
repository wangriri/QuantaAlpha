"""
QuantaAlpha Backend API
FastAPI-based REST + WebSocket API for factor mining and backtesting.

Integrates with the core QuantaAlpha CLI to launch experiments
and reads factor library JSON for the factor browsing API.
"""

import asyncio
import csv
import glob
import hashlib
import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Resolve the repository root. The active frontend lives under
# git_ignore_folder/frontend-v2, while older deployments used frontend-v2.
# ---------------------------------------------------------------------------
def _find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "quantaalpha").is_dir() and (candidate / "configs").is_dir():
            return candidate
    raise RuntimeError(f"Unable to locate QuantaAlpha project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve().parent)
# Ensure import quantaalpha is available (when backend is started from frontend-v2 directory, repo root is not in sys.path)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DOTENV_PATH = PROJECT_ROOT / ".env"
EXPERIMENT_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiment.yaml"
BACKTEST_CONFIG_PATH = PROJECT_ROOT / "configs" / "backtest.yaml"
EVALUATION_CONFIG_PATH = PROJECT_ROOT / "configs" / "evaluation.yaml"
TACTICAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "tactical_analysis.yaml"
TACTICAL_GROUP_TEST_DIR = PROJECT_ROOT / "data" / "results" / "tactical_group_tests"
DEDUP_REPORT_DIR = PROJECT_ROOT / "data" / "results" / "dedup_reports"
TRACE_ROOT = PROJECT_ROOT / "data" / "run_traces"
PROMPT_PACK_DEFAULTS = {
    "zh_quant_v1": {"output_language": "zh-CN", "strict_json": True},
    "en_default": {"output_language": "en", "strict_json": False},
}

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="QuantaAlpha API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
        "http://localhost:3011", "http://127.0.0.1:3011",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================== Pydantic Models ==========================


class MiningStartRequest(BaseModel):
    """Request to start a factor mining experiment."""
    direction: str = Field(..., description="Research direction, e.g. '价量因子挖掘'")
    numDirections: Optional[int] = Field(1, description="Parallel exploration directions")
    maxRounds: Optional[int] = Field(1, description="Evolution rounds")
    maxLoops: Optional[int] = Field(1, description="Iterations per direction")
    factorsPerHypothesis: Optional[int] = Field(1, description="Factors per hypothesis")
    librarySuffix: Optional[str] = Field(None, description="Factor library file suffix")
    qualityGateEnabled: Optional[bool] = Field(None, description="Enable quality gate checks")
    parallelEnabled: Optional[bool] = Field(None, description="Enable parallel execution within evolution phases")
    backtestTimeout: Optional[int] = Field(None, description="Backtest timeout in seconds")
    promptPack: Optional[str] = Field(None, description="Prompt pack: zh_quant_v1 | en_default")


class BacktestStartRequest(BaseModel):
    """Compatibility request for the independent factor evaluator."""
    factorJson: str = Field(..., description="Path to factor library JSON")
    factorSource: str = Field("custom", description="custom | combined")
    configPath: Optional[str] = Field(None, description="Path to evaluation config")


class EvaluationStartRequest(BaseModel):
    """Request to evaluate factors in a library independently."""
    factorJson: str = Field(..., description="Factor library filename")
    mode: str = Field("unevaluated", description="unevaluated | all | specified")
    factorIds: Optional[List[str]] = Field(None, description="Factor IDs for specified mode")
    refreshMarketCache: bool = False
    configPath: Optional[str] = None


class DedupGenerateRequest(BaseModel):
    factorJson: str
    configPath: Optional[str] = None


class DedupArchiveRequest(BaseModel):
    factorIds: List[str]


class TacticalAnalyzeRequest(BaseModel):
    library: str = Field(..., description="Factor library JSON filename")


class TacticalGroupTestRequest(BaseModel):
    library: str = Field(..., description="Factor library JSON filename")
    factorIds: List[str] = Field(..., min_length=2, max_length=10, description="Factor IDs in one tactical group")
    refresh: bool = Field(False, description="Recompute even when a saved group test exists")
    averageCorrelation: Optional[float] = Field(None, ge=-1.0, le=1.0)
    minPairCorrelation: Optional[float] = Field(None, ge=-1.0, le=1.0)
    minOverlapDays: Optional[int] = Field(None, ge=0)


class TacticalConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    min_training_months: Optional[int] = Field(None, ge=1, le=120)
    min_validation_months: Optional[int] = Field(None, ge=1, le=120)
    min_trading_days_per_month: Optional[int] = Field(None, ge=1, le=31)
    strong_best_month_quantile: Optional[float] = Field(None, ge=0.0, le=1.0)
    burst_month_quantile: Optional[float] = Field(None, ge=0.0, le=1.0)
    high_volatility_quantile: Optional[float] = Field(None, ge=0.0, le=1.0)
    severe_loss_quantile: Optional[float] = Field(None, ge=0.0, le=1.0)
    severe_drawdown_quantile: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_positive_month_ratio: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_burst_month_count: Optional[int] = Field(None, ge=0, le=120)
    high_return_correlation_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    duplicate_return_correlation_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_return_correlation_overlap: Optional[int] = Field(None, ge=2, le=5000)
    return_correlation_group_size: Optional[int] = Field(None, ge=2, le=10)
    return_correlation_group_avg_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_return_correlation_groups: Optional[int] = Field(None, ge=1, le=500)


class EvaluationConfigUpdate(BaseModel):
    trainingStart: Optional[str] = None
    trainingEnd: Optional[str] = None
    validationStart: Optional[str] = None
    validationEnd: Optional[str] = None
    icThreshold: Optional[float] = None
    icirThreshold: Optional[float] = None
    spreadThreshold: Optional[float] = None
    excessSharpeThreshold: Optional[float] = None
    groupCount: Optional[int] = None
    rebalancePeriodDays: Optional[int] = Field(None, ge=1, le=252)
    feeThrough2023: Optional[float] = None
    feeFrom2024: Optional[float] = None


class SystemConfigUpdate(BaseModel):
    """Partial update to system configuration (.env and YAML defaults)."""
    QLIB_DATA_DIR: Optional[str] = None
    DATA_RESULTS_DIR: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    CHAT_MODEL: Optional[str] = None
    REASONING_MODEL: Optional[str] = None
    DEFAULT_LIBRARY_SUFFIX: Optional[str] = None

    defaultNumDirections: Optional[int] = None
    defaultMaxRounds: Optional[int] = None
    defaultMaxLoops: Optional[int] = None
    defaultFactorsPerHypothesis: Optional[int] = None
    defaultMarket: Optional[str] = None
    parallelExecution: Optional[bool] = None
    qualityGateEnabled: Optional[bool] = None
    backtestTimeout: Optional[int] = None
    promptPack: Optional[str] = None


class ApiResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None


# ========================== In-Memory State ==========================

tasks: Dict[str, Dict[str, Any]] = {}
ws_connections: Dict[str, List[WebSocket]] = {}  # task_id -> list of WS


# ========================== Utility Helpers ==========================

def _gen_id() -> str:
    return str(uuid.uuid4())[:8]


def _now() -> str:
    return datetime.now().isoformat()


def _load_dotenv_dict() -> Dict[str, str]:
    """Parse the .env file into a dict (simple key=value, ignoring comments)."""
    env: Dict[str, str] = {}
    if DOTENV_PATH.exists():
        for line in DOTENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                env[key.strip()] = val.strip()
    return env


def _load_yaml_dict(path: Path) -> Dict[str, Any]:
    """Load a YAML file as a mutable dict."""
    if not path.exists():
        return {}
    try:
        from ruamel.yaml import YAML

        yaml_rt = YAML()
        with path.open("r", encoding="utf-8") as f:
            data = yaml_rt.load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _write_yaml_dict(path: Path, data: Dict[str, Any]) -> None:
    """Persist YAML defaults in a stable structured form."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from ruamel.yaml import YAML

        yaml_rt = YAML()
        yaml_rt.preserve_quotes = True
        yaml_rt.indent(mapping=2, sequence=4, offset=2)
        with path.open("w", encoding="utf-8") as f:
            yaml_rt.dump(data, f)
        return
    except Exception:
        pass

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _get_experiment_defaults(dotenv: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Read frontend-facing defaults from the canonical YAML/.env files."""
    dotenv = dotenv or _load_dotenv_dict()
    exp_cfg = _load_yaml_dict(EXPERIMENT_CONFIG_PATH)
    backtest_cfg = _load_yaml_dict(BACKTEST_CONFIG_PATH)

    planning = exp_cfg.get("planning") or {}
    execution = exp_cfg.get("execution") or {}
    evolution = exp_cfg.get("evolution") or {}
    factor = exp_cfg.get("factor") or {}
    qg = exp_cfg.get("quality_gate") or {}
    exp_backtest = exp_cfg.get("backtest") or {}
    prompting = exp_cfg.get("prompting") or {}
    bt_data = backtest_cfg.get("data") or {}

    quality_enabled = bool(
        qg.get("consistency_enabled")
        or qg.get("complexity_enabled")
        or qg.get("redundancy_enabled")
    )

    return {
        "defaultNumDirections": int(planning.get("num_directions", 1) or 1),
        "defaultMaxRounds": int(evolution.get("max_rounds", 1) or 1),
        "defaultMaxLoops": int(execution.get("max_loops", 1) or 1),
        "defaultFactorsPerHypothesis": int(factor.get("factors_per_hypothesis", 1) or 1),
        "defaultMarket": bt_data.get("market", "csi300"),
        "parallelExecution": bool(
            evolution.get("parallel_enabled", execution.get("parallel_execution", False))
        ),
        "qualityGateEnabled": quality_enabled,
        "backtestTimeout": int(exp_backtest.get("timeout", 600) or 600),
        "defaultLibrarySuffix": dotenv.get("DEFAULT_LIBRARY_SUFFIX", ""),
        "promptPack": prompting.get("pack", "zh_quant_v1"),
    }


def _apply_experiment_default_updates(updates: Dict[str, Any]) -> None:
    """Map frontend setting names onto experiment/backtest YAML defaults."""
    exp_cfg = _load_yaml_dict(EXPERIMENT_CONFIG_PATH)
    backtest_cfg = _load_yaml_dict(BACKTEST_CONFIG_PATH)
    exp_changed = False
    backtest_changed = False

    if "defaultNumDirections" in updates:
        exp_cfg.setdefault("planning", {})["num_directions"] = updates["defaultNumDirections"]
        exp_changed = True
    if "defaultMaxRounds" in updates:
        exp_cfg.setdefault("evolution", {})["max_rounds"] = updates["defaultMaxRounds"]
        exp_changed = True
    if "defaultMaxLoops" in updates:
        exp_cfg.setdefault("execution", {})["max_loops"] = updates["defaultMaxLoops"]
        exp_changed = True
    if "defaultFactorsPerHypothesis" in updates:
        exp_cfg.setdefault("factor", {})["factors_per_hypothesis"] = updates["defaultFactorsPerHypothesis"]
        exp_changed = True
    if "parallelExecution" in updates:
        enabled = bool(updates["parallelExecution"])
        exp_cfg.setdefault("evolution", {})["parallel_enabled"] = enabled
        exp_cfg.setdefault("execution", {})["parallel_execution"] = enabled
        exp_changed = True
    if "qualityGateEnabled" in updates:
        enabled = bool(updates["qualityGateEnabled"])
        qg = exp_cfg.setdefault("quality_gate", {})
        if enabled:
            qg["complexity_enabled"] = True
            qg["redundancy_enabled"] = True
            qg.setdefault("consistency_enabled", False)
        else:
            qg["consistency_enabled"] = False
            qg["complexity_enabled"] = False
            qg["redundancy_enabled"] = False
        exp_changed = True
    if "backtestTimeout" in updates:
        exp_cfg.setdefault("backtest", {})["timeout"] = updates["backtestTimeout"]
        exp_changed = True
    if "promptPack" in updates:
        prompt_pack = str(updates["promptPack"] or "zh_quant_v1")
        if prompt_pack not in PROMPT_PACK_DEFAULTS:
            raise HTTPException(status_code=400, detail=f"Unsupported prompt pack: {prompt_pack}")
        prompt_cfg = exp_cfg.setdefault("prompting", {})
        prompt_cfg["pack"] = prompt_pack
        prompt_cfg.update(PROMPT_PACK_DEFAULTS[prompt_pack])
        exp_changed = True
    if "defaultMarket" in updates:
        backtest_cfg.setdefault("data", {})["market"] = updates["defaultMarket"]
        backtest_changed = True

    if exp_changed:
        _write_yaml_dict(EXPERIMENT_CONFIG_PATH, exp_cfg)
    if backtest_changed:
        _write_yaml_dict(BACKTEST_CONFIG_PATH, backtest_cfg)


def _find_factor_jsons() -> List[str]:
    """Find all factor library JSON files in data/factorlib/."""
    factorlib_dir = PROJECT_ROOT / "data" / "factorlib"
    pattern = str(factorlib_dir / "all_factors_library*.json")
    results = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    old_pattern = str(PROJECT_ROOT / "all_factors_library*.json")
    old_results = sorted(glob.glob(old_pattern), key=os.path.getmtime, reverse=True)

    seen = set(results)
    for r in old_results:
        if r not in seen:
            results.append(r)
    return results


def _load_factor_library(path: str) -> Dict[str, Any]:
    """Load and parse a factor library JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl_file(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)
        except Exception:
            continue
    return rows


def _mtime_iso(path: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except Exception:
        return None


def _rel_to_trace(run_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(run_dir))
    except Exception:
        return str(path)


def _resolve_trace_dir(run_id: str) -> Path:
    if "/" in run_id or "\\" in run_id or not run_id.startswith("run_"):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    trace_root = TRACE_ROOT.resolve()
    run_dir = (trace_root / run_id).resolve()
    if not run_dir.exists() or not run_dir.is_dir() or trace_root not in run_dir.parents:
        raise HTTPException(status_code=404, detail=f"Trace run not found: {run_id}")
    return run_dir


def _extract_prompt_pack(run_dir: Path, config_snapshot: Dict[str, Any]) -> Optional[str]:
    prompting = config_snapshot.get("prompting") if isinstance(config_snapshot, dict) else None
    if isinstance(prompting, dict) and prompting.get("pack"):
        return str(prompting.get("pack"))
    planning = _read_json_file(run_dir / "00_planning" / "01_output.json", {}) or {}
    prompt_pack = (((planning.get("raw") or {}).get("variables") or {}).get("prompt_pack") or {})
    if isinstance(prompt_pack, dict) and prompt_pack.get("name"):
        return str(prompt_pack.get("name"))
    return None


def _node_kind(node_type: str, path: str = "") -> str:
    if node_type in {"planning_prompt", "planning_output", "hypothesis", "experiment", "feedback"}:
        return "agent"
    if node_type in {"factor"}:
        return "factor"
    if node_type in {"evaluation"}:
        return "evaluation"
    if node_type in {"formula_attempt"}:
        return "attempt"
    if "saved_factors" in path:
        return "storage"
    return "program"


def _node_explanation(node_type: str, label: str) -> str:
    explanations = {
        "user_input": "记录研究员提交的原始研究主题和前端参数。",
        "config_snapshot": "记录本次运行使用的实验配置快照，便于复盘参数。",
        "planning_prompt": "PlanningAgent 的输入提示词，负责把用户主题拆成多个研究方向。",
        "planning_output": "PlanningAgent 的输出，包含解析后的研究方向 JSON。",
        "direction": "一个可进入后续假设生成阶段的研究方向。",
        "round": "一次 original、mutation 或 crossover 轮次。",
        "task": "一个方向在某一轮中的具体挖掘任务。",
        "hypothesis": "HypothesisAgent 根据方向生成正式研究假设和约束。",
        "experiment": "FactorGenerationAgent 根据假设生成因子定义和公式。",
        "factor": "单个候选因子的名称、描述、公式和生命周期记录。",
        "formula_attempt": "公式生成或校验的一次尝试记录。",
        "evaluation": "后端对因子的 IC、ICIR、收益、Sharpe 等评价结果。",
        "feedback": "FeedbackAgent 根据因子结果总结经验，供后续轮次使用。",
        "saved_factors": "后端把候选因子写入因子库文件的记录。",
    }
    return explanations.get(node_type, f"{label} 的结构化运行记录。")


def _artifact_preview(run_dir: Path, rel_path: str) -> Dict[str, Any]:
    file_part = rel_path.split("#", 1)[0]
    if not file_part:
        return {}
    path = run_dir / file_part
    data = _read_json_file(path, None)
    if not isinstance(data, dict):
        return {}

    parsed = data.get("parsed") if isinstance(data.get("parsed"), dict) else {}
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    definition = data.get("definition") if isinstance(data.get("definition"), dict) else {}
    lifecycle = data.get("lifecycle") if isinstance(data.get("lifecycle"), dict) else {}

    preview: Dict[str, Any] = {}
    if "research_topic" in data:
        preview["用户输入"] = data.get("research_topic")
    actor = data.get("actor")
    if actor:
        preview["actor"] = actor
    if data.get("status"):
        preview["status"] = data.get("status")
    if raw.get("system_prompt"):
        preview["input"] = "包含 system_prompt、user_prompt 和 prompt variables"
    if raw.get("user_prompt"):
        preview["userPrompt"] = raw.get("user_prompt")
    if "response_text" in raw:
        preview["rawOutput"] = raw.get("response_text")

    parsed_data = parsed.get("data")
    if isinstance(parsed_data, dict):
        for key, cn_key in [
            ("hypothesis", "研究假设"),
            ("concise_observation", "观察"),
            ("concise_justification", "理由"),
            ("concise_knowledge", "沉淀知识"),
            ("concise_specification", "约束"),
        ]:
            if key in parsed_data:
                preview[cn_key] = parsed_data[key]
    if parsed.get("directions"):
        preview["研究方向"] = [d.get("text") for d in parsed.get("directions", []) if isinstance(d, dict)]
    if definition:
        preview["因子名称"] = definition.get("name")
        preview["因子公式"] = definition.get("expression")
        preview["因子描述"] = definition.get("description")
    if lifecycle:
        preview["生命周期"] = lifecycle
    metrics = parsed.get("metrics")
    if isinstance(metrics, dict):
        preview["指标"] = {
            key: metrics.get(key)
            for key in [
                "IC", "ICIR", "Rank IC", "Rank ICIR",
                "ic", "icir", "rank_ic", "rank_icir",
                "long_short_spread", "excess_sharpe",
                "1day.excess_return_with_cost.information_ratio",
                "1day.excess_return_without_cost.annualized_return",
            ]
            if key in metrics
        }
    if data.get("library_path"):
        preview["保存位置"] = data.get("library_path")
    if data.get("result_h5_path"):
        preview["因子值文件"] = data.get("result_h5_path")
    return {k: v for k, v in preview.items() if v not in (None, "", [], {})}


def _build_graph_from_events(run_dir: Path, run_id: str) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for event in _read_jsonl_file(run_dir / "04_events.jsonl"):
        if event.get("type") in {"node_created", "node_completed"} and event.get("node_id"):
            node_id = event["node_id"]
            nodes.setdefault(
                node_id,
                {
                    "id": node_id,
                    "type": event.get("node_type", "node"),
                    "label": event.get("label", node_id.rsplit(".", 1)[-1]),
                    "path": event.get("path", ""),
                    "status": event.get("status", "success"),
                },
            )
            for key in ["node_type", "label", "path", "status", "phase", "round_idx"]:
                if event.get(key) is not None:
                    target = "type" if key == "node_type" else key
                    nodes[node_id][target] = event.get(key)
        elif event.get("type") == "edge_created":
            edge = {"from": event.get("from_node"), "to": event.get("to_node"), "type": event.get("edge_type")}
            if edge.get("from") and edge.get("to") and edge not in edges:
                edges.append(edge)
    return {"schema_version": "1.0", "run_id": run_id, "nodes": list(nodes.values()), "edges": edges}


def _augment_graph_from_files(run_dir: Path, graph: Dict[str, Any]) -> Dict[str, Any]:
    run_id = run_dir.name
    nodes = {node.get("id"): dict(node) for node in graph.get("nodes", []) if node.get("id")}
    edges = list(graph.get("edges", []))

    def add_node(node_id: str, node_type: str, label: str, rel_path: str, **extra: Any) -> None:
        node = nodes.setdefault(
            node_id,
            {"id": node_id, "type": node_type, "label": label, "path": rel_path, "status": "success"},
        )
        node.update({k: v for k, v in extra.items() if v is not None})
        node.setdefault("path", rel_path)

    def add_edge(source: str, target: str, edge_type: str) -> None:
        edge = {"from": source, "to": target, "type": edge_type}
        if source in nodes and target in nodes and edge not in edges:
            edges.append(edge)

    if (run_dir / "01_user_input.json").exists():
        add_node(f"{run_id}.user_input", "user_input", "用户输入研究方向", "01_user_input.json")
    if (run_dir / "02_config_snapshot.yaml").exists():
        add_node(f"{run_id}.config", "config_snapshot", "配置快照", "02_config_snapshot.yaml")
    if (run_dir / "00_planning" / "00_prompt.json").exists():
        add_node(f"{run_id}.planning.prompt", "planning_prompt", "Planning Prompt", "00_planning/00_prompt.json")
    if (run_dir / "00_planning" / "01_output.json").exists():
        add_node(f"{run_id}.planning.output", "planning_output", "Planning Agent 输出方向", "00_planning/01_output.json")
        add_edge(f"{run_id}.planning.prompt", f"{run_id}.planning.output", "LLM_OUTPUT")
        planning = _read_json_file(run_dir / "00_planning" / "01_output.json", {}) or {}
        for item in ((planning.get("parsed") or {}).get("directions") or []):
            if isinstance(item, dict) and item.get("direction_id"):
                add_node(item["direction_id"], "direction", f"Direction {item.get('index', '')}", f"00_planning/01_output.json#parsed.directions[{item.get('index', 0)}]", direction_text=item.get("text"))
                add_edge(f"{run_id}.planning.output", item["direction_id"], "GENERATES_DIRECTION")

    for round_summary in sorted(run_dir.glob("round_*_*/00_round_summary.json")):
        round_dir = round_summary.parent
        round_data = _read_json_file(round_summary, {}) or {}
        round_idx = round_data.get("round_idx")
        phase = round_data.get("phase", round_dir.name.split("_", 2)[-1])
        round_id = round_data.get("round_id") or f"{run_id}.round_{int(round_idx or 0):02d}"
        add_node(round_id, "round", f"Round {round_idx} {phase}", _rel_to_trace(run_dir, round_summary), phase=phase, round_idx=round_idx)
        for task_file in sorted(round_dir.glob("task_*/00_task.json")):
            task_dir = task_file.parent
            task_data = _read_json_file(task_file, {}) or {}
            task_id = task_data.get("task_id") or f"{round_id}.task_{task_data.get('task_index', 0):03d}"
            add_node(task_id, "task", f"{task_data.get('phase', phase)} task {task_data.get('task_index', 0):03d}", _rel_to_trace(run_dir, task_file), phase=task_data.get("phase", phase), round_idx=task_data.get("round_idx", round_idx))
            add_edge(round_id, task_id, "HAS_TASK")
            if task_data.get("direction_ref"):
                add_edge(task_data["direction_ref"], task_id, "USES_DIRECTION")

            for rel_name, node_type, label, suffix, edge_from, edge_type in [
                ("02_mutation_prompt.json", "mutation_prompt", "MutationAgent 输入", "mutation_prompt", task_id, "HAS_PROMPT"),
                ("03_mutation_output.json", "mutation_output", "MutationAgent 输出", "mutation_output", task_id, "GENERATES_DIRECTION"),
                ("02_crossover_prompt.json", "crossover_prompt", "CrossoverAgent 输入", "crossover_prompt", task_id, "HAS_PROMPT"),
                ("03_crossover_output.json", "crossover_output", "CrossoverAgent 输出", "crossover_output", task_id, "GENERATES_DIRECTION"),
                ("03_hypothesis.json", "hypothesis", "LLM 生成研究假设", "hyp_000", task_id, "GENERATES_HYPOTHESIS"),
                ("05_hypothesis.json", "hypothesis", "LLM 生成研究假设", "hyp_000", task_id, "GENERATES_HYPOTHESIS"),
                ("04_experiment.json", "experiment", "LLM 生成因子公式", "experiment_000", f"{task_id}.hyp_000", "GENERATES_EXPERIMENT"),
                ("06_experiment.json", "experiment", "LLM 生成因子公式", "experiment_000", f"{task_id}.hyp_000", "GENERATES_EXPERIMENT"),
                ("07_feedback.json", "feedback", "LLM 根据结果生成反馈", "feedback_000", task_id, "HAS_FEEDBACK"),
                ("09_feedback.json", "feedback", "LLM 根据结果生成反馈", "feedback_000", task_id, "HAS_FEEDBACK"),
                ("08_saved_factors.json", "saved_factors", "后端保存因子和指标", "saved_factors", task_id, "SAVES_TO_LIBRARY"),
                ("10_saved_factors.json", "saved_factors", "后端保存因子和指标", "saved_factors", task_id, "SAVES_TO_LIBRARY"),
            ]:
                file_path = task_dir / rel_name
                if file_path.exists():
                    node_id = f"{task_id}.{suffix}"
                    add_node(node_id, node_type, label, _rel_to_trace(run_dir, file_path), phase=task_data.get("phase", phase), round_idx=task_data.get("round_idx", round_idx))
                    add_edge(edge_from, node_id, edge_type)

            factor_roots = list(task_dir.glob("05_factors/factor_*")) + list(task_dir.glob("07_factors/factor_*"))
            for factor_dir in sorted([p for p in factor_roots if p.is_dir()]):
                factor_file = factor_dir / "00_factor.json"
                factor_data = _read_json_file(factor_file, {}) or {}
                factor_id = factor_data.get("factor_id") or f"{task_id}.{factor_dir.name}"
                definition = factor_data.get("definition") or {}
                add_node(factor_id, "factor", definition.get("name") or factor_dir.name, _rel_to_trace(run_dir, factor_file), phase=task_data.get("phase", phase), round_idx=task_data.get("round_idx", round_idx))
                add_edge(f"{task_id}.experiment_000", factor_id, "GENERATES_FACTOR")
                for attempt in sorted((factor_dir / "01_formula_attempts").glob("attempt_*.json")) if (factor_dir / "01_formula_attempts").exists() else []:
                    attempt_data = _read_json_file(attempt, {}) or {}
                    attempt_id = attempt_data.get("attempt_id") or f"{factor_id}.{attempt.stem}"
                    add_node(attempt_id, "formula_attempt", attempt.stem.replace("_", " ").title(), _rel_to_trace(run_dir, attempt), phase=task_data.get("phase", phase), round_idx=task_data.get("round_idx", round_idx))
                    add_edge(factor_id, attempt_id, "HAS_ATTEMPT")
                value_ref = factor_dir / "02_factor_values_ref.json"
                if value_ref.exists():
                    add_node(f"{factor_id}.values", "factor_values", "后端计算因子值", _rel_to_trace(run_dir, value_ref), phase=task_data.get("phase", phase), round_idx=task_data.get("round_idx", round_idx))
                    add_edge(factor_id, f"{factor_id}.values", "HAS_VALUES")
                evaluation = factor_dir / "03_factor_evaluation.json"
                if evaluation.exists():
                    add_node(f"{factor_id}.eval_000", "evaluation", "因子评价结果", _rel_to_trace(run_dir, evaluation), phase=task_data.get("phase", phase), round_idx=task_data.get("round_idx", round_idx))
                    add_edge(factor_id, f"{factor_id}.eval_000", "HAS_EVALUATION")

    graph["nodes"] = list(nodes.values())
    graph["edges"] = edges
    return graph


def _load_trace_graph(run_dir: Path) -> Dict[str, Any]:
    graph = _read_json_file(run_dir / "03_run_graph.json", {}) or {}
    if not graph.get("nodes"):
        graph = _build_graph_from_events(run_dir, run_dir.name)
    graph = _augment_graph_from_files(run_dir, graph)
    graph["nodes"] = [
        {
            **node,
            "kind": _node_kind(str(node.get("type", "")), str(node.get("path", ""))),
            "explanation": _node_explanation(str(node.get("type", "")), str(node.get("label", ""))),
            "preview": _artifact_preview(run_dir, str(node.get("path", ""))),
        }
        for node in graph.get("nodes", [])
    ]
    return graph


def _trace_summary(run_dir: Path) -> Dict[str, Any]:
    run_summary = _read_json_file(run_dir / "00_run_summary.json", {}) or {}
    user_input = _read_json_file(run_dir / "01_user_input.json", {}) or {}
    config_snapshot = _load_yaml_dict(run_dir / "02_config_snapshot.yaml")
    raw_graph = _read_json_file(run_dir / "03_run_graph.json", {}) or {}
    node_types = [node.get("type") for node in raw_graph.get("nodes", []) if isinstance(node, dict)]
    event_types = [
        event.get("node_type")
        for event in _read_jsonl_file(run_dir / "04_events.jsonl")
        if event.get("type") in {"node_created", "node_completed"}
    ]
    round_count = len(list(run_dir.glob("round_*_*/00_round_summary.json"))) or node_types.count("round") or event_types.count("round")
    task_count = len(list(run_dir.glob("round_*_*/task_*/00_task.json"))) or node_types.count("task") or event_types.count("task")
    factor_count = len(list(run_dir.glob("round_*_*/task_*/0*_factors/factor_*/00_factor.json"))) or node_types.count("factor") or event_types.count("factor")
    return {
        "runId": run_dir.name,
        "status": run_summary.get("status", raw_graph.get("status", "unknown")),
        "researchTopic": run_summary.get("research_topic") or user_input.get("research_topic"),
        "startedAt": run_summary.get("started_at") or user_input.get("submitted_at"),
        "endedAt": run_summary.get("ended_at"),
        "updatedAt": raw_graph.get("updated_at") or _mtime_iso(run_dir / "04_events.jsonl") or _mtime_iso(run_dir),
        "promptPack": _extract_prompt_pack(run_dir, config_snapshot),
        "roundCount": round_count,
        "taskCount": task_count,
        "factorCount": factor_count,
        "traceDir": str(run_dir),
        "graphComplete": bool(raw_graph.get("nodes")),
    }


def _resolve_factor_library(value: str) -> Path:
    """Resolve a library while keeping API inputs inside known library locations."""
    raw = Path(value).expanduser()
    candidates = [raw] if raw.is_absolute() else [
        PROJECT_ROOT / "data" / "factorlib" / raw.name,
        PROJECT_ROOT / raw,
    ]
    allowed_roots = [
        (PROJECT_ROOT / "data" / "factorlib").resolve(),
        PROJECT_ROOT.resolve(),
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if not resolved.exists() or resolved.suffix.lower() != ".json":
            continue
        if any(resolved == root or root in resolved.parents for root in allowed_roots):
            return resolved
    raise HTTPException(status_code=404, detail=f"Factor library not found: {raw.name}")


def _resolve_evaluation_config(value: Optional[str]) -> Path:
    if not value:
        return EVALUATION_CONFIG_PATH
    resolved = Path(value).expanduser().resolve()
    configs_root = (PROJECT_ROOT / "configs").resolve()
    if not resolved.exists() or configs_root not in resolved.parents:
        raise HTTPException(status_code=400, detail="Evaluation config must be under configs/")
    return resolved


def _classify_quality(backtest_results: Dict[str, Any]) -> str:
    """Classify factor quality based on backtest metrics."""
    if not backtest_results:
        return "low"
    # Use information ratio or IC-related metrics
    ic = None
    for key in ["1day.excess_return_without_cost.information_ratio",
                 "1day.excess_return_with_cost.information_ratio"]:
        if key in backtest_results:
            ic = backtest_results[key]
            break
    if ic is None:
        # Try to find any IC-like metric
        for key, val in backtest_results.items():
            if "information_ratio" in key and isinstance(val, (int, float)):
                ic = val
                break
    if ic is None:
        return "medium"
    if ic > 0.5:
        return "high"
    if ic > 0.1:
        return "medium"
    return "low"


async def _broadcast(task_id: str, message: Dict[str, Any]):
    """Send a JSON message to all WebSocket clients for a task."""
    if task_id not in ws_connections:
        return
    dead: List[WebSocket] = []
    for ws in ws_connections[task_id]:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_connections[task_id].remove(ws)


# ========================== Mining Process ==========================

async def _run_mining(task_id: str, req: MiningStartRequest):
    """
    Launch the actual QuantaAlpha mining experiment as a subprocess
    and stream its output over WebSocket.
    """
    task = tasks[task_id]
    try:
        # Build the command
        env = os.environ.copy()
        # Load .env into env
        dotenv = _load_dotenv_dict()
        env.update(dotenv)
        venv_bin = PROJECT_ROOT / ".venv" / "bin"
        if not venv_bin.exists():
            venv_bin = Path(sys.executable).parent
        env.setdefault("VIRTUAL_ENV", str(Path(sys.executable).parents[1]))
        env.setdefault("CONDA_DEFAULT_ENV", env.get("CONDA_ENV_NAME", "quantaalpha"))
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
        env["FACTOR_CoSTEER_PYTHON_BIN"] = str(Path(sys.executable))

        # Use experiment_id as suffix to guarantee isolation
        experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        env["EXPERIMENT_ID"] = experiment_id
        selected_prompt_pack = req.promptPack
        
        # Enforce unique library suffix if not provided
        if not req.librarySuffix:
            req.librarySuffix = experiment_id
            # Update task config so frontend knows the suffix
            task["config"]["librarySuffix"] = req.librarySuffix
            
        env["FACTOR_LIBRARY_SUFFIX"] = req.librarySuffix

        results_base = dotenv.get("DATA_RESULTS_DIR", str(PROJECT_ROOT / "data" / "results"))
        env["WORKSPACE_PATH"] = f"{results_base}/workspace_{experiment_id}"
        env["PICKLE_CACHE_FOLDER_PATH_STR"] = f"{results_base}/pickle_cache_{experiment_id}"

        os.makedirs(env["WORKSPACE_PATH"], exist_ok=True)
        os.makedirs(env["PICKLE_CACHE_FOLDER_PATH_STR"], exist_ok=True)

        # Qlib symlink
        qlib_data = dotenv.get("QLIB_DATA_DIR", "")
        if qlib_data:
            qlib_symlink_dir = Path.home() / ".qlib" / "qlib_data"
            qlib_symlink_dir.mkdir(parents=True, exist_ok=True)
            cn_data_link = qlib_symlink_dir / "cn_data"
            if not cn_data_link.exists() or os.readlink(str(cn_data_link)) != qlib_data:
                if cn_data_link.is_symlink():
                    cn_data_link.unlink()
                cn_data_link.symlink_to(qlib_data)

        # Build a temporary config with frontend parameter overrides
        base_config_path = EXPERIMENT_CONFIG_PATH
        config_path_to_use = str(base_config_path)

        try:
            with open(base_config_path, "r", encoding="utf-8") as _f:
                run_cfg = yaml.safe_load(_f) or {}
            selected_prompt_pack = selected_prompt_pack or (
                (run_cfg.get("prompting") or {}).get("pack")
            )

            # Apply frontend overrides
            if req.numDirections is not None:
                run_cfg.setdefault("planning", {})["num_directions"] = req.numDirections
            if req.maxRounds is not None:
                run_cfg.setdefault("evolution", {})["max_rounds"] = req.maxRounds
            if req.maxLoops is not None:
                run_cfg.setdefault("execution", {})["max_loops"] = req.maxLoops
            if req.factorsPerHypothesis is not None:
                run_cfg.setdefault("factor", {})["factors_per_hypothesis"] = req.factorsPerHypothesis

            # Apply parallel execution override from frontend
            if req.parallelEnabled is not None:
                run_cfg.setdefault("evolution", {})["parallel_enabled"] = req.parallelEnabled
                run_cfg.setdefault("execution", {})["parallel_execution"] = req.parallelEnabled

            # Apply quality gate override from frontend
            if req.qualityGateEnabled is not None:
                qg = run_cfg.setdefault("quality_gate", {})
                if req.qualityGateEnabled:
                    # Enable quality gate: enable complexity and redundancy checks (default on), consistency keeps user YAML setting
                    qg.setdefault("complexity_enabled", True)
                    qg.setdefault("redundancy_enabled", True)
                    # Consistency check is expensive, only enable if explicitly enabled in YAML
                    qg.setdefault("consistency_enabled", False)
                else:
                    # Disable quality gate: disable all
                    qg["consistency_enabled"] = False
                    qg["complexity_enabled"] = False
                    qg["redundancy_enabled"] = False

            if req.backtestTimeout is not None:
                run_cfg.setdefault("backtest", {})["timeout"] = req.backtestTimeout
            if req.promptPack:
                if req.promptPack not in PROMPT_PACK_DEFAULTS:
                    raise ValueError(f"Unsupported prompt pack: {req.promptPack}")
                prompt_cfg = run_cfg.setdefault("prompting", {})
                prompt_cfg["pack"] = req.promptPack
                prompt_cfg.update(PROMPT_PACK_DEFAULTS[req.promptPack])

            # Write to a temporary file so the original is untouched
            tmp_dir = Path(env.get("WORKSPACE_PATH", "/tmp"))
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_cfg = tmp_dir / "experiment_override.yaml"
            with open(tmp_cfg, "w", encoding="utf-8") as _f:
                yaml.safe_dump(run_cfg, _f, allow_unicode=True, default_flow_style=False)
            config_path_to_use = str(tmp_cfg)
        except Exception as cfg_err:
            # Fall back to original config if anything fails
            import traceback
            traceback.print_exc()

        # Build CLI args
        if selected_prompt_pack in PROMPT_PACK_DEFAULTS:
            env["QUANTAALPHA_PROMPT_PACK"] = selected_prompt_pack

        cmd = [
            sys.executable, "-m", "quantaalpha.cli", "mine",
            "--direction", req.direction,
            "--config_path", config_path_to_use,
        ]

        task["status"] = "running"
        task["progress"]["phase"] = "planning"
        task["progress"]["message"] = "正在启动实验..."
        task["updatedAt"] = _now()

        await _broadcast(task_id, {
            "type": "progress",
            "taskId": task_id,
            "data": task["progress"],
            "timestamp": _now(),
        })

        # Launch subprocess
        process_options: Dict[str, Any] = {}
        if hasattr(os, "setsid"):
            process_options["preexec_fn"] = os.setsid

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            env=env,
            **process_options,
        )
        task["pid"] = proc.pid

        # Stream stdout line by line
        line_count = 0
        current_phase = "planning"

        # Noisy patterns to suppress (shared with backtest)
        _MINING_NOISE = (
            "field data contains nan",
            "common_infra",
            "PyTorch models are skipped",
            "UserWarning: pkg_resources",
            "FutureWarning",
            "UserWarning",
            "Training until validation scores",
            "Did not meet early stopping",
        )

        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            line_count += 1

            # Skip noisy warnings
            if any(p in line for p in _MINING_NOISE):
                continue

            if "Run trace directory:" in line:
                trace_dir = line.split("Run trace directory:", 1)[1].strip()
                trace_run_id = Path(trace_dir).name
                task["traceRunId"] = trace_run_id
                task["traceDir"] = trace_dir
                task.setdefault("config", {})["traceRunId"] = trace_run_id
                task["updatedAt"] = _now()
                await _broadcast(task_id, {
                    "type": "trace",
                    "taskId": task_id,
                    "data": {"traceRunId": trace_run_id, "traceDir": trace_dir},
                    "timestamp": _now(),
                })

            # Detect phase from log messages
            new_phase = current_phase
            if "factor_propose" in line:
                new_phase = "evolving"
            elif "factor_backtest" in line or "backtest" in line.lower():
                new_phase = "backtesting"
            elif "feedback" in line:
                new_phase = "analyzing"
            elif "factor_calculate" in line:
                new_phase = "evolving"
            elif "规划" in line or "planning" in line.lower():
                new_phase = "planning"
            elif "进化完成" in line or "程序执行完成" in line:
                new_phase = "completed"

            if new_phase != current_phase:
                current_phase = new_phase
                task["progress"]["phase"] = current_phase
                task["progress"]["message"] = line[:200]
                task["progress"]["timestamp"] = _now()
                await _broadcast(task_id, {
                    "type": "progress",
                    "taskId": task_id,
                    "data": task["progress"],
                    "timestamp": _now(),
                })

            # Send log every line (throttle to avoid flooding)
            if line_count % 3 == 0 or "INFO" in line or "ERROR" in line or "WARNING" in line:
                level = "info"
                if "ERROR" in line or "Error" in line:
                    level = "error"
                elif "WARNING" in line or "Warning" in line:
                    level = "warning"
                elif "完成" in line or "success" in line.lower():
                    level = "success"

                log_entry = {
                    "id": _gen_id(),
                    "timestamp": _now(),
                    "level": level,
                    "message": line[:500],
                }
                task["logs"].append(log_entry)
                # Keep only last 500 logs in memory
                if len(task["logs"]) > 500:
                    task["logs"] = task["logs"][-500:]

                await _broadcast(task_id, {
                    "type": "log",
                    "taskId": task_id,
                    "data": log_entry,
                    "timestamp": _now(),
                })

            # Extract metrics from log lines like "RankIC=0.0016"
            if "RankIC=" in line:
                try:
                    rank_ic_str = line.split("RankIC=")[1].split(",")[0].split(")")[0]
                    task["metrics"]["rankIc"] = float(rank_ic_str)
                    await _broadcast(task_id, {
                        "type": "metrics",
                        "taskId": task_id,
                        "data": task["metrics"],
                        "timestamp": _now(),
                    })
                except Exception:
                    pass
            
            # Check for factor saving to update top factors list
            if "已保存" in line or "因子" in line:
                _update_mining_metrics(task)
                if task.get("metrics"):
                     await _broadcast(task_id, {
                        "type": "result",
                        "taskId": task_id,
                        "data": {"status": task["status"], "metrics": task["metrics"]},
                        "timestamp": _now(),
                    })

        exit_code = await proc.wait()
        task["pid"] = None

        if task.get("status") == "cancelled":
            task["progress"]["phase"] = "cancelled"
            task["progress"]["message"] = "实验已停止"
        elif exit_code == 0:
            task["status"] = "completed"
            task["progress"]["phase"] = "completed"
            task["progress"]["progress"] = 100
            task["progress"]["message"] = "实验完成"
        else:
            task["status"] = "failed"
            task["progress"]["message"] = f"实验失败 (exit code: {exit_code})"

        task["updatedAt"] = _now()

        # Load final factor count from the library JSON
        # Prefer the library file matching the librarySuffix for this experiment
        _update_mining_metrics(task)

        await _broadcast(task_id, {
            "type": "result",
            "taskId": task_id,
            "data": {"status": task["status"], "metrics": task["metrics"]},
            "timestamp": _now(),
        })

    except Exception as e:
        task["status"] = "failed"
        task["progress"]["message"] = f"Error: {str(e)}"
        task["updatedAt"] = _now()
        await _broadcast(task_id, {
            "type": "error",
            "taskId": task_id,
            "data": {"error": str(e)},
            "timestamp": _now(),
        })


# ========================== API Endpoints ==========================

@app.get("/")
async def root():
    return {"message": "QuantaAlpha API", "version": "2.0.0"}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": _now()}


# ---- Mining endpoints ----

@app.post("/api/v1/mining/start", response_model=ApiResponse)
async def start_mining(req: MiningStartRequest):
    """Start a new factor mining experiment."""
    task_id = _gen_id()
    task = {
        "taskId": task_id,
        "status": "running",
        "config": req.model_dump(),
        "progress": {
            "phase": "parsing",
            "currentRound": 0,
            "totalRounds": req.maxRounds or 1,
            "progress": 0,
            "message": "正在初始化实验...",
            "timestamp": _now(),
        },
        "logs": [],
        "metrics": {
            "ic": 0, "icir": 0, "rankIc": 0, "rankIcir": 0,
            "annualReturn": 0, "sharpeRatio": 0, "maxDrawdown": 0,
            "totalFactors": 0, "highQualityFactors": 0,
            "mediumQualityFactors": 0, "lowQualityFactors": 0,
        },
        "result": None,
        "pid": None,
        "createdAt": _now(),
        "updatedAt": _now(),
    }
    tasks[task_id] = task

    # Launch the mining process in background
    asyncio.create_task(_run_mining(task_id, req))

    return ApiResponse(
        success=True,
        data={"taskId": task_id, "task": task},
        message="实验已启动",
    )


@app.get("/api/v1/mining/{task_id}", response_model=ApiResponse)
async def get_mining_status(task_id: str):
    """Get task status."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return ApiResponse(success=True, data={"task": tasks[task_id]})


@app.delete("/api/v1/mining/{task_id}", response_model=ApiResponse)
async def cancel_mining(task_id: str):
    """Cancel a running mining task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    task["status"] = "cancelled"
    task["progress"]["phase"] = "cancelled"
    task["progress"]["message"] = "正在停止任务..."
    task["updatedAt"] = _now()
    if task.get("pid"):
        try:
            pid = task["pid"]
            pgid = os.getpgid(pid) if hasattr(os, "getpgid") else None
            # Try graceful termination first
            if pgid and hasattr(os, "killpg"):
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
            
            # Wait briefly for cleanup (0.5s)
            for _ in range(5):
                try:
                    os.kill(pid, 0) # Check if alive
                    await asyncio.sleep(0.1)
                except ProcessLookupError:
                    break
            
            # Force kill if still running
            try:
                os.kill(pid, 0)
                if pgid and hasattr(os, "killpg"):
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass
    task["pid"] = None
    task["progress"]["message"] = "任务已停止"
    task["updatedAt"] = _now()
    await _broadcast(task_id, {
        "type": "result",
        "taskId": task_id,
        "data": {"status": "cancelled"},
        "timestamp": _now(),
    })
    return ApiResponse(success=True, message="任务已取消")


@app.get("/api/v1/mining/tasks/list", response_model=ApiResponse)
async def list_tasks():
    """List all tasks."""
    task_list = sorted(tasks.values(), key=lambda t: t["createdAt"], reverse=True)
    return ApiResponse(success=True, data={"tasks": task_list})


# ---- Run trace endpoints ----

@app.get("/api/v1/traces", response_model=ApiResponse)
async def list_traces():
    """List structured run traces stored under data/run_traces/."""
    if not TRACE_ROOT.exists():
        return ApiResponse(success=True, data={"runs": []})
    runs = [
        _trace_summary(run_dir)
        for run_dir in TRACE_ROOT.glob("run_*")
        if run_dir.is_dir()
    ]
    runs.sort(key=lambda item: item.get("updatedAt") or item.get("startedAt") or "", reverse=True)
    return ApiResponse(success=True, data={"runs": runs})


@app.get("/api/v1/traces/{run_id}", response_model=ApiResponse)
async def get_trace(run_id: str):
    """Return a visualizable trace graph with file-backed node previews."""
    run_dir = _resolve_trace_dir(run_id)
    summary = _trace_summary(run_dir)
    graph = _load_trace_graph(run_dir)
    events = _read_jsonl_file(run_dir / "04_events.jsonl")
    rounds = [
        _read_json_file(path, {}) or {}
        for path in sorted(run_dir.glob("round_*_*/00_round_summary.json"))
    ]
    tasks_found = [
        _read_json_file(path, {}) or {}
        for path in sorted(run_dir.glob("round_*_*/task_*/00_task.json"))
    ]
    factors = [
        _read_json_file(path, {}) or {}
        for path in sorted(run_dir.glob("round_*_*/task_*/0*_factors/factor_*/00_factor.json"))
    ]
    timeline = [
        {
            "eventId": event.get("event_id"),
            "type": event.get("type"),
            "time": event.get("time"),
            "nodeId": event.get("node_id") or event.get("to_node"),
            "label": event.get("label"),
            "status": event.get("status"),
        }
        for event in events
    ]
    return ApiResponse(
        success=True,
        data={
            "summary": summary,
            "nodes": graph.get("nodes", []),
            "edges": graph.get("edges", []),
            "rounds": rounds,
            "tasks": tasks_found,
            "factors": factors,
            "timeline": timeline,
        },
    )


@app.get("/api/v1/traces/{run_id}/artifact", response_model=ApiResponse)
async def get_trace_artifact(run_id: str, path: str = Query(..., description="Trace-relative artifact path")):
    """Read a trace artifact while preventing access outside the selected run."""
    run_dir = _resolve_trace_dir(run_id)
    file_part = path.split("#", 1)[0]
    if not file_part or Path(file_part).is_absolute():
        raise HTTPException(status_code=400, detail="Artifact path must be relative to the run trace")
    target = (run_dir / file_part).resolve()
    if target != run_dir and run_dir not in target.parents:
        raise HTTPException(status_code=403, detail="Artifact path escapes the run trace directory")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {file_part}")

    suffix = target.suffix.lower()
    try:
        if suffix == ".json":
            content = json.loads(target.read_text(encoding="utf-8"))
            kind = "json"
        elif suffix == ".jsonl":
            content = _read_jsonl_file(target)
            kind = "jsonl"
        elif suffix in {".yaml", ".yml"}:
            content = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
            kind = "yaml"
        else:
            content = target.read_text(encoding="utf-8", errors="replace")
            kind = "text"
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read artifact: {exc}") from exc

    return ApiResponse(
        success=True,
        data={
            "runId": run_id,
            "path": file_part,
            "kind": kind,
            "content": content,
            "updatedAt": _mtime_iso(target),
        },
    )


# ---- Factor library endpoints ----

@app.get("/api/v1/factors", response_model=ApiResponse)
async def get_factors(
    quality: Optional[str] = Query(None, description="Filter by quality: high/medium/low"),
    search: Optional[str] = Query(None, description="Search by factor name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    library: Optional[str] = Query(None, description="Specific library file name"),
):
    """Get factors from the factor library JSON."""
    # Find the most recent factor library
    if library:
        lib_path = str(PROJECT_ROOT / "data" / "factorlib" / library)
        # Fallback: check if file exists at project root (legacy location)
        if not Path(lib_path).exists():
            alt = str(PROJECT_ROOT / library)
            if Path(alt).exists():
                lib_path = alt
    else:
        jsons = _find_factor_jsons()
        if not jsons:
            return ApiResponse(
                success=True,
                data={"factors": [], "total": 0, "limit": limit, "offset": offset,
                      "libraries": []},
            )
        lib_path = jsons[0]

    try:
        raw = _load_factor_library(lib_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read factor library: {e}")

    factors_dict = raw.get("factors", {})
    metadata = raw.get("metadata", {})

    # Convert dict to list with quality classification
    factors_list: List[Dict[str, Any]] = []
    for factor_id, factor_info in factors_dict.items():
        if not isinstance(factor_info, dict):
            continue
        bt = factor_info.get("backtest_results", {})
        evaluation = factor_info.get("evaluation_v2") or {}
        training = evaluation.get("training") or {}
        validation = evaluation.get("validation") or {}
        evaluation_status = evaluation.get("status", "not_evaluated")
        lifecycle = factor_info.get("lifecycle") or evaluation.get("lifecycle") or {
            "status": "not_evaluated",
            "active": False,
        }
        if evaluation_status == "passed":
            q = "high"
        elif evaluation_status in {"not_evaluated", "running"}:
            q = "medium"
        else:
            q = "low"
        ic = training.get("ic", bt.get("IC", bt.get("1day.excess_return_without_cost.information_coefficient", 0)))
        icir = training.get("icir", bt.get("ICIR", bt.get("1day.excess_return_without_cost.information_coefficient_ir", 0)))
        rank_ic = training.get("rank_ic", bt.get("Rank IC", bt.get("rank_ic", bt.get("1day.excess_return_without_cost.rank_ic", 0))))
        rank_icir = training.get("rank_icir", bt.get("Rank ICIR", bt.get("rank_ic_ir", bt.get("1day.excess_return_without_cost.rank_ic_ir", 0))))
        
        factor_entry = {
            "factorId": factor_info.get("factor_id", factor_id),
            "factorName": factor_info.get("factor_name", "Unknown"),
            "factorExpression": factor_info.get("factor_expression", ""),
            "factorDescription": factor_info.get("factor_description", ""),
            "factorFormulation": factor_info.get("factor_formulation", ""),
            "quality": q,
            "backtestResults": bt,
            "qlibLegacy": factor_info.get("qlib_legacy"),
            "evaluationStatus": evaluation_status,
            "directionMultiplier": evaluation.get("direction_multiplier"),
            "trainingMetrics": training,
            "validationMetrics": validation,
            "gateResults": evaluation.get("gates") or evaluation.get("gate_results") or {},
            "artifacts": evaluation.get("artifacts") or {},
            "lookaheadAudit": evaluation.get("lookahead_audit") or {},
            "lifecycle": lifecycle,
            "oosStatus": factor_info.get("oos_status", evaluation.get("oos_status", "sealed")),
            "subperiods": evaluation.get("subperiods") or {},
            # Extract key metrics
            "ic": ic,
            "icir": icir,
            "rankIc": rank_ic,
            "rankIcir": rank_icir,
            "annualReturn": training.get("head_group_return_gross", bt.get("1day.excess_return_with_cost.annualized_return",
                                  bt.get("1day.excess_return_without_cost.annualized_return", 0)),
            ),
            "maxDrawdown": bt.get("1day.excess_return_with_cost.max_drawdown", 
                                 bt.get("1day.excess_return_without_cost.max_drawdown", 0)),
            "sharpeRatio": training.get("excess_sharpe", bt.get("1day.excess_return_with_cost.information_ratio",
                                bt.get("1day.excess_return_without_cost.information_ratio", 0)),
            ),
            "round": factor_info.get("evolution_metadata", {}).get("round", 0)
            if isinstance(factor_info.get("evolution_metadata"), dict) else 0,
            "direction": factor_info.get("evolution_metadata", {}).get("direction_index", "")
            if isinstance(factor_info.get("evolution_metadata"), dict) else "",
            "createdAt": factor_info.get("added_at", ""),
        }
        factors_list.append(factor_entry)

    # Apply filters
    if quality:
        factors_list = [
            f for f in factors_list
            if f["quality"] == quality
            or f["evaluationStatus"] == quality
            or (quality == "archived" and not (f.get("lifecycle") or {}).get("active", False))
            or (quality == "duplicate_suspected" and (f.get("lifecycle") or {}).get("status") == "duplicate_suspected")
        ]
    if search:
        search_lower = search.lower()
        factors_list = [
            f for f in factors_list
            if search_lower in f["factorName"].lower()
            or search_lower in f.get("factorDescription", "").lower()
            or search_lower in f.get("factorExpression", "").lower()
        ]

    total = len(factors_list)
    paginated = factors_list[offset: offset + limit]

    # Available library files
    all_libs = [Path(p).name for p in _find_factor_jsons()]

    return ApiResponse(
        success=True,
        data={
            "factors": paginated,
            "total": total,
            "limit": limit,
            "offset": offset,
            "metadata": metadata,
            "libraries": all_libs,
        },
    )


# ---- Factor cache endpoints ----
# IMPORTANT: These must be registered BEFORE /api/v1/factors/{factor_id}
# otherwise FastAPI matches "cache-status" as a factor_id parameter.

@app.get("/api/v1/factors/cache-status", response_model=ApiResponse)
async def get_cache_status(
    library: Optional[str] = Query(None, description="Factor library JSON filename"),
):
    """Check cache status of factors in the specified factor library."""
    if library:
        lib_path = str(PROJECT_ROOT / "data" / "factorlib" / library)
        if not Path(lib_path).exists():
            alt = str(PROJECT_ROOT / library)
            if Path(alt).exists():
                lib_path = alt
    else:
        jsons = _find_factor_jsons()
        if not jsons:
            return ApiResponse(success=True, data={
                "total": 0, "h5_cached": 0, "md5_cached": 0,
                "need_compute": 0, "factors": [],
            })
        lib_path = jsons[0]

    if not Path(lib_path).exists():
        raise HTTPException(status_code=404, detail=f"Factor library not found: {library}")

    # Import from core library
    from quantaalpha.factors.library import FactorLibraryManager
    result = FactorLibraryManager.check_cache_status(lib_path)
    return ApiResponse(success=True, data=result)


@app.post("/api/v1/factors/warm-cache", response_model=ApiResponse)
async def warm_cache(
    library: Optional[str] = Query(None, description="Factor library JSON filename"),
):
    """Batch sync from result.h5 to MD5 cache directory."""
    if library:
        lib_path = str(PROJECT_ROOT / "data" / "factorlib" / library)
        if not Path(lib_path).exists():
            alt = str(PROJECT_ROOT / library)
            if Path(alt).exists():
                lib_path = alt
    else:
        jsons = _find_factor_jsons()
        if not jsons:
            return ApiResponse(success=False, error="未找到因子库文件")
        lib_path = jsons[0]

    if not Path(lib_path).exists():
        raise HTTPException(status_code=404, detail=f"Factor library not found: {library}")

    from quantaalpha.factors.library import FactorLibraryManager
    result = FactorLibraryManager.warm_cache_from_json(lib_path)
    # Build a clear message
    parts = []
    if result['synced']:
        parts.append(f"新同步 {result['synced']} 个")
    if result.get('already_cached'):
        parts.append(f"已有缓存 {result['already_cached']} 个")
    if result.get('no_source'):
        parts.append(f"无H5源 {result['no_source']} 个(回测时从表达式计算)")
    if result['failed']:
        parts.append(f"失败 {result['failed']} 个")
    msg = "，".join(parts) if parts else "无需操作"
    return ApiResponse(
        success=True,
        data=result,
        message=msg,
    )


# ---- Factor library list endpoint (must be BEFORE {factor_id} route) ----

@app.get("/api/v1/factors/libraries", response_model=ApiResponse)
async def list_factor_libraries():
    """List all factor library JSON files in the project root."""
    libs = [Path(p).name for p in _find_factor_jsons()]
    return ApiResponse(success=True, data={"libraries": libs})


@app.get("/api/v1/factors/{factor_id}", response_model=ApiResponse)
async def get_factor_detail(
    factor_id: str,
    library: Optional[str] = Query(None, description="Factor library JSON filename"),
):
    """Get full detail of a single factor."""
    jsons = [_resolve_factor_library(library)] if library else _find_factor_jsons()
    for lib_path in jsons:
        try:
            raw = _load_factor_library(lib_path)
            factors = raw.get("factors", {})
            if factor_id in factors:
                info = factors[factor_id]
                return ApiResponse(success=True, data={"factor": info})
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="Factor not found")


# ---- Single-factor evaluation endpoints ----

def _new_evaluation_task(req: EvaluationStartRequest) -> tuple[str, Dict[str, Any], Path, Path]:
    if req.mode not in {"unevaluated", "all", "specified"}:
        raise HTTPException(status_code=400, detail="mode must be unevaluated, all, or specified")
    if req.mode == "specified" and not req.factorIds:
        raise HTTPException(status_code=400, detail="specified mode requires factorIds")
    library_path = _resolve_factor_library(req.factorJson)
    config_path = _resolve_evaluation_config(req.configPath)
    task_id = _gen_id()
    task = {
        "taskId": task_id,
        "status": "running",
        "type": "evaluation",
        "config": {**req.model_dump(), "factorJson": library_path.name, "configPath": str(config_path)},
        "progress": {
            "phase": "evaluating",
            "currentRound": 0,
            "totalRounds": 0,
            "progress": 0,
            "message": "正在准备单因子 OTO 评估...",
            "timestamp": _now(),
        },
        "logs": [],
        "metrics": {},
        "result": None,
        "pid": None,
        "createdAt": _now(),
        "updatedAt": _now(),
    }
    tasks[task_id] = task
    return task_id, task, library_path, config_path


@app.post("/api/v1/evaluations/start", response_model=ApiResponse)
async def start_evaluation(req: EvaluationStartRequest):
    task_id, task, library_path, config_path = _new_evaluation_task(req)
    asyncio.create_task(_run_evaluation(task_id, req, library_path, config_path))
    return ApiResponse(success=True, data={"taskId": task_id, "task": task}, message="因子评估已启动")


@app.get("/api/v1/evaluations/{task_id}", response_model=ApiResponse)
async def get_evaluation_status(task_id: str):
    if task_id not in tasks or tasks[task_id].get("type") != "evaluation":
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    return ApiResponse(success=True, data={"task": tasks[task_id]})


async def _cancel_evaluation_task(task_id: str) -> ApiResponse:
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    if task.get("pid"):
        try:
            os.kill(task["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    task["status"] = "cancelled"
    task["updatedAt"] = _now()
    task["progress"]["message"] = "评估已取消"
    await _broadcast(task_id, {
        "type": "result",
        "taskId": task_id,
        "data": {"status": "cancelled"},
        "timestamp": _now(),
    })
    return ApiResponse(success=True, message="因子评估已取消")


@app.delete("/api/v1/evaluations/{task_id}", response_model=ApiResponse)
async def cancel_evaluation(task_id: str):
    return await _cancel_evaluation_task(task_id)


async def _run_evaluation(
    task_id: str,
    req: EvaluationStartRequest,
    library_path: Path,
    config_path: Path,
):
    task = tasks[task_id]
    try:
        env = os.environ.copy()
        env.update(_load_dotenv_dict())
        venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
        python_bin = str(venv_python if venv_python.exists() else Path(sys.executable))
        mode = "unevaluated" if req.mode == "specified" else req.mode
        cmd = [
            python_bin,
            "-m",
            "quantaalpha.evaluation.cli",
            "evaluate-library",
            "--library",
            str(library_path),
            "--mode",
            mode,
            "--config",
            str(config_path),
        ]
        for factor_id in req.factorIds or []:
            cmd.extend(["--factor-id", factor_id])
        if req.refreshMarketCache:
            cmd.append("--refresh-market-cache")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        task["pid"] = proc.pid
        assert proc.stdout is not None
        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = None
            if isinstance(event, dict) and event.get("type") == "progress":
                current = int(event.get("current", event.get("completed", 0)) or 0)
                total = int(event.get("total", 0) or 0)
                status = event.get("status")
                factor_name = event.get("factor_name") or event.get("factor_id") or "因子"
                task["progress"].update({
                    "currentRound": current,
                    "totalRounds": total,
                    "progress": round((current / total) * 100) if total else 0,
                    "message": f"{factor_name}: {status or '评估中'}",
                    "factorId": event.get("factor_id"),
                    "timestamp": _now(),
                })
                task["metrics"].update({
                    "totalFactors": total,
                    "completedFactors": int(event.get("completed", max(0, current - 1)) or 0),
                    "passedFactors": int(event.get("passed", 0) or 0),
                    "failedFactors": int(event.get("failed", 0) or 0),
                })
                await _broadcast(task_id, {"type": "progress", "taskId": task_id, "data": task["progress"], "timestamp": _now()})
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                task["result"] = event
                task["metrics"].update(event.get("summary") or {})
                task["dedupReport"] = event.get("dedup_report")
                continue

            log_entry = {
                "id": _gen_id(),
                "timestamp": _now(),
                "level": "error" if "error" in line.lower() else "info",
                "message": line[:500],
            }
            task["logs"].append(log_entry)
            await _broadcast(task_id, {"type": "log", "taskId": task_id, "data": log_entry, "timestamp": _now()})

        exit_code = await proc.wait()
        task["pid"] = None
        if task.get("status") == "cancelled":
            return
        task["status"] = "completed" if exit_code == 0 else "failed"
        task["updatedAt"] = _now()
        task["progress"].update({
            "phase": "completed" if exit_code == 0 else "failed",
            "progress": 100 if exit_code == 0 else task["progress"].get("progress", 0),
            "message": "因子评估完成" if exit_code == 0 else f"因子评估失败 (exit code: {exit_code})",
            "timestamp": _now(),
        })
        await _broadcast(task_id, {
            "type": "result",
            "taskId": task_id,
            "data": {"status": task["status"], "metrics": task["metrics"], "result": task.get("result")},
            "timestamp": _now(),
        })
    except Exception as exc:
        task["status"] = "failed"
        task["pid"] = None
        task["updatedAt"] = _now()
        task["progress"]["message"] = str(exc)
        await _broadcast(task_id, {"type": "error", "taskId": task_id, "data": {"error": str(exc)}, "timestamp": _now()})


# ---- Backtest compatibility endpoints ----

@app.post("/api/v1/backtest/start", response_model=ApiResponse)
async def start_backtest(req: BacktestStartRequest):
    """Compatibility alias; combined multi-factor evaluation is intentionally removed."""
    if req.factorSource == "combined":
        raise HTTPException(status_code=400, detail="combined 模式已停用；evaluation_v2 只逐个评估单因子")
    evaluation_req = EvaluationStartRequest(
        factorJson=req.factorJson,
        mode="all",
        configPath=req.configPath,
    )
    task_id, task, library_path, config_path = _new_evaluation_task(evaluation_req)
    asyncio.create_task(_run_evaluation(task_id, evaluation_req, library_path, config_path))
    return ApiResponse(
        success=True,
        data={"taskId": task_id, "task": task},
        message="已通过兼容入口启动单因子 OTO 评估",
    )


@app.get("/api/v1/backtest/{task_id}", response_model=ApiResponse)
async def get_backtest_status(task_id: str):
    """Get backtest task status and results."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return ApiResponse(success=True, data={"task": tasks[task_id]})


@app.delete("/api/v1/backtest/{task_id}", response_model=ApiResponse)
async def cancel_backtest(task_id: str):
    return await _cancel_evaluation_task(task_id)


async def _run_backtest(task_id: str, req: BacktestStartRequest, config_path: str):
    """Disabled legacy implementation retained only for old task-state compatibility."""
    raise RuntimeError("Legacy Qlib backtest execution is disabled; use /api/v1/evaluations/start")
    task = tasks[task_id]
    try:
        env = os.environ.copy()
        dotenv = _load_dotenv_dict()
        env.update(dotenv)

        # --- Resolve factor JSON path ---
        # Frontend sends just the filename (e.g. "all_factors_library_test3hjback.json")
        # We need to resolve it to the full path under data/factorlib/
        factor_json_input = req.factorJson
        factor_json_path = Path(factor_json_input)
        if not factor_json_path.is_absolute():
            # Check data/factorlib/ first
            candidate = PROJECT_ROOT / "data" / "factorlib" / factor_json_input
            if candidate.exists():
                factor_json_path = candidate
            else:
                # Try as relative to project root
                candidate2 = PROJECT_ROOT / factor_json_input
                if candidate2.exists():
                    factor_json_path = candidate2
                else:
                    factor_json_path = candidate  # will fail with a clear error message
        factor_json_str = str(factor_json_path)

        # --- Find the correct Python executable ---
        # Legacy environment discovery retained for old serialized task compatibility.
        conda_env = dotenv.get("CONDA_ENV_NAME", "quantaalpha")
        python_bin = sys.executable  # fallback

        # Dynamically detect conda base path (portable, no hardcoded paths)
        conda_prefixes = [os.path.expanduser(f"~/.conda/envs/{conda_env}")]
        try:
            import subprocess as _sp
            conda_base = _sp.check_output(
                ["conda", "info", "--base"], text=True, timeout=5
            ).strip()
            conda_prefixes.insert(0, os.path.join(conda_base, "envs", conda_env))
        except Exception:
            pass
        # Also check CONDA_PREFIX if we're already in the right env
        if os.environ.get("CONDA_PREFIX"):
            conda_prefixes.insert(0, os.environ["CONDA_PREFIX"])

        for prefix in conda_prefixes:
            candidate_bin = Path(prefix) / "bin" / "python"
            if candidate_bin.exists():
                python_bin = str(candidate_bin)
                break

        # Build CLI command
        cmd = [python_bin, "-c", "raise RuntimeError('legacy backtest disabled')"]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        task["pid"] = proc.pid

        # Noisy warnings from Qlib / dependencies that can be safely suppressed
        _NOISY_PATTERNS = (
            "field data contains nan",
            "common_infra",
            "PyTorch models are skipped",
            "UserWarning: pkg_resources",
            "Training until validation scores",
            "FutureWarning",
            "UserWarning",
            "Did not meet early stopping",
            "num_leaves is set=",
        )

        # --- Stream stdout ---
        log_entry = None
        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue

            # Skip noisy repeated warnings
            if any(p in line for p in _NOISY_PATTERNS):
                continue

            level = "info"
            if "ERROR" in line or "Error" in line:
                level = "error"
            elif "WARNING" in line or "Warning" in line:
                level = "warning"
            elif "完成" in line or "success" in line.lower() or "✓" in line:
                level = "success"

            log_entry = {
                "id": _gen_id(),
                "timestamp": _now(),
                "level": level,
                "message": line[:500],
            }
            task["logs"].append(log_entry)
            if len(task["logs"]) > 2000:
                task["logs"] = task["logs"][-2000:]

            # Broadcast log to WebSocket
            await _broadcast(task_id, {
                "type": "log",
                "taskId": task_id,
                "data": log_entry,
                "timestamp": _now(),
            })

            # Update progress for meaningful lines
            if any(kw in line for kw in ["因子", "回测", "模型", "训练", "完成", "加载",
                                          "[1/4]", "[2/4]", "[3/4]", "[4/4]", "结果"]):
                task["progress"]["message"] = line[:200]

                # Estimate progress from run_backtest step markers
                if "[1/4]" in line:
                    task["progress"]["progress"] = 15
                elif "[2/4]" in line:
                    task["progress"]["progress"] = 35
                elif "[3/4]" in line:
                    task["progress"]["progress"] = 55
                elif "[4/4]" in line:
                    task["progress"]["progress"] = 75
                elif "结果已保存" in line or "回测结果" in line:
                    task["progress"]["progress"] = 95

                task["progress"]["timestamp"] = _now()
                await _broadcast(task_id, {
                    "type": "progress",
                    "taskId": task_id,
                    "data": task["progress"],
                    "timestamp": _now(),
                })

        # --- Process exit ---
        exit_code = await proc.wait()
        task["pid"] = None
        task["status"] = "completed" if exit_code == 0 else "failed"
        task["updatedAt"] = _now()

        # Try to load backtest results from output metrics JSON
        if exit_code == 0:
            task["progress"]["phase"] = "completed"
            task["progress"]["progress"] = 100
            task["progress"]["message"] = "回测完成"
            _load_backtest_results(task)
        else:
            task["progress"]["message"] = f"回测失败 (exit code: {exit_code})"

        await _broadcast(task_id, {
            "type": "result",
            "taskId": task_id,
            "data": {
                "status": task["status"],
                "metrics": task.get("metrics", {}),
            },
            "timestamp": _now(),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        task["status"] = "failed"
        task["progress"]["message"] = str(e)
        task["updatedAt"] = _now()
        await _broadcast(task_id, {
            "type": "error",
            "taskId": task_id,
            "data": {"error": str(e)},
            "timestamp": _now(),
        })


def _load_backtest_results(task: Dict[str, Any]):
    """Try to load backtest result metrics from the output directory."""
    try:
        config_path = task.get("config", {}).get("configPath") or str(
            PROJECT_ROOT / "configs" / "backtest.yaml"
        )
        with open(config_path, "r") as f:
            bt_config = yaml.safe_load(f)
        output_dir_raw = bt_config.get("experiment", {}).get(
            "output_dir", "data/results/backtest_v2_results"
        )
        # Resolve relative output_dir against PROJECT_ROOT (run_backtest runs with cwd=PROJECT_ROOT)
        output_dir = Path(output_dir_raw)
        if not output_dir.is_absolute():
            output_dir = PROJECT_ROOT / output_dir
        output_dir_str = str(output_dir)

        # Look for most recent metrics JSON
        metrics_files = sorted(
            glob.glob(os.path.join(output_dir_str, "*_backtest_metrics.json")),
            key=os.path.getmtime, reverse=True,
        )
        if metrics_files:
            with open(metrics_files[0], "r") as f:
                metrics_data = json.load(f)
            # The JSON has a nested structure: { metrics: {...}, config: {...}, ... }
            # Flatten: put the inner metrics dict at the top level for the frontend,
            # but also keep meta fields like experiment_name and elapsed_seconds.
            inner_metrics = metrics_data.get("metrics", {})
            flat = {**inner_metrics}
            # Carry over useful metadata
            for key in ("experiment_name", "factor_source", "num_factors",
                        "config", "elapsed_seconds"):
                if key in metrics_data:
                    flat[f"__{key}"] = metrics_data[key]
            
            # Load cumulative excess return data from CSV
            csv_path = metrics_files[0].replace("_backtest_metrics.json", "_cumulative_excess.csv")
            if os.path.exists(csv_path):
                import pandas as pd
                df = pd.read_csv(csv_path)
                if 'date' in df.columns and 'cumulative_excess_return' in df.columns:
                    cumulative_data = df[['date', 'cumulative_excess_return']].to_dict('records')
                    flat["cumulative_curve"] = [
                        {"date": r["date"], "value": r["cumulative_excess_return"]} 
                        for r in cumulative_data
                    ]

            task["metrics"] = flat
    except Exception as e:
        import traceback
        traceback.print_exc()  # print for debugging, but don't crash


# ---- Evaluation configuration and deduplication endpoints ----

def _evaluation_config_for_frontend() -> Dict[str, Any]:
    config = _load_yaml_dict(EVALUATION_CONFIG_PATH)
    periods = config.get("periods") or {}
    metrics = config.get("metrics") or {}
    portfolio = config.get("portfolio") or {}
    schedule = (config.get("costs") or {}).get("schedule") or []
    training = periods.get("training") or ["2023-01-01", "2025-06-30"]
    validation = periods.get("validation") or ["2025-07-01", "2025-12-31"]
    return {
        "trainingStart": str(training[0]),
        "trainingEnd": str(training[1]),
        "validationStart": str(validation[0]),
        "validationEnd": str(validation[1]),
        "icThreshold": metrics.get("ic_threshold", 0.03),
        "icirThreshold": metrics.get("icir_threshold", 0.5),
        "spreadThreshold": metrics.get("spread_threshold", 0.30),
        "excessSharpeThreshold": metrics.get("excess_sharpe_threshold", 1.0),
        "groupCount": metrics.get("group_count", 10),
        "rebalancePeriodDays": portfolio.get("rebalance_period_days", 3),
        "feeThrough2023": schedule[0].get("rate", 0.0007) if schedule else 0.0007,
        "feeFrom2024": schedule[1].get("rate", 0.00035) if len(schedule) > 1 else 0.00035,
        "oosStatus": periods.get("oos_status", "sealed"),
        "engine": (config.get("engine") or {}).get("name", "oto_single_factor_v1"),
    }


def _tactical_config_for_frontend() -> Dict[str, Any]:
    from quantaalpha.evaluation.tactical import DEFAULT_TACTICAL_CONFIG

    raw = _load_yaml_dict(TACTICAL_CONFIG_PATH)
    config = dict(DEFAULT_TACTICAL_CONFIG)
    for key in DEFAULT_TACTICAL_CONFIG:
        if key in raw:
            config[key] = raw[key]
    return config


def _default_tactical_config_for_frontend() -> Dict[str, Any]:
    from quantaalpha.evaluation.tactical import DEFAULT_TACTICAL_CONFIG

    return dict(DEFAULT_TACTICAL_CONFIG)


def _resolve_tactical_artifact(path: str) -> Path:
    artifact = Path(path).expanduser()
    if not artifact.is_absolute():
        artifact = PROJECT_ROOT / artifact
    artifact = artifact.resolve()
    output_root = (PROJECT_ROOT / "data" / "results" / "factor_evaluations").resolve()
    if output_root not in artifact.parents or not artifact.exists() or artifact.suffix.lower() != ".csv":
        raise HTTPException(status_code=404, detail="Tactical artifact not found")
    return artifact


def _resolve_tactical_h5_artifact(path: str) -> Path:
    artifact = Path(path).expanduser()
    if not artifact.is_absolute():
        artifact = PROJECT_ROOT / artifact
    artifact = artifact.resolve()
    output_root = (PROJECT_ROOT / "data" / "results" / "factor_evaluations").resolve()
    if output_root not in artifact.parents or not artifact.exists() or artifact.suffix.lower() not in {".h5", ".hdf", ".hdf5"}:
        raise HTTPException(status_code=404, detail="Tactical factor value artifact not found")
    return artifact


def _read_tactical_excess_artifact(path: str):
    import pandas as pd

    artifact = _resolve_tactical_artifact(path)
    frame = pd.read_csv(artifact)
    if "excess_return" not in frame.columns:
        raise ValueError("CSV 缺少 excess_return 列")
    if "date" not in frame.columns and len(frame.columns):
        first = str(frame.columns[0])
        if first.lower().startswith("unnamed") or first == "":
            frame = frame.rename(columns={frame.columns[0]: "date"})
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["excess_return"] = pd.to_numeric(frame["excess_return"], errors="coerce")
    return frame


def _read_tactical_factor_values(path: str):
    import pandas as pd

    artifact = _resolve_tactical_h5_artifact(path)
    return pd.read_hdf(artifact)


def _build_tactical_records(library_path: Path) -> List[Dict[str, Any]]:
    raw = _load_factor_library(str(library_path))
    factors = raw.get("factors", {})
    records: List[Dict[str, Any]] = []
    for factor_id, factor_info in factors.items():
        if not isinstance(factor_info, dict):
            continue
        evaluation = factor_info.get("evaluation_v2") or {}
        artifacts = evaluation.get("artifacts") or {}
        record: Dict[str, Any] = {
            "factorId": factor_info.get("factor_id", factor_id),
            "factorName": factor_info.get("factor_name", factor_id),
            "factorExpression": factor_info.get("factor_expression", ""),
            "factorDescription": factor_info.get("factor_description", ""),
            "evaluationStatus": evaluation.get("status", "not_evaluated"),
        }
        training_path = artifacts.get("training_excess_returns")
        if not evaluation or evaluation.get("status") in {"not_evaluated", "running"}:
            record["skipReason"] = "因子尚未完成 evaluation_v2 评估"
            records.append(record)
            continue
        if not training_path:
            record["skipReason"] = "缺少训练期超额收益产物"
            records.append(record)
            continue
        try:
            record["training_excess"] = _read_tactical_excess_artifact(str(training_path))
        except Exception as exc:
            record["skipReason"] = f"训练期产物不可读：{exc}"
            records.append(record)
            continue
        validation_path = artifacts.get("validation_excess_returns")
        if validation_path:
            try:
                record["validation_excess"] = _read_tactical_excess_artifact(str(validation_path))
            except Exception:
                record["validation_excess"] = None
        records.append(record)
    return records


def _build_tactical_group_records(library_path: Path, factor_ids: List[str]) -> List[Dict[str, Any]]:
    raw = _load_factor_library(str(library_path))
    factors = raw.get("factors", {})
    missing = [factor_id for factor_id in factor_ids if factor_id not in factors]
    if missing:
        raise HTTPException(status_code=404, detail=f"Factor IDs not found in library: {', '.join(missing)}")

    records: List[Dict[str, Any]] = []
    for factor_id in factor_ids:
        factor_info = factors[factor_id]
        if not isinstance(factor_info, dict):
            raise HTTPException(status_code=400, detail=f"Invalid factor entry: {factor_id}")
        evaluation = factor_info.get("evaluation_v2") or {}
        artifacts = evaluation.get("artifacts") or {}
        h5_path = (factor_info.get("cache_location") or {}).get("result_h5_path")
        if not h5_path:
            raise HTTPException(status_code=400, detail=f"因子 {factor_id} 缺少 result.h5 因子值")
        record: Dict[str, Any] = {
            "factorId": factor_info.get("factor_id", factor_id),
            "factorName": factor_info.get("factor_name", factor_id),
            "factorExpression": factor_info.get("factor_expression", ""),
            "directionMultiplier": evaluation.get("direction_multiplier", 1),
            "factor_values": _read_tactical_factor_values(str(h5_path)),
        }
        training_path = artifacts.get("training_excess_returns")
        if training_path:
            record["training_excess"] = _read_tactical_excess_artifact(str(training_path))
        validation_path = artifacts.get("validation_excess_returns")
        if validation_path:
            try:
                record["validation_excess"] = _read_tactical_excess_artifact(str(validation_path))
            except Exception:
                record["validation_excess"] = None
        records.append(record)
    return records


def _tactical_group_test_key(library_name: str, factor_ids: List[str]) -> str:
    payload = json.dumps(
        {"library": Path(library_name).name, "factorIds": sorted(str(factor_id) for factor_id in factor_ids)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _tactical_group_test_path(library_name: str, factor_ids: List[str]) -> Path:
    key = _tactical_group_test_key(library_name, factor_ids)
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in Path(library_name).stem)
    return TACTICAL_GROUP_TEST_DIR / f"{safe_stem}_{key}.json"


def _summarize_tactical_group_test(payload: Dict[str, Any]) -> Dict[str, Any]:
    result = payload.get("result") or {}
    strategy = result.get("strategy") or {}
    training = strategy.get("training") or {}
    validation = strategy.get("validation") or {}
    value_corr = result.get("factorValueCorrelation") or {}
    group_metrics = result.get("groupMetrics") or payload.get("groupMetrics") or {}
    training_deltas = (training.get("comparison") or {}).get("deltas") or {}
    validation_deltas = (validation.get("comparison") or {}).get("deltas") or {}
    return {
        "key": payload.get("key"),
        "library": payload.get("library"),
        "factorIds": result.get("factorIds") or payload.get("factorIds") or [],
        "factorNames": result.get("factorNames") or [],
        "savedAt": payload.get("savedAt"),
        "updatedAt": payload.get("updatedAt"),
        "groupMetrics": group_metrics,
        "averageCorrelation": group_metrics.get("averageCorrelation"),
        "minPairCorrelation": group_metrics.get("minPairCorrelation"),
        "minOverlapDays": group_metrics.get("minOverlapDays"),
        "averagePearson": value_corr.get("averagePearson"),
        "averageSpearman": value_corr.get("averageSpearman"),
        "trainingTotalExcess": (training.get("metrics") or {}).get("total_excess"),
        "validationTotalExcess": (validation.get("metrics") or {}).get("total_excess"),
        "trainingTotalExcessDelta": training_deltas.get("total_excess"),
        "trainingMeanMonthlyExcessDelta": training_deltas.get("mean_monthly_excess"),
        "trainingDrawdownDelta": training_deltas.get("max_monthly_drawdown"),
        "trainingSharpeDelta": training_deltas.get("excess_sharpe"),
        "validationTotalExcessDelta": validation_deltas.get("total_excess"),
        "validationMeanMonthlyExcessDelta": validation_deltas.get("mean_monthly_excess"),
        "validationDrawdownDelta": validation_deltas.get("max_monthly_drawdown"),
        "validationSharpeDelta": validation_deltas.get("excess_sharpe"),
    }


def _read_tactical_group_test(library_name: str, factor_ids: List[str]) -> Optional[Dict[str, Any]]:
    path = _tactical_group_test_path(library_name, factor_ids)
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        return None
    return payload


def _save_tactical_group_test(
    library_name: str,
    factor_ids: List[str],
    result: Dict[str, Any],
    group_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    key = _tactical_group_test_key(library_name, factor_ids)
    existing = _read_tactical_group_test(library_name, factor_ids) or {}
    if group_metrics:
        result["groupMetrics"] = {key: value for key, value in group_metrics.items() if value is not None}
    payload = {
        "key": key,
        "library": Path(library_name).name,
        "factorIds": sorted(str(factor_id) for factor_id in factor_ids),
        "groupMetrics": result.get("groupMetrics") or existing.get("groupMetrics") or {},
        "savedAt": existing.get("savedAt") or now,
        "updatedAt": now,
        "result": result,
    }
    _write_json_file(_tactical_group_test_path(library_name, factor_ids), payload)
    return payload


def _tactical_group_metrics_from_request(req: TacticalGroupTestRequest) -> Dict[str, Any]:
    return {
        "averageCorrelation": req.averageCorrelation,
        "minPairCorrelation": req.minPairCorrelation,
        "minOverlapDays": req.minOverlapDays,
    }


def _list_tactical_group_tests(library_name: str) -> List[Dict[str, Any]]:
    library = Path(library_name).name
    if not TACTICAL_GROUP_TEST_DIR.exists():
        return []
    items: List[Dict[str, Any]] = []
    for path in TACTICAL_GROUP_TEST_DIR.glob("*.json"):
        payload = _read_json_file(path)
        if not isinstance(payload, dict) or payload.get("library") != library:
            continue
        items.append(_summarize_tactical_group_test(payload))
    return sorted(items, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


@app.get("/api/v1/evaluation/config", response_model=ApiResponse)
async def get_evaluation_config():
    return ApiResponse(success=True, data={"config": _evaluation_config_for_frontend()})


@app.get("/api/v1/tactical/config", response_model=ApiResponse)
async def get_tactical_config():
    return ApiResponse(
        success=True,
        data={
            "config": _tactical_config_for_frontend(),
            "defaults": _default_tactical_config_for_frontend(),
        },
    )


@app.put("/api/v1/tactical/config", response_model=ApiResponse)
async def update_tactical_config(update: TacticalConfigUpdate):
    values = {key: value for key, value in update.model_dump().items() if value is not None}
    config = _tactical_config_for_frontend()
    config.update(values)
    _write_yaml_dict(TACTICAL_CONFIG_PATH, config)
    return ApiResponse(success=True, data={"config": _tactical_config_for_frontend()}, message="战术因子配置已保存")


@app.post("/api/v1/tactical/analyze", response_model=ApiResponse)
async def analyze_tactical_factors(req: TacticalAnalyzeRequest):
    from quantaalpha.evaluation.tactical import TacticalFactorAnalyzer

    library_path = _resolve_factor_library(req.library)
    config = _tactical_config_for_frontend()
    records = _build_tactical_records(library_path)
    result = TacticalFactorAnalyzer(config).analyze_factors(records)
    result["library"] = library_path.name
    return ApiResponse(success=True, data=result)


@app.get("/api/v1/tactical/group-tests", response_model=ApiResponse)
async def list_tactical_factor_group_tests(library: str = Query(..., description="Factor library JSON filename")):
    library_path = _resolve_factor_library(library)
    return ApiResponse(success=True, data={"tests": _list_tactical_group_tests(library_path.name)})


@app.post("/api/v1/tactical/group-test/saved", response_model=ApiResponse)
async def get_saved_tactical_factor_group_test(req: TacticalGroupTestRequest):
    library_path = _resolve_factor_library(req.library)
    payload = _read_tactical_group_test(library_path.name, req.factorIds)
    if not payload:
        raise HTTPException(status_code=404, detail="Saved tactical group test not found")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Saved tactical group test is corrupted")
    result["library"] = library_path.name
    result["saved"] = True
    result["savedAt"] = payload.get("savedAt")
    result["updatedAt"] = payload.get("updatedAt")
    if "groupMetrics" not in result and payload.get("groupMetrics"):
        result["groupMetrics"] = payload.get("groupMetrics")
    return ApiResponse(success=True, data=result)


@app.post("/api/v1/tactical/group-test", response_model=ApiResponse)
async def test_tactical_factor_group(req: TacticalGroupTestRequest):
    from quantaalpha.evaluation.tactical import TacticalFactorAnalyzer

    library_path = _resolve_factor_library(req.library)
    config = _tactical_config_for_frontend()
    if not req.refresh:
        payload = _read_tactical_group_test(library_path.name, req.factorIds)
        if payload and isinstance(payload.get("result"), dict):
            result = payload["result"]
            request_metrics = {key: value for key, value in _tactical_group_metrics_from_request(req).items() if value is not None}
            if request_metrics:
                result["groupMetrics"] = {**(result.get("groupMetrics") or payload.get("groupMetrics") or {}), **request_metrics}
                payload = _save_tactical_group_test(library_path.name, req.factorIds, result, result["groupMetrics"])
            result["library"] = library_path.name
            result["saved"] = True
            result["savedAt"] = payload.get("savedAt")
            result["updatedAt"] = payload.get("updatedAt")
            if "groupMetrics" not in result and payload.get("groupMetrics"):
                result["groupMetrics"] = payload.get("groupMetrics")
            return ApiResponse(success=True, data=result, message="已读取保存的组合测试结果")
    try:
        records = _build_tactical_group_records(library_path, req.factorIds)
        result = TacticalFactorAnalyzer(config).test_factor_group(records)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"组合进一步测试失败：{exc}") from exc
    result["library"] = library_path.name
    payload = _save_tactical_group_test(library_path.name, req.factorIds, result, _tactical_group_metrics_from_request(req))
    result["saved"] = True
    result["savedAt"] = payload.get("savedAt")
    result["updatedAt"] = payload.get("updatedAt")
    return ApiResponse(success=True, data=result)


@app.get("/api/v1/evaluation/artifact", response_model=ApiResponse)
async def get_evaluation_artifact(path: str = Query(..., description="Artifact path returned by evaluation_v2")):
    artifact = Path(path).expanduser()
    if not artifact.is_absolute():
        artifact = PROJECT_ROOT / artifact
    artifact = artifact.resolve()
    output_root = (PROJECT_ROOT / "data" / "results" / "factor_evaluations").resolve()
    if output_root not in artifact.parents or not artifact.exists() or artifact.suffix.lower() != ".csv":
        raise HTTPException(status_code=404, detail="Evaluation artifact not found")
    with artifact.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return ApiResponse(success=True, data={"rows": rows, "name": artifact.name})


@app.put("/api/v1/evaluation/config", response_model=ApiResponse)
async def update_evaluation_config(update: EvaluationConfigUpdate):
    values = {key: value for key, value in update.model_dump().items() if value is not None}
    config = _load_yaml_dict(EVALUATION_CONFIG_PATH)
    periods = config.setdefault("periods", {})
    metrics = config.setdefault("metrics", {})
    portfolio = config.setdefault("portfolio", {})
    costs = config.setdefault("costs", {})
    schedule = costs.setdefault("schedule", [
        {"end_date": "2023-12-31", "rate": 0.0007},
        {"end_date": "9999-12-31", "rate": 0.00035},
    ])

    current_training = periods.get("training") or ["2023-01-01", "2025-06-30"]
    current_validation = periods.get("validation") or ["2025-07-01", "2025-12-31"]
    periods["training"] = [values.get("trainingStart", current_training[0]), values.get("trainingEnd", current_training[1])]
    periods["validation"] = [values.get("validationStart", current_validation[0]), values.get("validationEnd", current_validation[1])]
    metric_fields = {
        "icThreshold": "ic_threshold",
        "icirThreshold": "icir_threshold",
        "spreadThreshold": "spread_threshold",
        "excessSharpeThreshold": "excess_sharpe_threshold",
        "groupCount": "group_count",
    }
    for api_key, yaml_key in metric_fields.items():
        if api_key in values:
            metrics[yaml_key] = values[api_key]
    if "rebalancePeriodDays" in values:
        portfolio["rebalance_period_days"] = values["rebalancePeriodDays"]
    if "feeThrough2023" in values:
        schedule[0]["rate"] = values["feeThrough2023"]
    if "feeFrom2024" in values:
        while len(schedule) < 2:
            schedule.append({"end_date": "9999-12-31", "rate": 0.00035})
        schedule[1]["rate"] = values["feeFrom2024"]
    _write_yaml_dict(EVALUATION_CONFIG_PATH, config)
    return ApiResponse(success=True, data={"config": _evaluation_config_for_frontend()}, message="评估配置已保存")


@app.get("/api/v1/dedup/reports", response_model=ApiResponse)
async def list_dedup_reports():
    reports = []
    if DEDUP_REPORT_DIR.exists():
        for path in sorted(DEDUP_REPORT_DIR.glob("dedup_*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
                reports.append({
                    "reportId": report.get("report_id"),
                    "status": report.get("status"),
                    "createdAt": report.get("created_at"),
                    "library": Path(report.get("library_path", "")).name,
                    "clusterCount": len(report.get("clusters") or []),
                    "pairCount": len(report.get("pairs") or []),
                })
            except Exception:
                continue
    return ApiResponse(success=True, data={"reports": reports})


@app.post("/api/v1/dedup/reports", response_model=ApiResponse)
async def generate_dedup_report(req: DedupGenerateRequest):
    from quantaalpha.evaluation.config import load_evaluation_config
    from quantaalpha.evaluation.dedup import DeduplicationService

    library_path = _resolve_factor_library(req.factorJson)
    config = load_evaluation_config(_resolve_evaluation_config(req.configPath))
    report = await asyncio.to_thread(DeduplicationService(config).generate_report, library_path)
    return ApiResponse(success=True, data={"report": report}, message="重复因子报告已生成，等待人工确认")


def _resolve_dedup_report(report_id: str) -> Path:
    if not report_id.startswith("dedup_") or "/" in report_id or "\\" in report_id:
        raise HTTPException(status_code=400, detail="Invalid report ID")
    path = (DEDUP_REPORT_DIR / f"{report_id}.json").resolve()
    if not path.exists() or DEDUP_REPORT_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="Deduplication report not found")
    return path


@app.get("/api/v1/dedup/reports/{report_id}", response_model=ApiResponse)
async def get_dedup_report(report_id: str):
    report = json.loads(_resolve_dedup_report(report_id).read_text(encoding="utf-8"))
    return ApiResponse(success=True, data={"report": report})


@app.post("/api/v1/dedup/reports/{report_id}/archive", response_model=ApiResponse)
async def archive_duplicate_factors(report_id: str, req: DedupArchiveRequest):
    from quantaalpha.evaluation.dedup import DeduplicationService

    report_path = _resolve_dedup_report(report_id)
    result = await asyncio.to_thread(DeduplicationService().archive_confirmed, report_path, req.factorIds)
    return ApiResponse(success=True, data=result, message="重复因子已归档，原始记录和缓存均已保留")


# ---- System config endpoints ----

@app.get("/api/v1/system/config", response_model=ApiResponse)
async def get_system_config():
    """Read current system configuration from .env and experiment.yaml."""
    dotenv = _load_dotenv_dict()

    # Read experiment.yaml for display
    exp_yaml_content = ""
    if EXPERIMENT_CONFIG_PATH.exists():
        exp_yaml_content = EXPERIMENT_CONFIG_PATH.read_text(encoding="utf-8")

    # Mask API keys for security
    masked_env = {}
    for k, v in dotenv.items():
        if "KEY" in k.upper() and v:
            masked_env[k] = v[:8] + "..." + v[-4:] if len(v) > 12 else "***"
        else:
            masked_env[k] = v

    return ApiResponse(
        success=True,
        data={
            "env": masked_env,
            "experimentConfig": _get_experiment_defaults(dotenv),
            "experimentYaml": exp_yaml_content,
            "factorLibraries": [Path(p).name for p in _find_factor_jsons()],
        },
    )


@app.put("/api/v1/system/config", response_model=ApiResponse)
async def update_system_config(update: SystemConfigUpdate):
    """Update .env configuration and persisted YAML experiment defaults."""
    if not DOTENV_PATH.exists():
        DOTENV_PATH.write_text("", encoding="utf-8")

    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    env_keys = {
        "QLIB_DATA_DIR",
        "DATA_RESULTS_DIR",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "CHAT_MODEL",
        "REASONING_MODEL",
        "DEFAULT_LIBRARY_SUFFIX",
    }
    env_updates = {k: v for k, v in updates.items() if k in env_keys}
    yaml_updates = {k: v for k, v in updates.items() if k not in env_keys}

    import re
    if env_updates:
        content = DOTENV_PATH.read_text(encoding="utf-8")
        for key, val in env_updates.items():
            # Replace existing line or append
            pattern = rf"^{re.escape(key)}\s*=.*$"
            replacement = f"{key}={val}"
            new_content, n = re.subn(pattern, replacement, content, flags=re.MULTILINE)
            if n > 0:
                content = new_content
            else:
                content += f"\n{replacement}\n"
        DOTENV_PATH.write_text(content, encoding="utf-8")

    if yaml_updates:
        _apply_experiment_default_updates(yaml_updates)

    dotenv = _load_dotenv_dict()
    return ApiResponse(
        success=True,
        message="配置已更新",
        data={"experimentConfig": _get_experiment_defaults(dotenv)},
    )


# ---- WebSocket endpoint ----

@app.websocket("/ws/mining/{task_id}")
async def ws_mining(websocket: WebSocket, task_id: str):
    """WebSocket for real-time experiment updates."""
    await websocket.accept()

    if task_id not in ws_connections:
        ws_connections[task_id] = []
    ws_connections[task_id].append(websocket)

    # Send current state immediately
    if task_id in tasks:
        try:
            await websocket.send_json({
                "type": "progress",
                "taskId": task_id,
                "data": tasks[task_id].get("progress", {}),
                "timestamp": _now(),
            })
            # Send recent logs
            for log in tasks[task_id].get("logs", [])[-20:]:
                await websocket.send_json({
                    "type": "log",
                    "taskId": task_id,
                    "data": log,
                    "timestamp": _now(),
                })
        except Exception:
            pass

    try:
        while True:
            data = await websocket.receive_text()
            # Heartbeat
            if data == "ping":
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": _now(),
                })
    except WebSocketDisconnect:
        if task_id in ws_connections:
            try:
                ws_connections[task_id].remove(websocket)
            except ValueError:
                pass


# ========================== Entry Point ==========================

def _update_mining_metrics(task: Dict[str, Any]):
    """
    Update mining task metrics from the generated factor library.
    Calculates best factor stats and extracts top 10 factors.
    """
    jsons = _find_factor_jsons()
    # Prefer library with matching suffix if configured
    target_lib = None
    config = task.get("config", {})
    suffix = config.get("librarySuffix")
    
    if suffix:
        candidate = PROJECT_ROOT / "data" / "factorlib" / f"all_factors_library_{suffix}.json"
        # Fix: If suffix is specified, we ONLY look at this file.
        # If it doesn't exist yet, it means no factors have been mined yet for this task.
        if candidate.exists():
            target_lib = str(candidate)
        else:
            # Task specific file not found -> assume empty state
            return
            
    elif jsons:
        # No suffix provided, fallback to latest existing library (legacy behavior)
        target_lib = jsons[0]
        
    if not target_lib:
        return

    # Check modification time
    try:
        mtime = os.path.getmtime(target_lib)
        created_at_str = task.get("createdAt")
        if created_at_str:
            created_at_dt = datetime.fromisoformat(created_at_str)
            # Add a small buffer (e.g. 1 second) to avoid race conditions where file is created immediately
            if mtime < created_at_dt.timestamp():
                # File is older than the task -> ignore it
                return
    except Exception:
        pass

    try:
        lib = _load_factor_library(target_lib)
        factors = lib.get("factors", {})
        
        # 1. Update basic stats
        total = len(factors)
        task["metrics"]["totalFactors"] = total
        
        passed_count = failed_count = pending_count = 0
        factor_list = []
        
        for f_id, f_info in factors.items():
            # Check if this factor was created after task start
            # If we are using a shared library file (unlikely with new logic, but possible if user forces it),
            # we must ensure we don't display old factors.
            try:
                added_at_str = f_info.get("added_at", "")
                created_at_str = task.get("createdAt", "")
                if added_at_str and created_at_str:
                    # Parse timestamps
                    # added_at usually in isoformat
                    added_at_dt = datetime.fromisoformat(added_at_str)
                    created_at_dt = datetime.fromisoformat(created_at_str)
                    if added_at_dt < created_at_dt:
                        continue
            except Exception:
                pass # If date parsing fails, be permissive or conservative? Permissive for now.

            evaluation = f_info.get("evaluation_v2") or {}
            training = evaluation.get("training") or {}
            status = evaluation.get("status", "not_evaluated")
            if status == "passed":
                passed_count += 1
            elif status == "not_evaluated":
                pending_count += 1
            else:
                failed_count += 1
            factor_list.append({
                "factorName": f_info.get("factor_name", f_id),
                "factorExpression": f_info.get("factor_expression", ""),
                "evaluationStatus": status,
                "trainingPass": status == "passed",
                "rankIc": training.get("rank_ic") or 0,
                "rankIcir": training.get("rank_icir") or 0,
                "ic": training.get("ic") or 0,
                "icir": training.get("icir") or 0,
                "annualReturn": training.get("head_group_return_gross") or 0,
                "sharpeRatio": training.get("excess_sharpe") or 0,
                "longShortSpread": training.get("long_short_spread") or 0,
                "maxDrawdown": 0,
                "calmarRatio": 0,
                "cumulativeCurve": [],
            })

        task["metrics"]["highQualityFactors"] = passed_count
        task["metrics"]["mediumQualityFactors"] = pending_count
        task["metrics"]["lowQualityFactors"] = failed_count
        
        # 2. Find best factor
        if factor_list:
            factor_list.sort(
                key=lambda item: (
                    int(item["trainingPass"]),
                    item["sharpeRatio"],
                    abs(item["ic"]),
                    item["longShortSpread"],
                ),
                reverse=True,
            )
            best = factor_list[0]
            
            # Update task metrics with best factor's stats
            task["metrics"]["annualReturn"] = best["annualReturn"]
            task["metrics"]["rankIc"] = best["rankIc"]
            task["metrics"]["sharpeRatio"] = best["sharpeRatio"]
            task["metrics"]["maxDrawdown"] = best["maxDrawdown"]
            task["metrics"]["factorName"] = best["factorName"]
            
            # 3. Top 10 Factors
            task["metrics"]["top10Factors"] = factor_list[:10]
            
    except Exception:
        pass # Best effort

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
