"""Read-only Gemma native screen receipt checks. Never launches or submits anything.

Python 3.10+, standard library only. Hashes bind bytes, not native authenticity.
Outputs contain aggregate diagnostics only, never raw task errors or payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

MAX_BYTES = 8 * 1024 * 1024
MAX_TASKS = 128
MAX_EVENTS = 4096
ROLES = ("protocol", "pilot", "arm", "capture", "outer")
SHA = re.compile(r"^[0-9a-f]{64}$")
TASK = re.compile(r"^[A-Za-z0-9_:-]{1,160}$")


class Hold(ValueError):
    pass


def need(value, reason):
    if not value:
        raise Hold(reason)


def number(value, name, *, maximum=10**9):
    need(type(value) in (int, float) and math.isfinite(value)
         and 0 <= value <= maximum, "INVALID_NUMBER:" + name)
    return float(value)


def integer(value, name, *, maximum=MAX_TASKS):
    need(type(value) is int and 1 <= value <= maximum, "INVALID_INTEGER:" + name)
    return value


def task_ids(value, name):
    need(type(value) is list and 1 <= len(value) <= MAX_TASKS,
         "INVALID_TASK_LIST:" + name)
    need(all(type(x) is str and TASK.fullmatch(x) for x in value),
         "INVALID_TASK_ID:" + name)
    need(len(set(value)) == len(value), "DUPLICATE_TASK_ID:" + name)
    return value


def no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, "DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def parse(raw):
    need(len(raw) <= MAX_BYTES, "JSON_BYTE_LIMIT")
    def bad_constant(_):
        raise Hold("NONFINITE_JSON_CONSTANT")
    obj = json.loads(raw, object_pairs_hook=no_duplicate_keys,
                     parse_constant=bad_constant)
    need(type(obj) is dict, "JSON_OBJECT_REQUIRED")
    return obj


def read_pinned(path, digest):
    need(type(digest) is str and SHA.fullmatch(digest), "INVALID_SHA256")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    need(len(raw) <= MAX_BYTES, "JSON_BYTE_LIMIT")
    need(hashlib.sha256(raw).hexdigest() == digest, "ARTIFACT_HASH_MISMATCH")
    return {"sha256": digest, "value": parse(raw)}


def same_capture(blob, expected):
    return (type(blob) is dict and type(blob.get("bytes")) is int
            and 0 < blob["bytes"] <= MAX_BYTES and blob["bytes"] == expected["bytes"]
            and blob.get("sha256") == expected["sha256"])


def loaded_manifest(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    manifest = parse(raw)
    need(set(manifest) == {"plan", "files"}, "MANIFEST_KEYS")
    need(type(manifest["files"]) is dict and set(manifest["files"]) == set(ROLES),
         "MANIFEST_ROLES")
    bundle = {}
    for role in ROLES:
        spec = manifest["files"][role]
        need(type(spec) is dict and set(spec) == {"path", "sha256"}, "FILE_SPEC")
        need(type(spec["path"]) is str and 0 < len(spec["path"]) <= 4096, "FILE_PATH")
        target = Path(spec["path"])
        if not target.is_absolute():
            target = Path(path).parent / target
        bundle[role] = read_pinned(target, spec["sha256"])
    return manifest["plan"], bundle, hashlib.sha256(raw).hexdigest()


def _check(plan, bundle, out):
    need(type(plan) is dict and type(plan.get("schema_version")) is int
         and plan["schema_version"] == 1, "PLAN_SCHEMA")
    need(set(bundle) == set(ROLES), "BUNDLE_ROLES")
    for role in ROLES:
        need(type(bundle[role]) is dict and set(bundle[role]) == {"sha256", "value"}
             and type(bundle[role]["sha256"]) is str
             and SHA.fullmatch(bundle[role]["sha256"])
             and type(bundle[role]["value"]) is dict, "BUNDLE_SHAPE")
    p, pilot, arm, cap, outer = (bundle[k]["value"] for k in ROLES)
    planned = task_ids(plan.get("task_ids"), "plan")
    full = task_ids(plan.get("full_gate_task_ids"), "full_gate")
    need(set(planned).issubset(full), "SCREEN_OUTSIDE_FULL_GATE")
    need(planned == task_ids(p.get("task_ids"), "protocol"), "PROTOCOL_TASK_BINDING")
    need(type(plan.get("repo")) is str and p.get("repo") == plan["repo"], "REPO_BINDING")
    need(pilot.get("protocol_sha256") == bundle["protocol"]["sha256"], "PILOT_PROTOCOL_BINDING")
    need(pilot.get("status") == "SINGLE_PUBLIC_NATIVE_RETURNED_REVIEW_REQUIRED", "PILOT_NOT_RETURNED")
    need(outer.get("status") == "NATIVE_SINGLE_CANARY_RETURNED_REVIEW_REQUIRED"
         and type(outer.get("worker_exit_code_before_teardown")) is int
         and outer["worker_exit_code_before_teardown"] == 0, "OUTER_NOT_RETURNED")
    need(pilot.get("official_score") is None and arm.get("official_score") is None
         and cap.get("official_score") is None and outer.get("official_score") is None,
         "LOCAL_OFFICIAL_SCORE_CONTAMINATION")
    selected = p.get("arm_selection")
    need(type(selected) is list and len(selected) == 1 and selected[0] == plan.get("arm"),
         "SINGLE_ARM_REQUIRED")
    arm_name = selected[0]
    need(type(pilot.get("arms")) is dict and set(pilot["arms"]) == {arm_name}, "PILOT_ARM_SET")
    observed_arm = pilot["arms"][arm_name]
    need(type(observed_arm) is dict and observed_arm.get("receipt_sha256") == bundle["arm"]["sha256"],
         "ARM_RECEIPT_BINDING")
    need(arm.get("status") == "PUBLIC_TASK_NATIVE_RETURNED" and arm.get("strict_junit_sandbox_class") == "SubprocessManager",
         "ARM_NATIVE_ROUTE")
    need(arm.get("verification_capture_receipt_sha256") == bundle["capture"]["sha256"], "CAPTURE_BINDING")
    need(arm.get("actual_final_verification_capture") == cap, "EMBEDDED_CAPTURE_DRIFT")
    need(arm.get("task_ids") == planned and arm.get("repo") == plan["repo"], "ARM_INPUT_BINDING")
    frozen = pilot.get("frozen_public_input", {})
    need(type(frozen) is dict and frozen.get("task_ids") == planned
         and frozen.get("repo") == plan["repo"] and frozen.get("tasks_sha256") == p.get("tasks_file_sha256")
         and type(p.get("tasks_file_sha256")) is str and SHA.fullmatch(p["tasks_file_sha256"]),
         "PILOT_INPUT_BINDING")
    need(arm.get("snapshot_sha256_by_task") == pilot.get("frozen_public_input", {}).get("snapshot_sha256_by_task")
         and set(arm.get("snapshot_sha256_by_task", {})) == set(planned)
         and all(type(x) is str and SHA.fullmatch(x) for x in arm["snapshot_sha256_by_task"].values()),
         "SNAPSHOT_BINDING")
    for label, value in (("ARM", arm.get("preservation")),
                         ("OUTER", outer.get("outer_notebook_packet_preservation")),
                         ("PILOT", pilot.get("preservation_after_all_outcomes", {}).get(arm_name))):
        need(type(value) is dict and value.get("passed") is True, "PRESERVATION_" + label)
    for label, value in (("OUTER", outer.get("teardown")), ("PILOT", pilot.get("process_teardown"))):
        need(type(value) is dict and value.get("survivors") == [], "TEARDOWN_" + label)
    need(outer.get("incomplete_canary_excluded_from_route_qualification") is False, "INCOMPLETE_CANARY")
    for label, value in (("OUTER", outer), ("PILOT", pilot)):
        need(type(value.get("planned_attempt_denominator")) is int
             and value["planned_attempt_denominator"] == 1, "ATTEMPT_DENOMINATOR_" + label)
    need(type(cap.get("events")) is list and len(cap["events"]) <= MAX_EVENTS, "CAPTURE_EVENT_BOUND")
    need(cap.get("status") == "PASS_PRIVATE_FINAL_VERIFICATION_CAPTURE"
         and cap.get("methods_restored") is True and cap.get("capture_errors") == []
         and cap.get("missing_evidence") == [], "CAPTURE_NOT_RETURNED")
    finals = [e for e in cap["events"] if type(e) is dict and e.get("kind") == "FINAL_PYTEST_EXEC"]
    need([e.get("task_id") for e in finals] == planned and cap.get("finalpytest_count") == len(planned),
         "FINAL_VERIFICATION_DENOMINATOR")
    need(all(type(e) is dict and type(e.get("index")) is int and 1 <= e["index"] <= MAX_EVENTS
             for e in cap["events"]), "CAPTURE_EVENT_SHAPE")
    need([e["index"] for e in cap["events"]] == list(range(1, len(cap["events"])+1)),
         "CAPTURE_EVENT_ORDER")
    cats = [e for e in cap["events"] if e.get("kind") == "ACTUAL_CAT_JUNIT_EXEC"]
    validators = [e for e in cap["events"] if e.get("kind") == "ORIGINAL_STRICT_JUNIT_VALIDATOR"]
    need(cap.get("actual_cat_junit_count") == len(cats)
         and cap.get("original_validator_count") == len(validators), "CAPTURE_COUNT_DRIFT")
    for position, event in enumerate(finals):
        need(event.get("original_outcome") == "RETURN" and type(event.get("exit_code")) is int
             and event["exit_code"] in (0, 1) and event.get("timed_out", False) is False,
             "FINAL_VERIFICATION_EXECUTION_HEALTH")
        blob = event.get("junit_file_capture", {})
        need(type(blob) is dict and type(blob.get("bytes")) is int and 0 < blob["bytes"] <= MAX_BYTES
             and type(blob.get("sha256")) is str and SHA.fullmatch(blob["sha256"]), "FINAL_XML_CAPTURE")
        if event["exit_code"] == 0:
            end = finals[position+1]["index"] if position+1 < len(finals) else MAX_EVENTS+1
            matching_cats = [e for e in cats if event["index"] < e["index"] < end
                             and e.get("junit_virtual_path") == event.get("junit_virtual_path")
                             and e.get("original_outcome") == "RETURN" and type(e.get("exit_code")) is int
                             and e["exit_code"] == 0 and same_capture(e.get("actual_cat_stdout_capture"), blob)]
            matching_validators = [e for e in validators if event["index"] < e["index"] < end
                                   and e.get("original_outcome") == "RETURN"
                                   and same_capture(e.get("xml_input_capture"), blob)]
            need(len(matching_cats) == 1 and len(matching_validators) == 1,
                 "ZERO_EXIT_XML_CHAIN")
            need(matching_cats[0]["index"] < matching_validators[0]["index"], "XML_CHAIN_ORDER")
    rows = arm.get("rows")
    need(type(rows) is list and len(rows) == len(planned)
         and all(type(r) is dict for r in rows)
         and [r.get("instance_id") for r in rows] == planned, "RESULT_DENOMINATOR")
    need(rows == observed_arm.get("rows"), "EMBEDDED_RESULT_DRIFT")
    # The old aggregate 'infrastructure_error' is insufficient: caught task
    # exceptions are normal TaskResult returns. Keep task failures in the count.
    task_errors = sum(r.get("error") is not None and r.get("error") != "" for r in rows)
    out["task_error_count"] = task_errors
    need(task_errors == 0, "TASK_ERROR_ROUTE_UNPROVEN")
    need(all(type(r.get("resolved")) is bool and type(r.get("test_exit_code")) is int
             and r["test_exit_code"] in (0, 1) and r.get("repo") == plan["repo"] for r in rows),
         "TASK_RESULT_HEALTH")
    for row, event in zip(rows, finals):
        need(row["test_exit_code"] == event["exit_code"], "TASK_CAPTURE_EXIT_DRIFT")
        if row["resolved"]:
            need(event["exit_code"] == 0, "RESOLVED_NONZERO_EXIT")
            end = finals[planned.index(row["instance_id"])+1]["index"] if row["instance_id"] != planned[-1] else MAX_EVENTS+1
            witness = [e for e in validators if event["index"] < e["index"] < end]
            need(len(witness) == 1 and type(witness[0].get("original_result")) is list
                 and len(witness[0]["original_result"]) == 2 and witness[0]["original_result"][0] is True,
                 "RESOLVED_STRICT_VALIDATOR_WITNESS")
    timings = arm.get("timing", {})
    need(type(timings) is dict and type(timings.get("tasks_expected")) is int
         and type(timings.get("tasks_timed")) is int and timings["tasks_expected"] == len(planned)
         and timings["tasks_timed"] == len(planned), "TIMING_DENOMINATOR")
    per_task = timings.get("per_task")
    need(type(per_task) is list and [r.get("task_id") for r in per_task if type(r) is dict] == planned
         and len(per_task) == len(planned), "TASK_TIMING_BINDING")
    agent, verify, setup, total = [], [], [], []
    for row, timing in zip(rows, per_task):
        need(timing.get("error") == row.get("error") and timing.get("resolved") == row["resolved"], "TASK_TIMING_RESULT_DRIFT")
        a = number(timing.get("agent_seconds"), "agent_sandbox")
        v = number(timing.get("verification_seconds"), "verification")
        s = number(timing.get("setup_seconds"), "setup_residual")
        t = number(timing.get("total_seconds"), "task_total")
        need(abs(t-a-v-s) <= .01, "TASK_TIMING_SUM")
        agent.append(a); verify.append(v); setup.append(s); total.append(t)
    wall = number(observed_arm.get("elapsed_seconds"), "arm_wall")
    need(wall <= number(p.get("arm_cap_seconds", {}).get(arm_name), "arm_cap"), "ARM_CAP")
    need(wall + .01 * len(planned) >= sum(total), "ARM_WALL_SHORTER_THAN_TASKS")
    timeline = pilot.get("timeline_rel_seconds", {})
    need(type(timeline) is dict, "TIMELINE")
    order = ("install_started", "install_finished", "vllm_launch", "engine_ready", "health_ready",
             "weights_verified", "phase_a_started", "phase_a_done", "arm_started", "arm_finished")
    marks = [number(timeline.get(k), k) for k in order]
    need(marks == sorted(marks), "TIMELINE_ORDER")
    need(abs(timeline["arm_finished"] - timeline["arm_started"] - wall) <= .02, "ARM_TIMELINE_WALL")
    start = number(pilot.get("start_monotonic"), "pilot_start")
    deadline = number(pilot.get("deadline_monotonic"), "pilot_deadline")
    need(abs(start-number(outer.get("first_cell_start_monotonic"), "outer_start")) <= .001
         and abs(deadline-number(outer.get("absolute_deadline_monotonic"), "outer_deadline")) <= .001,
         "CLOCK_BINDING")
    allocation = number(pilot.get("allocation_overhead_seconds"), "allocation")
    need(allocation == outer.get("allocation_overhead_seconds"), "ALLOCATION_BINDING")
    abs_limit = number(p.get("absolute_seconds_including_model_load_and_allocation_reserve"), "absolute_limit")
    need(abs(deadline-start-(abs_limit-allocation)) <= .001, "ABSOLUTE_BUDGET_ARITHMETIC")
    outer_wall = number(outer.get("elapsed_from_first_cell_seconds"), "outer_wall")
    need(outer_wall <= deadline-start and timeline["arm_finished"] <= outer_wall, "NATIVE_ABSOLUTE_BOUND")
    need(pilot.get("model_weights_observed_sha256") == p.get("model_tensor_sha256")
         and type(p.get("model_tensor_sha256")) is str and SHA.fullmatch(p["model_tensor_sha256"]),
         "WEIGHT_VERIFICATION")
    readiness = number(p.get("readiness_budget_seconds"), "readiness_budget")
    need(timeline["weights_verified"] <= readiness, "READINESS_RESERVE")
    need(number(p.get("task_reserve_seconds"), "task_reserve") ==
         number(p.get("phase_a_cap_seconds"), "phase_a_cap") +
         number(p.get("arm_cap_seconds", {}).get(arm_name), "arm_cap") + 30,
         "TASK_RESERVE_ARITHMETIC")
    need(abs((deadline-start)-readiness-p["task_reserve_seconds"]) <= .001,
         "READINESS_BUDGET_ARITHMETIC")
    limits = plan.get("runtime_assumptions")
    need(type(limits) is dict, "RUNTIME_ASSUMPTIONS")
    count = integer(limits.get("hidden_task_count"), "hidden_tasks", maximum=10000)
    startup = max(number(limits.get("startup_seconds"), "assumed_startup"), timeline["weights_verified"])
    multiplier = number(limits.get("margin_multiplier"), "margin_multiplier", maximum=10)
    need(multiplier >= 1, "MARGIN_BELOW_ONE")
    session_limit = number(limits.get("session_limit_seconds"), "session_limit")
    nominal_limit = number(limits.get("nominal_projection_limit_seconds"), "nominal_projection_limit")
    agent_limit = number(limits.get("agent_sandbox_max_seconds"), "agent_sandbox_limit")
    other_limit = number(limits.get("verification_and_residual_setup_mean_limit_seconds"), "other_mean_limit")
    mean = wall/len(planned)  # includes import/start/receipt time outside evaluate_task
    nominal = startup + count*mean
    buffered = startup + count*mean*multiplier
    components = p.get("per_task_arm_cap_components", {})
    worst = startup + count*number(components.get("per_task_total"), "declared_task_cap")*multiplier
    out.update(tasks_checked=len(planned), resolved_count=sum(r["resolved"] for r in rows),
               agent_sandbox_max_seconds=max(agent),
               verification_and_residual_setup_mean_seconds=sum(v+s for v,s in zip(verify,setup))/len(planned),
               task_mean_seconds=sum(total)/len(planned), arm_wall_mean_seconds=mean,
               projected_nominal_seconds=nominal, projected_buffered_seconds=buffered,
               declared_cap_worst_projection_seconds=worst,
               declared_cap_worst_case_fits=worst <= session_limit,
               full_gate_coverage=planned == full,
               missing_full_gate_task_count=len(full)-len(planned),
               runtime_assumptions_are_external=True)
    need(max(agent) <= agent_limit, "AGENT_SANDBOX_LIMIT")
    need(out["verification_and_residual_setup_mean_seconds"] <= other_limit, "OTHER_PHASE_MEAN_LIMIT")
    need(nominal <= nominal_limit, "NOMINAL_RUNTIME_PROJECTION")
    need(buffered <= session_limit, "BUFFERED_RUNTIME_PROJECTION")
    out["status"] = "SCREEN_CHECKS_PASS_REVIEW_REQUIRED" if planned != full else "EXPOSED_GATE_CHECKS_PASS_REVIEW_REQUIRED"
    out["native_route_checks_passed"] = True


def review(plan, bundle):
    out = {"status": "HOLD", "native_route_checks_passed": False,
           "official_score": None, "submission_authorized": False,
           "native_authenticity_established": False, "hidden_runtime_guaranteed": False,
           "evidence_scope": "source-bound local receipt consistency; external attestation still required"}
    try:
        _check(plan, bundle, out)
    except (Hold, KeyError, TypeError, ValueError, OverflowError, AttributeError, IndexError, RecursionError) as exc:
        out["reason"] = str(exc) if isinstance(exc, Hold) else "INVALID_RECEIPT_STRUCTURE"
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan, bundle, digest = loaded_manifest(args.manifest)
        report = review(plan, bundle)
        report["manifest_sha256"] = digest
        report["artifact_sha256"] = {role: bundle[role]["sha256"] for role in ROLES}
    except (Hold, OSError, json.JSONDecodeError, UnicodeError, RecursionError, TypeError, ValueError):
        report = {"status": "HOLD", "reason": "MANIFEST_OR_PINNED_INPUT_INVALID",
                  "official_score": None, "submission_authorized": False,
                  "native_route_checks_passed": False, "native_authenticity_established": False,
                  "hidden_runtime_guaranteed": False}
    print(json.dumps(report, sort_keys=True, allow_nan=False, indent=2))
    return 0 if report["status"].endswith("PASS_REVIEW_REQUIRED") else 2


if __name__ == "__main__":
    sys.exit(main())
