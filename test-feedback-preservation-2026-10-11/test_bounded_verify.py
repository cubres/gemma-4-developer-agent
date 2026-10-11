"""Invented command controls; no competition tasks, harness, or model calls."""

import subprocess
import sys
import unittest
import os

from bounded_verify import bounded_command


class VerifyTests(unittest.TestCase):
    def run_python(self, source, **limits):
        command = bounded_command([sys.executable, "-c", source], **limits)
        return subprocess.run(
            ["/bin/bash", "-c", command], capture_output=True, timeout=5
        )

    def test_success(self):
        result = self.run_python("print('passed')")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"VERIFY_PRODUCER_EXIT=0 VERIFY_TAIL_EXIT=0,0", result.stdout)

    def test_test_failure_one(self):
        self.assertEqual(self.run_python("raise SystemExit(1)").returncode, 1)

    def test_interrupt_two(self):
        self.assertEqual(self.run_python("raise SystemExit(2)").returncode, 2)

    def test_no_tests_five(self):
        self.assertEqual(self.run_python("raise SystemExit(5)").returncode, 5)

    def test_silent_failure(self):
        result = self.run_python("raise SystemExit(4)")
        self.assertEqual(result.returncode, 4)
        self.assertIn(b"VERIFY_PRODUCER_EXIT=4", result.stdout)

    def test_stderr_tail(self):
        result = self.run_python("import sys; print('error', file=sys.stderr); sys.exit(3)")
        self.assertEqual(result.returncode, 3)
        self.assertIn(b"error", result.stdout)

    def test_missing_program(self):
        result = subprocess.run(
            ["/bin/bash", "-c", bounded_command(["/nonexistent/verify_program"])],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 127)

    def test_line_tail(self):
        result = self.run_python("for i in range(100): print('row_'+str(i))", line_limit=2)
        self.assertIn(b"row_98\nrow_99", result.stdout)
        self.assertNotIn(b"row_97", result.stdout)

    def test_large_single_line(self):
        result = self.run_python("print('x'*1000000+'END'); raise SystemExit(1)", byte_limit=100)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"END", result.stdout)
        self.assertLessEqual(len(result.stdout), 180)

    def test_unicode_output(self):
        result = self.run_python("print(chr(0x03bb)*5000)", byte_limit=101)
        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout), 180)
        self.assertIn(b"VERIFY_PRODUCER_EXIT=0", result.stdout)

    def test_literal_metacharacters(self):
        argument = "space ' quote; $(printf WENT_WRONG) `printf WENT_WRONG`\nend"
        result = subprocess.run(
            ["/bin/bash", "-c", bounded_command([sys.executable, "-c", "import sys; print(repr(sys.argv[1]))", argument])],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(repr(argument).encode(), result.stdout)

    def test_fake_trailer_cannot_mask_failure(self):
        result = self.run_python("print('VERIFY_PRODUCER_EXIT=0'); raise SystemExit(1)")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.rstrip().endswith(b"VERIFY_PRODUCER_EXIT=1 VERIFY_TAIL_EXIT=0,0"))

    def test_inherited_errexit_and_pipefail(self):
        command = bounded_command([sys.executable, "-c", "raise SystemExit(2)"])
        result = subprocess.run(
            ["/bin/bash", "-e", "-o", "pipefail", "-c", command],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 2)

    def test_missing_tail_holds_output(self):
        command = bounded_command([sys.executable, "-c", "print('ok')"])
        environment = dict(os.environ)
        environment["PATH"] = "/nonexistent/verify_path"
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True,
            timeout=5,
            env=environment,
        )
        self.assertEqual(result.returncode, 125)

    def test_minimal_prompt_idiom(self):
        import shlex
        producer = " ".join(map(shlex.quote, [sys.executable, "-c", "print('failed'); raise SystemExit(1)"]))
        script = producer + " 2>&1 | tail -n 15 | tail -c 3000"
        result = subprocess.run(
            ["/bin/bash", "-o", "pipefail", "-c", script],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 1)

    def test_invalid_argv(self):
        for argv in ([], "python", b"python", [""], ["python", 4], ["python", "\x00"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                bounded_command(argv)

    def test_invalid_limits(self):
        for field, value in (("line_limit", True), ("line_limit", 0), ("line_limit", 201), ("byte_limit", 0), ("byte_limit", 3501), ("byte_limit", 3.5)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                bounded_command(["python"], **{field: value})

    def test_original_tail_pipeline_masks_failure(self):
        # This is the deliberately broken comparison, using invented output.
        import shlex
        command = " ".join(map(shlex.quote, [sys.executable, "-c", "print('failed'); raise SystemExit(1)"]))
        result = subprocess.run(
            ["/bin/bash", "-c", command + " 2>&1 | tail -15"],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
