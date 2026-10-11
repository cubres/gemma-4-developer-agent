"""Invented receipts only; no model, task, file cleanup, or network execution."""
from copy import deepcopy
import hashlib
import json
import math
import unittest

from screen_gate import Hold, parse, review


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def bind(raw):
    raw = deepcopy(raw)
    raw["arm"]["actual_final_verification_capture"] = deepcopy(raw["capture"])
    raw["arm"]["verification_capture_receipt_sha256"] = digest(raw["capture"])
    raw["pilot"]["protocol_sha256"] = digest(raw["protocol"])
    raw["pilot"]["arms"]["D5b"]["receipt_sha256"] = digest(raw["arm"])
    raw["pilot"]["arms"]["D5b"]["rows"] = deepcopy(raw["arm"]["rows"])
    return {k: {"value": v, "sha256": digest(v)} for k,v in raw.items()}


def fixture():
    tasks = ["invented_a", "invented_b"]
    sha = "a"*64
    plan = {"schema_version": 1, "task_ids": tasks, "full_gate_task_ids": tasks+["invented_c", "invented_d"],
            "repo": "invented/repo", "arm": "D5b", "runtime_assumptions": {
                "hidden_task_count": 120, "startup_seconds": 900, "margin_multiplier": 1.25,
                "session_limit_seconds": 43200, "nominal_projection_limit_seconds": 37800,
                "agent_sandbox_max_seconds": 227,
                "verification_and_residual_setup_mean_limit_seconds": 100}}
    protocol = {"task_ids": tasks, "repo": plan["repo"], "arm_selection": ["D5b"],
                "model_tensor_sha256": sha, "tasks_file_sha256": sha,
                "absolute_seconds_including_model_load_and_allocation_reserve": 8880,
                "readiness_budget_seconds": 3714, "task_reserve_seconds": 4986,
                "phase_a_cap_seconds": 420, "arm_cap_seconds": {"D5b": 4536},
                "per_task_arm_cap_components": {"per_task_total": 567}}
    rows = [{"instance_id": t, "repo": plan["repo"], "error": None,
             "resolved": True, "test_exit_code": 0} for t in tasks]
    timings = [{"task_id": t, "error": None, "resolved": True,
                "agent_seconds": 180., "verification_seconds": 50., "setup_seconds": 10.,
                "total_seconds": 240.} for t in tasks]
    snapshots = {t:sha for t in tasks}
    events = []
    for t in tasks:
        path = "/tmp/invented.xml"
        events.extend([
            {"index":len(events)+1, "kind":"FINAL_PYTEST_EXEC", "task_id":t,
             "original_outcome":"RETURN", "exit_code":0, "junit_virtual_path":path,
             "junit_file_capture":{"sha256":sha,"bytes":20}},
            {"index":len(events)+2,"kind":"ACTUAL_CAT_JUNIT_EXEC",
             "original_outcome":"RETURN", "exit_code":0, "junit_virtual_path":path,
             "actual_cat_stdout_capture":{"sha256":sha,"bytes":20}},
            {"index":len(events)+3,"kind":"ORIGINAL_STRICT_JUNIT_VALIDATOR",
             "original_outcome":"RETURN", "original_result":[True,None],
             "xml_input_capture":{"sha256":sha,"bytes":20}}])
    cap = {"status":"PASS_PRIVATE_FINAL_VERIFICATION_CAPTURE", "official_score":None,
           "methods_restored":True, "capture_errors":[], "missing_evidence":[], "events":events,
           "finalpytest_count":2, "actual_cat_junit_count":2, "original_validator_count":2}
    arm = {"status":"PUBLIC_TASK_NATIVE_RETURNED", "strict_junit_sandbox_class":"SubprocessManager",
           "task_ids":tasks, "repo":plan["repo"], "snapshot_sha256_by_task":snapshots,
           "preservation":{"passed":True}, "official_score":None, "rows":rows,
           "timing":{"tasks_expected":2,"tasks_timed":2,"per_task":timings,"infrastructure_error":False}}
    pilot = {"status":"SINGLE_PUBLIC_NATIVE_RETURNED_REVIEW_REQUIRED", "official_score":None,
             "start_monotonic":1000., "deadline_monotonic":9700., "allocation_overhead_seconds":180.,
             "model_weights_observed_sha256":sha, "planned_attempt_denominator":1,
             "arms":{"D5b":{"elapsed_seconds":480.}},
             "preservation_after_all_outcomes":{"D5b":{"passed":True}},
             "process_teardown":{"survivors":[]},
             "frozen_public_input":{"task_ids":tasks,"repo":plan["repo"],"tasks_sha256":sha,
                                    "snapshot_sha256_by_task":snapshots},
             "timeline_rel_seconds":{"install_started":100., "install_finished":200., "vllm_launch":300.,
                 "engine_ready":800., "health_ready":810., "weights_verified":900.,
                 "phase_a_started":910., "phase_a_done":1100., "arm_started":1200., "arm_finished":1680.}}
    outer = {"status":"NATIVE_SINGLE_CANARY_RETURNED_REVIEW_REQUIRED", "official_score":None,
             "worker_exit_code_before_teardown":0,"first_cell_start_monotonic":1000.,
             "absolute_deadline_monotonic":9700., "allocation_overhead_seconds":180.,
             "elapsed_from_first_cell_seconds":1700., "teardown":{"survivors":[]},
             "outer_notebook_packet_preservation":{"passed":True}, "planned_attempt_denominator":1,
             "incomplete_canary_excluded_from_route_qualification":False}
    return plan, {"protocol":protocol,"pilot":pilot,"arm":arm,"capture":cap,"outer":outer}


