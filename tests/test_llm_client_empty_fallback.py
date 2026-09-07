import unittest
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
                            delta=SimpleNamespace(content=None),
                            finish_reason=None,
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=None),
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

    def test_deepseek_v4_flash_empty_stream_falls_back_to_deepseek_chat(self):
        api = object.__new__(APIBackend)
        api.use_chat_cache = False
        api.dump_chat_cache = False
        api.use_llama2 = False
        api.use_gcr_endpoint = False
        api.chat_model = "deepseek-v4-flash"
        api.reasoning_model = "deepseek-v4-flash"
        api.chat_model_map = {}
        api.chat_stream = True
        api.chat_seed = None
        api.base_url = "https://api.deepseek.com"
        api.chat_client = _FakeChatClient()

        with patch.object(LLM_SETTINGS, "chat_fallback_model", ""):
            response, finish_reason = api._create_chat_completion_inner_function(
                [{"role": "user", "content": "return JSON"}],
                reasoning_flag=False,
                json_mode=True,
            )

        self.assertEqual(response, '{"ok": true}')
        self.assertEqual(finish_reason, "stop")
        calls = api.chat_client.chat.completions.calls
        self.assertEqual([call["model"] for call in calls], ["deepseek-v4-flash", "deepseek-chat"])
        self.assertTrue(calls[0]["stream"])
        self.assertFalse(calls[1]["stream"])


if __name__ == "__main__":
    unittest.main()
