"""Adversarial offline tests: injected clocks, no APIs, models or commands."""
import asyncio
import json
import unittest
from deadline_contract import DeadlineContract, Kind, Reserve


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t
    def advance(self, delta): self.t += delta


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.c = DeadlineContract(clock=self.clock)

    def finish(self, kind, seconds, requested=240):
        t = self.c.admit(kind, requested)
        self.assertIsNotNone(t)
        self.clock.advance(seconds)
        return self.c.settle(t, "COMPLETE")

    def test_long_model_preserves_full_reserve(self):
        t = self.c.admit(Kind.MODEL, 420)
        self.assertEqual(t.timeout_seconds, 390)
        self.clock.advance(390)
        self.c.settle(t, "COMPLETE")
        self.assertEqual(self.c.aggregate()["remaining_seconds"], 90)

    def test_exact_reserve_denies_every_optional(self):
        self.clock.advance(390)
        for kind in (Kind.MODEL, Kind.COMMAND, Kind.SCOUT, Kind.COMPACTION):
            self.assertIsNone(self.c.admit(kind, 30))
        self.assertEqual(self.c.aggregate()["denied_count"], 4)

    def test_finish_order_retains_tests_capture_and_settle(self):
        self.clock.advance(390)
        t = self.c.admit(Kind.FINAL_EDIT, 240)
        self.assertEqual(t.timeout_seconds, 15)
        self.clock.advance(15); self.c.settle(t, "COMPLETE")
        t = self.c.admit(Kind.FINAL_TEST, 240)
        self.assertEqual(t.timeout_seconds, 60)
        self.clock.advance(60); self.c.settle(t, "COMPLETE")
        t = self.c.admit(Kind.FINAL_CAPTURE, 240)
        self.assertEqual(t.timeout_seconds, 10)
        self.clock.advance(10); self.c.settle(t, "COMPLETE")
        self.assertEqual(self.c.aggregate()["remaining_seconds"], 5)
        self.assertEqual(self.c.aggregate()["finish_operations_completed"], 3)

    def test_near_deadline_no_five_second_floor(self):
        self.clock.advance(474.9)
        self.c.final_stage = 2; self.c.begin_finish()
        t = self.c.admit(Kind.FINAL_CAPTURE, 240)
        self.assertAlmostEqual(t.timeout_seconds, 0.1)

    def test_request_is_never_inflated(self):
        t = self.c.admit(Kind.COMMAND, 0.2)
        self.assertEqual(t.timeout_seconds, 0.2)

    def test_subminimum_is_denied(self):
        self.assertIsNone(self.c.admit(Kind.MODEL, 0.01))

    def test_earlier_finish_stops_optional(self):
        self.c.begin_finish()
        self.assertIsNone(self.c.admit(Kind.SCOUT, 5))
        self.assertIsNotNone(self.c.admit(Kind.FINAL_EDIT, 5))

    def test_out_of_order_final_is_denied(self):
        self.assertIsNone(self.c.admit(Kind.FINAL_TEST, 60))
        self.assertEqual(self.c.aggregate()["finish_operations_completed"], 0)

    def test_single_flight(self):
        t = self.c.admit(Kind.MODEL, 10)
        self.assertIsNone(self.c.admit(Kind.SCOUT, 10))
        self.c.settle(t, "COMPLETE")
        self.assertIsNotNone(self.c.admit(Kind.SCOUT, 10))

    def test_actual_failure_is_counted(self):
        t = self.c.admit(Kind.COMPACTION, 10)
        self.c.settle(t, "FAILED")
        self.assertEqual(self.c.aggregate()["counts"]["FAILED"], 1)

    def test_unfinished_is_not_completion(self):
        t = self.c.admit(Kind.MODEL, 10)
        self.c.settle(t, "UNFINISHED")
        self.assertEqual(self.c.aggregate()["counts"]["COMPLETE"], 0)
        self.assertEqual(self.c.aggregate()["counts"]["UNFINISHED"], 1)

    def test_unsettled_operation_fences(self):
        t = self.c.admit(Kind.MODEL, 10)
        self.c.settle(t, "UNFINISHED", cancellation_settled=False)
        self.assertTrue(self.c.aggregate()["hold"])
        self.assertIsNone(self.c.admit(Kind.FINAL_EDIT, 10))

    def test_return_after_deadline_never_counts_success(self):
        t = self.c.admit(Kind.MODEL, 10)
        self.clock.advance(11)
        self.assertEqual(self.c.settle(t, "COMPLETE")["status"], "UNFINISHED")
        self.assertTrue(self.c.aggregate()["hold"])

    def test_wrong_ticket_does_not_settle_active(self):
        t = self.c.admit(Kind.MODEL, 10)
        from dataclasses import replace
        with self.assertRaises(ValueError): self.c.settle(replace(t), "COMPLETE")
        self.assertEqual(self.c.aggregate()["active_count"], 1)

    def test_final_failure_does_not_mark_phase_complete(self):
        t = self.c.admit(Kind.FINAL_EDIT, 10)
        self.c.settle(t, "FAILED")
        self.assertTrue(self.c.aggregate()["hold"])
        self.assertEqual(self.c.aggregate()["finish_operations_completed"], 0)

    def test_bad_numbers_are_rejected_under_optimized_python(self):
        for value in (True, False, float("nan"), float("inf"), -1, 0, "10"):
            with self.assertRaises(ValueError): DeadlineContract(value)
            with self.assertRaises(ValueError): self.c.admit(Kind.MODEL, value)

    def test_bad_kind_cannot_escape_fixed_public_vocabulary(self):
        with self.assertRaises(ValueError): self.c.admit("PRIVATE_TASK_SECRET", 10)
        self.assertNotIn("PRIVATE_TASK_SECRET", json.dumps(self.c.aggregate()))

    def test_invalid_reserve_rejected(self):
        with self.assertRaises(ValueError): Reserve(tests=0)
        with self.assertRaises(ValueError): DeadlineContract(90)

    def test_regressing_clock_fences(self):
        self.clock.advance(-1)
        with self.assertRaises(ValueError): self.c.admit(Kind.MODEL, 1)
        self.assertTrue(self.c.fenced)

    def test_completed_operations_never_claim_quality(self):
        self.finish(Kind.FINAL_EDIT, 1)
        self.finish(Kind.FINAL_TEST, 1)
        self.finish(Kind.FINAL_CAPTURE, 1)
        a = self.c.aggregate()
        self.assertEqual(a["quality_promotion"], "UNPROVEN")
        self.assertEqual(a["native_compatibility"], "HOLD_UNVERIFIED")
        self.assertIsNone(a["native_tests_passed"])
        self.assertIsNone(a["official_score"])


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_clamped_timeout_is_passed_and_value_private(self):
        clock = Clock(); c = DeadlineContract(clock=clock)
        seen = []
        async def operation(timeout):
            seen.append(timeout); clock.advance(2)
            return "PRIVATE_PROMPT_PATCH_OR_TASK_SECRET"
        result = await c.run(Kind.MODEL, 420, operation)
        self.assertEqual(seen, [389.9])
        self.assertEqual(result.value, "PRIVATE_PROMPT_PATCH_OR_TASK_SECRET")
        self.assertNotIn("PRIVATE_PROMPT", json.dumps(c.aggregate()))

    async def test_failure_receipt_redacts_exception(self):
        c = DeadlineContract(clock=Clock())
        async def operation(timeout): raise RuntimeError("PRIVATE_TASK_SECRET")
        result = await c.run(Kind.SCOUT, 1, operation)
        self.assertEqual(result.receipt["status"], "FAILED")
        self.assertNotIn("PRIVATE_TASK_SECRET", json.dumps(c.aggregate()))

    async def test_blocked_cooperative_call_unfinished(self):
        c = DeadlineContract(clock=Clock(), minimum_call_seconds=0.001)
        async def operation(timeout): await asyncio.Event().wait()
        result = await c.run(Kind.COMPACTION, 0.002, operation, cancellation_grace_seconds=0.005)
        self.assertEqual(result.receipt["status"], "UNFINISHED")
        self.assertTrue(result.receipt["cancellation_settled"])

    async def test_cancellation_grace_is_budgeted_before_admission(self):
        clock = Clock(); c = DeadlineContract(clock=clock, minimum_call_seconds=0.001)
        clock.advance(389.98)
        async def operation(timeout):
            try: await asyncio.Event().wait()
            except asyncio.CancelledError:
                clock.advance(timeout + 0.01)
                raise
        result = await c.run(Kind.MODEL, 0.002, operation, cancellation_grace_seconds=0.01)
        self.assertEqual(result.receipt["status"], "UNFINISHED")
        self.assertTrue(result.receipt["deadline_overrun"])
        self.assertFalse(result.receipt["settlement_overrun"])
        self.assertFalse(c.aggregate()["hold"])
        self.assertGreaterEqual(c.aggregate()["remaining_seconds"], 90)
        self.assertIsNotNone(c.admit(Kind.FINAL_EDIT, 15))

    async def test_settlement_that_does_not_fit_is_denied(self):
        clock = Clock(); c = DeadlineContract(clock=clock, minimum_call_seconds=0.001)
        clock.advance(389.998)
        async def operation(timeout): self.fail("grace does not fit")
        result = await c.run(Kind.MODEL, 0.002, operation, cancellation_grace_seconds=0.01)
        self.assertEqual(result.receipt["status"], "DENIED")
        self.assertGreaterEqual(c.aggregate()["remaining_seconds"], 90)

    async def test_cancellation_late_beyond_budgeted_grace_holds(self):
        clock = Clock(); c = DeadlineContract(clock=clock, minimum_call_seconds=0.001)
        async def operation(timeout):
            try: await asyncio.Event().wait()
            except asyncio.CancelledError:
                clock.advance(timeout + 0.02)
                raise
        result = await c.run(Kind.MODEL, 0.002, operation, cancellation_grace_seconds=0.01)
        self.assertEqual(result.receipt["status"], "UNFINISHED")
        self.assertTrue(result.receipt["settlement_overrun"])
        self.assertTrue(c.aggregate()["hold"])

    async def test_cancellation_survivor_holds_and_stays_unfinished(self):
        c = DeadlineContract(clock=Clock(), minimum_call_seconds=0.001)
        release = asyncio.Event()
        async def operation(timeout):
            try: await asyncio.Event().wait()
            except asyncio.CancelledError: await release.wait()
        result = await c.run(Kind.MODEL, 0.002, operation, cancellation_grace_seconds=0.002)
        self.assertEqual(result.receipt["status"], "UNFINISHED")
        self.assertFalse(result.receipt["cancellation_settled"])
        self.assertTrue(c.aggregate()["hold"])
        self.assertIsNone(c.admit(Kind.FINAL_EDIT, 1))
        release.set(); await asyncio.sleep(0)

    async def test_denied_operation_is_never_called(self):
        clock = Clock(); c = DeadlineContract(clock=clock); clock.advance(390)
        async def operation(timeout): self.fail("denied operation ran")
        result = await c.run(Kind.SCOUT, 1, operation)
        self.assertEqual(result.receipt["status"], "DENIED")

    async def test_external_cancellation_fences_and_propagates(self):
        c = DeadlineContract(clock=Clock()); entered = asyncio.Event()
        async def operation(timeout):
            entered.set(); await asyncio.Event().wait()
        wrapper = asyncio.create_task(c.run(Kind.MODEL, 1, operation))
        await entered.wait(); wrapper.cancel()
        with self.assertRaises(asyncio.CancelledError): await wrapper
        self.assertTrue(c.aggregate()["hold"])
        self.assertEqual(c.aggregate()["counts"]["UNFINISHED"], 1)

    async def test_synchronous_callback_creation_error_is_failed(self):
        c = DeadlineContract(clock=Clock())
        def operation(timeout): raise RuntimeError("PRIVATE_SECRET")
        with self.assertRaises(RuntimeError): await c.run(Kind.MODEL, 1, operation)
        self.assertEqual(c.aggregate()["counts"]["FAILED"], 1)


if __name__ == "__main__": unittest.main()
