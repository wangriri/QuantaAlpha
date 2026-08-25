from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quantaalpha.factors.coder.factor_ast import (
    BinaryOpNode,
    ConditionalNode,
    FunctionNode,
    Node,
    NumberNode,
    UnaryOpNode,
    parse_expression,
)

from .config import EvaluationConfig, PROJECT_ROOT


_LAG_FUNCTIONS = {"DELAY", "DELTA", "TS_PCTCHANGE"}
_LAG_METHODS = {"shift", "diff", "pct_change"}
_FORBIDDEN_IMPORT_PREFIXES = {"pymongo", "requests", "httpx", "urllib", "qlib.data"}


class LookaheadAuditor:
    def __init__(self, config: EvaluationConfig):
        self.config = config

    def audit(
        self,
        *,
        expression: str,
        code: str,
        factor_values: pd.Series | pd.DataFrame,
        workspace_path: str | Path | None,
        source_data_path: str | Path | None = None,
    ) -> dict[str, Any]:
        cfg = self.config.section("lookahead_audit")
        if not cfg.get("enabled", True):
            return {"status": "disabled", "static": {}, "truncation": {}}

        static_result = self.static_check(expression, code)
        if static_result["status"] != "passed":
            return {"status": "lookahead_rejected", "static": static_result, "truncation": {"status": "skipped"}}

        if not cfg.get("truncation_check", True):
            return {"status": "passed", "static": static_result, "truncation": {"status": "disabled"}}

        truncation = self.truncation_check(
            code=code,
            factor_values=factor_values,
            workspace_path=workspace_path,
            source_data_path=source_data_path,
        )
        status = "passed" if truncation.get("status") == "passed" else "lookahead_rejected"
        return {"status": status, "static": static_result, "truncation": truncation}

    def static_check(self, expression: str, code: str) -> dict[str, Any]:
        issues: list[str] = []
        warnings: list[str] = []
        if expression:
            try:
                root = parse_expression(expression)
                self._check_expression_node(root, issues)
            except Exception as exc:
                warnings.append(f"expression_ast_fallback:{type(exc).__name__}")
                issues.extend(self._regex_lookahead_checks(expression))

        try:
            tree = ast.parse(code or "")
        except SyntaxError as exc:
            issues.append(f"python_parse_failed:{exc.lineno}")
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name.startswith(prefix) for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                            issues.append(f"forbidden_import:{alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if any(module.startswith(prefix) for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                        issues.append(f"forbidden_import:{module}")
                elif isinstance(node, ast.Call):
                    name = self._call_name(node.func)
                    if name.split(".")[-1] in _LAG_METHODS | _LAG_FUNCTIONS:
                        for arg in node.args[1:] if name.split(".")[-1] in _LAG_FUNCTIONS else node.args[:1]:
                            number = self._literal_number(arg)
                            if number is not None and number < 0:
                                issues.append(f"negative_period:{name}({number})")
                    if name.endswith(("read_csv", "read_parquet", "read_pickle", "read_json")):
                        issues.append(f"nonstandard_external_read:{name}")
                    if name.endswith("read_hdf") and node.args:
                        path = self._literal_string(node.args[0])
                        if path is not None and Path(path).name != "daily_pv.h5":
                            issues.append(f"nonstandard_hdf_read:{path}")

        issues.extend(self._regex_lookahead_checks(code or ""))
        issues = sorted(set(issues))
        return {"status": "passed" if not issues else "failed", "issues": issues, "warnings": warnings}

    def _check_expression_node(self, node: Node, issues: list[str]) -> None:
        if isinstance(node, FunctionNode):
            if node.name.upper() in _LAG_FUNCTIONS:
                for arg in node.args[1:]:
                    if isinstance(arg, NumberNode) and arg.value < 0:
                        issues.append(f"negative_period:{node.name}({arg.value})")
            for arg in node.args:
                self._check_expression_node(arg, issues)
        elif isinstance(node, BinaryOpNode):
            self._check_expression_node(node.left, issues)
            self._check_expression_node(node.right, issues)
        elif isinstance(node, ConditionalNode):
            self._check_expression_node(node.condition, issues)
            self._check_expression_node(node.true_expr, issues)
            self._check_expression_node(node.false_expr, issues)
        elif isinstance(node, UnaryOpNode):
            self._check_expression_node(node.operand, issues)

    def truncation_check(
        self,
        *,
        code: str,
        factor_values: pd.Series | pd.DataFrame,
        workspace_path: str | Path | None,
        source_data_path: str | Path | None,
    ) -> dict[str, Any]:
        workspace = Path(workspace_path).resolve() if workspace_path else None
        factor_py = workspace / "factor.py" if workspace else None
        if not code and (factor_py is None or not factor_py.exists()):
            return {"status": "failed", "reason": "factor_code_unavailable"}

        source = Path(source_data_path).expanduser().resolve() if source_data_path else None
        if source is None and workspace is not None:
            candidate = workspace / "daily_pv.h5"
            if candidate.exists():
                source = candidate.resolve()
        if source is None:
            configured = os.environ.get("FACTOR_CoSTEER_DATA_FOLDER", "")
            base = Path(configured) if configured else PROJECT_ROOT / "git_ignore_folder" / "factor_implementation_source_data"
            if not base.is_absolute():
                base = PROJECT_ROOT / base
            source = (base / "daily_pv.h5").expanduser().resolve()
        if not source.exists():
            return {"status": "failed", "reason": "daily_pv_source_unavailable"}

        full_result = factor_values.iloc[:, 0] if isinstance(factor_values, pd.DataFrame) else factor_values
        if not isinstance(full_result.index, pd.MultiIndex) or "datetime" not in full_result.index.names:
            return {"status": "failed", "reason": "factor_result_index_invalid"}
        full_result = full_result.sort_index()
        training_start, training_end = map(pd.Timestamp, self.config.training_period)
        result_dates = pd.DatetimeIndex(full_result.index.get_level_values("datetime").unique()).sort_values()
        result_dates = result_dates[(result_dates >= training_start) & (result_dates <= training_end)]
        if len(result_dates) < 4:
            return {"status": "failed", "reason": "insufficient_dates_for_truncation"}

        raw_source = pd.read_hdf(source, key="data")
        if not isinstance(raw_source.index, pd.MultiIndex) or "datetime" not in raw_source.index.names:
            return {"status": "failed", "reason": "daily_pv_index_invalid"}
        quantiles = self.config.section("lookahead_audit").get("cutoff_quantiles", [0.25, 0.5, 0.75])
        cutoffs = sorted({result_dates[min(len(result_dates) - 1, int((len(result_dates) - 1) * float(q)))] for q in quantiles})
        rtol = float(self.config.section("lookahead_audit").get("rtol", 1e-8))
        atol = float(self.config.section("lookahead_audit").get("atol", 1e-10))
        checks: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix="quantaalpha_lookahead_") as temp_dir:
            temp = Path(temp_dir)
            temp_factor = temp / "factor.py"
            if code:
                temp_factor.write_text(code, encoding="utf-8")
            else:
                shutil.copy2(factor_py, temp_factor)
            for cutoff in cutoffs:
                truncated = raw_source[raw_source.index.get_level_values("datetime") <= cutoff]
                truncated.to_hdf(temp / "daily_pv.h5", key="data", mode="w")
                result_path = temp / "result.h5"
                result_path.unlink(missing_ok=True)
                env = os.environ.copy()
                env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
                completed = subprocess.run(
                    [sys.executable, str(temp_factor)],
                    cwd=temp,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=1200,
                )
                if completed.returncode != 0 or not result_path.exists():
                    return {
                        "status": "failed",
                        "reason": "truncated_factor_execution_failed",
                        "cutoff": str(cutoff.date()),
                        "returncode": completed.returncode,
                    }
                truncated_result = pd.read_hdf(result_path)
                if isinstance(truncated_result, pd.DataFrame):
                    truncated_result = truncated_result.iloc[:, 0]
                expected = full_result.xs(cutoff, level="datetime").sort_index()
                actual = truncated_result.xs(cutoff, level="datetime").sort_index()
                joined = pd.concat([expected.rename("expected"), actual.rename("actual")], axis=1).dropna()
                matches = bool(
                    len(joined) > 0
                    and np.allclose(joined["expected"].to_numpy(), joined["actual"].to_numpy(), rtol=rtol, atol=atol)
                )
                checks.append({"cutoff": str(cutoff.date()), "compared_values": len(joined), "matches": matches})
                if not matches:
                    return {"status": "failed", "reason": "future_values_change_past_factor", "checks": checks}
        return {"status": "passed", "checks": checks}

    @staticmethod
    def _call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = LookaheadAuditor._call_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    @staticmethod
    def _literal_number(node: ast.AST) -> float | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = LookaheadAuditor._literal_number(node.operand)
            return -value if value is not None else None
        return None

    @staticmethod
    def _literal_string(node: ast.AST) -> str | None:
        return str(node.value) if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

    @staticmethod
    def _regex_lookahead_checks(code: str) -> list[str]:
        issues = []
        for name in ("shift", "diff", "pct_change"):
            if re.search(rf"\.{name}\s*\(\s*-\s*\d+", code):
                issues.append(f"negative_period_regex:{name}")
        for name in _LAG_FUNCTIONS:
            if re.search(rf"\b{name}\s*\([^\)]*,\s*-\s*\d+", code, flags=re.IGNORECASE):
                issues.append(f"negative_period_regex:{name}")
        return issues
