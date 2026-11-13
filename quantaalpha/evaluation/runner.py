from __future__ import annotations

import hashlib
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from quantaalpha.components.runner import CachedRunner
from quantaalpha.core.exception import FactorEmptyError
from quantaalpha.factors.experiment import QlibFactorExperiment
from quantaalpha.log import logger

from .config import load_evaluation_config
from .engine import SingleFactorEvaluator
from .lookahead import LookaheadAuditor
from .service import _configured_daily_pv_path, _generic_factor_code, _load_backtest_data_config


class OTOSingleFactorRunner(CachedRunner[QlibFactorExperiment]):
    """Evaluate every generated factor independently with the company OTO target."""

    def develop(
        self,
        exp: QlibFactorExperiment,
        use_local: bool = True,
        backtest_timeout: int | None = None,
    ) -> QlibFactorExperiment:
        del use_local, backtest_timeout
        config = load_evaluation_config()
        evaluator = SingleFactorEvaluator(config)
        auditor = LookaheadAuditor(config)
        results: dict[str, dict[str, Any]] = {}

        tasks = list(getattr(exp, "sub_tasks", []) or [])
        workspaces = list(getattr(exp, "sub_workspace_list", []) or [])
        if not tasks or not workspaces:
            raise FactorEmptyError("No factor tasks or workspaces available for OTO evaluation")

        for index, task in enumerate(tasks):
            factor_name = getattr(task, "factor_name", f"factor_{index}")
            expression = getattr(task, "factor_expression", "")
            factor_id = hashlib.md5(f"{factor_name}_{expression}".encode()).hexdigest()[:16]
            if index >= len(workspaces):
                results[factor_name] = self._error_result(
                    factor_id,
                    factor_name,
                    "workspace_missing",
                    retryable=False,
                )
                continue
            workspace = workspaces[index]
            try:
                values = self._load_factor_values(
                    workspace,
                    factor_name=factor_name,
                    expression=expression,
                    config=config,
                )
                if values is None:
                    raise FactorEmptyError(f"No factor values generated for {factor_name}")
                if isinstance(values, pd.Series):
                    values = values.rename(factor_name)
                code = (getattr(workspace, "code_dict", {}) or {}).get("factor.py", "")
                if not code and expression:
                    code = _generic_factor_code(expression, factor_name)
                workspace_path = getattr(workspace, "workspace_path", None)
                audit = auditor.audit(
                    expression=expression,
                    code=code,
                    factor_values=values,
                    workspace_path=workspace_path,
                    # The workspace still points at the small Debug dataset used
                    # during code generation.  Formal values were computed from
                    # the canonical dataset, so truncation must use that same
                    # source or cross-sectional operators (RANK/ZSCORE) differ.
                    source_data_path=_configured_daily_pv_path(),
                )
                evaluation = evaluator.evaluate(
                    values,
                    factor_id=factor_id,
                    factor_name=factor_name,
                    lookahead_audit=audit,
                )
                results[factor_name] = evaluation.to_dict()
                logger.info(
                    f"OTO single-factor evaluation: {factor_name}, status={evaluation.status}, "
                    f"IC={evaluation.training.get('ic')}, Sharpe={evaluation.training.get('excess_sharpe')}"
                )
            except Exception as exc:
                logger.error(f"OTO evaluation failed for {factor_name}: {exc}")
                logger.error(traceback.format_exc())
                results[factor_name] = self._error_result(
                    factor_id,
                    factor_name,
                    str(exc),
                    error_type=type(exc).__name__,
                    retryable=True,
                )

        primary = self._select_primary(results)
        exp.result = {
            "evaluation_engine": str(config.section("engine").get("name", "oto_single_factor_v1")),
            "config_hash": config.config_hash,
            "factors": results,
            "summary": {
                "total": len(results),
                "passed": sum(item.get("status") == "passed" for item in results.values()),
                "failed": sum(item.get("status") not in {"passed", "running"} for item in results.values()),
                "primary_factor": primary,
                "oos_status": "sealed",
            },
        }
        return exp

    @staticmethod
    def _values_are_usable(values: pd.Series | pd.DataFrame | None) -> bool:
        if values is None or len(values) == 0:
            return False
        missing = values.isna()
        return not bool(missing.all().all() if isinstance(missing, pd.DataFrame) else missing.all())

    @classmethod
    def _load_factor_values(
        cls,
        workspace: Any,
        *,
        factor_name: str,
        expression: str,
        config: Any,
    ) -> pd.Series | pd.DataFrame | None:
        """Load values computed against the formal evaluation dataset.

        Mining workspaces normally contain a ``result.h5`` produced by the
        Debug execution pass.  That file is useful for implementation feedback,
        but it must never be used as the input to formal OTO evaluation.
        """
        workspace_path_value = getattr(workspace, "workspace_path", None)
        workspace_path = Path(workspace_path_value) if workspace_path_value else None
        result_path = workspace_path / "result.h5" if workspace_path else None

        if expression:
            try:
                from quantaalpha.backtest.custom_factor_calculator import CustomFactorCalculator

                calculator = CustomFactorCalculator(
                    config=_load_backtest_data_config(config),
                    auto_extract_cache=False,
                )
                values = calculator.calculate_factor(factor_name, expression)
                if cls._values_are_usable(values):
                    logger.info(
                        f"Computed factor values from expression on the formal dataset for OTO evaluation: {factor_name}"
                    )
                    return values
            except Exception as exc:
                logger.warning(f"Formal expression computation failed for {factor_name}: {exc}")

            # The generated implementation may support an expression that the
            # local calculator does not.  Re-run it with full data rather than
            # accepting the Debug result already present in the workspace.
            _message, values = workspace.execute("All")
            return values if cls._values_are_usable(values) else None

        # Legacy entries without an expression cannot be recomputed cheaply.
        # Prefer a full execution; only then fall back to an existing result.
        _message, values = workspace.execute("All")
        if cls._values_are_usable(values):
            return values

        if result_path and result_path.exists():
            try:
                values = pd.read_hdf(result_path)
                if cls._values_are_usable(values):
                    logger.warning(
                        f"Using unverified legacy factor values because no expression is available: {result_path}"
                    )
                    return values
            except Exception as exc:
                logger.warning(f"Failed to read legacy factor values {result_path}: {exc}")
        return None

    @staticmethod
    def _select_primary(results: dict[str, dict[str, Any]]) -> str | None:
        if not results:
            return None

        def key(item: tuple[str, dict[str, Any]]) -> tuple[float, float, float, float]:
            _name, result = item
            training = result.get("training") or {}
            return (
                1.0 if result.get("status") == "passed" else 0.0,
                float(training.get("excess_sharpe") or float("-inf")),
                float(training.get("ic_abs") or float("-inf")),
                float(training.get("long_short_spread") or float("-inf")),
            )

        return max(results.items(), key=key)[0]

    @staticmethod
    def _error_result(
        factor_id: str,
        factor_name: str,
        message: str,
        *,
        error_type: str = "EvaluationError",
        retryable: bool = True,
    ) -> dict[str, Any]:
        return {
            "factor_id": factor_id,
            "factor_name": factor_name,
            "status": "data_error",
            "evaluation_engine": "oto_single_factor_v1",
            "training": {},
            "validation": {},
            "gate_results": {},
            "lifecycle": {"status": "evaluation_error", "active": False},
            "oos_status": "sealed",
            "error": {"type": error_type, "message": message, "retryable": retryable},
        }
