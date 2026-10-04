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

"""Arithmetic/input contracts only; no quotas queried or compute dispatched."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import json
import math
import random
import unittest

from resource_planner import (ComparisonRequirements, DurationReading, QuotaSnapshot,
                              dated_snapshot_20261004, duration_seconds, plan_comparison)


def snapshot(allowance=10000, used=2000, reserved=1000, multiplier=2):
    return QuotaSnapshot('2026-10-04T00:00:00+00:00',
                         (DurationReading('typed', allowance),),
                         (DurationReading('typed', used),),
                         (DurationReading('typed', reserved),), multiplier)


def requirements(**changes):
    values = dict(arms=2, minimum_execution_seconds_per_arm=1000,
                  whole_run_setup_seconds=500, whole_run_finalization_seconds=100,
                  per_arm_setup_seconds=300, per_arm_finalization_seconds=50,
                  safety_reserve_wall_seconds=200)
    values.update(changes)
    return ComparisonRequirements(**values)


class DurationTests(unittest.TestCase):
    def test_serialized_and_typed_seconds_are_exact(self):
        self.assertEqual(duration_seconds('75600s'), Decimal(75600))
        self.assertEqual(duration_seconds(66341.335), Decimal('66341.335'))
        self.assertEqual(duration_seconds('0.000000001s'), Decimal('0.000000001'))

    def test_timedelta_conversion_preserves_microseconds(self):
        self.assertEqual(duration_seconds(timedelta(days=1, seconds=123, microseconds=1)),
                         Decimal('86523.000001'))

    def test_timedelta_conversion_is_exact_under_low_ambient_precision(self):
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(duration_seconds(timedelta(days=1, seconds=123, microseconds=1)),
                             Decimal('86523.000001'))
            self.assertEqual(duration_seconds(timedelta.max), Decimal('86399999999999.999999'))
            self.assertEqual(context.prec, 3)

    def test_actual_malformed_used_string_is_rejected_not_repaired(self):
        with self.assertRaisesRegex(ValueError, 'malformed'):
            DurationReading('serialized', '66341.335.0s')

    def test_malformed_unknown_negative_and_nonfinite_values_are_rejected(self):
        for value in [None, True, [], {}, -1, timedelta(microseconds=-1), math.nan, math.inf,
                      Decimal('NaN'), Decimal('Infinity'), 'nan s', '12', ' 12s', '12s ',
                      '-1s', '1e3s', '1.0000000001s', '1.s', '١s']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                duration_seconds(value)

    def test_zero_is_valid_but_not_assumed_for_unknown_usage(self):
        self.assertEqual(duration_seconds('0s'), 0)
        with self.assertRaises(ValueError):
            duration_seconds(None)

    def test_reading_requires_a_label(self):
        with self.assertRaises(ValueError):
            DurationReading('', 0)


class ObservationTests(unittest.TestCase):
    def test_smaller_allowance_wins_regardless_of_representation_order(self):
        base = snapshot()
        readings = (DurationReading('typed', 162000), DurationReading('serialized', '75600s'))
        for ordered in [readings, readings[::-1]]:
            plan = plan_comparison(replace(base, allowance=ordered), requirements())
            self.assertEqual(plan.allowance_seconds, 75600)
            self.assertTrue(plan.allowance_disagreement)

    def test_largest_valid_usage_and_reservation_win_without_double_counting(self):
        base = snapshot()
        observed = replace(base, used=(DurationReading('typed', 2000), DurationReading('serialized', '2500s')),
                           reserved=(DurationReading('typed', 1000), DurationReading('serialized', '1200s')))
        plan = plan_comparison(observed, requirements(minimum_execution_seconds_per_arm=1))
        self.assertEqual(plan.used_seconds, 2500)
        self.assertEqual(plan.reserved_seconds, 1200)
        self.assertEqual(plan.available_quota_seconds, 6300)
        self.assertTrue(plan.used_disagreement and plan.reserved_disagreement)

    def test_missing_readings_do_not_become_zero(self):
        for field in ['allowance', 'used', 'reserved']:
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(snapshot(), **{field: ()})

    def test_duplicate_representation_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            replace(snapshot(), used=(DurationReading('typed', 0), DurationReading('typed', 1)))

    def test_non_utc_or_missing_timestamp_is_rejected(self):
        for instant in ['2026-10-04', '2026-10-04T12:00:00', '2026-10-04T12:00:00+03:00', '', None]:
            with self.subTest(instant=instant), self.assertRaises(ValueError):
                replace(snapshot(), observed_at_utc=instant)

    def test_invalid_multiplier_never_defaults_to_one(self):
        for factor in [0, -2, True, math.nan, math.inf, '2', None]:
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                snapshot(multiplier=factor)

    def test_explicit_omission_notes_are_retained(self):
        observed = dated_snapshot_20261004()
        self.assertEqual(len(observed.used), 1)
        self.assertIn('66341.335.0s', observed.excluded_representation_notes[0])
        plan = plan_comparison(observed, requirements())
        self.assertEqual(plan.excluded_representation_notes, observed.excluded_representation_notes)

    def test_empty_omission_note_is_rejected(self):
        with self.assertRaises(ValueError):
            replace(snapshot(), excluded_representation_notes=('',))


class PlanningTests(unittest.TestCase):
    def test_dated_observation_has_only_4629_wall_seconds_before_overheads(self):
        plan = plan_comparison(dated_snapshot_20261004(), requirements())
        self.assertEqual(plan.quota_balance_seconds, Decimal('9258.665'))
        self.assertEqual(plan.quota_wall_limit_seconds, Decimal('4629.3325'))
        self.assertEqual(plan.allowance_seconds, 75600)
        self.assertEqual(plan.used_seconds, Decimal('66341.335'))
        self.assertEqual(plan.reserved_seconds, 0)

    def test_all_whole_and_per_arm_phases_are_charged(self):
        plan = plan_comparison(snapshot(), requirements())
        self.assertEqual(plan.status, 'FEASIBLE')
        self.assertEqual(plan.execution_seconds_per_arm, 1000)
        self.assertEqual(plan.arm_wall_seconds, 1350)
        self.assertEqual(plan.planned_wall_seconds, 3300)
        self.assertEqual(plan.budgeted_wall_seconds_including_reserve, 3500)
        self.assertEqual(plan.quota_seconds_including_reserve, 7000)

    def test_multiplier_two_reduces_wall_time_without_halving_overhead_twice(self):
        one = plan_comparison(snapshot(multiplier=1), requirements())
        two = plan_comparison(snapshot(multiplier=2), requirements())
        self.assertEqual(one.quota_wall_limit_seconds, two.quota_wall_limit_seconds * 2)
        self.assertEqual(one.execution_seconds_per_arm, 2750)
        self.assertEqual(two.execution_seconds_per_arm, 1000)
        self.assertEqual(one.per_arm_overhead_seconds, two.per_arm_overhead_seconds)

    def test_separate_arm_startups_are_not_amortized_as_one(self):
        zero = plan_comparison(snapshot(), requirements(per_arm_setup_seconds=0))
        per_arm = plan_comparison(snapshot(), requirements())
        self.assertEqual(zero.execution_seconds_per_arm - per_arm.execution_seconds_per_arm, 300)

    def test_overall_cap_includes_overhead_and_reserve(self):
        plan = plan_comparison(snapshot(), requirements(overall_wall_cap_seconds=3000,
                                                       minimum_execution_seconds_per_arm=750))
        self.assertEqual(plan.execution_seconds_per_arm, 750)
        self.assertEqual(plan.budgeted_wall_seconds_including_reserve, 3000)

    def test_per_arm_cap_includes_startup_and_finalization(self):
        plan = plan_comparison(snapshot(), requirements(arm_wall_cap_seconds=1200,
                                                       minimum_execution_seconds_per_arm=850))
        self.assertEqual(plan.execution_seconds_per_arm, 850)
        self.assertEqual(plan.arm_wall_seconds, 1200)

    def test_arm_cap_smaller_than_its_overhead_is_hold(self):
        plan = plan_comparison(snapshot(), requirements(arm_wall_cap_seconds=349))
        self.assertEqual(plan.status, 'HOLD')
        self.assertEqual(plan.reason, 'arm_cap_cannot_fit_overheads')

    def test_safety_reserve_is_inside_the_budget(self):
        plan = plan_comparison(snapshot(), requirements(safety_reserve_wall_seconds=400,
                                                       minimum_execution_seconds_per_arm=900))
        self.assertEqual(plan.execution_seconds_per_arm, 900)
        self.assertEqual(plan.budgeted_wall_seconds_including_reserve, 3500)

    def test_no_meaningful_comparison_returns_hold_and_no_recommended_budget(self):
        plan = plan_comparison(snapshot(), requirements(minimum_execution_seconds_per_arm=1001))
        self.assertEqual(plan.status, 'HOLD')
        self.assertEqual(plan.maximum_execution_seconds_per_arm, 1000)
        self.assertIsNone(plan.execution_seconds_per_arm)
        self.assertIsNone(plan.quota_seconds_including_reserve)

    def test_fractional_minimum_cannot_be_met_by_rounding_up(self):
        plan = plan_comparison(snapshot(), requirements(minimum_execution_seconds_per_arm=Decimal('1000.001')))
        self.assertEqual(plan.status, 'HOLD')

    def test_usage_over_allowance_holds_without_negative_allocations(self):
        plan = plan_comparison(snapshot(allowance=100, used=110, reserved=5), requirements())
        self.assertEqual(plan.status, 'HOLD')
        self.assertEqual(plan.reason, 'quota_exhausted')
        self.assertEqual(plan.quota_balance_seconds, -15)
        self.assertEqual(plan.maximum_execution_seconds_per_arm, 0)

    def test_zero_allowance_is_hold(self):
        self.assertEqual(plan_comparison(snapshot(0, 0, 0), requirements()).status, 'HOLD')

    def test_phase_overheads_over_total_limit_are_hold(self):
        plan = plan_comparison(snapshot(), requirements(whole_run_setup_seconds=4000))
        self.assertEqual(plan.status, 'HOLD')
        self.assertEqual(plan.reason, 'overheads_or_reserve_exceed_wall_limit')

    def test_invalid_arm_count_and_meaningless_zero_minimum_are_rejected(self):
        for changes in [dict(arms=1), dict(arms=0), dict(arms=True), dict(arms=2.0),
                        dict(minimum_execution_seconds_per_arm=0)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                requirements(**changes)

    def test_missing_negative_or_nonfinite_phase_bound_is_rejected(self):
        for value in [None, -1, math.inf]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                requirements(per_arm_setup_seconds=value)

    def test_dated_full_nominal_twelve_task_budget_is_hold_even_without_overheads(self):
        config = requirements(minimum_execution_seconds_per_arm=3600, whole_run_setup_seconds=0,
                              whole_run_finalization_seconds=0, per_arm_setup_seconds=0,
                              per_arm_finalization_seconds=0, safety_reserve_wall_seconds=0)
        self.assertEqual(plan_comparison(dated_snapshot_20261004(), config).status, 'HOLD')

    def test_json_report_preserves_decimal_strings_and_hold_nulls(self):
        plan = plan_comparison(dated_snapshot_20261004(), requirements(minimum_execution_seconds_per_arm=99999))
        encoded = json.loads(json.dumps(plan.as_dict()))
        self.assertEqual(encoded['quota_wall_limit_seconds'], '4629.3325')
        self.assertIsNone(encoded['execution_seconds_per_arm'])

    def test_large_decimal_inputs_do_not_round_away_real_overheads(self):
        observed = snapshot(allowance=Decimal('100000000000000000000000000000000000000000000000001'),
                            used=0, reserved=0, multiplier=2)
        plan = plan_comparison(observed, requirements())
        with localcontext() as ctx:
            ctx.prec = 200
            exact_cost = plan.budgeted_wall_seconds_including_reserve * 2
            self.assertEqual(plan.quota_seconds_including_reserve, exact_cost)
            self.assertLessEqual(exact_cost, observed.allowance[0].seconds)

    def test_nonterminating_multipliers_never_exceed_exact_fraction_limits(self):
        rng = random.Random(20261004)
        for _ in range(120):
            factor = rng.choice([Decimal('1.3'), Decimal('2'), Decimal('3'), Decimal('7.1')])
            observed = snapshot(allowance=rng.randrange(5000, 30000), used=rng.randrange(0, 1000),
                                reserved=rng.randrange(0, 1000), multiplier=factor)
            config = requirements(arms=rng.randrange(2, 5), minimum_execution_seconds_per_arm=1,
                                  overall_wall_cap_seconds=rng.randrange(1500, 5000))
            plan = plan_comparison(observed, config)
            if plan.status != 'FEASIBLE':
                continue
            wall = Fraction(str(plan.budgeted_wall_seconds_including_reserve))
            allowed_wall = Fraction(str(config.overall_wall_cap_seconds))
            quota = wall * Fraction(str(factor))
            available = Fraction(str(plan.available_quota_seconds))
            self.assertLessEqual(wall, allowed_wall)
            self.assertLessEqual(quota, available)
            self.assertGreaterEqual(plan.execution_seconds_per_arm, config.minimum_execution_seconds_per_arm)


if __name__ == '__main__':
    unittest.main()
