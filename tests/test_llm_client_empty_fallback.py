import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from quantaalpha.llm.client import APIBackend
from quantaalpha.llm.config import LLM_SETTINGS


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"] == "deepseek-v4-flash":
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=None, reasoning_content="先分析输入格式。"),
                            finish_reason=None,
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=None, reasoning_content="继续推导但没有输出正文。"),
                            finish_reason="length",
                        )
                    ]
                ),
            ]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ok": true}'),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(total_tokens=10, prompt_tokens=8, completion_tokens=2),
        )


class _FakeChatClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


class LLMClientEmptyFallbackTest(unittest.TestCase):
    def test_deepseek_endpoint_coerces_openai_default_model_names(self):
        api = object.__new__(APIBackend)
        api.base_url = "https://api.deepseek.com"
        api.chat_api_base = ""

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(api._coerce_provider_model("gpt-4-turbo"), "deepseek-v4-flash")
            self.assertEqual(api._coerce_provider_model(""), "deepseek-v4-flash")
            self.assertEqual(api._coerce_provider_model("deepseek-chat"), "deepseek-chat")

    def test_deepseek_endpoint_uses_configured_chat_model_for_openai_default(self):
        api = object.__new__(APIBackend)
        api.base_url = "https://api.deepseek.com"
        api.chat_api_base = ""

        with patch.dict("os.environ", {"CHAT_MODEL": "deepseek-chat"}, clear=True):
            self.assertEqual(api._coerce_provider_model("gpt-4-turbo"), "deepseek-chat")

    def test_deepseek_chat_enables_thinking_by_default(self):
        api = object.__new__(APIBackend)
        api.base_url = "https://api.deepseek.com"
        api.chat_api_base = ""

        with patch.object(LLM_SETTINGS, "deepseek_disable_thinking", False):
            self.assertEqual(
                api._build_provider_kwargs(
                    model="deepseek-v4-flash",
                    reasoning_flag=False,
                    tag="AlphaAgentHypothesisGen",
                ),
                {"extra_body": {"thinking": {"type": "enabled"}}},
            )

    def test_deepseek_factor_generation_uses_low_reasoning_effort(self):
        api = object.__new__(APIBackend)
        api.base_url = "https://api.deepseek.com"
        api.chat_api_base = ""

        with (
            patch.object(LLM_SETTINGS, "deepseek_disable_thinking", False),
            patch.object(LLM_SETTINGS, "deepseek_factor_generation_reasoning_effort", "low"),
        ):
            self.assertEqual(
                api._build_provider_kwargs(
                    model="deepseek-v4-flash",
                    reasoning_flag=False,
                    tag="AlphaAgentHypothesis2FactorExpression",
                ),
                {
                    "extra_body": {"thinking": {"type": "enabled"}},
                    "reasoning_effort": "low",
                },
            )

    def test_deepseek_thinking_can_still_be_disabled(self):
        api = object.__new__(APIBackend)
        api.base_url = "https://api.deepseek.com"
        api.chat_api_base = ""

        with patch.object(LLM_SETTINGS, "deepseek_disable_thinking", True):
            self.assertEqual(
                api._build_provider_kwargs(
                    model="deepseek-v4-flash",
                    reasoning_flag=False,
                    tag="AlphaAgentHypothesis2FactorExpression",
                ),
                {"extra_body": {"thinking": {"type": "disabled"}}},
            )
            self.assertEqual(
                api._build_provider_kwargs(
                    model="deepseek-reasoner",
                    reasoning_flag=False,
                    tag="AlphaAgentHypothesis2FactorExpression",
                ),
                {},
            )

    def test_non_deepseek_endpoint_does_not_add_provider_kwargs(self):
        api = object.__new__(APIBackend)
        api.base_url = "https://api.openai.com/v1"
        api.chat_api_base = ""

        with patch.object(LLM_SETTINGS, "deepseek_disable_thinking", False):
            self.assertEqual(
                api._build_provider_kwargs(
                    model="gpt-4-turbo",
                    reasoning_flag=False,
                    tag="AlphaAgentHypothesis2FactorExpression",
                ),
                {},
            )

    def test_tag_specific_openai_endpoint_keeps_gpt_model_under_deepseek_default(self):
        api = object.__new__(APIBackend)
        api.base_url = "https://api.deepseek.com"
        api.chat_api_base = ""

        self.assertEqual(
            api._coerce_provider_model("gpt-5.5", "https://api.openai.com/v1"),
            "gpt-5.5",
        )
        self.assertEqual(
            api._build_provider_kwargs(
                model="gpt-5.5",
                reasoning_flag=False,
                tag="AlphaAgentHypothesis2FactorExpression",
                endpoint="https://api.openai.com/v1",
            ),
            {},
        )

    def test_deepseek_v4_flash_empty_stream_raises_without_fallback(self):
        api = object.__new__(APIBackend)
        api.use_chat_cache = False
        api.dump_chat_cache = False
        api.use_llama2 = False
        api.use_gcr_endpoint = False
        api.chat_model = "deepseek-v4-flash"
        api.reasoning_model = "deepseek-v4-flash"
        api.chat_model_map = {}
        api.chat_base_url_map = {}
        api.chat_api_key_map = {}
        api.chat_stream = True
        api.chat_seed = None
        api.base_url = "https://api.deepseek.com"
        api.chat_api_key = "test-key"
        api.chat_client = _FakeChatClient()

        with TemporaryDirectory() as tmpdir:
            with (
                patch.object(LLM_SETTINGS, "chat_fallback_model", ""),
                patch.dict("os.environ", {"QUANTAALPHA_ACTIVE_TRACE_DIR": tmpdir}, clear=False),
            ):
                with self.assertRaisesRegex(RuntimeError, "reasoning_content_preview=.*继续推导"):
                    api._create_chat_completion_inner_function(
                        [{"role": "user", "content": "return JSON"}],
                        reasoning_flag=False,
                        json_mode=True,
                    )

            reasoning_dir = Path(tmpdir) / "99_reasoning_content"
            txt_files = list(reasoning_dir.glob("*.txt"))
            json_files = list(reasoning_dir.glob("*.json"))
            self.assertEqual(len(txt_files), 1)
            self.assertEqual(len(json_files), 1)
            self.assertEqual(txt_files[0].read_text(encoding="utf-8"), "先分析输入格式。继续推导但没有输出正文。")
            self.assertIn("reasoning_content", json_files[0].read_text(encoding="utf-8"))

        calls = api.chat_client.chat.completions.calls
        self.assertEqual([call["model"] for call in calls], ["deepseek-v4-flash"])
        self.assertTrue(calls[0]["stream"])
        self.assertEqual(calls[0]["extra_body"], {"thinking": {"type": "enabled"}})


if __name__ == "__main__":
    unittest.main()
