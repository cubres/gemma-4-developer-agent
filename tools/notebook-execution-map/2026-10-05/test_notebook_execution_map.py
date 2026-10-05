"""Tiny synthetic source-string fixtures; no notebook files or actual campaign inputs."""
import hashlib
import json
from pathlib import Path
import time
import unittest
from unittest.mock import mock_open, patch

import notebook_execution_map as inspector


def fixture(*sources):
    return json.dumps({"cells": [{"cell_type": "code", "source": source} for source in sources]}).encode()


class ExecutionMapTests(unittest.TestCase):
    def test_comments_are_ignored(self):
        result = inspector.inspect_bytes(fixture("# RUN_GPU = True\nRUN_GPU = False\n"))
        self.assertEqual(len(result["assignments"]), 1)
        self.assertEqual(result["assignments"][0]["line"], 2)
        self.assertIs(result["assignments"][0]["scalar_value"], False)

    def test_literal_and_dynamic_are_distinct(self):
        result = inspector.inspect_bytes(fixture("TIMEOUT = 30\nMAX_SECONDS = 5 * 60\nRUN_TEST = os.environ.get('EXAMPLE')\n"))
        self.assertEqual([row["assignment_kind"] for row in result["assignments"]], ["literal", "dynamic", "dynamic"])
        self.assertNotIn("scalar_value", result["assignments"][1])

    def test_configuration_class_and_scopes(self):
        source = "class CFG:\n    epochs = 2\n    path = 'example'\n\ndef example():\n    RUN_GPU = True\nclass Model:\n    EPOCHS = 100\n"
        result = inspector.inspect_bytes(fixture(source))
        self.assertEqual([row["name"] for row in result["assignments"]], ["epochs", "path"])
        self.assertEqual(result["execution_budget_flags"][0]["categories"], ["work_budget"])
        self.assertNotIn("scalar_value", result["assignments"][1])

    def test_conditional_and_repeated_assignments(self):
        result = inspector.inspect_bytes(fixture("RUN_TEST = False\nif condition:\n    RUN_TEST = True\n"))
        self.assertEqual([row["conditional"] for row in result["assignments"]], [False, True])

    def test_source_hash_and_cell_counts(self):
        source = json.dumps({"cells": [{"cell_type": "markdown", "source": "# example"},
                                      {"cell_type": "code", "source": ["SEED = ", "42\n"]}]}).encode()
        result = inspector.inspect_bytes(source)
        self.assertEqual(result["source_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual((result["cell_count"], result["code_cell_count"]), (2, 1))

    def test_unsupported_magic_is_partial(self):
        result = inspector.inspect_bytes(fixture("%%writefile example.py\nprint('example')\n", "SEED = 1\n"))
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(len(result["assignments"]), 1)

    def test_invalid_encoding_fails_cleanly(self):
        self.assertEqual(inspector.inspect_bytes(b'\xff')["error"], "invalid_utf8")

    def test_oversize_fails_cleanly(self):
        self.assertEqual(inspector.inspect_bytes(b' ' * (inspector.MAX_BYTES + 1))["error"], "input_too_large")

    def test_oversized_code_fails_cleanly(self):
        self.assertEqual(inspector.inspect_bytes(fixture(' ' * (inspector.MAX_CELL_CHARS + 1)))["error"], "code_size_limit")

    def test_invalid_json_and_schema(self):
        self.assertEqual(inspector.inspect_bytes(b'{')["error"], "invalid_json")
        self.assertEqual(inspector.inspect_bytes(b'[]')["error"], "missing_cells")

    def test_outputs_and_metadata_not_inspected(self):
        source = json.dumps({"metadata": {"unrelated": [1, 2]}, "cells": [
            {"cell_type": "code", "source": "RUN_TEST = False", "outputs": [{"text": "RUN_TEST=True"}]}]}).encode()
        self.assertEqual(len(inspector.inspect_bytes(source)["assignments"]), 1)

    def test_no_execution_of_calls(self):
        result = inspector.inspect_bytes(fixture("MAX_SECONDS = undefined_function()\n"))
        self.assertEqual(result["status"], "MAPPED")
        self.assertEqual(result["assignments"][0]["expression_kind"], "Call")

    def test_input_is_opened_readonly_without_writes(self):
        source = fixture("RUN_TEST = False\n")
        calls = []
        # Mock the file descriptor boundary. No fixture file is created.
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def fileno(self): return 71
            def read(self, size):
                calls.append(("read", size))
                return source
        import stat
        info = type("FileInfo", (), {"st_mode": stat.S_IFREG, "st_size": len(source)})()
        with patch.object(inspector.os, "open", return_value=71) as opened, \
             patch.object(inspector.os, "fdopen", return_value=Stream()) as fdopen, \
             patch.object(inspector.os, "fstat", return_value=info), \
             patch.object(Path, "write_text", side_effect=AssertionError("write attempted")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write attempted")):
            result = inspector.inspect_path(Path("synthetic-user-input.ipynb"))
        self.assertEqual(result["status"], "MAPPED")
        self.assertEqual(opened.call_args.args[1] & inspector.os.O_ACCMODE, inspector.os.O_RDONLY)
        fdopen.assert_called_once_with(71, "rb")
        self.assertEqual(calls, [("read", inspector.MAX_BYTES + 1)])

    def test_cell_and_assignment_limits(self):
        self.assertEqual(inspector.inspect_bytes(fixture(*([""] * (inspector.MAX_CELLS + 1))))["error"], "cell_limit")
        many = '\n'.join(f"MAX_STEPS_{i} = 1" for i in range(inspector.MAX_ASSIGNMENTS + 1))
        self.assertEqual(inspector.inspect_bytes(fixture(many))["error"], "assignment_limit")

    def test_all_reports_are_strict_json(self):
        result = inspector.inspect_bytes(fixture("TIMEOUT = 1e999\n"))
        json.dumps(result, allow_nan=False)
        self.assertNotIn("scalar_value", result["assignments"][0])


if __name__ == "__main__":
    unittest.main()
