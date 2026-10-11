"""Original read-only planner: static prepared assets, never a launch command.

Only metadata and restricted Python AST expressions are inspected. No organizer,
bootstrap, notebook, SDK or model code is imported or executed. Reports always
retain HOLD for uncollected coordinator/native evidence.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys

from entry_join import Hold, encode, finite, need, parse, read_pin, sha, task_list

FILES={"protocol","build","bootstrap","candidate","kernel_metadata",
       "dataset_metadata","native_supervisor","native_watchdog","preregistration"}
NAME=re.compile(r"^[A-Za-z0-9_-]{1,100}\.py$")


def integer(value,reason):
    need(type(value) is int and 0<=value<=10**7,reason)
    return value


def protocol_envelope(protocol):
    """One protocol-derived first-cell envelope; no historical fallback."""
    absolute=integer(protocol.get("absolute_seconds_including_model_load_and_allocation_reserve"),"ABSOLUTE_BUDGET_UNKNOWN")
    allocation=integer(protocol.get("allocation_overhead_seconds_reserved"),"ALLOCATION_BUDGET_UNKNOWN")
    deadline=integer(protocol.get("deadline_seconds_from_first_cell"),"FIRST_CELL_BUDGET_UNKNOWN")
    reserve=integer(protocol.get("task_reserve_seconds"),"TASK_RESERVE_UNKNOWN")
    readiness=integer(protocol.get("readiness_budget_seconds"),"READINESS_BUDGET_UNKNOWN")
    session=integer(protocol.get("session_timeout_seconds"),"SESSION_BUDGET_UNKNOWN")
    components=protocol.get("reserve_arithmetic_seconds")
    need(type(components) is dict and len(components)>0
         and sum(integer(v,"RESERVE_COMPONENT_UNKNOWN") for v in components.values())==reserve,"TASK_RESERVE_ARITHMETIC")
    need(0<allocation<absolute<=session and absolute-allocation==deadline
         and 0<reserve<deadline and deadline-reserve==readiness,"PROTOCOL_BUDGET_CONFLICT")
    return {"first_cell_budget_seconds":deadline,"readiness_budget_seconds":readiness,
            "task_reserve_seconds":reserve,"allocation_reserved_seconds":allocation,
            "absolute_including_allocation_seconds":absolute,"session_timeout_seconds":session}


def observed_deadline(protocol,*,first_cell_start,observed_origin,current_monotonic):
    """Validate actual supplied same-process marks; does not authenticate them.

    A coordinator must observe the original first-cell mark, never replace it
    with loader/entry start. This pure function never obtains a new origin.
    """
    need(all(finite(v) for v in (first_cell_start,observed_origin,current_monotonic)),"LIVE_CLOCK_TYPE_OR_FINITE")
    need(type(first_cell_start) is type(observed_origin) and first_cell_start==observed_origin,
         "FIRST_CELL_ORIGIN_RESET_OR_CONFLICT")
    need(current_monotonic>=first_cell_start,"MONOTONIC_ORIGIN_IN_FUTURE")
    envelope=protocol_envelope(protocol)
    deadline=first_cell_start+envelope["first_cell_budget_seconds"]
    need(current_monotonic<deadline,"PROTOCOL_DEADLINE_ALREADY_EXHAUSTED")
    return {**envelope,"original_first_cell_start":first_cell_start,"absolute_deadline":deadline,
            "elapsed_from_first_cell_seconds":current_monotonic-first_cell_start,
            "remaining_seconds":deadline-current_monotonic,"native_authenticity_established":False}


def affine(node,names):
    """Parse +/- affine scalars only; do not eval an expression."""
    if isinstance(node,ast.Name) and node.id in names:return {node.id:1.0},0.0
    if isinstance(node,ast.Constant) and type(node.value) in (int,float) and finite(node.value):return {},float(node.value)
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) \
       and node.func.value.id=="time" and node.func.attr=="monotonic" and not node.args and not node.keywords:
        return {"time.monotonic()":1.0},0.0
    if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub)):
        left,a=affine(node.left,names);right,b=affine(node.right,names)
        multiplier=1 if isinstance(node.op,ast.Add) else -1
        result=dict(left)
        for name,value in right.items():result[name]=result.get(name,0)+multiplier*value
        return {k:v for k,v in result.items() if v},a+multiplier*b
    raise Hold("UNRECOGNIZED_OUTER_CLOCK_EXPRESSION")


def assigned_names(node):
    if isinstance(node,ast.Assign):return [n.id for t in node.targets for n in ast.walk(t) if isinstance(n,ast.Name)]
    if isinstance(node,(ast.AnnAssign,ast.AugAssign,ast.NamedExpr)):
        return [n.id for n in ast.walk(node.target) if isinstance(n,ast.Name)]
    return []


def outer_clock(bootstrap_raw,first_cell_source):
    tree=ast.parse(bootstrap_raw)
    need(not any("GEMMA_NATIVE_T0" in assigned_names(n) for n in ast.walk(tree)),"BOOTSTRAP_RESETS_FIRST_CELL_ORIGIN")
    first=ast.parse(first_cell_source)
    assignments=[n for n in ast.walk(first) if "GEMMA_NATIVE_T0" in assigned_names(n)]
    need(len(assignments)==1 and isinstance(assignments[0],ast.Assign)
         and affine(assignments[0].value,set())==({"time.monotonic()":1.0},0.0),"FIRST_CELL_CLOCK_UNKNOWN")
    guards=[n for n in first.body if isinstance(n,ast.If)]
    need(len(guards)==1 and guards[0].lineno<assignments[0].lineno
         and ast.unparse(guards[0].test)=="'GEMMA_NATIVE_T0' in globals()"
         and len(guards[0].body)==1 and isinstance(guards[0].body[0],ast.Raise),"FIRST_CELL_RESET_GUARD_UNKNOWN")
    deadlines=[n for n in ast.walk(tree) if "deadline" in assigned_names(n)]
    need(len(deadlines)==1 and isinstance(deadlines[0],ast.Assign),"OUTER_DEADLINE_DENOMINATOR")
    coeff,offset=affine(deadlines[0].value,{"GEMMA_NATIVE_T0"})
    need(coeff=={"GEMMA_NATIVE_T0":1.0},"OUTER_FIRST_CELL_ORIGIN_UNKNOWN")
    timeouts=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) \
           and node.func.value.id=="subprocess" and node.func.attr=="run":
            timeouts.extend(k.value for k in node.keywords if k.arg=="timeout")
    need(len(timeouts)==1,"ENCLOSING_TIMEOUT_DENOMINATOR")
    expression=timeouts[0]
    need(isinstance(expression,ast.Call) and isinstance(expression.func,ast.Name) and expression.func.id=="max"
         and not expression.keywords and len(expression.args)==2,"ENCLOSING_TIMEOUT_SHAPE")
    lower=expression.args[0]
    need(isinstance(lower,ast.Constant) and type(lower.value) in (int,float) and lower.value==1,
         "ENCLOSING_TIMEOUT_FLOOR_UNREVIEWED")
    coeff,grace=affine(expression.args[1],{"deadline"})
    need(coeff=={"deadline":1.0,"time.monotonic()":-1.0} and finite(grace),"ENCLOSING_TIMEOUT_ORIGIN")
    return {"declared_outer_deadline_offset_seconds":offset,"timeout_grace_seconds":grace,
            "timeout_minimum_seconds":lower.value,"nominal_parent_cap_from_first_cell_seconds":offset+grace,
            "first_cell_reset_guard_syntax_present":True,
            "origin_analysis_scope":"Pinned source and restricted direct-assignment/affine syntax only; dynamic aliases/global mutations are not semantically proven absent.",
            "cap_note":"Nominal cap while remaining deadline exceeds the timeout floor; a late call can run for the floor. This is source analysis, not a measured receipt."}


def inner_origin(raw):
    tree=ast.parse(raw)
    expressions=[n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and "deadline" in assigned_names(n)]
    need(len(expressions)==1,"INNER_DEADLINE_DENOMINATOR")
    expression=ast.unparse(expressions[0])
    # A restricted structural contract, not execution of third-party code.
    allowed={"a.start + protocol['absolute_seconds_including_model_load_and_allocation_reserve'] - overhead",
             "a.start + protocol['absolute_seconds_including_model_load_and_allocation_reserve'] - allocation_overhead"}
    need(expression in allowed,"INNER_PROTOCOL_CLOCK_UNKNOWN")
    return {"deadline_expression_uses_passed_start":True,"deadline_expression_uses_protocol_absolute_and_allocation":True,
            "scope":"Restricted pinned-source expression, not runtime origin attestation."}


def identity(value):
    names=("id","id_no","title","code_file")
    need(type(value) is dict and all(name in value for name in names),"FULL_IDENTITY_UNKNOWN")
    result={name:value[name] for name in names}
    need(type(result["id_no"]) is int and result["id_no"]>0
         and all(type(result[k]) is str and result[k] for k in ("id","title","code_file")),"FULL_IDENTITY_TYPE")
    return result


def plan(manifest):
    need(type(manifest) is dict and type(manifest.get("schema_version")) is int and manifest["schema_version"]==1,"PLANNER_SCHEMA")
    specs=manifest.get("files")
    need(type(specs) is dict and set(specs)==FILES,"PLANNER_FILE_DENOMINATOR")
    raw={name:read_pin(spec) for name,spec in specs.items()}
    values={name:parse(raw[name]) for name in ("protocol","build","candidate","kernel_metadata","dataset_metadata","preregistration")}
    protocol=values["protocol"];build=values["build"];candidate=values["candidate"]
    expected=identity(manifest.get("expected_identity"))
    need(identity(build.get("identity"))==expected and identity(values["kernel_metadata"])==expected,"SAVED_IDENTITY_CONFLICT")
    need(build.get("status")=="PREPARED_V26_R1_NOT_PUSHED"
         and all(type(build.get(k)) is int and build[k]==0 for k in ("pushes","native_model_calls","competition_submissions")),"PREPARED_EVIDENCE_CONTEXT_UNKNOWN")
    need(build.get("protocol_sha256")==sha(raw["protocol"])
         and build.get("bootstrap_sha256")==build.get("bootstrap_pin")==sha(raw["bootstrap"])
         and build.get("candidate_notebook_sha256")==sha(raw["candidate"])
         and type(build.get("candidate_notebook_bytes")) is int and build["candidate_notebook_bytes"]==len(raw["candidate"]),"BUILD_SOURCE_BINDING")
    for role in ("native_supervisor","native_watchdog"):
        name=role+".py"
        need(protocol.get("component_hashes",{}).get(name)==build.get("component_hashes",{}).get(name)==sha(raw[role]),"INNER_SOURCE_BINDING")
    asset=values["dataset_metadata"]
    need(type(manifest.get("expected_dataset_identity")) is dict and set(manifest["expected_dataset_identity"])=={"id","title"}
         and {k:asset.get(k) for k in ("id","title")}==manifest["expected_dataset_identity"],"DATASET_IDENTITY_CONFLICT")
    planned=task_list(protocol.get("task_ids"));full=task_list(values["preregistration"].get("gate_task_ids"))
    need(build.get("task_ids")==planned and planned==full[:len(planned)],"ORDERED_PREREGISTRATION_PREFIX_CONFLICT")
    need(build.get("arm_selection")==protocol.get("arm_selection") and type(protocol.get("arm_selection")) is list
         and len(protocol["arm_selection"])==1,"SINGLE_ARM_DENOMINATOR")
    envelope=protocol_envelope(protocol)
    for key in ("session_timeout_seconds","deadline_seconds_from_first_cell","task_reserve_seconds","readiness_budget_seconds"):
        need(type(build.get(key)) is int and build[key]==protocol[key],"BUILD_BUDGET_CONFLICT")
    cells=candidate.get("cells");index=build.get("loader_cell_index")
    need(type(cells) is list and type(index) is int and 0<index<len(cells),"LOADER_CELL_UNKNOWN")
    first_source=cells[0].get("source");loader=cells[index].get("source")
    need(type(first_source) is str and type(loader) is str and cells[index].get("cell_type")=="code","NOTEBOOK_SOURCE_SHAPE_UNKNOWN")
    current_name=Path(specs["bootstrap"]["path"]).name;current_sha=sha(raw["bootstrap"])
    need(NAME.fullmatch(current_name) and loader.count(current_name)==1 and loader.count(current_sha)==1
         and "exec(compile(_b, _P[0], \"exec\"))" in loader,"EXTERNAL_LOADER_BINDING_UNKNOWN")
    need(all(path in loader for path in (asset["id"].split("/")[-1],"datasets/"+asset["id"])),"LOADER_ASSET_IDENTITY_UNKNOWN")
    outer=outer_clock(raw["bootstrap"],first_source)
    inner={name:inner_origin(raw[name]) for name in ("native_watchdog","native_supervisor")}
    wire=integer(build.get("wire_bytes_with_proposed_overrides"),"SDK_WIRE_SIZE_UNKNOWN")
    cap=integer(build.get("wire_cap_bytes"),"SDK_WIRE_CAP_UNKNOWN")
    need(cap>=wire,"SAVED_WIRE_OVER_CAP")
    spare=cap-wire
    need(type(build.get("wire_delta_vs_cap")) is int and build["wire_delta_vs_cap"]==-spare
         and build.get("wire_within_cap") is True,"SAVED_WIRE_ARITHMETIC_CONFLICT")
    projection=manifest.get("hypothetical_loader_replacement")
    need(type(projection) is dict and set(projection)=={"filename","sha256"}
         and type(projection["filename"]) is str and NAME.fullmatch(projection["filename"])
         and type(projection["sha256"]) is str and re.fullmatch("[0-9a-f]{64}",projection["sha256"]),"HYPOTHETICAL_ASSET_SHAPE")
    name=projection["filename"];digest=projection["sha256"]
    need(len(name.encode())==len(current_name.encode()) and len(digest)==len(current_sha),"HYPOTHETICAL_LOADER_BYTE_GROWTH")
    need(raw["candidate"].count(current_name.encode())==raw["candidate"].count(current_sha.encode())==1,"GLOBAL_REPLACEMENT_WOULD_TOUCH_OTHER_SOURCES")
    projected=raw["candidate"].replace(current_name.encode(),name.encode()).replace(current_sha.encode(),digest.encode())
    projected_value=parse(projected)
    need(len(projected)==len(raw["candidate"]),"PROJECTED_NOTEBOOK_BYTE_GROWTH")
    comparison=parse(raw["candidate"])
    expected_loader=loader.replace(current_name,name).replace(current_sha,digest)
    comparison["cells"][index]["source"]=expected_loader
    need(encode(projected_value)==encode(comparison),"PROJECTED_PRESERVED_NOTEBOOK_DRIFT")
    gaps=[]
    if outer["nominal_parent_cap_from_first_cell_seconds"]<envelope["first_cell_budget_seconds"]:
        gaps.append("ENCLOSING_PARENT_CAP_PREEMPTS_PROTOCOL_ENVELOPE")
    if "clock_collector.py" not in protocol.get("component_hashes",{}):gaps.append("PREPARED_PROTOCOL_HAS_NO_REVIEWED_CLOCK_COLLECTOR")
    if "entry_join.py" not in protocol.get("component_hashes",{}):gaps.append("PREPARED_PROTOCOL_HAS_NO_REVIEWED_EXTERNAL_ENTRY")
    supervisor_tree=ast.parse(raw["native_supervisor"])
    routed=any(isinstance(n,ast.Constant) and n.value=="native_arm.py" for n in ast.walk(supervisor_tree))
    if routed:gaps.append("PREPARED_SUPERVISOR_STILL_ROUTES_DIRECT_OWNED_ARM")
    gaps.extend(["FUTURE_SEALED_ASSET_INVENTORY_AND_BOOTSTRAP_PIN_UNCOLLECTED",
                 "FRESH_SERVER_IDENTITY_AND_TERMINAL_STATUS_UNCOLLECTED",
                 "ACTUAL_FUTURE_SDK_WIRE_AND_QUOTA_GATES_UNCOLLECTED",
                 "NATIVE_FULL_RECEIPTS_AND_ATTESTATION_UNCOLLECTED"])
    return {"schema_version":1,"status":"HOLD_PREPARED_ROUTE_ONLY","source_sha256":{k:sha(v) for k,v in raw.items()},
            "prepared_evidence_only":True,"accepted_version_qualified":False,"observed_native_failure_claimed":False,
            "identity_consistency_only":True,"ordered_screen_task_count":len(planned),"full_gate_task_count":len(full),
            "protocol_envelope":envelope,"outer_clock_source_analysis":outer,"inner_clock_source_analysis":inner,
            "nominal_parent_shortfall_seconds":envelope["first_cell_budget_seconds"]-outer["nominal_parent_cap_from_first_cell_seconds"],
            "saved_wire":{"bytes":wire,"cap":cap,"spare":spare,"not_fresh_wire_qualification":True},
            "hypothetical_loader_projection":{"filename":name,"pin_is_placeholder_only":True,
                "notebook_byte_delta":0,"other_cells_metadata_outputs_unchanged":True,
                "sdk_wire_delta_unmeasured":True,"future_asset_uploaded":False},
            "adoption_gaps":gaps,"notebook_written":False,"dataset_uploaded":False,"run_started":False,
            "native_authenticity_established":False,"official_score":None,"submission_authorized":False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--manifest",type=Path,required=True)
    args=parser.parse_args()
    try:
        with args.manifest.open("rb") as stream:manifest=parse(stream.read(8*1024*1024+1))
        report=plan(manifest)
    except Exception as error:
        report={"status":"HOLD_INPUT_UNKNOWN","reason":str(error) if isinstance(error,Hold) else type(error).__name__,
                "native_authenticity_established":False,"official_score":None,"submission_authorized":False}
    print(encode(report).decode())
    return 2


if __name__=="__main__":sys.exit(main())
