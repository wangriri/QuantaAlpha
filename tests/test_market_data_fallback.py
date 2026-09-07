from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from quantaalpha.evaluation.config import EvaluationConfig, load_evaluation_config
from quantaalpha.evaluation.market_data import MongoMarketDataProvider


def make_config(tmp_path: Path) -> EvaluationConfig:
    raw = deepcopy(load_evaluation_config().raw)
    raw["engine"]["market_cache_dir"] = str(tmp_path / "cache")
    return EvaluationConfig(raw=raw, path=tmp_path / "evaluation.yaml")


class MarketDataFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_trade_dates_fall_back_to_cached_panel_without_mongo(self):
        config = make_config(self.tmp_path)
        cache_dir = Path(config.raw["engine"]["market_cache_dir"])
        cache_dir.mkdir()
        panel = pd.DataFrame(
            [
                {
                    "code": "600000",
                    "entry_date": pd.Timestamp("2023-01-03"),
                    "exit_date": pd.Timestamp("2023-01-04"),
                    "oto_return": 0.01,
                    "open_limit": False,
                    "is_st": False,
                },
                {
                    "code": "600000",
                    "entry_date": pd.Timestamp("2023-01-04"),
                    "exit_date": pd.Timestamp("2023-01-05"),
                    "oto_return": 0.02,
                    "open_limit": False,
                    "is_st": False,
                },
            ]
        )
        panel.to_pickle(cache_dir / "oto_panel_exact_session_v2_20230103_20230105.pkl")

        with patch.dict("os.environ", {}, clear=True):
            dates = MongoMarketDataProvider(config).load_trade_dates("2023-01-03", "2023-01-05")

        self.assertEqual(dates, [pd.Timestamp("2023-01-03"), pd.Timestamp("2023-01-04"), pd.Timestamp("2023-01-05")])

    def test_trade_dates_fall_back_to_local_qlib_calendar_without_mongo(self):
        config = make_config(self.tmp_path)
        calendar = self.tmp_path / "data" / "qlib" / "cn_data" / "calendars"
        calendar.mkdir(parents=True)
        (calendar / "day.txt").write_text("2023-01-02\n2023-01-03\n2023-01-04\n", encoding="utf-8")

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("quantaalpha.evaluation.market_data.PROJECT_ROOT", self.tmp_path),
        ):
            dates = MongoMarketDataProvider(config).load_trade_dates("2023-01-03", "2023-01-04")

        self.assertEqual(dates, [pd.Timestamp("2023-01-03"), pd.Timestamp("2023-01-04")])


if __name__ == "__main__":
    unittest.main()
