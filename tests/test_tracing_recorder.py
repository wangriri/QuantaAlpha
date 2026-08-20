from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quantaalpha.tracing import RunRecorder


class RunRecorderTest(unittest.TestCase):
    def test_step_files_events_and_graph_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = RunRecorder.create(
                project_root=root,
                initial_direction="volume reversal",
                config_path=None,
                run_cfg={"planning": {"enabled": False}},
                execution_context={"step_n": 0},
            )
            recorder.write_planning_prompt("system", "user", {"n": 1})
            recorder.write_planning_output(
                {
                    "raw": {"response_text": '{"directions": ["volume reversal"]}'},
                    "directions": ["volume reversal"],
                    "parser": {"attempt_count": 1, "warnings": []},
                }
            )
            task = {
                "phase": "original",
                "direction_id": 0,
                "round_idx": 0,
                "task_index": 0,
                "parent_trajectories": [],
                "strategy_suffix": "",
            }
            recorder.write_round_summary(0, "original", [task])
            task_recorder = recorder.task_recorder(task, direction="volume reversal")
            task_recorder.write_hypothesis(
                {"hypothesis": "panic selling may reverse"},
                {
                    "raw": {"response_text": '{"hypothesis": "panic selling may reverse"}'},
                    "parsed": {"ok": True, "data": {"hypothesis": "panic selling may reverse"}},
                    "parser": {"attempt_count": 1},
                },
            )
            recorder.write_run_complete()

            run_dir = recorder.run_dir
            self.assertTrue((run_dir / "00_run_summary.json").exists())
            self.assertTrue((run_dir / "00_planning" / "00_prompt.json").exists())
            self.assertTrue((run_dir / "00_planning" / "01_output.json").exists())
            self.assertTrue(
                (
                    run_dir
                    / "round_00_original"
                    / "task_000_original_direction_000"
                    / "03_hypothesis.json"
                ).exists()
            )
            self.assertTrue((run_dir / "04_events.jsonl").exists())

            graph = json.loads((run_dir / "03_run_graph.json").read_text(encoding="utf-8"))
            node_paths = {node["path"] for node in graph["nodes"]}
            self.assertIn("00_planning/01_output.json", node_paths)
            self.assertIn("round_00_original/task_000_original_direction_000/03_hypothesis.json", node_paths)
            self.assertGreaterEqual(len(graph["edges"]), 1)


if __name__ == "__main__":
    unittest.main()
