from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from .config import EvaluationConfig, PROJECT_ROOT, load_evaluation_config
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


def _generic_factor_code(expression: str, factor_name: str) -> str:
    return f"""import os
import numpy as np
import pandas as pd
from quantaalpha.factors.coder.expr_parser import parse_expression, parse_symbol
from quantaalpha.factors.coder.function_lib import *


def calculate_factor(expr: str, name: str):
    df = pd.read_hdf('./daily_pv.h5', key='data')
    expr = parse_symbol(expr, df.columns)
    expr = parse_expression(expr)
    for col in df.columns:
        if col.startswith('$'):
            expr = expr.replace(col[1:], f"df['{{col}}']")
    df[name] = eval(expr)
    result = df[name].astype(np.float64)
    if os.path.exists('result.h5'):
        os.remove('result.h5')
    result.to_hdf('result.h5', key='data')


if __name__ == '__main__':
    expr = {expression!r}
    name = {factor_name!r}
    calculate_factor(expr, name)
"""


def _evaluation_output_root(config: EvaluationConfig) -> Path:
    output_dir = Path(config.section("engine").get("output_dir", "data/results/factor_evaluations"))
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    return output_dir


def _load_backtest_data_config(config: EvaluationConfig) -> dict[str, Any]:
    backtest_path = PROJECT_ROOT / "configs" / "backtest.yaml"
    raw: dict[str, Any] = {}
    if backtest_path.exists():
        loaded = yaml.safe_load(backtest_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded

    data_cfg = dict(raw.get("data") or {})
    train_start, _train_end = config.training_period
    _valid_start, valid_end = config.validation_period
    start = pd.Timestamp(train_start) - pd.Timedelta(days=500)
    data_cfg.setdefault("provider_uri", "~/.qlib/qlib_data/cn_data")
    data_cfg.setdefault("region", "cn")
    data_cfg.setdefault("market", "csi300")
    data_cfg["start_time"] = min(pd.Timestamp(data_cfg.get("start_time", start)), start).strftime("%Y-%m-%d")
    data_cfg["end_time"] = max(pd.Timestamp(data_cfg.get("end_time", valid_end)), pd.Timestamp(valid_end)).strftime("%Y-%m-%d")
    return {"data": data_cfg}


def _configured_daily_pv_path() -> Path:
    configured = os.environ.get("FACTOR_CoSTEER_DATA_FOLDER", "")
    base = Path(configured) if configured else PROJECT_ROOT / "git_ignore_folder" / "factor_implementation_source_data"
    if not base.is_absolute():
        base = PROJECT_ROOT / base
    return (base / "daily_pv.h5").expanduser().resolve()


def _required_source_columns(expression: str) -> set[str]:
    return set(re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*", expression or ""))


def _h5_columns(path: Path) -> set[str]:
    return set(pd.read_hdf(path, key="data", start=0, stop=0).columns)


def _stage_source_data(workspace: Path, expression: str, fallback_source: pd.DataFrame) -> Path:
    source_data_path = workspace / "daily_pv.h5"
    canonical = _configured_daily_pv_path()
    required = _required_source_columns(expression)

    if canonical.exists():
        try:
            if required.issubset(_h5_columns(canonical)):
                source_data_path.unlink(missing_ok=True)
                os.symlink(canonical, source_data_path)
                return source_data_path
        except Exception:
            pass

    fallback_source.to_hdf(source_data_path, key="data", mode="w")
    return source_data_path


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
        run_id = uuid.uuid4().hex[:12]
        source_data_path: Path | None = None
        workspace: Path | None = None

        if h5_path and Path(h5_path).exists():
            values = pd.read_hdf(h5_path)
            workspace = Path(h5_path).parent
        else:
            expression = str(entry.get("factor_expression", "")).strip()
            if not expression:
                return {
                    "factor_id": factor_id,
                    "factor_name": factor_name,
                    "status": "data_error",
                    "evaluation_engine": "oto_single_factor_v1",
                    "error": {"type": "FactorExpressionMissing", "message": "factor_expression is unavailable", "retryable": False},
                    "lifecycle": {"status": "not_evaluated", "active": False},
                    "oos_status": "sealed",
                }
            computed = self._compute_entry_from_expression(factor_id, factor_name, expression, entry, run_id)
            if computed.get("error"):
                return {
                    "factor_id": factor_id,
                    "factor_name": factor_name,
                    "status": "data_error",
                    "evaluation_engine": "oto_single_factor_v1",
                    "error": computed["error"],
                    "lifecycle": {"status": "not_evaluated", "active": False, "reason": "expression_compute_failed"},
                    "oos_status": "sealed",
                }
            values = computed["values"]
            h5_path = str(computed["result_h5_path"])
            workspace = computed["workspace"]
            source_data_path = computed["source_data_path"]

        code = _factor_code(entry)
        if not code:
            code = _generic_factor_code(str(entry.get("factor_expression", "")), factor_name)
        audit = self.auditor.audit(
            expression=str(entry.get("factor_expression", "")),
            code=code,
            factor_values=values,
            workspace_path=workspace,
            source_data_path=source_data_path,
        )
        return self.evaluator.evaluate(
            values,
            factor_id=factor_id,
            factor_name=factor_name,
            lookahead_audit=audit,
            run_id=run_id if source_data_path is not None else None,
            refresh_market_cache=refresh_market_cache,
        ).to_dict()

    def _compute_entry_from_expression(
        self,
        factor_id: str,
        factor_name: str,
        expression: str,
        entry: dict[str, Any],
        run_id: str,
    ) -> dict[str, Any]:
        try:
            from quantaalpha.backtest.custom_factor_calculator import CustomFactorCalculator

            workspace = _evaluation_output_root(self.config) / factor_id / run_id
            workspace.mkdir(parents=True, exist_ok=True)

            calculator = CustomFactorCalculator(config=_load_backtest_data_config(self.config), auto_extract_cache=False)
            values = calculator.calculate_factor(factor_name, expression)
            if values is None or len(values) == 0:
                raise ValueError("expression computation returned no values")
            if values.isna().all():
                raise ValueError("expression computation returned all-NaN values")

            source = calculator.data_df
            result_h5_path = workspace / "result.h5"
            factor_py_path = workspace / "factor.py"

            source_data_path = _stage_source_data(workspace, expression, source)
            values.to_hdf(result_h5_path, key="data", mode="w")
            code = _factor_code(entry) or _generic_factor_code(expression, factor_name)
            factor_py_path.write_text(code, encoding="utf-8")

            cache_location = dict(entry.get("cache_location") or {})
            cache_location.update(
                {
                    "workspace_path": str(workspace),
                    "result_h5_path": str(result_h5_path),
                    "generated_by": "evaluation_v2_expression_fallback",
                }
            )
            entry["cache_location"] = cache_location
            return {
                "values": values,
                "workspace": workspace,
                "source_data_path": source_data_path,
                "result_h5_path": result_h5_path,
            }
        except Exception as exc:
            return {
                "error": {
                    "type": type(exc).__name__,
                    "message": f"factor_expression computation failed: {exc}",
                    "retryable": True,
                }
            }

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
            selected: list[str] = []
            for factor_id, entry in factors.items():
                evaluation = entry.get("evaluation_v2") or {}
                retryable = (evaluation.get("error") or {}).get("retryable") is True
                if not evaluation or (evaluation.get("status") == "data_error" and retryable):
                    selected.append(factor_id)
            return selected
        raise ValueError(f"Unsupported evaluation mode: {mode}")
