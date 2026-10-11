# SPDX-License-Identifier: Apache-2.0
"""Data-only advice for coding-agent tool calls; never execute or rewrite a call.

Schemas must come from the caller's reviewed runtime, not a model's assertion.
This module neither reads files nor resolves paths, and its decisions grant no
permission. Tool execution, charged-call accounting and final verification stay
with the native evaluator. One instance represents one task.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Mapping

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
_MAX_ARGUMENTS = 16
_MAX_STRING_BYTES = 262144
_MAX_INTEGER = (1 << 63) - 1
_MAX_NUMBER = 1e12


@dataclass(frozen=True)
class Advice:
    action: str
    code: str
    message: str


@dataclass(frozen=True)
class ToolContract:
    """Small strict contract; unsupported schema types fail explicitly."""
    properties: Mapping[str, str]
    required: frozenset[str]

    def __post_init__(self):
        if type(self.properties) is not dict or not 0 <= len(self.properties) <= _MAX_ARGUMENTS:
            raise ValueError("Bounded plain property dictionary required")
        properties = dict(self.properties)
        if any(type(k) is not str or not _IDENTIFIER.fullmatch(k) or type(v) is not str or v not in _TYPES
               for k, v in properties.items()):
            raise ValueError("Unsupported property contract")
        if (type(self.required) is not frozenset or len(self.required) > _MAX_ARGUMENTS
                or any(type(k) is not str or not _IDENTIFIER.fullmatch(k) for k in self.required)
                or not self.required <= properties.keys()):
            raise ValueError("Required keys must belong to the contract")
        object.__setattr__(self, "properties", MappingProxyType(properties))


def _finite_seconds(value):
    if (type(value) not in (int, float) or not 0 <= value <= 86400
            or (type(value) is float and not math.isfinite(value))):
        raise ValueError("A finite measured remaining-time value is required")
    return float(value)


def _lexical_workspace_path(value: str) -> bool:
    # This is an early usability check, not a symlink or security boundary.
    if not value or "\\" in value or "\x00" in value or value.startswith("~"):
        return False
    path = PurePosixPath(value)
    if ".." in path.parts or str(path) in (".", "/workspace"):
        return False
    return not path.is_absolute() or path.is_relative_to(PurePosixPath("/workspace"))


class ToolFeedback:
    """Advise, without dispatching tools, on malformed calls and wasted checks.

    All feedback is fixed text or reviewed schema key names. Arguments, paths,
    commands, task text and results are never returned in feedback or retained.
    Purpose labels and outcome fields need a trusted integration adapter. They
    are observations supplied by the caller, not inferred by this module.
    """

    def __init__(self, contracts: Mapping[str, ToolContract], *, minimum_finish_seconds=75):
        if type(contracts) is not dict or not 0 < len(contracts) <= 32:
            raise ValueError("Bounded plain contract dictionary required")
        if any(type(k) is not str or not _IDENTIFIER.fullmatch(k) or type(v) is not ToolContract
               for k, v in contracts.items()):
            raise ValueError("Invalid tool contracts")
        for name in ("read_file", "write_file", "edit_file"):
            if name in contracts and contracts[name].properties.get("filepath") != "string":
                raise ValueError("Recognized file role requires string filepath")
        if "read_file" in contracts:
            if any(contracts["read_file"].properties.get(key) != "integer"
                   for key in ("start_line", "end_line")):
                raise ValueError("Read-range policy requires declared integer range keys")
        self.contracts = MappingProxyType(dict(contracts))
        self.minimum_finish_seconds = _finite_seconds(minimum_finish_seconds)
        self._check_failures = 0

    def preflight(self, name: str, arguments: dict, *, remaining_seconds: float,
                  purpose: str = "source") -> Advice:
        remaining = _finite_seconds(remaining_seconds)
        if type(purpose) is not str or purpose not in ("source", "check", "scratch", "finish"):
            raise ValueError("Explicit bounded purpose required")
        if remaining < self.minimum_finish_seconds and purpose != "finish":
            return Advice("FINISH", "LOW_TIME", "Inspect the existing diff and finish honestly; start no new investigation or scratch repair.")
        if self._check_failures >= 2 and purpose in ("check", "scratch"):
            return Advice("REASSESS", "CHECK_RECOVERY_EXHAUSTED", "Stop repairing check programs. Reassess the source or finish with the validation limitation.")
        if type(name) is not str or name not in self.contracts:
            return Advice("REVISE", "UNKNOWN_TOOL", "Choose a tool from the reviewed runtime contract.")
        contract = self.contracts[name]
        if type(arguments) is not dict or len(arguments) > _MAX_ARGUMENTS:
            return Advice("REVISE", "ARGUMENT_SHAPE", "Use a bounded plain argument object.")
        if any(type(key) is not str for key in arguments):
            return Advice("REVISE", "ARGUMENT_KEYS", "Argument keys must be strings.")
        if arguments.keys() - contract.properties.keys():
            if not contract.properties:
                return Advice("REVISE", "UNKNOWN_ARGUMENT", "This reviewed tool takes no arguments.")
            keys = ", ".join(sorted(contract.properties))
            return Advice("REVISE", "UNKNOWN_ARGUMENT", "Use only these exact keys: " + keys + ".")
        if contract.required - arguments.keys():
            keys = ", ".join(sorted(contract.required))
            return Advice("REVISE", "MISSING_ARGUMENT", "Required exact keys: " + keys + ".")
        for key, value in arguments.items():
            kind = contract.properties[key]
            if kind == "number":
                valid = (type(value) in (int, float) and abs(value) <= _MAX_NUMBER
                         and (type(value) is not float or math.isfinite(value)))
            else:
                valid = type(value) is _TYPES[kind]
                if valid and kind == "integer":
                    valid = abs(value) <= _MAX_INTEGER
            if not valid:
                return Advice("REVISE", "ARGUMENT_TYPE", "Use the exact primitive types in the reviewed schema.")
            if type(value) is str:
                if len(value) > _MAX_STRING_BYTES:
                    return Advice("REVISE", "ARGUMENT_SIZE", "Use bounded valid UTF-8 arguments.")
                try:
                    bounded = len(value.encode("utf-8")) <= _MAX_STRING_BYTES
                except UnicodeEncodeError:
                    bounded = False
                if not bounded:
                    return Advice("REVISE", "ARGUMENT_SIZE", "Use bounded valid UTF-8 arguments.")
        if name in ("read_file", "write_file", "edit_file") and "filepath" in arguments:
            if not _lexical_workspace_path(arguments["filepath"]):
                return Advice("REVISE", "WORKSPACE_PATH", "Use a repository path within the tool workspace; scratch checks need a separate reviewed command route.")
        if name == "read_file":
            start, end = arguments.get("start_line"), arguments.get("end_line")
            if start is None or end is None:
                return Advice("REVISE", "READ_RANGE_REQUIRED", "Supply both start_line and end_line explicitly; do not rely on a default first-page read.")
            if type(start) is not int or type(end) is not int or start < 1 or end < start:
                return Advice("REVISE", "READ_RANGE_INVALID", "Use a positive inclusive line range in source order.")
            if end - start + 1 > 80:
                return Advice("REVISE", "READ_RANGE_LARGE", "Request at most 80 inclusive lines around the known source location.")
        return Advice("PASS", "CONTRACT_OK", "The local preflight found no covered mismatch; native tool checks still apply.")

    def observe_command(self, *, status: str, exit_code: int | None,
                        error_present: bool, purpose: str) -> Advice:
        """Normalize actual result fields, never a formatted log's success label.

        A nonzero nested exit or actual error outweighs a misleading status.
        No exit evidence is UNKNOWN, even if a display label says success.
        Neither zero exit nor PASS establishes a valid source repair.
        """
        if type(status) is not str or status not in ("ok", "error", "unknown"):
            raise ValueError("Normalized status required")
        if exit_code is not None and (type(exit_code) is not int or not -255 <= exit_code <= 255):
            raise ValueError("Bounded integer command exit required")
        if (type(error_present) is not bool or type(purpose) is not str
                or purpose not in ("source", "check", "scratch", "finish")):
            raise ValueError("Typed observed outcome and purpose required")
        failed = error_present or status == "error" or (exit_code is not None and exit_code != 0)
        if failed:
            if purpose in ("check", "scratch"):
                self._check_failures = min(2, self._check_failures + 1)
                if self._check_failures == 2:
                    return Advice("REASSESS", "CHECK_RECOVERY_EXHAUSTED", "Two check attempts failed. Stop repairing the check program; reassess source or finish honestly.")
                return Advice("REVISE", "CHECK_FAILED_ONCE", "The check failed. Allow at most one short repair if time permits; verify the real source API first.")
            return Advice("REASSESS", "COMMAND_FAILED", "Actual command failure overrides any success label. Inspect source and report the limitation.")
        if exit_code is None:
            return Advice("UNKNOWN", "EXIT_UNOBSERVED", "No actual command exit was observed; do not report a successful check.")
        return Advice("PASS", "COMMAND_EXIT_ZERO", "Observed zero exit is command evidence only; source behavior still needs native verification.")
