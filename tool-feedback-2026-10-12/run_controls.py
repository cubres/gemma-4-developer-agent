# SPDX-License-Identifier: Apache-2.0
"""Run only the original invented unittest controls with bounded CPU/wall time."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    os.nice(5)
    old_soft, old_hard = resource.getrlimit(resource.RLIMIT_CPU)
    finite = [20, *[v for v in (old_soft, old_hard) if v != resource.RLIM_INFINITY]]
    cpu_limit = min(finite)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, old_hard))
    def timeout(_signum, _frame):
        raise TimeoutError("Invented control wall limit")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(30)
    started_cpu, started_wall = time.process_time(), time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent), pattern="test_tool_feedback.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    record = {"qualification": "PASS_INVENTED_CPU_CONTROLS" if result.wasSuccessful() else "FAIL_INVENTED_CPU_CONTROLS",
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "python": sys.version.split()[0], "optimization": sys.flags.optimize,
              "cpu_limit_seconds": cpu_limit, "wall_limit_seconds": 30,
              "cpu_seconds": time.process_time() - started_cpu,
              "wall_seconds": time.monotonic() - started_wall,
              "source_sha256": hashlib.sha256((Path(__file__).parent / "tool_feedback.py").read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256((Path(__file__).parent / "test_tool_feedback.py").read_bytes()).hexdigest(),
              "model_or_native_execution": False, "official_score": None}
    with args.receipt.open("x") as handle:
        json.dump(record, handle, indent=2); handle.write("\n")
    signal.alarm(0)
    print(json.dumps(record))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
