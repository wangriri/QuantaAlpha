from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from quantaalpha.evaluation.config import EvaluationConfig, load_evaluation_config
from quantaalpha.evaluation.engine import SingleFactorEvaluator
from quantaalpha.evaluation.lookahead import LookaheadAuditor
from quantaalpha.evaluation.market_data import _attach_exact_next_session_return


class FakeMarketData:
    def __init__(self, dates: pd.DatetimeIndex, panel: pd.DataFrame):
        self.dates = list(dates)
        self.panel = panel

    def load_trade_dates(self, start: str, end: str) -> list[pd.Timestamp]:
        return [date for date in self.dates if pd.Timestamp(start) <= date <= pd.Timestamp(end)]

    def load_panel(self, start: str, end: str, refresh: bool = False) -> pd.DataFrame:
        return self.panel.copy()


def make_config(tmp_path: Path) -> EvaluationConfig:
    raw = deepcopy(load_evaluation_config().raw)
    raw["periods"]["training"] = ["2023-01-03", "2023-01-12"]
    raw["periods"]["validation"] = ["2023-01-13", "2023-01-18"]
    raw["engine"]["output_dir"] = str(tmp_path / "reports")
    raw["metrics"]["half_life_max_lag"] = 3
    raw["metrics"]["ic_threshold"] = 0.03
    raw["metrics"]["icir_threshold"] = 0.0
    raw["metrics"]["spread_threshold"] = -999.0
    raw["metrics"]["excess_sharpe_threshold"] = -999.0
    raw["metrics"]["qcut_random_seed"] = 42
    return EvaluationConfig(raw=raw, path=tmp_path / "evaluation.yaml")


def with_rebalance_period(config: EvaluationConfig, days: int) -> EvaluationConfig:
    raw = deepcopy(config.raw)
    raw["portfolio"] = {"rebalance_period_days": days}
    return EvaluationConfig(raw=raw, path=config.path)


def make_fixture(direction: int = 1):
    dates = pd.bdate_range("2023-01-02", "2023-01-18")
    codes = [f"{600000 + index:06d}" for index in range(20)]
    panel_rows = []
    factor_rows = []
    for date_index, date in enumerate(dates):
        if date_index < len(dates) - 1:
            for stock_index, code in enumerate(codes):
                scale = 0.8 + date_index * 0.07
                panel_rows.append(
                    {
                        "code": code,
                        "entry_date": date,
                        "exit_date": dates[date_index + 1],
                        "oto_return": scale * (stock_index - 9.5) / 1000.0,
                        "open_limit": False,
                        "is_st": False,
                    }
                )
        for stock_index, code in enumerate(codes):
            factor_rows.append((date, f"sh{code}", direction * float(stock_index)))
    factor = pd.Series(
        [row[2] for row in factor_rows],
        index=pd.MultiIndex.from_tuples(
            [(row[0], row[1]) for row in factor_rows], names=["datetime", "instrument"]
        ),
        name="fixture_factor",
    )
    return dates, pd.DataFrame(panel_rows), factor


class SingleFactorEvaluationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_previous_trading_day_alignment_and_direction(self):
        dates, panel, factor = make_fixture(direction=-1)
        evaluator = SingleFactorEvaluator(make_config(self.tmp_path), FakeMarketData(dates, panel))
        result = evaluator.evaluate(
            factor,
            factor_id="negative_factor",
            factor_name="fixture_factor",
            lookahead_audit={"status": "passed"},
            run_id="test",
        )

        self.assertEqual(result.direction_multiplier, -1)
        self.assertLess(result.training["ic"], 0)
        self.assertGreater(result.training["directional_ic"], 0)
        self.assertTrue(result.alignment["factor_before_entry"])
        self.assertTrue(
            all(
                pd.Timestamp(item["factor_date"]) < pd.Timestamp(item["entry_date"])
                for item in result.alignment["samples"]
            )
        )

    def test_period_returns_never_cross_boundary(self):
        dates, panel, factor = make_fixture(direction=1)
        evaluator = SingleFactorEvaluator(make_config(self.tmp_path), FakeMarketData(dates, panel))
        normalized = evaluator._normalize_factor(factor, "fixture_factor")
        aligned = evaluator._align(normalized, panel, list(dates), "2023-01-03", "2023-01-12")

        self.assertGreaterEqual(aligned["entry_date"].min(), pd.Timestamp("2023-01-03"))
        self.assertLessEqual(aligned["exit_date"].max(), pd.Timestamp("2023-01-12"))
        self.assertFalse(
            ((aligned["entry_date"] == "2023-01-12") & (aligned["exit_date"] > "2023-01-12")).any()
        )

    def test_spring_festival_uses_previous_trade_date(self):
        dates = [pd.Timestamp("2025-01-27"), pd.Timestamp("2025-02-05"), pd.Timestamp("2025-02-06")]
        mapping = SingleFactorEvaluator._calendar_previous_map(dates)
        self.assertEqual(mapping[pd.Timestamp("2025-02-05")], pd.Timestamp("2025-01-27"))

    def test_suspended_stock_does_not_jump_to_next_available_observation(self):
        prices = pd.DataFrame([
            {"code": "600000", "entry_date": pd.Timestamp("2023-01-03"), "open": 10.0, "close": 10.2, "pre_close": 9.9},
            {"code": "600000", "entry_date": pd.Timestamp("2023-01-06"), "open": 10.3, "close": 10.4, "pre_close": 10.2},
        ])
        result = _attach_exact_next_session_return(
            prices,
            [pd.Timestamp("2023-01-03"), pd.Timestamp("2023-01-04"), pd.Timestamp("2023-01-05"), pd.Timestamp("2023-01-06")],
        )
        first = result[result["entry_date"] == pd.Timestamp("2023-01-03")].iloc[0]
        self.assertEqual(first["exit_date"], pd.Timestamp("2023-01-04"))
        self.assertTrue(pd.isna(first["oto_return"]))

    def test_half_life_requires_three_consecutive_lags(self):
        evaluator = SingleFactorEvaluator(make_config(self.tmp_path), FakeMarketData(pd.DatetimeIndex([]), pd.DataFrame()))
        decay = pd.DataFrame({"ic": [1.0, 0.7, 0.49, 0.40, 0.30]}, index=[1, 2, 3, 4, 5])
        self.assertEqual(evaluator._half_life(decay), 3)

    def test_static_lookahead_rejects_negative_shift(self):
        auditor = LookaheadAuditor(make_config(self.tmp_path))
        bad = auditor.static_check("DELAY($close, -1)", "result = df.groupby('instrument').shift(-1)")
        good = auditor.static_check("DELAY($close, 1)", "result = df.groupby('instrument').shift(1)")

        self.assertEqual(bad["status"], "failed")
        self.assertTrue(any("negative_period" in issue for issue in bad["issues"]))
        self.assertEqual(good["status"], "passed")

    def test_fee_formula_matches_oto_membership_turnover_and_benchmark_is_uncosted_market_mean(self):
        dates, panel, factor = make_fixture(direction=1)
        evaluator = SingleFactorEvaluator(with_rebalance_period(make_config(self.tmp_path), 1), FakeMarketData(dates, panel))
        normalized = evaluator._normalize_factor(factor, "fixture_factor")
        aligned = evaluator._align(normalized, panel, list(dates), "2023-01-03", "2023-01-12")
        period_panel = evaluator._period_panel(panel, "2023-01-03", "2023-01-12")
        groups, excess = evaluator._group_returns(aligned, 1, period_panel)

        self.assertTrue(np.isclose(groups.iloc[0]["G9_fee"], 2 * 0.0007))
        self.assertTrue(np.isclose(excess.iloc[0]["benchmark_fee"], 0.0))
        self.assertTrue(np.isclose(groups.iloc[1]["G9_fee"], 0.0))
        self.assertTrue(np.isclose(excess.iloc[1]["benchmark_fee"], 0.0))
        first_day = period_panel[period_panel["entry_date"] == excess.index[0]]
        self.assertTrue(np.isclose(excess.iloc[0]["benchmark_net_return"], first_day["oto_return"].mean()))
        self.assertTrue({f"G{index}" for index in range(10)}.issubset(groups.columns))

    def test_benchmark_uses_raw_market_panel_not_eligible_universe(self):
        dates, panel, factor = make_fixture(direction=1)
        first_entry = pd.Timestamp("2023-01-03")
        panel.loc[(panel["entry_date"] == first_entry) & (panel["code"] == "600019"), "open_limit"] = True
        panel.loc[(panel["entry_date"] == first_entry) & (panel["code"] == "600019"), "oto_return"] = 1.0
        evaluator = SingleFactorEvaluator(with_rebalance_period(make_config(self.tmp_path), 1), FakeMarketData(dates, panel))
        normalized = evaluator._normalize_factor(factor, "fixture_factor")
        eligible = evaluator._eligible_panel(panel)
        raw_period = evaluator._period_panel(panel, "2023-01-03", "2023-01-12")
        aligned = evaluator._align(normalized, eligible, list(dates), "2023-01-03", "2023-01-12")

        _, excess = evaluator._group_returns(aligned, 1, raw_period)

        self.assertFalse(
            ((aligned["entry_date"] == first_entry) & (aligned["code"] == "600019")).any()
        )
        expected_benchmark = raw_period[raw_period["entry_date"] == first_entry]["oto_return"].mean()
        self.assertTrue(np.isclose(excess.loc[first_entry, "benchmark_net_return"], expected_benchmark))
        self.assertEqual(excess.loc[first_entry, "benchmark_fee"], 0.0)

    def test_rebalance_period_defaults_to_three_and_validates(self):
        evaluator = SingleFactorEvaluator(make_config(self.tmp_path), FakeMarketData(pd.DatetimeIndex([]), pd.DataFrame()))
        self.assertEqual(evaluator._rebalance_period_days(), 3)

        bad_config = with_rebalance_period(make_config(self.tmp_path), 0)
        bad = SingleFactorEvaluator(bad_config, FakeMarketData(pd.DatetimeIndex([]), pd.DataFrame()))
        with self.assertRaisesRegex(ValueError, "rebalance_period_days"):
            bad._rebalance_period_days()

    def test_three_day_rebalance_keeps_holdings_but_marks_daily_returns(self):
        dates, panel, factor = make_fixture(direction=1)
        config = with_rebalance_period(make_config(self.tmp_path), 3)
        evaluator = SingleFactorEvaluator(config, FakeMarketData(dates, panel))
        normalized = evaluator._normalize_factor(factor, "fixture_factor")
        aligned = evaluator._align(normalized, panel, list(dates), "2023-01-03", "2023-01-12")
        period_panel = evaluator._period_panel(panel, "2023-01-03", "2023-01-12")

        groups, excess = evaluator._group_returns(aligned, 1, period_panel)

        self.assertEqual(groups["is_rebalance_day"].head(4).tolist(), [True, False, False, True])
        self.assertTrue((groups.loc[groups["is_rebalance_day"] == False].filter(regex=r"^G\d+_fee$") == 0.0).all().all())
        self.assertEqual(len(groups), period_panel["entry_date"].nunique())
        self.assertEqual(len(excess), len(groups))
        self.assertEqual(set(groups["rebalance_period_days"].unique()), {3})

        first_day_top = aligned[aligned["entry_date"] == groups.index[0]].nlargest(2, "factor_value")["oto_return"].mean()
        second_return_day = period_panel[
            (period_panel["entry_date"] == groups.index[1])
            & (period_panel["code"].isin(["600018", "600019"]))
        ]["oto_return"].mean()
        self.assertTrue(np.isclose(groups.iloc[0]["G9"], first_day_top))
        self.assertTrue(np.isclose(groups.iloc[1]["G9"], second_return_day))

    def test_validation_degradation_uses_locked_directional_metrics(self):
        result = SingleFactorEvaluator._validation_degradation(
            {"directional_ic": 0.04, "icir": 0.8, "long_short_spread": 0.4, "excess_sharpe": 2.0},
            {"directional_ic": 0.02, "icir": 0.4, "long_short_spread": 0.1, "excess_sharpe": 1.0},
        )
        self.assertAlmostEqual(result["directional_ic"]["retention_ratio"], 0.5)
        self.assertAlmostEqual(result["long_short_spread"]["degradation_ratio"], 0.75)


if __name__ == "__main__":
    unittest.main()
