# E03 with the current V31 package profile: local mechanics passed

On 14 October, one local model-free check completed successfully using physically measured package archives from the published organizer wheelhouse version 31. Both the exact scored E01 control and E03 issue-contract candidate passed compiler and template checks with nine tool declarations. The [machine-readable result](CURRENT_V31_MECHANICS_RESULT.json) records the archive, package and evidence hashes.

| Check | E01 control | E03 treatment |
|---|---:|---:|
| Source archive bytes | 8,055 | 8,525 |
| Compiler and templates | PASS | PASS |
| Tool declaration count | 9 | 9 |
| Charged calls in the scripted loop | 5 | 5 |
| Scripted LLM calls | 9 | 9 |
| Target-model calls | 0 | 0 |

The paired invented routing produced the same patch hash in both arms: `4e73a2364a1ea685a8721e45ee69ed250de3cfeee9ecff395eeabd5a3bf94246`. Three invalid-input controls were rejected as expected. These observations check local mechanics; they measure no model decision, issue-contract adherence or task-repair quality.

The measured current profile uses **adk_submission 0.2.13**, **adk_eval_core 0.1.0** and **swegemma 0.2.11**. Package hashes distinguish the actual archives. Both arms retain an 8-minute budget, 28 charged calls and 80 turns. Command execution has a **240-second** timeout; current phase-2 verification has a separate **300-second** timeout.

**Native quality, hosted organizer ABI compatibility and the E03 official score remain unmeasured.** Full target-runtime dependencies were not qualified, and submission admission and scientific preregistration were not completed by this check. The [existing E01 submission 57111761, COMPLETE at 0.18](https://github.com/cubres/gemma-4-developer-agent/blob/e4e612afb6c25b0778d33134e368e3330aef2a2c/bfv5-coverage-2026-10-12/RESULT.md) remains a separate organizer evaluation.

This follow-up publishes original factual metadata only. Organizer source, tool descriptions, traces, resources, local paths and package binaries remain excluded. The existing experiment source, diagrams, artwork and notebook identities are unchanged.
