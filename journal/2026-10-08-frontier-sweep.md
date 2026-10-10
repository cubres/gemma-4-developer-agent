# Frontier sweep, 8 October 2026

A read-only sweep of the public frontier for the Gemma 4 Developer Agent competition, run from 14:40 to 15:40 UTC on 2026-10-08. Nothing on Kaggle was changed. The sweep read public notebooks, the discussion forum, dataset metadata and the scorer's pinned harness packages. The packages were read in place and not executed. Labels are defined in the [README](README.md).

## Bottom line

1. No public write-up explains the top score. The top account (0.24 on the day) had no public Gemma notebook, and its only kernel dated from 2023 [V]. Three other teams in the top five had no public kernels [V].
2. The public frontier at 0.15 to 0.18 is one payload. Budget-Fit Single Agent V5 (0.18), Calibrated Sin V1 (0.17), Ultimate Duo V3 (0.15) and SuperAgent (run on 10-08) carry the same main files, and their hashes match [V]. The settings are one agent with thinking on (budget 4096, thoughts included), output 8192, temperature 0.2, 28 tool calls, 8 minutes, 80 turns, a 240-second command timeout, nine tools declared, and a prompt that forbids the three graph tools [V].
3. Our five scored draws were 5, 4, 5, 4 and 3 of 58, all with thinking off [V]. The family payload's three public draws were 11, 10 and 9 of 58 [V, from a UI reading on 10-07].
4. Two failure paths in our payloads are absent from the family payload. An advertised but undeclared graph call ends the task with an empty patch. Context overflow ends the task with an empty patch, even after submit. Both were read from the harness source [V].
5. Thinking is the largest measured lever in the public dev data: 23 of 129 dev tasks solved with thinking off, 48 with it on [P, one author's ablation].

## 1. Our position

| Quantity | Value | Label |
|---|---|---|
| Scored draws | 5, 4, 5, 4, 3 of 58 (mean 4.2; best 0.08) | [V] |
| Pending at the sweep | one thinking-on row (row 56949760); see the state report | [V] |
| Family payload, three public draws | 11, 10, 9 of 58 | [V, UI reading] |
| Leaderboard, top 20 (14:42 UTC) | 0.24 once; 0.18 four times; 0.17 from rank 6 | [V] |
| Leaderboard blocks (10:06 UTC) | 1989 teams; 122 at 0.15 or above; our rank 1116 | [V] |
| Gap to family mean / to leader | 5.8 tasks (0.10) / 9 tasks (0.16) | [V, arithmetic] |
| Draw noise | identical ZIPs: ours 5 and 4 (two uploads); one public baseline's identical ZIP 0.12, 0.10 and 0.06; family 11, 10, 9; a repeated local config 55 vs 48 of 129 | [V] and [P] |

Compared with the family payload, the thinking-on draft differed in five ways [V, from the ZIP contents and the harness source]. Thinking was on in the engineer only. The command and final-verification timeout was 90 seconds, against 240. The budget was 100 calls and 5 minutes, against 28 calls and 8 minutes. It had a scout sub-agent. Its graph tools were not declared, although the harness still advertised them.

## 2. Public write-ups as the sweep recorded them

Scores are as displayed on 2026-10-07 and 10-08, or as the author stated them. Scores marked [P] are author claims.

| Notebook (slug) | Score | What it is | Label |
|---|---|---|---|
| verracodeguacas/gemma-4-agent-budget-fit-single-agent (V5) | 0.18 | Family payload; Apache-2.0 on the UI reading | [V] |
| Calibrated Sin, lavinwins (V1 scored, V2 now) | 0.17 (V1) | Family payload; V2 prompt hash equals the family prompt | [V] |
| matterhorn3838/gemma-gemini-the-ultimate-duo (V3) | 0.15 | Family payload despite the "Duo" name | [V] |
| matterhorn3838/gemma-4-superagent (run 10-08) | not shown | Byte-identical main files to Ultimate Duo V3 | [V] |
| lucifer19/black-cat-swe-agent-pack-instinct | 0.12 (anchor) | Coder plus analyzer; 5 minutes, 100 calls | [P] |
| romanrozen/gemma-eda-baseline-for-a-start-lb-top-1 | 0.12 (author); 0.10 and 0.06 for identical ZIPs | Coder plus analyzer; thinking off; no evaluation caps | [P] |
| hsiaosuan/gemma-developer-agent-0-13-submission | 0.13 | Explore then coder; thinking off; 5 minutes, 60 calls | [P] |
| hitarthjain0/gemma-4-apex-budget-fit-single-agent | not shown | Family without graph tools; 6.5 minutes; a public-repo hotspot map | [V] source |
| honghanhhh/gemma-4-baseline-lb-0-24 | not shown | "0.24" in the title is the leader's score, not its own | [V] |
| hanifnoerrofiq/patchsmith | not shown | Thinking 2048, output 6144; 5 minutes, 32 calls | [V] source |
| kaitofukami/gemma4-agent-v8-shell | not shown | Shell-only tools; thinking 512; 4 minutes | [V] source |
| nihilisticneuralnet notebook | 0.10 | Localizer and verifier sub-agents; thinking off | [P] |
| flexonafft notebook (v2) | 0.10 | Thinking on; 4 minutes; bounded test-feedback loop | [P] |
| dmitriigluzdov measure-before-you-tune | 0.06 (v4), 0.08 (C1B) | Measurement study; a LoRA trial was a NO-GO | [P] |

The leader's account had no public Gemma notebook [V]. None of the top eight notebooks attached a dataset, model or kernel; each embedded its payload as strings [V]. Licences are not exposed by the API. The Apache-2.0 licence of the family payload was seen only in a UI reading [V].

## 3. Harness facts checked in source

These were read from the scorer's pinned harness wheel and the agent framework wheel. They were not executed.

- Budget stops are soft. The session-time, tool-call and turn limits each break the loop. The harness then falls back to the working-tree diff against the baseline. A run with edits on disk and no submit still produces a patch [V].
- Generic exceptions return an empty patch, even after submit. The patch is read from the submission only inside the main try block. Context-window overflow is the main case [V].
- The harness nudges after at most three consecutive text-only turns [V].
- The task message advertises the three graph tools whenever graph and embedding data exist. The agent framework raises an error on an undeclared tool, and the task ends with an empty patch [V].
- The search-similar-code tool returns each matched node's full code body, with no character cap in this harness version. The five-thousand-character cap applies to the shell tool only [V]. A later host post says an output cap is planned [P]. The sweep first recorded it as in place; the verifier found it promised but not confirmed [V].
- The compaction summariser keeps every message part that has text. Reasoning parts carry text, so reasoning reaches the summary. Function calls and function results are dropped [V, agent framework source].

## 4. Discussion evidence

Host statements [P, host]:

- Topic 743063: the scorer reads only the timeout, the call cap, the time cap and the turn cap. A 12-hour overrun errors the whole submission. A plan to score unfinished tasks as zero was under reconsideration on 10-07 and was not deployed.
- Topic 745805: the 12 hours include vLLM startup. Verification should not time out.
- Topic 746008: every submission runs both the public and the private task sets, so a public score means both finished.
- Topic 744354 and related posts: thought retention, double-encoded tool output, thinking-budget forwarding and LoRA cache handling were fixed in the 09-30 wheelhouse. Old submissions were not rescored.
- Topic 745028: a call to an undeclared tool ends the task. The host said a fix would be implemented. Deployment was not confirmed.
- Topic 745059: with include-thoughts false, thinking is off, and a thinking budget above zero needs the serving reasoning config.

Measured community evidence [P]:

- Topic 746250 (a participant's dev sweep, 129 tasks): thinking off 23, thinking on 48; thought summaries off 35, on 51; temperature 0.0 47, 0.2 48, 0.4 51, 1.0 51; budget 2048 50, 4096 48, 6144 48; calls 25 gives 36 and 50 gives 50; an analyzer sub-agent +1; time caps of 6, 10 and 15 minutes give 37, 46 and 54 with 61, 26 and 3 session timeouts; a repeat of one config gives 55 vs 48. The author reported Kaggle calibration at 8.68 seconds per call with thinking on. The call-cap and quality comparisons ran at a 15- or 60-minute active cap, not the submission's 8-minute cap.
- Topic 747168 (a participant, 124 tasks): two passes gave 54 and 53, and 15 percent of tasks flipped between identical passes. The same post reports that a tool-parser issue retried edit calls up to 27 times.
- Topic 745774: identical commands were repeated up to 69 times in one task, so prompt rules did not stop loops.
- Topics 743683 and 746480: many "A system error" results after about 15 hours, on 10-06 and 10-07, including short config-only bundles. Platform-side is an inference.
- Topics 747186, 744692 and 745977: compaction at 14,336 tokens with interval 5, overlap 2 and retention 5. Overflow discards edits.
- Topics 743213 and 746503: LoRA adapters are accepted. A rank-16 adapter ran out of memory at scorer warmup. No public LoRA had a published score above the family.
- Topic 745855 (a participant): six of 129 public tasks are unwinnable. Topic 743506: the public board has exactly 58 tasks.

## 5. Claims checked, refuted or corrected

| Claim in the sweep or its inputs | Outcome | Label |
|---|---|---|
| Four top notebooks share one payload | Confirmed; their main files match by hash | [V] |
| Our thinking-on draft is not the family configuration | Confirmed (100 calls, 5 minutes, 160 turns, scout sub-agent) | [V] |
| Our D v3 build uses 8 minutes; the plan text says 5 or 6 | Conflict found; the plan's text was left as written and later builds used 8 | [V] |
| NOTE lines survive compaction (A_scout description) | Not supported by the wire data: visible text was empty in 7 of 7 tool-call turns. The summariser also reads reasoning, so that measure is the wrong channel | [V] |
| About 12 percent overflow at the 14,336 threshold | A single poster's pre-fix local runs. The example cited for after the fix is a separate post | [P], label corrected |
| Search output is now capped | A host promise, not confirmed in the snapshot | [P] |
| "The 12 hours cover all about 120 tasks" was a host statement | It was a participant's post; the host confirmed full evaluation at submission time | [P], attribution corrected |
| Sweep language implying that submission timing matters for budget stops | Budget stops keep the working-tree diff; submission timing matters only as overflow insurance | [V] |
| Leader at 0.24 explained by a public notebook | Not found | [V] |

The plan records the sweep's lever verdicts (section 6 below). The adversarial verification file named in the sweep was never written to disk. The verdicts exist only in the plan and in the sweep's working notes. The sweep noted that the local decode path is eager and so slower than the scorer's. That is a caveat, not a measurement [V].

## 6. Plan verdicts on the sweep's levers (10-08)

- Kept: thinking on (the A_think row, pending at the time); the eight-minute cap with 28 calls, in the D v3 build; declaring the three graph tools and forbidding them in the prompt (D v4); a smaller thinking budget and output cap (2048 and 6144) as a separate arm (later shelved, see the strategy report); a single agent on the family budget; the 240-second timeout.
- Refuted: extra edit-robustness prompt rules, since D v3 already covers them and the heredoc rule adds corruption risk; pointing the public notebook at a payload before the payload confirms; a LoRA or SFT adapter, on weak evidence and cost.
- Missing from the sweep's list: the family payload used verbatim as a control (not planned); a call cap of 36 to 40 under the eight-minute cap (estimated at 1.8 GPU-hours of canary); temperature changes (treated as noise).

## 7. Gaps

- The adversarial verification document named in the sweep does not exist on disk. The sweep's notes say it was intentionally not written as a file.
- Several forum claims are first posts only. Host replies were not in the snapshot and were not re-read, so host claims stay [P].
- The sweep's time-cap and call-cap evidence was produced at 15 or 60 minutes, not 8 minutes. Those gains do not transfer to the submission's cap without a test.
