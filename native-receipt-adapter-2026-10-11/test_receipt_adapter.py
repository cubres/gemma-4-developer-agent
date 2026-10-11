"""Invented receipt/control tests; no organizer, model, task or network execution.

Run with RECEIPT_R4_GATE set to the exact reviewed sibling screen_gate.py.
"""
import asyncio
from copy import deepcopy
import inspect
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import receipt_adapter as adapter
from clock_collector import ClockCollector, observe


def package(raw):
    raw = deepcopy(raw)
    raw["arm"]["actual_final_verification_capture"] = deepcopy(raw["capture"])
    raw["arm"]["verification_capture_receipt_sha256"] = adapter.digest(raw["capture"])
    raw["pilot"]["protocol_sha256"] = adapter.digest(raw["protocol"])
    raw["pilot"]["arms"]["probe"]["receipt_sha256"] = adapter.digest(raw["arm"])
    raw["pilot"]["arms"]["probe"]["rows"] = deepcopy(raw["arm"]["rows"])
    return {role:adapter.pinned(adapter.encoded(value)) for role,value in raw.items()}


def fixture():
    task_ids = ["invented_alpha", "invented_beta"]
    token = "a"*64
    sources = dict(adapter.REVIEWED_SOURCE_SHA256)
    sources["clock_collector.py"] = adapter.sha(Path(__file__).with_name("clock_collector.py").read_bytes())
    plan = {"schema_version":1, "task_ids":task_ids, "full_gate_task_ids":task_ids+["invented_gamma"],
            "repo":"invented/project", "arm":"probe", "runtime_assumptions":{
                "hidden_task_count":120, "startup_seconds":900, "margin_multiplier":1.25,
                "session_limit_seconds":43200, "nominal_projection_limit_seconds":37800,
                "agent_sandbox_max_seconds":227, "verification_and_residual_setup_mean_limit_seconds":100,
                "policy_elapsed_max_seconds":150, "policy_sandbox_clock_tolerance_seconds":.02}}
    protocol = {"task_ids":task_ids, "repo":plan["repo"], "arm_selection":["probe"],
                "model_tensor_sha256":token, "tasks_file_sha256":token,
                "absolute_seconds_including_model_load_and_allocation_reserve":8880,
                "readiness_budget_seconds":3714, "task_reserve_seconds":4986,
                "phase_a_cap_seconds":420, "arm_cap_seconds":{"probe":4536},
                "per_task_arm_cap_components":{"per_task_total":567},
                "fresh_python_source_sha256":{k:sources[k] for k in adapter.OFFICIAL_SOURCES},
                "component_hashes":{k:sources[k] for k in adapter.OWNED_SOURCES}}
    rows = [{"task_id":task, "error_message":None, "repo":plan["repo"], "resolved":True,
             "test_exit_code":0, "status":"SUCCESS", "agent_patch":"opaque private patch sentinel",
             "test_output":"opaque private stdout sentinel", "duration_seconds":240.} for task in task_ids]
    timings = [{"task_id":task, "error":None, "resolved":True, "agent_seconds":180.,
                "verification_seconds":50., "setup_seconds":10., "total_seconds":240.} for task in task_ids]
    events, blobs = [], {}
    for task in task_ids:
        content = ('<testsuite name="'+task+'" tests="1" failures="0"><testcase name="test_a"/></testsuite>').encode()
        spec = {"bytes":len(content), "sha256":adapter.sha(content), "path":"/native/path/not-used.xml"}
        path = "/virtual/ordinary.xml"
        first = len(events)+1
        events.extend([
            {"index":first,"kind":"FINAL_PYTEST_EXEC","task_id":task,"exit_code":0,
             "original_outcome":"RETURN","junit_virtual_path":path,"junit_file_capture":deepcopy(spec)},
            {"index":first+1,"kind":"ACTUAL_CAT_JUNIT_EXEC","task_id":task,"exit_code":0,
             "original_outcome":"RETURN","junit_virtual_path":path,"actual_cat_stdout_capture":deepcopy(spec)},
            {"index":first+2,"kind":"ORIGINAL_STRICT_JUNIT_VALIDATOR","original_outcome":"RETURN",
             "original_result":[True,None],"xml_input_capture":deepcopy(spec)}])
        for index,field in ((first,"junit_file_capture"),(first+1,"actual_cat_stdout_capture"),(first+2,"xml_input_capture")):
            blobs[str(index)+":"+field] = content
    capture = {"status":"PASS_PRIVATE_FINAL_VERIFICATION_CAPTURE","official_score":None,
               "events":events,"methods_restored":True,"capture_errors":[],"missing_evidence":[],
               "finalpytest_count":2,"actual_cat_junit_count":2,"original_validator_count":2}
    snapshots = {task:token for task in task_ids}
    arm = {"status":"PUBLIC_TASK_NATIVE_RETURNED","strict_junit_sandbox_class":"SubprocessManager",
           "task_ids":task_ids,"repo":plan["repo"],"snapshot_sha256_by_task":snapshots,
           "preservation":{"passed":True},"official_score":None,"rows":rows,
           "timing":{"tasks_expected":2,"tasks_timed":2,"per_task":timings,"infrastructure_error":False}}
    pilot = {"status":"SINGLE_PUBLIC_NATIVE_RETURNED_REVIEW_REQUIRED","official_score":None,
             "start_monotonic":1000.,"deadline_monotonic":9700.,"allocation_overhead_seconds":180.,
             "model_weights_observed_sha256":token,"planned_attempt_denominator":1,
             "arms":{"probe":{"elapsed_seconds":480.}},"preservation_after_all_outcomes":{"probe":{"passed":True}},
             "process_teardown":{"survivors":[]},"frozen_public_input":{"task_ids":task_ids,"repo":plan["repo"],
              "tasks_sha256":token,"snapshot_sha256_by_task":snapshots},
             "timeline_rel_seconds":{"install_started":100.,"install_finished":200.,"vllm_launch":300.,
               "engine_ready":800.,"health_ready":810.,"weights_verified":900.,"phase_a_started":910.,
               "phase_a_done":1100.,"arm_started":1200.,"arm_finished":1680.}}
    outer = {"status":"NATIVE_SINGLE_CANARY_RETURNED_REVIEW_REQUIRED","official_score":None,
             "worker_exit_code_before_teardown":0,"first_cell_start_monotonic":1000.,
             "absolute_deadline_monotonic":9700.,"allocation_overhead_seconds":180.,"elapsed_from_first_cell_seconds":1700.,
             "teardown":{"survivors":[]},"outer_notebook_packet_preservation":{"passed":True},
             "planned_attempt_denominator":1,"incomplete_canary_excluded_from_route_qualification":False}
    raw = {"protocol":protocol,"pilot":pilot,"arm":arm,"capture":capture,"outer":outer}
    clocks = []
    for offset,task in enumerate(task_ids):
        start = 2000.+300*offset
        clocks.append({"task_id":task,"clock":"time.perf_counter","state":"OBSERVED_FROZEN","outcome":"RETURN",
                       "wrapper_started":start,"policy_started":start+20,"policy_finished":start+160,
                       "wrapper_finished":start+180,"policy_elapsed_seconds":140.,"preparation_seconds":20.,
                       "completion_seconds":20.,"sandbox_wall_seconds":180.})
    return plan,raw,sources,clocks,blobs


