from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

from quantaalpha.factors.minute.engine import MinuteFactorEngine
from pymongo.errors import AutoReconnect
import yaml

from quantaalpha.factors.minute.mongo_reader import MongoMinuteProvider, MinuteDayResult, is_sh_sz_a_share, normalize_minute_documents
from quantaalpha.factors.minute.quick_run import prepare_quick_run
from quantaalpha.factors.coder.factor import stage_minute_debug_hdf
from quantaalpha.evaluation.source_window import is_same_day_minute_expression, minute_source_start
from quantaalpha.factors.minute.operators import M_DELAY, M_SESSION_RETURN, M_SLICE


def minute_frame(date: str, instrument: str, closes: list[float]) -> pd.DataFrame:
    minutes = pd.date_range(f"{date} 09:30", periods=len(closes), freq="min")
    index = pd.MultiIndex.from_arrays(
        [[pd.Timestamp(date)] * len(minutes), [instrument] * len(minutes), minutes],
        names=["datetime", "instrument", "minute"],
    )
    return pd.DataFrame({"$m_close": closes, "$m_volume": np.arange(1, len(closes) + 1)}, index=index)


class FakeProvider:
    def __init__(self):
        self.calls = []

    def load_day(self, trade_date, instruments, minute_columns):
        self.calls.append((pd.Timestamp(trade_date), tuple(instruments), tuple(minute_columns)))
        frames = []
        for offset, instrument in enumerate(instruments):
            base = 10 + offset + pd.Timestamp(trade_date).day
            frame = minute_frame(pd.Timestamp(trade_date).strftime("%Y-%m-%d"), instrument, [base, base + 1, base + 2])
            frames.append(frame[list(minute_columns)])
        return MinuteDayResult(pd.concat(frames).sort_index() if frames else pd.DataFrame(), [])


class FakeStreamingProvider:
    def __init__(self):
        self.calls = []

    def iter_stock_days(self, instrument, trade_dates, minute_columns):
        self.calls.append((instrument, len(trade_dates)))
        for date in trade_dates:
            frame = minute_frame(pd.Timestamp(date).strftime("%Y-%m-%d"), instrument, [10, 11, 12])
            yield MinuteDayResult(frame[list(minute_columns)], [])


class MinuteOperatorTest(unittest.TestCase):
    def test_rolling_state_resets_each_stock_day(self):
        first = minute_frame("2024-01-02", "sz000001", [1, 2, 3])
        second = minute_frame("2024-01-03", "sz000001", [10, 11, 12])
        values = pd.concat([first, second])["$m_close"]
        delayed = M_DELAY(values)
        self.assertTrue(np.isnan(delayed.loc[(pd.Timestamp("2024-01-03"), "sz000001")].iloc[0]))

    def test_slice_and_session_return(self):
        values = minute_frame("2024-01-02", "sz000001", [10, 11, 12])["$m_close"]
        result = M_SESSION_RETURN(M_SLICE(values, 930, 932))
        self.assertAlmostEqual(result.iloc[0], 0.2)


class MinuteDataQualityTest(unittest.TestCase):
    def test_transient_mongo_cancellation_retries_the_read(self):
        class Collection:
            calls = 0

            def find(self, *_args):
                self.calls += 1
                if self.calls == 1:
                    raise AutoReconnect("operation cancelled")
                return [{"trade_time": "2025-01-02 09:30:00"}]

        collection = Collection()
        with patch("quantaalpha.factors.minute.mongo_reader.time.sleep"):
            rows = MongoMinuteProvider._read_rows(collection, {}, {})
        self.assertEqual(collection.calls, 2)
        self.assertEqual(len(rows), 1)

    def test_universe_accepts_only_shanghai_shenzhen_a_shares(self):
        self.assertTrue(is_sh_sz_a_share("sh600000"))
        self.assertTrue(is_sh_sz_a_share("sz300750"))
        self.assertFalse(is_sh_sz_a_share("bj430001"))
        self.assertFalse(is_sh_sz_a_share("sh000001"))  # index, not a stock
        self.assertFalse(is_sh_sz_a_share("sh900901"))  # B share

    def test_equivalent_timestamp_spellings_are_deduplicated(self):
        rows = []
        for minute, close in [("09:30:00", 10.0), ("09:31:00", 11.0), ("09:32:00", 12.0)]:
            rows.append({"trade_time": f"2024-09-25 {minute}", "close": close})
        rows.append({"trade_time": "2024-09-25T09:30:00Z", "close": 10.0 + 1e-7})
        result = normalize_minute_documents(rows, "2024-09-25", "sz300750", {"close"}, expected_bars=3)
        self.assertEqual(len(result.frame), 3)
        self.assertEqual(result.issues, [])

    def test_conflicting_duplicate_rejects_stock_day(self):
        rows = [
            {"trade_time": "2024-09-25 09:30:00", "close": 10.0},
            {"trade_time": "2024-09-25T09:30:00Z", "close": 10.5},
        ]
        result = normalize_minute_documents(rows, "2024-09-25", "sz300750", {"close"}, expected_bars=1)
        self.assertTrue(result.frame.empty)
        self.assertIn("conflicting_duplicate", result.issues[0].reason)

    def test_opening_pre_close_can_be_missing(self):
        rows = [
            {"trade_time": "2024-09-25 09:30:00", "close": 10.0, "pre_close": np.nan},
            {"trade_time": "2024-09-25 09:31:00", "close": 10.1, "pre_close": 10.1},
        ]
        result = normalize_minute_documents(
            rows, "2024-09-25", "sz300750", {"close", "pre_close"}, expected_bars=2
        )
        self.assertEqual(len(result.frame), 2)


