from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from quantaalpha.evaluation.config import EvaluationConfig, load_evaluation_config
from quantaalpha.evaluation.dedup import DeduplicationService
from quantaalpha.evaluation.lookahead import LookaheadAuditor
from quantaalpha.evaluation.service import (
    ConcurrentLibraryUpdateError,
    FactorLibraryEvaluationService,
    _atomic_json_write,
)


class _Result:
    def to_dict(self):
        return {
            "status": "passed",
            "training": {"ic": 0.04, "ic_abs": 0.04, "icir": 0.6, "long_short_spread": 0.4, "excess_sharpe": 1.2},
            "validation": {},
            "gate_results": {},
            "lifecycle": {"status": "candidate", "active": True},
            "oos_status": "sealed",
        }


class _Evaluator:
    def evaluate(self, *_args, **_kwargs):
        return _Result()


class _Auditor:
    def audit(self, **_kwargs):
        return {"status": "passed"}


def _config(root: Path) -> EvaluationConfig:
    raw = json.loads(json.dumps(load_evaluation_config().raw))
    raw["engine"]["output_dir"] = str(root / "reports")
    return EvaluationConfig(raw=raw, path=root / "evaluation.yaml")


class EvaluationServicesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_library_migration_preserves_qlib_legacy(self):
        index = pd.MultiIndex.from_product(
            [[pd.Timestamp("2023-01-03")], ["sh600000"]], names=["datetime", "instrument"]
        )
        h5 = self.root / "result.h5"
        pd.Series([1.0], index=index, name="factor").to_hdf(h5, key="data")
        library_path = self.root / "library.json"
        library_path.write_text(json.dumps({"metadata": {}, "factors": {"id": {
            "factor_name": "factor", "factor_expression": "DELAY($close, 1)",
            "cache_location": {"result_h5_path": str(h5)},
            "backtest_results": {"IC": 0.123},
        }}}), encoding="utf-8")
        service = FactorLibraryEvaluationService(_config(self.root))
        service.evaluator = _Evaluator()
        service.auditor = _Auditor()
        summary = service.evaluate_library(library_path, mode="all")
        saved = json.loads(library_path.read_text(encoding="utf-8"))["factors"]["id"]
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(saved["qlib_legacy"]["IC"], 0.123)
        self.assertEqual(saved["evaluation_v2"]["status"], "passed")
        self.assertTrue(saved["lifecycle"]["active"])

    def test_atomic_write_detects_concurrent_update(self):
        path = self.root / "library.json"
        path.write_text('{"version": 1}', encoding="utf-8")
        version = path.stat().st_mtime_ns
        path.write_text('{"version": 2, "changed": true}', encoding="utf-8")
        with self.assertRaises(ConcurrentLibraryUpdateError):
            _atomic_json_write(path, {"version": 3}, expected_mtime_ns=version)

    def test_manual_archive_keeps_factor_and_cache_reference(self):
        library = self.root / "library.json"
        library.write_text(json.dumps({"metadata": {}, "factors": {
            "keep": {"cache_location": {"result_h5_path": "/tmp/keep.h5"}},
            "drop": {"cache_location": {"result_h5_path": "/tmp/drop.h5"}},
        }}), encoding="utf-8")
        report = self.root / "dedup_report.json"
        report.write_text(json.dumps({
            "report_id": "dedup_test", "library_path": str(library), "status": "pending_confirmation",
            "clusters": [{"recommended_keep": "keep", "recommended_archive": ["drop"]}],
        }), encoding="utf-8")
        result = DeduplicationService(_config(self.root)).archive_confirmed(report, ["drop"])
        saved = json.loads(library.read_text(encoding="utf-8"))["factors"]
        self.assertEqual(result["archived_factor_ids"], ["drop"])
        self.assertIn("drop", saved)
        self.assertEqual(saved["drop"]["cache_location"]["result_h5_path"], "/tmp/drop.h5")
        self.assertEqual(saved["drop"]["lifecycle"]["status"], "duplicate_rejected")

    def test_truncation_recompute_detects_future_dependency(self):
        dates = pd.bdate_range("2023-01-02", periods=8)
        instruments = ["sh600000", "sh600001", "sh600002"]
        index = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
        source = pd.DataFrame({"close": range(len(index))}, index=index)
        source_path = self.root / "daily_pv.h5"
        source.to_hdf(source_path, key="data")
        future = source["close"].groupby(level="instrument").shift(-1).rename("future")
        code = """from pathlib import Path
import pandas as pd
data = pd.read_hdf(Path(__file__).with_name('daily_pv.h5'), key='data')
result = data['close'].groupby(level='instrument').shift(-1).rename('future')
result.to_hdf(Path(__file__).with_name('result.h5'), key='data')
"""
        config = _config(self.root)
        config.raw["periods"]["training"] = [str(dates[0].date()), str(dates[-1].date())]
        outcome = LookaheadAuditor(config).truncation_check(
            code=code, factor_values=future, workspace_path=None, source_data_path=source_path
        )
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["reason"], "future_values_change_past_factor")


if __name__ == "__main__":
    unittest.main()
