"""CPU-only synthetic semantic checks plus one frozen public-row contract.

No shell command, source tool, tokenizer, model, engine, or network is executed.
"""

import copy
import hashlib
import json
import shlex
import unittest
from pathlib import Path

from trajectory_converter import (
    MAX_MESSAGES, Refusal, assistant_text, convert_messages, digest,
    source_content, source_path, strict_json, transfer_call, transfer_shell, validate_messages,
)


def assistant(call_id, name, args, text="one thought"):
    return {"role": "assistant", "content": text, "thought": text,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def observation(call_id, text="SOURCE observation"):
    return {"role": "tool", "content": text, "tool_call_ids": [call_id]}


def sequence():
    return [{"role": "system", "content": "source tool contract"},
            {"role": "user", "content": "repair a novel synthetic function"},
            assistant("c1", "str_replace_editor", {"command": "view", "path": "/testbed/pkg/a.py"}),
            observation("c1"), assistant("c2", "submit", {})]


class SemanticContracts(unittest.TestCase):
    def refuses(self, reason, function, *args):
        with self.assertRaises(Refusal) as error:
            function(*args)
        self.assertEqual(error.exception.reason, reason)

    def test_relative_and_absolute_source_paths(self):
        self.assertEqual(source_path("/testbed/pkg/./a.py"), "pkg/a.py")
        self.assertEqual(source_path("pkg//a.py"), "pkg/a.py")
        self.assertEqual(source_path("pkg/α.py"), "pkg/α.py")

    def test_double_separator_cannot_create_absolute_target(self):
        for path in ("/testbed//etc/passwd", "/testbed///a.py", "/testbed//"):
            with self.subTest(path=path):
                self.refuses("absolute_target_path", source_path, path)

    def test_traversal_and_absolute_root_boundaries(self):
        for path in ("/testbed/../a.py", "pkg/../a.py", "../a.py"):
            with self.subTest(path=path):
                self.refuses("path_traversal", source_path, path)
        for path in ("/testbed2/a.py", "/etc/a.py", "//testbed/a.py"):
            with self.subTest(path=path):
                self.refuses("outside_source_root", source_path, path)

    def test_directory_and_control_character_refusal(self):
        self.refuses("outside_source_root", source_path, "/testbed")
        self.refuses("directory_root_view_unsupported", source_path, ".")
        self.refuses("directory_view_unsupported", source_path, "/testbed/pkg/")
        for path in ("pkg\\a.py", "pkg/\x00a.py", "pkg/\na.py"):
            with self.subTest(path=path):
                self.refuses("invalid_path_character", source_path, path)

    def test_inclusive_view_and_end_of_file_mapping(self):
        def view(span):
            return transfer_call("str_replace_editor", {"command": "view", "path": "/testbed/a.py", "view_range": span})
        self.assertEqual(view([3, 7]), {"name": "read_file", "arguments": {
            "filepath": "a.py", "start_line": 3, "end_line": 7}})
        self.assertEqual(view([3, -1])["arguments"]["end_line"], None)
        self.assertEqual(transfer_call("str_replace_editor", {"command": "view", "path": "a.py"})["arguments"], {"filepath": "a.py"})

    def test_view_range_bool_and_invalid_bounds(self):
        for span in ([True, 3], [0, 3], [3, 2], [3], [3, -2], [1, 1_000_001]):
            with self.subTest(span=span):
                self.refuses("invalid_view_range", transfer_call, "str_replace_editor", {
                    "command": "view", "path": "a.py", "view_range": span})

    def test_create_exact_bytes_only_with_known_absence(self):
        text = "α = 'β'\n\n"
        native = transfer_call("str_replace_editor", {"command": "create", "path": "/testbed/pkg/a.py", "file_text": text}, {"pkg/a.py": None})
        source_state = {}; target_state = {}
        source_state["pkg/a.py"] = text
        target_state[native["arguments"]["filepath"]] = native["arguments"]["content"]
        self.assertEqual(source_state, target_state)
        self.assertEqual(native["name"], "write_file")
        self.assertEqual(native["arguments"]["content"].encode(), text.encode())

    def test_create_unknown_and_existing_are_distinct(self):
        args = {"command": "create", "path": "a.py", "file_text": "x"}
        self.refuses("create_absence_unproven", transfer_call, "str_replace_editor", args)
        self.refuses("create_absence_unproven", transfer_call, "str_replace_editor", args, {})
        self.refuses("create_would_overwrite_existing_file", transfer_call, "str_replace_editor", args, {"a.py": ""})

    def test_replacement_unique_exact_semantics(self):
        current = "head\nα = 1\ntail\n"
        args = {"command": "str_replace", "path": "/testbed/a.py", "old_str": "α = 1", "new_str": "α = 2"}
        native = transfer_call("str_replace_editor", args, {"a.py": current})
        target = native["arguments"]
        self.assertEqual(current.replace(args["old_str"], args["new_str"]),
                         current.replace(target["old_string"], target["new_string"]))
        self.assertIs(target["allow_multiple"], False)
        args["new_str"] = ""
        self.assertEqual(transfer_call("str_replace_editor", args, {"a.py": current})["arguments"]["new_string"], "")

    def test_replacement_never_uses_fuzzy_or_unknown_match(self):
        args = {"command": "str_replace", "path": "a.py", "old_str": "x = 1", "new_str": "x = 2"}
        self.refuses("replacement_current_file_unproven", transfer_call, "str_replace_editor", args)
        self.refuses("replacement_current_file_unproven", transfer_call, "str_replace_editor", args, {"a.py": None})
        for current in ("x=1", "x = 1\nx = 1"):
            with self.subTest(current=current):
                self.refuses("replacement_not_unique_exact_match", transfer_call, "str_replace_editor", args, {"a.py": current})
        args["old_str"] = ""
        self.refuses("empty_old_string", transfer_call, "str_replace_editor", args, {"a.py": ""})

    def test_unhandled_editor_and_extra_argument_refusals(self):
        for command in ("insert", "undo_edit", "other"):
            with self.subTest(command=command):
                self.refuses("unhandled_editor_operation", transfer_call, "str_replace_editor", {"command": command})
        self.refuses("unhandled_argument", transfer_call, "str_replace_editor", {"command": "view", "path": "a.py", "unexpected": 1})

    def test_shell_explicit_cwd_and_argv_preservation(self):
        tail = "python 'pkg/a b.py' '--option=x y'"
        converted = transfer_shell("cd /testbed && " + tail)
        self.assertEqual(shlex.split(converted), shlex.split(tail))
        self.assertEqual(transfer_shell("cd /testbed && python -m pytest -q"), "python -m pytest -q")
        self.assertEqual(transfer_shell("cd /testbed && git diff --stat"), "git diff --stat")

    def test_shell_refuses_unhandled_cwd_and_paths(self):
        for command in ("pytest -q", "cd '/testbed' && pytest -q", "cat /testbed/a.py", "cd /testbed/sub && pytest"):
            with self.subTest(command=command):
                self.refuses("unhandled_shell_cwd_or_path", transfer_shell, command)
        for tail in ("python /testbed/a.py", "pytest --path=/etc/a", "pytest /etc/a"):
            with self.subTest(tail=tail):
                self.refuses("unhandled_shell_absolute_path", transfer_shell, "cd /testbed && " + tail)

    def test_shell_refuses_operators_expansion_and_inline_programs(self):
        for tail in ("pytest | head", "pytest; echo x", "pytest > out", "pytest $FLAGS", "pytest `echo x`", "pytest *.py", "pytest # note"):
            with self.subTest(tail=tail):
                self.refuses("unhandled_shell_syntax", transfer_shell, "cd /testbed && " + tail)
        self.refuses("unhandled_shell_inline_program", transfer_shell, "cd /testbed && python -c 'print 1'")
        self.refuses("shell_path_traversal", transfer_shell, "cd /testbed && pytest ../a.py")
        self.refuses("unhandled_shell_executable", transfer_shell, "cd /testbed && unknown a.py")

    def test_shell_tilde_and_control_characters(self):
        self.refuses("unhandled_shell_syntax", transfer_shell, "cd /testbed && python ~/check.py")
        for value in ("\x00", "\x7f", "\x85", "\n", "\r"):
            with self.subTest(value=value):
                self.refuses("shell_control_character", transfer_shell, "cd /testbed && python a" + value + ".py")

    def test_embedded_option_and_revision_traversal(self):
        for tail in ("pytest --basetemp=../outside", "git show HEAD:../file", "python -o../outside", "pytest sub/.."):
            with self.subTest(tail=tail):
                self.refuses("shell_path_traversal", transfer_shell, "cd /testbed && " + tail)

    def test_shell_short_options_cannot_hide_paths(self):
        for tail in ("python script.py -o/etc/report",
                     "pytest -c/etc/pytest.ini",
                     "git diff -O/etc/order",
                     "python script.py -orelative/path"):
            with self.subTest(tail=tail):
                command = "cd /testbed && " + tail
                self.refuses("unhandled_shell_short_option_path", transfer_shell, command)
                self.refuses("unhandled_shell_short_option_path", transfer_call,
                             "bash", {"command": command})

    def test_strict_argument_json(self):
        self.refuses("duplicate_json_key", strict_json, '{"command":"a","command":"b"}')
        self.refuses("nonfinite_json", strict_json, '{"x":NaN}')
        self.refuses("invalid_json", strict_json, "{broken}")

    def test_exponent_overflow_and_supplied_nonfinite_arguments(self):
        self.refuses("nonfinite_json", strict_json, '{"value":1e400}')
        self.refuses("nonfinite_json", strict_json, '{"value":-1e400}')
        self.assertEqual(strict_json('{"value":1e-400}'), {"value": 0.0})
        ms = sequence(); ms[2]["tool_calls"][0]["function"]["arguments"] = {"extra": float("inf")}
        self.refuses("invalid_or_nonfinite_function_arguments", validate_messages, ms)

    def test_response_identity_and_fifo_order(self):
        ms = sequence()
        second = assistant("c3", "bash", {"command": "cd /testbed && pytest -q"})["tool_calls"][0]
        ms[2]["tool_calls"].append(second)
        ms.insert(4, observation("c3"))
        validate_messages(ms)
        bad = copy.deepcopy(ms)
        bad[3], bad[4] = bad[4], bad[3]
        self.refuses("tool_response_order_or_identity", validate_messages, bad)
        bad = sequence(); bad[3]["tool_call_ids"] = ["unknown"]
        self.refuses("tool_response_order_or_identity", validate_messages, bad)

    def test_missing_reply_and_terminal_submit_boundary(self):
        validate_messages(sequence())
        self.refuses("missing_tool_response_before_next_message", validate_messages, sequence()[:3] + sequence()[4:])
        self.refuses("unterminated_nonterminal_call", validate_messages, sequence()[:3])
        bad = sequence(); bad[-1]["tool_calls"][0]["function"]["arguments"] = '{"x":1}'
        self.refuses("unterminated_nonterminal_call", validate_messages, bad)

    def test_duplicate_call_and_ambiguous_reply_ids(self):
        bad = sequence(); bad[-1]["tool_calls"][0]["id"] = "c1"
        self.refuses("duplicate_call_id", validate_messages, bad)
        bad = sequence(); bad[3]["tool_call_ids"] = ["c1", "c2"]
        self.refuses("ambiguous_tool_response_ids", validate_messages, bad)

    def test_thought_content_once_and_ambiguous_text(self):
        ms = sequence(); result = convert_messages(ms)
        self.assertEqual(result.accepted[0].target["content"], "one thought")
        self.assertNotIn("thought", result.accepted[0].target)
        self.assertNotIn("thought", result.accepted[1].source_prefix[2])
        self.assertEqual(assistant_text({"content": "", "thought": "one thought"}), "one thought")
        self.refuses("ambiguous_distinct_thought_and_content", assistant_text, {"content": "answer", "thought": "other reasoning"})

    def test_causal_prefix_no_target_or_future_observation(self):
        ms = sequence(); before = convert_messages(ms)
        earlier = before.accepted[0]
        self.assertEqual(len(earlier.source_prefix), 2)
        self.assertFalse(any(m["role"] == "assistant" for m in earlier.source_prefix))
        altered = copy.deepcopy(ms); altered[3]["content"] = "future observation with a different outcome"
        after = convert_messages(altered)
        self.assertEqual(earlier.scalar(), after.accepted[0].scalar())
        self.assertNotEqual(before.accepted[1].scalar()["prefix_sha256"], after.accepted[1].scalar()["prefix_sha256"])
        ms[0]["content"] = "mutated caller state"
        self.assertEqual(earlier.source_prefix[0]["content"], "source tool contract")

    def test_source_text_blocks_preserved_without_native_claim(self):
        ms = sequence()
        ms[1]["content"] = [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]
        ms[3]["content"] = [{"type": "text", "text": "original source observation"}]
        result = convert_messages(ms)
        self.assertEqual(result.accepted[0].source_prefix[1]["content"], ms[1]["content"])
        self.assertEqual(result.accepted[1].source_prefix[3]["content"], ms[3]["content"])
        ms[1]["content"][0]["text"] = "mutated input"
        ms[3]["content"][0]["text"] = "changed later observation"
        self.assertEqual(result.accepted[0].source_prefix[1]["content"][0]["text"], "first")
        self.assertEqual(result.accepted[1].source_prefix[3]["content"][0]["text"], "original source observation")
        self.assertFalse(result.scalar()["training_ready"])

    def test_unknown_and_malformed_source_blocks_refused(self):
        for value in ([{"type": "image", "text": "x"}], [{"type": "text", "text": "x", "extra": 1}], ["x"], None):
            with self.subTest(value=value):
                reason = "unsupported_source_content_shape" if value is None else "unsupported_source_content_block"
                self.refuses(reason, source_content, value)
        self.refuses("invalid_content_block_text", source_content, [{"type": "text", "text": 1}])

    def test_source_block_bound_is_combined(self):
        self.refuses("source_content_blocks_bound", source_content,
                     [{"type": "text", "text": "x" * 50_000}, {"type": "text", "text": "y" * 50_000}])

    def test_refused_targets_do_not_gain_future_state_facts(self):
        ms = sequence(); ms[2] = assistant("c1", "str_replace_editor", {"command": "create", "path": "a.py", "file_text": "x"})
        ms[3]["content"] = "source says creation succeeded"
        result = convert_messages(ms)
        self.assertEqual(result.refused, ((2, "create_absence_unproven"),))
        result = convert_messages(ms, {2: {"a.py": None}})
        self.assertEqual(len(result.accepted), 2)
        self.assertFalse(result.scalar()["training_ready"])
        self.assertIn("unverified", result.scalar()["supervision_contract"])

    def test_resource_limits_and_nonassistant_calls(self):
        self.refuses("invalid_message_count", validate_messages, [{"role": "user", "content": ""}] * (MAX_MESSAGES + 1))
        ms = sequence(); ms[0]["content"] = "x" * 80_001
        self.refuses("invalid_message_content", validate_messages, ms)
        ms = sequence(); ms[1]["tool_calls"] = [{}]
        self.refuses("calls_on_nonassistant_message", validate_messages, ms)

    def test_bound_includes_thought_only_and_serialized_arguments(self):
        for field in ("thought", "arguments"):
            ms = [{"role": "system", "content": "source"}, {"role": "user", "content": "task"}]
            for i in range(4):
                a = assistant(str(i), "submit", {})
                if field == "thought":
                    a.update(content="", thought="x" * 60_000)
                else:
                    a["tool_calls"][0]["function"]["arguments"] = json.dumps({"text": "x" * 60_000})
                ms.extend([a, observation(str(i))])
            with self.subTest(field=field):
                self.refuses("total_content_bound", validate_messages, ms)


@unittest.skipUnless(
    all((Path(__file__).resolve().parent.parent / name).is_file()
        for name in ("frozen_source_response.json", "source_provenance.json",
                     "upstream_MIT_NOTICE.txt")),
    "The frozen trajectory contents are retained privately; only the synthetic suite runs publicly.")
class FrozenPublicRowContract(unittest.TestCase):
    def test_exact_ap_ispec_row_argument_contract_and_private_provenance(self):
        root = Path(__file__).resolve().parent.parent
        raw = (root / "frozen_source_response.json").read_bytes()
        self.assertLess(len(raw), 160_000)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "d3339ebf2ec2a909ede1e731c25615ebca3eb408f1853e507f843eec6d1b6b1c")
        provenance = strict_json((root / "source_provenance.json").read_text())
        self.assertEqual(provenance["revision"], "08e109b4a59eaeebf80e4675cd125d42e7ac99a4")
        self.assertIs(provenance["source_contents_private"], True)
        row_record = strict_json(raw.decode())["rows"][0]
        self.assertEqual(row_record["row_idx"], 1)
        self.assertEqual(row_record["truncated_cells"], [])
        row = row_record["row"]
        self.assertEqual(row["instance_id"], "marshmallow-code__apispec.8b421526.func_pm_remove_assign__kdkrbg6a")
        self.assertEqual(row["model"], "claude-3-7-sonnet-20250219")
        self.assertIs(row["resolved"], True)
        self.assertEqual(len(row["patch"].encode()), 1925)
        result = convert_messages(strict_json(row["messages"]))
        self.assertEqual(result.assistant_turns, 21)
        self.assertEqual(len(result.accepted) + len(result.refused), 21)
        self.assertTrue(any(t.target["tool_calls"][0]["function"]["name"] == "run_command" for t in result.accepted))
        self.assertTrue(any(reason == "create_absence_unproven" for _, reason in result.refused))
        self.assertIs(result.scalar()["training_ready"], False)
        self.assertNotIn(row["patch"], json.dumps(result.scalar()))
        self.assertEqual(hashlib.sha256((root / "upstream_MIT_NOTICE.txt").read_bytes()).hexdigest(), "f345555ff39d6b573342781a6346a5202a8f14bce424fee41f910c6c5379cc7d")


if __name__ == "__main__":
    unittest.main()
