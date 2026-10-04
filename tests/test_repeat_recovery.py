# MIT License
# Copyright (c) 2026 cubres
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Deterministic controller mechanics; no agent bundle or model execution.

From the repository root: PYTHONPATH=src python -m unittest discover -s tests -v
"""
import copy
import json
import unittest

from repeat_recovery import (FEEDBACK_KEY, PrivateRecoveryBoundary,
                             RepeatRecoveryController, observation_kind)


EMPTY_GREP = {"status": "error", "error_type": "CommandError", "error_message": "",
              "details": {"stdout": "", "stderr": "", "exit_code": 1}}
MISSING = {"error": "Invoking `edit_file()` failed as the following mandatory input parameters are not present:\nold_string\nYou could retry calling this tool, but it is IMPORTANT for you to provide all the mandatory parameters."}
CAPTURED = {"status": "ok", "patch_size": 200, "files_changed": 1}


class ControllerMechanics(unittest.TestCase):
    def observation(self, ctrl, *, tool="run_command", args=None, obs=EMPTY_GREP, actor="root", charged=None):
        return ctrl.observe(actor=actor, tool=tool, arguments=args or {"command": "grep symbol source.py"},
                            observation=obs, charged_tool_calls=charged)

    def test_no_match_is_absence_not_command_failure(self):
        self.assertEqual(observation_kind("run_command", EMPTY_GREP, {"command": "grep symbol source.py"}), "absence_result_exit_1")

    def test_silent_non_search_failure_is_not_a_grep_absence(self):
        self.assertEqual(observation_kind("run_command", EMPTY_GREP, {"command": "python -c 'raise SystemExit(1)'"}), "tool_error")

    def test_quoted_search_word_is_not_a_search_invocation(self):
        self.assertEqual(observation_kind("run_command", EMPTY_GREP, {"command": "python -c 'print(\"grep symbol\")'"}), "tool_error")

    def test_git_grep_absence_is_recognized(self):
        self.assertEqual(observation_kind("run_command", EMPTY_GREP, {"command": "git grep -n symbol"}), "absence_result_exit_1")

    def test_find_exit_one_is_a_tool_error(self):
        self.assertEqual(observation_kind("run_command", EMPTY_GREP, {"command": "find . -name source.py"}), "tool_error")

    def test_nonempty_stderr_is_a_real_tool_error(self):
        obs = copy.deepcopy(EMPTY_GREP)
        obs["details"]["stderr"] = "fatal: invalid revision"
        self.assertEqual(observation_kind("run_command", obs), "tool_error")

    def test_empty_success_is_empty_not_error(self):
        obs = {"status": "ok", "stdout": "", "stderr": "", "exit_code": 0}
        self.assertEqual(observation_kind("run_command", obs), "empty_success_result")

    def test_feedback_on_third_stable_call(self):
        ctrl = RepeatRecoveryController()
        self.assertIsNone(self.observation(ctrl).feedback)
        self.assertIsNone(self.observation(ctrl).feedback)
        decision = self.observation(ctrl)
        self.assertEqual(decision.event, "REPEAT_RECOVERY")
        self.assertIn("stable absence", decision.feedback)
        self.assertFalse(decision.verified_correct)

    def test_feedback_cadence_does_not_repeat_every_call(self):
        ctrl = RepeatRecoveryController()
        emits = [n for n in range(1, 25) if self.observation(ctrl).feedback]
        self.assertEqual(emits, [3, 6, 12, 24])

    def test_different_arguments_break_repeat_chain(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl); self.observation(ctrl)
        decision = self.observation(ctrl, args={"command": "find . -name source.py"})
        self.assertEqual(decision.run_count, 1)
        self.assertIsNone(decision.feedback)

    def test_different_output_breaks_repeat_chain(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl); self.observation(ctrl)
        decision = self.observation(ctrl, obs={"status": "ok", "stdout": "source.py:1:symbol", "stderr": "", "exit_code": 0})
        self.assertEqual(decision.run_count, 1)

    def test_budget_warning_does_not_hide_stability(self):
        ctrl = RepeatRecoveryController()
        for n in range(3):
            obs = {**EMPTY_GREP, "budget_warning": f"{10-n} remaining"}
            decision = self.observation(ctrl, obs=obs)
        self.assertEqual(decision.event, "REPEAT_RECOVERY")

    def test_meaningful_nested_budget_field_is_preserved(self):
        ctrl = RepeatRecoveryController()
        for n in range(3):
            obs = {"status": "ok", "data": {"budget_warning": n}}
            decision = self.observation(ctrl, obs=obs)
        self.assertEqual(decision.run_count, 1)

    def test_native_rejections_count_raw_without_guessing_charged(self):
        ctrl = RepeatRecoveryController()
        for _ in range(106):
            decision = self.observation(ctrl, tool="edit_file", args={"filepath": "module.py", "new_string": "x"}, obs=MISSING, charged=16)
        self.assertEqual(decision.raw_invocations, 106)
        self.assertEqual(decision.charged_tool_calls, 16)
        self.assertEqual(decision.observation_kind, "native_argument_validation")

    def test_missing_fields_feedback_is_specific(self):
        ctrl = RepeatRecoveryController()
        for _ in range(3):
            decision = self.observation(ctrl, tool="edit_file", args={"filepath": "module.py"}, obs=MISSING)
        self.assertIn("old_string", decision.feedback)
        self.assertIn("native run_command", decision.feedback)

    def test_unknown_charged_counter_stays_unknown(self):
        ctrl = RepeatRecoveryController()
        for _ in range(3): decision = self.observation(ctrl)
        self.assertIsNone(decision.charged_tool_calls)
        self.assertIn("charged tools=unknown", decision.feedback)

    def test_status_does_not_break_repetition(self):
        ctrl = RepeatRecoveryController()
        for n in range(3):
            self.observation(ctrl, tool="get_status", args={}, obs={"status": "ok", "tool_calls_used": n, "patch_submitted": False})
            decision = self.observation(ctrl)
        self.assertEqual(decision.event, "REPEAT_RECOVERY")
        self.assertEqual(decision.raw_invocations, 6)
        self.assertEqual(decision.charged_tool_calls, 2)

    def test_authoritative_counter_decrease_is_rejected(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, charged=7)
        with self.assertRaises(ValueError): self.observation(ctrl, charged=6)

    def test_conflicting_counter_sources_are_rejected(self):
        ctrl = RepeatRecoveryController()
        with self.assertRaises(ValueError):
            self.observation(ctrl, tool="get_status", obs={"status": "ok", "tool_calls_used": 5}, charged=6)

    def test_boolean_counter_is_not_an_integer_count(self):
        ctrl = RepeatRecoveryController()
        with self.assertRaises(ValueError): self.observation(ctrl, charged=True)

    def test_submission_requires_valid_nonempty_capture(self):
        ctrl = RepeatRecoveryController()
        decision = self.observation(ctrl, tool="submit_patch", args={}, obs=CAPTURED)
        self.assertEqual(decision.event, "PATCH_CAPTURE_CONFIRMED")
        self.assertFalse(decision.terminal_handoff)
        final = ctrl.observe_final(actor="root", text="Completed the change.")
        self.assertTrue(final.terminal_handoff)
        self.assertFalse(final.verified_correct)

    def test_empty_capture_does_not_finish(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs={"status": "ok", "patch_size": 0, "files_changed": 0})
        self.assertFalse(ctrl.observe_final(actor="root", text="Done").terminal_handoff)

    def test_failed_capture_does_not_finish(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs={"status": "error", "error_type": "GitDiffError"})
        self.assertFalse(ctrl.observe_final(actor="root", text="Done").terminal_handoff)

    def test_malformed_capture_types_do_not_finish(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs={"status": "ok", "patch_size": True, "files_changed": 1})
        self.assertFalse(ctrl.observe_final(actor="root", text="Done").terminal_handoff)

    def test_final_text_without_capture_does_not_finish(self):
        self.assertFalse(RepeatRecoveryController().observe_final(actor="root", text="Done").terminal_handoff)

    def test_literal_tool_text_does_not_finish(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs=CAPTURED)
        self.assertFalse(ctrl.observe_final(actor="root", text="<|tool_call>call:pk_done{}<tool_call|>").terminal_handoff)

    def test_scout_cannot_finalize_root(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs=CAPTURED)
        self.assertFalse(ctrl.observe_final(actor="scout", text="Located it").terminal_handoff)

    def test_unknown_helper_is_not_a_submission_signal(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="pk_done", args={}, obs={"status": "ok"})
        self.assertFalse(ctrl.observe_final(actor="root", text="Done").terminal_handoff)

    def test_unknown_tool_after_capture_invalidates_confirmation(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs=CAPTURED)
        self.observation(ctrl, tool="unknown_tool", args={}, obs={"status": "ok"})
        self.assertFalse(ctrl.observe_final(actor="root", text="Done").terminal_handoff)

    def test_command_after_capture_requires_fresh_capture(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs=CAPTURED)
        self.observation(ctrl, obs={"status": "ok", "stdout": "", "stderr": "", "exit_code": 0})
        self.assertFalse(ctrl.observe_final(actor="root", text="Done").terminal_handoff)

    def test_native_validation_does_not_claim_executed_mutation(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, tool="submit_patch", args={}, obs=CAPTURED)
        self.observation(ctrl, tool="edit_file", obs=MISSING)
        self.assertTrue(ctrl.observe_final(actor="root", text="Done").terminal_handoff)

    def test_actors_have_separate_repeat_streams(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl); self.observation(ctrl, actor="scout")
        self.assertIsNone(self.observation(ctrl).feedback)
        self.assertEqual(self.observation(ctrl).event, "REPEAT_RECOVERY")

    def test_original_inputs_are_unchanged(self):
        ctrl = RepeatRecoveryController(); boundary = PrivateRecoveryBoundary(ctrl)
        original = copy.deepcopy(EMPTY_GREP)
        for _ in range(3): response, decision = boundary.after_tool(actor="root", tool="run_command", arguments={"command": "grep symbol source.py"}, result=EMPTY_GREP)
        self.assertEqual(EMPTY_GREP, original)
        self.assertEqual(response["details"], original["details"])
        self.assertEqual(response["status"], original["status"])
        self.assertIn(FEEDBACK_KEY, response)

    def test_string_and_dictionary_return_contracts_are_equivalent(self):
        ctrl = RepeatRecoveryController()
        self.observation(ctrl, obs=json.dumps(EMPTY_GREP))
        self.observation(ctrl, obs={"result": json.dumps(EMPTY_GREP)})
        self.assertEqual(self.observation(ctrl).event, "REPEAT_RECOVERY")

    def test_controller_feedback_does_not_create_apparent_progress(self):
        ctrl = RepeatRecoveryController(); boundary = PrivateRecoveryBoundary(ctrl)
        for _ in range(3): response, _ = boundary.after_tool(actor="root", tool="run_command", arguments={"command": "grep symbol source.py"}, result=EMPTY_GREP)
        decision = self.observation(ctrl, obs=response)
        self.assertEqual(decision.run_count, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
