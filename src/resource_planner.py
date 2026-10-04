# MIT License
#
# Copyright (c) 2026 cubres
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Pure quota arithmetic for a sequential comparison; no platform operations.

All phase durations and caps are wall seconds. Observed allowance, used and
reserved durations are quota seconds. A configured multiplier charges the
entire planned wall interval, including setup/finalization and a safety reserve.
Feasibility is conditional on the caller's bounds and snapshot; it is neither
current availability nor a guarantee that a task panel will finish.
"""

from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, localcontext
import re


def duration_seconds(value) -> Decimal:
    """Strict nonnegative seconds: numeric, timedelta, or serialized `123.45s`.

    Strings require the suffix and at most nine fractional digits. Malformed
    representations raise ValueError; no reading is silently dropped or repaired.
    Floats use their decimal string value. Timedelta conversion is exact.
    """
    if isinstance(value, bool):
        raise ValueError('boolean is not a duration')
    if isinstance(value, timedelta):
        # Integer microseconds avoid rounding intermediate day/second sums.
        # Conversion has its own context; callers may use low Decimal precision.
        microseconds = ((value.days * 86400 + value.seconds) * 1000000
                        + value.microseconds)
        with localcontext() as context:
            context.prec = max(30, len(str(abs(microseconds))))
            result = Decimal(microseconds) / 1000000
    elif isinstance(value, str):
        if re.fullmatch(r'[0-9]+(?:\.[0-9]{1,9})?s', value) is None:
            raise ValueError('malformed serialized duration; expected nonnegative seconds with s suffix')
        result = Decimal(value[:-1])
    elif isinstance(value, (int, float, Decimal)):
        result = Decimal(str(value))
    else:
        raise ValueError('unsupported duration representation')
    if not result.is_finite() or result < 0:
        raise ValueError('duration must be finite and nonnegative')
    return result


@dataclass(frozen=True)
class DurationReading:
    """One labeled representation of the same cumulative quota quantity."""
    representation: str
    value: object
    seconds: Decimal = field(init=False)

    def __post_init__(self):
        if not isinstance(self.representation, str) or not self.representation.strip():
            raise ValueError('duration reading needs a representation label')
        object.__setattr__(self, 'seconds', duration_seconds(self.value))


def _check_readings(readings):
    if (not isinstance(readings, tuple) or not readings
            or any(not isinstance(r, DurationReading) for r in readings)
            or len({r.representation for r in readings}) != len(readings)):
        raise ValueError('provide a nonempty tuple of uniquely labeled valid duration readings')


@dataclass(frozen=True)
class QuotaSnapshot:
    """Dated caller evidence; independent reservations must be summed upstream.

    Repeated representations of one allowance use min; repeated representations
    of the same cumulative usage/reservation use max, not sum. Every supplied
    reading must already be valid. Explicit omissions belong in the notes.
    """
    observed_at_utc: str
    allowance: tuple[DurationReading, ...]
    used: tuple[DurationReading, ...]
    reserved: tuple[DurationReading, ...]
    multiplier: object
    excluded_representation_notes: tuple[str, ...] = ()

    def __post_init__(self):
        try:
            instant = datetime.fromisoformat(self.observed_at_utc.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as exc:
            raise ValueError('snapshot needs an explicit UTC timestamp') from exc
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            raise ValueError('snapshot timestamp must explicitly use UTC')
        for readings in (self.allowance, self.used, self.reserved):
            _check_readings(readings)
        if isinstance(self.multiplier, bool) or not isinstance(self.multiplier, (int, float, Decimal)):
            raise ValueError('quota multiplier must be a numeric value')
        factor = Decimal(str(self.multiplier))
        if not factor.is_finite() or factor <= 0:
            raise ValueError('quota multiplier must be positive and finite')
        object.__setattr__(self, 'multiplier', factor)
        if (not isinstance(self.excluded_representation_notes, tuple)
                or any(not isinstance(n, str) or not n.strip() for n in self.excluded_representation_notes)):
            raise ValueError('excluded representations require explicit nonempty notes')


@dataclass(frozen=True)
class ComparisonRequirements:
    """Caller-declared bounds for sequential arms, each with its own server.

    Per-arm execution excludes per-arm setup and finalization. Whole-run setup
    can include dependency installation. Overall/arm caps include their overheads;
    the safety reserve is also held inside the overall wall limit. Zero overhead
    or reserve is possible only when explicitly declared by the caller.
    """
    arms: int
    minimum_execution_seconds_per_arm: object
    whole_run_setup_seconds: object
    whole_run_finalization_seconds: object
    per_arm_setup_seconds: object
    per_arm_finalization_seconds: object
    safety_reserve_wall_seconds: object
    overall_wall_cap_seconds: object = None
    arm_wall_cap_seconds: object = None

    def __post_init__(self):
        if isinstance(self.arms, bool) or not isinstance(self.arms, int) or self.arms < 2:
            raise ValueError('a comparison requires at least two integer arms')
        for item in fields(self):
            if item.name == 'arms':
                continue
            value = getattr(self, item.name)
            if value is None and item.name in ('overall_wall_cap_seconds', 'arm_wall_cap_seconds'):
                continue
            object.__setattr__(self, item.name, duration_seconds(value))
        if self.minimum_execution_seconds_per_arm <= 0:
            raise ValueError('meaningful per-arm execution must be strictly positive')


@dataclass(frozen=True)
class ResourcePlan:
    """Explicit conditional budget or HOLD; as_dict is JSON serializable."""
    status: str
    reason: str
    observed_at_utc: str
    arms: int
    allowance_seconds: Decimal
    used_seconds: Decimal
    reserved_seconds: Decimal
    quota_multiplier: Decimal
    quota_balance_seconds: Decimal
    available_quota_seconds: Decimal
    quota_wall_limit_seconds: Decimal
    effective_wall_limit_seconds: Decimal
    whole_run_overhead_seconds: Decimal
    per_arm_overhead_seconds: Decimal
    safety_reserve_wall_seconds: Decimal
    minimum_execution_seconds_per_arm: Decimal
    maximum_execution_seconds_per_arm: int
    execution_seconds_per_arm: int | None
    arm_wall_seconds: Decimal | None
    planned_wall_seconds: Decimal | None
    budgeted_wall_seconds_including_reserve: Decimal | None
    quota_seconds_including_reserve: Decimal | None
    allowance_disagreement: bool
    used_disagreement: bool
    reserved_disagreement: bool
    excluded_representation_notes: tuple[str, ...]

    def as_dict(self):
        """Preserve decimal precision as strings, rather than JSON float rounding."""
        return {item.name: (str(value) if isinstance(value := getattr(self, item.name), Decimal)
                            else list(value) if isinstance(value, tuple) else value)
                for item in fields(self)}


def plan_comparison(snapshot: QuotaSnapshot, requirements: ComparisonRequirements) -> ResourcePlan:
    """Allocate equal integer execution budgets after every declared overhead.

    Caller bounds cover a single allocated compute session with sequential arms.
    Stale observations, parallel sessions, underestimated overheads and other
    account usage can invalidate the conditional calculation.
    """
    with localcontext() as context:
        numeric_inputs = [r.seconds for readings in (snapshot.allowance, snapshot.used, snapshot.reserved)
                          for r in readings] + [snapshot.multiplier]
        numeric_inputs += [getattr(requirements, f.name) for f in fields(requirements)
                           if f.name != 'arms' and getattr(requirements, f.name) is not None]
        # Preserve finite input sums/products exactly even for very large or
        # very small decimals; only nonterminating division needs downward rounding.
        context.prec = max(50, sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent)
                                   for v in numeric_inputs) + len(str(requirements.arms)) + 20)
        allowance = min(r.seconds for r in snapshot.allowance)
        used = max(r.seconds for r in snapshot.used)
        reserved = max(r.seconds for r in snapshot.reserved)
        balance = allowance - used - reserved
        available = max(Decimal(0), balance)
        # Round division downward; integer allocation never rounds up a budget.
        context.rounding = ROUND_FLOOR
        quota_wall = available / snapshot.multiplier
        wall_limit = quota_wall
        if requirements.overall_wall_cap_seconds is not None:
            wall_limit = min(wall_limit, requirements.overall_wall_cap_seconds)
        whole_overhead = requirements.whole_run_setup_seconds + requirements.whole_run_finalization_seconds
        arm_overhead = requirements.per_arm_setup_seconds + requirements.per_arm_finalization_seconds
        remainder = (wall_limit - requirements.safety_reserve_wall_seconds
                     - whole_overhead - requirements.arms * arm_overhead)
        per_arm = max(Decimal(0), remainder / requirements.arms)
        arm_cap_insufficient = False
        if requirements.arm_wall_cap_seconds is not None:
            cap = requirements.arm_wall_cap_seconds - arm_overhead
            arm_cap_insufficient = cap < 0
            per_arm = min(per_arm, max(Decimal(0), cap))
        maximum = int(per_arm.to_integral_value(rounding=ROUND_FLOOR))
        if available <= 0:
            reason = 'quota_exhausted'
        elif remainder < 0:
            reason = 'overheads_or_reserve_exceed_wall_limit'
        elif arm_cap_insufficient:
            reason = 'arm_cap_cannot_fit_overheads'
        elif Decimal(maximum) < requirements.minimum_execution_seconds_per_arm:
            reason = 'meaningful_per_arm_execution_does_not_fit'
        else:
            reason = 'declared_bounds_fit'
        feasible = reason == 'declared_bounds_fit'
        arm_wall = arm_overhead + maximum if feasible else None
        planned_wall = whole_overhead + requirements.arms * arm_wall if feasible else None
        budgeted_wall = planned_wall + requirements.safety_reserve_wall_seconds if feasible else None
        quota_needed = budgeted_wall * snapshot.multiplier if feasible else None
        if feasible:
            assert budgeted_wall <= wall_limit
            assert quota_needed <= available
        return ResourcePlan(
            'FEASIBLE' if feasible else 'HOLD', reason, snapshot.observed_at_utc, requirements.arms,
            allowance, used, reserved, snapshot.multiplier, balance, available, quota_wall, wall_limit,
            whole_overhead, arm_overhead, requirements.safety_reserve_wall_seconds,
            requirements.minimum_execution_seconds_per_arm, maximum, maximum if feasible else None,
            arm_wall, planned_wall, budgeted_wall, quota_needed,
            len({r.seconds for r in snapshot.allowance}) > 1,
            len({r.seconds for r in snapshot.used}) > 1,
            len({r.seconds for r in snapshot.reserved}) > 1,
            snapshot.excluded_representation_notes,
        )


def dated_snapshot_20261004() -> QuotaSnapshot:
    """Frozen observation at 14:39:16.663810 UTC; never a live quota guarantee."""
    return QuotaSnapshot(
        observed_at_utc='2026-10-04T14:39:16.663810+00:00',
        allowance=(DurationReading('typed', 162000), DurationReading('serialized', '75600s')),
        used=(DurationReading('typed_explicit', Decimal('66341.335')),),
        reserved=(DurationReading('typed', 0),), multiplier=2,
        excluded_representation_notes=(
            "Serialized used '66341.335.0s' is malformed and explicitly excluded; valid typed used was supplied.",
            'Multiplier 2 is a configured four-L4 hand-off value, not an automatically measured billing rate.',
        ),
    )
