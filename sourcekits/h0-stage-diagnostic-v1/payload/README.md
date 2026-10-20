# H0 stage observer — source only, no new attempt authorized

This separate input payload observes a future, separately admitted H0 run. It
does not modify or redistribute the original V1 kit. V34/native360225179 remains
ERROR/closed. No future dataset ID/version, certificate, notebook candidate or
GPU authorization is provided here. New code is Apache-2.0; see LICENSE/NOTICE.

`h0_stage_diagnostic.py` accepts the existing `--execute --bundle-root ...
--manifest-sha256 ... --certificate-json ...` invocation, and optionally the
original `--model-dir`/`--official-wheels` flags. It forwards argv unchanged to
the pinned original helper exactly once using isolated Python `-I -S`. The
current JSON-certificate invocation is supported; root-certificate file mode
is intentionally not an interface of this separate entrypoint. Original
certificate/schema/time/all11/resource/rights/source/once/cleanup predicates
remain enforced by the unchanged helper and core.

Before spawning, it checks the original V1 manifest/helper/core/serializer hashes
and source containment. It prints one fixed ASCII enum line <=80B. Original
helper stdout/stderr is suppressed; original private `/tmp` logs remain intact.
No paths, file values, exception messages, model/task text or raw logs are emitted.
The original helper return code is preserved, including self-signalling for a
signal termination. Observer failure cannot turn helper failure into success;
observer failure also does not turn an original helper success into H0 failure.
The existing `h0_public_receipt.json` and serializer/schema are untouched.

The original helper/core timers and native1050/core900 limits are unchanged.
Source-pin reads and the post-helper observer each have a one-second checked
budget. The observer caps each file by both its per-file bound and the remaining1MiB
budget before any read. It reads exactly the observed file size, without an
extra EOF-probe byte. It reads seven fixed files, with per-file
caps, no directory scan and no network. This is bounded local file inspection,
not a new timer or retry around the model helper; the native cap includes it.

Only this experiment's `/tmp/h0_private_<32hex>/private_output` is observed.
The outer work directory must be owned0700; child directories must be owned and
opened without following symlinks. Fixed leaf files must be owned, regular,
single-link, non-symlink, size-bounded and unchanged during reading. JSON must
be complete UTF-8 with no duplicate keys/nonfinite constants and the expected
top-level shape. Missing earlier milestones followed by a later one reject.
These checks do not claim full receipt-schema or model success validation.

| Original filename under private_output | Original creation point | Observer enum |
|---|---|---|
| `H0_ATTEMPT_CONSUMED.json` | Core supervisor: psutil/runtime summary, admission and exclusive output creation passed; before child start. | `CORE_ATTEMPT_FILE_PRESENT` |
| `MOUNTED_PUBLIC_WHEEL_INVENTORY.json` | Offline overlay extraction finished; inventory written. | `WHEEL_INVENTORY_PRESENT` |
| `ACTUAL_MODEL_MANIFEST.json` | Initial mounted-model file hashing finished; runtime capture has not necessarily finished. | `MODEL_MANIFEST_PRESENT` |
| `ACTUAL_RUNTIME_MANIFEST.json` | Nine-package critical/dist-info source capture, budget-processor presence and initial driver/CUDA observation finished. | `RUNTIME_MANIFEST_PRESENT` |
| `SERVER_CONFIGURATION.json` | Exact official sources/runtime/model/GPU inventory/config-command checks finished; before server Popen. | `SERVER_CONFIG_PRESENT` |
| `ACTUAL_WIRE_OBSERVATIONS.json` | Server became healthy with the expected alias, then the compiler probe's finally block wrote observations; the probe may have failed. | `WIRE_OBSERVATIONS_PRESENT` |
| `H0_CHILD_PASS.json` | Both actual compiler/tool/marker arms passed, before child server finally cleanup and supervisor acceptance. | `CHILD_PASS_FILE_PRESENT` |

No work/output/first milestone gives `NO_CORE_ATTEMPT_FILE`; unsafe, partial,
oversized or inconsistent inspection gives `OBSERVER_REJECTED`. Every enum means
only a parsed artifact was observed. It never replaces the unchanged positive
H0 receipt and independent exact-output/native/cleanup review.

Other original files remain private and are **not read by this observer**:
outer `ATTEMPT_CONSUMED.json` (before model start), `new_root_admission.json`,
`private_copy_provenance.json`, private source `core/`; output
`H0_TERMINAL_RECEIPT.json` (supervisor cleanup/result, including failures), fixture
`agent.yaml` files, and `private_bootstrap_child.log`/`private_child.log`/
`private_server.log`. A terminal receipt alone is not a progress milestone and
would mask the failing setup boundary, so it does not choose the diagnostic enum.

Production code contains no install, fetch, model patch, guard change, retry,
alternate path/profile or competition submission. Before any future use root
still needs the new human revised-attempt exception, real separate public-input
identity/version/hash qualification, all11 fresh checks, external once and an
exact reviewed notebook/metadata/installed-SDK source below1MB. Retain V1, V34,
all old attempts/certificates/history/art and every notebook identity.
