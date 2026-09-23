"""Model discovery must use live provider data without leaking saved credentials."""
import asyncio
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError


def load_app():
    path = Path(__file__).resolve().parents[1] / 'frontend-v2/backend/app.py'
    spec = importlib.util.spec_from_file_location('model_list_backend', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProviderModelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = load_app()

    def test_live_ids_deduplicated_with_base_path_preserved(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(
            b'{"data":[{"id":"new-model"},{"id":"deepseek-flash"},{"id":"new-model"},{"id":null}]}')
        with patch('urllib.request.build_opener', return_value=opener):
            ids = self.backend._fetch_provider_models('https://api.deepseek.com/v1/', 'secret')
        self.assertEqual(ids, ['deepseek-flash', 'new-model'])
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'https://api.deepseek.com/v1/models')

    def test_provider_error_does_not_leak_response_or_key(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError('https://example.com', 401, 'secret', {}, None)
        with patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaises(self.backend.HTTPException) as error:
                self.backend._fetch_provider_models('https://example.com', 'secret')
        self.assertEqual(error.exception.status_code, 502)
        self.assertNotIn('secret', error.exception.detail)

    def test_invalid_or_empty_payload_rejected(self):
        for payload in (b'{}', b'{"data":[]}', b'not-json'):
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = io.BytesIO(payload)
            with patch('urllib.request.build_opener', return_value=opener):
                with self.assertRaises(self.backend.HTTPException):
                    self.backend._fetch_provider_models('https://example.com', 'secret')

    def test_saved_key_used_only_for_saved_endpoint(self):
        env = {'OPENAI_BASE_URL': 'https://api.deepseek.com', 'OPENAI_API_KEY': 'saved-secret'}
        with patch.object(self.backend, '_load_dotenv_dict', return_value=env), patch.object(
            self.backend, '_fetch_provider_models', return_value=['deepseek-flash']
        ) as fetch:
            result = asyncio.run(self.backend.list_provider_models(self.backend.ModelListRequest()))
            self.assertEqual(result.data['models'], ['deepseek-flash'])
            fetch.assert_called_once_with('https://api.deepseek.com', 'saved-secret')
            with self.assertRaises(self.backend.HTTPException):
                asyncio.run(self.backend.list_provider_models(
                    self.backend.ModelListRequest(baseUrl='https://other.example')))
            self.assertEqual(fetch.call_count, 1)

    def test_explicit_new_credentials_work_without_saving(self):
        with patch.object(self.backend, '_load_dotenv_dict', return_value={}), patch.object(
            self.backend, '_fetch_provider_models', return_value=['model-a']
        ) as fetch:
            asyncio.run(self.backend.list_provider_models(self.backend.ModelListRequest(
                baseUrl='https://provider.example/v1', apiKey='new-secret')))
            fetch.assert_called_once_with('https://provider.example/v1', 'new-secret')


if __name__ == '__main__':
    unittest.main()
