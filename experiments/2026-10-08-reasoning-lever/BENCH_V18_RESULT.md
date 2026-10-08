# V18 result (zz-gpuchk-861737 v18, pushed 14:37:33 UTC): the route works natively; the agent made no edit in 5.5 min, so HOLD

Evidence: `v18_mine_20261008T*/files/` (paced fetch, 10 pages). T0 = first cell. Total 885 s; 0.558 quota-h at 2×.

| Gate item (V17_LAUNCH_REVIEW / PLAN) | Measured | Verdict |
|---|---|---|
| 1 Clean run | Teardown clean. HOLD only from item 4 (arm exit 1: "no finalpytest invocation") | pass (process level) |
| 2 Reasoning on in every request | 15/15 requests carry `enable_thinking: true` and `thinking_token_budget: 4096`; vLLM 400s: **0** | **pass** |
| 3 ≥ 3 parsed tool calls with reasoning; no malformed or refusal | **13 tool calls**, all `finish_reason: tool_calls`, 0 malformed or unregistered. Compaction fired at 15,530 prompt tokens (5/2/14336/5); the next prompt was 6,640; no refusal | **pass** |
| 4 Non-empty diff + final pytest/JUnit | Session hit the 5.5-min cap (331.9 s) with **patch size 0**; no final pytest, so the JUnit capture is empty | **fail (not exercised)** |
| 5 Timing | Model calls: median **7.2 s**, p90 45 s, max 120 s. Decode ≈ **12 tok/s** under eager (1,437 tok / 120 s). Reasoning ≤ 4,842 chars (~1.2k tok), typical 30–570 chars; 4096 cap hit in **0/15** | pass (median < 25 s) |

Phases: weight hash 179.0 s · vLLM launch T0+~345 → ready **T0+500** (weights 2.11 s from cache, init 8.7 s) · first request T0+552.
Where the 5.5 min went:
- 5 reads, mostly whole files despite the 80-line rule.
- `write_file` of a /tmp repro script took **120 s** to generate and was then rejected ("Path traversal detected": write_file is confined to /workspace).
- A repro run errored, then 5 more reads/greps.
- One compaction summary took 58.6 s (the summariser also runs with reasoning on).
Three long generations used 224 of 332 s. That is a prompt/time problem, not a mechanics problem.

## Verdict for D-family official candidates: **GO on mechanics; no D ZIP promoted yet**
- By the predeclared rule (D blocked only if items 1–3 fail), D is unblocked. The scorer's own final verification already runs on every
  scored row. Item 4 failed on agent behaviour under eager decode (~12 tok/s) with a 5.5-min cap; the scorer's decode is faster [I].
- The arm did not pass, so I am not naming D v2 (641e23d4) as the first official D. Proposed **D v3** (not built yet; needs the 7 compiler tests + sha):
  - D v2 with `max_time_minutes: 8`, an integer equal to the public payload's scored value. That payload, also capped at 28 calls, finished within 12 h on the scorer.
  - Remove the operations-only "notebook identity" line.
  - Add one prompt sentence: no reproduction script before the first source edit; scratch files only via `run_command` into /tmp, never `write_file`.
  - Everything else byte-identical. Bundled change, labelled as such.
- 12 h risk: overruns only if most tasks hit the 8-min cap; relies on the 28-call cap binding first, as for the public payload [P].
- Decision tree: D v3 enters on **refute**, or after A_think240 on **confirm**. Optional V19 canary: arm cap 795 s, reserve 825 s (ready T0+500 fits).
