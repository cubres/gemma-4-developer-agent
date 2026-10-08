# Next official draw: **A_think** (prepared and tested; NOT uploaded)

## Submit this file
`A_think90_submission.zip`, 3,739 bytes, SHA-256
**`2c737622b4c562d3c336505bf0edbcfcf1b1037bda875e0d9ebdeeed6f6038a6`**
(the same bytes as `dist/release_20261008T103154Z/submit/A_scout_submission.zip`).

Submission description (277 characters; row 6's description was 274 and was accepted):
```
A_think: scored A_scout d43f4706 (rows 56794711, 56859742) with one file changed: engineer thinking on (budget 4096), max_output 8192. Scout, prompts, 5min/100/160/90s unchanged. Predeclared thinking test. SHA256 2c737622b4c562d3c336505bf0edbcfcf1b1037bda875e0d9ebdeeed6f6038a6
```

**One paragraph for the ledger.** A_think is our already scored A_scout archive (d43f4706, drawn twice: 5 and 4 of 58) with
exactly one member replaced: `configs/sampling.yaml`. The engineer now reasons (`thinking_config: {thinking_budget: 4096,
include_thoughts: true}`) and gets an output cap of 8192 instead of 4096, so a full reasoning budget still leaves room for the
tool call. The scout sub-agent, both prompts, the six tools, temperature 0.2, top_p and top_k, and the eval budget (5 min /
100 calls / 160 turns / 90 s) are byte-identical. In the current organiser bridge, `include_thoughts: false` forces
`enable_thinking = False`, so every one of our five scored draws ran without reasoning. The public payload behind the 0.15–0.18
scorecards runs with it on. The only public ablation measured 48 vs 23 of 129 development tasks with reasoning on vs off. This
draw tests that single factor on the scorer.

## Predeclared hypothesis and reading rule
H: *Reasoning is the main lever our agent is missing.* Baseline: A_scout {5, 4} of 58, mean 4.5. The second concurrent arm is
row 56921186 (A_scout with a 240 s timeout, pending), which tests the timeout factor against the same baseline. Together they
form two single-factor contrasts around the best-replicated configuration.

| A_think public score | Reading |
|---|---|
| ≥ 0.12 (≥ 7 of 58, i.e. ≥ +2.5 over the baseline mean) | **Confirms.** Reasoning stays on in every later candidate. Next: the direct route with reasoning (D_budgetfit55 family, which V17 qualifies), then (240 s, on). |
| 0.08–0.10 (5–6) | Inconclusive: within one SD. One repeat draw before building on it. |
| ≤ 0.06 (≤ 4) | **Refutes** reasoning as the gap for the scout route at 5 min. Next: test the direct route (D) itself, which bundles the other family factors. |
| ERROR | Operational: reasoning broke the run (parser, 12 h, refusal). Inspect the error text; do not resubmit unchanged. |

Expected [I]: 6–9 of 58. A single draw cannot separate +1 from +3 tasks. Only the ≥ 7 band is decision-grade.

## Why this draw and not the others
- **A one-factor flip on the best-replicated configuration.** Every other option bundles changes. D_budgetfit55 changes about 7
  factors at once (prompt, scout removed, thinking, output, calls, turns, minutes), so a D score would not say *why*.
- **It does not depend on the pending row.** Its worst-case wall clock is identical to d43f4706, which finished twice. The time
  cap is a hard `asyncio.timeout` (I verified this in the fresh `agent_runner.py`), so slower reasoning cannot stretch a task past
  5 minutes. A variant stacked on the 240 s parent (`A_think240_alt_submission.zip`, 7d2d8e70…89c7, also fully tested) would
  inherit row 6's unresolved timeout risk and give no clean contrast until row 6 scores. Keep it as the follow-up (240 s, on).
- **The harness is built for this.** `agent_runner.py` excludes `thought` parts from text-only detection. In the scripted
  replay (below), reasoning parts sit next to function calls without costing a charged call or a text-only nudge. ADK history
  re-sends them. The compaction summariser reads them, but not tool output, so reasoning gives automatic post-compaction memory,
  much like our NOTE lines.
- Not chosen: a patch kit (B scored 3); a raised call cap (A already has 100 at 5 min, and the timer binds first); a stronger
  handoff or test-first prompt (prompt edits are the weakest-evidenced lever, and the family's prompt differs in many places).

## Known risks
1. A refusal is possible if prompt + 8192 > 32,768. The prompt ceiling is now 24,576, 10,240 above the compaction trigger. The
   public payload carries the same exposure and still scores [P].
2. Reasoning slows each engineer call, so fewer calls fit in 5 minutes. That is part of the factor being tested. The family uses
   8 minutes; a time change would be a separate draw.
3. The vLLM gemma4 reasoning parser plus tool parser with reasoning on is not exercised by a CPU test here. That path is what
   every public 0.15–0.18 run uses on the scorer [P], and V17 exercises it natively.

## Tests (all model-free; no GPU, network or Kaggle call)
Suite: the 72 tests of `candidate_20261002T1634Z`, copied into `tests/`, with 3 assertions in `test_bundle.py` adapted (engineer:
thinking on, budget 4096, output 8192, ceiling ≥ 10,000; scout still off) and **2 new replays** in `test_replay.py`: reasoning
parts with tool calls produce the patch and count 10 charged calls; reasoning reaches the compaction summary but tool output
does not. Total 74 distinct tests. The kit and install suites run under both Python 3.9 and 3.12.

| Build | Harness source | Receipt | Result |
|---|---|---|---|
| A_think90 (`release_20261008T103154Z`) | fresh 10-07 wheels (`codex_gemma_public_frontier_20261007/harness_*/src`) | `tests/receipts/20261008T103201Z/receipt.json` | all passed (40+40+6+6+8+8+12) |
| A_think90 | 10-02 v28 copy | `tests/receipts/20261008T103251Z/receipt.json` | all passed |
| A_think240_alt (`release_20261008T102624Z`) | fresh 10-07 | `tests/receipts/20261008T102947Z/receipt.json` | all passed |
| A_think240_alt | 10-02 v28 copy | `tests/receipts/20261008T102854Z/receipt.json` | all passed |

The official compiler (adk_submission 0.2.12) compiles both bundles. The engineer's request carries `enable_thinking: true` and
`thinking_token_budget: 4096`; the scout's carries `enable_thinking: false` and no budget.
ZIP contract (`ZIP_CONTRACT_RECEIPT.json`): CRC ok, sorted, files only, exactly one root `agent.yaml`, allowed suffixes, no
identity artefacts, and **the only member that differs from the parent is `configs/sampling.yaml`**. The builder reproduces
row 6's parent byte for byte (`parent_rebuild_check/REBUILD_CHECK.json`: 1ebbb3e7 rebuilt identical), so the build path is
faithful.

## Files
`A_think90_submission.zip` (submit), `A_think240_alt_submission.zip` (follow-up), `dist/` (the builder's releases, including
the unused B and screen sides), `src/` (only `configs/sampling.yaml` differs from `candidate_20261002T1634Z/src`; `eval_config.yaml`
was set to 240 for the alt build and back to 90), `tests/`, `zip_contract.py`, `reproduce_parent.py`. `CANDIDATE.md` is the
parent's 2 Oct text, copied unchanged; it describes A_scout and B_scout_kit, not A_think.
