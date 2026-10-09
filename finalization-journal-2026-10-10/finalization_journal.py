"""Original append-only finalization evidence; no verifier/process/API execution.

The journal observes a reviewed adapter. It does not validate task assertions,
stop processes, or qualify a native score. Every output file is newly created;
staging files survive interruption and are never removed or renamed.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time

MAX_EVENT = 8192
MAX_XML = 16 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
EVENT = re.compile(r"event_([0-9]{6})\.json\Z")
ZERO = "0" * 64


def finite(v, *, positive=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("finite numeric value required")
    v = float(v)
    if not math.isfinite(v) or (v <= 0 if positive else v < 0):
        raise ValueError("invalid numeric value")
    return v


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw): return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Ticket:
    timeout_seconds: float
    started: float
    command_deadline: float


@dataclass(frozen=True)
class Observation:
    exit_code: int
    timed_out: bool
    patch_sha256: str
    patch_bytes: int
    retained_xml: bytes
    cat_xml: bytes
    validator_xml: bytes
    strict_validator_ok: bool


class FinalizationJournal:
    """Single-writer immutable journal, using exclusive hardlink publication.

    Begin must durably publish START before a caller may invoke its verifier.
    The adapter must enforce the returned cap. One active ticket is allowed.
    After capture, a separate supervisor cleanup observation is required before
    COMMIT. Calls below never execute the verifier or supervise any process.
    """
    def __init__(self, directory, *, absolute_deadline, capture_reserve_seconds=5,
                 clock=time.monotonic):
        p = Path(directory)
        if not p.name.startswith("finalize-evidence-"):
            raise ValueError("new finalize-evidence-* directory required")
        self.clock = clock
        self.now_last = finite(clock())
        self.deadline = finite(absolute_deadline, positive=True)
        self.reserve = finite(capture_reserve_seconds, positive=True)
        if self.deadline - self.now_last <= self.reserve:
            raise ValueError("no finalization window")
        p.mkdir(exist_ok=False)  # never opens an existing journal for mutation
        self.path = p.resolve(strict=True)
        self.lock = threading.RLock()
        self.previous = ZERO
        self.count = 0
        self.active = None
        self.poisoned = False
        self.capture_recorded = False
        self.capture_consistent = False
        self.pass_observation = False
        self.closed = False

    def now(self):
        v = finite(self.clock())
        if v < self.now_last:
            self.poisoned = True
            raise ValueError("monotonic clock regressed")
        self.now_last = v
        return v

    def _fsync_directory(self):
        fd = os.open(self.path, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def _append(self, stage, values):
        if self.poisoned or self.closed:
            raise RuntimeError("journal is fenced")
        row = {"schema": "original_finalization_journal_v1", "index": self.count + 1,
               "previous_sha256": self.previous, "stage": stage, "values": values}
        raw = canonical(row)
        if len(raw) > MAX_EVENT: raise ValueError("event byte cap")
        stage_path = self.path / ("stage_%06d.json" % row["index"])
        event_path = self.path / ("event_%06d.json" % row["index"])
        try:
            # The staging file remains as immutable historical evidence.
            with stage_path.open("xb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            self._fsync_directory()
            # Same-directory hardlink publication is atomic and refuses any
            # existing target. No rename, replace, delete or cleanup occurs.
            os.link(stage_path, event_path)
            self._fsync_directory()
        except BaseException:
            self.poisoned = True
            raise
        self.previous = digest(raw)
        self.count += 1
        return self.previous

    def begin(self, requested_timeout_seconds=240):
        with self.lock:
            if self.active is not None or self.capture_recorded:
                raise RuntimeError("one verifier attempt per journal")
            requested = finite(requested_timeout_seconds, positive=True)
            n = self.now()
            cap = min(requested, self.deadline - n - self.reserve)
            if cap <= 0:
                self._append("DENIED", {"reason": "NO_CAPTURE_WINDOW"})
                self.closed = True
                return None
            t = Ticket(cap, n, n + cap)
            self._append("START", {"planned_timeout_upper_bound_seconds": cap,
                                    "capture_reserve_seconds": self.reserve})
            # Publication and fsync consume time too. Recompute after durable
            # START; callers cannot begin using a stale pre-write timeout.
            cap = min(cap, self.deadline - self.now() - self.reserve)
            if cap <= 0:
                self._append("ABORT", {"reason": "START_WRITE_CONSUMED_WINDOW"})
                self.closed = True
                return None
            t = Ticket(cap, self.now_last, self.now_last + cap)
            self.active = t
            return t

    def command_timeout(self, ticket):
        """Recheck immediately before the caller starts the reviewed command."""
        with self.lock:
            if self.active is not ticket or self.poisoned or self.closed or self.capture_recorded:
                raise ValueError("wrong or fenced ticket")
            cap = min(ticket.timeout_seconds, ticket.command_deadline - self.now(),
                      self.deadline - self.now_last - self.reserve)
            if cap <= 0:
                self._append("ABORT", {"reason": "COMMAND_START_DEADLINE"})
                self.closed = True
                return None
            return cap

    def returned(self, ticket, observation):
        with self.lock:
            if self.active is not ticket or self.capture_recorded:
                raise ValueError("wrong active ticket")
            if not isinstance(observation, Observation): raise ValueError("typed observation required")
            o = observation
            if type(o.exit_code) is not int or type(o.timed_out) is not bool or type(o.strict_validator_ok) is not bool:
                raise ValueError("strict outcome types required")
            if type(o.patch_bytes) is not int or o.patch_bytes < 0 or not isinstance(o.patch_sha256, str) or not HEX.fullmatch(o.patch_sha256):
                raise ValueError("invalid patch binding")
            if any(type(b) is not bytes or len(b) > MAX_XML for b in (o.retained_xml, o.cat_xml, o.validator_xml)):
                raise ValueError("bounded XML bytes required")
            n = self.now()
            late = n > ticket.command_deadline
            self._append("RETURN", {"exit_code": o.exit_code, "timed_out": o.timed_out,
                                    "elapsed_seconds": n - ticket.started, "late_return": late})
            if self.now() >= self.deadline:
                self._append("ABORT", {"reason": "CAPTURE_DEADLINE"})
                self.closed = True
                return False
            hashes = [digest(b) for b in (o.retained_xml, o.cat_xml, o.validator_xml)]
            # Nonzero pytest exits legitimately skip cat/strict validation.
            # Their retained XML still records a completed negative observation.
            complete = o.patch_bytes > 0 and bool(o.retained_xml) and (o.exit_code != 0 or hashes[0] == hashes[1] == hashes[2])
            passed = complete and not late and not o.timed_out and o.exit_code == 0 and o.strict_validator_ok
            if self.now() >= self.deadline:
                self._append("ABORT", {"reason": "HASHING_DEADLINE"})
                self.closed = True
                return False
            self._append("CAPTURE", {"patch_sha256": o.patch_sha256, "patch_bytes": o.patch_bytes,
                                     "xml_sha256": hashes, "xml_bytes": [len(b) for b in (o.retained_xml, o.cat_xml, o.validator_xml)],
                                     "capture_consistent": complete, "strict_validator_ok": o.strict_validator_ok,
                                     "passed_test_observation": passed})
            self.capture_recorded = True
            self.capture_consistent = complete
            self.pass_observation = passed
            return complete

    def close(self, *, cleanup_verified, survivor_count):
        """Project a separate reviewed supervisor receipt, never pytest exit.

        Unknown cleanup or any survivor forbids successful evidence commit.
        This function does not stop, kill, wait, reset or remove anything.
        """
        with self.lock:
            if type(cleanup_verified) is not bool or (survivor_count is not None and (type(survivor_count) is not int or survivor_count < 0)):
                raise ValueError("strict cleanup evidence required")
            clear = cleanup_verified and survivor_count == 0
            self._append("CLEANUP", {"verified": cleanup_verified, "survivor_count": survivor_count, "clear": clear})
            before = self.now() < self.deadline
            status = "COMMITTED_CAPTURE" if before and clear and self.capture_recorded and self.capture_consistent else "HOLD"
            sha = self._append("COMMIT", {"status": status, "passed_test_observation": self.pass_observation if status == "COMMITTED_CAPTURE" else False,
                                          "native_compatibility": "HOLD_UNVERIFIED", "official_score": None})
            # A slow fsync may finish beyond the deadline; append a terminal
            # deadline revocation. A reader uses the last terminal event.
            if self.now() >= self.deadline:
                sha = self._append("ABORT", {"reason": "COMMIT_WRITE_DEADLINE"})
                status = "HOLD"
            self.closed = True
            return {"status": status, "last_event_sha256": sha, "native_compatibility": "HOLD_UNVERIFIED", "official_score": None}


def _values(row, prior):
    """Exact event schemas; unknown user strings never enter projections."""
    stage, v = row["stage"], row["values"]
    keys = {
        "START": {"planned_timeout_upper_bound_seconds", "capture_reserve_seconds"},
        "DENIED": {"reason"}, "ABORT": {"reason"},
        "RETURN": {"exit_code", "timed_out", "elapsed_seconds", "late_return"},
        "CAPTURE": {"patch_sha256", "patch_bytes", "xml_sha256", "xml_bytes", "capture_consistent", "strict_validator_ok", "passed_test_observation"},
        "CLEANUP": {"verified", "survivor_count", "clear"},
        "COMMIT": {"status", "passed_test_observation", "native_compatibility", "official_score"},
    }[stage]
    if type(v) is not dict or set(v) != keys: raise ValueError("event value schema")
    def boolean(name):
        if type(v[name]) is not bool: raise ValueError("event boolean schema")
    def integer(value, minimum=0):
        if type(value) is not int or value < minimum: raise ValueError("event integer schema")
    if stage == "START":
        finite(v["planned_timeout_upper_bound_seconds"], positive=True)
        finite(v["capture_reserve_seconds"], positive=True)
    elif stage in ("DENIED", "ABORT"):
        allowed = {"NO_CAPTURE_WINDOW"} if stage == "DENIED" else {"START_WRITE_CONSUMED_WINDOW", "COMMAND_START_DEADLINE", "CAPTURE_DEADLINE", "HASHING_DEADLINE", "COMMIT_WRITE_DEADLINE"}
        if v["reason"] not in allowed: raise ValueError("unknown terminal reason")
    elif stage == "RETURN":
        if type(v["exit_code"]) is not int: raise ValueError("exit type")
        boolean("timed_out"); boolean("late_return"); finite(v["elapsed_seconds"])
    elif stage == "CAPTURE":
        integer(v["patch_bytes"])
        if type(v["patch_sha256"]) is not str or not HEX.fullmatch(v["patch_sha256"]): raise ValueError("patch hash")
        if type(v["xml_sha256"]) is not list or len(v["xml_sha256"]) != 3 or any(type(x) is not str or not HEX.fullmatch(x) for x in v["xml_sha256"]): raise ValueError("XML hashes")
        if type(v["xml_bytes"]) is not list or len(v["xml_bytes"]) != 3: raise ValueError("XML byte schema")
        for x in v["xml_bytes"]:
            integer(x)
            if x > MAX_XML: raise ValueError("XML byte cap")
        for name in ("capture_consistent", "strict_validator_ok", "passed_test_observation"): boolean(name)
        ret = prior.get("RETURN")
        if ret is None: raise ValueError("capture without return")
        same = len(set(v["xml_sha256"])) == 1 and len(set(v["xml_bytes"])) == 1
        consistent = v["patch_bytes"] > 0 and v["xml_bytes"][0] > 0 and (ret["exit_code"] != 0 or same)
        passed = consistent and not ret["late_return"] and not ret["timed_out"] and ret["exit_code"] == 0 and v["strict_validator_ok"]
        if v["capture_consistent"] != consistent or v["passed_test_observation"] != passed: raise ValueError("capture derivation mismatch")
    elif stage == "CLEANUP":
        boolean("verified"); boolean("clear")
        if v["survivor_count"] is not None: integer(v["survivor_count"])
        if v["clear"] != (v["verified"] and v["survivor_count"] == 0): raise ValueError("cleanup derivation mismatch")
    else:
        boolean("passed_test_observation")
        if v["status"] not in ("COMMITTED_CAPTURE", "HOLD") or v["native_compatibility"] != "HOLD_UNVERIFIED" or v["official_score"] is not None: raise ValueError("terminal value schema")
        complete = prior.get("CAPTURE", {}).get("capture_consistent", False) and prior.get("CLEANUP", {}).get("clear", False) and "START" in prior and "RETURN" in prior
        expected_pass = complete and prior.get("CAPTURE", {}).get("passed_test_observation", False) and v["status"] == "COMMITTED_CAPTURE"
        if v["status"] == "COMMITTED_CAPTURE" and not complete: raise ValueError("commit without complete evidence")
        if v["passed_test_observation"] != expected_pass: raise ValueError("commit derivation mismatch")
    prior[stage] = v


def inspect_journal(directory):
    """Bounded read-only consistency projection, not authenticated provenance."""
    path = Path(directory)
    if path.is_symlink() or not path.is_dir(): raise ValueError("regular journal directory required")
    entries = []
    for entry in path.iterdir():
        entries.append(entry)
        if len(entries) > 256: raise ValueError("directory inventory cap")
    paths = sorted(p for p in entries if EVENT.fullmatch(p.name))
    if len(paths) > 100: raise ValueError("event count cap")
    transitions = {
        None: {"START", "DENIED", "CLEANUP"},
        "START": {"RETURN", "ABORT", "CLEANUP"},
        "RETURN": {"CAPTURE", "ABORT", "CLEANUP"},
        "CAPTURE": {"CLEANUP", "ABORT"}, "CLEANUP": {"COMMIT"},
        "COMMIT": {"ABORT"}, "ABORT": set(), "DENIED": set(),
    }
    previous, rows, prior, state = ZERO, [], {}, None
    for i, p in enumerate(paths, 1):
        if p.is_symlink() or not p.is_file() or p.name != "event_%06d.json" % i: raise ValueError("regular ordered event required")
        with p.open("rb") as f: raw = f.read(MAX_EVENT + 1)
        if len(raw) > MAX_EVENT: raise ValueError("event byte cap")
        row = json.loads(raw)
        if type(row) is not dict or set(row) != {"schema", "index", "previous_sha256", "stage", "values"} or canonical(row) != raw or row.get("schema") != "original_finalization_journal_v1" or type(row.get("index")) is not int or row["index"] != i or row.get("previous_sha256") != previous: raise ValueError("event chain or canonical bytes invalid")
        stage = row.get("stage")
        if type(stage) is not str or stage not in transitions[state]: raise ValueError("invalid event transition")
        _values(row, prior)
        state = stage; previous = digest(raw); rows.append(row)
    status = "UNFINISHED" if "START" in prior else "NO_DURABLE_START"
    if state in ("ABORT", "DENIED"): status = "HOLD"
    elif state == "COMMIT": status = prior["COMMIT"]["status"]
    names = {p.name for p in entries}
    return {"schema": "original_finalization_projection_v1", "status": status,
            "event_count": len(rows), "durable_start": "START" in prior,
            "return_observed": "RETURN" in prior, "capture_observed": "CAPTURE" in prior,
            "unpublished_staging_count": sum(p.name.startswith("stage_") and p.name.replace("stage_", "event_", 1) not in names for p in entries),
            "last_event_sha256": previous, "native_compatibility": "HOLD_UNVERIFIED",
            "native_tests_passed": None, "quality_promotion": "UNPROVEN", "official_score": None}
