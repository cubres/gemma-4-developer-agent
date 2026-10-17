# Invented four-file ZIP contract illustrations

**Status:** a local publication candidate; no Kaggle or other dataset identity
has been created. **License:** MIT for this original synthetic material.
**Size:** eleven tiny ZIP cases, one producer manifest and a CSV index.

This is a deterministic teaching and regression-test collection for archive
provenance checks. Every payload was written for this packet: paper cranes,
color labels and simple bead sequences. No competition task, real issue,
upstream agent configuration, gold patch, benchmark answer, model output,
person or organization record is represented. The four filenames model a
public bundle layout; their contents are deliberately not runnable agent code.

| ZIP case | Expected outcome | Lesson |
| --- | --- | --- |
| valid_stored | PASS | Exact intended members |
| valid_deflated | PASS | Same members with another supported storage method |
| valid_timestamp | PASS | Member identity does not imply archive identity |
| changed_content | HASH_MISMATCH | Same-length content substitution |
| duplicate_name | DUPLICATE_MEMBER | Duplicate name replacing a required member |
| path_traversal | UNSAFE_PATH | A dot-dot path is rejected, never extracted |
| encrypted_flag | ENCRYPTED_MEMBER | Marked encryption is rejected; payload is invented plaintext |
| symlink_metadata | SYMLINK_MEMBER | Link metadata is rejected; no link is created |
| oversize_declaration | MEMBER_TOO_LARGE | A tiny archive declares an excessive decoded size |
| missing_member | MEMBER_SET | Omitted required member |
| forged_prefix | SIZE_MISMATCH | Actual DEFLATE stream contains an undeclared suffix |

The `expected` labels in `fixtures/cases.csv` are hand-specified contract
outcomes, not empirical agent-performance labels. This is not a representative
security benchmark and cannot estimate real failure rates or leaderboard
performance. It has no train/test split and should not be used to train a
model to solve competition tasks. It is useful for CI regression tests,
teaching artifact identity, and testing changes to a ZIP producer.

Reproduce with `python3 make_fixtures.py ./new-directory`; the destination must
not exist. Run `python3 -m unittest -v test_audit.py` to validate the generated
and checked-in bytes, expected rejection codes, stream bounds and optional
whole-archive pin. All examples fit the audit bounds; the oversize declaration
is intentionally inconsistent and does not contain a large payload. Inspect
them through the no-extraction auditor rather than treating them as agent
submissions. The generator has no network, notebook or publication behavior.

The separate `faithful_v10_*` JSON files are public provenance facts for a
real accepted native downloadable artifact, matching the previously retained
archive; they are not synthetic cases or new data.
The source recipe and its separate license are linked in the README. No private
accepted-row identifier, local path or captured response is part of this card.
