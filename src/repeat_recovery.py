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

"""Original observation controller for private evaluation; no tool execution.

The reviewed organizer runner supplies no custom callback registry.
This module is development infrastructure, with no deployed-agent or solve-rate
claim. It changes neither a callable tool's execution nor its budget accounting.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shlex
from dataclasses import dataclass, field
from typing import Any, Mapping

SOURCE_BOUNDARY = {
    "private_app_plugin_insertion": "swegemma/harness/agent_runner.py:406 App plugins",
    "after_native_validation": "google/adk/flows/llm_flows/functions.py:548 after_tool_callback",
    "missing_args_before_native_budget": "google/adk/tools/function_tool.py:184",
    "source_identity_gap": "B/E attest versions and runner/agent hashes, not deployed native-tool member hashes. Hidden runtime unverified.",
    "official_submission_constraint": "compile_submission receives no callback_registry; a custom Python controller is not an established supported submission component.",
}

FEEDBACK_KEY = "repeat_observation_recovery"
FREE_TOOLS = frozenset({"get_status", "submit_patch"})
KNOWN_MUTATING_TOOLS = frozenset({"run_command", "edit_file", "write_file", "run_skill_script"})
KNOWN_READ_ONLY_TOOLS = frozenset({"read_file", "scout", "list_skills", "load_skill", "load_skill_resource"})


def decode_observation(observation: Any) -> Any:
    """Normalize old JSON-string and newer dict tool returns without mutation."""
    value = copy.deepcopy(observation)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value
    if isinstance(value, dict) and "result" in value:
        inner = value["result"]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                return value
        if isinstance(inner, dict):
            siblings = {k: v for k, v in value.items() if k != "result"}
            return {**siblings, **inner}
    return value


def normalized_observation(observation: Any) -> Any:
    value = decode_observation(observation)
    if isinstance(value, dict):
        # Ignore only known top-level tool metadata. Nested fields remain data.
        value.pop("budget_warning", None)
        value.pop(FEEDBACK_KEY, None)
    return value


def _search_command(arguments: Mapping[str, Any] | None) -> bool:
    """Recognize explicit search invocations, without executing shell text."""
    command = str((arguments or {}).get("command", ""))
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return bool(tokens) and (tokens[0] in {"grep", "rg"} or tokens[:2] == ["git", "grep"])


def observation_kind(tool: str, observation: Any, arguments: Mapping[str, Any] | None = None) -> str:
    value = decode_observation(observation)
    if not isinstance(value, dict):
        return "unstructured_observation"
    error = str(value.get("error", value.get("error_message", "")))
    if "mandatory input parameters" in error:
        return "native_argument_validation"
    io = value.get("details", value)
    if isinstance(io, dict):
        # grep uses exit 1 for a legitimate no-match result. Do not turn this
        # into positive evidence of broken command execution or reward it.
        if tool == "run_command" and _search_command(arguments) and io.get("exit_code") == 1 and io.get("stdout") == "" and io.get("stderr") == "":
            return "absence_result_exit_1"
        if tool == "run_command" and io.get("exit_code") == 0 and io.get("stdout") == "" and io.get("stderr") == "":
            return "empty_success_result"
    if value.get("status") == "error" or "error" in value:
        return "tool_error"
    if value.get("status") == "ok":
        return "successful_observation"
    return "unstructured_observation"


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _capture_confirmed(tool: str, value: Any) -> bool:
    if not isinstance(value, dict) or value.get("status") != "ok":
        return False
    size = value.get("patch_size")
    if not _nonnegative_int(size) or size == 0:
        return False
    if tool == "submit_patch":
        count = value.get("files_changed")
        return _nonnegative_int(count) and count > 0
    return tool == "get_status" and value.get("patch_submitted") is True


@dataclass(frozen=True)
class RecoveryDecision:
    event: str
    observation_kind: str
    run_count: int
    raw_invocations: int
    charged_tool_calls: int | None
    feedback: str | None = None
    terminal_handoff: bool = False
    verified_correct: bool = False


@dataclass
class _ActorState:
    fingerprint: str | None = None
    run_count: int = 0
    patch_capture_confirmed: bool = False


@dataclass
class RepeatRecoveryController:
    """One controller per task/session; actor streams are kept separate."""
    trigger_count: int = 3
    root_actor: str = "root"
    raw_invocations: int = 0
    charged_tool_calls: int | None = None
    _actors: dict[str, _ActorState] = field(default_factory=dict)

    def __post_init__(self):
        if not _nonnegative_int(self.trigger_count) or self.trigger_count < 2:
            raise ValueError("trigger_count must be an integer >= 2")

    def _update_charged(self, value: int | None):
        if value is None:
            return
        if not _nonnegative_int(value):
            raise ValueError("charged counter must be a nonnegative integer or unknown")
        if self.charged_tool_calls is not None and value < self.charged_tool_calls:
            raise ValueError("charged counter decreased; start a new session controller")
        self.charged_tool_calls = value

    def observe(self, *, actor: str, tool: str, arguments: Mapping[str, Any], observation: Any,
                charged_tool_calls: int | None = None) -> RecoveryDecision:
        """Consume one original tool response; never guess a charged counter."""
        value = decode_observation(observation)
        if tool == "get_status" and isinstance(value, dict) and value.get("status") == "ok":
            reported = value.get("tool_calls_used")
            if _nonnegative_int(reported):
                if charged_tool_calls is not None and charged_tool_calls != reported:
                    raise ValueError("conflicting authoritative charged counters")
                charged_tool_calls = reported
        self._update_charged(charged_tool_calls)
        self.raw_invocations += 1
        state = self._actors.setdefault(actor, _ActorState())
        kind = observation_kind(tool, value, arguments)
        if _capture_confirmed(tool, value):
            state.patch_capture_confirmed = True
            return self._decision("PATCH_CAPTURE_CONFIRMED", kind, state, "A nonempty patch was captured; finish with a text-only completion. Correctness is unverified.")
        if tool == "submit_patch":
            state.patch_capture_confirmed = False
            return self._decision("PATCH_CAPTURE_UNCONFIRMED", kind, state, "No nonempty patch capture is confirmed. Inspect the working diff and complete the requested source change before finishing.")
        if tool == "get_status":
            # Status polling must not let a repeated command evade detection.
            if isinstance(value, dict) and value.get("patch_submitted") is False:
                state.patch_capture_confirmed = False
            return self._decision("STATUS_OBSERVED", kind, state)
        if (tool in KNOWN_MUTATING_TOOLS or tool not in KNOWN_READ_ONLY_TOOLS) and kind != "native_argument_validation":
            # A command might mutate source even if it returns an error. The
            # controller cannot inspect the filesystem and assumes no safety.
            state.patch_capture_confirmed = False
        encoded = json.dumps([actor, tool, dict(arguments), normalized_observation(value)],
                             sort_keys=True, separators=(",", ":"), allow_nan=False)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        state.run_count = state.run_count + 1 if state.fingerprint == fingerprint else 1
        state.fingerprint = fingerprint
        emit = self._should_emit(state.run_count)
        event = "REPEAT_RECOVERY" if emit else "OBSERVATION"
        return self._decision(event, kind, state, self._feedback(tool, kind, value) if emit else None)

    def _should_emit(self, count: int) -> bool:
        if count < self.trigger_count or count % self.trigger_count:
            return False
        multiple = count // self.trigger_count
        # Repeat feedback at 3,6,12,... without adding it on every response.
        return multiple & (multiple - 1) == 0

    def _feedback(self, tool: str, kind: str, value: Any) -> str:
        counters = f"raw tool responses={self.raw_invocations}; charged tools="
        counters += "unknown" if self.charged_tool_calls is None else str(self.charged_tool_calls)
        if kind == "native_argument_validation":
            error = str(value.get("error", ""))
            required = error.split("not present:\n", 1)[-1].split("\nYou could", 1)[0].strip()
            action = (f"Provide the missing required fields ({required}) in a complete registered tool call. "
                      "If multi-string edits continue to parse incorrectly, use native run_command with one command argument and a short patch script; then inspect git diff.")
        elif kind in {"absence_result_exit_1", "empty_success_result"}:
            action = ("This is a stable absence/empty result, not proof of broken command execution. "
                      "Inspect the repository layout, nearby definitions and imports, or determine whether the requested symbol must be added. Change the search before another attempt.")
        elif tool == "read_file":
            action = ("Use a filepath containing only the path; line bounds belong in their own fields. "
                      "If the path is valid, act on the code already returned or inspect a different relevant location.")
        elif kind == "tool_error":
            action = "The same error is unchanged. Correct the path, quoting or call arguments before retrying; use only registered tools."
        else:
            action = ("The same call returned the same observation. Use its result to change the source or inspect a different relevant condition. "
                      "Repeat a test after an actual edit, then capture a nonempty patch through submit_patch.")
        return f"Stable identical call and observation repeated. {counters}. {action}"

    def _decision(self, event, kind, state, feedback=None, terminal=False):
        return RecoveryDecision(event, kind, state.run_count, self.raw_invocations,
                                self.charged_tool_calls, feedback, terminal)

    def observe_final(self, *, actor: str, text: str) -> RecoveryDecision:
        """Recognize final handoff only; this never certifies a task as solved."""
        state = self._actors.setdefault(actor, _ActorState())
        literal_tool = any(marker in text for marker in ("<|tool_call", "<tool_call|>", '"tool_calls"'))
        valid = actor == self.root_actor and state.patch_capture_confirmed and bool(text.strip()) and not literal_tool
        if valid:
            return self._decision("TERMINAL_HANDOFF", "text_completion", state, terminal=True)
        return self._decision("FINAL_UNCONFIRMED", "text_completion", state,
                              "Completion is unconfirmed. Use registered native tools to capture a nonempty patch, then return a text-only completion.")


class PrivateRecoveryBoundary:
    """Pure adapter for a private after-tool hook; caller owns session lifecycle.

    An App plugin may call after_tool after native validation and execution.
    This wrapper preserves the original normalized response and adds feedback
    only when needed. No adapter is installed in the current organizer runner.
    """
    def __init__(self, controller: RepeatRecoveryController):
        self.controller = controller

    def after_tool(self, *, actor: str, tool: str, arguments: Mapping[str, Any], result: Any,
                   charged_tool_calls: int | None = None) -> tuple[Any, RecoveryDecision]:
        decision = self.controller.observe(actor=actor, tool=tool, arguments=arguments,
                                           observation=result, charged_tool_calls=charged_tool_calls)
        if decision.feedback is None:
            return result, decision
        response = decode_observation(result)
        if not isinstance(response, dict):
            response = {"result": response}
        response[FEEDBACK_KEY] = {
            "event": decision.event, "feedback": decision.feedback,
            "raw_invocations": decision.raw_invocations,
            "charged_tool_calls": decision.charged_tool_calls,
            "verified_correct": False,
        }
        return response, decision
