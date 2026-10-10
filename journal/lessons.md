# Engineering lessons from the Gemma 4 developer-agent campaign

Each lesson gives the situation, the rule adopted, the evidence and how it was checked. Dates are UTC. Labels are defined in the [README](README.md). "Offline" marks work with no native run behind it; no score gain is claimed for it.

## 1. A transport cap shorter than one legitimate turn

- Situation: V19's proxy capped each model call at 150 seconds. Two long reasoning turns were cut, and the agent used its 8-minute budget without submitting.
- Rule: A canary's transport cap must exceed the longest legitimate turn at the measured decode speed. A cap change is a gate change and is recorded as one.
- Evidence: V19 (ledger 2026-10-08T16:33:14Z). V20, with a 420-second cap, completed a 323-second turn (ledger 2026-10-08T17:08:46Z).
- Checked: the proxy's failure times (150.01 and 150.09 seconds) and the V20 turn record.

## 2. Measure the budget in request time, and reserve the cold path

- Situation: In V20 completed requests used 459.8 of 480 seconds, with 7 of 28 calls made. Tool time was under 0.4 seconds between turns. V16 lost its reserve to a 364-second weight hash.
- Rule: Report time share and call share together, and set call caps only after the time share is measured. Reservations cover the cold path. Use one statistic for gates and budget models: in V20 the median root call was 18.0 seconds and the mean 59.0, because one 323-second turn dominated the mean.
- Evidence: V20 (ledger 2026-10-08T17:08:46Z); V16 (ledger, before 2026-10-08 09:43).
- Checked: the request ledger against the 481.87-second task record, and per-turn walls recomputed from the wire records.

## 3. Match the scorer's launch path, and check how the bridge maps config

- Situation: The V17 canary omitted the reasoning-config flag that the organiser's launcher adds, so all six model requests returned HTTP 400. Separately, the scorer's bridge forces thinking off when include-thoughts is false, so all five early draws ran with thinking off.
- Rule: A canary reproduces every organiser flag that changes model behaviour. Check the bridge's mapping of each config key, not only the YAML.
- Evidence: V17 (ledger 2026-10-08T14:01:10Z and 14:31:57Z); V18 with the flag accepted 15 of 15 requests; the five early rows.
- Checked: the V18 wire ledger, and the launcher and bridge source read in place.

## 4. Read the summariser's input, and watch the largest prompt

- Situation: A recovery rule assumed a compaction summary keeps little state, since the agent wrote no visible text beside tool calls. The harness reads the submitted patch inside its main try block, so an overflow returns an empty patch even after submit.
- Rule: Inspect the summariser's actual input before designing around it. Keep prompt plus output under the served context with margin, and stop for review on any context error.
- Evidence: the V20 compaction request (6,990 characters) held the task text and four reasoning fragments. V20's largest prompt was 14,993 tokens, and largest prompt plus 8,192 was 23,185, with no context errors (ledger 2026-10-08T17:08:46Z).
- Checked: the captured request, the framework source, and the harness exception path read in place.

## 5. A waived gate is not validation

- Situation: D v4 canaries V19 and V20 failed gate items 1 and 4. The coordinator waived item 4 as hardware-bound (10-08 17:25 UTC) and the status and exit parts of item 1 (17:35 UTC). D v4 was uploaded on 10-10 at 10:18 UTC.
- Rule: An upload made after a waiver is recorded as not validated by a native canary. A waiver names the gate, the reason and the evidence it relies on.
- Evidence: ledger 2026-10-08T17:08:46Z and 2026-10-10T10:18:11Z; the waiver text in the plan.
- Checked: the gate table in the V20 result, against the waiver text.

## 6. Do not claim gains below the detection limit

- Situation: Several levers had central expected gains of about half a task. Paired arms of 6 to 8 draws each cannot detect that. The thinking-on row scored 0.12, against 0.08 for the first thinking-off draw and 0.06 for its repeat.
- Rule: A gain below one task is recorded as untestable on the official board, and such a lever is adopted only on process metrics. Compare a new result with the repeat, not only the first draw.
- Evidence: verifier power calculations (0.07 to 0.13 for +0.5); ledger 2026-10-10T10:26:17Z.
- Checked: the verifiers' recomputed power tables.

## 7. Operational checks: pending rows, durable runners, raw quota

