from __future__ import annotations

import json
import uuid
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import EvaluationConfig, PROJECT_ROOT, load_evaluation_config
from .engine import SingleFactorEvaluator
from .service import _atomic_json_write


class DeduplicationService:
    def __init__(self, config: EvaluationConfig | None = None):
        self.config = config or load_evaluation_config()

    def generate_report(self, library_path: str | Path) -> dict[str, Any]:
        path = Path(library_path).expanduser().resolve()
        with path.open("r", encoding="utf-8") as handle:
            library = json.load(handle)
        groups: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for factor_id, entry in (library.get("factors") or {}).items():
            evaluation = entry.get("evaluation_v2") or {}
            lifecycle = entry.get("lifecycle") or evaluation.get("lifecycle") or {}
            if evaluation.get("status") != "passed" or not lifecycle.get("active", False):
                continue
            direction = (entry.get("metadata") or {}).get("planning_direction") or "unclassified"
            groups[str(direction)].append((factor_id, entry))

        threshold = float(self.config.section("deduplication").get("threshold", 0.7))
        pair_rows: list[dict[str, Any]] = []
        cluster_rows: list[dict[str, Any]] = []
        for direction, entries in groups.items():
            if len(entries) < 2:
                continue
            values = {factor_id: self._load_training_factor(entry) for factor_id, entry in entries}
            edges: dict[str, set[str]] = defaultdict(set)
            for left_index, (left_id, left_entry) in enumerate(entries):
                for right_id, right_entry in entries[left_index + 1 :]:
                    pearson, spearman, days = self._pair_correlation(values[left_id], values[right_id])
                    triggered = (
                        pearson is not None and abs(pearson) >= threshold
                    ) or (
                        spearman is not None and abs(spearman) >= threshold
                    )
                    if not triggered:
                        continue
                    edges[left_id].add(right_id)
                    edges[right_id].add(left_id)
                    pair_rows.append(
                        {
                            "direction": direction,
                            "left_factor_id": left_id,
                            "left_factor_name": left_entry.get("factor_name", left_id),
                            "right_factor_id": right_id,
                            "right_factor_name": right_entry.get("factor_name", right_id),
                            "pearson": pearson,
                            "spearman": spearman,
                            "days": days,
                            "threshold": threshold,
                        }
                    )
            for component in self._components(edges):
                ranked = sorted(
                    component,
                    key=lambda factor_id: float(
                        ((library["factors"][factor_id].get("evaluation_v2") or {}).get("training") or {}).get("excess_sharpe")
                        or float("-inf")
                    ),
                    reverse=True,
                )
                if len(ranked) > 1:
                    cluster_rows.append(
                        {
                            "direction": direction,
                            "factor_ids": ranked,
                            "recommended_keep": ranked[0],
                            "recommended_archive": ranked[1:],
                        }
                    )

        report_id = f"dedup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        report = {
            "report_id": report_id,
            "status": "pending_confirmation",
            "library_path": str(path),
            "library_updated_at": (library.get("metadata") or {}).get("last_updated"),
            "config_hash": self.config.config_hash,
            "threshold": threshold,
            "methods": ["pearson", "spearman"],
            "pairs": pair_rows,
            "clusters": cluster_rows,
            "created_at": datetime.now().isoformat(),
        }
        output_dir = PROJECT_ROOT / "data" / "results" / "dedup_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(output_dir / f"{report_id}.json", report)
        return report

    def archive_confirmed(self, report_path: str | Path, archive_factor_ids: list[str]) -> dict[str, Any]:
        report_file = Path(report_path).expanduser().resolve()
        with report_file.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
        library_path = Path(report["library_path"]).resolve()
        with library_path.open("r", encoding="utf-8") as handle:
            library = json.load(handle)
        allowed = {
            factor_id
            for cluster in report.get("clusters", [])
            for factor_id in cluster.get("recommended_archive", [])
        }
        requested = set(archive_factor_ids)
        if not requested.issubset(allowed):
            raise ValueError("Archive request contains factors outside this deduplication report")
        archived = []
        for factor_id in requested:
            entry = (library.get("factors") or {}).get(factor_id)
            if entry is None:
                continue
            entry["lifecycle"] = {
                "status": "duplicate_rejected",
                "active": False,
                "reason": f"confirmed_from_{report['report_id']}",
                "updated_at": datetime.now().isoformat(),
            }
            archived.append(factor_id)
        library.setdefault("metadata", {})["last_updated"] = datetime.now().isoformat()
        _atomic_json_write(library_path, library)
        report["status"] = "applied"
        report["archived_factor_ids"] = archived
        report["applied_at"] = datetime.now().isoformat()
        _atomic_json_write(report_file, report)
        return {"report_id": report["report_id"], "archived_factor_ids": archived}

    def _load_training_factor(self, entry: dict[str, Any]) -> pd.DataFrame:
        h5 = entry.get("cache_location", {}).get("result_h5_path")
        if not h5 or not Path(h5).exists():
            return pd.DataFrame(columns=["factor_date", "code", "factor_value"])
        values = pd.read_hdf(h5)
        name = entry.get("factor_name", "factor")
        frame = SingleFactorEvaluator._normalize_factor(values, name)
        start, end = map(pd.Timestamp, self.config.training_period)
        return frame[(frame["factor_date"] >= start) & (frame["factor_date"] <= end)]

    @staticmethod
    def _pair_correlation(left: pd.DataFrame, right: pd.DataFrame) -> tuple[float | None, float | None, int]:
        merged = left.merge(right, on=["factor_date", "code"], suffixes=("_left", "_right"))
        pearson_values = []
        spearman_values = []
        for _date, group in merged.groupby("factor_date"):
            if len(group) < 3:
                continue
            pearson_values.append(group["factor_value_left"].corr(group["factor_value_right"], method="pearson"))
            spearman_values.append(group["factor_value_left"].corr(group["factor_value_right"], method="spearman"))
        finite_pearson = [value for value in pearson_values if pd.notna(value)]
        finite_spearman = [value for value in spearman_values if pd.notna(value)]
        pearson = float(np.mean(finite_pearson)) if finite_pearson else None
        spearman = float(np.mean(finite_spearman)) if finite_spearman else None
        return pearson, spearman, max(len(finite_pearson), len(finite_spearman))

    @staticmethod
    def _components(edges: dict[str, set[str]]) -> list[list[str]]:
        unseen = set(edges)
        components = []
        while unseen:
            root = unseen.pop()
            queue = deque([root])
            component = [root]
            while queue:
                current = queue.popleft()
                for neighbor in edges[current]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        component.append(neighbor)
                        queue.append(neighbor)
            components.append(component)
        return components
