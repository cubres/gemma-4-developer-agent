# 2026-10-08: the reasoning lever, one predeclared draw, and an environment drift

Three dated notes from the Gemma 4 Developer Agent campaign.

- [STATE_2026-10-08.md](STATE_2026-10-08.md): all official rows to date and what each tested. Every scored draw so far (3 to 5 of 58 tasks) ran with the model's reasoning forced off: in the organiser's current bridge, `include_thoughts: false` disables thinking regardless of the budget. The public 0.15-0.18 block runs with thinking on. The leaderboard snapshot (1,989 teams; leader 0.24) is dated.
- [A_THINK_PREDECLARATION.md](A_THINK_PREDECLARATION.md): the single-factor test submitted on 8 October 10:44 UTC (row 56949760): the twice-scored A_scout archive with one file changed so the engineer reasons (budget 4096, output 8192). The reading rule was fixed before submission: at least 0.12 confirms, 0.08-0.10 is inconclusive, at most 0.06 refutes. The score is unknown at this writing. Operational note learned the same morning: this competition rejects uploads not named exactly `submission.zip`.
- [WHEELHOUSE_DRIFT.md](WHEELHOUSE_DRIFT.md): why versions 21 and 22 of the public notebook failed at the compiler check in 45 seconds (the organiser's wheelhouse moved from adk-submission 0.2.11 to 0.2.12 after 30 September; a dataset-version pin did not change what the notebook saw) and the fix shipped as version 23 (pin updated in the notebook itself).

A separate row submitted on 7 October (the 240-second command-timeout variant, 56921186) ended in a Kaggle-side system error and is therefore unmeasured. Documentation here is MIT like its siblings; model and harness terms are the organisers'.
