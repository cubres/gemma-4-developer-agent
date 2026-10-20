# SPDX-License-Identifier: Apache-2.0
"""Invented files and mocked helper only. Never executes the original H0 helper."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('h0_diag_under_test', HERE / 'payload/h0_stage_diagnostic.py')
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)
ORIGINAL = HERE.parent / 'codex_gemma_h0_offline_delivery_stage_20261020/bundle'


class InventedFixtures(unittest.TestCase):
    def setUp(self):
        # Retained tiny fixture directory; no removal, notebook or real admission is created.
        self.base = Path(tempfile.mkdtemp(prefix='h0_diag_source_fixture_'))
        self.eid = 'a' * 32
        self.work = self.base / ('h0_private_' + self.eid)
        self.work.mkdir(mode=0o700)
        self.output = self.work / 'private_output'
        self.output.mkdir()

    def observe(self):
        with patch.object(diag, 'TMP_ROOT', self.base):
            return diag.observe_stage(self.eid)

    def write(self, index, value=None):
        name, _, shape, _ = diag.MILESTONES[index]
        if value is None:
            value = [] if shape is list else {'invented': 'PRIVATE_SECRET /arbitrary/private/path'}
        (self.output / name).write_text(json.dumps(value))

    def test_missing_then_each_monotone_milestone(self):
        self.assertEqual(self.observe(), 'NO_CORE_ATTEMPT_FILE')
        for i, (_, _, _, expected) in enumerate(diag.MILESTONES):
            self.write(i)
            self.assertEqual(self.observe(), expected)

    def test_traversal_and_nonprivate_directory_rejected(self):
        with self.assertRaises(ValueError):
            diag.observe_stage('../PRIVATE_SECRET')
        self.work.chmod(0o755)
        with self.assertRaises(ValueError):
            self.observe()

    def test_symlink_output_and_leaf_rejected_without_read(self):
        outside = self.base / 'outside_secret'
        outside.write_text('PRIVATE_SECRET')
        leaf = self.output / diag.MILESTONES[0][0]
        leaf.symlink_to(outside)
        with patch.object(diag.os, 'read') as read:
            with self.assertRaises(OSError):
                self.observe()
            read.assert_not_called()
        other = 'b' * 32
        (self.base / ('h0_private_' + other)).symlink_to(self.work, target_is_directory=True)
        with patch.object(diag, 'TMP_ROOT', self.base):
            with self.assertRaises(OSError):
                diag.observe_stage(other)
        third = self.base / ('h0_private_' + 'c' * 32)
        third.mkdir(mode=0o700)
        (third / 'private_output').symlink_to(self.output, target_is_directory=True)
        with patch.object(diag, 'TMP_ROOT', self.base):
            with self.assertRaises(OSError):
                diag.observe_stage('c' * 32)

    def test_oversize_partial_duplicates_and_holes_rejected(self):
        leaf = self.output / diag.MILESTONES[0][0]
        leaf.write_bytes(b'x' * (diag.MILESTONES[0][1] + 1))
        with patch.object(diag.os, 'read') as read:
            with self.assertRaises(ValueError):
                self.observe()
            read.assert_not_called()
        for raw in ('{"partial":', '{"same":1,"same":2}', '{"bad":NaN}'):
            leaf.write_text(raw)
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                self.observe()
        leaf.write_text('{}')
        self.write(2)
        with self.assertRaises(ValueError):
            self.observe()

    def test_original_source_pins_and_no_mutation(self):
        input_root = self.base / 'input'
        bundle = input_root / 'original_v1'
        bundle.mkdir(parents=True)
        before = {}
        for name, expected in diag.PINS.items():
            raw = (ORIGINAL / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            before[name] = raw
            (bundle / name).write_bytes(raw)
        # Deliberately incomplete invalid certificate: never passed to an actual helper.
        c = json.dumps({'status': 'ROOT_AUTHORIZE_DISTINCT_OFFLINE_H0_CANARY',
                        'coordinator': 'root', 'source_id': 12718547, 'source_version': 1,
                        'experiment_id': self.eid})
        argv = ['--execute', '--bundle-root', str(bundle), '--manifest-sha256', diag.MANIFEST_SHA,
                '--certificate-json', c]
        with patch.object(diag, 'INPUT_ROOT', input_root):
            self.assertEqual(diag.validated_request(argv), (bundle.resolve(), self.eid))
            (bundle / 'private_h0_flat_bootstrap.py').write_bytes(b'INVENTED_CORRUPTION')
            with self.assertRaises(ValueError):
                diag.validated_request(argv)
        self.assertTrue(all((ORIGINAL / name).read_bytes() == raw for name, raw in before.items()))

    def test_remaining_aggregate_budget_checked_before_read(self):
        for i in range(3):
            self.write(i, [] if diag.MILESTONES[i][2] is list else {})
        consumed = sum((self.output / diag.MILESTONES[i][0]).stat().st_size for i in range(3))
        limit = 64
        remaining = limit - consumed
        offending = self.output / diag.MILESTONES[3][0]
        offending.write_text(json.dumps({'x': 'z' * remaining}))
        offending_inode = offending.stat().st_ino
        reads = []
        original_read = os.read

        def counted_read(fd, size):
            inode = os.fstat(fd).st_ino
            data = original_read(fd, size)
            reads.append((inode, size, len(data)))
            return data

        with patch.object(diag, 'MAX_TOTAL_BYTES', limit), patch.object(diag.os, 'read', side_effect=counted_read):
            with self.assertRaises(ValueError):
                self.observe()
        self.assertFalse(any(inode == offending_inode for inode, _, _ in reads))
        self.assertEqual(sum(n for _, _, n in reads), consumed)
        self.assertLessEqual(sum(requested for _, requested, _ in reads), limit)

        exact = ('{"x":"' + 'z' * (remaining - 8) + '"}').encode()
        self.assertEqual(len(exact), remaining)
        offending.write_bytes(exact)
        reads.clear()
        with patch.object(diag, 'MAX_TOTAL_BYTES', limit), patch.object(diag.os, 'read', side_effect=counted_read):
            self.assertEqual(self.observe(), 'RUNTIME_MANIFEST_PRESENT')
        self.assertEqual(sum(n for _, _, n in reads), limit)
        self.assertEqual(sum(requested for _, requested, _ in reads), limit)

    def test_failed_helper_once_exact_args_private_output_and_exitcode(self):
        argv = ['--execute', '--certificate-json', 'PRIVATE_SECRET']
        fake_root = Path('/invented/original_v1')
        captured = io.StringIO()
        with patch.object(diag, 'validated_request', return_value=(fake_root, self.eid)), \
             patch.object(diag, 'observe_stage', side_effect=ValueError('PRIVATE_SECRET /private/path')), \
             patch.object(diag.subprocess, 'run', return_value=types.SimpleNamespace(returncode=17)) as run, \
             contextlib.redirect_stdout(captured):
            self.assertEqual(diag.run_diagnostic(argv), 17)
        run.assert_called_once_with(
            [diag.sys.executable, '-I', '-S', str(fake_root / 'private_h0_flat_bootstrap.py'), *argv],
            stdout=diag.subprocess.DEVNULL, stderr=diag.subprocess.DEVNULL, check=False)
        line = captured.getvalue()
        self.assertEqual(line, 'H0_DIAGNOSTIC_STAGE=OBSERVER_REJECTED\n')
        self.assertLessEqual(len(line.encode()), 80)
        self.assertNotIn('PRIVATE_SECRET', line)
        with patch.object(diag, 'validated_request', side_effect=ValueError('PRIVATE_SECRET')), \
             patch.object(diag, 'invoke_helper') as helper, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(diag.run_diagnostic(argv), 2)
            helper.assert_not_called()


if __name__ == '__main__':
    unittest.main()
