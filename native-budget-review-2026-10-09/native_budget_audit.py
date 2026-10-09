"""Original, offline projection of native Gemma timing and termination evidence.

No task contents, model prompts, patches, arbitrary source strings, or paths are
emitted. This module never restores, modifies, or removes an input artifact.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics

MAX_INPUT_BYTES = 8 * 1024 * 1024
KNOWN_TOOLS = frozenset({"run_command", "read_file", "edit_file", "write_file",
                         "get_status", "submit_patch", "get_code_neighbors",
                         "search_similar_code", "get_code_subgraph"})


def number(value, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric scalar")
    if not math.isfinite(value) or value < 0 or (integer and int(value) != value):
        raise ValueError("Invalid nonnegative numeric scalar")
    return int(value) if integer else float(value)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Timestamp must carry an offset")
    return t.timestamp()


def read_artifact(path, *, jsonl=False):
    # Read one bounded existing file; no directory traversal or downloaded code.
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds the artifact byte cap")
    text = raw.decode("utf-8")
    value = [json.loads(line) for line in text.splitlines() if line.strip()] if jsonl else json.loads(text)
    return value, hashlib.sha256(raw).hexdigest()


def rounded(value):
    return None if value is None else round(value, 6)


def audit(ledger, task_rows, arm, verification, watchdog, *, budget_seconds):
    """Accept one observed canary; never infer official score or population gain."""
    budget = number(budget_seconds)
    if budget <= 0 or len(task_rows) != 1:
        raise ValueError("A positive budget and exactly one canary task are required")
    task = task_rows[0]
    arm_rows = arm.get("rows")
    if not isinstance(arm_rows, list) or len(arm_rows) != 1:
        raise ValueError("Arm must contain exactly one native task row")
    native_row = arm_rows[0]
    for row, identity_key in ((task, "instance_id"), (native_row, "task_id")):
        if any(not isinstance(row.get(key), str) or not row[key].strip()
               for key in (identity_key, "repo")):
            raise ValueError("Task identity and repository need explicit nonempty strings")
        for key in ("tool_calls", "total_llm_calls", "task_index"):
            if key not in row:
                raise ValueError("Mandatory task counter is absent")
            number(row[key], integer=True)
        if "test_exit_code" not in row or (row["test_exit_code"] is not None and type(row["test_exit_code"]) is not int):
            raise ValueError("Test exit needs explicit integer or null evidence")
    if (native_row.get("task_id") != task.get("instance_id")
        or any(native_row.get(key) != task.get(key) for key in
               ("repo", "resolved", "test_exit_code", "tool_calls", "total_llm_calls", "task_index"))
        or abs(number(native_row["duration_seconds"]) - number(task["duration_seconds"])) > 0.02
        or not isinstance(native_row.get("agent_patch"), str)
        or len(native_row["agent_patch"]) != number(task["agent_patch_size"], integer=True)):
        raise ValueError("Arm receipt and task projection describe different task rows")
    if type(task.get("resolved")) is not bool:
        raise ValueError("Native task resolved outcome needs an explicit boolean")
    elapsed = number(task["duration_seconds"])
    arm_start = timestamp(arm["started_utc"])
    arm_end = timestamp(arm["finished_utc"])
    if arm_end < arm_start or abs((arm_end - arm_start) - elapsed) > 2:
        raise ValueError("Arm and task clocks do not establish the same task window")
    cut = arm_start + elapsed
    rows = ledger["rows"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("No observed model requests")
    indices = [number(row["index"], integer=True) for row in rows]
    if len(set(indices)) != len(indices) or indices != sorted(indices):
        raise ValueError("Request indices must be unique and ordered")
    counts = Counter()
    tools = Counter()
    root_complete = []
    root_failed = []
    completed_seconds = failed_seconds = censored_seconds = compaction_seconds = 0.0
    completion_counts = []
    root_decode = []
    declared_budgets = set()
    prior_observed_end = arm_start
    unknown_tool_count = 0
    for row in rows:
        capture = row.get("capture")
        if not isinstance(capture, dict) or type(capture.get("root_call")) is not bool:
            raise ValueError("Request class needs explicit native evidence")
        is_root = capture["root_call"]
        kind = "root" if is_root else "compaction"
        start = timestamp(row["started_utc"])
        if start < arm_start - 1 or start > cut + 1 or start < prior_observed_end - 0.1:
            raise ValueError("Requests lie outside or overlap the observed task window")
        state = row["status"]
        if state not in {"COMPLETE", "ERROR", "STARTED"}:
            raise ValueError("Unknown native model request status")
        counts[f"{kind}_{state.lower()}"] += 1
        if row.get("thinking_token_budget") is not None:
            declared_budgets.add(number(row["thinking_token_budget"], integer=True))
        if state == "STARTED":
            if row.get("finished_utc") is not None:
                raise ValueError("Unfinished request carries a finish timestamp")
            duration = max(0.0, cut - start)
            censored_seconds += duration
            prior_observed_end = cut
        else:
            end = timestamp(row["finished_utc"])
            if end < start or end > cut + 1:
                raise ValueError("Invalid request finish timestamp")
            duration = end - start
            # Cross-check the independent monotonic clock when present.
            if row.get("started_monotonic") is not None and row.get("finished_monotonic") is not None:
                mono = number(row["finished_monotonic"]) - number(row["started_monotonic"])
                if mono < 0 or abs(mono - duration) > 0.25:
                    raise ValueError("Wall and monotonic request durations disagree")
            prior_observed_end = end
            if state == "COMPLETE":
                if row.get("http_status") != 200:
                    raise ValueError("Completed request lacks HTTP success evidence")
                completed_seconds += duration
                if is_root:
                    root_complete.append(duration)
                    usage = row.get("usage") or {}
                    if usage.get("completion_tokens") is not None:
                        completion_counts.append(number(usage["completion_tokens"], integer=True))
                    decode = row.get("decode") or {}
                    if decode.get("server_decode_tok_s") is not None:
                        root_decode.append(number(decode["server_decode_tok_s"]))
                else:
                    compaction_seconds += duration
            else:
                failed_seconds += duration
                if is_root:
                    root_failed.append(duration)
        names = row.get("returned_tool_names") or []
        if not isinstance(names, list):
            raise ValueError("Invalid native tool-name projection")
        for name in names:
            if name in KNOWN_TOOLS:
                tools[name] += 1
            else:
                unknown_tool_count += 1
    # A task row provides duration, but not an independently recorded task-end
    # timestamp. Arm-clock censor durations are estimates, not exact latency.
    incurred_finished = completed_seconds + failed_seconds
    incurred = incurred_finished + censored_seconds
    if incurred > elapsed + 2:
        raise ValueError("Model durations exceed the measured single-task window")
    patch_size = number(task["agent_patch_size"], integer=True)
    finalpytest = number(verification["finalpytest_count"], integer=True)
    junit = number(verification["actual_cat_junit_count"], integer=True)
    capture_errors = verification.get("capture_errors")
    if not isinstance(capture_errors, list):
        raise ValueError("Verification capture errors need explicit evidence")
    survivors = watchdog.get("teardown", {}).get("survivors")
    nvml = watchdog.get("nvml_after_teardown", {})
    arm_preserved = arm.get("preservation", {}).get("passed") is True
    outer_preserved = watchdog.get("outer_notebook_packet_preservation", {}).get("passed") is True
    cleanup = survivors == [] and nvml.get("returncode") == 0 and nvml.get("rows") == []
    tests_passed = type(task.get("test_exit_code")) is int and task["test_exit_code"] == 0 and task["resolved"] is True
    evidence_complete = patch_size > 0 and finalpytest > 0 and junit > 0 and not capture_errors and cleanup and arm_preserved and outer_preserved
    process_returned = (arm.get("status") == "PUBLIC_TASK_NATIVE_RETURNED"
                        and watchdog.get("status") == "NATIVE_SINGLE_CANARY_RETURNED_REVIEW_REQUIRED"
                        and type(watchdog.get("worker_exit_code_before_teardown")) is int
                        and watchdog["worker_exit_code_before_teardown"] == 0)
    longest = max(root_complete + root_failed, default=None)
    median_completed = statistics.median(root_complete) if root_complete else None
    warnings = []
    if counts["root_started"] or counts["compaction_started"]:
        warnings.append("UNFINISHED_REQUESTS_RETAINED_IN_DENOMINATOR")
    if root_failed:
        warnings.append("COMPLETED_ONLY_MEDIAN_EXCLUDES_FAILED_REQUESTS")
    if longest is not None and longest / budget > 0.25:
        warnings.append("ONE_REQUEST_EXCEEDS_QUARTER_OF_TASK_BUDGET")
    if patch_size == 0 and incurred / budget > 0.8:
        warnings.append("NO_PATCH_WHILE_MODEL_TIME_DOMINATES")
    if not evidence_complete:
        warnings.append("PATCH_VERIFICATION_OR_PRESERVATION_EVIDENCE_INCOMPLETE")
    cap = next(iter(declared_budgets)) if len(declared_budgets) == 1 else None
    decode_median = statistics.median(root_decode) if root_decode else None
    return {
        "schema": "gemma-native-budget-audit-v1",
        "scope": "ONE_NATIVE_CANARY_NOT_OFFICIAL_SCORE_OR_QUALITY_GAIN",
        "task_denominator": 1,
        "outcome": {"patch_characters": patch_size, "resolved_in_native_task": task.get("resolved") is True,
                    "native_tests_passed": tests_passed, "finalpytest_invocations": finalpytest,
                    "junit_reads": junit, "verification_capture_errors": len(capture_errors),
                    "owned_cleanup_evidence": cleanup, "notebook_preservation_evidence": arm_preserved and outer_preserved,
                    "expected_native_process_return_evidence": process_returned,
                    "patch_and_verification_evidence_complete": evidence_complete,
                    "native_execution_and_capture_evidence_complete": evidence_complete and process_returned,
                    "official_score": None},
        "timing": {"budget_seconds": budget, "task_elapsed_seconds": elapsed,
                   "observed_requests": len(rows), "request_counts": dict(sorted(counts.items())),
                   "completed_root_median_seconds": rounded(median_completed),
                   "longest_finished_root_seconds": rounded(longest),
                   "longest_finished_root_budget_fraction": rounded(longest / budget) if longest is not None else None,
                   "completed_model_seconds_including_compaction": rounded(completed_seconds),
                   "failed_model_seconds": rounded(failed_seconds),
                   "censored_model_seconds_arm_clock_estimate": rounded(censored_seconds),
                   "censored_timing_basis": "arm started_utc plus task duration; task end timestamp absent",
                   "completed_compaction_seconds": rounded(compaction_seconds),
                   "finished_model_seconds": rounded(incurred_finished),
                   "finished_model_budget_fraction": rounded(incurred_finished / budget),
                   "model_seconds_including_censored_estimate": rounded(incurred),
                   "model_budget_fraction_including_censored_estimate": rounded(incurred / budget)},
        "tools": {"known_returned_tool_counts": dict(sorted(tools.items())), "unknown_returned_tools": unknown_tool_count,
                  "returned_tool_names_do_not_prove_successful_edits": True},
        "tokens": {"completed_root_usage_count": len(completion_counts),
                   "max_reported_completion_tokens": max(completion_counts, default=None),
                   "declared_thinking_budget": cap,
                   "reasoning_tokens": None, "reasoning_cap_hit_rate": None,
                   "reason": "Native usage has no separate reasoning-token or cap-hit evidence",
                   "measured_server_decode_median_tokens_per_second": rounded(decode_median),
                   "declared_thinking_budget_decode_seconds_if_fully_used": rounded(cap / decode_median) if cap is not None and decode_median else None,
                   "full_budget_decode_projection_is_inference": True},
        "diagnostic_warnings": warnings,
        "quality_promotion": "UNPROVEN_REQUIRES_PAIRED_TASK_EVIDENCE_AND_EXACT_COMPLETED_OFFICIAL_ROW",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("ledger", "task", "arm", "verification", "watchdog"):
        parser.add_argument("--" + role, type=Path, required=True)
    parser.add_argument("--budget-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True, help="A new JSON file; existing files are never overwritten")
    args = parser.parse_args()
    values, hashes = {}, {}
    for role in ("ledger", "task", "arm", "verification", "watchdog"):
        values[role], hashes[role] = read_artifact(getattr(args, role), jsonl=role == "task")
    if values["arm"].get("verification_capture_receipt_sha256") != hashes["verification"]:
        raise ValueError("Arm does not bind the supplied verification receipt bytes")
    result = audit(values["ledger"], values["task"], values["arm"], values["verification"], values["watchdog"], budget_seconds=args.budget_seconds)
    result["input_sha256_by_role"] = hashes
    if args.output.suffix != ".json" or args.output.name == "kernel-metadata.json":
        raise ValueError("Only a new ordinary aggregate JSON output is permitted")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"scope": result["scope"], "outcome": result["outcome"], "timing": result["timing"]}, sort_keys=True))


if __name__ == "__main__":
    main()
