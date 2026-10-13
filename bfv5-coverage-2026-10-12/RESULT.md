# Budget-Fit V5 coverage checkpoint: completed official result

Our exploratory `e01` submission completed with **public score 0.18**. The exact Kaggle row is **57111761**, submitted on 12 October at 15:36:36.663 UTC and verified COMPLETE on 13 October at 23:35:30.661910 UTC. This exceeds the account's earlier verified 0.13 from the separate D v4 configuration. The credited upstream V5 notebook had also displayed 0.18 in the retained source snapshot.

The raw official row binds `prvsiyan`, `submission.zip`, the timestamp and the complete experiment description. A subsequent download of that row's archive reproduced the original **8,055-byte ZIP byte for byte**, SHA256 `0311b8a71ff9498aaaca30a8a6d22be5622a62539eaef0360dd585d401fe3af9`. All six member hashes are recorded in [SCORED_ARCHIVE_IDENTITY.json](SCORED_ARCHIVE_IDENTITY.json). The API's separately reported `totalBytes=116729` is retained as metadata; it is not substituted for the measured download length.

## What the experiment changes

The underlying recipe is **Wilmer E. Henao (verracodeguacas), Gemma 4 Agent: Budget-Fit Single Agent, V5**, under Apache-2.0. The original addition is a bounded source-coverage checkpoint after the first source edit: check whether another implementation or public registration needs the same correction, while retaining the original clocks and call limits. Full attribution and the original source hashes remain in [NOTICE.txt](NOTICE.txt).

![The original bounded checkpoint and its budget conditions](coverage-checkpoint.svg)

The three runtime configuration files remain byte-identical to V5: one 31B QAT coder with four-bit weights, nine declared tools, 8 minutes, 28 charged calls, 80 turns and 240-second commands. Read the [original guide](README.md) for the conditional checkpoint, unchanged graph-tool restrictions and exact CPU rebuild:

```sh
python3 rebuild.py --output ../coverage-build
```

That builder reconstructs the submitted source archive without loading a model or making a submission. Use a fresh destination and compare its receipt with the scored archive hash. The [public campaign notebook](https://www.kaggle.com/code/prvsiyan/gemma-and-the-shape-of-doubt) supplies wider campaign context; the result belongs to this exact ZIP and official row.

## Interpretation and next comparison

This is one completed organizer evaluation. It establishes the observed public score for this configuration. It does not isolate a causal benefit from the added checkpoint: D v4 is a different configuration, the upstream score came from a separate run, and evaluator traces exposing checkpoint adherence were unavailable in this refresh. The earlier independent native qualification HOLD remains preserved; an official result does not change that local runtime evidence.

The useful next comparison is the unchanged V5 control and this treatment on the same frozen development tasks, with completion, time, charged calls and checkpoint adherence recorded for both arms. Keep code and prompt attribution intact, and preserve the already-consumed upload marker: this accepted submission must never be repeated as monitoring or recovery.
