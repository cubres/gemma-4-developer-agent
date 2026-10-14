#!/usr/bin/env python3
"""Rebuild original E03 source; no model, network, notebook or submission actions."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import zipfile
import zlib

BASE = Path(__file__).resolve().parent
CONSTANTS_SHA256 = "d186041bad9caed422b483a15cad116385bc526f15a01c1b48e305f646738e2f"
MANIFEST_SHA256 = "96f3f617f67a6f3617a1cd4cb833ca6755650338488912b98e7a3008a0623a33"
ACCEPTED_SHA256 = "0311b8a71ff9498aaaca30a8a6d22be5622a62539eaef0360dd585d401fe3af9"
MAX_FILE_BYTES = 65536


def digest(data):
    return hashlib.sha256(data).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def bound_file(path, expected, maximum=MAX_FILE_BYTES):
    need(path.is_file() and not path.is_symlink(), "Expected regular non-symlink input")
    need(path.stat().st_size <= maximum, "Input exceeds bounded size")
    data = path.read_bytes()
    need(digest(data) == expected, "Input SHA256 mismatch")
    return data


def inputs(accepted_path):
    constants = json.loads(bound_file(BASE / "BUILDER_CONSTANTS.json", CONSTANTS_SHA256))
    manifest = json.loads(bound_file(BASE / "SOURCE_MANIFEST.json", MANIFEST_SHA256))
    order = constants["order"]
    expected_order = ["agent.yaml", "configs/sampling.yaml", "eval_config.yaml",
                      "prompts/system.md", "LICENSE.txt", "NOTICE.txt"]
    need(order == expected_order, "Six-member order differs")
    accepted_bytes = bound_file(accepted_path, ACCEPTED_SHA256)
    need(len(accepted_bytes) == 8055, "Accepted E01 ZIP size differs")
    with zipfile.ZipFile(io.BytesIO(accepted_bytes), "r") as archive:
        need(len(archive.namelist()) == 6 and set(archive.namelist()) == set(order),
             "Accepted archive member set differs")
        need(sum(x.file_size for x in archive.infolist()) == 17894,
             "Accepted uncompressed size differs")
        accepted = {name: archive.read(name) for name in order}
    for name in order:
        need(digest(accepted[name]) == constants["accepted"][name],
             "Accepted member differs")
    prefix = bound_file(BASE / "ISSUE_CONTRACT.txt", constants["prefix_sha"])
    notice = bound_file(BASE / "NOTICE_ADDITION.txt", constants["notice_sha"])
    need(len(prefix.decode("utf-8").split()) == 50, "Prefix word count differs")
    candidate_root = BASE / "candidate"
    need(candidate_root.is_dir() and not candidate_root.is_symlink(),
         "Candidate source root differs")
    actual = set()
    for path in candidate_root.rglob("*"):
        need(not path.is_symlink(), "Candidate source contains a symlink")
        if path.is_file():
            actual.add(path.relative_to(candidate_root).as_posix())
        else:
            need(path.is_dir(), "Candidate source contains non-regular input")
    need(actual == set(order), "Candidate must contain exactly six source members")
    candidate = {name: bound_file(candidate_root / name, constants["candidate"][name])
                 for name in order}
    need(candidate["prompts/system.md"] == prefix + accepted["prompts/system.md"],
         "Original scored prompt or coverage checkpoint changed")
    need(candidate["NOTICE.txt"] == accepted["NOTICE.txt"] + notice,
         "Original attribution changed")
    for name in ("agent.yaml", "configs/sampling.yaml", "eval_config.yaml", "LICENSE.txt"):
        need(candidate[name] == accepted[name], "Unchanged member differs")
    for name in order:
        need(manifest["members"][name]["candidate_sha256"] == digest(candidate[name]),
             "Source manifest member differs")
    need(encode_archive(order, accepted) == accepted_bytes,
         "Current Python/zlib does not reproduce exact accepted ZIP wrapper")
    return order, candidate


def encode_archive(order, members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", allowZip64=False) as archive:
        archive.comment = b""
        for name in order:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o644 << 16
            info.internal_attr = 0
            info.extra = b""
            info.comment = b""
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, members[name])
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="A fresh output directory whose parent already exists")
    args = parser.parse_args()
    order, candidate = inputs(args.accepted_zip)
    candidate_archive = encode_archive(order, candidate)
    out = args.out
    need(not out.exists() and not out.is_symlink(), "Output already exists; preserve it")
    need(out.parent.is_dir(), "Output parent must already exist")
    out.mkdir()
    for name in order:
        path = out / "source" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(candidate[name])
    zip_path = out / "submission.zip"
    with zip_path.open("xb") as stream:
        stream.write(candidate_archive)
    with zipfile.ZipFile(zip_path, "r") as archive:
        need(archive.namelist() == order, "Output member order differs")
        for name in order:
            need(archive.read(name) == candidate[name], "Output member bytes differ")
            need(archive.getinfo(name).compress_type == zipfile.ZIP_DEFLATED,
                 "Unexpected compression")
    receipt = {
        "schema": "gemma-e03-actual-cpu-source-rebuild/1",
        "status": "PASS_SOURCE_REBUILD_ONLY_NO_MODEL_QUALITY_CLAIM",
        "accepted_submission_id": 57111761,
        "accepted_zip_sha256": ACCEPTED_SHA256,
        "source_manifest_sha256": MANIFEST_SHA256,
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "candidate_zip_sha256": digest(zip_path.read_bytes()),
        "candidate_zip_bytes": zip_path.stat().st_size,
        "archive_format": "exact E01 wrapper: fixed-order ZIP_DEFLATED; 1980-01-01; 0644 permissions",
        "accepted_wrapper_byte_roundtrip_verified": True,
        "members": {name: {"bytes": len(candidate[name]), "sha256": digest(candidate[name])}
                    for name in order},
        "python": sys.version,
        "zlib_build_version": zlib.ZLIB_VERSION,
        "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        "platform": platform.platform(),
        "model_calls": 0,
        "native_quality": "UNMEASURED",
        "official_score": None,
        "submission_made": False,
    }
    with (out / "BUILD_RECEIPT.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"],
                      "candidate_zip_sha256": receipt["candidate_zip_sha256"],
                      "candidate_zip_bytes": receipt["candidate_zip_bytes"]}))


if __name__ == "__main__":
    main()
