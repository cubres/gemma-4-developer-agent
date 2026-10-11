# SPDX-License-Identifier: MIT
"""Original invented example; no network, model, candidate edit or submission."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

EXPECTED_TOOL_SHA256 = '560eed0c11f1f76a12f8f447d80bbb7130e796aa51fb8854160bd919aabd1b81'

def load_tool(path):
    # Obtain this original helper from the separately recorded pinned commit.
    # A digest checks consistency; it does not authenticate an untrusted pin.
    with Path(path).open("rb") as f:
        raw = f.read(1_048_577)
    if len(raw) > 1_048_576 or hashlib.sha256(raw).hexdigest() != EXPECTED_TOOL_SHA256:
        raise ValueError("PINNED_TOOL_MISMATCH")
    module = types.ModuleType("companion_pinned_tool")
    module.__file__ = str(Path(path))
    sys.modules[module.__name__] = module
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module

def run(tool):
    here = Path(__file__).resolve().parent
    pin = (here / "demo-manifest-pin.txt").read_text().strip()
    raw_layout = (here / "demo-layout.json").read_bytes()
    report = tool.verify(here / "demo", pin, raw_layout)
    wrong_pin = ("0" if pin[0] != "0" else "1") + pin[1:]
    try:
        tool.verify(here / "demo", wrong_pin, raw_layout)
    except tool.Hold as exc:
        negative = str(exc)
    else:
        raise ValueError("INVENTED_EXPECTATION_MISMATCH")
    if report["status"] != "PASS_PINNED_BYTES" or negative != "MANIFEST_PIN_MISMATCH":
        raise ValueError("INVENTED_EXPECTATION_MISMATCH")
    return {"status": "INVENTED_FLATPACK_ONLY", "verified": report,
            "wrong_manifest_pin": negative, "files_restored_or_executed": 0,
            "agent_package_or_prompt_included": False, "official_score": None}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True, help="Path to the pinned original helper")
    args = parser.parse_args()
    try:
        result = run(load_tool(args.tool))
    except (OSError, ValueError) as exc:
        # No input path, content, credentials or traceback is printed on HOLD.
        print(json.dumps({"status": "HOLD", "reason": "SOURCE_OR_EXAMPLE_CHECK_FAILED"}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
