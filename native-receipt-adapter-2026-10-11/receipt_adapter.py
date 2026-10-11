"""Read-only normalization of pinned Gemma receipts for the reviewed R4 gate.

No network, model, task, organizer imports, execution, or publication. Derived
hashes describe normalized objects, never substitute for original receipt pins.
An internally consistent screen still needs independent native attestation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

MAX_BYTES = 8 * 1024 * 1024
MAX_TASKS = 128
MAX_EVENTS = 4096
MAX_TOTAL_BYTES = 64 * 1024 * 1024
ROLES = ("protocol", "pilot", "arm", "capture", "outer")
OFFICIAL_SOURCES = ("adk_eval_core/models/base.py", "swegemma/context.py",
                    "swegemma/harness/agent_runner.py", "swegemma/evaluate.py",
                    "swegemma/harness/verification.py", "swegemma/models/task.py")
OWNED_SOURCES = ("native_arm.py", "private_junit_receipts.py", "clock_collector.py")
SHA = re.compile(r"^[0-9a-f]{64}$")
TASK = re.compile(r"^[A-Za-z0-9_:-]{1,160}$")
R4_SHA256 = "511518072a7ddc236867ae96d653f1be37b371959efc81a78fe4535359d378a8"
REVIEWED_SOURCE_SHA256 = {
    "adk_eval_core/models/base.py": "bdedef267b1022ffac970c7bc18c2d0a53753ce1f120a3c355b91c9b7b666a0d",
    "swegemma/context.py": "97f06280c50df3132d1af7ef6126884b66b48887a1cf94b293af01e5907dc2a7",
    "swegemma/harness/agent_runner.py": "4d7eccabd203c26f7c39e882684d2fd851f383f6a5c76c4a75b0e559cd5d6a18",
    "swegemma/evaluate.py": "96a46f49267ffcf861f7f90b98efbe828d03f27553ceefce745819028589de1e",
    "swegemma/harness/verification.py": "766e52c34da16cfdc73fc6df22848ab5b9d6b80943d61e7173a844e8efc6c1d9",
    "swegemma/models/task.py": "0b9d705ce759645bd1ee59bb28662a25a951990c024bfeb1e00a41f08350812a",
    "native_arm.py": "d0134b99e2544bed8f8a3d24d1d00cf1f74e19be691e315e08474fb7716012e2",
    "private_junit_receipts.py": "dd9eb12b6a0cb71d7f902806cebf04c039a124e3960a7757407203154ce6e839",
    "clock_collector.py": "316dfa7a05dd54ce51b54e616e4cfe9b58d7fe1e95c7355df521b62fa55810eb",
}


class Hold(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Hold(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return sha(encoded(value))


def pairs(values):
    out = {}
    for key, value in values:
        need(key not in out, "DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def parse(raw):
    need(type(raw) is bytes and len(raw) <= MAX_BYTES, "JSON_BYTE_BOUND")
    def bad(_):
        raise Hold("NONFINITE_JSON_CONSTANT")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    need(type(value) is dict, "JSON_OBJECT_REQUIRED")
    return value


def pinned(raw):
    return {"sha256": sha(raw), "raw": raw, "value": parse(raw)}


def validate_pinned(item):
    need(type(item) is dict and set(item) == {"sha256", "raw", "value"}, "RAW_ARTIFACT_SHAPE")
    need(type(item["sha256"]) is str and SHA.fullmatch(item["sha256"]), "RAW_PIN_FORMAT")
    need(sha(item["raw"]) == item["sha256"]
         and encoded(parse(item["raw"])) == encoded(item["value"]),
         "RAW_PIN_OR_OBJECT_DRIFT")


def tasks(value):
    need(type(value) is list and 0 < len(value) <= MAX_TASKS
         and all(type(v) is str and TASK.fullmatch(v) for v in value)
         and len(set(value)) == len(value), "ORDERED_TASK_DENOMINATOR_INVALID")
    return value


def number(value):
    need(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**9,
         "CLOCK_OR_LIMIT_INVALID")
    return float(value)


def alias(row, primary, alternate, *, identity=False):
    need(type(row) is dict and (primary in row or alternate in row), "RESULT_FIELD_ABSENT")
    if primary in row and alternate in row:
        need(type(row[primary]) is type(row[alternate]) and row[primary] == row[alternate],
             "RESULT_ALIAS_CONFLICT")
    value = row[primary] if primary in row else row[alternate]
    if identity:
        need(type(value) is str and TASK.fullmatch(value), "RESULT_IDENTITY_INVALID")
    else:
        need(value is None or type(value) is str, "RESULT_ERROR_TYPE_INVALID")
        need(value is None or len(value.encode("utf-8")) <= MAX_BYTES, "RESULT_ERROR_BOUND")
    return value


def normalized_rows(rows):
    need(type(rows) is list and len(rows) <= MAX_TASKS, "RESULT_LIST_INVALID")
    result = []
    for row in rows:
        task = alias(row, "task_id", "instance_id", identity=True)
        error = alias(row, "error_message", "error")
        need(type(row.get("resolved")) is bool and type(row.get("test_exit_code")) is int
             and type(row.get("repo")) is str, "RESULT_HEALTH_FIELDS_ABSENT")
        # Opaque patch, trace, test stdout, metadata and status are deliberately
        # excluded from the derived gate view. Status SUCCESS is not health.
        result.append({"instance_id": task, "error": error, "repo": row["repo"],
                       "resolved": row["resolved"], "test_exit_code": row["test_exit_code"]})
    return result


def raw_bindings(plan, bundle):
    need(set(bundle) == set(ROLES), "RAW_ARTIFACTS_MISSING")
    for role in ROLES:
        validate_pinned(bundle[role])
    p, pilot, arm, cap = (bundle[k]["value"] for k in ROLES[:4])
    selected = p.get("arm_selection")
    need(type(selected) is list and selected == [plan.get("arm")], "RAW_ARM_SELECTION")
    need(pilot.get("protocol_sha256") == bundle["protocol"]["sha256"], "RAW_PROTOCOL_BINDING")
    observed = pilot.get("arms", {}).get(plan["arm"])
    need(type(observed) is dict, "RAW_ARM_RECEIPT_ABSENT")
    need(observed.get("receipt_sha256") == bundle["arm"]["sha256"], "RAW_ARM_BINDING")
    need(arm.get("verification_capture_receipt_sha256") == bundle["capture"]["sha256"],
         "RAW_CAPTURE_BINDING")
    need(arm.get("actual_final_verification_capture") == cap, "RAW_CAPTURE_EMBEDDED_DRIFT")
    need(arm.get("rows") == observed.get("rows"), "RAW_RESULT_EMBEDDED_DRIFT")


def source_bindings(protocol, sources):
    need(type(sources) is dict and set(sources) == set(OFFICIAL_SOURCES+OWNED_SOURCES),
         "OBSERVED_SOURCE_PINS_MISSING")
    for name, observed in sources.items():
        need(type(observed) is str and SHA.fullmatch(observed), "SOURCE_PIN_INVALID")
        container = "fresh_python_source_sha256" if name in OFFICIAL_SOURCES else "component_hashes"
        need(protocol.get(container, {}).get(name) == observed, "PROTOCOL_SOURCE_BINDING")
        if name in REVIEWED_SOURCE_SHA256:
            need(observed == REVIEWED_SOURCE_SHA256[name], "REVIEWED_SOURCE_CONTRACT_DRIFT")


def xml_proof(capture, planned, blobs):
    events = capture.get("events")
    need(type(events) is list and len(events) <= MAX_EVENTS
         and all(type(e) is dict and type(e.get("index")) is int for e in events), "XML_EVENT_SHAPE")
    need([e["index"] for e in events] == list(range(1, len(events)+1)), "XML_EVENT_ORDER")
    finals = [e for e in events if e.get("kind") == "FINAL_PYTEST_EXEC"]
    need([e.get("task_id") for e in finals] == planned, "XML_FINAL_TASK_DENOMINATOR")
    for name,kind in (("finalpytest_count","FINAL_PYTEST_EXEC"),
                      ("actual_cat_junit_count","ACTUAL_CAT_JUNIT_EXEC"),
                      ("original_validator_count","ORIGINAL_STRICT_JUNIT_VALIDATOR")):
        need(type(capture.get(name)) is int
             and capture[name] == sum(e.get("kind") == kind for e in events),
             "XML_CAPTURE_COUNT_TYPE_OR_DRIFT")
    needed = set()
    bytes_checked = 0
    def blob_for(event, field):
        nonlocal bytes_checked
        key = str(event["index"])+":"+field
        needed.add(key)
        spec = event.get(field)
        need(type(spec) is dict and type(spec.get("bytes")) is int
             and 0 < spec["bytes"] <= MAX_BYTES and type(spec.get("sha256")) is str
             and SHA.fullmatch(spec["sha256"]), "XML_CAPTURE_DECLARATION")
        need(type(blobs) is dict and key in blobs and type(blobs[key]) is bytes,
             "ACTUAL_XML_BYTES_ABSENT")
        raw = blobs[key]
        bytes_checked += len(raw)
        need(bytes_checked <= MAX_TOTAL_BYTES, "XML_TOTAL_BYTE_BOUND")
        need(len(raw) == spec["bytes"] and sha(raw) == spec["sha256"], "XML_ACTUAL_PIN_OR_SIZE_DRIFT")
        return raw
    for offset, final in enumerate(finals):
        need(type(final.get("exit_code")) is int and final["exit_code"] in (0, 1)
             and final.get("original_outcome") == "RETURN" and final.get("timed_out", False) is False,
             "PYTEST_EXECUTED_TEST_POLICY")
        first = blob_for(final, "junit_file_capture")
        if final["exit_code"] == 0:
            end = finals[offset+1]["index"] if offset+1 < len(finals) else MAX_EVENTS+1
            window = [e for e in events if final["index"] < e["index"] < end]
            cats = [e for e in window if e.get("kind") == "ACTUAL_CAT_JUNIT_EXEC"]
            witnesses = [e for e in window if e.get("kind") == "ORIGINAL_STRICT_JUNIT_VALIDATOR"]
            need(len(cats) == len(witnesses) == 1, "XML_CHAIN_DENOMINATOR")
            cat, witness = cats[0], witnesses[0]
            need(cat["index"] < witness["index"] and cat.get("original_outcome") == "RETURN"
                 and type(cat.get("exit_code")) is int and cat["exit_code"] == 0
                 and cat.get("junit_virtual_path") == final.get("junit_virtual_path"), "XML_CAT_ROUTE")
            # Cat's actual task_id, if exposed, must agree; validator has no such
            # observed field and is bound by ordered window and identical bytes.
            need("task_id" not in cat or cat["task_id"] == final["task_id"], "XML_CAT_TASK_CONFLICT")
            need(witness.get("original_outcome") == "RETURN"
                 and type(witness.get("original_result")) is list
                 and len(witness["original_result"]) == 2
                 and type(witness["original_result"][0]) is bool, "XML_ORIGINAL_VALIDATOR_WITNESS")
            need(first == blob_for(cat, "actual_cat_stdout_capture")
                 and first == blob_for(witness, "xml_input_capture"), "XML_EXACT_BYTE_CHAIN")
    need(type(blobs) is dict and set(blobs) == needed, "XML_LOCAL_MAPPING_DENOMINATOR")
    return {"xml_blob_count": len(needed), "xml_bytes_checked": bytes_checked,
            "strict_verifier_execution_not_repeated": True}


def policy_clock(plan, bundle, sources, clock):
    need(clock is not None, "POLICY_CLOCK_ABSENT")
    validate_pinned(clock)
    value = clock["value"]
    need(type(value.get("schema_version")) is int and value["schema_version"] == 1,
         "POLICY_CLOCK_SCHEMA")
    need(value.get("raw_protocol_sha256") == bundle["protocol"]["sha256"]
         and value.get("raw_arm_sha256") == bundle["arm"]["sha256"]
         and value.get("source_sha256") == sources, "POLICY_CLOCK_RAW_SOURCE_BINDING")
    need(type(value.get("observer_errors")) is int and value["observer_errors"] == 0,
         "POLICY_OBSERVER_ERROR")
    records = value.get("records")
    planned = tasks(plan.get("task_ids"))
    need(type(records) is list and len(records) == len(planned)
         and all(type(r) is dict for r in records)
         and [r.get("task_id") for r in records] == planned, "POLICY_CLOCK_DENOMINATOR")
    timings = bundle["arm"]["value"].get("timing", {}).get("per_task")
    need(type(timings) is list and len(timings) == len(planned)
         and [t.get("task_id") for t in timings] == planned, "POLICY_SANDBOX_TIMING_DENOMINATOR")
    limits = plan.get("runtime_assumptions", {})
    cap = number(limits.get("policy_elapsed_max_seconds"))
    tolerance = number(limits.get("policy_sandbox_clock_tolerance_seconds"))
    need(tolerance <= 1, "POLICY_CLOCK_TOLERANCE_TOO_LARGE")
    policy, prep, completion, sandbox = [], [], [], []
    for row, timing in zip(records, timings):
        need(row.get("state") == "OBSERVED_FROZEN" and row.get("outcome") == "RETURN"
             and row.get("clock") == "time.perf_counter", "POLICY_CLOCK_NOT_OBSERVED_FROZEN")
        marks = [number(row.get(k)) for k in ("wrapper_started", "policy_started", "policy_finished", "wrapper_finished")]
        need(marks == sorted(marks), "POLICY_CLOCK_MARK_ORDER")
        measured = [number(row.get(k)) for k in ("policy_elapsed_seconds", "preparation_seconds", "completion_seconds", "sandbox_wall_seconds")]
        expected = [marks[2]-marks[1], marks[1]-marks[0], marks[3]-marks[2], marks[3]-marks[0]]
        need(all(abs(a-b) <= .002 for a,b in zip(measured, expected)), "POLICY_CLOCK_ARITHMETIC")
        need(abs(measured[3]-number(timing.get("agent_seconds"))) <= tolerance, "POLICY_SANDBOX_WALL_DRIFT")
        need(measured[0] <= cap, "POLICY_ELAPSED_LIMIT")
        policy.append(measured[0]); prep.append(measured[1]); completion.append(measured[2]); sandbox.append(measured[3])
    return {"policy_clock_sha256": clock["sha256"], "policy_elapsed_max_seconds": max(policy),
            "preparation_mean_seconds": sum(prep)/len(prep),
            "post_policy_completion_mean_seconds": sum(completion)/len(completion),
            "sandbox_wall_max_seconds": max(sandbox), "policy_is_distinct_from_sandbox_wall": True}


def normalize(plan, bundle):
    raw_bindings(plan, bundle)
    raw = {role: deepcopy(bundle[role]["value"]) for role in ROLES}
    arm, pilot, cap = (raw[k] for k in ("arm", "pilot", "capture"))
    rows = normalized_rows(arm.get("rows"))
    planned = tasks(plan.get("task_ids"))
    need([r["instance_id"] for r in rows] == planned, "NORMALIZED_RESULT_DENOMINATOR")
    need(arm.get("task_ids") == planned, "RAW_ARM_TASK_DENOMINATOR")
    timings = arm.get("timing", {}).get("per_task")
    need(type(timings) is list and len(timings) == len(rows), "TIMING_LIST_ABSENT")
    truncations = 0
    for row, timing in zip(rows, timings):
        need(type(timing) is dict and timing.get("task_id") == row["instance_id"]
             and timing.get("resolved") == row["resolved"] and "error" in timing, "TIMING_RESULT_IDENTITY")
        error = row["error"]
        # Exact current native_arm.py source stores str(error)[:300] when truthy.
        # This declared transform is validated before expanding to the raw field.
        expected = error[:300] if error else None
        need(timing["error"] == expected, "TIMING_ERROR_SOURCE_TRANSFORM_DRIFT")
        truncations += int(timing["error"] != error)
        timing["error"] = error
    arm["rows"] = rows
    pilot["arms"][plan["arm"]]["rows"] = deepcopy(rows)
    arm["actual_final_verification_capture"] = deepcopy(cap)
    arm["verification_capture_receipt_sha256"] = digest(cap)
    pilot["protocol_sha256"] = digest(raw["protocol"])
    pilot["arms"][plan["arm"]]["receipt_sha256"] = digest(arm)
    derived = {role: {"sha256": digest(value), "value": value} for role,value in raw.items()}
    return derived, {"row_alias_count": len(rows), "timing_error_expansions": truncations,
                     "task_error_count": sum(bool(r["error"]) for r in rows),
                     "opaque_result_payloads_excluded": True,
                     "derived_hash_scope": "canonical normalized JSON; not native receipt bytes"}


def gate_module(path):
    raw = read_bytes(path)
    need(sha(raw) == R4_SHA256, "REVIEWED_R4_SOURCE_DRIFT")
    # Compile the exact bytes already hashed; no reopen/import-path race.
    spec = importlib.util.spec_from_loader("reviewed_r4_receipt_gate", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    module._ADAPTER_PIN_VERIFIED = True
    return module


def examine(plan, bundle, *, sources=None, clock=None, blobs=None, gate=None):
    out = {"status": "HOLD", "adoption_status": "HOLD_NATIVE_ATTESTATION_REQUIRED",
           "submission_authorized": False, "official_score": None,
           "native_authenticity_established": False, "hidden_runtime_guaranteed": False,
           "raw_artifact_sha256": {}, "missing_artifact_roles": [r for r in ROLES if r not in bundle],
           "policy_clock_present": clock is not None, "xml_mapping_present": bool(blobs),
           "derived_gate_checks_passed": False}
    try:
        need(type(plan) is dict and type(plan.get("schema_version")) is int and plan["schema_version"] == 1,
             "PLAN_SCHEMA")
        planned, full = tasks(plan.get("task_ids")), tasks(plan.get("full_gate_task_ids"))
        need(set(planned).issubset(full), "PLAN_TASKS_OUTSIDE_FULL_GATE")
        out.update(planned_task_count=len(planned), full_gate_task_count=len(full),
                   full_ordered_gate_coverage=planned == full, missing_full_gate_task_count=len(full)-len(planned))
        for role,item in bundle.items():
            need(role in ROLES, "UNKNOWN_ARTIFACT_ROLE")
            validate_pinned(item)
            out["raw_artifact_sha256"][role] = item["sha256"]
        if "arm" in bundle:
            # Diagnostic only: retain errors even in legacy/incomplete HOLD runs.
            rows = normalized_rows(bundle["arm"]["value"].get("rows"))
            out.update(observed_row_count=len(rows), task_error_count=sum(bool(r["error"]) for r in rows),
                       ordinary_pytest_exit_count=sum(r["test_exit_code"] in (0,1) for r in rows))
        need(not out["missing_artifact_roles"], "RAW_ARTIFACTS_MISSING")
        raw_bindings(plan, bundle)
        source_bindings(bundle["protocol"]["value"], sources)
        derived, transform = normalize(plan, bundle)
        out.update(transform)
        out["derived_artifact_sha256"] = {r:derived[r]["sha256"] for r in ROLES}
        out.update(xml_proof(bundle["capture"]["value"], planned, blobs))
        out.update(policy_clock(plan, bundle, sources, clock))
        need(gate is not None and getattr(gate, "_ADAPTER_PIN_VERIFIED", False) is True,
             "REVIEWED_R4_GATE_NOT_LOADED")
        result = gate.review(plan, derived)
        out["derived_gate_result"] = result
        out["derived_gate_checks_passed"] = result.get("native_route_checks_passed") is True
        need(out["derived_gate_checks_passed"], "DERIVED_R4_CHECKS_HOLD")
        out["status"] = "ADAPTED_CONSISTENCY_REVIEW_REQUIRED"
    except (Hold, KeyError, TypeError, ValueError, OverflowError, AttributeError, IndexError, RecursionError):
        error = sys.exc_info()[1]
        out["reason"] = str(error) if isinstance(error, Hold) else "INVALID_RECEIPT_STRUCTURE"
    return out


def read_bytes(path):
    need(type(path) in (str, Path) or isinstance(path, Path), "INPUT_PATH_INVALID")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES+1)
    need(len(raw) <= MAX_BYTES, "INPUT_BYTE_BOUND")
    return raw


def loaded_manifest(path):
    raw = read_bytes(path)
    manifest = parse(raw)
    need(set(manifest) == {"schema_version", "plan", "files", "source_files", "clock_file", "xml_files"}
         and type(manifest["schema_version"]) is int and manifest["schema_version"] == 1, "MANIFEST_SCHEMA")
    total = 0
    def read_spec(spec):
        nonlocal total
        need(type(spec) is dict and set(spec) == {"path", "sha256"}
             and type(spec["path"]) is str and 0 < len(spec["path"]) <= 4096
             and type(spec["sha256"]) is str and SHA.fullmatch(spec["sha256"]), "PINNED_FILE_SPEC")
        target = Path(spec["path"])
        if not target.is_absolute():
            target = Path(path).parent/target
        content = read_bytes(target)
        total += len(content)
        need(total <= MAX_TOTAL_BYTES, "MANIFEST_TOTAL_BYTE_BOUND")
        need(sha(content) == spec["sha256"], "MANIFEST_FILE_PIN_DRIFT")
        return content
    need(type(manifest["files"]) is dict and set(manifest["files"]).issubset(ROLES), "MANIFEST_ROLES")
    need(type(manifest["source_files"]) is dict and len(manifest["source_files"]) <= len(OFFICIAL_SOURCES+OWNED_SOURCES),
         "MANIFEST_SOURCE_BOUND")
    need(type(manifest["xml_files"]) is dict and len(manifest["xml_files"]) <= MAX_EVENTS, "MANIFEST_XML_BOUND")
    bundle = {role:pinned(read_spec(spec)) for role,spec in manifest["files"].items()}
    sources = {name:sha(read_spec(spec)) for name,spec in manifest["source_files"].items()}
    clock = None if manifest["clock_file"] is None else pinned(read_spec(manifest["clock_file"]))
    blobs = {key:read_spec(spec) for key,spec in manifest["xml_files"].items()}
    return manifest["plan"], bundle, sources, clock, blobs, sha(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan,bundle,sources,clock,blobs,manifest_sha = loaded_manifest(args.manifest)
        gate = gate_module(args.gate)
        report = examine(plan, bundle, sources=sources, clock=clock, blobs=blobs, gate=gate)
        report["manifest_sha256"] = manifest_sha
        report["reviewed_r4_sha256"] = R4_SHA256
    except (Hold, OSError, json.JSONDecodeError, UnicodeError, RecursionError, TypeError, ValueError):
        report = {"status": "HOLD", "reason": "MANIFEST_OR_REVIEWED_SOURCE_INVALID",
                  "adoption_status": "HOLD_NATIVE_ATTESTATION_REQUIRED", "submission_authorized": False,
                  "official_score": None, "native_authenticity_established": False,
                  "hidden_runtime_guaranteed": False, "derived_gate_checks_passed": False}
    print(json.dumps(report, sort_keys=True, allow_nan=False, indent=2))
    return 0 if report["status"] == "ADAPTED_CONSISTENCY_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    sys.exit(main())
