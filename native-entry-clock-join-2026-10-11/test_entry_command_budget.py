"""Original invented child-glue/deadline controls; no native entry is invoked."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import bootstrap_budget as budget
import entry_command as command
import entry_join as entry
from test_entry_join import protocol


class BudgetTests(unittest.TestCase):
    def test_future_budget_preserves_origin_and_explicit_tail(self):
        p=protocol();p["entry_parent_cleanup_tail_seconds"]=65;raw=entry.encode(p)
        v=budget.parent_timeout(raw,entry.sha(raw),first_cell_start=100.,observed_origin=100.,current_monotonic=200.)
        self.assertEqual(v["absolute_deadline"],8800.);self.assertEqual(v["parent_absolute_deadline"],8865.)
        self.assertEqual(v["subprocess_timeout_seconds"],8665.);self.assertEqual(v["readiness_absolute_deadline"],3814.)

    def test_unknown_bool_or_outside_headroom_tail_refused(self):
        for tail in (None,True,0,121):
            p=protocol()
            if tail is not None:p["entry_parent_cleanup_tail_seconds"]=tail
            raw=entry.encode(p)
            with self.subTest(tail=tail),self.assertRaises(entry.Hold):
                budget.parent_timeout(raw,entry.sha(raw),first_cell_start=100.,observed_origin=100.,current_monotonic=200.)

    def test_protocol_pin_drift_refused(self):
        with self.assertRaisesRegex(entry.Hold,"PROTOCOL_SOURCE_DRIFT"):
            budget.parent_timeout(entry.encode(protocol()),"0"*64,first_cell_start=100.,observed_origin=100.,current_monotonic=200.)


class ChildGlueTests(unittest.TestCase):
    def setUp(self):
        parent=Path(os.environ.get("ENTRY_TEST_OUTPUT",str(Path(__file__).parent/"retained-invented-fixtures")))
        parent.mkdir(parents=True,exist_ok=True);self.folder=Path(tempfile.mkdtemp(prefix="child_fixture_",dir=parent))
        # This tiny fake is original test data. It has no evaluator/model code.
        self.source=b'''import json\ndef parse(raw):return json.loads(raw)\ndef encode(value):return json.dumps(value).encode()\ndef execute_checked_arm(manifest,argv):\n return {"status":manifest["status"],"fake_only":True,"argv":argv}\n'''
        self.source_path=self.folder/"invented_entry.txt"
        with self.source_path.open("xb") as stream:stream.write(self.source)
        self.manifest_path=self.folder/"invented_manifest.json"
        self.manifest=entry.encode({"status":"OBSERVED_CLOCK_SIDECAR_REVIEW_REQUIRED"})
        with self.manifest_path.open("xb") as stream:stream.write(self.manifest)

    def run_child(self,*,source_sha=None,manifest_sha=None):
        # Executes only the original argv glue against the above original fake.
        return subprocess.run([sys.executable,"-B","-c",command.CHILD_PROGRAM,str(self.manifest_path),
            manifest_sha or entry.sha(self.manifest),str(self.source_path),source_sha or entry.sha(self.source),
            "--toy","literal argument"],capture_output=True,text=True,timeout=5)

    def test_actual_child_glue_retains_literal_argv(self):
        r=self.run_child();self.assertEqual(r.returncode,0,r.stderr)
        value=json.loads(r.stdout);self.assertTrue(value["fake_only"]);self.assertEqual(value["argv"],["--toy","literal argument"])

    def test_child_source_or_manifest_drift_refused_before_fake(self):
        for specs in ({"source_sha":"0"*64},{"manifest_sha":"0"*64}):
            with self.subTest(specs=specs):
                r=self.run_child(**specs);self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,"")
                self.assertIn("ENTRY_CHILD_SOURCE_OR_ROUTE_PIN_DRIFT",r.stderr)

    def test_hold_fake_child_never_emits_success_exit(self):
        path=self.folder/"invented_hold_manifest.json";raw=entry.encode({"status":"HOLD"})
        with path.open("xb") as stream:stream.write(raw)
        r=subprocess.run([sys.executable,"-B","-c",command.CHILD_PROGRAM,str(path),entry.sha(raw),
            str(self.source_path),entry.sha(self.source)],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,2);self.assertEqual(json.loads(r.stdout)["status"],"HOLD")


if __name__=="__main__":unittest.main()
