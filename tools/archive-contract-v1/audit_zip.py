#!/usr/bin/env python3
"""Bounded, read-only four-member ZIP audit. Original code; MIT licensed."""
import argparse
import hashlib
import io
import json
import re
import stat
import struct
import zipfile
import zlib
from pathlib import Path

NAMES = frozenset({"agent.yaml", "configs/sampling.yaml", "eval_config.yaml", "prompts/system.md"})
MAX_ARCHIVE = 8 * 1024 * 1024
MAX_MEMBER = 1024 * 1024
MAX_TOTAL = 4 * MAX_MEMBER
MAX_MANIFEST = 16 * 1024
SCHEMA = "four-member-producer-manifest/1"


class AuditError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def fail(code, detail):
    raise AuditError(code, detail)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("MANIFEST_DUPLICATE_KEY", "Manifest JSON contains a repeated key")
        result[key] = value
    return result


def parse_manifest(data):
    if len(data) > MAX_MANIFEST:
        fail("MANIFEST_TOO_LARGE", "Manifest exceeds 16 KiB")
    try:
        doc = json.loads(data, object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        fail("MANIFEST_INVALID", type(exc).__name__)
    if not isinstance(doc, dict) or set(doc) != {"schema", "members"} or doc["schema"] != SCHEMA:
        fail("MANIFEST_SCHEMA", "Expected schema and members fields only")
    members = doc["members"]
    if not isinstance(members, dict) or set(members) != NAMES:
        fail("MANIFEST_NAMES", "Manifest must bind the four exact producer member names")
    for name, expected in members.items():
        if not isinstance(expected, dict) or set(expected) != {"bytes", "sha256"}:
            fail("MANIFEST_MEMBER", "Each member needs bytes and sha256 only")
        size = expected["bytes"]
        digest = expected["sha256"]
        if type(size) is not int or not 0 <= size <= MAX_MEMBER:
            fail("MANIFEST_SIZE", "Each member size must be an integer between 0 and 1 MiB")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail("MANIFEST_DIGEST", "Expected lowercase hexadecimal SHA-256")
    return doc


def validate_name(name):
    if not name or "\\" in name or "\x00" in name or ":" in name:
        fail("UNSAFE_PATH", "Unsafe ZIP member name")
    if any(part in {"", ".", ".."} for part in name.split("/")):
        fail("UNSAFE_PATH", "Absolute, empty or dot path component")


def exact_stream(data, info, central_start, next_offset):
    """Verify local header and actual stream; ZipExtFile can hide a forged suffix."""
    offset = info.header_offset
    if offset < 0 or offset + 30 > central_start:
        fail("INVALID_LAYOUT", "Local header lies outside the member region")
    signature, version, flags, method, tm, dt, crc, compressed, decoded, nlen, xlen = struct.unpack_from(
        "<4s5H3I2H", data, offset)
    if signature != b"PK\x03\x04" or flags != info.flag_bits or method != info.compress_type:
        fail("INVALID_LAYOUT", "Local and central headers disagree")
    if flags & ~(0x800):
        fail("UNSUPPORTED_FLAGS", "This narrow contract accepts only the UTF-8 name flag")
    if xlen or info.extra or info.comment:
        fail("UNSUPPORTED_METADATA", "Extra fields and member comments are outside this contract")
    start = offset + 30 + nlen + xlen
    end = start + compressed
    if (crc, compressed, decoded) != (info.CRC, info.compress_size, info.file_size):
        fail("INVALID_LAYOUT", "Local and central sizes or CRC disagree")
    if data[offset + 30:offset + 30 + nlen] != info.filename.encode("ascii"):
        fail("INVALID_LAYOUT", "Local and central member names disagree")
    if end != next_offset or end > central_start:
        fail("INVALID_LAYOUT", "Member gaps, overlaps or hidden trailing bytes")
    payload = data[start:end]
    if method == zipfile.ZIP_STORED:
        output = payload
    else:
        decoder = zlib.decompressobj(-15)
        output = decoder.decompress(payload, MAX_MEMBER + 1)
        if len(output) > MAX_MEMBER:
            fail("OBSERVED_TOO_LARGE", "Actual decompressed member exceeds 1 MiB")
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            fail("INVALID_STREAM", "Deflate stream is incomplete or contains trailing data")
    if len(output) != decoded:
        fail("SIZE_MISMATCH", "Actual stream size differs from the declared size")
    if zlib.crc32(output) & 0xffffffff != crc:
        fail("CRC_MISMATCH", "Actual stream CRC differs from the declared CRC")
    return output


def central_boundary(data, infos):
    if len(data) < 22:
        fail("INVALID_LAYOUT", "Missing plain ZIP end record")
    sig, disk, central_disk, disk_count, count, size, offset, comment_size = struct.unpack_from(
        "<4s4H2IH", data, len(data) - 22)
    if (sig != b"PK\x05\x06" or disk or central_disk or comment_size
            or disk_count != count or count != len(infos) or offset + size != len(data) - 22):
        fail("INVALID_LAYOUT", "Only a plain single-disk ZIP with no archive comment or trailer is accepted")
    ordered = sorted(infos, key=lambda item: item.header_offset)
    if not ordered or ordered[0].header_offset != 0:
        fail("INVALID_LAYOUT", "Archive prefix or missing local header")
    # Reject central-directory gaps or unparsed records as well.
    cursor = offset
    for info in infos:
        if data[cursor:cursor + 4] != b"PK\x01\x02" or cursor + 46 > len(data) - 22:
            fail("INVALID_LAYOUT", "Malformed central directory")
        name_size, extra_size, member_comment_size = struct.unpack_from("<3H", data, cursor + 28)
        cursor += 46 + name_size + extra_size + member_comment_size
    if cursor != len(data) - 22:
        fail("INVALID_LAYOUT", "Central directory has extra bytes")
    return offset, ordered


def audit_bytes(data, manifest, expected_archive_sha256=None):
    """Audit one bounded byte snapshot. Never extract, parse YAML, or execute members."""
    if len(data) > MAX_ARCHIVE:
        fail("ARCHIVE_TOO_LARGE", "Archive exceeds 8 MiB")
    # Revalidate in-memory callers too; do not trust a constructed Python dict.
    manifest = parse_manifest(json.dumps(manifest).encode())
    digest = sha256(data)
    if expected_archive_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_archive_sha256):
            fail("ARCHIVE_PIN_INVALID", "Expected lowercase hexadecimal SHA-256")
        if digest != expected_archive_sha256:
            fail("ARCHIVE_HASH_MISMATCH", "Archive bytes do not match the supplied independent pin")
    measured = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > len(NAMES):
                fail("ENTRY_COUNT", "More than four entries")
            seen = set()
            total_declared = 0
            for info in infos:
                # orig_filename retains an embedded NUL that filename truncates.
                validate_name(info.orig_filename)
                if info.filename in seen:
                    fail("DUPLICATE_MEMBER", "Repeated ZIP member name")
                seen.add(info.filename)
                if info.flag_bits & (1 | 64):
                    fail("ENCRYPTED_MEMBER", "Encrypted members are not accepted")
                kind = stat.S_IFMT(info.external_attr >> 16)
                if kind == stat.S_IFLNK:
                    fail("SYMLINK_MEMBER", "Symlink members are not accepted")
                if kind not in {0, stat.S_IFREG}:
                    fail("NON_REGULAR_MEMBER", "Only regular files are accepted")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    fail("UNSUPPORTED_COMPRESSION", "Only stored and deflated members are supported")
                if info.file_size > MAX_MEMBER or info.compress_size > MAX_ARCHIVE:
                    fail("MEMBER_TOO_LARGE", "A member exceeds the declared size limits")
                total_declared += info.file_size
                if total_declared > MAX_TOTAL:
                    fail("TOTAL_TOO_LARGE", "Declared total exceeds 4 MiB")
            if seen != NAMES:
                fail("MEMBER_SET", "Archive has missing or unexpected members")
            central_start, ordered = central_boundary(data, infos)
            next_offsets = {info.filename: ordered[index + 1].header_offset
                            if index + 1 < len(ordered) else central_start
                            for index, info in enumerate(ordered)}
            total_observed = 0
            for info in sorted(infos, key=lambda item: item.filename):
                expected = manifest["members"][info.filename]
                if info.file_size != expected["bytes"]:
                    fail("SIZE_MISMATCH", "A member size differs from the producer manifest")
                output = exact_stream(data, info, central_start, next_offsets[info.filename])
                observed = len(output)
                total_observed += observed
                if observed > MAX_MEMBER or total_observed > MAX_TOTAL:
                    fail("OBSERVED_TOO_LARGE", "Decoded bytes exceed the limits")
                if observed != expected["bytes"]:
                    fail("SIZE_MISMATCH", "Decoded size differs from the producer manifest")
                member_digest = sha256(output)
                if member_digest != expected["sha256"]:
                    fail("HASH_MISMATCH", "A member hash differs from the producer manifest")
                measured[info.filename] = {"bytes": observed, "sha256": member_digest}
    except AuditError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError, RuntimeError,
            NotImplementedError, ValueError, struct.error, zlib.error, UnicodeError) as exc:
        fail("INVALID_ZIP", type(exc).__name__)
    return {"schema": "four-member-archive-audit/1", "status": "PASS",
            "archive_bytes": len(data), "archive_sha256": digest,
            "independent_archive_pin_checked": expected_archive_sha256 is not None,
            "members": measured,
            "scope": "Producer byte contract only; no agent execution, score or native association proof"}


def read_bounded(path, limit, code):
    with Path(path).open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        fail(code, "File exceeds the configured byte limit")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--expected-archive-sha256", help="Optional independently recorded exact ZIP pin")
    args = parser.parse_args(argv)
    data = None
    try:
        manifest = parse_manifest(read_bounded(args.manifest, MAX_MANIFEST, "MANIFEST_TOO_LARGE"))
        data = read_bounded(args.archive, MAX_ARCHIVE, "ARCHIVE_TOO_LARGE")
        report = audit_bytes(data, manifest, args.expected_archive_sha256)
    except (AuditError, OSError) as exc:
        report = {"schema": "four-member-archive-audit/1", "status": "REJECT",
                  "code": exc.code if isinstance(exc, AuditError) else "IO_ERROR",
                  "detail": exc.detail if isinstance(exc, AuditError) else type(exc).__name__}
        if data is not None:
            report.update(archive_bytes=len(data), archive_sha256=sha256(data))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
