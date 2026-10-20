# E07 source kit: final-edit verification and six tools

This Apache-2.0 source kit describes a new, unmeasured policy combination. Its
graded bundle uses the exact completed E06 `agent.yaml` (six tools) and the
other three exact completed E05 members, including the final-edit verification
prompt. Only three graph-tool declaration lines differ from E05. No model,
endpoint, H0 helper, wheels, task data, gold patch or private trace is included.

The flat source files map to exactly four graded ZIP members:

| Source file | Graded member |
|---|---|
| agent.yaml | agent.yaml |
| sampling.yaml | configs/sampling.yaml |
| eval_config.yaml | eval_config.yaml |
| system.md | prompts/system.md |

`e07_cpu_packager.py` uses Python's standard library. Before constructing an
archive, it rejects an unexpected source-member set, symlinks, nonregular or
oversized files, wrong lengths and wrong SHA256 values for every other kit
member. The notebook separately pins this entrypoint's exact length/hash.
ZIP members use sorted names, the fixed1980 timestamp, DEFLATE, and regular
0644 attributes. No wall time, source path or environment value enters the
ZIP. Compression bytes are qualified in the actual canary/native environment;
the future completed native ZIP must be independently checked.

CLI execution writes only the new root files `/kaggle/working/submission.zip`
and `/kaggle/working/e07_public_contract.json`, with exclusive creation and
readback. Existing outputs are never overwritten. The public contract is at
most4096 bytes and contains only fixed experiment/status text, graded-member
lengths/hashes, output length/hash and producer scope. It measures packaging,
not agent adherence, task success or leaderboard improvement.

The public `build(source_root, output_root)` function supports a separately
admitted CPU fixture canary in a new directory. Neither importing the module
nor a source manifest grants execution or submission authority. Actual CLI
execution requires `--package-only`; it is not a launch gate or certificate.

Historical own official results were E05 .18 (V32/native359522074,
row57329048) and E06 .17 (V33/native359872054,row57374841), separate unpaired
draws. The credited upstream V10/native357955943 displayed .22 in the retained
19October2026 native observation. Those scores are not a result for E07 and
do not establish a causal policy effect. Retain the full LICENSE and NOTICE.

Intended future input ref: `prvsiyan/gemma-e07-verification-six-tools`.
At this immutable source-build stage it is UNPUBLISHED: no actual Kaggle ID,
version, mount, availability or public-byte receipt is claimed. Publication
and later qualification belong in a separate root receipt, without backfilling
this build-time statement. The proposed notebook has an unconditional stop.
Root must qualify public input bytes/ID/version, prepare the exact final
candidate and SDK review, and refresh every applicable admission gate before
any CPU commit or native-menu official submission. Closed H0 attempts stay
closed; this kit cannot authorize their recovery or waive their gates.
