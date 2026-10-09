"""Adversarial tests for evidence denominators, clock binding, and privacy."""
import copy
from datetime import datetime, timedelta, timezone
import json
import math
import unittest

from native_budget_audit import audit

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def stamp(seconds):
    return (START + timedelta(seconds=seconds)).isoformat()


def request(index, start, end, *, status="COMPLETE", root=True, names=None):
    result = {"index": index, "started_utc": stamp(start), "started_monotonic": start,
              "status": status, "capture": {"root_call": root},
              "returned_tool_names": names or [], "thinking_token_budget": 4096}
    if end is not None:
        result.update(finished_utc=stamp(end), finished_monotonic=end,
                      http_status=200 if status == "COMPLETE" else 502,
                      usage={"completion_tokens": 100}, decode={"server_decode_tok_s": 12})
    return result


def fixture():
    task = {"instance_id": "PRIVATE_TASK", "repo": "PRIVATE_REPO", "resolved": True,
            "test_exit_code": 0, "tool_calls": 1, "total_llm_calls": 1,
            "task_index": 0, "duration_seconds": 480, "agent_patch_size": 1,
            "error": "PRIVATE_ERROR"}
    native = {**task, "task_id": task["instance_id"], "agent_patch": "x"}
    arm = {"rows": [native], "started_utc": stamp(0), "finished_utc": stamp(480),
           "status": "PUBLIC_TASK_NATIVE_RETURNED", "preservation": {"passed": True},
           "task_prompt": "SECRET_PROMPT", "credential": "SECRET_CREDENTIAL"}
    verification = {"finalpytest_count": 1, "actual_cat_junit_count": 1, "capture_errors": []}
    watchdog = {"status": "NATIVE_SINGLE_CANARY_RETURNED_REVIEW_REQUIRED",
                "worker_exit_code_before_teardown": 0,
                "teardown": {"survivors": []},
                "nvml_after_teardown": {"returncode": 0, "rows": []},
                "outer_notebook_packet_preservation": {"passed": True}}
    ledger = {"rows": [request(1, 1, 21, names=["edit_file"])], "prompt": "SECRET_PROMPT"}
    return [ledger, [task], arm, verification, watchdog]


def evaluate(values):
    return audit(*values, budget_seconds=480)


