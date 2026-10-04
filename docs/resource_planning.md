# Planning a bounded comparison

[resource_planner.py](../src/resource_planner.py) is a standalone, standard-library utility for planning sequential experiment arms. It performs arithmetic only: it does not query quota, launch work, reserve resources, change billing settings, or change notebooks. A `FEASIBLE` result means the **supplied snapshot and declared phase bounds** admit a budget. It does not guarantee current availability or completion of a task panel.

From the repository root, make `src` importable in your current shell and run the 34 contract tests:

```sh
export PYTHONPATH=src
python -m unittest discover -s tests -p 'test_resource_planner.py'
```

Use Python 3.12, then run this example in a Python session in that shell:

```python
import json
from resource_planner import (
    ComparisonRequirements, dated_snapshot_20261004, plan_comparison,
)

# Historical input only: 2026-10-04 at 14:39:16.663810 UTC.
snapshot = dated_snapshot_20261004()
requirements = ComparisonRequirements(
    arms=2,
    minimum_execution_seconds_per_arm=3600,
    whole_run_setup_seconds=1200,
    whole_run_finalization_seconds=120,
    per_arm_setup_seconds=600,
    per_arm_finalization_seconds=60,
    safety_reserve_wall_seconds=300,
    overall_wall_cap_seconds=8800,
    arm_wall_cap_seconds=4200,
)
plan = plan_comparison(snapshot, requirements)
assert plan.status == "HOLD"
assert plan.execution_seconds_per_arm is None
assert plan.maximum_execution_seconds_per_arm == 844
print(json.dumps(plan.as_dict(), indent=2))
```

The example freezes an observed allowance of **75,600 serialized seconds versus 162,000 typed seconds**, **66,341.335 used seconds**, and **zero reserved seconds**. It selects the smaller allowance. That leaves 9,258.665 quota seconds. The configured multiplier of 2 gives 4,629.3325 wall seconds before overheads or reserve. This multiplier is a hand-off assumption for four L4 GPUs, not a billing rate independently established by the utility or a staff guarantee. The phase values above are explicit planning assumptions: 1,200 seconds for two bounded setup commands, with hypothetical startup, finalization and reserve bounds. The 3,600-second minimum is a caller-declared nominal execution policy; it does not prove that twelve tasks finish in that time. Under those inputs, only 844 integer execution seconds per arm fit, so the meaningful minimum yields `HOLD`.

For new observations, construct `QuotaSnapshot` with labeled `DurationReading` tuples. They must represent the **same cumulative quantity** in different forms: allowance uses their minimum; used and reserved use their maximum. Independent reservations are different quantities and must be summed before supplying an aggregate reservation reading. Do not substitute zero for unknown usage or reservations.

`duration_seconds` accepts finite nonnegative numeric seconds, `datetime.timedelta`, or a serialized string such as `"75600s"`. Strings require a seconds suffix and at most nine fractional digits. The malformed serialized used value `"66341.335.0s"` raises `ValueError`; it is never repaired or silently discarded. The historical factory explicitly supplies the valid typed used value and records the excluded malformed representation in its notes. Any other omitted evidence likewise needs an explicit caller decision and provenance record.

`ComparisonRequirements` keeps all durations in **wall seconds**:

- Whole-run setup covers installation and initialization outside arm timers; whole-run finalization covers final output collection.
- Per-arm setup covers a server started separately for each arm, graph/endpoint checks and environment preparation. Per-arm finalization covers the corresponding finish work.
- Per-arm execution is useful work after those overheads. Its minimum must be strictly positive and declared by the caller.
- The overall cap includes all phases and the safety reserve; each arm cap includes its setup, execution and finalization.

The planner subtracts whole-run overhead once, per-arm overhead for every arm, and a wall-time reserve. It then applies both caps and rounds equal per-arm execution budgets down to integer seconds. The quota multiplier charges **all** budgeted wall time, including overhead and reserve. If the minimum cannot fit, it reports `HOLD` and no recommended budget; `maximum_execution_seconds_per_arm` remains a diagnostic ceiling. Do not reinterpret that ceiling as a complete-panel runtime estimate.

For `FEASIBLE`, read `execution_seconds_per_arm` alongside `arm_wall_seconds`, `planned_wall_seconds`, `budgeted_wall_seconds_including_reserve`, and `quota_seconds_including_reserve`. Decimal-valued report fields are strings to preserve precision in JSON. Malformed inputs, missing readings, duplicate representation labels, invalid UTC timestamps, negative phases or nonpositive multipliers raise `ValueError` rather than producing a plan.

A previous twelve-task duration sum or empirical mean omits other phases and provides no runtime bound. Fresh account usage, concurrent sessions, queue behavior, changing platform charges, or underestimated phase bounds can invalidate a calculation. A queued job is not evidence of a model failure. [Kaggle's queue discussion](https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/743683) discusses L4 queueing and delayed rescoring; it does not establish the cause of any particular pending job. A planning result also supplies no authorization for paid compute or launch.
