# SPDX-License-Identifier: MIT
# MIT License
#
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
"""Synthetic CLI and ADK-argv mechanics; no official agent or model execution."""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import locator_skill


class SkillTests(unittest.TestCase):
    def invoke(self, arguments, *, core=None):
        if core is None:
            core = SimpleNamespace(locate=lambda root, query, **limits: {
                "status": "OK", "locations": [], "edges": []})
        output, errors = io.StringIO(), io.StringIO()
        with patch("locator_skill._load_core", return_value=core), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            exit_code = locator_skill.main(arguments)
        text = output.getvalue()
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(len(text.splitlines()), 1)
        self.assertLessEqual(len(text.encode("utf-8")), 4500)
        return exit_code, json.loads(text)

    def test_fixed_root_and_scalar_bounds(self):
        captured = {}
        def locate(root, query, **limits):
            captured.update(root=root, query=query, **limits)
            return {"status": "OK", "locations": [], "edges": []}
        code, result = self.invoke(["--query", "two words", "--max-files", "8", "--seconds", "0.5"],
                                   core=SimpleNamespace(locate=locate))
        self.assertEqual(code, 0)
        self.assertEqual(captured["root"], "/workspace")
        self.assertEqual(captured["query"], "two words")
        self.assertEqual(captured["max_files"], 8)
        self.assertEqual(captured["seconds"], 0.5)

    def test_adk_argument_dictionary_shape_and_underscores(self):
        # Exact scalar conversion observed in ADK: ['--key', str(value)].
        arguments = {"query": "dispatch request", "max_files": 4,
                     "max-results": 2, "seconds": 0.75}
        argv = [part for key, value in arguments.items() for part in ("--" + key, str(value))]
        captured = {}
        def locate(root, query, **limits):
            captured.update(root=root, query=query, **limits)
            return {"status": "OK", "locations": [], "edges": []}
        code, result = self.invoke(argv, core=SimpleNamespace(locate=locate))
        self.assertEqual(code, 0)
        self.assertEqual(captured["query"], "dispatch request")
        self.assertEqual(captured["max_files"], 4)
        self.assertEqual(captured["max_results"], 2)

    def test_root_override_and_abbreviation_rejected(self):
        for option in ("--root", "--allowed-root", "--roo"):
            with self.subTest(option=option):
                code, result = self.invoke(["--query", "target", option, "/outside"])
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "INVALID_ARGUMENTS")
                self.assertEqual(result["locations"], [])
                self.assertEqual(result["edges"], [])

    def test_help_and_missing_query_are_json_errors(self):
        for argv in ([], ["--help"]):
            with self.subTest(argv=argv):
                code, result = self.invoke(argv)
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "INVALID_ARGUMENTS")

    def test_real_runpy_entrypoint_rejects_root_as_json(self):
        original_argv = sys.argv[:]
        output, errors = io.StringIO(), io.StringIO()
        try:
            sys.argv = ["scripts/locator_skill.py", "--query", "target", "--root", "/outside"]
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as stopped:
                runpy.run_path(locator_skill.__file__, run_name="__main__")
        finally:
            sys.argv[:] = original_argv
        self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(json.loads(output.getvalue())["status"], "INVALID_ARGUMENTS")

    def test_owned_module_failure_is_json_at_cli_boundary(self):
        output = io.StringIO()
        with patch("locator_skill._load_core", side_effect=ValueError("published source hash mismatch")), contextlib.redirect_stdout(output):
            code = locator_skill.main(["--query", "target"])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error"]["type"], "ValueError")
        self.assertEqual(result["locations"], [])

    def test_invalid_scalar_values_and_caps(self):
        for flag, value in (("--max-files", "True"), ("--max-files", "2049"),
                            ("--max-results", "7"), ("--max-bytes", "0"),
                            ("--max-file-bytes", "262145"),
                            ("--max-entries", "20001"), ("--max-ast-nodes", "300001"),
                            ("--seconds", "nan"), ("--seconds", "inf"),
                            ("--seconds", "3.1"), ("--seconds", "0")):
            with self.subTest(flag=flag, value=value):
                code, result = self.invoke(["--query", "target", flag, value])
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "INVALID_ARGUMENTS")

    def test_empty_or_long_query_rejected(self):
        for query in (" ", "x" * 4001):
            with self.subTest(query=query):
                code, result = self.invoke(["--query", query])
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "INVALID_ARGUMENTS")

    def test_limit_is_preserved_with_nonzero_exit(self):
        core = SimpleNamespace(locate=lambda *a, **kw: {"status": "LIMIT", "limit": "time",
                                                       "locations": [], "edges": []})
        code, result = self.invoke(["--query", "target"], core=core)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "LIMIT")

    def test_read_error_is_full_json(self):
        def fail(*args, **kwargs):
            raise OSError("synthetic unreadable workspace\ncontinued")
        code, result = self.invoke(["--query", "target"], core=SimpleNamespace(locate=fail))
        self.assertEqual(code, 2)
        self.assertEqual(result["error"]["type"], "OSError")
        self.assertIn("\n", result["error"]["message"])

    def test_output_limit_never_emits_truncated_json(self):
        core = SimpleNamespace(locate=lambda *a, **kw: {"status": "OK", "locations": [
            {"filepath": "x" * 20000, "symbol": "target", "excerpt": "example"}], "edges": []})
        code, result = self.invoke(["--query", "target"], core=core)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "OK")
        self.assertTrue(result["output_truncated"])
        self.assertEqual(result["omitted"]["locations"], 1)
        self.assertEqual(result["locations"], [])

    def test_unicode_output_is_bounded_utf8_json(self):
        entry = {"filepath": "\u03bb.py", "symbol": "target", "excerpt": "\u03bb\n\"quote\""}
        core = SimpleNamespace(locate=lambda *a, **kw: {"status": "OK", "locations": [entry], "edges": []})
        code, result = self.invoke(["--query", "target"], core=core)
        self.assertEqual(code, 0)
        self.assertEqual(result["locations"], [entry])

    def test_surrogateescaped_filesystem_name_remains_exact_valid_json(self):
        entry = {"filepath": "raw\udcff.py", "symbol": "target", "excerpt": "example"}
        core = SimpleNamespace(locate=lambda *a, **kw: {"status": "OK", "locations": [entry], "edges": []})
        code, result = self.invoke(["--query", "target"], core=core)
        self.assertEqual(code, 0)
        self.assertEqual(result["locations"], [entry])

    def test_surrogate_argument_error_is_valid_utf8_json(self):
        code, result = self.invoke(["--query", "target", "--root", "raw\udcff"])
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "INVALID_ARGUMENTS")
        self.assertIn("raw\udcff", result["error"]["message"])

    def test_twenty_thousand_unicode_gaps_summarized(self):
        gaps = [{"filepath": "\u03bb" * 2000 + str(i), "reason": "symlink skipped"}
                for i in range(20000)]
        source = {"status": "OK", "locations": [], "edges": [],
                  "coverage": {"complete": False, "skipped": gaps}}
        core = SimpleNamespace(locate=lambda *a, **kw: source)
        _, result = self.invoke(["--query", "target"], core=core)
        self.assertEqual(result["coverage"]["skipped_count"], 20000)
        self.assertEqual(result["coverage"]["skipped_reasons"],
                         [{"reason": "symlink skipped", "count": 20000}])
        self.assertTrue(result["output_truncated"])
        self.assertEqual(result["omitted"]["skipped_examples"], 20000)
        self.assertEqual(len(source["coverage"]["skipped"]), 20000)

    def test_edges_excerpts_and_locations_reduce_deterministically(self):
        locations = [{"filepath": "\u03bb" * 900 + str(i) + ".py", "symbol": "target",
                      "excerpt": "\u03b4" * 360} for i in range(6)]
        edges = [{"filepath": "\u03bb" * 900 + ".py", "caller": "caller", "line": i,
                  "target": "target", "expression": "\u03b4" * 160,
                  "evidence": "literal_same_file_name"} for i in range(24)]
        source = {"status": "OK", "locations": locations, "edges": edges}
        core = SimpleNamespace(locate=lambda *a, **kw: source)
        _, first = self.invoke(["--query", "target"], core=core)
        _, second = self.invoke(["--query", "target"], core=core)
        self.assertEqual(first, second)
        self.assertTrue(first["output_truncated"])
        self.assertGreater(first["omitted"]["locations"], 0)
        self.assertGreater(first["omitted"]["edges"], 0)
        for retained in first["locations"]:
            self.assertIn(retained["filepath"], [item["filepath"] for item in locations])
        self.assertEqual(len(locations[0]["excerpt"]), 360)

    def test_query_special_characters_remain_single_argument(self):
        query = 'dispatch "quoted" \\ path\n\u03bb; $(inert)'
        captured = {}
        def locate(root, value, **limits):
            captured["query"] = value
            return {"status": "OK", "locations": [], "edges": []}
        code, _ = self.invoke(["--query", query], core=SimpleNamespace(locate=locate))
        self.assertEqual(code, 0)
        self.assertEqual(captured["query"], query)

    def test_large_unicode_argument_error_is_bounded_and_explicit(self):
        code, result = self.invoke(["--query", "target", "--root", "\u03bb" * 4000])
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "INVALID_ARGUMENTS")
        self.assertTrue(result["output_truncated"])
        self.assertGreater(result["omitted"]["error_message_characters"], 0)

    def test_owned_module_ignores_sys_path_and_cached_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "bounded_ast_locator.py").write_text("raise RuntimeError('must not import this')\n")
            original_path = sys.path[:]
            try:
                sys.path.insert(0, str(root))
                with patch.dict(sys.modules, {"bounded_ast_locator": SimpleNamespace(locate=None)}):
                    core = locator_skill._load_core()
                self.assertTrue(callable(core.locate))
                self.assertEqual(Path(core.__file__).resolve().parent, Path(locator_skill.__file__).resolve().parent)
            finally:
                sys.path[:] = original_path

    def test_adk_temp_cwd_and_runpy_mechanics_with_only_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            scripts = base / "skill" / "scripts"
            scripts.mkdir(parents=True)
            workspace = base / "repository"
            workspace.mkdir()
            fixture = workspace / "a.py"
            fixture.write_text("def dispatch():\n    return 1\n")
            owned = Path(locator_skill.__file__).resolve().parent
            for name in ("locator_skill.py", "bounded_ast_locator.py"):
                (scripts / name).write_bytes((owned / name).read_bytes())
            before = fixture.read_bytes()
            original_cwd, original_argv = Path.cwd(), sys.argv[:]
            output = io.StringIO()
            try:
                os.chdir(scripts.parent)  # ADK's generated wrapper uses skill TD.
                sys.argv = ["scripts/locator_skill.py", "--query", "dispatch", "--max_files", "2"]
                namespace = runpy.run_path("scripts/locator_skill.py", run_name="mechanics_only")
                # Only the fixture invocation substitutes the trusted root;
                # deployed source remains the fixed literal /workspace.
                namespace["main"].__globals__["_TRUSTED_ROOT"] = str(workspace)
                with contextlib.redirect_stdout(output):
                    code = namespace["main"]()
            finally:
                os.chdir(original_cwd)
                sys.argv[:] = original_argv
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result["locations"][0]["filepath"], "a.py")
            self.assertEqual(fixture.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in scripts.iterdir()), ["bounded_ast_locator.py", "locator_skill.py"])
            self.assertEqual(sorted(p.name for p in workspace.iterdir()), ["a.py"])

    def test_modified_sibling_fails_before_source_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp).resolve()
            (scripts / "bounded_ast_locator.py").write_text("raise RuntimeError('must not execute')\n")
            with patch("locator_skill.__file__", str(scripts / "locator_skill.py")), self.assertRaisesRegex(ValueError, "published source hash"):
                locator_skill._load_core()

    def test_symlink_sibling_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp).resolve()
            source = Path(locator_skill.__file__).resolve().with_name("bounded_ast_locator.py")
            (scripts / "bounded_ast_locator.py").symlink_to(source)
            with patch("locator_skill.__file__", str(scripts / "locator_skill.py")), self.assertRaises(OSError):
                locator_skill._load_core()

    def test_published_module_hash_is_preserved(self):
        source = Path(locator_skill.__file__).resolve().with_name("bounded_ast_locator.py")
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), locator_skill._CORE_SHA256)


if __name__ == "__main__":
    unittest.main()