class MinuteEngineTest(unittest.TestCase):
    def setUp(self):
        self.index = pd.MultiIndex.from_product(
            [pd.to_datetime(["2024-01-02", "2024-01-03"]), ["sh600000", "sz000001"]],
            names=["datetime", "instrument"],
        )
        self.daily = pd.DataFrame({"$pe_ttm": [10.0, 20.0, 12.0, 18.0]}, index=self.index)

    def test_minute_and_daily_stages_are_combined_and_days_are_loaded_once(self):
        provider = FakeProvider()
        engine = MinuteFactorEngine(provider)
        expressions = {
            "combined": "RANK(M_SESSION_RETURN(M_SLICE($m_close, 930, 932))) * RANK(1 / ($pe_ttm + 1e-8))",
            "volume": "RANK(M_SESSION_SUM($m_volume))",
        }
        result = engine.calculate_many(expressions, self.daily)
        self.assertEqual(result.shape, (4, 2))
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(set(provider.calls[0][2]), {"$m_close", "$m_volume"})
        self.assertEqual(engine.last_report.coverage, 1.0)

    def test_unreduced_minute_expression_is_rejected(self):
        engine = MinuteFactorEngine(FakeProvider())
        with self.assertRaisesRegex(ValueError, "must end"):
            engine.calculate("bad", "M_TS_MEAN($m_close, 5)", self.daily)

    def test_daily_operator_inside_minute_stage_is_rejected(self):
        engine = MinuteFactorEngine(FakeProvider())
        with self.assertRaisesRegex(ValueError, "Daily operators"):
            engine.calculate("bad", "M_TO_DAILY(TS_MEAN($m_close, 5))", self.daily)

    def test_beijing_instruments_are_not_requested(self):
        index = self.index.append(pd.MultiIndex.from_tuples(
            [(pd.Timestamp("2024-01-02"), "bj430001")], names=self.index.names
        ))
        daily = self.daily.reindex(index)
        provider = FakeProvider()
        MinuteFactorEngine(provider).calculate("x", "M_SESSION_MEAN($m_close)", daily)
        self.assertNotIn("bj430001", provider.calls[0][1])

    def test_streaming_provider_preserves_daily_output(self):
        provider = FakeStreamingProvider()
        result = MinuteFactorEngine(provider).calculate("x", "M_SESSION_RETURN($m_close) * $pe_ttm", self.daily)
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(result.notna().sum(), 4)
        self.assertAlmostEqual(result.iloc[0], 2.0)

    def test_same_day_audit_window_is_only_used_for_safe_formulas(self):
        simple = "RANK(M_SESSION_RETURN(M_SLICE($m_close,1430,1500))) * RANK($pe_ttm)"
        historical = "TS_MEAN(M_SESSION_RETURN($m_close),20) * RANK($pe_ttm)"
        self.assertTrue(is_same_day_minute_expression(simple))
        self.assertFalse(is_same_day_minute_expression(historical))
        self.assertEqual(minute_source_start(simple, "2023-01-01"), pd.Timestamp("2022-11-22"))
        self.assertIsNone(minute_source_start(historical, "2023-01-01"))


class MinuteQuickRunTest(unittest.TestCase):
    def test_debug_subset_does_not_change_original_daily_hdf(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            dates = pd.bdate_range("2025-01-01", periods=70)
            index = pd.MultiIndex.from_product([dates, ["sz000001"]], names=["datetime", "instrument"])
            source = root / "source.h5"
            pd.DataFrame({"$pe_ttm": range(70)}, index=index).to_hdf(source, key="data")
            staged = root / "daily_pv.h5"
            staged.symlink_to(source)
            stage_minute_debug_hdf(staged)
            self.assertFalse(staged.is_symlink())
            self.assertEqual(len(pd.read_hdf(staged, key="data")), 60)
            self.assertEqual(len(pd.read_hdf(source, key="data")), 70)

    def test_daily_input_is_bounded_and_minute_bars_are_not_saved(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            dates = pd.bdate_range("2025-11-03", periods=24)
            index = pd.MultiIndex.from_product([dates, ["sz000001", "sh600000", "bj430001"]], names=["datetime", "instrument"])
            pd.DataFrame({"$pe_ttm": range(len(index))}, index=index).to_hdf(root / "debug.h5", key="data")
            config = {"periods": {}, "engine": {}}
            (root / "evaluation.yaml").write_text(yaml.safe_dump(config))
            source, evaluation, rows = prepare_quick_run(root / "debug.h5", root / "evaluation.yaml", root / "quick")
            result = pd.read_hdf(source, key="data")
            self.assertEqual(rows, 40)
            self.assertEqual(result.index.get_level_values("datetime").nunique(), 20)
            self.assertNotIn("bj430001", result.index.get_level_values("instrument"))
            self.assertEqual(sorted(path.name for path in source.parent.iterdir()), ["daily_pv.h5"])
            self.assertEqual(evaluation.parent, source.parent.parent)
            self.assertEqual(yaml.safe_load(evaluation.read_text())["periods"]["training"][0], dates[4].strftime("%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