def clock_artifact(bundle, sources, records):
    return adapter.pinned(adapter.encoded({"schema_version":1,"raw_protocol_sha256":bundle["protocol"]["sha256"],
        "raw_arm_sha256":bundle["arm"]["sha256"],"source_sha256":sources,"records":records,"observer_errors":0}))


class AdapterControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Tests import only the original reviewed checker, never organizer code.
        path = os.environ.get("RECEIPT_R4_GATE")
        if not path:
            raise RuntimeError("Set RECEIPT_R4_GATE to reviewed screen_gate.py")
        cls.gate = adapter.gate_module(Path(path))

    def setUp(self):
        self.plan,self.raw,self.sources,self.records,self.blobs = fixture()

    def result(self, *, clock=True, blobs=True):
        bundle = package(self.raw)
        return adapter.examine(self.plan,bundle,sources=self.sources,
            clock=clock_artifact(bundle,self.sources,self.records) if clock else None,
            blobs=self.blobs if blobs else {},gate=self.gate)

    def held(self, reason):
        result = self.result()
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],reason)
        self.assertFalse(result["submission_authorized"])
        self.assertIsNone(result["official_score"])
        return result

    def test_complete_invented_screen_unscored_unattested(self):
        result=self.result()
        self.assertEqual(result["status"],"ADAPTED_CONSISTENCY_REVIEW_REQUIRED")
        self.assertEqual(result["adoption_status"],"HOLD_NATIVE_ATTESTATION_REQUIRED")
        self.assertFalse(result["native_authenticity_established"])
        self.assertFalse(result["full_ordered_gate_coverage"])
        self.assertEqual(result["missing_full_gate_task_count"],1)
        self.assertEqual(result["policy_elapsed_max_seconds"],140.)
        self.assertEqual(result["sandbox_wall_max_seconds"],180.)
        self.assertNotIn("opaque private",json.dumps(result))

    def test_full_denominator_remains_unattested(self):
        self.plan["full_gate_task_ids"] = self.plan["task_ids"][:]
        result=self.result()
        self.assertTrue(result["full_ordered_gate_coverage"])
        self.assertFalse(result["submission_authorized"])

    def test_aliases_agree(self):
        for row in self.raw["arm"]["rows"]:
            row.update(instance_id=row["task_id"],error=row["error_message"])
        self.assertEqual(self.result()["status"],"ADAPTED_CONSISTENCY_REVIEW_REQUIRED")

    def test_alias_identity_conflict(self):
        self.raw["arm"]["rows"][0]["instance_id"]="invented_wrong"
        self.held("RESULT_ALIAS_CONFLICT")

    def test_alias_error_conflict(self):
        self.raw["arm"]["rows"][0]["error"]="private error sentinel"
        result=self.held("RESULT_ALIAS_CONFLICT")
        self.assertNotIn("private error sentinel",json.dumps(result))

    def test_missing_error_field_not_health(self):
        self.raw["arm"]["rows"][0].pop("error_message")
        self.held("RESULT_FIELD_ABSENT")

    def test_caught_error_with_success_and_zero(self):
        row=self.raw["arm"]["rows"][0]
        row["error_message"]="private task failure"
        self.raw["arm"]["timing"]["per_task"][0]["error"]="private task failure"
        result=self.held("DERIVED_R4_CHECKS_HOLD")
        self.assertEqual(result["task_error_count"],1)
        self.assertEqual(result["derived_gate_result"]["reason"],"TASK_ERROR_ROUTE_UNPROVEN")

    def test_current_timing_error_truncation_retained(self):
        self.raw["arm"]["rows"][0]["error_message"]="x"*400
        self.raw["arm"]["timing"]["per_task"][0]["error"]="x"*300
        result=self.held("DERIVED_R4_CHECKS_HOLD")
        self.assertEqual(result["timing_error_expansions"],1)
        self.assertEqual(result["task_error_count"],1)

    def test_error_truncation_conflict(self):
        self.raw["arm"]["rows"][0]["error_message"]="x"*400
        self.raw["arm"]["timing"]["per_task"][0]["error"]="y"*300
        self.held("TIMING_ERROR_SOURCE_TRANSFORM_DRIFT")

    def test_missing_task_order(self):
        self.raw["arm"]["rows"].reverse()
        self.held("NORMALIZED_RESULT_DENOMINATOR")

    def test_pilot_raw_pin_drift(self):
        bundle=package(self.raw)
        bundle["pilot"]["value"]["arms"]["probe"]["receipt_sha256"]="b"*64
        result=adapter.examine(self.plan,bundle,sources=self.sources,gate=self.gate)
        self.assertEqual(result["reason"],"RAW_PIN_OR_OBJECT_DRIFT")

    def test_raw_boolean_and_number_type_drift(self):
        for field,value in (("incomplete_canary_excluded_from_route_qualification",0),
                            ("planned_attempt_denominator",1.0)):
            with self.subTest(field=field,value=value):
                bundle=package(self.raw)
                bundle["outer"]["value"][field]=value
                result=adapter.examine(self.plan,bundle,sources=self.sources,gate=self.gate)
                self.assertEqual(result["reason"],"RAW_PIN_OR_OBJECT_DRIFT")

    def test_embedded_raw_drift_not_rebound(self):
        bundle=package(self.raw)
        value=deepcopy(bundle["pilot"]["value"])
        value["arms"]["probe"]["rows"][0]["error_message"]="private"
        bundle["pilot"]=adapter.pinned(adapter.encoded(value))
        result=adapter.examine(self.plan,bundle,sources=self.sources,gate=self.gate)
        self.assertEqual(result["reason"],"RAW_RESULT_EMBEDDED_DRIFT")

    def test_missing_arm_hold(self):
        bundle=package(self.raw);bundle.pop("arm")
        result=adapter.examine(self.plan,bundle,sources=self.sources,gate=self.gate)
        self.assertEqual(result["reason"],"RAW_ARTIFACTS_MISSING")
        self.assertEqual(result["missing_artifact_roles"],["arm"])

    def test_unreviewed_source_even_protocol_agrees(self):
        self.sources["native_arm.py"]="b"*64
        self.raw["protocol"]["component_hashes"]["native_arm.py"]="b"*64
        self.held("REVIEWED_SOURCE_CONTRACT_DRIFT")

    def test_unreviewed_collector_even_protocol_agrees(self):
        self.sources["clock_collector.py"]="b"*64
        self.raw["protocol"]["component_hashes"]["clock_collector.py"]="b"*64
        self.held("REVIEWED_SOURCE_CONTRACT_DRIFT")

    def test_unreviewed_task_subclass_even_protocol_agrees(self):
        self.sources["swegemma/models/task.py"]="b"*64
        self.raw["protocol"]["fresh_python_source_sha256"]["swegemma/models/task.py"]="b"*64
        self.held("REVIEWED_SOURCE_CONTRACT_DRIFT")

    def test_protocol_source_drift(self):
        self.sources["native_arm.py"]="b"*64
        self.held("PROTOCOL_SOURCE_BINDING")

    def test_missing_clock_hold(self):
        self.assertEqual(self.result(clock=False)["reason"],"POLICY_CLOCK_ABSENT")

    def test_missing_actual_xml_hold(self):
        self.assertEqual(self.result(blobs=False)["reason"],"ACTUAL_XML_BYTES_ABSENT")

    def test_declared_xml_byte_bool_zero_and_drift(self):
        for field,index in (("junit_file_capture",0),("actual_cat_stdout_capture",1),("xml_input_capture",2)):
            for count in (True,0,999):
                with self.subTest(field=field,count=count):
                    old=self.raw["capture"]["events"][index][field]["bytes"]
                    self.raw["capture"]["events"][index][field]["bytes"]=count
                    result=self.result()
                    self.assertEqual(result["status"],"HOLD")
                    self.raw["capture"]["events"][index][field]["bytes"]=old

    def test_xml_actual_mutation(self):
        key="2:actual_cat_stdout_capture"
        self.blobs[key]=self.blobs[key]+b" "
        self.held("XML_ACTUAL_PIN_OR_SIZE_DRIFT")

    def test_xml_hash_drift(self):
        self.raw["capture"]["events"][0]["junit_file_capture"]["sha256"]="b"*64
        self.held("XML_ACTUAL_PIN_OR_SIZE_DRIFT")

    def test_xml_extra_local_blob(self):
        self.blobs["invented_extra"]=b"private"
        self.held("XML_LOCAL_MAPPING_DENOMINATOR")

    def test_pytest_unhealthy_exit_policy(self):
        for code in (-1,2,3,4,5,True):
            with self.subTest(code=code):
                self.raw["capture"]["events"][0]["exit_code"]=code
                self.raw["arm"]["rows"][0]["test_exit_code"]=code
                result=self.result()
                self.assertEqual(result["status"],"HOLD")

    def test_ordinary_unresolved_failure_is_observed(self):
        row=self.raw["arm"]["rows"][0];row.update(test_exit_code=1,resolved=False)
        self.raw["arm"]["timing"]["per_task"][0]["resolved"]=False
        events=self.raw["capture"]["events"]
        events[0]["exit_code"]=1
        self.raw["capture"]["events"]=[events[0]]+events[3:]
        for index,event in enumerate(self.raw["capture"]["events"],1):event["index"]=index
        self.raw["capture"].update(actual_cat_junit_count=1,original_validator_count=1)
        old=self.blobs
        self.blobs={"1:junit_file_capture":old["1:junit_file_capture"],
                    "2:junit_file_capture":old["4:junit_file_capture"],
                    "3:actual_cat_stdout_capture":old["5:actual_cat_stdout_capture"],
                    "4:xml_input_capture":old["6:xml_input_capture"]}
        result=self.result()
        self.assertEqual(result["status"],"ADAPTED_CONSISTENCY_REVIEW_REQUIRED")
        self.assertEqual(result["derived_gate_result"]["resolved_count"],1)

    def test_final_task_denominator(self):
        self.raw["capture"]["events"]=self.raw["capture"]["events"][:3]
        self.held("XML_FINAL_TASK_DENOMINATOR")

    def test_capture_counter_type_and_drift(self):
        for field in ("finalpytest_count","actual_cat_junit_count","original_validator_count"):
            for value in (True,2.0,1,3):
                with self.subTest(field=field,value=value):
                    self.raw["capture"][field]=value
                    self.held("XML_CAPTURE_COUNT_TYPE_OR_DRIFT")
                    self.raw["capture"][field]=2

    def test_original_validator_negative_resolved(self):
        self.raw["capture"]["events"][2]["original_result"][0]=False
        result=self.held("DERIVED_R4_CHECKS_HOLD")
        self.assertEqual(result["derived_gate_result"]["reason"],"RESOLVED_STRICT_VALIDATOR_WITNESS")

    def test_cat_identity_conflict(self):
        self.raw["capture"]["events"][1]["task_id"]="invented_wrong"
        self.held("XML_CAT_TASK_CONFLICT")

    def test_policy_unknown_and_missing_end(self):
        self.records[0]["state"]="UNKNOWN"
        self.held("POLICY_CLOCK_NOT_OBSERVED_FROZEN")

    def test_policy_clock_bool_and_nan(self):
        for value in (True,math.nan):
            self.records[0]["policy_elapsed_seconds"]=value
            if math.isnan(value):
                with self.assertRaises(ValueError):self.result()
            else:
                self.held("CLOCK_OR_LIMIT_INVALID")

    def test_policy_clock_raw_arm_binding(self):
        bundle=package(self.raw)
        value=clock_artifact(bundle,self.sources,self.records)["value"]
        value["raw_arm_sha256"]="b"*64
        result=adapter.examine(self.plan,bundle,sources=self.sources,
            clock=adapter.pinned(adapter.encoded(value)),blobs=self.blobs,gate=self.gate)
        self.assertEqual(result["reason"],"POLICY_CLOCK_RAW_SOURCE_BINDING")

    def test_policy_clock_order_arithmetic_and_limit(self):
        self.records[0]["policy_finished"]=self.records[0]["wrapper_finished"]+1
        self.held("POLICY_CLOCK_MARK_ORDER")
        self.records[0]["policy_finished"]-=1
        self.held("POLICY_CLOCK_ARITHMETIC")

    def test_policy_limit_separate_from_sandbox(self):
        self.plan["runtime_assumptions"]["policy_elapsed_max_seconds"]=139
        self.held("POLICY_ELAPSED_LIMIT")

    def test_policy_sandbox_clock_drift(self):
        self.raw["arm"]["timing"]["per_task"][0]["agent_seconds"]=190
        self.held("POLICY_SANDBOX_WALL_DRIFT")

    def test_reordered_clock_denominator(self):
        self.records.reverse()
        self.held("POLICY_CLOCK_DENOMINATOR")

    def test_raw_hold_survives_normalization(self):
        self.raw["outer"]["incomplete_canary_excluded_from_route_qualification"]=True
        result=self.held("DERIVED_R4_CHECKS_HOLD")
        self.assertEqual(result["derived_gate_result"]["reason"],"INCOMPLETE_CANARY")

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(adapter.Hold):adapter.parse(raw)

    def test_private_payloads_not_emitted(self):
        self.raw["arm"]["rows"][0]["error_message"]="secret sentinel"
        result=self.result()
        self.assertNotIn("secret sentinel",json.dumps(result))
        self.assertNotIn("opaque private",json.dumps(result))


