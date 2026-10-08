# V17 result (zz-gpuchk-861737 v17, 13:44:52 UTC): HOLD, caused by a canary-only server flag

Evidence: `v17_mine_20261008T140207Z/files/` (paced read-only fetch; plain fetches hit 429 on 8,000+ venv output files).

**Root cause (measured).** The arm ran. All 6 model requests got HTTP 400 from vLLM:
`ValueError: thinking_token_budget is set but reasoning_config is not configured. Please set --reasoning-config`
(`PRIVATE_vllm.log`). ADK retried 5 times. The task ended after 90.5 s with no model call, no patch and no final pytest, so the JUnit
capture is empty. Arm exit 1, then HOLD. The canary launched vLLM by hand without `--reasoning-config`. The organiser launcher
(`adk_submission/server.py`, `VllmConfig`) adds `--reasoning-config {"reasoning_start_str": "<|channel>", "reasoning_end_str": "<channel|>"}`
automatically when `reasoning_parser == "gemma4"`. So **the scorer is not affected**: A_think 56949760 and D are fine there,
consistent with the public reasoning payload's scores.

| Phase (T0 = first cell 13:45:11.4 UTC) | Measured | My estimate |
|---|---|---|
| Hashes incl. full 23.27 GB tensor | ends T0+193 (inventory 188.8 s) | 365 |
| Offline pip (75 s) + runtime probe | T0+193 → T0+346 (153 s) | 100–110 |
| vLLM TP4 eager launch → ready | T0+346 → T0+499 (153 s; weights 2.12 s from page cache, init 8.3 s, KV 64,720 tok) | 100–220 |
| **Ready, pre-arm total** | **T0+499** (gate T0+955, 456 s spare) | 575–695 |
| Arm: setup → first request → end | T0+551 first request; arm 141.8 s, exit 1; total 644.4 s; ≈ 0.425 quota-h at 2× | – |

Shown natively: tensor sha 1b9b1d62…; child-venv pins (vLLM 0.19.1, transformers 5.13.1, ADK 1.36.1, genai 2.11.0,
torch 2.10.0+cu128); 4×L4; served alias; wire carries `enable_thinking: true`, `thinking_token_budget: 4096`, seed and the 6 tools;
preservation passed; no surviving processes. **Not shown:** any reasoning-on generation, any parsed tool call, pytest/JUnit, latency.

## V18: **GO** with one required change
1. **Required:** add `"--reasoning-config", '{"reasoning_start_str": "<|channel>", "reasoning_end_str": "<channel|>"}'` to the vLLM command in
   `native_supervisor.py`. This is the organiser default byte for byte.
2. **Recommended:** compaction `EventsCompactionConfig(5, 2, 14336, 5)` at `run_gpu_validation_candidate.py:616` (scorer value). Move the
   runtime venv to `/kaggle/temp` so outputs stay fetchable.
3. Keep `rich_3772`, D v2 (641e23d4), budgets 1750/120/675/645 s (worst case ≈ T0+1175; quota ≈ 2,600 s); re-seal, re-check, one SaveKernel 1800 s.
