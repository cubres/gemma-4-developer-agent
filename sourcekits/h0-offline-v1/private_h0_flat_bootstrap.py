#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""NEW flat offline-source H0 wrapper. Default describes HOLD; only root may execute.

Raw logs stay in a fixed exclusive /tmp attempt. Only a pre-reviewed bounded
serializer may reconstruct public receipts. There is no network/source fallback.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import types

CORE_COMMIT='66341ae7cb84d6cdeddd2be79f8d6ea17c661cac'
CORE_SHA='cd9154a22e6139289dabdada6610acb3f4f781f304e3d72351a85da00f8a9090'
CORE_FILES={'FORK_AND_REBUILD.md': 'cbdaaeb52558f1f7d52def97ccbdd45e07d05cbc927782806da523029dd1a4e4', 'LICENSE': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30', 'NOTICE': '8ab5cb1bf0ec033bae7ed6fbea1e9612f39120394ddaac16c7fec9cc7609e1f7', 'OPERATOR_ADMISSION_CONTRACT.json': 'd0bc400921a96eca388f2dd81f6cc3a1c8408e019413d5ccb4bea181bdd7ce0b', 'README.md': 'ff032898dc4e4c12f772e391f0570926a72920b7c160d4954cd1249ac8d948d8', 'ROOT_H0_ADMISSION.json': '37aa13d0801901b18bd0dae448ed8d175316414e68ab889f5b55a1521750ee3a', 'payload_manifest.json': '2ceb01793ab9e0df8e9fa7f837f7deadc1f8392c93ba222d70706e3803044224', 'run_h0.py': 'cd9154a22e6139289dabdada6610acb3f4f781f304e3d72351a85da00f8a9090'}


def need(ok):
    if not ok:raise ValueError('PRIVATE_H0_ROOT_OR_SOURCE_GATE_CLOSED')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_source(name,path):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(Path(path).read_text(),str(path),'exec'),module.__dict__)
    return module


def check_bundle(directory,expected_manifest):
    root=Path(directory).resolve(strict=True)
    need(root.is_dir() and (root/'BUNDLE_MANIFEST.json').is_file()
         and not (root/'BUNDLE_MANIFEST.json').is_symlink())
    need(sha(root/'BUNDLE_MANIFEST.json')==expected_manifest)
    m=json.loads((root/'BUNDLE_MANIFEST.json').read_text())
    need(set(m)=={'schema','status','core_git_commit','files','core'}
         and m['schema']=='gemma-h0-flat-offline-bundle/1' and m['core_git_commit']==CORE_COMMIT)
    need(set(p.name for p in root.iterdir())==set(m['files'])|{'BUNDLE_MANIFEST.json'})
    need(set(m['core'])==set(CORE_FILES) and 0<sum(v['bytes'] for v in m['files'].values())<=500000)
    for name,entry in m['files'].items():
        f=root/name
        need(Path(name).name==name and f.is_file() and not f.is_symlink()
             and type(entry['bytes']) is int and 0<=entry['bytes']<=100000
             and f.stat().st_size==entry['bytes'] and sha(f)==entry['sha256'])
    for name,expected in CORE_FILES.items():
        entry=m['core'][name]
        need(entry['sha256']==expected and m['files'][entry['stored_name']]['sha256']==expected)
    need(Path(__file__).resolve()==root/'private_h0_flat_bootstrap.py')
    return root,m


CHECKS=set('IDENTITY_SOURCE_FULL17_TERMINAL EXACT_PUBLIC_BUNDLE_ID_VERSION_HASHES PUBLIC_MODEL_V2_RIGHTS FOUR_L4_PROFILE_OFFLINE GLOBAL_SLOT_AND_NO_GEMMA_STACK QUOTA_8400_RESERVED SOURCE_PRIVACY_SCHEMA_PEER EXTERNAL_ONCE_BEFORE_PUSH NO_RECOVERY_OR_FALLBACK NATIVE_1050S_LIMIT CORE_ARTWORK_HISTORY_PRESERVED'.split())