class CollectorControls(unittest.TestCase):
    def test_frozen_context_separates_clocks(self):
        ctx=SimpleNamespace(agent_start_time=20.,agent_end_time=50.,agent_elapsed_seconds=30.)
        result=observe("invented_alpha",ctx,10.,60.,"RETURN")
        self.assertEqual(result["state"],"OBSERVED_FROZEN")
        self.assertEqual(result["policy_elapsed_seconds"],30.)
        self.assertEqual(result["preparation_seconds"],10.)
        self.assertEqual(result["completion_seconds"],10.)
        self.assertEqual(result["sandbox_wall_seconds"],50.)

    def test_missing_context_never_inferred_zero(self):
        for ctx in (None,SimpleNamespace(agent_start_time=None,agent_end_time=None,agent_elapsed_seconds=0.),
                    SimpleNamespace(agent_start_time=20.,agent_end_time=None,agent_elapsed_seconds=5.)):
            result=observe("invented_alpha",ctx,10.,60.,"RETURN")
            self.assertEqual(result["state"],"UNKNOWN")
            self.assertNotIn("policy_elapsed_seconds",result)

    def test_observer_preserves_signature_return_and_arguments(self):
        marker=object();received=[]
        async def original(self,task,context=None):
            received.append((self,task,context));return marker
        collector=ClockCollector();wrapped=collector.wrap(original)
        ctx=SimpleNamespace(agent_start_time=20.,agent_end_time=30.,agent_elapsed_seconds=10.)
        task=SimpleNamespace(task_id="invented_alpha",instance_id="invented_alpha")
        with patch("clock_collector.time.perf_counter",side_effect=[10.,40.]):
            result=asyncio.run(wrapped(marker,task,ctx))
        self.assertIs(result,marker)
        self.assertEqual(received,[(marker,task,ctx)])
        self.assertEqual(inspect.signature(wrapped),inspect.signature(original))
        self.assertEqual(collector.records[0]["state"],"OBSERVED_FROZEN")

    def test_original_exception_identity_survives(self):
        sentinel=RuntimeError("private sentinel")
        async def original(task,context=None):raise sentinel
        collector=ClockCollector();wrapped=collector.wrap(original)
        with self.assertRaises(RuntimeError) as caught:
            asyncio.run(wrapped(SimpleNamespace(instance_id="invented_alpha")))
        self.assertIs(caught.exception,sentinel)
        self.assertEqual(collector.records[0]["outcome"],"EXCEPTION")
        self.assertNotIn("private sentinel",json.dumps(collector.records))

    def test_observer_error_never_replaces_original(self):
        marker=object()
        async def original(task,context=None):return marker
        collector=ClockCollector();wrapped=collector.wrap(original)
        with patch("clock_collector.observe",side_effect=RuntimeError("private")):
            result=asyncio.run(wrapped(SimpleNamespace(instance_id="invented_alpha")))
        self.assertIs(result,marker)
        self.assertEqual(collector.observer_errors,1)

    def test_conflicting_context_task_aliases_unknown_identity(self):
        async def original(task,context=None):return None
        collector=ClockCollector()
        asyncio.run(collector.wrap(original)(SimpleNamespace(task_id="invented_alpha",instance_id="invented_other")))
        self.assertIsNone(collector.records[0]["task_id"])


if __name__ == "__main__":
    unittest.main()
