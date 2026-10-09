"""Original source-only deadline admission contract; no model, shell or API code.

Only cancellation-cooperative adapters can honor this contract. Returning from a
callback proves that operation finished, never that tests or patch are correct.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Awaitable, Callable


class Kind(str, Enum):
    MODEL = "model"
    COMMAND = "command"
    SCOUT = "scout"
    COMPACTION = "compaction"
    FINAL_EDIT = "final_edit"
    FINAL_TEST = "final_test"
    FINAL_CAPTURE = "final_capture"


FINAL = (Kind.FINAL_EDIT, Kind.FINAL_TEST, Kind.FINAL_CAPTURE)


def number(value: float, name: str, *, positive: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name)
    value = float(value)
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(name)
    return value


@dataclass(frozen=True)
class Reserve:
    edit: float = 15.0
    tests: float = 60.0
    capture: float = 10.0
    settle: float = 5.0

    def __post_init__(self):
        for name in ("edit", "tests", "capture", "settle"):
            object.__setattr__(self, name, number(getattr(self, name), name))

    @property
    def total(self) -> float:
        return self.edit + self.tests + self.capture + self.settle


@dataclass(frozen=True)
class Ticket:
    index: int
    kind: Kind
    timeout_seconds: float
    started: float
    operation_deadline: float
    settlement_seconds: float


@dataclass(frozen=True)
class Outcome:
    receipt: dict
    value: object = None  # private; never included in the public aggregate


class DeadlineContract:
    """Single-flight contract with a reserved final edit -> test -> capture phase.

    The adapter must enforce the supplied timeout and honor cancellation. A
    timed-out call becomes UNFINISHED even if cancellation later settles it.
    A cancellation survivor fences the contract permanently (HOLD).
    """

    def __init__(self, budget_seconds: float = 480, reserve: Reserve = Reserve(),
                 *, clock: Callable[[], float] = time.monotonic,
                 minimum_call_seconds: float = 0.05):
        self.budget = number(budget_seconds, "budget")
        if not isinstance(reserve, Reserve) or reserve.total >= self.budget:
            raise ValueError("reserve must fit inside budget")
        self.reserve = reserve
        self.clock = clock
        self.minimum = number(minimum_call_seconds, "minimum")
        self.started = number(clock(), "clock", positive=False)
        self.last_clock = self.started
        self.deadline = self.started + self.budget
        self.finishing = False
        self.final_stage = 0
        self.fenced = False
        self.active: Ticket | None = None
        self.receipts: list[dict] = []
        self.denied: list[dict] = []

    def _now(self) -> float:
        now = number(self.clock(), "clock", positive=False)
        if now < self.last_clock:
            self.fenced = True
            raise ValueError("monotonic clock regressed")
        self.last_clock = now
        return now

    def begin_finish(self) -> None:
        self.finishing = True

    def _deny(self, kind: Kind, reason: str, now: float) -> None:
        self.denied.append({"kind": kind.value, "reason": reason,
                            "elapsed_seconds": round(now - self.started, 6)})

    def admit(self, kind: Kind, requested_seconds: float,
              *, settlement_seconds: float = 0.0) -> Ticket | None:
        if not isinstance(kind, Kind):
            raise ValueError("kind must be a fixed Kind enum")
        requested = number(requested_seconds, "requested")
        settlement = number(settlement_seconds, "settlement", positive=False)
        if settlement > self.reserve.settle:
            raise ValueError("settlement exceeds configured grace cap")
        now = self._now()
        if self.fenced or self.active is not None:
            self._deny(kind, "HOLD_UNSETTLED_OR_ACTIVE", now)
            return None
        if kind in FINAL:
            self.finishing = True
            if self.final_stage >= len(FINAL) or kind != FINAL[self.final_stage]:
                self._deny(kind, "FINAL_ORDER", now)
                return None
            downstream = {
                Kind.FINAL_EDIT: self.reserve.tests + self.reserve.capture + self.reserve.settle,
                Kind.FINAL_TEST: self.reserve.capture + self.reserve.settle,
                Kind.FINAL_CAPTURE: self.reserve.settle,
            }[kind]
        else:
            if self.finishing:
                self._deny(kind, "FINISH_PHASE", now)
                return None
            downstream = self.reserve.total
        available = self.deadline - now - downstream - settlement
        if available < self.minimum:
            if kind not in FINAL:
                self.begin_finish()
            self._deny(kind, "NO_OPERATION_WINDOW", now)
            return None
        timeout = min(requested, available)
        if timeout < self.minimum:
            self._deny(kind, "REQUEST_BELOW_MINIMUM", now)
            return None
        ticket = Ticket(len(self.receipts), kind, timeout, now, now + timeout, settlement)
        self.active = ticket
        return ticket

    def settle(self, ticket: Ticket, status: str, *, cancellation_settled: bool = True) -> dict:
        if self.active is not ticket or status not in ("COMPLETE", "FAILED", "UNFINISHED"):
            raise ValueError("wrong active ticket or status")
        if type(cancellation_settled) is not bool:
            raise ValueError("cancellation_settled")
        now = self._now()
        overran = now > ticket.operation_deadline + 0.001
        settlement_overran = now > ticket.operation_deadline + ticket.settlement_seconds + 0.001
        if overran and status != "UNFINISHED":
            status = "UNFINISHED"
            self.fenced = True
        if settlement_overran:
            status = "UNFINISHED"
            self.fenced = True
        if not cancellation_settled:
            status = "UNFINISHED"
            self.fenced = True
        row = {"index": ticket.index, "kind": ticket.kind.value, "status": status,
               "timeout_seconds": round(ticket.timeout_seconds, 6),
               "elapsed_seconds": round(now - ticket.started, 6),
               "deadline_overrun": overran,
               "settlement_seconds_budgeted": ticket.settlement_seconds,
               "settlement_overrun": settlement_overran,
               "cancellation_settled": cancellation_settled}
        self.receipts.append(row)
        self.active = None
        # Even a settled timeout cannot prove this final stage finished.
        if ticket.kind in FINAL:
            if status == "COMPLETE":
                self.final_stage += 1
            else:
                self.fenced = True
        return row

    async def run(self, kind: Kind, requested_seconds: float,
                  operation: Callable[[float], Awaitable[object]],
                  *, cancellation_grace_seconds: float = 0.1) -> Outcome:
        """Pass a clamped timeout to an async adapter; bounded cancellation wait.

        Sync/blocking code and detached external work cannot be preempted here.
        Do not integrate such adapters until an owned supervisor proves stop.
        """
        grace = number(cancellation_grace_seconds, "grace", positive=False)
        grace = min(grace, self.reserve.settle)
        ticket = self.admit(kind, requested_seconds, settlement_seconds=grace)
        if ticket is None:
            return Outcome({"status": "DENIED", "reason": self.denied[-1]["reason"]})
        task = None
        try:
            # Synchronous work inside operation creation is outside async
            # enforcement: the adapter contract explicitly forbids it.
            task = asyncio.ensure_future(operation(ticket.timeout_seconds))
            done, _ = await asyncio.wait({task}, timeout=ticket.timeout_seconds)
            if done:
                try:
                    value = task.result()
                except asyncio.CancelledError:
                    return Outcome(self.settle(ticket, "UNFINISHED"))
                except Exception:
                    return Outcome(self.settle(ticket, "FAILED"))
                return Outcome(self.settle(ticket, "COMPLETE"), value)
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=grace)
            if done:
                # Retrieve an exception without publishing its message/type.
                if not task.cancelled():
                    task.exception()
            else:
                task.add_done_callback(_consume_exception)
            return Outcome(self.settle(ticket, "UNFINISHED", cancellation_settled=bool(done)))
        except asyncio.CancelledError:
            if task is not None:
                task.cancel()
                task.add_done_callback(_consume_exception)
            self.settle(ticket, "UNFINISHED", cancellation_settled=False)
            raise
        except Exception:
            if self.active is ticket:
                self.settle(ticket, "FAILED")
            raise

    def aggregate(self) -> dict:
        now = self._now()
        statuses = ("COMPLETE", "FAILED", "UNFINISHED")
        return {"schema": "original_deadline_contract_v1", "scope": "source_only_offline_contract",
                "budget_seconds": self.budget, "finish_reserve_seconds": self.reserve.total,
                "remaining_seconds": max(0.0, round(self.deadline - now, 6)),
                "counts": {s: sum(r["status"] == s for r in self.receipts) for s in statuses},
                "active_count": int(self.active is not None), "denied_count": len(self.denied),
                "finish_operations_completed": self.final_stage,
                "hold": self.fenced, "native_compatibility": "HOLD_UNVERIFIED",
                "native_tests_passed": None, "official_score": None,
                "quality_promotion": "UNPROVEN", "operations": list(self.receipts),
                "denials": list(self.denied)}


def _consume_exception(task: asyncio.Future) -> None:
    if not task.cancelled():
        task.exception()
