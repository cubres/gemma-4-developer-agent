#!/usr/bin/env python3
"""Generate only invented ZIP illustrations into a new directory. MIT licensed."""
import argparse
import csv
import io
import json
import stat
import struct
import zlib
from pathlib import Path

from audit_zip import MAX_MEMBER, SCHEMA, sha256

MEMBERS = {
    "agent.yaml": b"# Invented illustration, not an agent configuration.\nexample_label: paper-crane\n",
    "configs/sampling.yaml": b"# Invented illustration.\nexample_beads: [2, 4, 6]\n",
    "eval_config.yaml": b"# Invented illustration.\nexample_colors: [blue, green]\n",
    "prompts/system.md": b"# An imaginary library\nArrange paper cranes by color. No real benchmark task is represented.\n",
}


def zip_bytes(entries, *, deflated=False, date=33, flags=0, oversize=False, forged_prefix=False):
    """Small explicit ZIP encoder; fixed metadata, no zlib-version dependence.

    Deflated examples use a single uncompressed DEFLATE block. This is valid
    method 8 data, deliberately without any compression-ratio claim.
    """
    local, central = bytearray(), bytearray()
    for index, (name, content, mode) in enumerate(entries):
        encoded = name.encode("ascii")
        actual = content + b"HIDDEN SUFFIX" if forged_prefix and index == 0 else content
        crc = zlib.crc32(content) & 0xffffffff
        decoded = MAX_MEMBER + 1 if oversize and index == 0 else len(content)
        method = 8 if deflated else 0
        if deflated:
            assert len(actual) < 65536
            payload = b"\x01" + struct.pack("<HH", len(actual), len(actual) ^ 65535) + actual
        else:
            payload = actual
        offset = len(local)
        local += struct.pack("<4s5H3I2H", b"PK\x03\x04", 20, flags, method, 0, date,
                             crc, len(payload), decoded, len(encoded), 0) + encoded + payload
        central += struct.pack("<4s6H3I5H2I", b"PK\x01\x02", (3 << 8) | 20, 20,
                               flags, method, 0, date, crc, len(payload), decoded,
                               len(encoded), 0, 0, 0, 0, mode << 16, offset) + encoded
    end = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, len(entries), len(entries),
                      len(central), len(local), 0)
    return bytes(local + central + end)


def fixtures():
    entries = [(name, content, stat.S_IFREG | 0o644) for name, content in sorted(MEMBERS.items())]
    changed = list(entries)
    name, content, mode = changed[0]
    changed[0] = (name, content.replace(b"crane", b"flame"), mode)
    duplicate = entries[:3] + [entries[0]]
    traversal = list(entries); traversal[0] = ("../agent.yaml", entries[0][1], entries[0][2])
    symlink = list(entries); symlink[0] = (entries[0][0], entries[0][1], stat.S_IFLNK | 0o777)
    return [
        ("valid_stored.zip", zip_bytes(entries), "PASS", "Exact invented producer members"),
        ("valid_deflated.zip", zip_bytes(entries, deflated=True), "PASS", "Same members, different valid storage method"),
        ("valid_timestamp.zip", zip_bytes(entries, date=34), "PASS", "Same members, different valid timestamp"),
        ("changed_content.zip", zip_bytes(changed), "HASH_MISMATCH", "Same length, changed invented content"),
        ("duplicate_name.zip", zip_bytes(duplicate), "DUPLICATE_MEMBER", "Repeated member replaces one required member"),
        ("path_traversal.zip", zip_bytes(traversal), "UNSAFE_PATH", "Dot-dot member name; never extracted"),
        ("encrypted_flag.zip", zip_bytes(entries, flags=1), "ENCRYPTED_MEMBER", "Marked encrypted; payload is only invented plaintext"),
        ("symlink_metadata.zip", zip_bytes(symlink), "SYMLINK_MEMBER", "Symlink metadata; no filesystem link is created"),
        ("oversize_declaration.zip", zip_bytes(entries, oversize=True), "MEMBER_TOO_LARGE", "Tiny fixture with an oversized declared member"),
        ("missing_member.zip", zip_bytes(entries[:-1]), "MEMBER_SET", "One required member omitted"),
        ("forged_prefix.zip", zip_bytes(entries, deflated=True, forged_prefix=True), "SIZE_MISMATCH", "Declared prefix plus CRC hides actual deflate suffix"),
    ]


def generate(destination):
    destination = Path(destination)
    destination.mkdir(parents=False, exist_ok=False)
    manifest = {"schema": SCHEMA, "members": {
        name: {"bytes": len(content), "sha256": sha256(content)}
        for name, content in sorted(MEMBERS.items())}}
    (destination / "producer_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    rows = []
    for name, data, expected, purpose in fixtures():
        with (destination / name).open("xb") as handle:
            handle.write(data)
        rows.append({"file": name, "bytes": len(data), "sha256": sha256(data),
                     "expected": expected, "purpose": purpose})
    with (destination / "cases.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256", "expected", "purpose"], lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="Must not exist; nothing is overwritten")
    args = parser.parse_args()
    rows = generate(args.destination)
    print(json.dumps({"created_cases": len(rows), "content": "wholly invented illustrations"}, sort_keys=True))


if __name__ == "__main__":
    main()
