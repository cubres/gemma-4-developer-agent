# SPDX-License-Identifier: Apache-2.0
"""Invented failure-mode controls; no tasks, model, commands or network."""
import math
import unittest
from tool_feedback import ToolContract, ToolFeedback


def advisor():
    return ToolFeedback({
        "read_file": ToolContract({"filepath": "string", "start_line": "integer", "end_line": "integer"}, frozenset({"filepath"})),
        "write_file": ToolContract({"filepath": "string", "content": "string"}, frozenset({"filepath", "content"})),
        "run_command": ToolContract({"command": "string", "timeout": "number"}, frozenset({"command"})),
        "get_status": ToolContract({}, frozenset()),
        "submit_patch": ToolContract({}, frozenset()),
    })


class Controls(unittest.TestCase):
    def preflight(self, args, **kw):
        return advisor().preflight("read_file", args, remaining_seconds=180, **kw)

    def test_exact_range_passes_without_argument_mutation(self):
        args = {"filepath": "src/example.py", "start_line": 120, "end_line": 150}
        saved = dict(args)
        self.assertEqual(self.preflight(args).action, "PASS")
        self.assertEqual(args, saved)

    def test_typo_is_not_silently_ignored_or_rewritten(self):
        args = {"filepath": "src/example.py", 'start_line"': 120, "end_line": 150}
        result = self.preflight(args)
        self.assertEqual(result.code, "UNKNOWN_ARGUMENT")
        self.assertIn('start_line"', args)
        self.assertNotIn("src/example.py", result.message)

    def test_missing_range_cannot_fall_back_to_first_page(self):
        self.assertEqual(self.preflight({"filepath": "src/example.py"}).code, "READ_RANGE_REQUIRED")

    def test_one_missing_range_endpoint(self):
        self.assertEqual(self.preflight({"filepath": "src/example.py", "start_line": 120}).code, "READ_RANGE_REQUIRED")

    def test_inclusive_80_lines(self):
        self.assertEqual(self.preflight({"filepath": "a.py", "start_line": 10, "end_line": 89}).action, "PASS")

    def test_inclusive_81_lines(self):
        self.assertEqual(self.preflight({"filepath": "a.py", "start_line": 10, "end_line": 90}).code, "READ_RANGE_LARGE")

    def test_reversed_and_zero_ranges(self):
        for start, end in ((5, 4), (0, 8), (-1, 2)):
            self.assertEqual(self.preflight({"filepath": "a.py", "start_line": start, "end_line": end}).code, "READ_RANGE_INVALID")

    def test_bool_is_not_integer(self):
        self.assertEqual(self.preflight({"filepath": "a.py", "start_line": True, "end_line": 3}).code, "ARGUMENT_TYPE")

    def test_absolute_scratch_write_rejected_locally(self):
        result = advisor().preflight("write_file", {"filepath": "/tmp/example.py", "content": "invented"}, remaining_seconds=180)
        self.assertEqual(result.code, "WORKSPACE_PATH")
        self.assertNotIn("invented", result.message)

    def test_workspace_absolute_write_passes_lexical_check(self):
        self.assertEqual(advisor().preflight("write_file", {"filepath": "/workspace/src/example.py", "content": "x"}, remaining_seconds=180).action, "PASS")

    def test_workspace_prefix_collision(self):
        self.assertEqual(advisor().preflight("write_file", {"filepath": "/workspace-other/a.py", "content": "x"}, remaining_seconds=180).code, "WORKSPACE_PATH")

    def test_parent_segments_are_rejected(self):
        for path in ("../a.py", "src/../../a.py", "/workspace/../a.py"):
            self.assertEqual(self.preflight({"filepath": path, "start_line": 1, "end_line": 2}).code, "WORKSPACE_PATH")

    def test_non_posix_and_null_paths(self):
        for path in ("src\\a.py", "a\x00b", "", "~/.a", "."):
            self.assertEqual(self.preflight({"filepath": path, "start_line": 1, "end_line": 2}).code, "WORKSPACE_PATH")

    def test_unknown_tool_and_nested_values(self):
        self.assertEqual(advisor().preflight("unknown", {}, remaining_seconds=180).code, "UNKNOWN_TOOL")
        self.assertEqual(self.preflight({"filepath": {"x": "a"}}).code, "ARGUMENT_TYPE")

    def test_unknown_keys_do_not_echo_private_values(self):
        result = self.preflight({"filepath": "private-value", "secret": "private-secret"})
        self.assertEqual(result.code, "UNKNOWN_ARGUMENT")
        self.assertNotIn("private", result.message)

    def test_oversize_and_invalid_utf8(self):
        for value in ("x" * 262145, "\ud800"):
            self.assertEqual(self.preflight({"filepath": value}).code, "ARGUMENT_SIZE")

    def test_budget_boundary_and_finish(self):
        a = advisor()
        args = {"command": "invented"}
        self.assertEqual(a.preflight("run_command", args, remaining_seconds=75).action, "PASS")
        self.assertEqual(a.preflight("run_command", args, remaining_seconds=74.9).action, "FINISH")
        self.assertEqual(a.preflight("run_command", args, remaining_seconds=0, purpose="finish").action, "PASS")

    def test_invalid_remaining_time(self):
        for value in (True, -1, math.inf, math.nan, 86401):
            with self.assertRaises(ValueError):
                advisor().preflight("run_command", {"command": "x"}, remaining_seconds=value)

    def test_success_label_cannot_hide_nested_failure(self):
        self.assertEqual(advisor().observe_command(status="ok", exit_code=1, error_present=False, purpose="check").code, "CHECK_FAILED_ONCE")

    def test_error_cannot_be_overridden_by_zero_exit_label(self):
        self.assertEqual(advisor().observe_command(status="error", exit_code=0, error_present=False, purpose="check").code, "CHECK_FAILED_ONCE")

    def test_actual_error_cannot_be_overridden(self):
        self.assertEqual(advisor().observe_command(status="ok", exit_code=0, error_present=True, purpose="check").code, "CHECK_FAILED_ONCE")

    def test_missing_exit_is_unknown(self):
        self.assertEqual(advisor().observe_command(status="ok", exit_code=None, error_present=False, purpose="check").action, "UNKNOWN")

    def test_two_distinct_failed_checks_stop_recovery(self):
        a = advisor()
        a.observe_command(status="error", exit_code=1, error_present=True, purpose="scratch")
        result = a.observe_command(status="error", exit_code=1, error_present=True, purpose="check")
        self.assertEqual(result.code, "CHECK_RECOVERY_EXHAUSTED")
        self.assertEqual(a.preflight("run_command", {"command": "different invented text"}, remaining_seconds=180, purpose="scratch").action, "REASSESS")

    def test_source_and_finish_remain_available_after_failure(self):
        a = advisor()
        for _ in range(2):
            a.observe_command(status="error", exit_code=1, error_present=True, purpose="check")
        for purpose in ("source", "finish"):
            self.assertEqual(a.preflight("run_command", {"command": "invented"}, remaining_seconds=180, purpose=purpose).action, "PASS")

    def test_unknown_does_not_burn_or_reset_recovery(self):
        a = advisor()
        a.observe_command(status="ok", exit_code=None, error_present=False, purpose="check")
        self.assertEqual(a.observe_command(status="error", exit_code=1, error_present=True, purpose="check").code, "CHECK_FAILED_ONCE")

    def test_success_does_not_reset_task_recovery_budget(self):
        a = advisor()
        a.observe_command(status="error", exit_code=1, error_present=True, purpose="check")
        a.observe_command(status="ok", exit_code=0, error_present=False, purpose="check")
        self.assertEqual(a.observe_command(status="error", exit_code=1, error_present=True, purpose="check").code, "CHECK_RECOVERY_EXHAUSTED")

    def test_no_retention_of_argument_or_result_text(self):
        a = advisor()
        a.preflight("run_command", {"command": "PRIVATE_OPAQUE_TEXT"}, remaining_seconds=180)
        self.assertNotIn("PRIVATE_OPAQUE_TEXT", repr(vars(a)))

    def test_contracts_are_snapshot_and_immutable(self):
        properties = {"a": "string"}
        c = ToolContract(properties, frozenset({"a"}))
        properties["b"] = "string"
        self.assertNotIn("b", c.properties)
        with self.assertRaises(TypeError):
            c.properties["b"] = "string"

    def test_unsupported_schema_and_required_key(self):
        for properties, required in (({"a": "object"}, frozenset()), ({"a": "string"}, frozenset({"b"}))):
            with self.assertRaises(ValueError):
                ToolContract(properties, required)

    def test_invalid_outcome_types(self):
        a = advisor()
        for field, value in (("exit_code", True), ("exit_code", 256), ("status", "success"), ("error_present", 1), ("purpose", "guessed")):
            args = {"status": "ok", "exit_code": 0, "error_present": False, "purpose": "check"}
            args[field] = value
            with self.assertRaises(ValueError):
                a.observe_command(**args)

    def test_missing_required_and_bad_argument_container(self):
        self.assertEqual(advisor().preflight("write_file", {"filepath": "a.py"}, remaining_seconds=180).code, "MISSING_ARGUMENT")
        self.assertEqual(advisor().preflight("write_file", [], remaining_seconds=180).code, "ARGUMENT_SHAPE")

    def test_nonfinite_number_argument(self):
        self.assertEqual(advisor().preflight("run_command", {"command": "x", "timeout": math.nan}, remaining_seconds=180).code, "ARGUMENT_TYPE")

    def test_arbitrary_schema_values_are_rejected_without_protocol_calls(self):
        class Trap:
            def __hash__(self):
                raise AssertionError("Must not hash arbitrary schema values")
            def __eq__(self, _other):
                raise AssertionError("Must not compare arbitrary schema values")
        for value in ([], {}, Trap()):
            with self.assertRaises(ValueError):
                ToolContract({"a": value}, frozenset())

    def test_required_keys_must_be_exact_primitive_identifiers(self):
        class StringSubclass(str):
            pass
        for required in (frozenset({1}), frozenset({'a"'}), frozenset({StringSubclass("a")})):
            with self.assertRaises(ValueError):
                ToolContract({"a": "string"}, required)

    def test_huge_numeric_inputs_return_fixed_failure(self):
        huge = 10 ** 1000
        self.assertEqual(self.preflight({"filepath": "a.py", "start_line": huge, "end_line": huge}).code, "ARGUMENT_TYPE")
        self.assertEqual(advisor().preflight("run_command", {"command": "x", "timeout": huge}, remaining_seconds=180).code, "ARGUMENT_TYPE")
        with self.assertRaises(ValueError):
            advisor().preflight("run_command", {"command": "x"}, remaining_seconds=huge)

    def test_integer_boundary_is_bounded(self):
        for value in ((1 << 63), -(1 << 63)):
            self.assertEqual(self.preflight({"filepath": "a.py", "start_line": value, "end_line": value}).code, "ARGUMENT_TYPE")

    def test_role_schema_drift_fails_at_construction(self):
        with self.assertRaises(ValueError):
            ToolFeedback({"write_file": ToolContract({"filepath": "integer"}, frozenset({"filepath"}))})
        with self.assertRaises(ValueError):
            ToolFeedback({"read_file": ToolContract({"filepath": "string"}, frozenset({"filepath"}))})

    def test_null_float_and_string_range_are_explicit_treatment_rejections(self):
        for value in (None, 1.0, "1"):
            self.assertEqual(self.preflight({"filepath": "a.py", "start_line": value, "end_line": 2}).code, "ARGUMENT_TYPE")

    def test_purpose_is_exact_string(self):
        class StringSubclass(str):
            pass
        for purpose in (1, [], StringSubclass("source")):
            with self.assertRaises(ValueError):
                advisor().preflight("run_command", {"command": "x"}, remaining_seconds=180, purpose=purpose)

    def test_low_time_precedes_argument_recovery(self):
        self.assertEqual(advisor().preflight("read_file", {"typo": "x"}, remaining_seconds=1).action, "FINISH")

    def test_exhausted_checks_do_not_restart_on_malformed_proposal(self):
        a = advisor()
        for _ in range(2):
            a.observe_command(status="error", exit_code=1, error_present=True, purpose="check")
        self.assertEqual(a.preflight("run_command", {"typo": "x"}, remaining_seconds=180, purpose="check").action, "REASSESS")

    def test_zero_argument_status_and_submit_tools(self):
        for name in ("get_status", "submit_patch"):
            self.assertEqual(advisor().preflight(name, {}, remaining_seconds=180, purpose="finish").action, "PASS")

    def test_zero_argument_tool_rejects_extra_keys(self):
        result = advisor().preflight("submit_patch", {"summary": "private invented text"}, remaining_seconds=180, purpose="finish")
        self.assertEqual(result.code, "UNKNOWN_ARGUMENT")
        self.assertEqual(result.message, "This reviewed tool takes no arguments.")

    def test_workspace_root_is_not_a_file_path(self):
        for path in ("/workspace", "/workspace/.", "/workspace//"):
            self.assertEqual(self.preflight({"filepath": path, "start_line": 1, "end_line": 2}).code, "WORKSPACE_PATH")


if __name__ == "__main__":
    unittest.main()
