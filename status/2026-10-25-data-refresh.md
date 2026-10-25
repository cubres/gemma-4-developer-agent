# Gemma public-task data refresh — 2026-10-25

## Retrieved from Kaggle

- `tasks.jsonl`: 1,984,455 bytes; SHA-256 `e4b3fd60f69dbc2b9213e54eeb9636db78aefe92c1d06269d73d9f5f8f3c8ad6`. It contains 129 public task records: 67 FastAPI, 48 Rich, 13 Requests and 1 HTTPX.
- `HARNESS_README.md`: 55,940 bytes; SHA-256 `445000219b803942c469391ec8b69791a31e9cec2f934738c767e34b5ca0aa1f`.
- The raw competition files are not copied into this repository. This note records hashes and aggregate counts only.

## What the task files support

A local profile of the gold patches found 38 of 129 tasks changing more than one non-test path. This supports testing a conditional, one-call code-neighbor lookup after direct source inspection. It does not show that the tool improves an agent's pass rate.

The task file includes base commits, gold patches and test patches, but it does not include repository snapshots or a compatible 31B evaluation environment. A paired control/treatment experiment is not yet runnable from this download alone. No score claim is made.

## Rule-source conflict

The online [competition overview](https://www.kaggle.com/competitions/gemma-4-developer-agent/overview/model-selection-budget-and-harness-rules) says the supported base model is `gemma-4-31b-it-qat-w4a16-ct` for every agent and sub-agent. A Kaggle staff reply gives the same clarification ([discussion 743056](https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/743056)). The downloadable harness README lists four quantized variants. These official sources conflict, so this work keeps the stricter 31B requirement and does not switch models.

## Verified Kaggle state

A fresh pull verified the existing notebook identity: ID `135663039`, title `Gemma and the Shape of Doubt`, code file `gemma-and-the-shape-of-doubt.ipynb`. Kaggle reports its latest kernel run as complete.

The latest completed official submission observed was V35, submission `57431737`, public score `0.15`. V32, submission `57329048`, scored `0.18`. These are separate unpaired evaluations; they do not isolate the effect of any one change.

No notebook update, dataset publication or competition submission was made in this refresh. The next safe step is to reconcile notebook ownership and identity, then run a paired public-task experiment on a compatible harness and model runtime before preparing another version.
