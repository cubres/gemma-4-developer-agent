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
"""Synthetic mechanics tests; no repository tasks or model calls."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bounded_ast_locator import locate


class LocatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def source(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_exact_paths_and_lines_are_separate(self):
        self.source("src/pkg/core.py", "\ndef parse_result(value):\n    return value\n")
        result = locate(self.root, "parse_result")
        found = result["locations"][0]
        self.assertEqual(found["filepath"], "src/pkg/core.py")
        self.assertEqual(found["symbol"], "parse_result")
        self.assertEqual(found["start_line"], 2)
        self.assertEqual(found["end_line"], 3)

    def test_async_and_classmethod(self):
        self.source("app.py", "class Client:\n    @classmethod\n    async def dispatch(cls):\n        return cls.prepare()\n    @classmethod\n    def prepare(cls):\n        return 1\n")
        result = locate(self.root, "dispatch prepare")
        self.assertTrue(any(x["symbol"] == "Client.dispatch" and x["kind"] == "async_function" for x in result["locations"]))
        edge = next(x for x in result["edges"] if x["caller"] == "Client.dispatch")
        self.assertEqual(edge["target"], "Client.prepare")
        self.assertEqual(edge["evidence"], "method_receiver_candidate")
        self.assertIn("dynamic dispatch", edge["uncertainty"])

    def test_call_edges_are_directed(self):
        self.source("a.py", "def helper():\n    pass\ndef caller():\n    helper()\n")
        result = locate(self.root, "caller helper")
        self.assertEqual([(x["caller"], x["target"]) for x in result["edges"]], [("caller", "helper")])

    def test_nested_name_resolution(self):
        self.source("a.py", "def inner():\n    pass\ndef outer():\n    def inner():\n        pass\n    inner()\n")
        result = locate(self.root, "outer")
        self.assertEqual(result["edges"][0]["target"], "outer.inner")

    def test_super_candidate_and_mro_uncertainty(self):
        self.source("a.py", "class Base:\n    def work(self):\n        pass\nclass Child(Base):\n    def work(self):\n        super().work()\n")
        edge = next(x for x in locate(self.root, "Child work")["edges"] if x["expression"] == "super().work")
        self.assertEqual(edge["target"], "Base.work")
        self.assertEqual(edge["evidence"], "literal_base_candidates")
        self.assertIn("MRO", edge["uncertainty"])

    def test_ambiguous_bases_remain_unresolved(self):
        self.source("a.py", "class A:\n    def work(self): pass\nclass B:\n    def work(self): pass\nclass C(A, B):\n    def work(self): super().work()\n")
        edge = next(x for x in locate(self.root, "C work")["edges"] if x["expression"] == "super().work")
        self.assertIsNone(edge["target"])
        self.assertEqual(edge["evidence"], "ambiguous_bases")

    def test_imports_and_dynamic_calls_are_not_fabricated(self):
        self.source("a.py", "import unknown as mod\ndef caller(obj):\n    mod.work()\n    getattr(obj, 'work')()\n")
        edges = locate(self.root, "caller")["edges"]
        self.assertTrue(edges)
        self.assertTrue(all(x["target"] is None for x in edges))

    def test_bare_method_name_does_not_resolve_class_namespace(self):
        self.source("a.py", "def helper(): pass\nclass C:\n    def helper(self): pass\n    def caller(self): helper()\n")
        edge = next(x for x in locate(self.root, "caller helper")["edges"] if x["caller"] == "C.caller")
        self.assertEqual(edge["target"], "helper")

    def test_parameter_shadowing_is_explicitly_unresolved(self):
        self.source("a.py", "def helper(): pass\ndef caller(helper): helper()\n")
        edge = locate(self.root, "caller")["edges"][0]
        self.assertIsNone(edge["target"])
        self.assertEqual(edge["evidence"], "unresolved_parameter")

    def test_parameter_shadows_literal_class_receiver(self):
        self.source("a.py", "class C:\n    def helper(self): pass\ndef caller(C): C.helper()\n")
        edge = locate(self.root, "caller")["edges"][0]
        self.assertIsNone(edge["target"])
        self.assertEqual(edge["evidence"], "unresolved_parameter")

    def test_unshadowed_literal_class_receiver_remains_candidate(self):
        self.source("a.py", "class C:\n    @classmethod\n    def helper(cls): pass\ndef caller(): C.helper()\n")
        edge = locate(self.root, "caller")["edges"][0]
        self.assertEqual(edge["target"], "C.helper")
        self.assertEqual(edge["evidence"], "literal_class_candidate")

    def test_static_method_argument_is_not_instance_receiver(self):
        self.source("a.py", "class C:\n    def helper(self): pass\n    @staticmethod\n    def caller(obj): obj.helper()\n")
        edge = locate(self.root, "caller")["edges"][0]
        self.assertIsNone(edge["target"])

    def test_nested_receiver_parameter_shadowing(self):
        self.source("a.py", "class C:\n    def helper(self): pass\n    def outer(self):\n        def caller(self): self.helper()\n")
        edge = locate(self.root, "caller")["edges"][0]
        self.assertIsNone(edge["target"])

    def test_six_result_cap_and_stable_order(self):
        for i in reversed(range(10)):
            self.source(f"p{i}.py", "def target(): pass\n")
        first = locate(self.root, "target")
        self.assertEqual(first, locate(self.root, "target"))
        self.assertEqual(len(first["locations"]), 6)
        self.assertEqual([x["filepath"] for x in first["locations"]], [f"p{i}.py" for i in range(6)])

    def test_read_only_and_no_import_execution(self):
        p = self.source("a.py", "raise RuntimeError('must not execute')\ndef target(): pass\n")
        before = p.read_bytes()
        result = locate(self.root, "target")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(before, p.read_bytes())
        self.assertEqual(sorted(x.name for x in self.root.iterdir()), ["a.py"])

    def test_source_tests_and_hidden_directories_excluded(self):
        self.source("tests/test_a.py", "def target(): pass\n")
        self.source(".hidden/a.py", "def target(): pass\n")
        self.assertEqual(locate(self.root, "target")["locations"], [])

    def test_relative_root_and_traversal_rejected(self):
        for root in (".", self.root / ".." / self.root.name):
            with self.subTest(root=root), self.assertRaises(ValueError):
                locate(root, "target")

    def test_symlink_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp).resolve() / "link"
            link.symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(ValueError):
                locate(link, "target")

    def test_symlink_file_and_directory_never_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp).resolve()
            external = outside / "outside.py"
            external.write_text("def secret_target(): pass\n")
            (self.root / "file.py").symlink_to(external)
            (self.root / "dir").symlink_to(outside, target_is_directory=True)
            result = locate(self.root, "secret_target")
            self.assertEqual(result["locations"], [])
            self.assertEqual(result["coverage"]["bytes_read"], 0)
            self.assertEqual(len(result["coverage"]["skipped"]), 2)

    def test_symlink_swap_at_file_open_blocked(self):
        path = self.source("a.py", "def target(): pass\n")
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp).resolve() / "external.py"
            external.write_text("def secret_target(): pass\n")
            real_open = __import__("os").open
            def swap(name, flags, **kwargs):
                if name == "a.py":
                    path.rename(self.root / "kept_source.py")
                    path.symlink_to(external)
                return real_open(name, flags, **kwargs)
            with patch("bounded_ast_locator.os.open", side_effect=swap):
                result = locate(self.root, "secret_target")
            self.assertEqual(result["coverage"]["bytes_read"], 0)
            self.assertEqual(result["locations"], [])

    def test_ancestor_symlink_swap_at_root_open_blocked(self):
        root = self.root / "parent" / "repo"
        root.mkdir(parents=True)
        parent = root.parent
        real_open = __import__("os").open
        def swap(name, flags, **kwargs):
            if name == "parent":
                parent.rename(self.root / "kept_parent")
                parent.symlink_to(self.root / "kept_parent", target_is_directory=True)
            return real_open(name, flags, **kwargs)
        with patch("bounded_ast_locator.os.open", side_effect=swap), self.assertRaises(OSError):
            locate(root, "target")

    def test_fifo_swap_before_open_does_not_block(self):
        import os
        path = self.source("a.py", "def target(): pass\n")
        real_open = os.open
        def swap(name, flags, **kwargs):
            if name == "a.py":
                path.rename(self.root / "kept_source.py")
                os.mkfifo(path)
            return real_open(name, flags, **kwargs)
        with patch("bounded_ast_locator.os.open", side_effect=swap):
            result = locate(self.root, "target")
        self.assertEqual(result["coverage"]["bytes_read"], 0)
        self.assertEqual(result["locations"], [])
        self.assertEqual(result["coverage"]["skipped"][0]["reason"], "not a regular file")

    def test_non_python_files_are_not_read(self):
        (self.root / "identity.json").write_text("private content")
        (self.root / "notes.txt").write_text("def target(): pass")
        result = locate(self.root, "target")
        self.assertEqual(result["coverage"]["bytes_read"], 0)
        self.assertEqual(result["locations"], [])

    def test_call_output_is_bounded(self):
        self.source("a.py", "def target():\n" + "    target()\n" * 40)
        result = locate(self.root, "target")
        self.assertEqual(len(result["edges"]), 24)
        self.assertLessEqual(len(result["locations"][0]["excerpt"]), 360)

    def test_file_count_limit_discards_partial_results(self):
        self.source("a.py", "def target(): pass\n")
        self.source("b.py", "def target(): pass\n")
        result = locate(self.root, "target", max_files=1)
        self.assertEqual(result["status"], "LIMIT")
        self.assertEqual(result["limit"], "source files")
        self.assertEqual(result["locations"], [])
        self.assertEqual(result["edges"], [])

    def test_total_byte_limit_never_overreads(self):
        self.source("a.py", "def target(): pass\n")
        result = locate(self.root, "target", max_bytes=5)
        self.assertEqual(result["limit"], "total source bytes")
        self.assertLessEqual(result["coverage"]["bytes_read"], 5)

    def test_oversized_file_is_explicit_gap(self):
        self.source("a.py", "def target():\n    pass\n" + "# large\n" * 100)
        self.source("b.py", "def target(): pass\n")
        result = locate(self.root, "target", max_file_bytes=30)
        self.assertEqual([x["filepath"] for x in result["locations"]], ["b.py"])
        self.assertEqual(result["coverage"]["skipped"][0]["reason"], "file byte limit")
        self.assertFalse(result["coverage"]["complete"])

    def test_directory_entry_budget(self):
        self.source("a.py", "def target(): pass\n")
        self.source("b.py", "def target(): pass\n")
        result = locate(self.root, "target", max_entries=1)
        self.assertEqual(result["limit"], "directory entries")
        self.assertEqual(result["locations"], [])

    def test_ast_budget(self):
        self.source("a.py", "def target():\n    return 1 + 2 + 3\n")
        result = locate(self.root, "target", max_ast_nodes=2)
        self.assertEqual(result["limit"], "AST nodes")
        self.assertEqual(result["locations"], [])

    def test_cooperative_time_limit_without_sleep(self):
        self.source("a.py", "def target(): pass\n")
        with patch("bounded_ast_locator.time.monotonic", side_effect=[0.0, 5.0]):
            result = locate(self.root, "target", seconds=1)
        self.assertEqual(result["limit"], "time")
        self.assertEqual(result["locations"], [])

    def test_syntax_and_encoding_gaps(self):
        self.source("bad.py", "def broken(:\n")
        (self.root / "binary.py").write_bytes(b"\xff\xfe")
        self.source("good.py", "def target(): pass\n")
        result = locate(self.root, "target")
        self.assertEqual(len(result["locations"]), 1)
        self.assertEqual({x["reason"] for x in result["coverage"]["skipped"]}, {"SyntaxError", "UnicodeDecodeError"})

    def test_no_match_is_success_not_confidence(self):
        self.source("a.py", "def target(): pass\n")
        result = locate(self.root, "unrelated")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["locations"], [])
        self.assertIn("do not prove", result["interpretation"])

    def test_validation(self):
        for options in ({"max_results": 7}, {"max_results": True}, {"max_bytes": 0},
                        {"seconds": float("inf")}, {"seconds": False}, {"max_ast_nodes": -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                locate(self.root, "target", **options)
        for query in ("", " " , "x" * 4001, None):
            with self.subTest(query=query), self.assertRaises(ValueError):
                locate(self.root, query)


if __name__ == "__main__":
    unittest.main()
