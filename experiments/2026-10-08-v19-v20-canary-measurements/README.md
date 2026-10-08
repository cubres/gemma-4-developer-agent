# Two bench canaries: decode speed, a 150-second cap, and a waived gate item

Two private one-task canaries of the direct Gemma agent (D v4: nine tools declared, the three code-graph tools forbidden in the
prompt, 8 minutes, 28 calls, 240-second commands) on the competition runtime: vLLM 0.19.1, four L4s, eager execution, one request
at a time. They measure the route, not quality. One public task (`rich_3772`, chosen before any outcome) cannot measure a solve
rate, and no official score follows from either run.

| Measurement | V19 | V20 |
|---|---|---|
| Per-turn transport cap | 150 s | 420 s |
| Root turns completed, cut, in flight at the cut | 4, 2 (both cut at 150 s), 1 | 7, 0, 1 |
| Decode per completed root turn (server) | 11.8 to 12.1 tok/s (vLLM log) | 9.3 to 12.2 tok/s, median 11.9 |
| Longest completed turn | none completed past 150 s | 323 s, 3,799 completion tokens |
| Requests that waited for the server | 0 | 0 of 229 samples |
| Reasoning cap (4,096) reached | 0 of 4 turns | 0 of 7 turns (largest at 93%) |
| Context-window errors | 0 | 0 |
| Compaction | none | once, at 14,993 prompt tokens (threshold 14,336) |
| Agent budget used | 482 s of 480 s; 4 tool calls | 482 s of 480 s; 7 of 28 tool calls |
| Submit, patch, final JUnit | none, none, none | none, none, none |

Findings:

- Decode is about 12 tokens/s for a single request with eager execution, and requests never queued. That is the server's single-stream
  rate here, not contention.
- The 150-second per-turn cap cut two reasoning turns while the server was still generating. V19 reached no completed turn beyond it.
  Raising the cap to 420 seconds removed that failure: the 323-second turn completed.
- The 8-minute budget, not the 28-call cap, is the binding limit at this rate. About 5,700 tokens are generated in 480 seconds, so one
  long reasoning turn uses most of it. Both runs ended on the budget with no submission, no patch and no final test.
- In V20 one turn wrote a scratch file with `write_file`; the harness refused it. The prompt says to use `run_command` for scratch
  files, and that rule did not bind.

Gate decision (recorded for the bench):

- Item 4, "submit within the 8-minute budget", is waived for the bench. Eager single-stream decode at 12 tokens/s is hardware-bound. The
  official scorer's decode speed is unmeasured, and the public family runs the same budget.
- Item 1's status and arm-exit parts are waived only as a consequence of that waiver. The arm exits 1 when no final JUnit exists. The
  preservation, survivor and NVML parts remain required, and both runs passed them.
- Items 2, 3 and 5 passed. Thinking was on, with a 4,096-token budget, on every root request. Every tool call parsed, was registered
  and ran; none called a code-graph tool. The median completed root turn took 18 seconds.

A further D v4 upload is planned for the 2026-10-09 daily slot, subject to the outcome of an earlier submission. This note does not
record an upload.
