# Why field normalization needs evidence

The retained organizer result model stores `task_id` and `error_message` as
fields. `instance_id` and `error` are compatibility properties. The protected
evaluation helper serializes result models, so the saved rows use the stored
field names. Status and exit-code defaults alone do not prove execution health.

The adapter checks explicit field presence and rejects conflicting aliases. It
keeps the real error value in the private derived gate input. Public reports show
the error count and fixed diagnostic codes, never the error text. It excludes
opaque patch, trace, metadata and test-output payloads from the derived row view.

The current owned arm truncates its timing error string to 300 characters and
stores a falsey error as `null`. The adapter permits only this exact source-bound
transform, then expands the timing alias to the preserved raw result error for
the R4 equality check. This does not erase an error or turn a failed result into a
healthy one. A mismatching prefix is HOLD.

## Frozen boundaries

| Source | Contract under review |
|---|---|
| `adk_eval_core/models/base.py` | Stored result fields and compatibility aliases |
| `swegemma/models/task.py` | TaskResult subclass and alias/default handling |
| `swegemma/evaluate.py` | Caught task errors and agent-sandbox call boundary |
| `swegemma/context.py` | Policy start, frozen end, elapsed-time property |
| `swegemma/harness/agent_runner.py` | Policy marks inside setup and extraction boundaries |
| `swegemma/harness/verification.py` | Actual pytest/cat/original strict-verifier route |
| `native_arm.py` | Whole sandbox timing and timing-error truncation |
| `private_junit_receipts.py` | Retained capture shapes and event ordering |
| `clock_collector.py` | Original passive observation of frozen policy marks |

SHA256 constants in the adapter freeze these exact boundary sources. The CLI
hashes the explicitly supplied local files, compares the protocol's hashes, then
requires the reviewed constants too. This is source consistency, not proof that
those sources ran remotely. Updating a protocol and file together does not grant
admission for unreviewed code.

## Raw versus derived hashes

The original JSON bytes, SHA256 and parsed object are checked together using
canonical type-preserving JSON; boolean/integer or integer/float drift is HOLD.
Raw pilot
→ protocol, pilot → arm, arm → capture, embedded capture and embedded raw rows
must agree before normalization. The adapter preserves every original artifact
pin in its report.

Derived rows use the compatibility aliases. Derived embedded links are then
recomputed using canonical normalized JSON. Their hashes are labelled as derived
and never presented as hashes of native receipt bytes. This allows the reviewed
R4 checker to compare the normalized contract while the adapter retains the raw
binding chain separately.

## What remains unproven

This tool establishes neither native authenticity nor hidden-task generalization.
Policy clocks need an actual future sidecar; XML needs the actual retained files;
partial screens need the full ordered task gate. The declared worst-case runtime
projection can still exceed the session limit even when a measured screen passes.
No result here authorizes a competition submission or supports an official score
claim.

