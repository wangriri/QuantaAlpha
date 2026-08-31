from __future__ import annotations

import unittest

from quantaalpha.pipeline.evolution.controller import EvolutionConfig, EvolutionController
from quantaalpha.pipeline.evolution.trajectory import RoundPhase, StrategyTrajectory


class EvolutionControllerTest(unittest.TestCase):
    def test_max_rounds_limits_total_rounds_in_serial_mode(self):
        controller = EvolutionController(
            EvolutionConfig(
                num_directions=2,
                max_rounds=3,
                mutation_enabled=True,
                crossover_enabled=True,
                crossover_n=1,
                crossover_size=2,
                fresh_start=True,
            )
        )
        controller.mutation_op.generate_mutation_prompt_suffix = lambda parent: ""
        controller.crossover_op.generate_crossover_prompt_suffix = lambda parents: ""

        observed_rounds = []
        while True:
            task = controller.get_next_task()
            if task is None:
                break

            observed_rounds.append((task["round_idx"], task["phase"]))
            self.assertLess(task["round_idx"], 3)

            trajectory = StrategyTrajectory(
                trajectory_id=StrategyTrajectory.generate_id(
                    task["direction_id"],
                    task["round_idx"],
                    task["phase"],
                    timestamp=f"test-{len(observed_rounds)}",
                ),
                direction_id=task["direction_id"],
                round_idx=task["round_idx"],
                phase=task["phase"],
                hypothesis=f"hypothesis {len(observed_rounds)}",
                factors=[{"name": "factor", "expression": "$return"}],
                backtest_metrics={"RankIC": 0.1},
                parent_ids=[p.trajectory_id for p in task.get("parent_trajectories", [])],
            )
            controller.report_task_complete(task, trajectory)

        self.assertEqual(
            [round_idx for round_idx, _phase in observed_rounds],
            [0, 0, 1, 1, 2],
        )
        self.assertEqual(
            [phase for _round_idx, phase in observed_rounds],
            [
                RoundPhase.ORIGINAL,
                RoundPhase.ORIGINAL,
                RoundPhase.MUTATION,
                RoundPhase.MUTATION,
                RoundPhase.CROSSOVER,
            ],
        )
        self.assertTrue(controller.is_complete())


if __name__ == "__main__":
    unittest.main()