- Situation: The Gemma limit is one submission per day. On 10-09 the D v4 upload was refused because the thinking-on row had been pending for 31 hours. Midnight runners kept in scratch space were lost when the session restarted that day. A quota view misreported free GPU time after the reset, and the launcher refused a valid canary with "free -12,481 s"; the raw reading showed 73,842 seconds free.
- Rule: Check pending rows before planning the slot, and keep a ready fallback ZIP. Keep scheduled submissions in durable storage and have the next session check their receipts. Read quota from the raw endpoint, and treat a negative value as a parse error until the raw value confirms it.
- Evidence: ledger 2026-10-09T17:54:17Z (restart), 17:57:58Z (refusal: "team already has 1 pending submission"), 2026-10-10T10:17:19Z (row scored), 10:38:09Z (quota).
- Checked: the refusal message, the absence of midnight receipts, and the raw quota reading.

## 8. Pin dataset versions, and verify wheels before a GPU session

- Situation: On 10-08 the public notebook's install cell failed in 45 seconds: adk-submission 0.2.11 did not resolve against the mounted 0.2.12. The bootstrap was then moved to an unversioned private dataset to fit the notebook size limit. On 10-10 the wheelhouse had resolved to newer wheels, and the canary held at 135 seconds.
- Rule: Pin every dataset source, including datasets that hold offloaded code. The pilot's first step checks wheel names and hashes against the pins, so a mismatch costs minutes, not a GPU session.
- Evidence: ledger 2026-10-08T11:04 and 11:42 UTC; 2026-10-08T16:41:38Z (accepted 1,036,069 bytes, smallest rejected 1,181,475); 2026-10-10T11:19:28Z and 11:27:29Z.
- Checked: the wheelhouse version listing, the mounted wheel names and the hold receipt.

## 9. System-error rows: follow the exact text, and fix the re-upload rule in advance

- Situation: Row 56921186 (A_scout with a 240-second command and final-verification timeout) ended ERROR with "A system error. Please try resubmitting". The handoff said never to re-upload those bytes, while the sweep's policy was to re-upload identical bytes after a system error. The coordinator chose D v4 for the next slot, which keeps the 240-second setting. Three ERROR rows in another competition on 10-06 carried the same text.
- Rule: A row counts as platform-side only when its text matches exactly. Any other text holds the next upload for diagnosis. Write the re-upload rule for each error into the plan before the slot.
- Evidence: ledger 2026-10-08T11:46Z and 15:52Z; plan decision of 17:25 UTC; the 10-06 rows of the other competition.
- Checked: the row's raw text; the submit script's guard tests (16 of 16); the D v4 evaluation config.

## 10. Offline design: a deadline contract with a protected finishing reserve

- Situation: In V19 the agent was cut at 482 seconds with no submit. In V20 the budget ran out 17 seconds into a generation, with no patch. Neither run reserved time for the final edit, the targeted tests or the patch capture.
- Rule (designed, not yet native): reserve time inside the agent budget for the final edit (15 seconds), targeted tests (60), patch capture (10) and margin (5), and refuse optional work once exploration is spent. The 90-second reserve is a design choice, not a measured need. (offline)
- Evidence: V19 and V20 results; the package was committed to the public repository on 10-10.
- Checked: the package's offline unit tests under normal and optimized Python. Native compatibility remains HOLD.

## 11. Offline design: an interruption-safe finalization journal

- Situation: The capture helper wrote its start event in memory and wrote the event after verification ran. An interruption could leave a partial artifact under a valid-looking name.
- Rule (designed): write the start event durably before verification runs; stage each event, fsync it and publish it by exclusive link; flag incomplete or inconsistent chains. The chain is not authentication, so its observations must be bound to real calls before use. (offline)
- Evidence: the journal package's source observations, committed on 10-10. No campaign run has used it.
- Checked: the package's offline tests for interruption, publication failure, late commit and forged events. Not run natively.

## 12. A draft-token cap on another stack: check the serving source first (not a Gemma row)

- Situation: In the ARC3 bench a setting of 4 speculative steps needed 5 draft tokens. The QSA attention backend allows draft tokens only up to its compress ratio of 4, so the server failed at CUDA-graph capture, the control arm was skipped, and the lever was closed.
- Rule: Before spending a bench, check the serving source for hard limits on any swept parameter. Here draft tokens must be at most 4, which means at most 3 steps.
- Evidence: ledger 2026-10-10T11:13:47Z and 11:16:48Z. The Gemma serving log records speculative config as none, so this cap does not bind the Gemma stack.
- Checked: as recorded in the ledger by the ARC3 campaign; not re-checked for this journal.
