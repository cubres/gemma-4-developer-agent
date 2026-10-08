# V21 canary design, the 10-09 D v4 decision, and the held payload variants

Written 2026-10-08 (UTC). Design and decisions only. V21 is built and tested offline. It has not been pushed or run, and this note
records no upload.

## V21: non-eager official-speed calibration canary (built, not run)

Purpose: the serving-fidelity gate (L4). The V19 and V20 canaries ran eager, with 512 batched tokens and one sequence, so their decode
speed may not match the official scorer. V21 removes those settings.

| Item | V21 | Basis |
|---|---|---|
| Serving flags | No enforce-eager; CUDA graphs on; default batched tokens; GPU memory utilisation 0.90; tensor parallel 4; thinking on with the reasoning config (4,096 budget). LoRA flags left out | organiser `build_cmd`; no adapters in use |
| Phase A (no tools, before any tool call) | Replay of the seven V20 root-request shapes: prompts 3,612 to 14,993 tokens, completions 55 to 3,799 (4,723 tokens in total). Temperature 0.2, top_p 0.95, top_k 40. Decode tokens/s, first-token latency and KV use recorded per request | V20 request ledger; D v4 sampling file |
| Phase B | D v4 arm, 420 s per-turn transport cap, per-call capture, 8-minute budget | as V20 |
| Timeout | 2,400 s server timeout | cold worst case 2,287 s from push (113 s slack); warm 2,123 s |
| Quota | 4,800 quota-s reserved (2 x 2,400 s); 4,444 cold worst, 4,116 warm | the 2x rule |
| Bootstrap | Offloaded to a private dataset (63,627 B), pinned by sha256 in the loader. The loader resolves either mount layout and writes a listing of the input directory to its receipt before it runs anything | notebook size |
| Notebook wire size | 1,036,045 B with the dataset source in the push body | the V20 head measures 1,036,069 B exactly with the same serializer |
| Embedded alternative | 1,099,343 B | over 1 MiB (1,048,576 B); not pushable |
| Tests | 22 of 22 offline tests pass | |
| Dry run | `safe_push` dry run: DRY_RUN_OK, `is_private` true | |

Why offload: the V20 notebook is already at 1,036,069 B, the largest size accepted so far and close to the 1 MiB limit. Embedding the
bootstrap would add about 63 KB.

Timing: scheduled after the Saturday quota reset (2026-10-10 00:00 UTC). Nothing runs before then.

Still estimates until measured: the CUDA graph allowance (90 s), and the chat-template overhead used to size the phase A prompts. The
phase A prompts are synthetic text of the logged length, not the V20 text.

Not yet checked: the sha256 of the dataset file as stored on the server. The file listing returns only the name and size, which match
the pin (63,627 B). The hash needs a download of the file.

## 10-09 official upload: D v4 under guards

Decision (recorded in the PLAN at 17:25 UTC on 2026-10-08): the 10-09 official upload is D v4, instead of A240.

- Payload: D v4 ZIP, sha256 `b54331170e0b9b885c651eac50d62715166e1c1ade2122da45db8535b1391549`, 2,465 bytes, uploaded as `submission.zip`.
- Family budget: 8 minutes, 28 tool calls, 240 s command timeout. Nine tools declared. The three code-graph tools are declared, and the
  prompt forbids them.
- Hold rule: if row 56949760 (A_think) is an ERROR whose text points at thinking (refusal, overrun or compile), the upload is held and
  the coordinator is told. The standard system-error text does not hold it.
- Guards (`submit_d_v4.py`): local guards G1 to G3 (file name, sha, size, ZIP contract, description carries the sha). Live guards G4 to
  G7 (expected row count, one Gemma row per UTC day, sha not already in a description, row 56949760 check). Offline guard tests pass
  16 of 16. The dry check makes no network call.
- Known difference: D v4 sampling sets top_k 40, and the family's sampling sets none. The 10-09 draw is therefore not a prompt-only
  comparison. The next arm removes top_k.

Measurements behind the decision (V20, same packet, one private task):

- The 4,096 reasoning cap was never reached; the largest turn used 93% of it.
- Overflow count 0. One compaction, at 14,993 prompt tokens.
- The prompt rule to use `run_command` for scratch files did not bind: one `write_file` call was refused by the harness.
- The NOTE-line rule was not complied with in V19 or V20.

The upload is the coordinator's action on 10-09 UTC. This note does not record an upload or its result.

## Held payload variants and their gates

All variants derive from D v4 and are held. Gains are the strategy sweep's labels; [I] marks an inference.

| Variant | Change from D v4 | Gate (strategy sweep) | Expected gain |
|---|---|---|---|
| D v4h | Thinking budget 2,048, max output 6,144 (sampling file only). ZIP sha `34bd49c2e807944efeaca961a4a63bb132784d8f3893ef6ab54c4f1229a7124d`; 7 of 7 contract tests pass | The L4 official-speed canary passes first (L4 is named as the gate for L2). Runs after the reset. Second arm, after D v4 as control | 0 to +1, central +0.5 [I] |
| D v4k | D v4 minus top_k, plus a new guard file | None stated. The submit script is not edited before the 00:02 UTC run ends. Arm B on alternate days from 10-10 | Sign unknown; small [I] |
| D v5a | D v4k base, max tool calls 30, guard edits | Mean per-call gate of 9.8 s. The L3 notes gate 32 calls at 10 s per call; the strategy says 30. To be reconciled before the build | +0.5 central, 0 to +1.5 [I] |
| D v4y | D v4k base, thinking budget 2,048, max output 8,192 | Enforcement probe and canary both pass. The probe is named but not defined in the notes | 0 central, 0 to +0.5 [I] |
| D v4x | D v4k base, max output 6,144 | No gain unless the overflow trigger fires (prompt above 24,576 tokens, or a context error) | 0 unless triggered |

Not recorded here: the strategy sweep also names a V21 revision (r7) with per-call timing and a mean gate. That revision is not built
in the record this note describes.
