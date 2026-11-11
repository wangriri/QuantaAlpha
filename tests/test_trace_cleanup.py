import asyncio
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import HTTPException

app = importlib.import_module('frontend-v2.backend.app')


class TraceCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.traces = self.root / 'data/run_traces'
        self.run = self.traces / 'run_20200101_010101'
        self.run.mkdir(parents=True)
        (self.run / '00_run_summary.json').write_text(json.dumps({'config_path': '/old/workspace_exp_20200101_010100/experiment_override.yaml'}))
        self.patches = [patch.object(app, 'PROJECT_ROOT', self.root), patch.object(app, 'TRACE_ROOT', self.traces), patch.object(app, '_trace_is_active', return_value=False)]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_delete_is_recoverable_and_keeps_library(self):
        library = self.root / 'data/factorlib/a.json'
        library.parent.mkdir(); library.write_text('keep me')
        plan = app._trace_cleanup_plan(self.run.name)
        self.assertTrue(self.run.exists())
        result = asyncio.run(app.delete_trace(self.run.name, confirm=True))
        self.assertFalse(self.run.exists())
        recovery = Path(result.data['recoveryPath'])
        self.assertTrue((recovery / '00_run_summary.json').exists())
        self.assertEqual(library.read_text(), 'keep me')
        self.assertEqual(plan['libraries'], ['all_factors_library_exp_20200101_010100.json'])

    def test_confirmation_and_active_run_guards(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(app.delete_trace(self.run.name, confirm=False))
        self.assertEqual(ctx.exception.status_code, 400)
        with patch.object(app, '_trace_is_active', return_value=True):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(app.delete_trace(self.run.name, confirm=True))
            self.assertEqual(ctx.exception.status_code, 409)
        self.assertTrue(self.run.exists())

    def test_path_escape_and_symlinks_rejected(self):
        with self.assertRaises(HTTPException): app._trace_cleanup_plan('run_../outside')
        (self.traces / 'run_link').symlink_to(self.run, target_is_directory=True)
        with self.assertRaises(HTTPException): app._trace_cleanup_plan('run_link')

    def test_saved_library_wins_over_timestamp_and_shared_run_is_retained(self):
        libdir = self.root / 'data/factorlib'; libdir.mkdir()
        first = libdir / 'all_factors_library_custom.json'; first.write_text('{"factors": {}}')
        second = libdir / 'all_factors_library_shared.json'; second.write_text('{"factors": {}}')
        task = self.run / 'round_00_original/task_000'; task.mkdir(parents=True)
        (task / '08_saved_factors.json').write_text(json.dumps({'library_path': str(first)}))
        self.assertEqual(app._trace_library_names(self.run), {first.name})
        self.assertIn('run_trace', [i['category'] for i in app._build_library_cleanup_plan(first.name)['items']])
        (task / '10_saved_factors.json').write_text(json.dumps({'library_path': str(second)}))
        self.assertNotIn('run_trace', [i['category'] for i in app._build_library_cleanup_plan(first.name)['items']])


if __name__ == '__main__': unittest.main()
