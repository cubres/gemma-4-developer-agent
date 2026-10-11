# SPDX-License-Identifier: Apache-2.0
"""Append one original feedback policy to the exact released BudgetFit archive.

Builds files only. It never runs an agent, task, tool, subprocess or Kaggle call.
Runtime/model/sampling files and all existing source artifacts stay unchanged.
The derivative is unqualified for native execution or public package release.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

REFERENCE_SHA256 = "1cb73986bd9ad1682896d56516cfd3df7f4d5729c7ecfe7afda109c175dbbb94"
MEMBERS = {
    "agent.yaml": "680799291cc7d156d06fb7bfb5577f683ccc0d555b00e8ddb662d577f9bfa5e4",
    "configs/sampling.yaml": "571a934e89911734927533f1d36cbcc7b8d493592febe63b217e911cf7ed4926",
    "eval_config.yaml": "916cf6cb34a6cc3de39837fa72cac681599b9ac2a3ee0b893adadfd36474c531",
    "prompts/system.md": "475cc9b7fcc0dc295532f5cb5e1928f26a491f501837ad08b1c79bdbe1a3eaa4",
}
APPENDIX = """

## Tool-feedback checkpoint
Before each tool call, check the exact declared argument names. For read_file,
spell filepath, start_line and end_line exactly and supply a positive inclusive
range of at most 80 lines. Correct an ignored or malformed key rather than
repeating the default first-page read. File tools operate on repository paths;
do not send an absolute scratch path to write_file. get_status and submit_patch
take no arguments. A real error or nonzero nested command exit is failure even
when a formatted label says success; an absent exit is unknown. After a check
program fails, allow at most one short repair if time permits. If that repair
also fails, stop debugging the check program: reassess the source change or
submit honestly with its validation limitation. Keep the original task, source
fix, time budget and native verification authoritative.
"""
DERIVATIVE_NOTICE = """Budget-Fit V5 with an original tool-feedback prompt appendix

Upstream author: Wilmer E. Henao (verracodeguacas)
https://www.kaggle.com/code/verracodeguacas/gemma-4-agent-budget-fit-single-agent?scriptVersionId=355310852
Upstream licensed Apache-2.0; the full license is distributed beside this archive.
Exact original archive SHA256:
1cb73986bd9ad1682896d56516cfd3df7f4d5729c7ecfe7afda109c175dbbb94

Modification by cubres contributors, 2026: append the original tool-feedback
checkpoint to prompts/system.md. The other three compiler inputs are unchanged.
This source-only derivative has no native execution or official score evidence.
Developer-agent package publication remains subject to competition Rule 6b.
"""


def inspect_reference(raw: bytes):
    if type(raw) is not bytes or len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Exact bounded released reference required")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if [item.filename for item in entries] != list(MEMBERS):
            raise ValueError("Four exact ordered members required")
        contents = {}
        for item in entries:
            if item.is_dir() or item.flag_bits & 1 or item.file_size > 16384:
                raise ValueError("Unexpected reference envelope")
            content = archive.read(item)
            if hashlib.sha256(content).hexdigest() != MEMBERS[item.filename]:
                raise ValueError("Reference member changed")
            content.decode("utf-8", "strict")
            contents[item.filename] = content
        return entries, contents, archive.comment


def build(reference: Path, output: Path):
    if reference.is_symlink() or not reference.is_file() or reference.stat().st_size > 65536:
        raise ValueError("Bounded regular input archive required")
    raw = reference.read_bytes()
    entries, before, comment = inspect_reference(raw)
    after = dict(before)
    after["prompts/system.md"] += APPENDIX.encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", allowZip64=False) as archive:
        archive.comment = comment
        for item in entries:
            archive.writestr(item, after[item.filename])
    treatment = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(treatment)) as archive:
        if archive.namelist() != list(MEMBERS):
            raise ValueError("Treatment member order changed")
        for name in MEMBERS:
            if archive.read(name) != after[name]:
                raise ValueError("Treatment content differs from intended delta")
    terms = {}
    for name in ("LICENSE", "NOTICE"):
        source = Path(__file__).resolve().parent / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("Distribution terms missing")
        terms[name] = source.read_bytes()
    terms["NOTICE"] = DERIVATIVE_NOTICE.encode("utf-8")
    record = {"qualification": "PASS_SOURCE_ONLY_PROMPT_DELTA__HOLD_NATIVE_COST_RULE6B_AND_OFFICIAL",
              "reference_sha256": REFERENCE_SHA256, "treatment_sha256": hashlib.sha256(treatment).hexdigest(),
              "treatment_bytes": len(treatment), "changed_member": "prompts/system.md",
              "appendix_sha256": hashlib.sha256(APPENDIX.encode()).hexdigest(),
              "unchanged_members": list(MEMBERS)[:3], "native_execution": False,
              "runtime_model_sampling_unchanged": True, "official_score": None,
              "members": {name: {"bytes": len(after[name]), "sha256": hashlib.sha256(after[name]).hexdigest()} for name in MEMBERS}}
    output.mkdir(parents=True, exist_ok=False)
    with (output / "submission.zip").open("xb") as handle:
        handle.write(treatment)
    for name, content in terms.items():
        with (output / name).open("xb") as handle:
            handle.write(content)
    with (output / "SOURCE_RECEIPT.json").open("x") as handle:
        json.dump(record, handle, indent=2); handle.write("\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.reference, args.output), indent=2))


if __name__ == "__main__":
    main()