class Controls(unittest.TestCase):
    def setUp(self):
        self.plan, self.raw = fixture()

    def result(self):
        return review(self.plan, bind(self.raw))

    def held(self, reason):
        out = self.result()
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["reason"], reason)
        self.assertFalse(out["submission_authorized"])

    def test_healthy_screen_retains_scope(self):
        out=self.result()
        self.assertEqual(out["status"],"SCREEN_CHECKS_PASS_REVIEW_REQUIRED")
        self.assertFalse(out["full_gate_coverage"])
        self.assertEqual(out["missing_full_gate_task_count"],2)
        self.assertEqual(out["projected_buffered_seconds"],36900)
        self.assertFalse(out["declared_cap_worst_case_fits"])
        self.assertFalse(out["hidden_runtime_guaranteed"])

    def test_complete_local_gate_still_unscored(self):
        self.plan["full_gate_task_ids"]=self.plan["task_ids"][:]
        out=self.result()
        self.assertEqual(out["status"],"EXPOSED_GATE_CHECKS_PASS_REVIEW_REQUIRED")
        self.assertIsNone(out["official_score"])
        self.assertFalse(out["native_authenticity_established"])

    def test_task_error_aggregate_false(self):
        self.raw["arm"]["rows"][0]["error"]="private sentinel must never appear"
        self.held("TASK_ERROR_ROUTE_UNPROVEN")
        self.assertNotIn("private sentinel",json.dumps(self.result()))

    def test_missing_final_despite_capture_pass(self):
        self.raw["capture"]["events"]=self.raw["capture"]["events"][:3]
        self.raw["capture"]["finalpytest_count"]=1
        self.held("FINAL_VERIFICATION_DENOMINATOR")

    def test_duplicate_final_task(self):
        self.raw["capture"]["events"][3]["task_id"]="invented_a"
        self.held("FINAL_VERIFICATION_DENOMINATOR")

    def test_zero_exit_missing_xml_chain(self):
        self.raw["capture"]["events"][1]["actual_cat_stdout_capture"]["sha256"]="b"*64
        self.held("ZERO_EXIT_XML_CHAIN")

    def test_capture_counter_drift(self):
        self.raw["capture"]["actual_cat_junit_count"]=1
        self.held("CAPTURE_COUNT_DRIFT")

    def test_timed_out_final(self):
        self.raw["capture"]["events"][0]["timed_out"]=True
        self.held("FINAL_VERIFICATION_EXECUTION_HEALTH")

    def test_missing_result(self):
        self.raw["arm"]["rows"].pop()
        self.held("RESULT_DENOMINATOR")

    def test_negative_test_exit(self):
        self.raw["arm"]["rows"][0]["test_exit_code"]=-1
        self.held("TASK_RESULT_HEALTH")

    def test_nan_timing(self):
        self.raw["arm"]["timing"]["per_task"][0]["agent_seconds"]=math.nan
        self.held("INVALID_NUMBER:agent_sandbox")

    def test_boolean_duration(self):
        self.raw["arm"]["timing"]["per_task"][0]["agent_seconds"]=True
        self.held("INVALID_NUMBER:agent_sandbox")

    def test_timing_sum(self):
        self.raw["arm"]["timing"]["per_task"][0]["setup_seconds"]=30
        self.held("TASK_TIMING_SUM")

    def test_hidden_unmeasured_arm_overhead(self):
        self.raw["pilot"]["arms"]["D5b"]["elapsed_seconds"]=600.
        self.raw["pilot"]["timeline_rel_seconds"]["arm_finished"]=1800.
        self.raw["outer"]["elapsed_from_first_cell_seconds"]=1900.
        self.held("BUFFERED_RUNTIME_PROJECTION")

    def test_readiness_reserve(self):
        self.raw["protocol"]["readiness_budget_seconds"]=800.
        self.held("READINESS_RESERVE")

    def test_survivor(self):
        self.raw["outer"]["teardown"]["survivors"]=[{"pid":123}]
        self.held("TEARDOWN_OUTER")

    def test_preservation_false(self):
        self.raw["arm"]["preservation"]["passed"]=False
        self.held("PRESERVATION_ARM")

    def test_score_injection(self):
        self.raw["pilot"]["official_score"]=.949
        self.held("LOCAL_OFFICIAL_SCORE_CONTAMINATION")

    def test_component_clock_mismatch(self):
        self.raw["outer"]["first_cell_start_monotonic"]+=1
        self.held("CLOCK_BINDING")

    def test_unknown_outer(self):
        self.raw["outer"]["status"]="COMPLETE"
        self.held("OUTER_NOT_RETURNED")

    def test_task_reorder(self):
        self.raw["arm"]["rows"].reverse()
        self.held("RESULT_DENOMINATOR")

    def test_input_repo_drift(self):
        self.raw["pilot"]["frozen_public_input"]["repo"]="other/repo"
        self.held("PILOT_INPUT_BINDING")

    def test_duplicate_task(self):
        self.plan["task_ids"]=["invented_a","invented_a"]
        self.held("DUPLICATE_TASK_ID:plan")

    def test_json_duplicate(self):
        with self.assertRaises(Hold):
            parse(b'{"a":1,"a":2}')

    def test_json_nonfinite(self):
        with self.assertRaises(Hold):
            parse(b'{"a":NaN}')

    def test_malformed_nested_capture_holds(self):
        self.raw["capture"]["events"][1]["actual_cat_stdout_capture"]="bad"
        self.held("ZERO_EXIT_XML_CHAIN")

    def test_validator_negative_resolved_true(self):
        self.raw["capture"]["events"][2]["original_result"]=[False,"invented"]
        self.held("RESOLVED_STRICT_VALIDATOR_WITNESS")

    def test_task_final_exit_drift(self):
        self.raw["arm"]["rows"][0]["test_exit_code"]=1
        self.held("TASK_CAPTURE_EXIT_DRIFT")

    def test_pin_reader_is_bounded_and_exact(self):
        import io
        from unittest.mock import patch
        from screen_gate import read_pinned
        raw=b'{"invented":true}'
        with patch("pathlib.Path.open", return_value=io.BytesIO(raw)):
            value=read_pinned("never-opened-by-fixture",hashlib.sha256(raw).hexdigest())
            self.assertTrue(value["value"]["invented"])
        with patch("pathlib.Path.open", return_value=io.BytesIO(raw)):
            with self.assertRaises(Hold):
                read_pinned("never-opened-by-fixture","a"*64)

    def test_ordinary_test_failure_kept_in_denominator(self):
        self.raw["arm"]["rows"][0].update(resolved=False,test_exit_code=1)
        self.raw["arm"]["timing"]["per_task"][0]["resolved"]=False
        self.raw["capture"]["events"][0]["exit_code"]=1
        out=self.result()
        self.assertEqual(out["status"],"SCREEN_CHECKS_PASS_REVIEW_REQUIRED")
        self.assertEqual(out["resolved_count"],1)
        self.assertEqual(out["tasks_checked"],2)

    def test_nonordinary_pytest_exit_holds(self):
        for code in (2,3,4,5,64):
            self.raw["capture"]["events"][0]["exit_code"]=code
            self.raw["arm"]["rows"][0].update(resolved=False,test_exit_code=code)
            self.held("FINAL_VERIFICATION_EXECUTION_HEALTH")

    def test_boolean_attempt_denominator(self):
        for role in ("outer","pilot"):
            _,raw=fixture()
            raw[role]["planned_attempt_denominator"]=True
            out=review(self.plan,bind(raw))
            self.assertEqual(out["reason"],"ATTEMPT_DENOMINATOR_"+role.upper())

    def test_invalid_manifest_report_retains_limits(self):
        import io
        from unittest.mock import patch
        from screen_gate import main
        stdout=io.StringIO()
        with patch("sys.argv",["screen_gate.py","--manifest","invented.json"]), \
             patch("screen_gate.loaded_manifest",side_effect=Hold("invented")), \
             patch("sys.stdout",stdout):
            self.assertEqual(main(),2)
        out=json.loads(stdout.getvalue())
        for key in ("submission_authorized","native_route_checks_passed",
                    "native_authenticity_established","hidden_runtime_guaranteed"):
            self.assertIs(out[key],False)

    def test_xml_capture_size_drift(self):
        for position,key in ((1,"actual_cat_stdout_capture"),(2,"xml_input_capture")):
            for size in (0,19,21,True):
                self.plan,self.raw=fixture()
                self.raw["capture"]["events"][position][key]["bytes"]=size
                self.held("ZERO_EXIT_XML_CHAIN")


if __name__ == "__main__":
    unittest.main()
