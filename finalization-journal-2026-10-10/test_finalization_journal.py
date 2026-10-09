"""Invented offline boundary controls; retained test artifacts, no task runs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from finalization_journal import FinalizationJournal, Observation, canonical, inspect_journal


class Clock:
    def __init__(self): self.value = 100.0
    def __call__(self): return self.value
    def advance(self, v): self.value += v


def observation(**updates):
    xml = b'<testsuite tests="1"><testcase name="invented_control"/></testsuite>'
    values = dict(exit_code=0, timed_out=False, patch_sha256=hashlib.sha256(b'invented patch').hexdigest(),
                  patch_bytes=14, retained_xml=xml, cat_xml=xml, validator_xml=xml, strict_validator_ok=True)
    values.update(updates)
    return Observation(**values)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = Path(tempfile.mkdtemp(prefix='PRIVATE_TEST_ARTIFACTS_', dir=Path(__file__).parent))
        self.clock = Clock()
        self.j = FinalizationJournal(self.artifacts/'finalize-evidence-case', absolute_deadline=130, clock=self.clock)

    def successful_capture(self):
        t = self.j.begin(240); self.clock.advance(2)
        self.assertTrue(self.j.returned(t, observation()))

    def test_timeout_recomputed_after_durable_start_and_before_command(self):
        t = self.j.begin(240)
        self.assertEqual(t.timeout_seconds, 25)
        self.clock.advance(3)
        self.assertEqual(self.j.command_timeout(t), 22)

    def test_start_is_durable_before_any_verifier_runs(self):
        self.j.begin()
        a = inspect_journal(self.j.path)
        self.assertEqual(a['status'], 'UNFINISHED')
        self.assertTrue(a['durable_start'])
        self.assertFalse(a['return_observed'])

    def test_atomic_event_and_staging_bytes_match(self):
        self.j.begin()
        a, b = self.j.path/'event_000001.json', self.j.path/'stage_000001.json'
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(a.stat().st_ino, b.stat().st_ino)

    def test_link_failure_leaves_only_unpublished_staging_and_fences(self):
        with patch('finalization_journal.os.link', side_effect=OSError('PRIVATE_ERROR')):
            with self.assertRaises(OSError): self.j.begin()
        a = inspect_journal(self.j.path)
        self.assertEqual(a['status'], 'NO_DURABLE_START')
        self.assertEqual(a['unpublished_staging_count'], 1)
        self.assertTrue(self.j.poisoned)
        with self.assertRaises(RuntimeError): self.j.begin()

    def test_fsync_failure_cannot_return_start_ticket(self):
        with patch('finalization_journal.os.fsync', side_effect=OSError('PRIVATE_ERROR')):
            with self.assertRaises(OSError): self.j.begin()
        self.assertEqual(inspect_journal(self.j.path)['status'], 'NO_DURABLE_START')
        self.assertTrue(self.j.poisoned)

    def test_existing_journal_or_event_is_never_overwritten(self):
        with self.assertRaises(FileExistsError):
            FinalizationJournal(self.j.path, absolute_deadline=130, clock=self.clock)
        existing=self.j.path/'event_000001.json'; existing.write_bytes(b'preserved existing ordinary evidence')
        with self.assertRaises(FileExistsError): self.j.begin()
        self.assertEqual(existing.read_bytes(), b'preserved existing ordinary evidence')

    def test_success_requires_distinct_cleanup_receipt(self):
        self.successful_capture()
        self.assertEqual(inspect_journal(self.j.path)['status'], 'UNFINISHED')
        out=self.j.close(cleanup_verified=True, survivor_count=0)
        self.assertEqual(out['status'], 'COMMITTED_CAPTURE')
        a=inspect_journal(self.j.path)
        self.assertEqual(a['status'], 'COMMITTED_CAPTURE')
        self.assertIsNone(a['native_tests_passed']); self.assertIsNone(a['official_score'])
        self.assertEqual(a['native_compatibility'],'HOLD_UNVERIFIED')

    def test_unknown_cleanup_is_hold(self):
        self.successful_capture()
        self.assertEqual(self.j.close(cleanup_verified=False,survivor_count=None)['status'],'HOLD')

    def test_survivor_is_hold_even_after_passing_xml(self):
        self.successful_capture()
        self.assertEqual(self.j.close(cleanup_verified=True,survivor_count=1)['status'],'HOLD')

    def test_inconsistent_xml_is_not_complete_capture(self):
        t=self.j.begin()
        self.assertFalse(self.j.returned(t,observation(cat_xml=b'PRIVATE_DIFFERENT_XML')))
        self.assertEqual(self.j.close(cleanup_verified=True,survivor_count=0)['status'],'HOLD')
        self.assertNotIn('PRIVATE_DIFFERENT_XML',json.dumps(inspect_journal(self.j.path)))

    def test_zero_exit_without_xml_or_patch_cannot_complete(self):
        t=self.j.begin()
        self.assertFalse(self.j.returned(t,observation(patch_bytes=0,retained_xml=b'',cat_xml=b'',validator_xml=b'')))
        self.assertEqual(self.j.close(cleanup_verified=True,survivor_count=0)['status'],'HOLD')

    def test_nonzero_exit_can_commit_negative_capture_without_validator(self):
        t=self.j.begin()
        self.assertTrue(self.j.returned(t,observation(exit_code=1,cat_xml=b'',validator_xml=b'',strict_validator_ok=False)))
        self.assertEqual(self.j.close(cleanup_verified=True,survivor_count=0)['status'],'COMMITTED_CAPTURE')
        row=json.loads((self.j.path/'event_000005.json').read_bytes())
        self.assertFalse(row['values']['passed_test_observation'])

    def test_strict_validator_false_never_means_test_success(self):
        t=self.j.begin();self.j.returned(t,observation(strict_validator_ok=False))
        self.j.close(cleanup_verified=True,survivor_count=0)
        row=json.loads((self.j.path/'event_000005.json').read_bytes())
        self.assertFalse(row['values']['passed_test_observation'])

    def test_timed_out_command_never_means_test_success(self):
        t=self.j.begin();self.j.returned(t,observation(timed_out=True))
        self.j.close(cleanup_verified=True,survivor_count=0)
        row=json.loads((self.j.path/'event_000005.json').read_bytes())
        self.assertFalse(row['values']['passed_test_observation'])

    def test_capture_deadline_interrupts_after_durable_return(self):
        t=self.j.begin();self.clock.advance(31)
        self.assertFalse(self.j.returned(t,observation()))
        a=inspect_journal(self.j.path)
        self.assertTrue(a['return_observed']);self.assertFalse(a['capture_observed'])
        self.assertEqual(a['status'],'HOLD')

    def test_command_start_after_budget_exhaustion_is_denied(self):
        t=self.j.begin();self.clock.advance(25)
        self.assertIsNone(self.j.command_timeout(t))
        self.assertEqual(inspect_journal(self.j.path)['status'],'HOLD')

    def test_durable_start_consuming_window_returns_no_ticket(self):
        original=self.j._fsync_directory
        def advance(): original();self.clock.advance(15)
        with patch.object(self.j,'_fsync_directory',side_effect=advance):
            self.assertIsNone(self.j.begin())
        self.assertEqual(inspect_journal(self.j.path)['status'],'HOLD')

    def test_partial_future_event_is_rejected(self):
        self.j.begin()
        with (self.j.path/'event_000002.json').open('xb') as f:f.write(b'{')
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_gap_or_hash_mismatch_is_rejected(self):
        self.j.begin()
        row={'schema':'original_finalization_journal_v1','index':2,'previous_sha256':'f'*64,'stage':'RETURN','values':{}}
        with (self.j.path/'event_000002.json').open('xb') as f:f.write(canonical(row))
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_untrusted_terminal_string_never_leaks(self):
        row={'schema':'original_finalization_journal_v1','index':1,'previous_sha256':'0'*64,'stage':'COMMIT','values':{'status':'PRIVATE_TASK_SECRET'}}
        with (self.j.path/'event_000001.json').open('xb') as f:f.write(canonical(row))
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_lone_well_formed_commit_is_rejected(self):
        row={'schema':'original_finalization_journal_v1','index':1,'previous_sha256':'0'*64,'stage':'COMMIT','values':{'status':'COMMITTED_CAPTURE','passed_test_observation':True,'native_compatibility':'HOLD_UNVERIFIED','official_score':None}}
        with (self.j.path/'event_000001.json').open('xb') as f:f.write(canonical(row))
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_capture_before_return_is_rejected(self):
        self.j.begin()
        previous=hashlib.sha256((self.j.path/'event_000001.json').read_bytes()).hexdigest()
        row={'schema':'original_finalization_journal_v1','index':2,'previous_sha256':previous,'stage':'CAPTURE','values':{}}
        with (self.j.path/'event_000002.json').open('xb') as f:f.write(canonical(row))
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_extra_private_field_is_rejected(self):
        row={'schema':'original_finalization_journal_v1','index':1,'previous_sha256':'0'*64,'stage':'START','values':{'planned_timeout_upper_bound_seconds':25,'capture_reserve_seconds':5,'private_task':'PRIVATE_SECRET'}}
        with (self.j.path/'event_000001.json').open('xb') as f:f.write(canonical(row))
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_boolean_event_index_is_rejected(self):
        row={'schema':'original_finalization_journal_v1','index':True,'previous_sha256':'0'*64,'stage':'START','values':{'planned_timeout_upper_bound_seconds':25,'capture_reserve_seconds':5}}
        with (self.j.path/'event_000001.json').open('xb') as f:f.write(canonical(row))
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_cleanup_claim_is_derived_not_trusted(self):
        row={'schema':'original_finalization_journal_v1','index':1,'previous_sha256':'0'*64,'stage':'CLEANUP','values':{'verified':False,'survivor_count':None,'clear':True}}
        with (self.j.path/'event_000001.json').open('xb') as f:f.write(canonical(row))
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_directory_inventory_cap(self):
        for i in range(257):
            with (self.j.path/('unlisted_%03d'%i)).open('x') as f:f.write('')
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_event_symlink_is_rejected(self):
        ordinary=self.artifacts/'ordinary.json'
        with ordinary.open('x') as f:f.write('{}')
        (self.j.path/'event_000001.json').symlink_to(ordinary)
        with self.assertRaises(ValueError):inspect_journal(self.j.path)

    def test_slow_commit_write_is_revoked(self):
        self.successful_capture()
        original=self.j._fsync_directory
        def delay_commit():
            original()
            if (self.j.path/'event_000005.json').exists():self.clock.advance(31)
        with patch.object(self.j,'_fsync_directory',side_effect=delay_commit):
            self.assertEqual(self.j.close(cleanup_verified=True,survivor_count=0)['status'],'HOLD')
        self.assertEqual(inspect_journal(self.j.path)['status'],'HOLD')

    def test_strict_bool_and_counter_validation_under_O(self):
        t=self.j.begin()
        for values in ({'exit_code':True},{'timed_out':1},{'strict_validator_ok':'yes'},{'patch_bytes':True},{'patch_sha256':'private'}):
            with self.assertRaises(ValueError):self.j.returned(t,observation(**values))
        with self.assertRaises(ValueError):self.j.close(cleanup_verified=1,survivor_count=0)
        with self.assertRaises(ValueError):self.j.close(cleanup_verified=True,survivor_count=True)

    def test_clock_regression_poisoned(self):
        self.j.begin();self.clock.advance(-1)
        with self.assertRaises(ValueError):self.j.now()
        self.assertTrue(self.j.poisoned)

    def test_wrong_identity_or_second_attempt_rejected(self):
        t=self.j.begin()
        from dataclasses import replace
        with self.assertRaises(ValueError):self.j.returned(replace(t),observation())
        with self.assertRaises(RuntimeError):self.j.begin()

    def test_notebook_like_output_name_rejected(self):
        for name in ('kernel-metadata.json','example.ipynb','old-source'):
            with self.assertRaises(ValueError):FinalizationJournal(self.artifacts/name,absolute_deadline=130,clock=self.clock)

    def test_bounded_xml_and_numeric_inputs(self):
        t=self.j.begin()
        with self.assertRaises(ValueError):self.j.returned(t,observation(retained_xml=b'x'*(16*1024*1024+1)))
        for value in (True,float('nan'),float('inf'),-1,0,'30'):
            with self.assertRaises(ValueError):FinalizationJournal(self.artifacts/'finalize-evidence-bad',absolute_deadline=value,clock=self.clock)


if __name__=='__main__':unittest.main()
