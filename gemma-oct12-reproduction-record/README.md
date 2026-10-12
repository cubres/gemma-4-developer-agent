# Gemma, 12 October 2026: a useful reproduction and an honest record

Start with the [public V27 quickstart notebook](https://www.kaggle.com/code/prvsiyan/gemma-and-the-shape-of-doubt/27) or the [faithful source package at its frozen commit](https://github.com/cubres/gemma-4-developer-agent/tree/3cad9792f90dd846d0d89b4d2cd5514fc8323775/bfv5-faithful-reproduction-2026-10-12). This work makes a licensed developer-agent recipe readable, reconstructible and easier to inspect. It supplies **no new agent-quality result or score gain**.

## Reproduce the reference

The faithful package reproduces **Wilmer E. Henao (verracodeguacas), Gemma 4 Agent: Budget-Fit Single Agent, Version 5**. Its four runtime files are byte-identical to published V5. Only inert `LICENSE.txt` and `NOTICE.txt` are added to the archive; the model, prompt, tools, sampling and budgets remain unchanged.

Preserve the folder structure and run the existing [stdlib builder](https://github.com/cubres/gemma-4-developer-agent/blob/3cad9792f90dd846d0d89b4d2cd5514fc8323775/bfv5-faithful-reproduction-2026-10-12/rebuild.py) on CPU: `python3 rebuild.py --output ../faithful-v5-build`. It writes `submission.zip` and `rebuild_receipt.json` without importing the organizer or model, executing tasks, using a network or submitting. The faithful **local** archive is **7,469 bytes**, SHA256 `50804cdc0be576e364f93f0154fa3b6dbff66ec559bf24e4343432dedfed5501`.

The [separate coverage source](https://github.com/cubres/gemma-4-developer-agent/tree/072969d3b7fb175550e355690b4fb1f7c6d2e9d3/bfv5-coverage-2026-10-12) adds an original bounded sibling/public-registration prompt checkpoint. It has its own archive and output directory, remains unattempted, and has no native-quality result. Keep its source and outcomes separate from the faithful reference.

## What was actually verified

Actual organizer compiler, ADK template and nine-tool declaration parity passed for upstream V5 and the faithful reproduction. All four runtime members matched exactly. Qualification used **zero target-model calls and zero executed agent or synthetic tasks**: structural evidence only; native agent quality remains **UNMEASURED**.

[V26](https://www.kaggle.com/code/prvsiyan/gemma-and-the-shape-of-doubt/26) preserved the existing owned workshop artwork and original workflow SVG; the actual public browser displayed both. V27 retained every one of V26's 47 complete cells and added one current-status/CPU quickstart panel after the hero. Full identity, metadata and typed JSON readback passed. The actual public V27 browser verified the panel, three correctly preformatted YAML blocks and the unchanged **1672×941** hero. Its **30.3-second successful source-packaging run produced six output files**. This notebook success is not a target-model evaluation. Historical sections retain their dated evidence.

## The official attempt stopped at transport

The one attempt for local archive `50804cdc…fed5501` reached **Start HTTP 200**, then stopped with a client `Hold` before any recorded PUT or Create request. No accepted reference was returned. The precise allocation value or failed predicate was not retained; the exact cause remains unknown.

One read-only inventory reconciliation at **13:18:11 UTC on 12 October** found **eight unchanged rows, no new row and no matching accepted reference**. The permanent outcome is **UNKNOWN_NEVER_REPEAT**. A local archive hash does not prove a server-stored binary. **Do not retry, resubmit or cosmetically repackage this consumed candidate.**

There is **no new official score**. The account's earlier **0.13** belongs to a separate private D configuration; it is not a result for this faithful reproduction, coverage experiment or presentation work.

## Credit and readable source

The [upstream notebook](https://www.kaggle.com/code/verracodeguacas/gemma-4-agent-budget-fit-single-agent) is by Wilmer E. Henao (verracodeguacas), under [Apache-2.0](https://github.com/cubres/gemma-4-developer-agent/blob/3cad9792f90dd846d0d89b4d2cd5514fc8323775/bfv5-faithful-reproduction-2026-10-12/LICENSE.txt); its [NOTICE](https://github.com/cubres/gemma-4-developer-agent/blob/3cad9792f90dd846d0d89b4d2cd5514fc8323775/bfv5-faithful-reproduction-2026-10-12/NOTICE.txt) retains attribution. The portable builder, original diagrams, owned concept artwork and documentation are cubres contributions. The artwork is an illustration, not measured evidence or official Gemma branding.

[STATUS.json](STATUS.json) records aggregate outcomes and evidence digests. [SOURCE_REFERENCES.json](SOURCE_REFERENCES.json) links the existing public files. This packet duplicates no code or images and distributes no organizer files, task snapshots, raw responses or credentials.
