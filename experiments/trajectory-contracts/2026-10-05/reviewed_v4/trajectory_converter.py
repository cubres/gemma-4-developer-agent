"""Original, offline transfer contracts for a single public SWE-smith trajectory.

This is data preparation, with no execution, tokenizer, model, or network code.
Source observations remain source-format evidence. They are never represented
as authentic target-harness responses. Targets are abstract assistant messages;
no token-level supervision mask or runnable native conversation is asserted.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shlex
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

MAX_MESSAGES = 128
MAX_CALLS = 64
MAX_CONTENT_CHARS = 80_000
MAX_TOTAL_CHARS = 200_000
MAX_PATH_CHARS = 512
MAX_COMMAND_CHARS = 4096


class Refusal(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def strict_json(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise Refusal("duplicate_json_key")
            result[key] = value
        return result

    def constant(_: str) -> Any:
        raise Refusal("nonfinite_json")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise Refusal("nonfinite_json")
        return number

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant,
                          parse_float=finite_float)
    except Refusal:
        raise
    except (TypeError, ValueError) as exc:
        raise Refusal("invalid_json") from exc


def digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def source_path(path: Any) -> str:
    """Map only a lexical source-root path into a relative workspace path.

    This does not certify symlink resolution or the existence/type of a file.
    Actual workspace containment remains a target-harness responsibility.
    """
    if type(path) is not str or not path or len(path) > MAX_PATH_CHARS:
        raise Refusal("invalid_path")
    if "\x00" in path or "\\" in path or any(ord(c) < 32 for c in path):
        raise Refusal("invalid_path_character")
    if ".." in path.split("/"):
        raise Refusal("path_traversal")
    if path.startswith("/testbed/"):
        relative = path[len("/testbed/"):]
    elif path.startswith("/"):
        raise Refusal("outside_source_root")
    else:
        relative = path
    if relative.startswith("/"):
        raise Refusal("absolute_target_path")
    normalized = PurePosixPath(relative).as_posix()
    if PurePosixPath(normalized).is_absolute():
        raise Refusal("absolute_target_path")
    if normalized in ("", "."):
        raise Refusal("directory_root_view_unsupported")
    if path.endswith("/"):
        raise Refusal("directory_view_unsupported")
    return normalized


def _keys(args: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if type(args) is not dict or not required <= args.keys():
        raise Refusal("missing_or_invalid_arguments")
    if args.keys() - required - optional:
        raise Refusal("unhandled_argument")


def _text(value: Any, name: str, *, nonempty: bool = False) -> str:
    if type(value) is not str or len(value) > MAX_CONTENT_CHARS:
        raise Refusal("invalid_" + name)
    if nonempty and not value:
        raise Refusal("empty_" + name)
    return value


def source_content(value: Any) -> str | list[dict[str, str]]:
    """Preserve source text blocks exactly; do not invent native observations."""
    if type(value) is str:
        return _text(value, "message_content")
    if type(value) is not list or len(value) > 16:
        raise Refusal("unsupported_source_content_shape")
    count = 0
    for block in value:
        if (type(block) is not dict or set(block) != {"type", "text"}
                or block["type"] != "text"):
            raise Refusal("unsupported_source_content_block")
        count += len(_text(block["text"], "content_block_text"))
    if count > MAX_CONTENT_CHARS:
        raise Refusal("source_content_blocks_bound")
    return copy.deepcopy(value)


def transfer_shell(command: Any) -> str:
    """Transfer an explicit root-cwd command with a single, expansion-free argv.

    No general shell substitution is attempted. Retaining an absolute source
    path, implicit cwd, operators, substitutions, globs, scripts via -c, or an
    unreviewed executable causes refusal. The target runs in its workspace root.
    """
    if type(command) is not str or not command or len(command) > MAX_COMMAND_CHARS:
        raise Refusal("invalid_shell_command")
    if any(unicodedata.category(c) == "Cc" and c != "\t" for c in command):
        raise Refusal("shell_control_character")
    match = re.fullmatch(r"cd[ \t]+/testbed[ \t]+&&[ \t]+(.+)", command)
    if match is None:
        raise Refusal("unhandled_shell_cwd_or_path")
    tail = match.group(1)
    if "/testbed" in tail or re.search(r"(?:^|[=\s])/", tail):
        raise Refusal("unhandled_shell_absolute_path")
    if any(c in tail for c in ";&|<>$`\n\r*?[]{}()#~"):
        raise Refusal("unhandled_shell_syntax")
    try:
        argv = shlex.split(tail, posix=True)
    except ValueError as exc:
        raise Refusal("invalid_shell_quoting") from exc
    if not argv or argv[0] not in {"python", "python3", "pytest", "git"}:
        raise Refusal("unhandled_shell_executable")
    if any(a.startswith("/") or re.search(r"=/", a) for a in argv):
        raise Refusal("unhandled_shell_absolute_path")
    if any("../" in a or a.endswith("..") for a in argv):
        raise Refusal("shell_path_traversal")
    if any(a.startswith("-") and not a.startswith("--") and "/" in a
           for a in argv[1:]):
        raise Refusal("unhandled_shell_short_option_path")
    if argv[0] in {"python", "python3"}:
        if len(argv) < 2 or argv[1] in {"-c", "-"}:
            raise Refusal("unhandled_shell_inline_program")
        if argv[1].startswith("-") and argv[1:3] != ["-m", "pytest"]:
            raise Refusal("unhandled_shell_python_mode")
    if argv[0] == "git" and (len(argv) < 2 or argv[1] not in {
        "status", "diff", "show", "log", "ls-files"
    }):
        raise Refusal("unhandled_shell_git_operation")
    return shlex.join(argv)


def transfer_call(name: str, args: dict[str, Any],
                  files: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    """Return native arguments only when required source-state facts are known.

    `files` is caller-supplied causal state evidence: a string is the complete
    current file, and None is proven absence. Absence from the map is UNKNOWN.
    Source tool outcomes are not used to fabricate these input preconditions.
    """
    if name == "bash":
        _keys(args, {"command"})
        return {"name": "run_command", "arguments": {
            "command": transfer_shell(args["command"])}}
    if name == "submit":
        _keys(args, set())
        return {"name": "submit_patch", "arguments": {}}
    if name != "str_replace_editor":
        raise Refusal("unhandled_source_tool")
    if type(args) is not dict or "command" not in args:
        raise Refusal("missing_or_invalid_arguments")
    operation = args["command"]
    if operation == "view":
        _keys(args, {"command", "path"}, {"view_range"})
        path = source_path(args["path"])
        target: dict[str, Any] = {"filepath": path}
        span = args.get("view_range")
        if span is not None:
            if (type(span) is not list or len(span) != 2
                    or any(type(x) is not int for x in span)
                    or not 1 <= span[0] <= 1_000_000
                    or not (span[1] == -1 or span[0] <= span[1] <= 1_000_000)):
                raise Refusal("invalid_view_range")
            target.update(start_line=span[0], end_line=None if span[1] == -1 else span[1])
        return {"name": "read_file", "arguments": target}
    if operation == "create":
        _keys(args, {"command", "path", "file_text"})
        path = source_path(args["path"])
        text = _text(args["file_text"], "file_text")
        if files is None or path not in files:
            raise Refusal("create_absence_unproven")
        if files[path] is not None:
            raise Refusal("create_would_overwrite_existing_file")
        return {"name": "write_file", "arguments": {"filepath": path, "content": text}}
    if operation == "str_replace":
        _keys(args, {"command", "path", "old_str", "new_str"})
        path = source_path(args["path"])
        old = _text(args["old_str"], "old_string", nonempty=True)
        new = _text(args["new_str"], "new_string")
        if files is None or path not in files or files[path] is None:
            raise Refusal("replacement_current_file_unproven")
        current = _text(files[path], "current_file")
        if current.count(old) != 1:
            raise Refusal("replacement_not_unique_exact_match")
        return {"name": "edit_file", "arguments": {
            "filepath": path, "old_string": old, "new_string": new,
            "allow_multiple": False}}
    raise Refusal("unhandled_editor_operation")


def _calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    values = message.get("tool_calls", [])
    if type(values) is not list or len(values) > MAX_CALLS:
        raise Refusal("invalid_call_list")
    calls = []
    for value in values:
        if (type(value) is not dict or value.get("type") != "function"
                or type(value.get("id")) is not str or not value["id"]
                or len(value["id"]) > 200 or type(value.get("function")) is not dict):
            raise Refusal("invalid_function_call")
        function = value["function"]
        if type(function.get("name")) is not str or not function["name"]:
            raise Refusal("invalid_function_name")
        arguments = function.get("arguments")
        if type(arguments) is str:
            arguments = strict_json(arguments)
        if type(arguments) is not dict:
            raise Refusal("invalid_function_arguments")
        try:
            json.dumps(arguments, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise Refusal("invalid_or_nonfinite_function_arguments") from exc
        calls.append({"id": value["id"], "name": function["name"],
                      "arguments": arguments})
    return calls


def assistant_text(message: dict[str, Any]) -> str:
    content = _text(message.get("content", ""), "assistant_content")
    thought = _text(message.get("thought", ""), "assistant_thought")
    if content and thought and content != thought:
        raise Refusal("ambiguous_distinct_thought_and_content")
    return content or thought


def validate_messages(messages: Any) -> None:
    if type(messages) is not list or not 1 <= len(messages) <= MAX_MESSAGES:
        raise Refusal("invalid_message_count")
    pending: list[str] = []
    known: set[str] = set()
    last_calls: list[dict[str, Any]] = []
    total_chars = 0
    for i, message in enumerate(messages):
        if type(message) is not dict or message.get("role") not in {
            "system", "user", "assistant", "tool"
        }:
            raise Refusal("invalid_message_role")
        source_content(message.get("content", ""))
        role = message["role"]
        if role == "tool":
            ids = message.get("tool_call_ids")
            if type(ids) is not list or len(ids) != 1 or type(ids[0]) is not str:
                raise Refusal("ambiguous_tool_response_ids")
            if not pending or ids[0] != pending[0]:
                raise Refusal("tool_response_order_or_identity")
            pending.pop(0)
        else:
            if pending:
                raise Refusal("missing_tool_response_before_next_message")
            if role == "assistant":
                assistant_text(message)
                last_calls = _calls(message)
                for call in last_calls:
                    if call["id"] in known:
                        raise Refusal("duplicate_call_id")
                    known.add(call["id"])
                    pending.append(call["id"])
                if len(known) > MAX_CALLS:
                    raise Refusal("total_call_bound")
            elif message.get("tool_calls"):
                raise Refusal("calls_on_nonassistant_message")
        if role == "system" and i != 0:
            raise Refusal("late_system_message")
        # Count the actual effective source representation once: deduplicated
        # assistant text, serialized call arguments, IDs, roles and field names.
        total_chars += len(json.dumps(_source_message(message), ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False))
        if total_chars > MAX_TOTAL_CHARS:
            raise Refusal("total_content_bound")
    if pending and not (
        messages[-1]["role"] == "assistant" and len(last_calls) == 1
        and last_calls[0]["name"] == "submit" and not last_calls[0]["arguments"]
    ):
        raise Refusal("unterminated_nonterminal_call")


def _source_message(message: dict[str, Any]) -> dict[str, Any]:
    result = {"role": message["role"], "content":
              assistant_text(message) if message["role"] == "assistant"
              else source_content(message.get("content", ""))}
    if message["role"] == "assistant":
        result["tool_calls"] = copy.deepcopy(_calls(message))
    if message["role"] == "tool":
        result["tool_call_ids"] = list(message["tool_call_ids"])
    return result


@dataclass(frozen=True)
class TransferTurn:
    assistant_index: int
    source_prefix: tuple[dict[str, Any], ...]
    target: dict[str, Any]

    def scalar(self) -> dict[str, Any]:
        return {"assistant_index": self.assistant_index,
                "prefix_message_count": len(self.source_prefix),
                "prefix_sha256": digest(self.source_prefix),
                "target_sha256": digest(self.target),
                "target_functions": [x["function"]["name"] for x in self.target["tool_calls"]]}


@dataclass(frozen=True)
class PilotResult:
    assistant_turns: int
    accepted: tuple[TransferTurn, ...]
    refused: tuple[tuple[int, str], ...]

    def scalar(self) -> dict[str, Any]:
        return {"assistant_turns": self.assistant_turns,
                "accepted_argument_contract_turns": len(self.accepted),
                "refused_turns": len(self.refused),
                "unsupported_rate": len(self.refused) / self.assistant_turns,
                "refusal_reasons": dict(Counter(reason for _, reason in self.refused)),
                "refusal_indices": [{"assistant_index": i, "reason": r} for i, r in self.refused],
                "accepted_scalars": [turn.scalar() for turn in self.accepted],
                "source_observations": "source-format only; native equivalence unverified",
                "supervision_contract": "assistant-message target only; token mask unverified",
                "source_prompt_format": "SWE-smith; not a runnable target-harness conversation",
                "training_ready": False}


def convert_messages(messages: list[dict[str, Any]],
                     facts_by_assistant_index: Mapping[int, Mapping[str, str | None]] | None = None
                     ) -> PilotResult:
    validate_messages(messages)
    accepted: list[TransferTurn] = []
    refused: list[tuple[int, str]] = []
    count = 0
    for index, message in enumerate(messages):
        if message["role"] != "assistant":
            continue
        count += 1
        try:
            calls = _calls(message)
            if not calls:
                raise Refusal("no_function_call_target")
            converted = []
            facts = (facts_by_assistant_index or {}).get(index)
            for call in calls:
                function = transfer_call(call["name"], call["arguments"], facts)
                converted.append({"id": call["id"], "type": "function", "function": function})
            target = {"role": "assistant", "content": assistant_text(message),
                      "tool_calls": converted}
            prefix = tuple(_source_message(m) for m in messages[:index])
            accepted.append(TransferTurn(index, prefix, target))
        except Refusal as exc:
            refused.append((index, exc.reason))
    if not count:
        raise Refusal("no_assistant_turns")
    return PilotResult(count, tuple(accepted), tuple(refused))
