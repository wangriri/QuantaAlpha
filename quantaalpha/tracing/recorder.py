from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def safe_id(text: Any, fallback: str = "unknown") -> str:
    value = str(text.value if hasattr(text, "value") else text if text is not None else fallback)
    value = value.strip().lower().replace(" ", "_")
    keep = []
    for ch in value:
        if ch.isalnum() or ch in {"_", "-"}:
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep).strip("_") or fallback


def to_jsonable(value: Any, max_string: int = 20000) -> Any:
    """Best-effort JSON serializer that preserves readable raw values."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > max_string:
            return value[:max_string] + f"...[truncated {len(value) - max_string} chars]"
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v, max_string=max_string) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v, max_string=max_string) for v in value]
    if is_dataclass(value):
        return to_jsonable(asdict(value), max_string=max_string)

    # pandas / numpy values
    if hasattr(value, "to_dict"):
        try:
            return to_jsonable(value.to_dict(), max_string=max_string)
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return to_jsonable(value.tolist(), max_string=max_string)
        except Exception:
            pass

    # Project objects: keep public scalar-ish attrs, then fall back to str.
    if hasattr(value, "__dict__"):
        try:
            public = {
                k: v
                for k, v in vars(value).items()
                if not k.startswith("_") and k not in {"trace", "scen", "knowledge_base"}
            }
            if public:
                public["__class__"] = value.__class__.__name__
                return to_jsonable(public, max_string=max_string)
        except Exception:
            pass

    return str(value)


class NullRunRecorder:
    enabled = False

    def __getattr__(self, name):
        def noop(*args, **kwargs):
            return None
        return noop


class RunRecorder:
    """Phase-1 file recorder for run / round / task / step trace artifacts."""

    schema_version = "1.0"

    def __init__(self, run_dir: str | Path, run_id: str | None = None, resume: bool = False):
        self.enabled = True
        self.run_dir = Path(run_dir)
        self.run_id = run_id or self.run_dir.name
        self.events_path = self.run_dir / "04_events.jsonl"
        self.graph_path = self.run_dir / "03_run_graph.json"
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if resume:
            self._load_graph()

    @classmethod
    def create(
        cls,
        project_root: str | Path,
        initial_direction: str | None,
        config_path: str | Path | None,
        run_cfg: dict[str, Any] | None,
        execution_context: dict[str, Any] | None = None,
    ) -> "RunRecorder":
        trace_root = Path(os.environ.get("QUANTAALPHA_TRACE_ROOT", Path(project_root) / "data" / "run_traces"))
        run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        recorder = cls(trace_root / run_id, run_id=run_id)
        recorder.write_run_start(
            initial_direction=initial_direction,
            config_path=config_path,
            run_cfg=run_cfg or {},
            execution_context=execution_context or {},
        )
        return recorder

    @classmethod
    def open(cls, run_dir: str | Path) -> "RunRecorder":
        run_dir = Path(run_dir)
        return cls(run_dir, run_id=run_dir.name, resume=True)

    def _load_graph(self) -> None:
        if self.graph_path.exists():
            try:
                data = json.loads(self.graph_path.read_text(encoding="utf-8"))
                self._nodes = {n["id"]: n for n in data.get("nodes", []) if "id" in n}
                self._edges = list(data.get("edges", []))
            except Exception:
                self._nodes = {}
                self._edges = []

    def write_json(self, rel_path: str | Path, payload: dict[str, Any]) -> Path:
        path = self.run_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_yaml(self, rel_path: str | Path, payload: dict[str, Any]) -> Path:
        path = self.run_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(to_jsonable(payload), allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path

    def append_event(self, event_type: str, **payload: Any) -> None:
        event = {
            "event_id": f"evt_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "type": event_type,
            "run_id": self.run_id,
            "time": now_iso(),
            **to_jsonable(payload),
        }
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.events_path.with_suffix(self.events_path.suffix + ".lock")
        with FileLock(str(lock_path)):
            with self.events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        path: str,
        status: str = "success",
        **extra: Any,
    ) -> None:
        self._nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "path": path,
            "status": status,
            **to_jsonable(extra),
        }
        self.append_event(
            "node_completed",
            node_id=node_id,
            node_type=node_type,
            label=label,
            path=path,
            status=status,
            **to_jsonable(extra),
        )

    def add_edge(self, source: str, target: str, edge_type: str) -> None:
        edge = {"from": source, "to": target, "type": edge_type}
        if edge not in self._edges:
            self._edges.append(edge)
            self.append_event("edge_created", from_node=source, to_node=target, edge_type=edge_type)

    def flush_graph(self, status: str = "running") -> None:
        graph = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": status,
            "updated_at": now_iso(),
            "nodes": list(self._nodes.values()),
            "edges": self._edges,
        }
        self.write_json("03_run_graph.json", graph)

    def rebuild_graph_from_events(self, status: str = "running") -> None:
        nodes: dict[str, dict[str, Any]] = dict(self._nodes)
        edges: list[dict[str, Any]] = list(self._edges)
        if self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if event.get("type") in {"node_created", "node_completed"} and event.get("node_id"):
                    node_id = event["node_id"]
                    nodes.setdefault(
                        node_id,
                        {
                            "id": node_id,
                            "type": event.get("node_type", "node"),
                            "label": event.get("label", node_id.split(".")[-1]),
                            "path": event.get("path", ""),
                            "status": event.get("status", "success"),
                        },
                    )
                    if event.get("label"):
                        nodes[node_id]["label"] = event.get("label")
                    if event.get("path"):
                        nodes[node_id]["path"] = event.get("path")
                    if event.get("status"):
                        nodes[node_id]["status"] = event.get("status")
                elif event.get("type") == "edge_created":
                    edge = {"from": event.get("from_node"), "to": event.get("to_node"), "type": event.get("edge_type")}
                    if edge.get("from") and edge.get("to") and edge not in edges:
                        edges.append(edge)
        self._nodes = nodes
        self._edges = edges
        self.flush_graph(status=status)

    def write_run_start(
        self,
        initial_direction: str | None,
        config_path: str | Path | None,
        run_cfg: dict[str, Any],
        execution_context: dict[str, Any],
    ) -> None:
        self.append_event("run_started", initial_direction=initial_direction)
        self.write_json(
            "01_user_input.json",
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "research_topic": initial_direction,
                "frontend_params": to_jsonable(execution_context),
                "submitted_by": "system",
                "submitted_at": now_iso(),
            },
        )
        self.write_yaml("02_config_snapshot.yaml", run_cfg)
        self.write_environment(config_path=config_path, run_cfg=run_cfg)
        self.write_json(
            "00_run_summary.json",
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "status": "running",
                "started_at": now_iso(),
                "research_topic": initial_direction,
                "config_path": str(config_path) if config_path else None,
                "artifacts": {
                    "run_graph": "03_run_graph.json",
                    "events": "04_events.jsonl",
                },
            },
        )

    def write_environment(self, config_path: str | Path | None, run_cfg: dict[str, Any]) -> None:
        git = {"commit": None, "branch": None, "dirty": None}
        try:
            root = Path(__file__).resolve().parents[2]
            git["commit"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
            git["branch"] = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
            git["dirty"] = bool(
                subprocess.check_output(["git", "status", "--short"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
            )
        except Exception:
            pass

        llm_cfg = {}
        try:
            from quantaalpha.llm.config import LLM_SETTINGS
            llm_cfg = {
                "provider": getattr(LLM_SETTINGS, "provider", None),
                "model": getattr(LLM_SETTINGS, "model", None),
                "api_base_alias": "configured",
            }
        except Exception:
            pass

        data_cfg = (run_cfg or {}).get("data", {}) if isinstance(run_cfg, dict) else {}
        self.write_json(
            "05_environment.json",
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "code": git,
                "runtime": {
                    "python_version": sys.version,
                    "platform": platform.platform(),
                },
                "config_path": str(config_path) if config_path else None,
                "data": to_jsonable(data_cfg),
                "llm": llm_cfg,
            },
        )

    def write_run_complete(self, status: str = "completed", error: str | None = None) -> None:
        summary_path = self.run_dir / "00_run_summary.json"
        summary = {}
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                summary = {}
        summary.update({"status": status, "ended_at": now_iso(), "error": error})
        self.write_json("00_run_summary.json", summary)
        self.append_event("run_completed", status=status, error=error)
        self.rebuild_graph_from_events(status=status)

    def write_planning_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        variables: dict[str, Any],
    ) -> None:
        rel = "00_planning/00_prompt.json"
        self.write_json(
            rel,
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "node_id": f"{self.run_id}.planning.prompt",
                "type": "llm_prompt",
                "actor": "PlanningAgent",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "prompt_variables": variables,
                "created_at": now_iso(),
            },
        )
        self.add_node(f"{self.run_id}.planning.prompt", "planning_prompt", "Planning Prompt", rel)

    def write_planning_output(self, trace: dict[str, Any]) -> None:
        rel = "00_planning/01_output.json"
        node_id = f"{self.run_id}.planning.output"
        self.write_json(
            rel,
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "node_id": node_id,
                "type": "planning_output",
                "status": "success" if trace.get("directions") else "failed",
                "raw": trace.get("raw", {}),
                "parsed": {
                    "ok": bool(trace.get("directions")),
                    "directions": [
                        {"direction_id": f"{self.run_id}.direction_{i:03d}", "index": i, "text": d}
                        for i, d in enumerate(trace.get("directions") or [])
                    ],
                },
                "parser": trace.get("parser", {}),
                "fallback_used": trace.get("fallback_used", False),
            },
        )
        self.add_node(node_id, "planning_output", "Planning Agent 输出方向", rel)
        for i, _ in enumerate(trace.get("directions") or []):
            direction_id = f"{self.run_id}.direction_{i:03d}"
            self.add_node(direction_id, "direction", f"Direction {i}", f"{rel}#parsed.directions[{i}]")
            self.add_edge(node_id, direction_id, "GENERATES_DIRECTION")

    def write_round_summary(self, round_idx: int, phase: str, tasks: list[dict[str, Any]] | None = None) -> None:
        rel = f"round_{round_idx:02d}_{safe_id(phase)}/00_round_summary.json"
        node_id = f"{self.run_id}.round_{round_idx:02d}"
        self.write_json(
            rel,
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "round_id": node_id,
                "round_idx": round_idx,
                "phase": phase,
                "tasks": to_jsonable(tasks or []),
                "updated_at": now_iso(),
            },
        )
        self.add_node(node_id, "round", f"Round {round_idx} {phase}", rel, phase=phase, round_idx=round_idx)

    def task_recorder(self, task: dict[str, Any], direction: str | None = None) -> "TaskRecorder":
        return TaskRecorder(self, task=task, direction=direction)


class TaskRecorder:
    """Writes per-task step files while preserving step-level separation."""

    def __init__(self, run: RunRecorder, task: dict[str, Any], direction: str | None = None):
        self.run = run
        self.task = task
        self.phase = safe_id(task.get("phase", "original"))
        self.round_idx = int(task.get("round_idx", 0))
        self.direction_id = int(task.get("direction_id", 0))
        self.task_index = int(task.get("task_index", self.direction_id))
        self.direction = direction
        suffix = f"direction_{self.direction_id:03d}" if self.phase == "original" else self.phase
        self.rel_dir = Path(f"round_{self.round_idx:02d}_{self.phase}") / f"task_{self.task_index:03d}_{self.phase}_{suffix}"
        self.task_id = f"{self.run.run_id}.round_{self.round_idx:02d}.task_{self.task_index:03d}"
        self._factor_ids: list[str] = []
        self.write_task_files()

    def rel(self, child: str | Path) -> str:
        return str(self.rel_dir / child)

    def write_json(self, child: str | Path, payload: dict[str, Any]) -> Path:
        return self.run.write_json(self.rel(child), payload)

    def write_task_files(self) -> None:
        phase_obj = self.task.get("phase")
        phase_value = phase_obj.value if hasattr(phase_obj, "value") else str(phase_obj or self.phase)
        parent_ids = [
            getattr(parent, "trajectory_id", str(parent))
            for parent in self.task.get("parent_trajectories", []) or []
        ]
        self.write_json(
            "00_task.json",
            {
                "schema_version": RunRecorder.schema_version,
                "run_id": self.run.run_id,
                "task_id": self.task_id,
                "round_id": f"{self.run.run_id}.round_{self.round_idx:02d}",
                "round_idx": self.round_idx,
                "phase": phase_value,
                "task_index": self.task_index,
                "status": "running",
                "direction_ref": f"{self.run.run_id}.direction_{self.direction_id:03d}",
                "parent_refs": parent_ids,
                "strategy_suffix": self.task.get("strategy_suffix", ""),
                "created_at": now_iso(),
            },
        )
        self.run.add_node(
            self.task_id,
            "task",
            f"{phase_value} task {self.task_index:03d}",
            self.rel("00_task.json"),
            phase=phase_value,
            round_idx=self.round_idx,
        )
        self.run.add_edge(f"{self.run.run_id}.round_{self.round_idx:02d}", self.task_id, "HAS_TASK")
        direction_node = f"{self.run.run_id}.direction_{self.direction_id:03d}"
        self.run.add_edge(direction_node, self.task_id, "USES_DIRECTION")

        self.write_json(
            "01_direction.json",
            {
                "schema_version": RunRecorder.schema_version,
                "run_id": self.run.run_id,
                "task_id": self.task_id,
                "direction_id": direction_node,
                "text": self.direction,
                "source_phase": phase_value,
            },
        )
        parents = []
        for parent in self.task.get("parent_trajectories", []) or []:
            parents.append(
                {
                    "parent_trajectory_id": getattr(parent, "trajectory_id", None),
                    "phase": getattr(getattr(parent, "phase", None), "value", getattr(parent, "phase", None)),
                    "round_idx": getattr(parent, "round_idx", None),
                    "direction_id": getattr(parent, "direction_id", None),
                    "primary_metric": getattr(parent, "get_primary_metric", lambda: None)(),
                    "summary": parent.to_summary_text() if hasattr(parent, "to_summary_text") else str(parent),
                }
            )
        if parents:
            self.write_json(
                "01_parent_refs.json",
                {
                    "schema_version": RunRecorder.schema_version,
                    "run_id": self.run.run_id,
                    "task_id": self.task_id,
                    "phase": phase_value,
                    "parents": parents,
                },
            )
        mutation_trace = self.task.get("mutation_trace")
        if mutation_trace:
            self.write_agent_output("02_mutation_prompt.json", "MutationAgent", mutation_trace, prompt_only=True)
            self.write_agent_output("03_mutation_output.json", "MutationAgent", mutation_trace)
        crossover_trace = self.task.get("crossover_trace")
        if crossover_trace:
            self.write_agent_output("02_crossover_prompt.json", "CrossoverAgent", crossover_trace, prompt_only=True)
            self.write_agent_output("03_crossover_output.json", "CrossoverAgent", crossover_trace)

    def write_alpha_loop_index(self, loop: Any, latest_step: str | None = None) -> None:
        self.write_json(
            "02_alpha_loop.json" if self.phase == "original" else "04_alpha_loop.json",
            {
                "schema_version": RunRecorder.schema_version,
                "run_id": self.run.run_id,
                "task_id": self.task_id,
                "steps": list(getattr(loop, "steps", [])),
                "latest_step": latest_step,
                "loop_idx": getattr(loop, "loop_idx", None),
                "step_idx": getattr(loop, "step_idx", None),
                "trajectory_id": getattr(loop, "trajectory_id", None),
                "parent_trajectory_ids": getattr(loop, "parent_trajectory_ids", []),
                "updated_at": now_iso(),
            },
        )

    def write_agent_output(
        self,
        child: str,
        actor: str,
        trace: dict[str, Any] | None,
        parsed_obj: Any = None,
        prompt_only: bool = False,
    ) -> None:
        trace = trace or {}
        raw = trace.get("raw", {})
        payload = {
            "schema_version": RunRecorder.schema_version,
            "run_id": self.run.run_id,
            "task_id": self.task_id,
            "actor": actor,
            "status": "success" if trace.get("ok", True) else "failed",
            "raw": raw,
            "parsed": trace.get("parsed", {"ok": parsed_obj is not None, "data": to_jsonable(parsed_obj)}),
            "parser": trace.get("parser", {}),
            "error": trace.get("error"),
            "created_at": now_iso(),
        }
        if prompt_only:
            payload = {
                "schema_version": RunRecorder.schema_version,
                "run_id": self.run.run_id,
                "task_id": self.task_id,
                "actor": actor,
                "raw": {
                    "system_prompt": raw.get("system_prompt"),
                    "user_prompt": raw.get("user_prompt"),
                    "variables": raw.get("variables", {}),
                },
                "created_at": now_iso(),
            }
        self.write_json(child, payload)

    def write_hypothesis(self, hypothesis: Any, trace: dict[str, Any] | None) -> None:
        child = "03_hypothesis.json" if self.phase == "original" else "05_hypothesis.json"
        node_id = f"{self.task_id}.hyp_000"
        self.write_agent_output(child, "HypothesisAgent", trace, parsed_obj=hypothesis)
        self.run.add_node(node_id, "hypothesis", "LLM 生成研究假设", self.rel(child), phase=self.phase, round_idx=self.round_idx)
        self.run.add_edge(self.task_id, node_id, "GENERATES_HYPOTHESIS")

    def write_experiment(self, experiment: Any, trace: dict[str, Any] | None) -> None:
        child = "04_experiment.json" if self.phase == "original" else "06_experiment.json"
        node_id = f"{self.task_id}.experiment_000"
        self.write_agent_output(child, "FactorGenerationAgent", trace, parsed_obj=experiment)
        self.run.add_node(node_id, "experiment", "LLM 生成因子公式", self.rel(child), phase=self.phase, round_idx=self.round_idx)
        self.run.add_edge(f"{self.task_id}.hyp_000", node_id, "GENERATES_EXPERIMENT")
        self._write_factor_definitions(experiment, trace)

    def _write_factor_definitions(self, experiment: Any, trace: dict[str, Any] | None) -> None:
        factor_dir_name = "05_factors" if self.phase == "original" else "07_factors"
        tasks = list(getattr(experiment, "sub_tasks", []) or [])
        self._factor_ids = []
        attempts = (trace or {}).get("attempts", [])
        for idx, task in enumerate(tasks):
            factor_id = f"{self.task_id}.factor_{idx:03d}"
            self._factor_ids.append(factor_id)
            rel = Path(factor_dir_name) / f"factor_{idx:03d}"
            self.write_json(
                rel / "00_factor.json",
                {
                    "schema_version": RunRecorder.schema_version,
                    "run_id": self.run.run_id,
                    "task_id": self.task_id,
                    "factor_id": factor_id,
                    "global_factor_id": None,
                    "factor_version_id": None,
                    "source": {
                        "round_idx": self.round_idx,
                        "phase": self.phase,
                        "hypothesis_id": f"{self.task_id}.hyp_000",
                    },
                    "definition": {
                        "name": getattr(task, "factor_name", getattr(task, "name", f"factor_{idx}")),
                        "description": getattr(task, "factor_description", ""),
                        "formulation": getattr(task, "factor_formulation", ""),
                        "expression": getattr(task, "factor_expression", ""),
                        "variables": to_jsonable(getattr(task, "variables", {})),
                    },
                    "raw": {
                        "source_file": "../.." + ("/04_experiment.json" if self.phase == "original" else "/06_experiment.json"),
                        "raw_factor_block": self._raw_factor_block(trace, getattr(task, "factor_name", "")),
                    },
                    "lifecycle": {
                        "status": "candidate",
                        "active": False,
                        "reason": "newly_generated",
                        "updated_at": now_iso(),
                    },
                },
            )
            self.run.add_node(factor_id, "factor", getattr(task, "factor_name", f"factor_{idx}"), self.rel(rel / "00_factor.json"), phase=self.phase, round_idx=self.round_idx)
            self.run.add_edge(f"{self.task_id}.experiment_000", factor_id, "GENERATES_FACTOR")

        for attempt_idx, attempt in enumerate(attempts):
            factor_idx = int(attempt.get("factor_index", 0) or 0)
            rel = Path(factor_dir_name) / f"factor_{factor_idx:03d}" / "01_formula_attempts" / f"attempt_{attempt_idx:03d}.json"
            attempt_id = f"{self.task_id}.factor_{factor_idx:03d}.attempt_{attempt_idx:03d}"
            self.write_json(
                rel,
                {
                    "schema_version": RunRecorder.schema_version,
                    "run_id": self.run.run_id,
                    "task_id": self.task_id,
                    "attempt_id": attempt_id,
                    **to_jsonable(attempt),
                },
            )
            self.run.add_node(attempt_id, "formula_attempt", f"Formula Attempt {attempt_idx}", self.rel(rel), phase=self.phase, round_idx=self.round_idx)
            self.run.add_edge(f"{self.task_id}.factor_{factor_idx:03d}", attempt_id, "HAS_ATTEMPT")

    def _raw_factor_block(self, trace: dict[str, Any] | None, factor_name: str) -> Any:
        parsed = ((trace or {}).get("parsed") or {}).get("data")
        if isinstance(parsed, dict) and factor_name in parsed:
            return parsed.get(factor_name)
        return None

    def write_factor_values(self, experiment: Any) -> None:
        factor_dir_name = "05_factors" if self.phase == "original" else "07_factors"
        workspaces = list(getattr(experiment, "sub_workspace_list", []) or [])
        for idx, ws in enumerate(workspaces):
            factor_id = self._factor_ids[idx] if idx < len(self._factor_ids) else f"{self.task_id}.factor_{idx:03d}"
            workspace_path = getattr(ws, "workspace_path", None)
            result_h5 = Path(workspace_path) / "result.h5" if workspace_path else None
            self.write_json(
                Path(factor_dir_name) / f"factor_{idx:03d}" / "02_factor_values_ref.json",
                {
                    "schema_version": RunRecorder.schema_version,
                    "run_id": self.run.run_id,
                    "task_id": self.task_id,
                    "factor_id": factor_id,
                    "workspace_path": str(workspace_path) if workspace_path else None,
                    "result_h5_path": str(result_h5) if result_h5 and result_h5.exists() else None,
                    "code_files": list(getattr(ws, "code_dict", {}).keys()) if ws else [],
                    "updated_at": now_iso(),
                },
            )

    def write_factor_evaluation(self, experiment: Any) -> None:
        factor_dir_name = "05_factors" if self.phase == "original" else "07_factors"
        result = getattr(experiment, "result", None)
        result_data = to_jsonable(result)
        is_oto = isinstance(result, dict) and result.get("evaluation_engine") == "oto_single_factor_v1"
        per_factor_results = list((result.get("factors") or {}).values()) if is_oto else []
        for idx, factor_id in enumerate(self._factor_ids or []):
            rel = Path(factor_dir_name) / f"factor_{idx:03d}" / "03_factor_evaluation.json"
            eval_id = f"{factor_id}.eval_000"
            factor_result = per_factor_results[idx] if idx < len(per_factor_results) else result_data
            factor_status = factor_result.get("status") if isinstance(factor_result, dict) else None
            self.write_json(
                rel,
                {
                    "schema_version": RunRecorder.schema_version,
                    "run_id": self.run.run_id,
                    "task_id": self.task_id,
                    "evaluation_id": eval_id,
                    "factor_id": factor_id,
                    "evaluation_engine": "oto_single_factor_v1" if is_oto else "qlib_legacy",
                    "status": factor_status or ("success" if result is not None else "failed"),
                    "raw": {
                        "experiment_workspace": str(getattr(getattr(experiment, "experiment_workspace", None), "workspace_path", "")),
                        "result": factor_result,
                    },
                    "parsed": {
                        "ok": factor_status in {"passed", "failed"} if is_oto else result is not None,
                        "metrics": factor_result,
                    },
                    "final_decision": (
                        "candidate" if factor_status == "passed" else "failed"
                    ) if is_oto else ("candidate" if result is not None else "failed"),
                },
            )
            self.run.add_node(eval_id, "evaluation", "因子评价结果", self.rel(rel), phase=self.phase, round_idx=self.round_idx)
            self.run.add_edge(factor_id, eval_id, "HAS_EVALUATION")
        self.write_json(
            "06_batch_evaluation.json" if self.phase == "original" else "08_batch_evaluation.json",
            {
                "schema_version": RunRecorder.schema_version,
                "run_id": self.run.run_id,
                "task_id": self.task_id,
                "factor_ids": self._factor_ids,
                "evaluation_engine": "oto_single_factor_v1" if is_oto else "qlib_legacy",
                "raw": {"result": result_data},
                "parsed": {"ok": result is not None, "metrics": result_data},
                "status": "completed" if result is not None else "failed",
            },
        )

    def write_feedback(self, feedback: Any, trace: dict[str, Any] | None) -> None:
        child = "07_feedback.json" if self.phase == "original" else "09_feedback.json"
        node_id = f"{self.task_id}.feedback_000"
        self.write_agent_output(child, "FeedbackAgent", trace, parsed_obj=feedback)
        self.run.add_node(node_id, "feedback", "LLM 根据结果生成反馈", self.rel(child), phase=self.phase, round_idx=self.round_idx)
        for factor_id in self._factor_ids:
            self.run.add_edge(factor_id, node_id, "HAS_FEEDBACK")

    def write_saved_factors(self, library_path: str | Path | None, status: str = "completed") -> None:
        child = "08_saved_factors.json" if self.phase == "original" else "10_saved_factors.json"
        self.write_json(
            child,
            {
                "schema_version": RunRecorder.schema_version,
                "run_id": self.run.run_id,
                "task_id": self.task_id,
                "factor_ids": self._factor_ids,
                "library_path": str(library_path) if library_path else None,
                "status": status,
                "updated_at": now_iso(),
            },
        )
