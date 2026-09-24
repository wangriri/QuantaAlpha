from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from quantaalpha.factors.data_template.mongo_daily_pv import (
    FINAL_COLUMNS,
    normalize_daily_pv,
    ts_code_to_instrument,
)


class MongoDailyPVTest(unittest.TestCase):
    def test_ts_code_to_instrument(self):
        self.assertEqual(ts_code_to_instrument("000001.SZ"), "sz000001")
        self.assertEqual(ts_code_to_instrument("600000.SH"), "sh600000")

    def test_normalize_daily_pv_final_columns_and_pe_fill(self):
        frame = pd.DataFrame(
            {
                "datetime": pd.to_datetime(["2023-01-02", "2023-01-03"]),
                "instrument": ["sh600000", "sh600000"],
                "$open": [10.0, 11.0],
                "$close": [11.0, 12.0],
                "$high": [11.5, 12.5],
                "$low": [9.5, 10.5],
                "$volume": [100.0, 200.0],
                "$amount": [1000.0, 2400.0],
                "$pe": [np.nan, 12.3],
                "$pe_ttm": [np.nan, 11.5],
                "$buy_elg_amount": [99.0, 98.0],
                "$buy_md_amount": [9.0, 8.0],
            }
        )

        result = normalize_daily_pv(frame)

        self.assertEqual(list(result.columns), FINAL_COLUMNS)
        self.assertNotIn("$buy_elg_amount", result.columns)
        self.assertNotIn("$buy_md_amount", result.columns)
        self.assertEqual(float(result.iloc[0]["$pe"]), 0.0)
        self.assertEqual(float(result.iloc[0]["$pe_ttm"]), 0.0)
        self.assertAlmostEqual(float(result.iloc[0]["$vwap"]), 10.0)
        self.assertEqual(float(result.iloc[0]["$return"]), 0.0)
        self.assertAlmostEqual(float(result.iloc[1]["$return"]), 12.0 / 11.0 - 1.0)


if __name__ == "__main__":
    unittest.main()
