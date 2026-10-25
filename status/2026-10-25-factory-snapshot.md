# Gemma factory status — 25 October 2026

## Official results

- Latest completed owned evaluation: **V35, 0.15** (submission 57431737).
- Best captured owned result: **V32, 0.18** (submission 57329048).
- Current public leaderboard top observed on 25 October: **0.24**.

These are separate official evaluations. V35 bundled a final-edit verification prompt with a six-tool configuration, so its lower score does not isolate a cause.

- [Competition leaderboard](https://www.kaggle.com/competitions/gemma-4-developer-agent/leaderboard)
- [Current competition overview and rules](https://www.kaggle.com/competitions/gemma-4-developer-agent/overview)

## Controlled next step

Keep the current 31B setup as the control. Test one prompt-only change: call `get_code_neighbors` once, with a small result cap, only when direct source inspection has not found relevant callers. Keep tools, model, sampling, task budgets, and final verification fixed. Use the same seeded public development issues for both arms and record issue-level pass rate, tool calls, tokens, and time.

Local or Colab smoke checks cannot establish a Kaggle score. No notebook change, evaluation, or submission was made in this snapshot.
