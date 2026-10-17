"""Synthetic tests only; no model, benchmark task, notebook or network required."""
import copy
import io
import json
import stat
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

import audit_zip as audit
import make_fixtures as demo


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"schema": audit.SCHEMA, "members": {
            name: {"bytes": len(data), "sha256": audit.sha256(data)}
            for name, data in demo.MEMBERS.items()}}
        self.entries = [(name, data, stat.S_IFREG | 0o644) for name, data in sorted(demo.MEMBERS.items())]
        self.good = demo.zip_bytes(self.entries)

    def reject(self, data, code, manifest=None):
        with self.assertRaises(audit.AuditError) as caught:
            audit.audit_bytes(data, manifest if manifest is not None else self.manifest)
        self.assertEqual(caught.exception.code, code)

    def test_all_eleven_invented_cases(self):
        for name, data, expected, purpose in demo.fixtures():
            with self.subTest(case=name):
                if expected == "PASS":
                    self.assertEqual(audit.audit_bytes(data, self.manifest)["status"], "PASS")
                else:
                    self.reject(data, expected)

    def test_pin_distinguishes_member_equivalence(self):
        other = demo.zip_bytes(self.entries, date=34)
        self.assertEqual(audit.audit_bytes(other, self.manifest)["members"], self.manifest["members"])
        with self.assertRaises(audit.AuditError) as caught:
            audit.audit_bytes(other, self.manifest, audit.sha256(self.good))
        self.assertEqual(caught.exception.code, "ARCHIVE_HASH_MISMATCH")
        self.assertTrue(audit.audit_bytes(self.good, self.manifest, audit.sha256(self.good))["independent_archive_pin_checked"])

    def test_regular_zip_reader_can_accept_forged_prefix(self):
        forged = dict((name, data) for name, data, _, _ in demo.fixtures())["forged_prefix.zip"]
        # This regression demonstrates why successful ZipExtFile reads alone
        # are insufficient; our independent stream check still rejects it.
        with zipfile.ZipFile(io.BytesIO(forged)) as archive:
            self.assertEqual(archive.read("agent.yaml"), demo.MEMBERS["agent.yaml"])
        self.reject(forged, "SIZE_MISMATCH")

    def test_unsafe_names_and_nonregular_metadata(self):
        for name in ["/agent.yaml", "configs//sampling.yaml", "./agent.yaml", "a\\b", "C:agent.yaml", "agent.yaml\x00suffix"]:
            with self.subTest(name=name):
                entries = [(name, self.entries[0][1], self.entries[0][2])] + self.entries[1:]
                self.reject(demo.zip_bytes(entries), "UNSAFE_PATH")
        entries = [(self.entries[0][0], self.entries[0][1], stat.S_IFIFO | 0o600)] + self.entries[1:]
        self.reject(demo.zip_bytes(entries), "NON_REGULAR_MEMBER")

    def test_extra_entries_and_unknown_member(self):
        self.reject(demo.zip_bytes(self.entries + [("extra", b"invented", stat.S_IFREG | 0o644)]), "ENTRY_COUNT")
        self.reject(demo.zip_bytes([("other", self.entries[0][1], self.entries[0][2])] + self.entries[1:]), "MEMBER_SET")

    def test_no_hidden_wrapper_or_bad_crc(self):
        self.reject(b"wrapper" + self.good, "INVALID_LAYOUT")
        self.reject(self.good + b"trailer", "INVALID_LAYOUT")
        self.reject(self.good[:-1], "INVALID_ZIP")
        damaged = bytearray(self.good); damaged[30 + len("agent.yaml")] ^= 1
        self.reject(bytes(damaged), "CRC_MISMATCH")
        self.reject(b"not a ZIP", "INVALID_ZIP")

    def test_local_header_disagreement_and_unsupported_flags(self):
        damaged = bytearray(self.good); damaged[30] = ord("z")
        self.reject(bytes(damaged), "INVALID_LAYOUT")
        self.reject(demo.zip_bytes(self.entries, flags=8), "UNSUPPORTED_FLAGS")

    def test_manifest_ambiguity_and_types(self):
        with self.assertRaises(audit.AuditError) as caught:
            audit.parse_manifest(b'{"schema":1,"schema":2}')
        self.assertEqual(caught.exception.code, "MANIFEST_DUPLICATE_KEY")
        for value in [True, -1, audit.MAX_MEMBER + 1]:
            changed = copy.deepcopy(self.manifest); changed["members"]["agent.yaml"]["bytes"] = value
            self.reject(self.good, "MANIFEST_SIZE", changed)
        changed = copy.deepcopy(self.manifest); changed["members"]["agent.yaml"]["sha256"] = "x" * 64
        self.reject(self.good, "MANIFEST_DIGEST", changed)

    def test_actual_oversize_and_limit_boundary(self):
        for size in [audit.MAX_MEMBER, audit.MAX_MEMBER + 1]:
            content = b"x" * size
            entries = [(name, content if name == "agent.yaml" else data, mode) for name, data, mode in self.entries]
            encoded = demo.zip_bytes(entries)
            manifest = copy.deepcopy(self.manifest)
            manifest["members"]["agent.yaml"] = {"bytes": size, "sha256": audit.sha256(content)}
            if size == audit.MAX_MEMBER:
                self.assertEqual(audit.audit_bytes(encoded, manifest)["status"], "PASS")
            else:
                self.reject(encoded, "MEMBER_TOO_LARGE")
        self.reject(b"x" * (audit.MAX_ARCHIVE + 1), "ARCHIVE_TOO_LARGE")

    def test_actual_deflate_overflow_with_forged_header(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data, mode in self.entries:
                archive.writestr(name, b"x" * (audit.MAX_MEMBER + 1) if name == "agent.yaml" else data)
        encoded = bytearray(stream.getvalue())
        # Forge only the size to match the producer. Decode still hits the cap.
        central = encoded.index(b"PK\x01\x02")
        declared = self.manifest["members"]["agent.yaml"]["bytes"]
        struct.pack_into("<I", encoded, 22, declared)
        struct.pack_into("<I", encoded, central + 24, declared)
        self.reject(bytes(encoded), "OBSERVED_TOO_LARGE")

    def test_generated_files_reproducible_and_exclusive(self):
        with tempfile.TemporaryDirectory() as parent:
            a, b = Path(parent) / "a", Path(parent) / "b"
            demo.generate(a); demo.generate(b)
            self.assertEqual({p.name: p.read_bytes() for p in a.iterdir()}, {p.name: p.read_bytes() for p in b.iterdir()})
            with self.assertRaises(FileExistsError):
                demo.generate(a)
            checked_in = Path(__file__).parent / "fixtures"
            self.assertEqual({p.name: p.read_bytes() for p in a.iterdir()}, {p.name: p.read_bytes() for p in checked_in.iterdir()})


if __name__ == "__main__":
    unittest.main()
