#!/usr/bin/env python3
"""Preserved synthetic verification; imports the locator, never indexed source."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ARTIFACT = Path(__file__).absolute().parent
spec = importlib.util.spec_from_file_location("original_source_locator", ARTIFACT / "source_locator.py")
locator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = locator
spec.loader.exec_module(locator)
RUN = ARTIFACT / ("toy_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
RUN.mkdir(exist_ok=False)
TOY = RUN / "toy_repository"
CLEAN = RUN / "clean_repository"
EXTERNAL = RUN / "synthetic_external"
REPORTS = RUN / "reports"
for directory in (TOY, CLEAN, EXTERNAL, REPORTS):
    directory.mkdir(exist_ok=False)


def put(root: Path, relative: str, data: str | bytes) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(data.encode("utf-8") if isinstance(data, str) else data)


FILES = {
    "network/protocol.py": "def normalize_http_header(header):\n    return header.strip().lower()\n\ndef unrelated_geometry(radius):\n    return radius * radius\n",
    "duplicate_a.py": "def same_symbol(value):\n    return 'tie_token' + value\n",
    "duplicate_b.py": "def same_symbol(value):\n    return 'tie_token' + value\n",
    "shadowed.py": "def repeated(value):\n    return 'first_definition'\n\ndef repeated(value):\n    return 'second_definition'\n",
    "async_sample.py": "class Client:\n    @staticmethod\n    async def decodePayload(payload):\n        return payload\n\ndef outer_function():\n    def inner_function():\n        return 'nested_marker'\n    return inner_function\n",
    "long_snippet.py": "def longSnippetNeedle():\n    value = '" + "x" * 5000 + "'\n    return value\n",
    "unreadable.py": "def permission_probe():\n    return 'readable_before_fault_injection'\n",
    "execution_sentinel.py": "from pathlib import Path\nPath(" + repr(str(RUN / "INDEXED_SOURCE_EXECUTED")) + ").write_text('unexpected execution')\n",
    "blank.py": "\n",
}
for relative, content in FILES.items():
    put(TOY, relative, content)
    put(CLEAN, relative, content)
put(TOY, "broken.py", "def invalid_python(:\n    pass\n")
put(TOY, "invalid_utf8.py", b"# invalid source byte\n\xff\n")
put(TOY, ".git/ignored.py", "def ignored_secret():\n    return 'excluded_git_marker'\n")
put(TOY, "unindexed.txt", b"\xff this non-Python file is never parsed")
put(EXTERNAL, "outside.py", "def outside_secret():\n    return 'outside_marker'\n")
os.symlink(EXTERNAL / "outside.py", TOY / "outside_alias.py")
os.symlink(EXTERNAL, TOY / "outside_directory")
os.symlink(CLEAN, RUN / "root_alias")
os.symlink(REPORTS, RUN / "report_parent_alias")


def snapshot(root: Path) -> dict:
    result = {}
    for current, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(current) / name
            metadata = path.lstat()
            record = {"mode": stat.S_IMODE(metadata.st_mode), "size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns, "ctime_ns": metadata.st_ctime_ns}
            if stat.S_ISLNK(metadata.st_mode):
                record["symlink_target"] = os.readlink(path)
            elif stat.S_ISREG(metadata.st_mode):
                record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            result[str(path.relative_to(root))] = record
    return result


BEFORE = {name: snapshot(root) for name, root in (("toy", TOY), ("clean", CLEAN), ("external", EXTERNAL))}


class Verification(unittest.TestCase):
    def test_relevant_function_and_hash(self):
        result = locator.SourceIndex(CLEAN).search("normalize HTTP header", 5)
        winner = result["matches"][0]
        self.assertEqual((winner["path"], winner["kind"], winner["qualified_name"]), ("network/protocol.py", "function", "normalize_http_header"))
        expected = hashlib.sha256(FILES["network/protocol.py"].encode()).hexdigest()
        self.assertEqual(winner["source_sha256"], expected)
        self.assertEqual(result["status"], "OK")

    def test_distinct_files_and_exact_tie_order(self):
        result = locator.SourceIndex(CLEAN).search("tie token", 20)
        copies = [match for match in result["matches"] if match["qualified_name"] == "same_symbol"]
        self.assertEqual([match["path"] for match in copies], ["duplicate_a.py", "duplicate_b.py"])
        self.assertEqual(copies[0]["score"], copies[1]["score"])

    def test_duplicate_declaration_spans_are_preserved(self):
        units = [unit for unit in locator.SourceIndex(CLEAN).units if unit.path == "shadowed.py" and unit.qualified_name == "repeated"]
        self.assertEqual([(unit.start_line, unit.end_line) for unit in units], [(1, 2), (4, 5)])

    def test_async_decorators_and_nested_names(self):
        units = locator.SourceIndex(CLEAN).units
        asynchronous = next(unit for unit in units if unit.qualified_name == "Client.decodePayload")
        self.assertEqual((asynchronous.kind, asynchronous.start_line, asynchronous.end_line), ("async_function", 2, 4))
        self.assertTrue(any(unit.qualified_name == "outer_function.inner_function" for unit in units))

    def test_repeated_index_and_query_are_deterministic(self):
        left = locator.SourceIndex(TOY).search("tie token", 20)
        right = locator.SourceIndex(TOY).search("tie token", 20)
        self.assertEqual(locator.canonical_json(left), locator.canonical_json(right))

    def test_parse_and_decode_failure_coverage(self):
        result = locator.SourceIndex(TOY).search("normalize HTTP header")
        records = {record["path"]: record for record in result["coverage"]["files"]}
        self.assertEqual(records["broken.py"]["status"], "parse_error")
        self.assertEqual(records["invalid_utf8.py"]["status"], "decode_error")
        self.assertIsNotNone(records["broken.py"]["sha256"])
        self.assertIsNotNone(records["invalid_utf8.py"]["sha256"])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(records["broken.py"]["units"], 0)

    def test_permission_error_is_explicit(self):
        original_open = locator.os.open
        def denied(path, *arguments, **keywords):
            if path == "unreadable.py" and "dir_fd" in keywords:
                raise PermissionError(errno.EACCES, "Synthetic read denial")
            return original_open(path, *arguments, **keywords)
        with patch.object(locator.os, "open", denied):
            result = locator.SourceIndex(CLEAN).search("permission probe")
        record = next(item for item in result["coverage"]["files"] if item["path"] == "unreadable.py")
        self.assertEqual((record["status"], record["errno"], record["sha256"]), ("read_error", errno.EACCES, None))
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_unreadable_mode_gate_without_changing_inputs(self):
        original_stat = locator.os.stat
        def mode_denied(path, *arguments, **keywords):
            result = original_stat(path, *arguments, **keywords)
            if path == "unreadable.py" and "dir_fd" in keywords:
                return SimpleNamespace(st_mode=result.st_mode & ~0o444, st_size=result.st_size)
            return result
        with patch.object(locator.os, "stat", mode_denied):
            result = locator.SourceIndex(CLEAN).search("permission probe")
        record = next(item for item in result["coverage"]["files"] if item["path"] == "unreadable.py")
        self.assertEqual(record["status"], "unreadable_mode_bits")
        self.assertIsNone(record["sha256"])

    def test_symlinks_and_ignored_directories_are_not_indexed(self):
        result = locator.SourceIndex(TOY).search("outside secret excluded git", 20)
        paths = {record["path"] for record in result["coverage"]["files"]}
        self.assertNotIn("outside_alias.py", paths)
        self.assertNotIn("outside_directory/outside.py", paths)
        self.assertNotIn(".git/ignored.py", paths)
        self.assertEqual(result["matches"], [])
        events = {(event["path"], event["status"]) for event in result["coverage"]["directory_events"]}
        self.assertIn(("outside_alias.py", "excluded_symlink"), events)
        self.assertIn((".git", "excluded_directory"), events)

    def test_symlink_root_and_relative_root_are_refused(self):
        with self.assertRaises(OSError):
            locator.SourceIndex(RUN / "root_alias")
        with self.assertRaises(ValueError):
            locator.SourceIndex("relative/source")

    def test_caps_are_visible_and_never_claim_complete(self):
        examples = [
            (replace(locator.Limits(), max_files=1), "max_files"),
            (replace(locator.Limits(), max_total_bytes=1), "max_total_bytes"),
            (replace(locator.Limits(), max_units=1), "max_units"),
        ]
        for limits, reason in examples:
            with self.subTest(reason=reason):
                result = locator.SourceIndex(CLEAN, limits).search("header")
                self.assertEqual(result["status"], "INCOMPLETE")
                self.assertIn(reason, result["coverage"]["scan_stopped_reason"])
        result = locator.SourceIndex(CLEAN, replace(locator.Limits(), max_file_bytes=64)).search("header")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertGreater(result["coverage"]["statuses"].get("max_file_bytes", 0), 0)

    def test_query_bounds_and_bounded_snippets(self):
        index = locator.SourceIndex(CLEAN)
        result = index.search("snippet needle", 20)
        match = next(item for item in result["matches"] if item["qualified_name"] == "longSnippetNeedle")
        self.assertLessEqual(len(match["snippet"]["text"]), 1200)
        self.assertLessEqual(match["snippet"]["end_line"] - match["snippet"]["start_line"] + 1, 20)
        self.assertTrue(match["snippet"]["truncated"])
        with self.assertRaises(ValueError):
            index.search("x" * 4097)
        with self.assertRaises(ValueError):
            index.search("header", 21)
        with self.assertRaises(ValueError):
            index.search("!!!")

    def test_exclusive_report_and_repo_write_refusal(self):
        result = locator.SourceIndex(CLEAN).search("header")
        destination = REPORTS / "first_report.json"
        locator.write_exclusive_report(str(destination), result, CLEAN)
        original = destination.read_bytes()
        self.assertEqual(json.loads(original), result)
        with self.assertRaises(FileExistsError):
            locator.write_exclusive_report(str(destination), result, CLEAN)
        self.assertEqual(destination.read_bytes(), original)
        with self.assertRaises(ValueError):
            locator.write_exclusive_report(str(CLEAN / "forbidden_report.json"), result, CLEAN)
        with self.assertRaises(OSError):
            locator.write_exclusive_report(str(RUN / "report_parent_alias" / "forbidden.json"), result, CLEAN)
        self.assertFalse((CLEAN / "forbidden_report.json").exists())
        self.assertFalse((REPORTS / "forbidden.json").exists())

    def test_cli_json_and_no_indexed_source_execution(self):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run([sys.executable, str(ARTIFACT / "source_locator.py"), "--repo-root", str(TOY), "--query", "normalize HTTP header"], capture_output=True, text=True, env=environment, timeout=20)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["status"], "INCOMPLETE")
        self.assertEqual(process.stderr, "")
        self.assertFalse((RUN / "INDEXED_SOURCE_EXECUTED").exists())
        clean = subprocess.run([sys.executable, str(ARTIFACT / "source_locator.py"), "--repo-root", str(CLEAN), "--query", "normalize HTTP header"], capture_output=True, text=True, env=environment, timeout=20)
        self.assertEqual(clean.returncode, 0)
        self.assertEqual(json.loads(clean.stdout)["status"], "OK")
        self.assertFalse((RUN / "INDEXED_SOURCE_EXECUTED").exists())


    def test_double_leading_root_and_report_aliases_are_refused(self):
        result = locator.SourceIndex(CLEAN).search("header")
        aliases = ["//" + str(CLEAN).lstrip("/"), "///" + str(CLEAN).lstrip("/")]
        for alias in aliases:
            with self.subTest(alias=alias):
                with self.assertRaises(ValueError):
                    locator.SourceIndex(alias)
                with self.assertRaises(ValueError):
                    locator.write_exclusive_report(str(CLEAN / "alias_report.json"), result, Path(alias))
        for prefix in ("//", "///"):
            with self.assertRaises(ValueError):
                locator.write_exclusive_report(prefix + str(REPORTS / "alias_report.json").lstrip("/"), result, CLEAN)
        self.assertFalse((CLEAN / "alias_report.json").exists())
        self.assertFalse((REPORTS / "alias_report.json").exists())

    def test_non_python_entries_consume_the_global_entry_cap(self):
        root = RUN / "entry_cap_fixture"
        root.mkdir()
        for i in range(20):
            put(root, "data_" + str(i) + ".txt", "constructed nonsource data")
        before = snapshot(root)
        result = locator.SourceIndex(root, replace(locator.Limits(), max_entries=5)).search("header")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["directory_entries_seen"], 5)
        self.assertIn("max_entries", result["coverage"]["scan_stopped_reason"])
        self.assertEqual(result["coverage"]["source_files_seen"], 0)
        self.assertEqual(before, snapshot(root))

    def test_empty_directories_consume_visited_directory_cap(self):
        root = RUN / "directory_cap_fixture"
        root.mkdir()
        for i in range(4):
            (root / ("empty_" + str(i))).mkdir()
        before = snapshot(root)
        result = locator.SourceIndex(root, replace(locator.Limits(), max_directories=2)).search("header")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["directories_visited"], 2)
        self.assertIn("max_directories", result["coverage"]["scan_stopped_reason"])
        self.assertEqual(before, snapshot(root))

    def test_directory_depth_cap_is_explicit(self):
        root = RUN / "depth_cap_fixture"
        (root / "a" / "b" / "c").mkdir(parents=True)
        before = snapshot(root)
        result = locator.SourceIndex(root, replace(locator.Limits(), max_depth=1)).search("header")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["deepest_directory_depth"], 1)
        self.assertIn("max_depth", result["coverage"]["scan_stopped_reason"])
        self.assertEqual(before, snapshot(root))

    def test_scandir_replaces_unbounded_listdir(self):
        with patch.object(locator.os, "listdir", side_effect=AssertionError("unbounded listdir used")):
            result = locator.SourceIndex(CLEAN).search("header")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["coverage"]["directories_visited"], 2)
        self.assertEqual(result["coverage"]["directory_entries_seen"], 10)

    def test_cli_global_entry_cap_is_incomplete(self):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run([sys.executable, str(ARTIFACT / "source_locator.py"), "--repo-root", str(CLEAN), "--query", "header", "--max-entries", "1"], capture_output=True, text=True, env=environment, timeout=20)
        result = json.loads(process.stdout)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["directory_entries_seen"], 1)
        self.assertIn("max_entries", result["coverage"]["scan_stopped_reason"])

    def test_new_resource_limits_validate(self):
        for name in ("max_entries", "max_directories", "max_depth"):
            for bad in (0, -1, True):
                with self.subTest(name=name, bad=bad):
                    with self.assertRaises(ValueError):
                        locator.SourceIndex(CLEAN, replace(locator.Limits(), **{name: bad}))

    def test_exact_entry_cap_is_conservatively_incomplete(self):
        root = RUN / "exact_entry_cap_fixture"
        root.mkdir()
        put(root, "ordinary.py", "def header(value):\n    return value\n")
        before = snapshot(root)
        result = locator.SourceIndex(root, replace(locator.Limits(), max_entries=1)).search("header")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["directory_entries_seen"], 1)
        self.assertEqual(before, snapshot(root))


    def test_physical_parent_alias_is_refused_by_descriptor_identity(self):
        result = locator.SourceIndex(CLEAN).search("header")
        root_id = (CLEAN.stat().st_dev, CLEAN.stat().st_ino)
        original_dup = locator.os.dup
        original_fstat = locator.os.fstat
        mapped = set()
        def duplicate(fd):
            value = original_dup(fd)
            mapped.add(value)
            return value
        def aliased_stat(fd):
            if fd in mapped:
                return SimpleNamespace(st_dev=root_id[0], st_ino=root_id[1])
            return original_fstat(fd)
        destination = REPORTS / "physical_parent_alias.json"
        with patch.object(locator.os, "dup", duplicate), patch.object(locator.os, "fstat", aliased_stat):
            with self.assertRaisesRegex(ValueError, "inside indexed root"):
                locator.write_exclusive_report(str(destination), result, CLEAN)
        self.assertFalse(destination.exists())

    def test_physical_ancestor_alias_is_refused_by_descriptor_identity(self):
        result = locator.SourceIndex(CLEAN).search("header")
        root_id = (CLEAN.stat().st_dev, CLEAN.stat().st_ino)
        original_dup = locator.os.dup
        original_open = locator.os.open
        original_fstat = locator.os.fstat
        mapped = {}
        def duplicate(fd):
            value = original_dup(fd)
            mapped[value] = (root_id[0], root_id[1] + 10000000)
            return value
        def open_ancestor(path, *args, **kwargs):
            value = original_open(path, *args, **kwargs)
            if path == ".." and kwargs.get("dir_fd") in mapped:
                mapped[value] = root_id
            return value
        def aliased_stat(fd):
            if fd in mapped:
                return SimpleNamespace(st_dev=mapped[fd][0], st_ino=mapped[fd][1])
            return original_fstat(fd)
        destination = REPORTS / "physical_ancestor_alias.json"
        with patch.object(locator.os, "dup", duplicate), patch.object(locator.os, "open", open_ancestor), patch.object(locator.os, "fstat", aliased_stat):
            with self.assertRaisesRegex(ValueError, "ancestor is indexed root"):
                locator.write_exclusive_report(str(destination), result, CLEAN)
        self.assertFalse(destination.exists())

    def test_report_ancestry_must_reach_root_within_bound(self):
        root_id = (CLEAN.stat().st_dev, CLEAN.stat().st_ino)
        parent_fd = locator.directory_fd_without_symlinks(REPORTS)
        try:
            with self.assertRaisesRegex(ValueError, "bounded validation depth"):
                locator._reject_indexed_root_ancestry(parent_fd, root_id, max_ancestors=1)
            self.assertEqual(locator.os.fstat(parent_fd).st_ino, REPORTS.stat().st_ino)
        finally:
            locator.os.close(parent_fd)

    def test_report_ancestry_read_error_is_refused(self):
        result = locator.SourceIndex(CLEAN).search("header")
        original_open = locator.os.open
        def denied_ancestor(path, *args, **kwargs):
            if path == ".." and "dir_fd" in kwargs:
                raise PermissionError(errno.EACCES, "Constructed ancestor read denial")
            return original_open(path, *args, **kwargs)
        destination = REPORTS / "ancestry_denied.json"
        with patch.object(locator.os, "open", denied_ancestor):
            with self.assertRaises(PermissionError):
                locator.write_exclusive_report(str(destination), result, CLEAN)
        self.assertFalse(destination.exists())

    def test_captured_root_identity_drift_refuses_report(self):
        index = locator.SourceIndex(CLEAN)
        result = index.search("header")
        wrong = (index.root_identity[0], index.root_identity[1] + 1)
        for stage, values in (("initial", [wrong]), ("before_create", [index.root_identity, wrong])):
            destination = REPORTS / ("drift_" + stage + ".json")
            with patch.object(locator, "_directory_identity_without_symlinks", side_effect=values):
                with self.assertRaisesRegex(ValueError, "identity changed"):
                    locator.write_exclusive_report(str(destination), result, CLEAN, index.root_identity)
            self.assertFalse(destination.exists())

    def test_report_requires_captured_index_root_identity(self):
        destination = REPORTS / "missing_capture.json"
        with self.assertRaisesRegex(ValueError, "requires captured"):
            locator.write_exclusive_report(str(destination), {"matches": []}, CLEAN)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    capture = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Verification)
    outcome = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
    after = {name: snapshot(root) for name, root in (("toy", TOY), ("clean", CLEAN), ("external", EXTERNAL))}
    preserved = BEFORE == after
    receipt = {"status": "PASS" if outcome.wasSuccessful() and preserved else "FAIL", "tests_run": outcome.testsRun, "failures": len(outcome.failures), "errors": len(outcome.errors), "input_bytes_modes_and_tree_preserved": preserved, "indexed_source_execution_marker_absent": not (RUN / "INDEXED_SOURCE_EXECUTED").exists(), "unreadability_verification": "EACCES and zero read mode bits were fault-injected; source permissions and bytes stayed unchanged", "fixture_directory": str(RUN), "input_manifest_before_sha256": locator.digest(locator.canonical_json(BEFORE)), "input_manifest_after_sha256": locator.digest(locator.canonical_json(after)), "fixture_inputs": BEFORE, "test_output": capture.getvalue()}
    with (RUN / "verification_receipt.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with (RUN / "example_retrieval.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(locator.SourceIndex(CLEAN).search("normalize HTTP header"), indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: receipt[key] for key in ("status", "tests_run", "failures", "errors", "input_bytes_modes_and_tree_preserved", "indexed_source_execution_marker_absent", "fixture_directory")}))
    if not outcome.wasSuccessful():
        print(capture.getvalue())
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)
