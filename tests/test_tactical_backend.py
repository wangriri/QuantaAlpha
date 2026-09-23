from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from fastapi import HTTPException


def _load_backend_app():
    path = Path(__file__).resolve().parents[1] / "frontend-v2" / "backend" / "app.py"
    spec = importlib.util.spec_from_file_location("quantaalpha_frontend_backend_app", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TacticalBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.app = _load_backend_app()
        self.app.PROJECT_ROOT = self.root
        self.app.TACTICAL_CONFIG_PATH = self.root / "configs" / "tactical_analysis.yaml"
        self.app.TACTICAL_GROUP_TEST_DIR = self.root / "data" / "results" / "tactical_group_tests"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_tactical_config_uses_independent_yaml(self):
        self.app._write_yaml_dict(self.app.TACTICAL_CONFIG_PATH, {
            "min_training_months": 9,
            "strong_best_month_quantile": 0.9,
        })

        config = self.app._tactical_config_for_frontend()
        defaults = self.app._default_tactical_config_for_frontend()

        self.assertEqual(config["min_training_months"], 9)
        self.assertEqual(config["strong_best_month_quantile"], 0.9)
        self.assertEqual(defaults["min_training_months"], 6)
        self.assertEqual(defaults["strong_best_month_quantile"], 0.85)
        self.assertIn("burst_month_quantile", config)
        self.assertIn("high_return_correlation_threshold", config)

    def test_tactical_artifact_must_stay_under_evaluation_output_root(self):
        good = self.root / "data" / "results" / "factor_evaluations" / "factor" / "run" / "training_excess_returns.csv"
        good.parent.mkdir(parents=True)
        good.write_text("date,excess_return\n2025-01-02,0.01\n", encoding="utf-8")
        outside = self.root / "data" / "training_excess_returns.csv"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("date,excess_return\n2025-01-02,0.01\n", encoding="utf-8")

        self.assertEqual(self.app._resolve_tactical_artifact(str(good)), good.resolve())
        with self.assertRaises(HTTPException):
            self.app._resolve_tactical_artifact(str(outside))

    def test_tactical_h5_artifact_must_stay_under_evaluation_output_root(self):
        good = self.root / "data" / "results" / "factor_evaluations" / "factor" / "run" / "result.h5"
        good.parent.mkdir(parents=True)
        good.write_bytes(b"placeholder")
        outside = self.root / "data" / "result.h5"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(b"placeholder")

        self.assertEqual(self.app._resolve_tactical_h5_artifact(str(good)), good.resolve())
        with self.assertRaises(HTTPException):
            self.app._resolve_tactical_h5_artifact(str(outside))

    def test_build_tactical_records_skips_missing_or_bad_artifacts(self):
        output_root = self.root / "data" / "results" / "factor_evaluations"
        good = output_root / "factor_a" / "run" / "training_excess_returns.csv"
        bad = output_root / "factor_b" / "run" / "training_excess_returns.csv"
        good.parent.mkdir(parents=True)
        bad.parent.mkdir(parents=True)
        good.write_text("date,excess_return\n2025-01-02,0.01\n", encoding="utf-8")
        bad.write_text("date,wrong_column\n2025-01-02,0.01\n", encoding="utf-8")
        library = self.root / "library.json"
        library.write_text(json.dumps({"factors": {
            "factor_a": {
                "factor_name": "Factor A",
                "evaluation_v2": {"status": "passed", "artifacts": {"training_excess_returns": str(good)}},
            },
            "factor_b": {
                "factor_name": "Factor B",
                "evaluation_v2": {"status": "failed", "artifacts": {"training_excess_returns": str(bad)}},
            },
            "factor_c": {
                "factor_name": "Factor C",
                "evaluation_v2": {"status": "failed", "artifacts": {}},
            },
        }}), encoding="utf-8")

        records = self.app._build_tactical_records(library)

        by_id = {record["factorId"]: record for record in records}
        self.assertIn("training_excess", by_id["factor_a"])
        self.assertIn("skipReason", by_id["factor_b"])
        self.assertEqual(by_id["factor_c"]["skipReason"], "缺少训练期超额收益产物")

    def test_factor_detail_uses_selected_library(self):
        factorlib = self.root / "data" / "factorlib"
        factorlib.mkdir(parents=True)
        first = factorlib / "all_factors_library_first.json"
        second = factorlib / "all_factors_library_second.json"
        first.write_text(json.dumps({"factors": {"shared": {"factor_name": "old", "evaluation_v2": {"artifacts": {"training_excess_returns": "old.csv"}}}}}), encoding="utf-8")
        second.write_text(json.dumps({"factors": {"shared": {"factor_name": "selected", "evaluation_v2": {"artifacts": {"training_excess_returns": "selected.csv"}}}}}), encoding="utf-8")

        response = asyncio.run(self.app.get_factor_detail("shared", library=second.name))

        self.assertEqual(response.data["factor"]["factor_name"], "selected")
        self.assertEqual(
            response.data["factor"]["evaluation_v2"]["artifacts"]["training_excess_returns"],
            "selected.csv",
        )

    def test_tactical_group_test_save_and_read_uses_stable_factor_set_key(self):
        result = {
            "library": "library.json",
            "factorIds": ["factor_b", "factor_a"],
            "factorNames": ["Factor B", "Factor A"],
            "factorValueCorrelation": {"averagePearson": 0.82, "averageSpearman": 0.79},
            "strategy": {
                "training": {"metrics": {"total_excess": 0.12}},
                "validation": {"metrics": {"total_excess": 0.03}},
            },
        }

        saved = self.app._save_tactical_group_test("library.json", ["factor_b", "factor_a"], result)
        reread = self.app._read_tactical_group_test("library.json", ["factor_a", "factor_b"])
        listed = self.app._list_tactical_group_tests("library.json")

        self.assertEqual(saved["key"], reread["key"])
        self.assertEqual(reread["result"]["factorNames"], ["Factor B", "Factor A"])
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["factorIds"], ["factor_b", "factor_a"])
        self.assertAlmostEqual(listed[0]["trainingTotalExcess"], 0.12)


if __name__ == "__main__":
    unittest.main()