class EvidenceTests(unittest.TestCase):
    def test_valid_native_evidence_still_has_no_official_score(self):
        result = evaluate(fixture())
        self.assertTrue(result["outcome"]["native_execution_and_capture_evidence_complete"])
        self.assertIsNone(result["outcome"]["official_score"])
        self.assertIn("UNPROVEN", result["quality_promotion"])

    def test_privacy_projection_omits_arbitrary_strings(self):
        values = fixture()
        values[0]["rows"][0]["returned_tool_names"].append("SECRET_TOOL")
        text = json.dumps(evaluate(values))
        for secret in ("SECRET_PROMPT", "SECRET_CREDENTIAL", "PRIVATE_TASK", "PRIVATE_REPO", "PRIVATE_ERROR", "SECRET_TOOL"):
            self.assertNotIn(secret, text)

    def test_long_tail_compaction_failure_and_censor_all_count(self):
        values = fixture()
        values[0]["rows"] = [request(1, 0, 10), request(2, 10, 20), request(3, 20, 323),
                             request(4, 323, 369, root=False), request(5, 369, 459, status="ERROR"),
                             request(6, 459, None, status="STARTED")]
        result = evaluate(values)["timing"]
        self.assertEqual(result["observed_requests"], 6)
        self.assertEqual(result["completed_root_median_seconds"], 10)
        self.assertEqual(result["failed_model_seconds"], 90)
        self.assertEqual(result["completed_compaction_seconds"], 46)
        self.assertEqual(result["censored_model_seconds_arm_clock_estimate"], 21)
        self.assertEqual(result["finished_model_seconds"], 459)
        self.assertGreater(result["longest_finished_root_budget_fraction"], .6)

    def test_reasoning_cap_rate_is_unknown_with_completion_counts_only(self):
        result = evaluate(fixture())["tokens"]
        self.assertEqual(result["max_reported_completion_tokens"], 100)
        self.assertIsNone(result["reasoning_cap_hit_rate"])

    def test_no_junit_does_not_qualify(self):
        values = fixture(); values[3]["actual_cat_junit_count"] = 0
        self.assertFalse(evaluate(values)["outcome"]["native_execution_and_capture_evidence_complete"])

    def test_returned_edit_does_not_prove_a_patch(self):
        values = fixture(); values[1][0]["agent_patch_size"] = 0; values[2]["rows"][0]["agent_patch"] = ""
        self.assertFalse(evaluate(values)["outcome"]["patch_and_verification_evidence_complete"])

    def test_boolean_exit_is_invalid_evidence(self):
        values = fixture(); values[1][0]["test_exit_code"] = False; values[2]["rows"][0]["test_exit_code"] = False
        with self.assertRaises(ValueError): evaluate(values)

    def test_process_error_is_not_qualified_despite_patch_and_tests(self):
        values = fixture(); values[4]["worker_exit_code_before_teardown"] = 2
        self.assertFalse(evaluate(values)["outcome"]["native_execution_and_capture_evidence_complete"])

    def test_execution_capture_complete_does_not_mean_task_resolved(self):
        values = fixture()
        for row in (values[1][0], values[2]["rows"][0]):
            row["resolved"] = False; row["test_exit_code"] = 1
        result = evaluate(values)
        self.assertTrue(result["outcome"]["native_execution_and_capture_evidence_complete"])
        self.assertFalse(result["outcome"]["native_tests_passed"])
        self.assertIn("UNPROVEN", result["quality_promotion"])

    def test_missing_both_task_identities_is_rejected(self):
        values = fixture()
        for row, identity in ((values[1][0], "instance_id"), (values[2]["rows"][0], "task_id")):
            for key in (identity, "repo", "tool_calls", "total_llm_calls", "task_index"):
                row.pop(key)
        with self.assertRaises(ValueError): evaluate(values)

    def test_missing_both_task_counter_fields_is_rejected(self):
        values = fixture()
        values[1][0].pop("tool_calls"); values[2]["rows"][0].pop("tool_calls")
        with self.assertRaises(ValueError): evaluate(values)

    def test_duplicate_index_rejected(self):
        values = fixture(); values[0]["rows"].append(request(1, 22, 23))
        with self.assertRaises(ValueError): evaluate(values)

    def test_overlap_rejected_instead_of_double_counting(self):
        values = fixture(); values[0]["rows"].append(request(2, 20, 30))
        with self.assertRaises(ValueError): evaluate(values)

    def test_different_task_rejected(self):
        values = fixture(); values[2]["rows"][0]["task_id"] = "OTHER_TASK"
        with self.assertRaises(ValueError): evaluate(values)

    def test_nan_rejected(self):
        values = fixture(); values[1][0]["duration_seconds"] = math.nan
        with self.assertRaises(ValueError): evaluate(values)

    def test_boolean_patch_count_rejected(self):
        values = fixture(); values[1][0]["agent_patch_size"] = True
        with self.assertRaises(ValueError): evaluate(values)

    def test_multiple_task_denominator_rejected(self):
        values = fixture(); values[1].append(copy.deepcopy(values[1][0]))
        with self.assertRaises(ValueError): evaluate(values)

    def test_missing_root_class_rejected(self):
        values = fixture(); values[0]["rows"][0]["capture"] = {}
        with self.assertRaises(ValueError): evaluate(values)

    def test_unknown_status_rejected(self):
        values = fixture(); values[0]["rows"][0]["status"] = "SDK_DEFAULT"
        with self.assertRaises(ValueError): evaluate(values)

    def test_timestamp_and_monotonic_drift_rejected(self):
        values = fixture(); values[0]["rows"][0]["finished_monotonic"] += 1
        with self.assertRaises(ValueError): evaluate(values)

    def test_finish_outside_task_window_rejected(self):
        values = fixture(); values[0]["rows"] = [request(1, 470, 490)]
        with self.assertRaises(ValueError): evaluate(values)


if __name__ == "__main__":
    unittest.main()
