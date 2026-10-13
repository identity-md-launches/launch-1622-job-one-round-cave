import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch

import zto_archive as archive


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.obs = archive.path.read_json(str(archive.DEFAULT_SNAPSHOT))

    def test_real_snapshot_has_one_pin(self):
        report = archive.report_snapshot(self.obs)
        self.assertEqual(report['schema'], archive.SCHEMA)
        self.assertEqual(report['selected']['block'], self.obs['base']['block'])
        self.assertEqual(report['selected']['source'], self.obs['base']['source'])
        self.assertEqual(report['attempts'], [])

    def test_tampered_snapshot_refused(self):
        bad = copy.deepcopy(self.obs)
        bad['base']['initialize']['topics'][1] = '0x' + '11' * 32
        with self.assertRaises(ValueError):
            archive.validate_snapshot(bad)

    def test_fallback_returns_only_complete_second_source(self):
        expected = copy.deepcopy(self.obs)
        with patch.object(archive.path, 'capture', side_effect=[ValueError('history unavailable'), expected]) as cap:
            observation, attempts = archive.capture_one(('https://one.example', 'https://two.example'), 'finalized', 1)
        self.assertEqual(observation, expected)
        self.assertEqual([a['status'] for a in attempts], ['unavailable', 'selected'])
        self.assertEqual(cap.call_count, 2)

    def test_all_failures_are_honest(self):
        with patch.object(archive.path, 'capture', side_effect=ValueError('no archive')):
            with self.assertRaisesRegex(ValueError, 'no endpoint produced'):
                archive.capture_one(('https://one.example',), 'finalized', 1)

    def test_offline_cli_never_constructs_rpc(self):
        with patch.object(archive.path, 'capture', side_effect=AssertionError('network forbidden')):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(archive.main(['--snapshot', str(archive.DEFAULT_SNAPSHOT)]), 0)
        self.assertEqual(json.loads(out.getvalue())['mode'], 'offline_validation')

    def test_invalid_mode_and_radius_fail(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(archive.main(['--live', '--word-radius', '5']), 1)
            self.assertEqual(archive.main(['--snapshot', str(archive.DEFAULT_SNAPSHOT), '--save-observation', 'x.json']), 1)


if __name__ == '__main__':
    unittest.main()
