#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded invented controls. All fixture files remain in the chosen new folder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_flatpack as v

SCRATCH = None

def encoded(d):
    return json.dumps(d, sort_keys=True).encode()

def sample(dialect="list"):
    files = {"code__runner.py": b"print('invented example')\n", "notes.txt": b"invented\n"}
    rows = [{"path": n, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()]
    body = rows if dialect == "list" else {r["path"]: {k: r[k] for k in ("bytes", "sha256")} for r in rows}
    return {"file_count": len(rows), "total_bytes": sum(len(x) for x in files.values()), "files": body}, files

class Controls(unittest.TestCase):
    def parsed(self, d):
        data = encoded(d)
        return v.parse_manifest(data, hashlib.sha256(data).hexdigest())

    def reject(self, d, reason):
        with self.assertRaisesRegex(v.Hold, "^" + reason + "$"):
            self.parsed(d)

    def disk(self, dialect="list"):
        p = SCRATCH / self._testMethodName
        p.mkdir()
        d, files = sample(dialect)
        for n, b in files.items():
            (p / n).write_bytes(b)
        data = encoded(d)
        (p / "MANIFEST.json").write_bytes(data)
        return p, hashlib.sha256(data).hexdigest(), d

    def layout(self, paths):
        d, _ = sample()
        entries, _, _ = self.parsed(d)
        return v.parse_layout(encoded({"schema": "flatpack-layout-1", "manifest_sha256": "a"*64, "paths": paths}), entries, "a"*64)

    def test_01_list(self):
        e, dialect, total = self.parsed(sample()[0]); self.assertEqual((len(e), dialect, total), (2, "path-bearing-list", 35))
    def test_02_object(self):
        e, dialect, total = self.parsed(sample("object")[0]); self.assertEqual((len(e), dialect), (2, "name-keyed-object"))
    def test_03_bad_pin(self):
        with self.assertRaisesRegex(v.Hold, "MANIFEST_PIN_MISMATCH"): v.parse_manifest(encoded(sample()[0]), "a"*64)
    def test_04_bad_pin_format(self):
        with self.assertRaisesRegex(v.Hold, "INVALID_MANIFEST_PIN"): v.parse_manifest(b"{}", "not a digest")
    def test_05_count(self):
        d,_=sample(); d["file_count"]=3; self.reject(d,"FILE_COUNT_MISMATCH")
    def test_06_total(self):
        d,_=sample(); d["total_bytes"]+=1; self.reject(d,"TOTAL_BYTES_MISMATCH")
    def test_07_bool_bytes(self):
        d,_=sample(); d["files"][0]["bytes"]=True; self.reject(d,"INVALID_FILE_BYTES")
    def test_08_bool_count(self):
        d,_=sample(); d["file_count"]=True; self.reject(d,"INVALID_FILE_COUNT")
    def test_09_negative_bytes(self):
        d,_=sample(); d["files"][0]["bytes"]=-1; self.reject(d,"INVALID_FILE_BYTES")
    def test_10_oversize(self):
        d,_=sample(); d["files"][0]["bytes"]=v.MAX_FILE_BYTES+1; self.reject(d,"INVALID_FILE_BYTES")
    def test_11_traversal(self):
        d,_=sample(); d["files"][0]["path"]="../runner.py"; self.reject(d,"UNSAFE_PATH_COMPONENT")
    def test_12_absolute(self):
        d,_=sample(); d["files"][0]["path"]="/runner.py"; self.reject(d,"UNSAFE_PATH_COMPONENT")
    def test_13_backslash(self):
        d,_=sample(); d["files"][0]["path"]="code\\runner.py"; self.reject(d,"UNSAFE_PATH_COMPONENT")
    def test_14_case_collision(self):
        d,_=sample(); d["files"][1]["path"]="CODE__RUNNER.PY"; self.reject(d,"DUPLICATE_OR_CASE_COLLIDING_SOURCE")
    def test_15_duplicate_name(self):
        d,_=sample(); d["files"][1]["path"]="code__runner.py"; self.reject(d,"DUPLICATE_OR_CASE_COLLIDING_SOURCE")
    def test_16_duplicate_json_key(self):
        data=b'{"file_count":2,"file_count":1}';
        with self.assertRaisesRegex(v.Hold,"DUPLICATE_JSON_KEY"): v.parse_manifest(data,hashlib.sha256(data).hexdigest())
    def test_17_nonfinite(self):
        data=b'{"files":NaN}'
        with self.assertRaisesRegex(v.Hold,"NONFINITE_JSON_NUMBER"): v.parse_manifest(data,hashlib.sha256(data).hexdigest())
    def test_18_self_ref(self):
        d,_=sample(); d["files"][0]["path"]="MANIFEST.json"; self.reject(d,"SELF_REFERENTIAL_MANIFEST")
    def test_19_hash_format(self):
        d,_=sample(); d["files"][0]["sha256"]="A"*64; self.reject(d,"INVALID_FILE_SHA256")
    def test_20_metadata_excess(self):
        d,_=sample("object"); d["files"]["notes.txt"]["extra"]=1; self.reject(d,"INVALID_FILE_METADATA")
    def test_21_disk_list(self):
        p,pin,_=self.disk(); r=v.verify(p,pin); self.assertEqual(r["status"],"PASS_PINNED_BYTES"); self.assertEqual(r["verified_files"],2)
    def test_22_disk_object(self):
        p,pin,_=self.disk("object"); self.assertEqual(v.verify(p,pin)["manifest_dialect"],"name-keyed-object")
    def test_23_corrupt(self):
        p,pin,_=self.disk(); (p/"notes.txt").write_bytes(b"inventez\n")
        with self.assertRaisesRegex(v.Hold,"FILE_SHA256_MISMATCH"): v.verify(p,pin)
    def test_24_extra(self):
        p,pin,_=self.disk(); (p/"extra.txt").write_bytes(b"extra")
        with self.assertRaisesRegex(v.Hold,"UNLISTED_INPUTS"): v.verify(p,pin)
    def test_25_missing(self):
        # Invent a manifest reference absent from the beginning; do not remove fixtures.
        p,pin,d=self.disk(); d["files"][1]["path"]="absent.txt"; data=encoded(d)
        (p/"MANIFEST.json").write_bytes(data)
        with self.assertRaisesRegex(v.Hold,"MISSING_MANIFESTED_FILES"): v.verify(p,hashlib.sha256(data).hexdigest())
    def test_26_metadata_unverified(self):
        p,pin,_=self.disk(); (p/"dataset-metadata.json").write_bytes(b"unverified")
        self.assertEqual(v.verify(p,pin)["ignored_unverified_names"],["dataset-metadata.json"])
    def test_27_symlink_file(self):
        d,files=sample()
        # Point at a sibling fixture directory; source file remains preserved.
        q=SCRATCH/(self._testMethodName+"_source"); q.mkdir(); (q/"notes.txt").write_bytes(files["notes.txt"])
        r=SCRATCH/(self._testMethodName+"_pack"); r.mkdir()
        (r/"code__runner.py").write_bytes(files["code__runner.py"]); (r/"notes.txt").symlink_to(q/"notes.txt")
        data=encoded(d); (r/"MANIFEST.json").write_bytes(data)
        with self.assertRaises(OSError): v.verify(r,hashlib.sha256(data).hexdigest())
    def test_28_root_symlink(self):
        p,pin,_=self.disk(); q=SCRATCH/(self._testMethodName+"_link"); q.symlink_to(p,target_is_directory=True)
        with self.assertRaises(OSError): v.verify(q,pin)
    def test_29_explicit_map(self):
        result=self.layout({"code__runner.py":"code/runner.py","notes.txt":"notes.txt"}); self.assertEqual(result["code__runner.py"],"code/runner.py")
    def test_30_literal_dunder(self):
        self.assertEqual(v.target_path("package/__main__.py"),"package/__main__.py")
    def test_31_target_collision(self):
        with self.assertRaisesRegex(v.Hold,"LAYOUT_TARGET_COLLISION"): self.layout({"code__runner.py":"A.txt","notes.txt":"a.txt"})
    def test_32_file_directory_collision(self):
        with self.assertRaisesRegex(v.Hold,"LAYOUT_FILE_DIRECTORY_COLLISION"): self.layout({"code__runner.py":"a","notes.txt":"a/b.txt"})
    def test_33_map_incomplete(self):
        with self.assertRaisesRegex(v.Hold,"LAYOUT_SOURCE_SET_MISMATCH"): self.layout({"notes.txt":"notes.txt"})
    def test_34_target_traversal(self):
        with self.assertRaisesRegex(v.Hold,"UNSAFE_PATH_COMPONENT"): self.layout({"code__runner.py":"../runner.py","notes.txt":"notes.txt"})
    def test_35_device(self):
        d,_=sample(); d["files"][0]["path"]="NUL.txt"; self.reject(d,"NONPORTABLE_PATH_COMPONENT")
    def test_36_zero_file(self):
        p=SCRATCH/self._testMethodName; p.mkdir(); data=encoded({"files":[{"path":"empty.txt","bytes":0,"sha256":hashlib.sha256(b"").hexdigest()}],"file_count":1,"total_bytes":0});(p/"MANIFEST.json").write_bytes(data);(p/"empty.txt").write_bytes(b"")
        self.assertEqual(v.verify(p,hashlib.sha256(data).hexdigest())["verified_bytes"],0)
    def test_37_large_json(self):
        with self.assertRaisesRegex(v.Hold,"JSON_SIZE_LIMIT"): v._json(b" "*(v.MAX_JSON_BYTES+1))
    def test_38_layout_pin(self):
        d,_=sample(); entries,_,_=self.parsed(d)
        with self.assertRaisesRegex(v.Hold,"LAYOUT_PIN_MISMATCH"): v.parse_layout(encoded({"schema":"flatpack-layout-1","manifest_sha256":"b"*64,"paths":{}}),entries,"a"*64)
    def test_39_size_growth(self):
        p,pin,_=self.disk(); (p/"notes.txt").write_bytes(b"invented with extra bytes\n")
        with self.assertRaisesRegex(v.Hold,"INPUT_SIZE_LIMIT"): v.verify(p,pin)
    def test_40_source_stays_identical(self):
        p,pin,_=self.disk(); before={x.name:x.read_bytes() for x in p.iterdir()};v.verify(p,pin); after={x.name:x.read_bytes() for x in p.iterdir()};self.assertEqual(before,after)
    def test_41_fifo_refused(self):
        p=SCRATCH/self._testMethodName;p.mkdir();d,files=sample();(p/"code__runner.py").write_bytes(files["code__runner.py"]);os.mkfifo(p/"notes.txt");data=encoded(d);(p/"MANIFEST.json").write_bytes(data)
        with self.assertRaisesRegex(v.Hold,"NONREGULAR_INPUT"): v.verify(p,hashlib.sha256(data).hexdigest())
    def test_42_directory_refused(self):
        p=SCRATCH/self._testMethodName;p.mkdir();d,files=sample();(p/"code__runner.py").write_bytes(files["code__runner.py"]);(p/"notes.txt").mkdir();data=encoded(d);(p/"MANIFEST.json").write_bytes(data)
        with self.assertRaisesRegex(v.Hold,"NONREGULAR_INPUT"): v.verify(p,hashlib.sha256(data).hexdigest())
    def test_43_invalid_utf8(self):
        with self.assertRaisesRegex(v.Hold,"INVALID_JSON"): v._json(b"\xff")
    def test_44_layout_absolute(self):
        with self.assertRaisesRegex(v.Hold,"UNSAFE_PATH_COMPONENT"): v.target_path("/tmp/runner.py")
    def test_45_layout_empty_segment(self):
        with self.assertRaisesRegex(v.Hold,"UNSAFE_PATH_COMPONENT"): v.target_path("code//runner.py")
    def test_46_layout_depth(self):
        with self.assertRaisesRegex(v.Hold,"LAYOUT_DEPTH_LIMIT"): v.target_path("/".join(["a"]*17))
    def test_47_layout_backslash(self):
        with self.assertRaisesRegex(v.Hold,"UNSAFE_PATH_COMPONENT"): v.target_path("code\\runner.py")
    def test_48_manifest_bool_total(self):
        d,_=sample();d["total_bytes"]=True;self.reject(d,"INVALID_TOTAL_BYTES")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--scratch-root",type=Path,required=True);args=parser.parse_args()
    SCRATCH=args.scratch_root.resolve();SCRATCH.mkdir(parents=False,exist_ok=False)
    unittest.main(argv=[sys.argv[0]],verbosity=2)
