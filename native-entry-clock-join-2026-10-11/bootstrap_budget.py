"""Original deadline utility for a new reviewed external bootstrap only.

It never reads/replaces a notebook or starts a process. The old bootstrap is
preserved. New protocol fields and caller-observed original marks are required;
historical timeout_budget values are never fallback defaults.
"""
from route_planner import observed_deadline, integer
from entry_join import need, parse, sha


def parent_timeout(protocol_raw,expected_protocol_sha256,*,first_cell_start,observed_origin,current_monotonic):
    protocol=parse(protocol_raw)
    need(sha(protocol_raw)==expected_protocol_sha256,"BOOTSTRAP_PROTOCOL_SOURCE_DRIFT")
    result=observed_deadline(protocol,first_cell_start=first_cell_start,
        observed_origin=observed_origin,current_monotonic=current_monotonic)
    tail=integer(protocol.get("entry_parent_cleanup_tail_seconds"),"EXPLICIT_PARENT_CLEANUP_TAIL_REQUIRED")
    headroom=result["session_timeout_seconds"]-result["allocation_reserved_seconds"]-result["first_cell_budget_seconds"]
    need(0<tail<=headroom,"PARENT_CLEANUP_EXCEEDS_REVIEWED_SESSION_HEADROOM")
    return {**result,"parent_cleanup_tail_seconds":tail,
            "parent_deadline_from_first_cell_seconds":result["first_cell_budget_seconds"]+tail,
            "parent_absolute_deadline":result["absolute_deadline"]+tail,
            "subprocess_timeout_seconds":result["remaining_seconds"]+tail,
            "readiness_absolute_deadline":first_cell_start+result["readiness_budget_seconds"],
            "scope":"Prepared deadline arithmetic; no watchdog cleanup duration or native completion is guaranteed."}
