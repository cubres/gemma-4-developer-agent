# Checkpoint, 25 October 2026

Labels are defined in the [README](README.md). This checkpoint covers local work only. No notebook was changed, nothing was published to Kaggle and no submission was made.

## 1. Factory readiness

The campaign's factory readiness check for this competition completed and was accepted, with a retained evidence receipt [V]. The official rules, evaluation description and data description were retained as hashed local sources for the next step [V].

## 2. Local experiment: submission-layout preflight

Hypothesis, as reviewed: a standard-library `zipfile` preflight that encodes the official archive layout from the evaluation description should classify a fixed split of six synthetic archives correctly, against a baseline with no preflight. The layout requires `agent.yaml` at the archive root. The `configs`, `prompts`, `sub_agents`, `adapters` and `skills` directories are optional. The six cases were:

- one minimal conforming archive (pass)
- one conforming archive with the optional directories (pass)
- one with `agent.yaml` missing (fail)
- one with `agent.yaml` only in a nested folder (fail)
- one with a parent-traversal member path (fail)
- one with an absolute member path (fail)

The measurement was six of six correct within a 600 CPU-second budget. The inputs were the public evaluation and data descriptions only, not Competition Data.

Result:

- The worker reported six of six correct for the preflight and two of six for the no-preflight baseline, which passes everything [V, worker report].
- The coordinator reran the pinned local verifier. It exited 0 with `verified: true`: six tests run and six passing cases executed. `official_score` is null [V].
- **The result is not accepted.** The broker holds the outcome as `needs_review` with `validation_matches: false` [V]. One of the worker's declared checks used a placeholder instead of the exact hypothesis text [V]. That placeholder is the likely cause of the mismatch [I].
- None of the documented resolution routes applies to a passing write-mode result with no failed commands, so the task stays held. It was not retried and its slot was not reused [V].

This result is a local tool check only. It does not measure agent quality and does not predict the leaderboard [I].

## 3. Process notes

- The experiment contract had a single review, by the coordinator. The orchestration policy has no separate reviewer route for contract approval [V].
- Official rows were not re-read for this checkpoint. It makes no claim about the leaderboard.

## 4. Next

- The `needs_review` hold needs a documented resolution before this preflight can count as an accepted result.
- If it is accepted, the preflight can serve as a local gate before archive packaging [I].

## 5. Addendum: result accepted by coordinator validation (later on 25 October 2026)

Section 2 above is superseded on one point. Since then, the preflight result has been accepted through the queue's documented worker-review route, using an independently approved coordinator review packet (SHA256 `cd5cf5c2…`). The task is now COMPLETE, with result evidence `9dc1bd70…` [V].

- Acceptance came from coordinator validation of the actual worker output, contract and source tree. The worker's own declared validation is still recorded as unaccepted [V].
- The model was not rerun, and the task's slot was not reused [V].
- It is still a local archive-layout check only. It measures neither agent quality nor the leaderboard. No notebook was changed and nothing was submitted [V].
