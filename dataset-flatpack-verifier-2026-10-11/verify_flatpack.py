#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only flat dataset manifest verification. Python 3.10+, POSIX."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "flatpack-verification-1"
MAX_JSON_BYTES = 1_048_576
MAX_FILES = 5000
MAX_FILE_BYTES = 1_073_741_824
MAX_TOTAL_BYTES = 2_147_483_648
CHUNK_BYTES = 1_048_576
EXEMPT_NAMES = frozenset({"MANIFEST.json", "dataset-metadata.json"})
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMPONENT = re.compile(r"[A-Za-z0-9_.-]{1,180}\Z")
DEVICES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}

class Hold(ValueError):
    """A public error code, never a source-path or content dump."""

@dataclass(frozen=True)
class Entry:
    name: str
    bytes: int
    sha256: str

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Hold("DUPLICATE_JSON_KEY")
        result[key] = value
    return result

def _constant(value):
    raise Hold("NONFINITE_JSON_NUMBER")

def _json(data: bytes):
    if len(data) > MAX_JSON_BYTES:
        raise Hold("JSON_SIZE_LIMIT")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except Hold:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise Hold("INVALID_JSON") from None

def _component(s):
    if not isinstance(s, str) or not COMPONENT.fullmatch(s) or s in {".", ".."}:
        raise Hold("UNSAFE_PATH_COMPONENT")
    if s.endswith(".") or s.split(".", 1)[0].upper() in DEVICES:
        raise Hold("NONPORTABLE_PATH_COMPONENT")
    return s

def flat_name(s):
    return _component(s)

def target_path(s):
    if not isinstance(s, str) or not s or len(s) > 1024:
        raise Hold("INVALID_LAYOUT_TARGET")
    parts = s.split("/")
    if len(parts) > 16:
        raise Hold("LAYOUT_DEPTH_LIMIT")
    for part in parts:
        _component(part)
    return s

def _integer(value, minimum, maximum, code):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Hold(code)
    return value

def parse_manifest(data: bytes, expected_sha256: str):
    if not isinstance(expected_sha256, str) or not SHA.fullmatch(expected_sha256):
        raise Hold("INVALID_MANIFEST_PIN")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise Hold("MANIFEST_PIN_MISMATCH")
    document = _json(data)
    if not isinstance(document, dict):
        raise Hold("MANIFEST_NOT_OBJECT")
    files = document.get("files")
    count = _integer(document.get("file_count"), 1, MAX_FILES, "INVALID_FILE_COUNT")
    total = _integer(document.get("total_bytes"), 0, MAX_TOTAL_BYTES, "INVALID_TOTAL_BYTES")
    if isinstance(files, dict):
        raw = [(name, meta) for name, meta in files.items()]
        dialect = "name-keyed-object"
    elif isinstance(files, list):
        raw = []
        for row in files:
            if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
                raise Hold("INVALID_LIST_ENTRY")
            raw.append((row["path"], {"bytes": row["bytes"], "sha256": row["sha256"]}))
        dialect = "path-bearing-list"
    else:
        raise Hold("INVALID_FILES_COLLECTION")
    if len(raw) != count:
        raise Hold("FILE_COUNT_MISMATCH")
    entries, names = [], set()
    for name, meta in raw:
        flat_name(name)
        if name == "MANIFEST.json":
            raise Hold("SELF_REFERENTIAL_MANIFEST")
        if name.casefold() in names:
            raise Hold("DUPLICATE_OR_CASE_COLLIDING_SOURCE")
        names.add(name.casefold())
        if not isinstance(meta, dict) or set(meta) != {"bytes", "sha256"}:
            raise Hold("INVALID_FILE_METADATA")
        size = _integer(meta["bytes"], 0, MAX_FILE_BYTES, "INVALID_FILE_BYTES")
        digest = meta["sha256"]
        if not isinstance(digest, str) or not SHA.fullmatch(digest):
            raise Hold("INVALID_FILE_SHA256")
        entries.append(Entry(name, size, digest))
    if sum(e.bytes for e in entries) != total:
        raise Hold("TOTAL_BYTES_MISMATCH")
    return tuple(entries), dialect, total

