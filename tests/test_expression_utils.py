import unittest
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from quantaalpha.backtest.custom_factor_calculator import CustomFactorCalculator, get_qlib_stock_data
from quantaalpha.backtest.expression_utils import replace_data_column_tokens
from quantaalpha.evaluation.service import _generic_factor_code
from quantaalpha.factors.coder.expr_parser import parse_expression, parse_symbol
from quantaalpha.core.template import CodeTemplate


class ExpressionUtilsTest(unittest.TestCase):
    def test_mining_template_generates_values_with_overlapping_field_names(self):
        project_root = Path(__file__).resolve().parents[1]
        template = CodeTemplate(project_root / "quantaalpha/factors/coder/template.jinjia2")
        index = pd.MultiIndex.from_product(
            [pd.to_datetime(["2024-01-02", "2024-01-03"]), ["sz000001", "sz000002"]],
            names=["datetime", "instrument"],
        )
        frame = pd.DataFrame({
            "$pe": [1., 2., 3., 4.],
            "$pe_ttm": [10., 20., 30., 40.],
            "$amount": [100., 200., 300., 400.],
            "$buy_lg_amount": [9., 12., 15., 18.],
            "$sell_lg_amount": [2., 3., 4., 5.],
            "$buy_sm_amount": [5., 6., 7., 8.],
            "$sell_sm_amount": [1., 2., 3., 4.],
            "$buying": [20., 30., 40., 50.],
            "$selling": [10., 15., 20., 25.],
        }, index=index)
        expression = (
            "($pe_ttm + $pe) * "
            "($buy_lg_amount - $sell_lg_amount + $buy_sm_amount - $sell_sm_amount) "
            "/ $amount + ($buying - $selling) / ($buying + $selling)"
        )
        expected = (
            (frame["$pe_ttm"] + frame["$pe"])
            * (frame["$buy_lg_amount"] - frame["$sell_lg_amount"]
               + frame["$buy_sm_amount"] - frame["$sell_sm_amount"])
            / frame["$amount"]
            + (frame["$buying"] - frame["$selling"]) / (frame["$buying"] + frame["$selling"])
        ).rename("new_daily_features")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "factor.py").write_text(
                template.render(expression=expression, factor_name=expected.name), encoding="utf-8"
            )
            # Exercise both column orders: correctness must not depend on HDF layout.
            for reverse in (False, True):
                with self.subTest(reverse_columns=reverse):
                    data = frame.iloc[:, ::-1] if reverse else frame
                    data.to_hdf(workspace / "daily_pv.h5", key="data", mode="w")
                    (workspace / "result.h5").unlink(missing_ok=True)
                    run = subprocess.run(
                        [sys.executable, str(workspace / "factor.py")],
                        cwd=workspace, env=env, capture_output=True, text=True, timeout=60,
                    )
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    pd.testing.assert_series_equal(pd.read_hdf(workspace / "result.h5"), expected)

    def test_mining_template_supports_unary_and_binary_max_min(self):
        project_root = Path(__file__).resolve().parents[1]
        template = CodeTemplate(project_root / "quantaalpha/factors/coder/template.jinjia2")
        index = pd.MultiIndex.from_product(
            [pd.to_datetime(["2024-01-02", "2024-01-03"]), ["sz000001", "sz000002"]],
            names=["datetime", "instrument"],
        )
        frame = pd.DataFrame(
            {
                "$buy_lg_amount": [1.0, 4.0, 3.0, 2.0],
                "$sell_sm_amount": [2.0, 2.0, 1.0, 5.0],
            },
            index=index,
        )
        expression = (
            "MAX($buy_lg_amount) - MIN($sell_sm_amount) + "
            "MAX($buy_lg_amount, $sell_sm_amount) - "
            "MIN($buy_lg_amount, $sell_sm_amount)"
        )
        cross_max = frame["$buy_lg_amount"].groupby(level="datetime").transform("max")
        cross_min = frame["$sell_sm_amount"].groupby(level="datetime").transform("min")
        expected = (
            cross_max
            - cross_min
            + frame[["$buy_lg_amount", "$sell_sm_amount"]].max(axis=1)
            - frame[["$buy_lg_amount", "$sell_sm_amount"]].min(axis=1)
        ).rename("max_min_compatibility")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            frame.to_hdf(workspace / "daily_pv.h5", key="data", mode="w")
            (workspace / "factor.py").write_text(
                template.render(expression=expression, factor_name=expected.name), encoding="utf-8"
            )
            run = subprocess.run(
                [sys.executable, str(workspace / "factor.py")],
                cwd=workspace, env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            pd.testing.assert_series_equal(pd.read_hdf(workspace / "result.h5"), expected)

    def test_replace_data_column_tokens_avoids_prefix_collisions(self):
        columns = pd.Index(["$pe", "$pe_ttm", "$amount", "$buy_lg_amount"])

        parsed = parse_expression(parse_symbol("RANK($pe_ttm)", columns))
        self.assertEqual(replace_data_column_tokens(parsed, columns), "RANK(df['$pe_ttm'])")

        parsed = parse_expression(parse_symbol("RANK($buy_lg_amount / ($amount + 1e-8))", columns))
        replaced = replace_data_column_tokens(parsed, columns)
        self.assertIn("df['$buy_lg_amount']", replaced)
        self.assertIn("df['$amount']", replaced)
        self.assertNotIn("df['$pe']_ttm", replaced)
        self.assertNotIn("buy_lg_df['$amount']", replaced)

    def test_custom_factor_calculator_handles_new_prefixed_features(self):
        index = pd.MultiIndex.from_product(
            [pd.to_datetime(["2024-01-02", "2024-01-03"]), ["sz000001", "sz000002"]],
            names=["datetime", "instrument"],
        )
        frame = pd.DataFrame(
            {
                "$close": [10.0, 20.0, 11.0, 19.0],
                "$pe": [1.0, 2.0, 3.0, 4.0],
                "$pe_ttm": [10.0, 20.0, 30.0, 40.0],
                "$amount": [100.0, 200.0, 300.0, 400.0],
                "$buy_lg_amount": [5.0, 10.0, 15.0, 20.0],
            },
            index=index,
        )

        calculator = CustomFactorCalculator(data_df=frame, auto_extract_cache=False)
        result = calculator.calculate_factor(
            "prefix_collision_factor",
            "($pe_ttm + $buy_lg_amount) / ($amount + 1e-8)",
        )

        self.assertIsNotNone(result)
        expected = (frame["$pe_ttm"] + frame["$buy_lg_amount"]) / (frame["$amount"] + 1e-8)
        pd.testing.assert_series_equal(result, expected.rename("prefix_collision_factor"))

    def test_stock_data_loader_prefers_enhanced_daily_pv(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp)
            index = pd.MultiIndex.from_product(
                [pd.to_datetime(["2024-01-02", "2024-01-03", "2024-02-01"]), ["sz000001"]],
                names=["datetime", "instrument"],
            )
            frame = pd.DataFrame(
                {
                    "$close": [10.0, 11.0, 12.0],
                    "$pe_ttm": [1.0, 2.0, 3.0],
                    "$buy_lg_amount": [100.0, 200.0, 300.0],
                },
                index=index,
            )
            frame.to_hdf(source_dir / "daily_pv.h5", key="data", mode="w")

            with patch.dict("os.environ", {"FACTOR_CoSTEER_DATA_FOLDER": str(source_dir)}):
                loaded = get_qlib_stock_data(
                    {"data": {"start_time": "2024-01-01", "end_time": "2024-01-31"}}
                )

        self.assertIn("$pe_ttm", loaded.columns)
        self.assertIn("$buy_lg_amount", loaded.columns)
        self.assertEqual(len(loaded), 2)

    def test_generic_evaluation_code_template_compiles(self):
        code = _generic_factor_code("RANK($pe_ttm)", "prefix_collision_factor")
        compile(code, "factor.py", "exec")
        self.assertIn("calculate_factor_expression(expr, df, name)", code)


if __name__ == "__main__":
    unittest.main()
