"""Original, dormant Gemma entry lifecycle and create-only clock sidecar join.

No CLI launches an evaluation. A separately authorized coordinator may call the
checked entry API after reviewing its exact source/protocol/runtime manifest.
Hashes establish consistency, never native authenticity or a score.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import re
import sys
from types import ModuleType

MAX_BYTES = 8*1024*1024
MAX_TASKS = 128
SHA = re.compile(r"^[0-9a-f]{64}$")
TASK = re.compile(r"^[A-Za-z0-9_:-]{1,160}$")
SIDECAR_NAME = "PRIVATE_POLICY_CLOCK_RECEIPT.json"
NATIVE_ARM_SHA = "d0134b99e2544bed8f8a3d24d1d00cf1f74e19be691e315e08474fb7716012e2"
HELPER_SHA = "d44f8ab1bb3317b457595f353ea94fc861f518dd077acb9fdd92fd644c325833"
ADAPTER_SHA = "80931c14191502008be59fb0a3a4ef46a9373edfe64f61fd39c224744ec7c8f0"
COLLECTOR_SHA = "316dfa7a05dd54ce51b54e616e4cfe9b58d7fe1e95c7355df521b62fa55810eb"
R4_SHA = "511518072a7ddc236867ae96d653f1be37b371959efc81a78fe4535359d378a8"
REVIEWED_SOURCES = {
    "adk_eval_core/models/base.py":"bdedef267b1022ffac970c7bc18c2d0a53753ce1f120a3c355b91c9b7b666a0d",
    "swegemma/context.py":"97f06280c50df3132d1af7ef6126884b66b48887a1cf94b293af01e5907dc2a7",
    "swegemma/harness/agent_runner.py":"4d7eccabd203c26f7c39e882684d2fd851f383f6a5c76c4a75b0e559cd5d6a18",
    "swegemma/evaluate.py":"96a46f49267ffcf861f7f90b98efbe828d03f27553ceefce745819028589de1e",
    "swegemma/harness/verification.py":"766e52c34da16cfdc73fc6df22848ab5b9d6b80943d61e7173a844e8efc6c1d9",
    "swegemma/models/task.py":"0b9d705ce759645bd1ee59bb28662a25a951990c024bfeb1e00a41f08350812a",
    "native_arm.py":NATIVE_ARM_SHA,
    "private_junit_receipts.py":"dd9eb12b6a0cb71d7f902806cebf04c039a124e3960a7757407203154ce6e839",
    "clock_collector.py":COLLECTOR_SHA,
}


class Hold(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Hold(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def unique_pairs(items):
    result={}
    for key,value in items:
        need(key not in result,"DUPLICATE_JSON_KEY")
        result[key]=value
    return result


def parse(raw):
    need(type(raw) is bytes and len(raw)<=MAX_BYTES,"INPUT_BYTE_BOUND")
    def bad(_):raise Hold("NONFINITE_JSON_CONSTANT")
    value=json.loads(raw,object_pairs_hook=unique_pairs,parse_constant=bad)
    need(type(value) is dict,"JSON_OBJECT_REQUIRED")
    encode(value)  # Reject overflowing numerical literals too.
    return value


def read_pin(spec):
    need(type(spec) is dict and set(spec)=={"path","sha256"}
         and type(spec["path"]) is str and 0<len(spec["path"])<=4096
         and type(spec["sha256"]) is str and SHA.fullmatch(spec["sha256"]),"PIN_SPEC_INVALID")
    with Path(spec["path"]).open("rb") as stream:raw=stream.read(MAX_BYTES+1)
    need(len(raw)<=MAX_BYTES and sha(raw)==spec["sha256"],"SOURCE_OR_RECEIPT_PIN_DRIFT")
    return raw


def load_module(raw,path,label):
    """Compile the already-hashed exact bytes, never reopen through import paths."""
    module=ModuleType(label);module.__file__=str(path)
    exec(compile(raw,str(path),"exec"),module.__dict__)
    return module


def task_list(value):
    need(type(value) is list and 0<len(value)<=MAX_TASKS
         and all(type(x) is str and TASK.fullmatch(x) for x in value)
         and len(set(value))==len(value),"TASK_DENOMINATOR_INVALID")
    return value


def alias_identity(value):
    a=getattr(value,"task_id",None);b=getattr(value,"instance_id",None)
    need(a is not None or b is not None,"TASK_CONTEXT_ID_ABSENT")
    need(a is None or b is None or (type(a) is type(b) and a==b),"TASK_CONTEXT_ID_CONFLICT")
    result=a if a is not None else b
    need(type(result) is str and TASK.fullmatch(result),"TASK_CONTEXT_ID_INVALID")
    return result


def ordered_subsequence(observed,planned):
    need(type(observed) is list and len(observed)<=len(planned)
         and all(type(x) is str and x in planned for x in observed)
         and len(set(observed))==len(observed),"OBSERVED_DENOMINATOR_CONFLICT")
    need([planned.index(x) for x in observed]==sorted(planned.index(x) for x in observed),
         "OBSERVED_DENOMINATOR_ORDER")


class TimingLifecycle:
    """Low-level sequential lifecycle, also usable with explicitly invented fakes.

    This class alone is not source admission. execute_checked_arm supplies the
    checked runtime/source validators. It never starts/stops a process itself.
    """

    def __init__(self,owned_arm,collector,planned,*,boundary_check=None,context_check=None):
        self.owned=owned_arm;self.collector=collector;self.planned=task_list(planned)
        self.boundary_check=boundary_check;self.context_check=context_check
        self.original_install=None;self.originals=[];self.install_count=0
        self.call_count=0;self.active=False;self.entered=False
        self.failures=[];self.restoration_errors=[];self.restored=False

    def __enter__(self):
        need(not self.entered,"ENTRY_LIFECYCLE_REUSED")
        original=getattr(self.owned,"install_timing",None)
        need(callable(original),"OWNED_INSTALL_BOUNDARY_ABSENT")
        self.entered=True;self.original_install=original
        lifecycle=self

        @functools.wraps(original)
        def install(official_eval,timing):
            try:
                need(lifecycle.install_count==0,"MULTIPLE_INSTALL_BOUNDARIES_REFUSED")
                lifecycle.install_count+=1
                if lifecycle.boundary_check is not None:
                    lifecycle.boundary_check(official_eval)
                evaluator=getattr(official_eval,"Evaluator",None)
                need(type(evaluator) is type,"EVALUATOR_CLASS_REQUIRED")
                for target,name in ((evaluator,"evaluate_task"),(evaluator,"_run_agent_sandbox"),
                                    (official_eval,"verify_task")):
                    value=getattr(target,name,None)
                    need(callable(value),"EVALUATOR_CALLABLE_ABSENT")
                    lifecycle.originals.append((target,name,value))
                # Capture all originals before the owned installer can partially fail.
                install_result=original(official_eval,timing)
                sandbox=evaluator._run_agent_sandbox
                need(inspect.iscoroutinefunction(sandbox),"ASYNC_SANDBOX_BOUNDARY_REQUIRED")
                signature=inspect.signature(sandbox)
                observed=lifecycle.collector.wrap(sandbox)
            except BaseException:
                lifecycle.failures.append("INSTALL_OR_SOURCE_BOUNDARY_FAILED")
                raise

            @functools.wraps(sandbox)
            async def sequential(*args,**kwargs):
                try:
                    need(not lifecycle.active,"CONCURRENT_TASK_CALL_REFUSED")
                    bound=signature.bind(*args,**kwargs)
                    task=bound.arguments.get("task");context=bound.arguments.get("context")
                    identity=alias_identity(task)
                    need(lifecycle.call_count<len(lifecycle.planned)
                         and identity==lifecycle.planned[lifecycle.call_count],"SANDBOX_TASK_ORDER_OR_DENOMINATOR")
                    need(context is not None and hasattr(context,"agent_start_time")
                         and hasattr(context,"agent_end_time"),"POLICY_CONTEXT_ABSENT")
                    if lifecycle.context_check is not None:lifecycle.context_check(context)
                except BaseException:
                    lifecycle.failures.append("TASK_OR_SEQUENTIAL_CONTEXT_FAILED")
                    raise
                lifecycle.call_count+=1;lifecycle.active=True
                try:return await observed(*args,**kwargs)
                finally:lifecycle.active=False

            evaluator._run_agent_sandbox=sequential
            return install_result

        self.owned.install_timing=install
        return self

    def __exit__(self,kind,error,traceback):
        # Every saved boundary gets a restoration attempt, including partial
        # installation failures. Restoration never masks an original exception.
        for target,name,original in reversed(self.originals):
            try:
                setattr(target,name,original)
                if getattr(target,name) is not original:raise Hold("RESTORATION_IDENTITY_DRIFT")
            except BaseException:self.restoration_errors.append("RESTORATION_FAILED")
        try:
            self.owned.install_timing=self.original_install
            if self.owned.install_timing is not self.original_install:raise Hold("RESTORATION_IDENTITY_DRIFT")
        except BaseException:self.restoration_errors.append("OWNED_INSTALL_RESTORATION_FAILED")
        self.failures.extend(self.restoration_errors)
        self.restored=not self.restoration_errors
        if error is None and self.restoration_errors:raise Hold("ENTRY_RESTORATION_FAILED")
        return False


def finite(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=10**9


def inspect_records(records,planned):
    need(type(records) is list and len(records)<=len(planned)
         and all(type(r) is dict for r in records),"CLOCK_RECORD_BOUND")
    observed=[r.get("task_id") for r in records]
    ordered_subsequence(observed,planned)
    frozen=0
    for record in records:
        need(record.get("clock")=="time.perf_counter"
             and record.get("outcome") in ("RETURN","EXCEPTION")
             and record.get("state") in ("OBSERVED_FROZEN","UNKNOWN"),"CLOCK_RECORD_CONTEXT_INVALID")
        need(all(finite(record.get(k)) for k in ("wrapper_started","wrapper_finished")),"CLOCK_WRAPPER_MARKS_INVALID")
        need(record["wrapper_started"]<=record["wrapper_finished"],"CLOCK_WRAPPER_ORDER")
        if record["state"]=="UNKNOWN":
            need(not any(k in record for k in ("policy_started","policy_finished","policy_elapsed_seconds",
                     "preparation_seconds","completion_seconds","sandbox_wall_seconds")),"UNKNOWN_CLOCK_HAS_INVENTED_MEASUREMENTS")
            continue
        marks=[record.get(k) for k in ("wrapper_started","policy_started","policy_finished","wrapper_finished")]
        need(all(finite(v) for v in marks) and marks==sorted(marks),"CLOCK_MARK_ORDER_OR_TYPE")
        expected=(marks[2]-marks[1],marks[1]-marks[0],marks[3]-marks[2],marks[3]-marks[0])
        measured=[record.get(k) for k in ("policy_elapsed_seconds","preparation_seconds","completion_seconds","sandbox_wall_seconds")]
        need(all(finite(v) for v in measured) and all(abs(a-b)<=.002 for a,b in zip(measured,expected)),
             "CLOCK_MEASUREMENT_TYPE_OR_DRIFT")
        frozen+=int(record["outcome"]=="RETURN")
    return frozen


def create_sidecar(arm_path,protocol_raw,sources,collector,lifecycle,*,entry_sha256):
    """New sidecar only; the existing original arm receipt is never opened to write."""
    protocol=parse(protocol_raw);planned=task_list(protocol.get("task_ids"))
    need(type(entry_sha256) is str and SHA.fullmatch(entry_sha256),"ENTRY_PIN_REQUIRED")
    source_contract(protocol,sources,entry_sha256)
    arm_path=Path(arm_path)
    need(arm_path.name=="PRIVATE_NATIVE_ARM_RECEIPT.json" and arm_path.is_file()
         and not arm_path.is_symlink(),"ORIGINAL_RAW_ARM_ABSENT_OR_LINK")
    with arm_path.open("rb") as stream:arm_raw=stream.read(MAX_BYTES+1)
    arm=parse(arm_raw)
    need(type(protocol.get("repo")) is str and bool(protocol["repo"])
         and arm.get("task_ids")==planned and arm.get("repo")==protocol["repo"],"RAW_ARM_INPUT_CONFLICT")
    need(arm.get("helper_sha256")==HELPER_SHA
         and protocol.get("owned_helper_hashes",{}).get("run_gpu_validation_candidate.py")==HELPER_SHA,
         "PROTECTED_HELPER_SOURCE_CONFLICT")
    need(arm.get("status") in ("PUBLIC_TASK_NATIVE_RETURNED","HOLD") and arm.get("official_score") is None,
         "RAW_ARM_STATUS_OR_SCORE_INVALID")
    need(type(collector.observer_errors) is int and collector.observer_errors>=0
         and type(lifecycle.failures) is list and type(lifecycle.restored) is bool,"OBSERVER_STATE_INVALID")
    frozen=inspect_records(collector.records,planned)
    rows=arm.get("rows")
    need(type(rows) is list and len(rows)<=len(planned),"RAW_RESULT_DENOMINATOR_UNKNOWN")
    identities=[];caught=0;unsupported_exits=0
    for row in rows:
        need(type(row) is dict and ("task_id" in row or "instance_id" in row)
             and ("error_message" in row or "error" in row),"RAW_RESULT_CONTEXT_UNKNOWN")
        for a,b in (("task_id","instance_id"),("error_message","error")):
            if a in row and b in row:
                need(type(row[a]) is type(row[b]) and row[a]==row[b],"RAW_RESULT_ALIAS_CONFLICT")
        identities.append(row["task_id"] if "task_id" in row else row["instance_id"])
        err=row["error_message"] if "error_message" in row else row["error"]
        need(err is None or type(err) is str,"RAW_RESULT_ERROR_TYPE")
        caught+=int(bool(err))
        unsupported_exits+=int(type(row.get("test_exit_code")) is not int or row["test_exit_code"] not in (0,1))
    ordered_subsequence(identities,planned)
    errors=collector.observer_errors+len(lifecycle.failures)
    complete=(len(rows)==len(planned)==len(collector.records)==frozen and caught==0 and unsupported_exits==0
              and errors==0 and lifecycle.restored and arm["status"]=="PUBLIC_TASK_NATIVE_RETURNED")
    value={"schema_version":1,"status":"OBSERVED_CLOCK_SIDECAR_REVIEW_REQUIRED" if complete else "HOLD",
           "raw_protocol_sha256":sha(protocol_raw),"raw_arm_sha256":sha(arm_raw),
           "source_sha256":sources,"entry_source_sha256":entry_sha256,
           "records":collector.records,"observer_errors":errors,
           "collector_observer_errors":collector.observer_errors,"lifecycle_error_count":len(lifecycle.failures),
           "lifecycle_restored":lifecycle.restored,"planned_task_count":len(planned),
           "observed_clock_count":len(collector.records),"missing_clock_count":len(planned)-len(collector.records),
           "caught_task_error_count":caught,"observed_result_count":len(rows),
           "unsupported_or_unknown_test_exit_count":unsupported_exits,
           "native_authenticity_established":False,"native_run_qualified":False,
           "official_score":None,"submission_authorized":False}
    raw=encode(value)
    need(len(raw)<=MAX_BYTES,"SIDECAR_BYTE_BOUND")
    destination=arm_path.parent/SIDECAR_NAME
    # Existing sidecars, symlinks and partial failed writes remain untouched.
    with destination.open("xb") as stream:stream.write(raw)
    return {"status":value["status"],"sidecar_path":str(destination),"sidecar_sha256":sha(raw),
            "native_authenticity_established":False,"official_score":None,"submission_authorized":False}


def source_contract(protocol,sources,entry_sha256):
    need(type(sources) is dict and sources==REVIEWED_SOURCES,"REVIEWED_SOURCE_DENOMINATOR_OR_PIN")
    for name,digest in sources.items():
        key="component_hashes" if name in ("native_arm.py","private_junit_receipts.py","clock_collector.py") else "fresh_python_source_sha256"
        need(type(protocol.get(key)) is dict and protocol[key].get(name)==digest,"PROTOCOL_REVIEWED_SOURCE_CONFLICT")
    need(protocol.get("component_hashes",{}).get("entry_join.py")==entry_sha256,"PROTOCOL_ENTRY_SOURCE_BINDING")


def checked_route(manifest):
    """Read/verify route, without importing organizer or running an evaluation."""
    need(type(manifest) is dict and type(manifest.get("schema_version")) is int
         and manifest["schema_version"]==1,"ROUTE_SCHEMA")
    own=manifest.get("owned_sources",{})
    expected={"native_arm.py":NATIVE_ARM_SHA,"receipt_adapter.py":ADAPTER_SHA,
              "clock_collector.py":COLLECTOR_SHA,"screen_gate.py":R4_SHA}
    need(type(own) is dict and set(own)==set(expected)|{"entry_join.py"},"OWNED_SOURCE_DENOMINATOR")
    payload={}
    for name,spec in own.items():
        content=read_pin(spec);payload[name]=content
        wanted=expected.get(name,manifest.get("reviewed_entry_sha256"))
        need(type(wanted) is str and SHA.fullmatch(wanted) and sha(content)==wanted,"REVIEWED_ENTRY_SOURCE_DRIFT")
    protocol_raw=read_pin(manifest["protocol"]);protocol=parse(protocol_raw)
    need(type(manifest.get("reviewed_protocol_sha256")) is str
         and sha(protocol_raw)==manifest["reviewed_protocol_sha256"],"REVIEWED_PROTOCOL_PIN_REQUIRED")
    planned=task_list(protocol.get("task_ids"))
    need(manifest.get("task_ids")==planned and type(manifest.get("helper_concurrency")) is int
         and manifest["helper_concurrency"]==1,"SEQUENTIAL_DECLARED_CONTEXT_REQUIRED")
    prereg=parse(read_pin(manifest["preregistration"]));full=task_list(prereg.get("gate_task_ids"))
    ordered_subsequence(planned,full)
    need(manifest.get("full_gate_task_ids")==full,"FULL_GATE_INPUT_BINDING")
    need(type(protocol.get("arm_selection")) is list and len(protocol["arm_selection"])==1
         and type(protocol.get("repo")) is str,"SINGLE_ARM_INPUT_CONTEXT")
    adapter=load_module(payload["receipt_adapter.py"],own["receipt_adapter.py"]["path"],"checked_r3_adapter")
    observed={name:sha(read_pin(spec)) for name,spec in manifest.get("source_files",{}).items()}
    need(set(observed)==set(adapter.OFFICIAL_SOURCES+adapter.OWNED_SOURCES),"SOURCE_DENOMINATOR")
    adapter.source_bindings(protocol,observed)
    source_contract(protocol,observed,sha(payload["entry_join.py"]))
    helper=read_pin(manifest["helper"])
    need(sha(helper)==HELPER_SHA and protocol.get("owned_helper_hashes",{}).get("run_gpu_validation_candidate.py")==HELPER_SHA,
         "SEQUENTIAL_HELPER_SOURCE_BINDING")
    # Source consistency only; the coordinator still owes native attestation.
    return {"protocol_raw":protocol_raw,"protocol":protocol,"sources":observed,
            "payload":payload,"manifest":manifest,"planned":planned,"full":full}


def runtime_check(protocol):
    need(tuple(sys.version_info[:2])==(3,12),"PYTHON_RUNTIME_CONTEXT_UNKNOWN")
    pins=protocol.get("serving_version_pins")
    need(type(pins) is dict and set(pins)=={"torch","vllm","transformers","google-adk","google-genai"},
         "RUNTIME_VERSION_CONTEXT_UNKNOWN")
    for name,wanted in pins.items():
        try:actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:raise Hold("RUNTIME_PACKAGE_VERSION_ABSENT") from None
        need(type(wanted) is str and actual==wanted,"RUNTIME_VERSION_DRIFT")


def source_boundary_check(route,official_eval):
    spec=route["manifest"]["source_files"]["swegemma/evaluate.py"]
    need(getattr(official_eval,"__name__",None)=="swegemma.evaluate"
         and Path(getattr(official_eval,"__file__","")).resolve()==Path(spec["path"]).resolve(),"EVALUATOR_RUNTIME_ORIGIN_UNKNOWN")
    read_pin(spec)
    cls=getattr(official_eval,"Evaluator",None)
    need(type(cls) is type,"EVALUATOR_CLASS_REQUIRED")
    for fn in (cls.evaluate_task,cls._run_agent_sandbox,official_eval.verify_task):
        need(not hasattr(fn,"__wrapped__"),"ALREADY_WRAPPED_RUNTIME_REFUSED")
    for fn in (cls.evaluate_task,cls._run_agent_sandbox):
        need(getattr(fn,"__module__",None)=="swegemma.evaluate"
             and Path(inspect.getsourcefile(fn) or "").resolve()==Path(spec["path"]).resolve(),"EVALUATOR_CALLABLE_ORIGIN_UNKNOWN")
    verify_spec=route["manifest"]["source_files"]["swegemma/harness/verification.py"]
    need(getattr(official_eval.verify_task,"__module__",None)=="swegemma.harness.verification"
         and Path(inspect.getsourcefile(official_eval.verify_task) or "").resolve()==Path(verify_spec["path"]).resolve(),"VERIFIER_CALLABLE_ORIGIN_UNKNOWN")
    read_pin(verify_spec)


def context_source_check(route,context):
    spec=route["manifest"]["source_files"]["swegemma/context.py"]
    kind=type(context)
    need(kind.__name__=="SwegemmaContext" and kind.__module__=="swegemma.context"
         and Path(inspect.getsourcefile(kind) or "").resolve()==Path(spec["path"]).resolve(),"POLICY_CONTEXT_RUNTIME_ORIGIN_UNKNOWN")
    read_pin(spec)


def execute_checked_arm(manifest,arm_argv):
    """Dormant coordinator-only API; never invoked by this package's CLI/tests.

    Calls the existing exact owned arm only after source/runtime checks. All
    Kaggle identity/quota/privacy/native authorization gates remain external.
    """
    route=checked_route(manifest);runtime_check(route["protocol"])
    need(type(arm_argv) is list and all(type(x) is str for x in arm_argv),"ARM_ARGV_CONTEXT_UNKNOWN")
    parser=argparse.ArgumentParser(add_help=False)
    for name in ("protocol","agent","data","helper","output","official-source"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--port",type=int,required=True)
    args=parser.parse_args(arm_argv)
    need(args.protocol.resolve()==Path(manifest["protocol"]["path"]).resolve()
         and args.helper.resolve()==Path(manifest["helper"]["path"]).resolve(),"ARM_ARGV_SOURCE_BINDING")
    for name in ("swegemma/evaluate.py","swegemma/context.py"):
        need((args.official_source/name).resolve()==Path(manifest["source_files"][name]["path"]).resolve(),
             "ARM_OFFICIAL_ROOT_BINDING")
    need(0<args.port<65536 and not args.output.exists(),"ARM_RUNTIME_OUTPUT_OR_PORT_CONTEXT")
    context=manifest.get("arm_runtime_context")
    need(type(context) is dict and set(context)=={"agent","data","output","port"},"ARM_RUNTIME_PATH_CONTEXT_REQUIRED")
    for key in ("agent","data","output"):
        need(type(context[key]) is str and Path(context[key]).resolve()==getattr(args,key).resolve(),"ARM_RUNTIME_PATH_CONTEXT_CONFLICT")
    need(type(context["port"]) is int and context["port"]==args.port,"ARM_RUNTIME_PORT_CONTEXT_CONFLICT")
    need(not args.output.is_symlink() and args.agent.is_dir() and args.data.is_dir(),"ARM_RUNTIME_DIRECTORY_CONTEXT")
    collector_module=load_module(route["payload"]["clock_collector.py"],manifest["owned_sources"]["clock_collector.py"]["path"],"checked_clock_collector")
    arm=load_module(route["payload"]["native_arm.py"],manifest["owned_sources"]["native_arm.py"]["path"],"checked_owned_native_arm")
    collector=collector_module.ClockCollector()
    lifecycle=TimingLifecycle(arm,collector,route["planned"],
        boundary_check=lambda obj:source_boundary_check(route,obj),
        context_check=lambda obj:context_source_check(route,obj))
    original_argv=sys.argv;original_error=None;result=None
    try:
        sys.argv=[manifest["owned_sources"]["native_arm.py"]["path"],*arm_argv]
        with lifecycle:arm.main()
    except BaseException as error:
        original_error=error
        raise
    finally:
        sys.argv=original_argv
        receipt=args.output/"PRIVATE_NATIVE_ARM_RECEIPT.json"
        if receipt.is_file():
            try:
                result=create_sidecar(receipt,route["protocol_raw"],route["sources"],collector,lifecycle,
                    entry_sha256=manifest["reviewed_entry_sha256"])
            except BaseException:
                if original_error is None:raise
        elif original_error is None:
            raise Hold("ORIGINAL_RAW_ARM_ABSENT_NO_SIDECAR")
    return result


if __name__=="__main__":
    print(json.dumps({"status":"HOLD_COORDINATOR_API_ONLY","native_authenticity_established":False,
                      "official_score":None,"submission_authorized":False},sort_keys=True))
    sys.exit(2)
