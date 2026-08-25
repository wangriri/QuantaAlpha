from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .config import EvaluationConfig, load_evaluation_config
from .engine import SingleFactorEvaluator
from .lookahead import LookaheadAuditor


ProgressCallback = Callable[[dict[str, Any]], None]


class ConcurrentLibraryUpdateError(RuntimeError):
    pass


def _atomic_json_write(path: Path, data: dict[str, Any], expected_mtime_ns: int | None = None) -> None:
    if expected_mtime_ns is not None and path.exists() and path.stat().st_mtime_ns != expected_mtime_ns:
        raise ConcurrentLibraryUpdateError(f"Factor library changed during evaluation: {path}")
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
    temp.replace(path)


def _factor_code(entry: dict[str, Any]) -> str:
    workspace = entry.get("cache_location", {}).get("result_h5_path")
    if workspace:
        candidate = Path(workspace).parent / "factor.py"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    combined = str(entry.get("factor_implementation_code", ""))
    marker = "File: factor.py"
    if marker not in combined:
        return combined
    code = combined.split(marker, 1)[1].lstrip("\r\n")
    next_file = code.find("\nFile: ")
    return code[:next_file] if next_file >= 0 else code


class FactorLibraryEvaluationService:
    def __init__(self, config: EvaluationConfig | None = None):
        self.config = config or load_evaluation_config()
        self.evaluator = SingleFactorEvaluator(self.config)
        self.auditor = LookaheadAuditor(self.config)

    def evaluate_library(
        self,
        library_path: str | Path,
        *,
        mode: str = "unevaluated",
        factor_ids: list[str] | None = None,
        refresh_market_cache: bool = False,
        progress: ProgressCallback | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        path = Path(library_path).expanduser().resolve()
        with path.open("r", encoding="utf-8") as handle:
            library = json.load(handle)
        library_version = path.stat().st_mtime_ns
        factors = library.get("factors") or {}
        selected = self._select_factors(factors, mode, factor_ids)
        summary = {"total": len(selected), "completed": 0, "passed": 0, "failed": 0, "cancelled": False}

        for index, factor_id in enumerate(selected, start=1):
            if should_cancel and should_cancel():
                summary["cancelled"] = True
                break
            entry = factors[factor_id]
            factor_name = entry.get("factor_name", factor_id)
            if progress:
                progress({"stage": "evaluating", "factor_id": factor_id, "factor_name": factor_name, "current": index, "total": len(selected)})
            result = self._evaluate_entry(factor_id, entry, refresh_market_cache=refresh_market_cache and index == 1)
            if entry.get("backtest_results") and not entry.get("qlib_legacy"):
                entry["qlib_legacy"] = entry.get("backtest_results")
            entry["evaluation_v2"] = result
            entry["lifecycle"] = result.get("lifecycle") or {"status": "evaluation_failed", "active": False}
            entry["oos_status"] = "sealed"
            summary["completed"] += 1
            summary["passed" if result.get("status") == "passed" else "failed"] += 1
            library.setdefault("metadata", {})["evaluation_engine"] = "oto_single_factor_v1"
            library["metadata"]["evaluation_config_hash"] = self.config.config_hash
            _atomic_json_write(path, library, expected_mtime_ns=library_version)
            library_version = path.stat().st_mtime_ns
            if progress:
                progress({"stage": "completed_factor", "factor_id": factor_id, "status": result.get("status"), **summary})
        return summary

    def _evaluate_entry(
        self,
        factor_id: str,
        entry: dict[str, Any],
        *,
        refresh_market_cache: bool,
    ) -> dict[str, Any]:
        factor_name = entry.get("factor_name", factor_id)
        h5_path = entry.get("cache_location", {}).get("result_h5_path")
        if not h5_path or not Path(h5_path).exists():
            return {
                "factor_id": factor_id,
                "factor_name": factor_name,
                "status": "data_error",
                "evaluation_engine": "oto_single_factor_v1",
                "error": {"type": "FactorDataMissing", "message": "result.h5 is unavailable", "retryable": True},
                "lifecycle": {"status": "not_evaluated", "active": False},
                "oos_status": "sealed",
            }
        values = pd.read_hdf(h5_path)
        code = _factor_code(entry)
        workspace = Path(h5_path).parent
        audit = self.auditor.audit(
            expression=str(entry.get("factor_expression", "")),
            code=code,
            factor_values=values,
            workspace_path=workspace,
        )
        return self.evaluator.evaluate(
            values,
            factor_id=factor_id,
            factor_name=factor_name,
            lookahead_audit=audit,
            refresh_market_cache=refresh_market_cache,
        ).to_dict()

    @staticmethod
    def _select_factors(
        factors: dict[str, Any],
        mode: str,
        factor_ids: list[str] | None,
    ) -> list[str]:
        if factor_ids:
            return [factor_id for factor_id in factor_ids if factor_id in factors]
        if mode == "all":
            return list(factors)
        if mode == "unevaluated":
            return [factor_id for factor_id, entry in factors.items() if not entry.get("evaluation_v2")]
        raise ValueError(f"Unsupported evaluation mode: {mode}")
