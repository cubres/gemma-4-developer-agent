# SPDX-License-Identifier: Apache-2.0
"""Reproduce the credited Budget-Fit V5 archive; never run its agent.

All four compiler inputs and the original ZIP container are unchanged. The
small wrapper checks identity and writes new files exclusively. No Kaggle API,
model, task, native evaluator, subprocess or filesystem cleanup is invoked.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

UPSTREAM_URL = "https://www.kaggle.com/code/verracodeguacas/gemma-4-agent-budget-fit-single-agent?scriptVersionId=355310852"
UPSTREAM_AUTHOR = "Wilmer E. Henao (verracodeguacas)"
ZIP_SHA256 = "1cb73986bd9ad1682896d56516cfd3df7f4d5729c7ecfe7afda109c175dbbb94"
MEMBERS = {
    "agent.yaml": "680799291cc7d156d06fb7bfb5577f683ccc0d555b00e8ddb662d577f9bfa5e4",
    "configs/sampling.yaml": "571a934e89911734927533f1d36cbcc7b8d493592febe63b217e911cf7ed4926",
    "eval_config.yaml": "916cf6cb34a6cc3de39837fa72cac681599b9ac2a3ee0b893adadfd36474c531",
    "prompts/system.md": "475cc9b7fcc0dc295532f5cb5e1928f26a491f501837ad08b1c79bdbe1a3eaa4",
}
ARCHIVE_B64 = "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"


def inspect_archive(raw: bytes) -> dict:
    if type(raw) is not bytes or len(raw) > 65536:
        raise ValueError("Reference byte envelope")
    if hashlib.sha256(raw).hexdigest() != ZIP_SHA256:
        raise ValueError("Exact upstream ZIP changed")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if [entry.filename for entry in entries] != list(MEMBERS):
            raise ValueError("Four ordered compiler members required")
        if sum(entry.file_size for entry in entries) > 32768:
            raise ValueError("Reference unpacked envelope")
        observed = {}
        for entry in entries:
            if entry.is_dir() or entry.flag_bits & 1 or entry.file_size > 16384:
                raise ValueError("Unexpected reference member")
            content = archive.read(entry)
            if hashlib.sha256(content).hexdigest() != MEMBERS[entry.filename]:
                raise ValueError("Reference member changed")
            content.decode("utf-8", "strict")
            observed[entry.filename] = {"sha256": MEMBERS[entry.filename], "bytes": len(content)}
    return {"status": "BYTE_EXACT_RELEASED_REFERENCE", "zip_sha256": ZIP_SHA256,
            "zip_bytes": len(raw), "members": observed, "upstream": UPSTREAM_URL,
            "native_qualified": False, "own_official_score": None}


def emit(output: Path) -> dict:
    raw = base64.b64decode(ARCHIVE_B64, validate=True)
    receipt = inspect_archive(raw)
    # Attribution is distributed beside the exact compiler ZIP. Adding files
    # inside it would change the released package and its reproduction hash.
    terms = {}
    for name in ("LICENSE", "NOTICE.md"):
        path = Path(__file__).resolve().parent / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Distribution terms missing: " + name)
        terms[name] = path.read_bytes()
    output.mkdir(parents=True, exist_ok=False)
    with (output / "submission.zip").open("xb") as handle:
        handle.write(raw)
    for name, content in terms.items():
        with (output / name).open("xb") as handle:
            handle.write(content)
    with (output / "REFERENCE_RECEIPT.json").open("x") as handle:
        json.dump(receipt, handle, indent=2); handle.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(os.environ.get("GEMMA_REFERENCE_OUTPUT", "budgetfit_v5_reference")))
    args = parser.parse_args()
    print(json.dumps(emit(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
