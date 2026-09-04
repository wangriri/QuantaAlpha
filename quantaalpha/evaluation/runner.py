from __future__ import annotations

import hashlib
import traceback
from typing import Any

import pandas as pd

from quantaalpha.components.runner import CachedRunner
from quantaalpha.core.exception import FactorEmptyError
from quantaalpha.factors.experiment import QlibFactorExperiment
from quantaalpha.log import logger

from .config import load_evaluation_config
from .engine import SingleFactorEvaluator
from .lookahead import LookaheadAuditor


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
                results[factor_name] = self._error_result(factor_id, factor_name, "workspace_missing")
                continue
            workspace = workspaces[index]
            try:
                _message, values = workspace.execute("All")
                if values is None:
                    raise FactorEmptyError(f"No factor values generated for {factor_name}")
                if isinstance(values, pd.Series):
                    values = values.rename(factor_name)
                code = (getattr(workspace, "code_dict", {}) or {}).get("factor.py", "")
                workspace_path = getattr(workspace, "workspace_path", None)
                audit = auditor.audit(
                    expression=expression,
                    code=code,
                    factor_values=values,
                    workspace_path=workspace_path,
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
                results[factor_name] = self._error_result(factor_id, factor_name, str(exc))

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
    def _error_result(factor_id: str, factor_name: str, message: str) -> dict[str, Any]:
        return {
            "factor_id": factor_id,
            "factor_name": factor_name,
            "status": "failed",
            "evaluation_engine": "oto_single_factor_v1",
            "training": {},
            "validation": {},
            "gate_results": {},
            "lifecycle": {"status": "evaluation_error", "active": False},
            "oos_status": "sealed",
            "error": {"type": "EvaluationError", "message": message, "retryable": False},
        }
