# D v4 declares the graph tools, and the V24 bookkeeping candidate dry-runs

Offline work only on 8 October 2026. Two bundles of the direct Gemma agent were rebuilt with the three code-graph tools declared,
and a bookkeeping version of the public notebook was built and dry-run through the identity-checked push helper. Nothing was
uploaded, submitted or pushed to Kaggle. The results are compiler and contract receipts, not official scores.

| Artifact | sha256 | Checks |
|---|---|---|
| D v4: D v3 plus the three graph tools declared and one prompt rule | `b54331170e0b9b885c651eac50d62715166e1c1ade2122da45db8535b1391549` | 7 of 7 compiler tests in normal and `-O` mode; ZIP contract against D v3 |
| D v4h: D v4 with `thinking_budget` 2048 and `max_output_tokens` 6144 | `34bd49c2e807944efeaca961a4a63bb132784d8f3893ef6ab54c4f1229a7124d` | 7 of 7 in both modes; differs from D v4 only in `configs/sampling.yaml` |
| V24 notebook placeholder (`--a-think PENDING`) | `7d4cd85a39f00bf4eaabd956ef2f5fd447027910d971f3c9c1f5d46174f2cea3` | 11 of 11 verifier tests; `safe_push` dry run returned `DRY_RUN_OK` |

The three declared names are `get_code_neighbors`, `search_similar_code` and `get_code_subgraph`. They are checked against the
harness source (`swegemma/tools/__init__.py` and `swegemma/tools/graph.py`) and the pinned `swegemma` 0.2.7 wheel. The runner
advertises them in the task message whenever graph data exists, and an undeclared call ends the task with an empty patch. D v4
therefore declares them and tells the agent never to call them.

`get_code_subgraph` takes a list, so one ARRAY parameter now compiles. The verifier allows exactly that one and nothing else.

The V24 candidate changes only cells 20 and 21 of the live V23 notebook (sha `65401f5c…`). It lists submission 56921186 as
Kaggle's system error, which is shown rather than hidden. Submission 56949760 stays pending until its score is known. A fresh
read of the submission list confirmed both statuses and the five completed scores.

Not done: no canary has run on the nine-tool declaration. An 8-minute canary must show zero unparsed or unregistered tool calls
before D v4 is considered for an official draw. The `search_similar_code` output size is also unchecked.
