from __future__ import annotations

import unittest

import pandas as pd

from quantaalpha.evaluation.tactical import TacticalFactorAnalyzer, compute_monthly_drawdown


def _frame(monthly_returns: list[float], *, days: int = 12, start: str = "2025-01-01") -> pd.DataFrame:
    months = pd.period_range(start=start, periods=len(monthly_returns), freq="M")
    rows = []
    for month, monthly_return in zip(months, monthly_returns):
        dates = pd.bdate_range(month.start_time, periods=days)
        for date in dates:
            rows.append({"date": date, "excess_return": monthly_return / days})
    return pd.DataFrame(rows)


def _config() -> dict:
    return {
        "min_training_months": 4,
        "min_validation_months": 2,
        "min_trading_days_per_month": 10,
        "strong_best_month_quantile": 0.65,
        "burst_month_quantile": 0.75,
        "high_volatility_quantile": 0.50,
        "severe_loss_quantile": 0.10,
        "severe_drawdown_quantile": 0.10,
        "min_positive_month_ratio": 0.30,
        "min_burst_month_count": 1,
    }


class TacticalAnalysisTest(unittest.TestCase):
    def test_monthly_aggregation_filters_short_months(self):
        frame = pd.concat([
            _frame([0.20], days=2, start="2025-01-01"),
            _frame([0.03], days=12, start="2025-02-01"),
        ], ignore_index=True)

        monthly = TacticalFactorAnalyzer(_config()).monthly_returns(frame)

        self.assertEqual(monthly["month"].tolist(), ["2025-02"])
        self.assertAlmostEqual(monthly.iloc[0]["monthly_excess"], 0.03)

    def test_monthly_drawdown_counts_loss_from_zero(self):
        returns = pd.Series([0.10, -0.05, -0.03, 0.02], index=pd.period_range("2025-01", periods=4, freq="M"))

        self.assertAlmostEqual(compute_monthly_drawdown(returns), -0.08)

    def test_relative_quantiles_cover_all_tactical_labels(self):
        records = [
            {
                "factorId": "attack",
                "factorName": "Attack",
                "evaluationStatus": "failed",
                "training_excess": _frame([0.01, 0.09, 0.02, 0.07, -0.01, 0.03]),
                "validation_excess": _frame([0.02, 0.08, -0.01], start="2025-07-01"),
            },
            {
                "factorId": "crash",
                "factorName": "Crash",
                "evaluationStatus": "failed",
                "training_excess": _frame([0.12, -0.14, 0.01, 0.00, 0.02, 0.03]),
            },
            {
                "factorId": "stable",
                "factorName": "Stable",
                "evaluationStatus": "passed",
                "training_excess": _frame([0.010, 0.012, 0.009, 0.011, 0.010, 0.008]),
            },
            {
                "factorId": "inactive",
                "factorName": "Inactive",
                "evaluationStatus": "failed",
                "training_excess": _frame([-0.010, 0.000, 0.005, -0.004, 0.002, -0.003]),
            },
            {
                "factorId": "short",
                "factorName": "Short",
                "evaluationStatus": "passed",
                "training_excess": _frame([0.20], start="2025-01-01"),
            },
        ]

        result = TacticalFactorAnalyzer(_config()).analyze_factors(records)
        labels = {factor["factorId"]: factor["training"]["label"] for factor in result["factors"]}

        self.assertEqual(labels["attack"], "战术进攻型")
        self.assertEqual(labels["crash"], "高风险爆发型")
        self.assertEqual(labels["stable"], "稳健候选型")
        self.assertEqual(labels["inactive"], "暂无战术价值")
        self.assertEqual(labels["short"], "数据不足")
        self.assertEqual(result["summary"]["analyzed"], 5)
        self.assertGreater(result["factors"][0]["training"]["score"], 0)

    def test_missing_training_artifact_is_skipped(self):
        result = TacticalFactorAnalyzer(_config()).analyze_factors([
            {"factorId": "missing", "factorName": "Missing"},
        ])

        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["analyzed"], 0)
        self.assertEqual(result["summary"]["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
