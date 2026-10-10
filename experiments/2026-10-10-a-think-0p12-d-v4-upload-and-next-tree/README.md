# A_think public 0.12, the D v4 upload, and the 10-11 decision tree

Written 2026-10-10 (UTC). Measurements and decisions only. The V21 calibration canary has not run; its launch attempt failed (below).

## Measurements

| Row | Submitted (UTC) | Payload | Public score | Status |
|---|---|---|---|---|
| 56794711 | 2026-10-03 09:28 | A_scout: read-only scout first; 5 min, 100 calls | 0.08 | COMPLETE |
| 56859742 | 2026-10-05 18:50 | A_scout, exact control repeat (same ZIP) | 0.06 | COMPLETE |
| 56949760 | 2026-10-08 10:44 | A_think: A_scout with one file changed, thinking on (budget 4,096, max output 8,192); 5 min, 100 calls | 0.12 (7 of 58) | COMPLETE |
| 57039340 | 2026-10-10 10:17 | D v4: 8 min, 28 calls, 80 turns, 240 s; thinking 4,096; max output 8,192; nine tools declared, code-graph tools forbidden in the prompt | none yet | pending (no status field) |

Findings:

- Thinking on scored 0.12 against 0.08 for the A_scout row, +2 tasks. It is +3 against the same-ZIP repeat (0.06). The repeat moved by
  0.02 on an identical ZIP, about one task, so the thinking difference sits inside run-to-run variation.
- The D v4 row is pending, so there is no D v4 score in this note.

## Decisions

1. **D v4 is the official draw for this slot.** The guarded submit script submitted it on 2026-10-10 at 10:17 UTC, one day after the
   planned 10-09 slot. Payload: D v4 ZIP, sha256 `b54331170e0b9b885c651eac50d62715166e1c1ade2122da45db8535b1391549`, 2,465 bytes,
   uploaded as `submission.zip`. Its description carries the same sha.
2. **The V21 canary is not running.** Its launch attempt at 10:18 UTC failed before any Kaggle call: the launcher pointed at the
   notebook one folder above where it is stored. The runner still logged the step as exit 0, and the ledger line said "launching".
   Both records are wrong. No GPU quota was used. A relaunch is needed before the canary's speed reading exists.
3. **The public notebook is being rebuilt separately today** so that it builds the D v4 ZIP inside the notebook and can be submitted
   from its output. This note did not touch the public notebook packaging.

## Decision tree for 10-11 (keyed to the D v4 public score, row 57039340)

- **Score 0.14 or higher:** the D v5a call-cap arm is the next candidate, after the canary's speed reading. D v5a is D v4k with a
  lower call cap and the guard edits. Its gate is the mean per-call time of 9.8 s from the strategy sweep.
- **Score 0.10 or lower:** return to the A_think variants.
- **Score 0.11 to 0.13:** not covered by this tree. No arm is chosen.
- **No score yet on 10-11:** no branch applies, and the D v4 row stays the only official measurement for this slot.

Open for the coordinator: the A_think row is recorded here with 100 calls, from its own description. A different call cap (28) was
given in the coordinator's message.
