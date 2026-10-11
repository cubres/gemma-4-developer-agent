"""Original passive clock observer; never executes or changes an evaluation.

The coordinator may wrap a reviewed async call with this observer. It preserves
the original return object and exception, and records a frozen policy clock only
when both context marks are actually observed. It performs no I/O itself.
"""
from __future__ import annotations

import functools
import inspect
import math
import time


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def observe(task_id, context, started, finished, outcome):
    record = {"task_id": task_id, "clock": "time.perf_counter",
              "state": "UNKNOWN", "outcome": outcome,
              "wrapper_started": started, "wrapper_finished": finished}
    try:
        first = getattr(context, "agent_start_time", None)
        last = getattr(context, "agent_end_time", None)
        elapsed = getattr(context, "agent_elapsed_seconds", None)
        marks = (started, first, last, finished)
        if not all(finite(v) for v in marks) or list(marks) != sorted(marks):
            record["reason"] = "POLICY_MARKS_ABSENT_OR_OUTSIDE_WRAPPER"
            return record
        if not finite(elapsed) or abs(elapsed - (last-first)) > .002:
            record["reason"] = "POLICY_PROPERTY_MARK_DRIFT"
            return record
        record.update(state="OBSERVED_FROZEN", policy_started=first,
                      policy_finished=last, policy_elapsed_seconds=elapsed,
                      preparation_seconds=first-started,
                      completion_seconds=finished-last,
                      sandbox_wall_seconds=finished-started)
    except BaseException:
        # Observer failure must never replace the evaluator's task outcome.
        record["reason"] = "POLICY_OBSERVATION_FAILED"
    return record


class ClockCollector:
    """Explicit installation by a coordinator; sequential public task arms only.

    This object does not install itself, inspect modules, change timeouts, read
    tasks, write receipts, or restore callables. The caller owns that lifecycle.
    """

    def __init__(self):
        self.records = []
        self.observer_errors = 0

    def wrap(self, original):
        signature = inspect.signature(original)
        collector = self

        @functools.wraps(original)
        async def wrapped(*args, **kwargs):
            context = None
            task_id = None
            # Failure to bind an unusual call is diagnostic, never a task edit.
            try:
                bound = signature.bind(*args, **kwargs)
                task = bound.arguments.get("task")
                context = bound.arguments.get("context")
                a = getattr(task, "task_id", None)
                b = getattr(task, "instance_id", None)
                task_id = a if a is not None else b
                if a is not None and b is not None and a != b:
                    task_id = None
            except BaseException:
                pass
            started = time.perf_counter()
            outcome = "EXCEPTION"
            try:
                result = await original(*args, **kwargs)
                outcome = "RETURN"
                return result
            finally:
                finished = time.perf_counter()
                try:
                    collector.records.append(observe(task_id, context, started, finished, outcome))
                except BaseException:
                    collector.observer_errors += 1

        return wrapped