def certificate_value(d):
    need(set(d)==set('status coordinator experiment_id observed dispatch source_id source_version checks'.split()))
    need(d['status']=='ROOT_AUTHORIZE_DISTINCT_OFFLINE_H0_CANARY' and d['coordinator']=='root')
    need(type(d['experiment_id']) is str and re.fullmatch('[0-9a-f]{32}',d['experiment_id']) is not None)
    need(type(d['checks']) is list and len(d['checks'])==len(CHECKS) and set(d['checks'])==CHECKS)
    now=time.time();observed=d['observed'];dispatch=d['dispatch']
    need(type(observed) in (int,float) and type(dispatch) in (int,float)
         and 0<=dispatch-observed<=300 and 0<=now-dispatch and 0<=now-observed<=4650)
    need(type(d['source_id']) is int and 0<d['source_id']<2**63
         and type(d['source_version']) is int and 0<d['source_version']<=1000000)
    return d


def fresh_compute_admission(c):
    # Expand fixed contract fields only AFTER every explicit new root check.
    # No clock is generated or old record re-dated; actual observation comes from c.
    return {'status':'ROOT_AUTHORIZED_ONE_H0_NATIVE_CANARY','coordinator':'root','source_sha256':CORE_SHA,
      'model_identity_mode':'CAPTURE_IMMUTABLE_PUBLIC_V2_BEFORE_CALLS','external_native_model_version_verified':2,
      'root_fresh_identity_status_capacity_quota_checks_required_at_dispatch':True,
      'model_reference':'google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2','physical_gpu_count':4,
      'gpu_type':'NVIDIA L4','native_wall_seconds':1050,'raw_gpu_seconds_budget':4200,
      'quota_unit':'conservative_reserved_gpu_seconds','conservative_reservation_multiplier':2,
      'provider_billing_factor_verified':False,'required_quota_seconds':8400,'available_quota_seconds':8400,
      'active_or_ambiguous_gemma_jobs':0,'global_gpu_commit_slot_admitted':True,
      'public_model_rights_and_rules_checked':True,'native_profile_available':True,
      'runtime_qualification_is_goal_not_prior_claim':True,'retry':False,'submit':False,
      'observed_unix_seconds':c['observed']}


def copy_core(root,manifest,work):
    core=work/'core';core.mkdir(mode=0o700,exist_ok=False)
    for name,expected in CORE_FILES.items():
        raw=(root/manifest['core'][name]['stored_name']).read_bytes()
        need(hashlib.sha256(raw).hexdigest()==expected)
        with(core/name).open('xb') as f:f.write(raw)
    need(set(p.name for p in core.iterdir())==set(CORE_FILES)
         and all(sha(core/n)==h for n,h in CORE_FILES.items()))
    return core


def stop_owned(tracked,psutil):
    for sig in (signal.SIGTERM,signal.SIGKILL):
        for pid,birth in list(tracked.items()):
            try:
                p=psutil.Process(pid)
                if p.create_time()==birth and p.status()!=psutil.STATUS_ZOMBIE:p.send_signal(sig)
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            alive=[]
            for pid,birth in tracked.items():
                try:
                    p=psutil.Process(pid)
                    if p.create_time()==birth and p.status()!=psutil.STATUS_ZOMBIE:alive.append(pid)
                except psutil.NoSuchProcess:pass
                except psutil.AccessDenied:return False
            if not alive:return True
            time.sleep(.1)
    return False


