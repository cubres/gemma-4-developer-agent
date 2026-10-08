# V22 = V21 r3 (byte-identical notebook, sha b1232319…27ee) + pin metric/gemma-4-developer-agent-wheelhouse to version 25

Diagnosis (V21 ERROR 11:02 UTC, cell 15 / In[9]):
- V21 vs V20 inputs: base-package, pip-base and duplicate inventories IDENTICAL (same pinned docker image); runtime-overlay-constraints.txt IDENTICAL;
  available wheels 211 vs 211, the ONLY difference is in /kaggle/input/private-dataset (= metric/gemma-4-developer-agent-wheelhouse):
  adk_submission-0.2.11 (V20) -> adk_submission-0.2.12 (V21). The cell requests and constrains adk-submission==0.2.11 -> ResolutionImpossible.
- Dataset version list (wheelhouse_versions/): v21-v25 ship adk_submission-0.2.11 (v25 created 2026-09-27 11:49); v26 (09-30 19:08), v27, v28 (current) ship 0.2.12.
  V20 ran 09-30 16:01 (session 354188735), before v26 existed, so V20 mounted v25. v25's 41 wheel names == V20's mount exactly; v28 == V21's mount
  (wheelhouse_versions/MOUNT_MATCH_v25_v28.json). The competition-mounted wheels and our reproducibility wheels did not change.
Fix: dataset_sources "metric/gemma-4-developer-agent-wheelhouse/25" (SDK accepts owner/slug/version; versioned sources were accepted by the server in earlier
Knee/Enveda pushes). No notebook code change. Consequence: the compiler check reproduces V20's 0.2.11 environment, not the scorer's current 0.2.12 (state this in V23 prose).
Checks: all 16 code cells parse; cell sources == server V21; ledger block ran twice standalone; safe_push dry run DRY_RUN_OK (../public_v22_dryrun_20261008T110932Z/):
identity equal, only dataset_sources differs from server, is_private False. Server status before push: ERROR (V21), not RUNNING/QUEUED.
Residual risk: if the server ignores the version suffix, V22 fails identically within ~45 s; then fall back to code path B (pin 0.2.12 in cell 15).
