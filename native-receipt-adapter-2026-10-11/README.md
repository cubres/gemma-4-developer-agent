# Gemma receipt adapter

An evaluation can return a result object after a task fails. Its default status
can even be `SUCCESS`. Before comparing agent strategies, preserve those
failures, count every planned task, and check the evidence behind the test run.

This original, standard-library tool translates the saved Gemma result fields
`task_id` / `error_message` into the aliases expected by the separately reviewed
[R4 receipt gate](../native-receipt-gate-2026-10-11/README.md). It checks the
original receipt links **before** it derives anything. A conflicting alias, an
absent error field, missing actual XML bytes, or an unobserved policy clock keeps
the screen on HOLD.

![Original receipt and clock diagram](receipt-adapter.svg)

## What is measured

| Quantity | Evidence | Meaning |
|---|---|---|
| Result health | Explicit error field and final pytest exit | Caught errors count; ordinary executed-test exits are 0 or 1 |
| Final XML | Actual retained bytes at final pytest, cat and original verifier boundaries | Hash, size and exact byte equality, in the ordered invocation window |
| Policy time | Observed context start **and frozen end**, using `time.perf_counter` | Agent problem-solving session |
| Preparation | Wrapper start → observed policy start | Work before that session |
| Completion | Frozen policy end → wrapper finish | Work after that session, including patch extraction |
| Sandbox wall | Entire wrapped agent-sandbox call | Preparation + policy + completion; separate from the policy cap |
| Full gate coverage | Exact ordered planned list versus full gate list | A partial screen remains partial, even when its rows pass |

The collector never infers a zero policy duration from a missing start or end.
The adapter does not run pytest again or replace the original verifier. A failed
test with exit 1 and complete XML remains a real unresolved outcome. Exits 2–5,
negative exits, timeouts and missing final invocations fail the executed-test
health policy.

## Run locally

Use Python 3.10 or later and the separately published R4 checker. No third-party
Python dependencies are required.

```bash
python receipt_adapter.py \
  --gate ../native-receipt-gate-2026-10-11/screen_gate.py \
  --manifest private-manifest.json
```

The CLI reads the exact gate bytes, verifies their frozen SHA256, then compiles
those same bytes. It prints aggregate diagnostics and hashes. It does not write
files, contact Kaggle, import organizer modules, execute tasks, start compute,
change notebooks or authorize a submission. Exit 0 means internally consistent
derived receipts are ready for review; exit 2 means HOLD.

Every report retains `submission_authorized: false`, `official_score: null`,
`native_authenticity_established: false`, and `hidden_runtime_guaranteed: false`.
Even an internally consistent report has
`adoption_status: HOLD_NATIVE_ATTESTATION_REQUIRED`. File hashes demonstrate
consistency; a separately reviewed coordinator must establish native execution
and receipt provenance. The in-process Python gate object's marker is an API
precondition, not an authenticity credential.

## Manifest contract

Keep manifests and raw outputs private. The object has these exact top-level
keys: `schema_version`, `plan`, `files`, `source_files`, `clock_file`, `xml_files`.
The schema version is the integer 1. Each file specification has `path` and a
64-character lowercase `sha256`. Relative paths resolve beside the manifest.
Receipts' native capture paths are never used as local paths automatically.

| Key | Required contents |
|---|---|
| `plan` | R4 plan: ordered `task_ids`, ordered `full_gate_task_ids`, `repo`, `arm`, runtime assumptions, schema version 1 |
| `files` | Pinned `protocol`, `pilot`, `arm`, `capture`, `outer` raw JSON files; missing roles are diagnosable HOLD cases |
| `source_files` | Six frozen organizer source files plus `native_arm.py`, `private_junit_receipts.py`, `clock_collector.py`; names are listed in the adapter |
| `clock_file` | Pinned sidecar JSON, or `null` for a diagnostic HOLD |
| `xml_files` | Explicit local file mapping keyed as `event_index:capture_field` |

Runtime assumptions additionally require `policy_elapsed_max_seconds` and
`policy_sandbox_clock_tolerance_seconds` (at most one second). These are reviewed
external limits, not numbers inferred from test results. The original R4
`agent_sandbox_max_seconds` continues to bound the **entire sandbox wall**.

The sidecar has integer `schema_version: 1`, `raw_protocol_sha256`,
`raw_arm_sha256`, the exact observed `source_sha256` map, integer
`observer_errors: 0`, and ordered `records`. Each record comes from the passive
collector and has an actually observed `OBSERVED_FROZEN` state. Both the protocol
and local source hashes must match the frozen source contract; agreeing on an
unreviewed source hash is insufficient.

XML mapping fields are `junit_file_capture`, `actual_cat_stdout_capture`, and
`xml_input_capture`. Exit-zero windows need exactly one cat and original strict
validator. The validator has no observed task ID, so the adapter binds it through
the complete ordered invocation window and identical bytes. It does not invent
an ID for the verifier. Every declared capture size must be a positive integer,
match actual retained bytes and match its SHA256. The overall XML mapping must
have exactly the required entries.

## Passive collector adoption

`ClockCollector.wrap(original)` returns an async wrapper with the original
signature. The coordinator installs it at the reviewed agent-sandbox boundary;
it returns the exact original object or propagates the original exception. It
performs no I/O and records no task text, patch, model output or exception message.
Missing context marks, conflicting task aliases or observer failure remain
diagnostic evidence. Installation, restoration and sidecar persistence are
coordinator responsibilities; this package does not perform them.

The current unmodified arm does not produce this sidecar. Past receipts cannot be
upgraded by fabricating its fields. A future integration needs source review,
full receipt collection and independent native attestation. Any change to the
frozen organizer files, arm, recorder or collector requires a new contract review.

## Controls and evidence

```bash
RECEIPT_R4_GATE=../native-receipt-gate-2026-10-11/screen_gate.py \
  python -m unittest test_receipt_adapter.py -v
```

The retained author check used 46 invented unittest methods, including alias
conflicts, hidden caught errors, truncated timing errors, complete task order,
raw/embedded pin and JSON type drift, ordinary failed tests, pytest exits 2–5, actual XML byte
drift, missing clocks and source changes that agree with an unreviewed protocol.
Normal and optimized Python execution both passed. Five saved real receipt sets
were also read and quarantined: none had a complete modern arm, final capture
chain and observed policy-clock sidecar. Those classifications are local receipt
audits, not new native task runs or score improvements.

Only original tools, invented fixtures, explanation and the original diagram are
published. Raw receipts, task identifiers, task data, patches, organizer source,
private logs and native paths are excluded. See `SOURCE_BOUND_CONTRACT.md` and
`PROVENANCE.json` for the exact scope.