def parse_layout(data: bytes, entries: tuple[Entry, ...], manifest_sha256: str):
    doc = _json(data)
    if not isinstance(doc, dict) or set(doc) != {"schema", "manifest_sha256", "paths"}:
        raise Hold("INVALID_LAYOUT_DOCUMENT")
    if doc["schema"] != "flatpack-layout-1" or doc["manifest_sha256"] != manifest_sha256:
        raise Hold("LAYOUT_PIN_MISMATCH")
    paths = doc["paths"]
    if not isinstance(paths, dict) or set(paths) != {e.name for e in entries}:
        raise Hold("LAYOUT_SOURCE_SET_MISMATCH")
    targets = set()
    for name, value in paths.items():
        flat_name(name)
        target_path(value)
        folded = value.casefold()
        if folded in targets:
            raise Hold("LAYOUT_TARGET_COLLISION")
        targets.add(folded)
    for value in targets:
        parts = value.split("/")
        for n in range(1, len(parts)):
            if "/".join(parts[:n]) in targets:
                raise Hold("LAYOUT_FILE_DIRECTORY_COLLISION")
    return dict(sorted(paths.items()))

def _stamp(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns

def _read_fd(fd, limit, capture):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise Hold("NONREGULAR_INPUT")
    if before.st_size > limit:
        raise Hold("INPUT_SIZE_LIMIT")
    hasher = hashlib.sha256()
    chunks, size = [], 0
    while True:
        chunk = os.read(fd, min(CHUNK_BYTES, limit - size + 1))
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise Hold("INPUT_SIZE_LIMIT")
        hasher.update(chunk)
        if capture:
            chunks.append(chunk)
    if _stamp(before) != _stamp(os.fstat(fd)) or size != before.st_size:
        raise Hold("INPUT_CHANGED_DURING_READ")
    return size, hasher.hexdigest(), b"".join(chunks) if capture else None

def _open_named(root_fd, name):
    flat_name(name)
    return os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)

def _read_named(root_fd, name, limit, capture=False):
    fd = _open_named(root_fd, name)
    try:
        return _read_fd(fd, limit, capture)
    finally:
        os.close(fd)

def read_layout(path):
    # The caller selects a trusted parent directory; a symlink final file is refused.
    fd = os.open(os.fspath(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        return _read_fd(fd, MAX_JSON_BYTES, True)[2]
    finally:
        os.close(fd)

def verify(root, manifest_sha256, layout_data=None):
    """Verify bytes against a supplied manifest pin; never writes or executes."""
    if not all(hasattr(os, key) for key in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise Hold("POSIX_FLAGS_UNAVAILABLE")
    root_fd = os.open(os.fspath(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root_stamp = _stamp(os.fstat(root_fd))
        _, observed_manifest_sha, data = _read_named(root_fd, "MANIFEST.json", MAX_JSON_BYTES, True)
        entries, dialect, total = parse_manifest(data, manifest_sha256)
        layout = None if layout_data is None else parse_layout(layout_data, entries, manifest_sha256)
        expected = {e.name for e in entries}
        actual = set(os.listdir(root_fd))
        if expected - actual:
            raise Hold("MISSING_MANIFESTED_FILES")
        ignored = actual - expected
        if not ignored <= EXEMPT_NAMES:
            raise Hold("UNLISTED_INPUTS")
        # Exempt metadata is not inspected or certified. Manifest must be a regular file.
        for entry in entries:
            size, digest, _ = _read_named(root_fd, entry.name, entry.bytes)
            if size != entry.bytes:
                raise Hold("FILE_SIZE_MISMATCH")
            if digest != entry.sha256:
                raise Hold("FILE_SHA256_MISMATCH")
        if set(os.listdir(root_fd)) != actual or _stamp(os.fstat(root_fd)) != root_stamp:
            raise Hold("ROOT_CHANGED_DURING_SCAN")
        return {"schema": SCHEMA, "status": "PASS_PINNED_BYTES", "manifest_sha256": observed_manifest_sha,
                "manifest_dialect": dialect, "verified_files": len(entries), "verified_bytes": total,
                "ignored_unverified_names": sorted(ignored - {"MANIFEST.json"}),
                "layout_status": "PASS_EXPLICIT_MAP" if layout is not None else "NOT_CHECKED",
                "layout_plan": layout, "authentication": "EXTERNAL_PIN_REQUIRED",
                "runtime_compatibility": "NOT_TESTED", "scientific_validity": "NOT_TESTED"}
    finally:
        os.close(root_fd)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--layout", type=Path, help="Optional explicit map; prints a plan and makes no changes")
    args = parser.parse_args()
    try:
        report = verify(args.root, args.manifest_sha256, None if args.layout is None else read_layout(args.layout))
    except Hold as error:
        report = {"schema": SCHEMA, "status": "HOLD", "reason": str(error)}
    except (OSError, OverflowError):
        report = {"schema": SCHEMA, "status": "HOLD", "reason": "FILESYSTEM_READ_FAILED"}
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "PASS_PINNED_BYTES" else 2

if __name__ == "__main__":
    raise SystemExit(main())
