from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from quantaalpha.evaluation.runner import OTOSingleFactorRunner


class _Workspace:
    def __init__(self, path: Path, execute_values=None):
        self.workspace_path = path
        self.execute_values = execute_values
        self.execute_calls = 0

    def execute(self, data_type: str):
        self.execute_calls += 1
        return f"executed {data_type}", self.execute_values


class _Calculator:
    values = None
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def calculate_factor(self, factor_name: str, expression: str):
        type(self).calls += 1
        return type(self).values


def _values(name: str = "factor") -> pd.Series:
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2024-01-02")], ["sh600000", "sh600001"]],
        names=["datetime", "instrument"],
    )
    return pd.Series([1.0, 2.0], index=index, name=name)


class EvaluationRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        _Calculator.values = None
        _Calculator.calls = 0

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_debug_result_is_ignored_when_expression_is_available(self):
        debug_values = _values("debug")
        debug_values.to_hdf(self.root / "result.h5", key="data")
        expected = _values("formal")
        _Calculator.values = expected
        workspace = _Workspace(self.root, execute_values=_values("wrong"))

        with (
            patch("quantaalpha.evaluation.runner._load_backtest_data_config", return_value={}),
            patch("quantaalpha.backtest.custom_factor_calculator.CustomFactorCalculator", _Calculator),
        ):
            actual = OTOSingleFactorRunner._load_factor_values(
                workspace,
                factor_name="factor",
                expression="RANK($close)",
                config=object(),
            )

        pd.testing.assert_series_equal(actual, expected)
        self.assertEqual(workspace.execute_calls, 0)
        self.assertEqual(_Calculator.calls, 1)

    def test_missing_result_uses_expression_fallback_before_workspace_execution(self):
        expected = _values()
        _Calculator.values = expected
        workspace = _Workspace(self.root, execute_values=_values("wrong"))

        with (
            patch("quantaalpha.evaluation.runner._load_backtest_data_config", return_value={}),
            patch("quantaalpha.backtest.custom_factor_calculator.CustomFactorCalculator", _Calculator),
        ):
            actual = OTOSingleFactorRunner._load_factor_values(
                workspace,
                factor_name="factor",
                expression="RANK($close)",
                config=object(),
            )

        pd.testing.assert_series_equal(actual, expected)
        self.assertEqual(_Calculator.calls, 1)
        self.assertEqual(workspace.execute_calls, 0)

    def test_workspace_execution_remains_last_resort(self):
        expected = _values()
        workspace = _Workspace(self.root, execute_values=expected)

        with (
            patch("quantaalpha.evaluation.runner._load_backtest_data_config", return_value={}),
            patch("quantaalpha.backtest.custom_factor_calculator.CustomFactorCalculator", _Calculator),
        ):
            actual = OTOSingleFactorRunner._load_factor_values(
                workspace,
                factor_name="factor",
                expression="RANK($close)",
                config=object(),
            )

        pd.testing.assert_series_equal(actual, expected)
        self.assertEqual(workspace.execute_calls, 1)

    def test_execution_error_is_retryable_data_error(self):
        result = OTOSingleFactorRunner._error_result("id", "factor", "disk full")
        self.assertEqual(result["status"], "data_error")
        self.assertTrue(result["error"]["retryable"])

    def test_formal_audit_source_does_not_follow_debug_workspace_link(self):
        runner = OTOSingleFactorRunner.__new__(OTOSingleFactorRunner)
        task = type("Task", (), {"factor_name": "factor", "factor_expression": "RANK($close)"})()
        workspace = _Workspace(self.root, execute_values=_values())
        workspace.code_dict = {"factor.py": "print('factor')"}
        exp = type("Experiment", (), {"sub_tasks": [task], "sub_workspace_list": [workspace]})()
        formal_source = self.root / "formal_daily_pv.h5"
        captured = {}

        class _Audit:
            def __init__(self, _config):
                pass

            def audit(self, **kwargs):
                captured.update(kwargs)
                return {"status": "passed"}

        class _Evaluation:
            status = "failed"
            training = {}

            def to_dict(self):
                return {"status": self.status, "training": self.training}

        class _Evaluator:
            def __init__(self, _config):
                pass

            def evaluate(self, *args, **kwargs):
                return _Evaluation()

        with (
            patch("quantaalpha.evaluation.runner.load_evaluation_config", return_value=type(
                "Config", (), {"config_hash": "hash", "section": lambda self, _name: {}}
            )()),
            patch("quantaalpha.evaluation.runner.LookaheadAuditor", _Audit),
            patch("quantaalpha.evaluation.runner.SingleFactorEvaluator", _Evaluator),
            patch("quantaalpha.evaluation.runner._configured_daily_pv_path", return_value=formal_source),
            patch.object(OTOSingleFactorRunner, "_load_factor_values", return_value=_values()),
        ):
            runner.develop(exp)

        self.assertEqual(captured["source_data_path"], formal_source)


if __name__ == "__main__":
    unittest.main()
