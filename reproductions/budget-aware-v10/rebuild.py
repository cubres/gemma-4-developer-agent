#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild or verify the faithful four-member public Gemma agent ZIP.

No network, model loading, YAML execution, extraction, or file replacement.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

EXPECTED = {'agent.yaml': {'bytes': 314, 'sha256': '680799291cc7d156d06fb7bfb5577f683ccc0d555b00e8ddb662d577f9bfa5e4'}, 'configs/sampling.yaml': {'bytes': 119, 'sha256': '571a934e89911734927533f1d36cbcc7b8d493592febe63b217e911cf7ed4926'}, 'eval_config.yaml': {'bytes': 94, 'sha256': '916cf6cb34a6cc3de39837fa72cac681599b9ac2a3ee0b893adadfd36474c531'}, 'prompts/system.md': {'bytes': 6323, 'sha256': '7f8dde62578a247ffbfc1a519b712ae65849fcfae1ee70c49e0628cab74cbef6'}}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_bytes(archive_bytes):
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or set(names) != set(EXPECTED):
            raise ValueError("archive must contain exactly the four unique pinned members")
        for info in infos:
            pin = EXPECTED[info.filename]
            if info.file_size != pin["bytes"] or info.flag_bits & 1:
                raise ValueError("unexpected size or encryption: " + info.filename)
            if digest(archive.read(info)) != pin["sha256"]:
                raise ValueError("member hash mismatch: " + info.filename)
    return {"member_count": len(EXPECTED), "member_sha256": {
                name: pin["sha256"] for name, pin in EXPECTED.items()},
            "archive_bytes": len(archive_bytes), "archive_sha256": digest(archive_bytes),
            "entry_point": "agent.yaml", "model_executed": False}


def build_bytes():
    base = Path(__file__).resolve().parent / "bundle"
    contents = {}
    for name, pin in EXPECTED.items():
        path = base / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or symlinked bundle member: " + name)
        path.resolve().relative_to(base.resolve())
        with path.open("rb") as stream:
            data = stream.read(pin["bytes"] + 1)
        if len(data) != pin["bytes"] or digest(data) != pin["sha256"]:
            raise ValueError("bundle member changed: " + name)
        contents[name] = data
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in sorted(contents.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    data = buffer.getvalue()
    verify_bytes(data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="create a new .zip; refuses an existing path")
    mode.add_argument("--check", type=Path, help="verify an existing ZIP without extraction")
    args = parser.parse_args()
    if args.output is not None:
        if args.output.suffix.lower() != ".zip":
            parser.error("output filename must end in .zip")
        data = build_bytes()
        with args.output.open("xb") as stream:
            stream.write(data)
        receipt = verify_bytes(args.output.read_bytes())
    else:
        if args.check.stat().st_size > 1024 * 1024:
            parser.error("archive exceeds the 1 MiB inspection bound for this small bundle")
        receipt = verify_bytes(args.check.read_bytes())
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
