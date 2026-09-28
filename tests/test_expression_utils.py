import unittest

import pandas as pd

from quantaalpha.backtest.custom_factor_calculator import CustomFactorCalculator
from quantaalpha.backtest.expression_utils import replace_data_column_tokens
from quantaalpha.evaluation.service import _generic_factor_code
from quantaalpha.factors.coder.expr_parser import parse_expression, parse_symbol


class ExpressionUtilsTest(unittest.TestCase):
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

    def test_generic_evaluation_code_template_compiles(self):
        code = _generic_factor_code("RANK($pe_ttm)", "prefix_collision_factor")
        compile(code, "factor.py", "exec")
        self.assertIn("replace_data_column_tokens(expr, df.columns)", code)


if __name__ == "__main__":
    unittest.main()
