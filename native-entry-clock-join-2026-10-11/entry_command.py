"""Original read-only argv builder for an explicitly coordinated external entry.

build_command reads source/route pins and returns an argv list. It never executes
that list. The embedded child program is original glue, not organizer code.
Only a separately authorized coordinator may execute a fully reviewed route.
"""
from pathlib import Path
import entry_join as entry

CHILD_PROGRAM = r'''
import hashlib, pathlib, sys, types
limit=8*1024*1024
manifest_path, manifest_sha, entry_path, entry_sha = sys.argv[1:5]
def pinned(path,digest):
    with pathlib.Path(path).open("rb") as stream: raw=stream.read(limit+1)
    if len(raw)>limit or hashlib.sha256(raw).hexdigest()!=digest:
        raise RuntimeError("ENTRY_CHILD_SOURCE_OR_ROUTE_PIN_DRIFT")
    return raw
source=pinned(entry_path,entry_sha)
module=types.ModuleType("source_bound_gemma_entry")
module.__file__=entry_path
exec(compile(source,entry_path,"exec"),module.__dict__)
manifest=module.parse(pinned(manifest_path,manifest_sha))
result=module.execute_checked_arm(manifest,sys.argv[5:])
print(module.encode(result).decode())
if result.get("status") != "OBSERVED_CLOCK_SIDECAR_REVIEW_REQUIRED":
    raise SystemExit(2)
'''


def build_command(python_path,manifest_spec):
    """Pinned metadata-only planning; no native imports/evaluation occurs here."""
    raw=entry.read_pin(manifest_spec);manifest=entry.parse(raw)
    route=entry.checked_route(manifest)
    command_spec=manifest.get("entry_command_source")
    command_raw=entry.read_pin(command_spec)
    entry.need(route["protocol"].get("component_hashes",{}).get("entry_command.py")==entry.sha(command_raw)
               and command_raw==Path(__file__).read_bytes(),"REVIEWED_COMMAND_SOURCE_OR_PROTOCOL_DRIFT")
    entry.need(type(python_path) is str and Path(python_path).is_absolute(),"PYTHON_EXECUTABLE_PATH_UNKNOWN")
    context=manifest.get("arm_runtime_context")
    entry.need(type(context) is dict and set(context)=={"agent","data","output","port"}
               and all(type(context[k]) is str and context[k] for k in ("agent","data","output"))
               and type(context["port"]) is int and 0<context["port"]<65536,"ARM_RUNTIME_CONTEXT_REQUIRED")
    official=Path(manifest["source_files"]["swegemma/evaluate.py"]["path"]).parent.parent
    argv=[]
    for key,value in (("protocol",manifest["protocol"]["path"]),("agent",context["agent"]),
                      ("data",context["data"]),("helper",manifest["helper"]["path"]),("output",context["output"]),
                      ("official-source",str(official)),("port",str(context["port"]))):
        argv.extend(["--"+key,value])
    spec=manifest["owned_sources"]["entry_join.py"]
    return {"status":"HOLD_COORDINATOR_EXECUTION_AND_NATIVE_ATTESTATION_REQUIRED",
            "argv":[python_path,"-B","-c",CHILD_PROGRAM,manifest_spec["path"],manifest_spec["sha256"],
                    spec["path"],spec["sha256"],*argv],
            "source_sha256":{"entry_join.py":spec["sha256"],"entry_command.py":entry.sha(command_raw)},
            "route_manifest_sha256":entry.sha(raw),"executed":False,"native_authenticity_established":False,
            "official_score":None,"submission_authorized":False}