def execute(args):
    begin=time.monotonic()
    root,manifest=check_bundle(args.bundle_root,args.manifest_sha256)
    need(root.is_relative_to(Path('/kaggle/input').resolve()))
    need((args.root_certificate is None)!=(args.certificate_json is None))
    certificate_raw=(Path(args.root_certificate).read_text() if args.root_certificate is not None else args.certificate_json)
    c=certificate_value(json.loads(certificate_raw))
    serializer=load_source('approved_public_receipt_serializer',root/'public_receipt_serializer.py')
    # Fixed by experiment ID; rerunning the cell or changing a timestamp cannot reuse it.
    work=Path('/tmp')/('h0_private_'+c['experiment_id']);work.mkdir(mode=0o700,exist_ok=False)
    with(work/'ATTEMPT_CONSUMED.json').open('x') as f:
        json.dump({'status':'CONSUMED_BEFORE_MODEL_START','retry':False,
          'root_certificate_sha256':hashlib.sha256(certificate_raw.encode()).hexdigest(),
          'bundle_manifest_sha256':args.manifest_sha256},f)
    admission=work/'new_root_admission.json'
    with admission.open('x') as f:json.dump(fresh_compute_admission(c),f)
    core=copy_core(root,manifest,work)
    with(work/'private_copy_provenance.json').open('x') as f:
        json.dump({'bundle_manifest_sha256':args.manifest_sha256,'public_source_id':c['source_id'],
          'public_source_version':c['source_version'],'core_git_commit':CORE_COMMIT,'core_files':CORE_FILES},f)
    original=load_source('frozen_original_h0_core',core/'run_h0.py')
    original.admission(admission)  # exact source/4650/resource/rights predicate, unchanged
    output=work/'private_output'
    command=[sys.executable,'-S',str(core/'run_h0.py'),'--root-admission',str(admission),
      '--model-dir',args.model_dir,'--official-wheels',args.official_wheels,'--output',str(output)]
    import psutil
    tracked={};completed=False;clean=False;process=None
    try:
        with(work/'private_bootstrap_child.log').open('xb') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            tracked[process.pid]=psutil.Process(process.pid).create_time()
            # Core owns900s. Outer monitor reserves >=90s for cleanup and bounded export.
            deadline=min(begin+960,time.monotonic()+930)
            while process.poll() is None and time.monotonic()<deadline:
                try:
                    leader=psutil.Process(process.pid)
                    for p in [leader]+leader.children(recursive=True):tracked[p.pid]=p.create_time()
                except psutil.NoSuchProcess:pass
                time.sleep(.1)
            completed=process.poll()==0
    except BaseException:
        completed=False
    finally:
        clean=stop_owned(tracked,psutil)
        if process is not None:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:clean=False
    elapsed=time.monotonic()-begin
    if elapsed>1020:receipt=serializer.failure_receipt('HOLD_SCHEMA_REJECTED')
    elif not completed:receipt=serializer.failure_receipt('HOLD_H0_FAILED')
    else:receipt=serializer.reconstruct(output,clean,elapsed)
    if not clean:receipt=serializer.failure_receipt('HOLD_OUTER_CLEANUP_NOT_VERIFIED')
    # Source/schema policy was peer-reviewed BEFORE native admission. This is an
    # automatic data-schema review, not an independent exact-output review.
    serializer.export(receipt,'/kaggle/working',include_zip=False)
    print('H0_PUBLIC_BOUNDED_RECEIPT_WRITTEN')
    return 0 if receipt['status']=='PASS_H0_ONLY' else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--bundle-root')
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--root-certificate')
    parser.add_argument('--certificate-json')
    parser.add_argument('--model-dir',default='/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2')
    parser.add_argument('--official-wheels',default='/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'status':'HOLD_SOURCE_DELIVERY_CAPACITY_AND_RULES_NOT_ADMITTED',
          'network_fetch_implemented':False,'native_or_model_executed':False,
          'export_policy':'Source-reviewed bounded serializer; exact completed outputs need later independent review.'}))
        return 0
    try:
        need(args.bundle_root is not None and args.manifest_sha256 is not None)
        return execute(args)
    except BaseException:
        # Never print arbitrary provider/model/log/error/path strings to public logs.
        print('PRIVATE_H0_WORKFLOW_CLOSED_NO_RETRY')
        return 2


if __name__=='__main__':raise SystemExit(main())
