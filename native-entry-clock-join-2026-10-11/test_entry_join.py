"""Original invented async fixtures; never import/run organizer/model tasks.

Only the already reviewed original passive collector is loaded by exact SHA.
Fixtures are retained in fresh directories, with no destructive cleanup.
"""
from __future__ import annotations

import asyncio
import copy
import functools
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest

import entry_join as entry
import route_planner as planner

COLLECTOR_PATH=Path(os.environ.get("GEMMA_CLOCK_COLLECTOR",
    str(Path(__file__).parent.parent/"native-receipt-adapter-2026-10-11"/"clock_collector.py")))
COLLECTOR_RAW=entry.read_pin({"path":str(COLLECTOR_PATH),"sha256":entry.COLLECTOR_SHA})
COLLECTOR=entry.load_module(COLLECTOR_RAW,COLLECTOR_PATH,"reviewed_original_clock_collector_test_only")
ENTRY_SHA=entry.sha(Path(entry.__file__).read_bytes())


def protocol():
    sources=entry.REVIEWED_SOURCES
    owned={k:v for k,v in sources.items() if k in ("native_arm.py","private_junit_receipts.py","clock_collector.py")}
    owned["entry_join.py"]=ENTRY_SHA
    return {"task_ids":["toy_a","toy_b"],"repo":"invented/toy",
            "component_hashes":owned,"fresh_python_source_sha256":{k:v for k,v in sources.items() if k not in owned},
            "owned_helper_hashes":{"run_gpu_validation_candidate.py":entry.HELPER_SHA},
            "absolute_seconds_including_model_load_and_allocation_reserve":8880,
            "allocation_overhead_seconds_reserved":180,"deadline_seconds_from_first_cell":8700,
            "task_reserve_seconds":4986,"readiness_budget_seconds":3714,"session_timeout_seconds":9000,
            "reserve_arithmetic_seconds":{"phase_a":420,"arm":4536,"cleanup":30}}


class Context:
    def __init__(self):self.agent_start_time=None;self.agent_end_time=None
    @property
    def agent_elapsed_seconds(self):
        return None if self.agent_start_time is None or self.agent_end_time is None else self.agent_end_time-self.agent_start_time


def task(identity):return SimpleNamespace(task_id=identity,instance_id=identity)


class FakeSystem:
    def __init__(self,*,failure=None,missing_end=False,partial_install=False,waiting=None):
        self.result=object();self.install_result=object()
        system=self
        class Evaluator:
            async def evaluate_task(self,task,context):return await self._run_agent_sandbox(task,context)
            async def _run_agent_sandbox(self,task,context):
                context.agent_start_time=time.perf_counter()
                try:
                    if waiting is not None:
                        waiting[0].set();await waiting[1].wait()
                    await asyncio.sleep(0)
                    if failure is not None:raise failure
                    return system.result
                finally:
                    if not missing_end:context.agent_end_time=time.perf_counter()
        async def verify_task(*args,**kwargs):return system.result
        self.official=SimpleNamespace(Evaluator=Evaluator,verify_task=verify_task)
        self.originals=(Evaluator.evaluate_task,Evaluator._run_agent_sandbox,verify_task)
        def install(official,timing):
            # Original invented installer with the same three-boundary shape.
            old=official.Evaluator.evaluate_task
            @functools.wraps(old)
            async def timed_task(*args,**kwargs):return await old(*args,**kwargs)
            official.Evaluator.evaluate_task=timed_task
            if partial_install:raise system.install_failure
            old_agent=official.Evaluator._run_agent_sandbox
            @functools.wraps(old_agent)
            async def timed_agent(*args,**kwargs):return await old_agent(*args,**kwargs)
            old_verify=official.verify_task
            @functools.wraps(old_verify)
            async def timed_verify(*args,**kwargs):return await old_verify(*args,**kwargs)
            official.Evaluator._run_agent_sandbox=timed_agent;official.verify_task=timed_verify
            return system.install_result
        self.install_failure=RuntimeError("invented partial installer failure")
        self.owned=SimpleNamespace(install_timing=install);self.original_install=install
        self.collector=COLLECTOR.ClockCollector()
        self.lifecycle=entry.TimingLifecycle(self.owned,self.collector,["toy_a","toy_b"])

    def restored(self):
        return (self.owned.install_timing is self.original_install
                and (self.official.Evaluator.evaluate_task,self.official.Evaluator._run_agent_sandbox,
                     self.official.verify_task)==self.originals and self.lifecycle.restored)

    async def complete(self):
        evaluator=self.official.Evaluator()
        with self.lifecycle:
            result=self.owned.install_timing(self.official,object())
            for identity in ("toy_a","toy_b"):
                value=await evaluator.evaluate_task(task(identity),Context())
                if value is not self.result:raise AssertionError("return identity changed")
        return result


