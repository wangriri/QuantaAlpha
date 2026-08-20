from __future__ import annotations

import os
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

from quantaalpha.pipeline.planning import _parse_directions
from quantaalpha.prompting import (
    PROMPT_PACK_ENV,
    configure_prompting,
    get_prompt_pack_metadata,
    resolve_factor_prompts_path,
    resolve_planning_prompt_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / path).read_text(encoding="utf-8"))


class PromptTemplateTest(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop(PROMPT_PACK_ENV, None)

    def test_prompt_pack_paths_resolve_for_ab_testing(self) -> None:
        zh_meta = get_prompt_pack_metadata("zh_quant_v1")
        en_meta = get_prompt_pack_metadata("en_default")

        self.assertEqual(zh_meta["output_language"], "zh-CN")
        self.assertEqual(en_meta["output_language"], "en")

        zh_planning = resolve_planning_prompt_path("planning_prompts.yaml", "zh_quant_v1")
        en_planning = resolve_planning_prompt_path("planning_prompts.yaml", "en_default")
        zh_factor = resolve_factor_prompts_path(
            PROJECT_ROOT / "quantaalpha" / "factors" / "prompts" / "prompts.yaml",
            "zh_quant_v1",
        )
        en_factor = resolve_factor_prompts_path(
            PROJECT_ROOT / "quantaalpha" / "factors" / "prompts" / "prompts.yaml",
            "en_default",
        )

        self.assertTrue(zh_planning.exists())
        self.assertTrue(en_planning.exists())
        self.assertTrue(zh_factor.exists())
        self.assertTrue(en_factor.exists())
        self.assertEqual(zh_planning.name, "planning_prompts.yaml")
        self.assertEqual(en_planning.name, "planning_prompts_en_default.yaml")
        self.assertEqual(zh_factor.name, "prompts.yaml")
        self.assertEqual(en_factor.name, "prompts_en_default.yaml")

    def test_env_prompt_pack_overrides_config_for_one_off_ab_runs(self) -> None:
        os.environ[PROMPT_PACK_ENV] = "en_default"

        metadata = configure_prompting({"pack": "zh_quant_v1"})
        planning = resolve_planning_prompt_path("planning_prompts.yaml")

        self.assertEqual(metadata["name"], "en_default")
        self.assertEqual(planning.name, "planning_prompts_en_default.yaml")

    def test_planning_prompt_uses_plain_json_contract(self) -> None:
        prompts = load_yaml("quantaalpha/pipeline/prompts/planning_prompts.yaml")

        system_prompt = prompts["system"].format(initial_direction="量价反转", n=2)
        user_prompt = prompts["user"].format(initial_direction="量价反转", n=2)
        output_format = prompts["output_format"].replace("{n}", "2")

        combined = system_prompt + user_prompt + output_format
        self.assertNotIn("DATA_CONTEXT", combined)
        self.assertNotIn("FACTOR_LIBRARY", combined)
        self.assertNotIn("ENVIRONMENT_CONTEXT", combined)
        self.assertNotIn("```", output_format)
        self.assertIn('"directions"', output_format)

        parsed = _parse_directions('{"directions": ["方向一", "方向二"]}', 2)
        self.assertEqual(parsed, ["方向一", "方向二"])

    def test_alpha_agent_hypothesis_prompts_render_without_missing_context(self) -> None:
        prompts = load_yaml("quantaalpha/factors/prompts/prompts.yaml")
        env = Environment(undefined=StrictUndefined)

        system_prompt = env.from_string(prompts["hypothesis_gen"]["system_prompt"]).render(
            targets="factors",
            scenario="基于日频量价数据挖掘因子。",
            hypothesis_output_format=prompts["hypothesis_output_format"],
            hypothesis_specification=prompts["factor_hypothesis_specification"],
        )
        user_prompt = env.from_string(prompts["hypothesis_gen"]["user_prompt"]).render(
            targets="factors",
            hypothesis_and_feedback="",
            RAG=None,
            round=0,
        )

        combined = system_prompt + user_prompt
        self.assertNotIn("DATA_CONTEXT", combined)
        self.assertNotIn("FACTOR_LIBRARY", combined)
        self.assertNotIn("ENVIRONMENT_CONTEXT", combined)
        self.assertIn('"hypothesis"', combined)
        self.assertIn('"concise_knowledge"', combined)

    def test_alpha_agent_factor_prompt_keeps_machine_keys_and_expression_syntax(self) -> None:
        prompts = load_yaml("quantaalpha/factors/prompts/prompts.yaml")
        env = Environment(undefined=StrictUndefined)

        system_prompt = env.from_string(prompts["hypothesis2experiment"]["system_prompt"]).render(
            targets="factors",
            scenario="基于日频量价数据挖掘因子。",
            experiment_output_format=prompts["factor_experiment_output_format"],
        )
        user_prompt = env.from_string(prompts["hypothesis2experiment"]["user_prompt"]).render(
            targets="factors",
            target_hypothesis="研究异常放量后是否存在短期反转。",
            hypothesis_and_feedback="No previous hypothesis and feedback available.",
            function_lib_description=prompts["function_lib_description"],
            target_list=[],
            RAG=None,
            expression_duplication=None,
        )

        combined = system_prompt + user_prompt
        self.assertNotIn("DATA_CONTEXT", combined)
        self.assertNotIn("FACTOR_LIBRARY", combined)
        self.assertNotIn("ENVIRONMENT_CONTEXT", combined)
        self.assertIn('"description"', combined)
        self.assertIn('"variables"', combined)
        self.assertIn('"formulation"', combined)
        self.assertIn('"expression"', combined)
        self.assertIn("$close", combined)
        self.assertIn("TS_MEAN", combined)


if __name__ == "__main__":
    unittest.main()