class EntryTests(unittest.TestCase):
    def setUp(self):
        parent=Path(os.environ.get("ENTRY_TEST_OUTPUT",str(Path(__file__).parent/"retained-invented-fixtures")))
        parent.mkdir(parents=True,exist_ok=True)
        self.folder=Path(tempfile.mkdtemp(prefix="fixture_",dir=parent))

    def raw_arm(self,*,rows=None,status="PUBLIC_TASK_NATIVE_RETURNED"):
        rows=rows if rows is not None else [{"task_id":x,"error_message":None,"test_exit_code":0} for x in ("toy_a","toy_b")]
        arm={"task_ids":["toy_a","toy_b"],"repo":"invented/toy","rows":rows,"helper_sha256":entry.HELPER_SHA,
             "status":status,"official_score":None}
        path=self.folder/"PRIVATE_NATIVE_ARM_RECEIPT.json"
        with path.open("xb") as stream:stream.write(entry.encode(arm))
        return path

    def sidecar(self,system,arm=None,proto=None,sources=None):
        return entry.create_sidecar(arm or self.raw_arm(),entry.encode(protocol() if proto is None else proto),
            entry.REVIEWED_SOURCES if sources is None else sources,system.collector,system.lifecycle,entry_sha256=ENTRY_SHA)

    def test_complete_preserves_return_installer_and_every_boundary(self):
        s=FakeSystem();self.assertIs(asyncio.run(s.complete()),s.install_result)
        self.assertTrue(s.restored());self.assertEqual(entry.inspect_records(s.collector.records,["toy_a","toy_b"]),2)

    def test_partial_installer_failure_restores_all_and_exception_identity(self):
        s=FakeSystem(partial_install=True)
        try:
            with s.lifecycle:s.owned.install_timing(s.official,object())
        except RuntimeError as error:self.assertIs(error,s.install_failure)
        else:self.fail("missing original exception")
        self.assertTrue(s.restored());self.assertEqual(s.lifecycle.failures,["INSTALL_OR_SOURCE_BOUNDARY_FAILED"])

    def test_task_exception_identity_and_restoration(self):
        error=RuntimeError("invented task failure");s=FakeSystem(failure=error)
        try:asyncio.run(s.complete())
        except RuntimeError as caught:self.assertIs(caught,error)
        else:self.fail("missing task exception")
        self.assertTrue(s.restored());self.assertEqual(s.collector.records[0]["outcome"],"EXCEPTION")

    def test_cancellation_identity_restoration_and_observation(self):
        error=asyncio.CancelledError("invented cancellation");s=FakeSystem(failure=error)
        try:asyncio.run(s.complete())
        except asyncio.CancelledError as caught:self.assertIs(caught,error)
        else:self.fail("missing original cancellation")
        self.assertTrue(s.restored());self.assertEqual(s.collector.records[0]["outcome"],"EXCEPTION")

    def test_concurrent_attempt_refused_and_first_return_kept(self):
        async def run():
            ready=asyncio.Event();release=asyncio.Event();s=FakeSystem(waiting=(ready,release))
            with s.lifecycle:
                s.owned.install_timing(s.official,object());e=s.official.Evaluator()
                pending=asyncio.create_task(e.evaluate_task(task("toy_a"),Context()));await ready.wait()
                try:
                    with self.assertRaisesRegex(entry.Hold,"CONCURRENT"):await e.evaluate_task(task("toy_b"),Context())
                finally:release.set()
                self.assertIs(await pending,s.result)
            return s
        s=asyncio.run(run());self.assertTrue(s.restored());self.assertEqual(len(s.collector.records),1)
        self.assertTrue(s.lifecycle.failures)

    def test_wrong_order_refused_before_observation(self):
        async def run():
            s=FakeSystem()
            with s.lifecycle:
                s.owned.install_timing(s.official,object())
                with self.assertRaisesRegex(entry.Hold,"ORDER_OR_DENOMINATOR"):
                    await s.official.Evaluator().evaluate_task(task("toy_b"),Context())
            return s
        s=asyncio.run(run());self.assertTrue(s.restored());self.assertEqual(s.collector.records,[])

    def test_alias_conflict_refused(self):
        with self.assertRaisesRegex(entry.Hold,"ID_CONFLICT"):entry.alias_identity(SimpleNamespace(task_id="toy_a",instance_id="toy_b"))

    def test_denominator_boolean_or_duplicate_refused(self):
        for value in (True,[True],["toy_a","toy_a"],[]):
            with self.subTest(value=value),self.assertRaises(entry.Hold):entry.task_list(value)

    def test_missing_end_observed_unknown_without_fabricated_values(self):
        s=FakeSystem(missing_end=True);asyncio.run(s.complete())
        self.assertTrue(s.restored());self.assertTrue(all(r["state"]=="UNKNOWN" for r in s.collector.records))
        self.assertFalse(any("policy_elapsed_seconds" in r for r in s.collector.records))
        self.assertEqual(self.sidecar(s)["status"],"HOLD")

    def test_observer_append_error_preserves_original_return(self):
        class BrokenList(list):
            def append(self,value):raise ValueError("invented observer failure")
        s=FakeSystem();s.collector.records=BrokenList();asyncio.run(s.complete())
        self.assertTrue(s.restored());self.assertEqual(s.collector.observer_errors,2)
        # The collector state is not a valid plain list: no sidecar is invented.
        with self.assertRaisesRegex(entry.Hold,"CLOCK_RECORD_BOUND"):self.sidecar(s)

    def test_multiple_installer_refused_restores_first_install(self):
        s=FakeSystem()
        with s.lifecycle:
            s.owned.install_timing(s.official,object())
            with self.assertRaisesRegex(entry.Hold,"MULTIPLE_INSTALL"):s.owned.install_timing(s.official,object())
        self.assertTrue(s.restored());self.assertTrue(s.lifecycle.failures)

    def test_context_validator_error_preserved_and_restored(self):
        marker=ValueError("invented context rejection");s=FakeSystem()
        def reject(_):raise marker
        s.lifecycle.context_check=reject
        try:asyncio.run(s.complete())
        except ValueError as error:self.assertIs(error,marker)
        else:self.fail("context error lost")
        self.assertTrue(s.restored());self.assertEqual(s.collector.records,[])

    def test_source_validator_error_preserved_and_restored(self):
        marker=ValueError("invented source rejection");s=FakeSystem()
        def reject(_):raise marker
        s.lifecycle.boundary_check=reject
        try:asyncio.run(s.complete())
        except ValueError as error:self.assertIs(error,marker)
        else:self.fail("source error lost")
        self.assertTrue(s.restored())

    def test_lifecycle_reuse_refused(self):
        s=FakeSystem();asyncio.run(s.complete())
        with self.assertRaisesRegex(entry.Hold,"LIFECYCLE_REUSED"):
            with s.lifecycle:pass

    def test_sidecar_complete_is_new_and_raw_receipt_unchanged(self):
        s=FakeSystem();asyncio.run(s.complete());arm=self.raw_arm();before=arm.read_bytes()
        report=self.sidecar(s,arm);self.assertEqual(report["status"],"OBSERVED_CLOCK_SIDECAR_REVIEW_REQUIRED")
        self.assertEqual(arm.read_bytes(),before)
        value=entry.parse(Path(report["sidecar_path"]).read_bytes())
        self.assertEqual(value["raw_arm_sha256"],entry.sha(before));self.assertFalse(value["native_authenticity_established"])
        self.assertIsNone(value["official_score"]);self.assertFalse(value["submission_authorized"])

    def test_sidecar_collision_preserves_existing_and_raw(self):
        s=FakeSystem();asyncio.run(s.complete());arm=self.raw_arm();before=arm.read_bytes()
        side=self.folder/entry.SIDECAR_NAME
        with side.open("xb") as stream:stream.write(b"retained invented collision")
        with self.assertRaises(FileExistsError):self.sidecar(s,arm)
        self.assertEqual(side.read_bytes(),b"retained invented collision");self.assertEqual(arm.read_bytes(),before)

    def test_missing_raw_receipt_never_creates_sidecar(self):
        s=FakeSystem();asyncio.run(s.complete())
        with self.assertRaisesRegex(entry.Hold,"RAW_ARM_ABSENT"):
            self.sidecar(s,self.folder/"PRIVATE_NATIVE_ARM_RECEIPT.json")
        self.assertFalse((self.folder/entry.SIDECAR_NAME).exists())

    def test_incomplete_clock_denominator_holds(self):
        s=FakeSystem();asyncio.run(s.complete());s.collector.records=s.collector.records[:1]
        self.assertEqual(self.sidecar(s)["status"],"HOLD")

    def test_caught_task_error_holds(self):
        s=FakeSystem();asyncio.run(s.complete())
        rows=[{"task_id":"toy_a","error_message":"invented caught error","test_exit_code":-1},
              {"task_id":"toy_b","error_message":None,"test_exit_code":0}]
        self.assertEqual(self.sidecar(s,self.raw_arm(rows=rows))["status"],"HOLD")

    def test_pytest_interrupt_usage_empty_boolean_exits_hold(self):
        s=FakeSystem();asyncio.run(s.complete())
        for exit_code in (2,3,4,5,True,None):
            with self.subTest(exit_code=exit_code):
                # Separate create-only subdirectory per existing arm receipt.
                sub=self.folder/(type(exit_code).__name__+"_"+str(exit_code));sub.mkdir()
                rows=[{"task_id":x,"error_message":None,"test_exit_code":exit_code} for x in ("toy_a","toy_b")]
                path=sub/"PRIVATE_NATIVE_ARM_RECEIPT.json"
                raw={"task_ids":["toy_a","toy_b"],"repo":"invented/toy","rows":rows,
                     "helper_sha256":entry.HELPER_SHA,"status":"PUBLIC_TASK_NATIVE_RETURNED","official_score":None}
                with path.open("xb") as stream:stream.write(entry.encode(raw))
                self.assertEqual(self.sidecar(s,path)["status"],"HOLD")

    def test_unknown_source_pin_refused_even_if_protocol_agrees(self):
        s=FakeSystem();asyncio.run(s.complete());sources=dict(entry.REVIEWED_SOURCES);sources["clock_collector.py"]="a"*64
        p=protocol();p["component_hashes"]["clock_collector.py"]="a"*64
        with self.assertRaisesRegex(entry.Hold,"REVIEWED_SOURCE"):self.sidecar(s,proto=p,sources=sources)

    def test_entry_protocol_pin_absent_refused(self):
        s=FakeSystem();asyncio.run(s.complete());p=protocol();p["component_hashes"].pop("entry_join.py")
        with self.assertRaisesRegex(entry.Hold,"PROTOCOL_ENTRY"):self.sidecar(s,proto=p)

    def test_raw_alias_or_missing_error_refused(self):
        s=FakeSystem();asyncio.run(s.complete())
        with self.assertRaisesRegex(entry.Hold,"ALIAS_CONFLICT"):
            self.sidecar(s,self.raw_arm(rows=[{"task_id":"toy_a","instance_id":"toy_b","error_message":None,"test_exit_code":0}]))

    def test_clock_type_drift_or_unknown_measurement_refused(self):
        s=FakeSystem();asyncio.run(s.complete());s.collector.records[0]["policy_elapsed_seconds"]=True
        with self.assertRaisesRegex(entry.Hold,"MEASUREMENT_TYPE"):self.sidecar(s)

    def test_unknown_clock_reverse_wrappers_refused(self):
        r={"task_id":"toy_a","clock":"time.perf_counter","state":"UNKNOWN","outcome":"RETURN",
           "wrapper_started":2.0,"wrapper_finished":1.0}
        with self.assertRaisesRegex(entry.Hold,"WRAPPER_ORDER"):entry.inspect_records([r],["toy_a"])

    def test_duplicate_json_or_nonfinite_refused(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'):
            with self.subTest(raw=raw),self.assertRaises((entry.Hold,ValueError)):entry.parse(raw)


class PlannerClockTests(unittest.TestCase):
    def test_protocol_envelope_uses_current_fields(self):
        self.assertEqual(planner.protocol_envelope(protocol())["first_cell_budget_seconds"],8700)

    def test_clock_original_origin_is_preserved(self):
        report=planner.observed_deadline(protocol(),first_cell_start=100.5,observed_origin=100.5,current_monotonic=200.5)
        self.assertEqual(report["absolute_deadline"],8800.5);self.assertEqual(report["elapsed_from_first_cell_seconds"],100.)

    def test_clock_reset_bool_nonfinite_future_exhaustion_refused(self):
        cases=((100.,101.,200.),(True,True,200.),(float("nan"),100.,200.),(100.,100.,99.),(100.,100.,8800.))
        for first,origin,now in cases:
            with self.subTest(case=(first,origin,now)),self.assertRaises(entry.Hold):
                planner.observed_deadline(protocol(),first_cell_start=first,observed_origin=origin,current_monotonic=now)

    def test_conflicting_or_boolean_budget_refused(self):
        for key,value in (("deadline_seconds_from_first_cell",True),("readiness_budget_seconds",3715),
                          ("task_reserve_seconds",float("inf"))):
            p=protocol();p[key]=value
            with self.subTest(key=key),self.assertRaises(entry.Hold):planner.protocol_envelope(p)

    def test_static_parent_gap_is_prepared_only(self):
        bootstrap=b'deadline = GEMMA_NATIVE_T0 + 2350 - 180\nsubprocess.run([], timeout=max(1, deadline-time.monotonic()+5))\n'
        first='import time\nif "GEMMA_NATIVE_T0" in globals():\n raise RuntimeError("clock set")\nGEMMA_NATIVE_T0=time.monotonic()\n'
        report=planner.outer_clock(bootstrap,first)
        self.assertEqual(report["nominal_parent_cap_from_first_cell_seconds"],2175)
        self.assertIn("not a measured receipt",report["cap_note"])

    def test_outer_reset_or_unknown_timeout_refused(self):
        first='if "GEMMA_NATIVE_T0" in globals():\n raise RuntimeError("clock set")\nGEMMA_NATIVE_T0=time.monotonic()\n'
        for raw in (b'GEMMA_NATIVE_T0=time.monotonic()\ndeadline=GEMMA_NATIVE_T0+100\n',
                    b'deadline=GEMMA_NATIVE_T0+100\nsubprocess.run([],timeout=999)\n'):
            with self.subTest(raw=raw),self.assertRaises(entry.Hold):planner.outer_clock(raw,first)

    def test_unreviewed_timeout_floor_is_unknown(self):
        first='if "GEMMA_NATIVE_T0" in globals():\n raise RuntimeError("clock set")\nGEMMA_NATIVE_T0=time.monotonic()\n'
        raw=b'deadline=GEMMA_NATIVE_T0+2170\nsubprocess.run([],timeout=max(1e8,deadline-time.monotonic()+5))\n'
        with self.assertRaisesRegex(entry.Hold,"FLOOR_UNREVIEWED"):planner.outer_clock(raw,first)


if __name__=="__main__":unittest.main()
