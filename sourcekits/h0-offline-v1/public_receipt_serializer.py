#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconstruct bounded benign H0 facts; never copy raw private files or errors."""
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

DRIVER_SHA='cd9154a22e6139289dabdada6610acb3f4f781f304e3d72351a85da00f8a9090'
ALIAS='gemma-4-31b-it-qat-w4a16-ct'
MAX_JSON_BYTES=1048576
MAX_PUBLIC_BYTES=16384
STATUSES={'PASS_H0_ONLY','HOLD_H0_FAILED','HOLD_SCHEMA_REJECTED','HOLD_OUTER_CLEANUP_NOT_VERIFIED'}


def need(ok):
    if not ok:raise ValueError('PRIVATE_INPUT_SCHEMA_REJECTED')


def keys(value,expected):
    need(type(value) is dict and set(value)==set(expected.split()))


def number(value,lo,hi,integer=False):
    need(type(value) in ((int,) if integer else (int,float)) and math.isfinite(value) and lo<=value<=hi)
    return value


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hexhash(value):
    need(type(value) is str and len(value)==64 and set(value)<=set('0123456789abcdef'))


def parse(raw):
    need(len(raw)<=MAX_JSON_BYTES)
    def pairs(items):
        out={}
        for k,v in items:
            need(k not in out);out[k]=v
        return out
    def constant(value):raise ValueError('NONFINITE_JSON_REJECTED')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def private_read(root,name):
    path=root/name
    need(path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_JSON_BYTES)
    with path.open('rb') as f:raw=f.read(MAX_JSON_BYTES+1)
    need(len(raw)<=MAX_JSON_BYTES)
    return raw


def private_manifest_checks(root):
    """Reject unknown provider/model fields; none of these strings are exported."""
    def relative_name(value):
        need(type(value) is str and re.fullmatch(r'[A-Za-z0-9_./-]{1,240}',value)
             and not value.startswith('/') and '..' not in Path(value).parts)
    def version(value):
        need(type(value) is str and re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,6}){1,3}(?:(?:a|b|rc|\.post|\.dev)[0-9]{1,6})?(?:\+[a-z0-9.]{1,40})?',value))
    model=parse(private_read(root,'ACTUAL_MODEL_MANIFEST.json'))
    keys(model,'model_reference files identity_scope')
    need(model['model_reference']=='google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2'
         and model['identity_scope']=='Exact mounted immutablepublicV2; upstream scored weight bytes not acquired')
    need(type(model['files']) is dict and 1<=len(model['files'])<=4096)
    need(any(n.endswith('.safetensors') for n in model['files']))
    for name,item in model['files'].items():
        relative_name(name);keys(item,'bytes sha256');number(item['bytes'],0,64*1024**3,True);hexhash(item['sha256'])
    runtime=parse(private_read(root,'ACTUAL_RUNTIME_MANIFEST.json'))
    keys(runtime,'packages driver_versions torch_cuda_version vllm_budget_processor_source_verified budget_processor_sources real_generation_budget_clipping_observed')
    need(runtime['vllm_budget_processor_source_verified'] is True and runtime['real_generation_budget_clipping_observed'] is False)
    keys(runtime['packages'],'google-adk google-genai litellm openai vllm transformers tokenizers torch psutil')
    for item in runtime['packages'].values():
        keys(item,'version critical_files metadata_sha256 record_sha256');version(item['version'])
        hexhash(item['metadata_sha256']);hexhash(item['record_sha256'])
        need(type(item['critical_files']) is dict and 1<=len(item['critical_files'])<=4096)
        for name,value in item['critical_files'].items():relative_name(name);hexhash(value)
    need(type(runtime['driver_versions']) is list and 1<=len(runtime['driver_versions'])<=4)
    for value in runtime['driver_versions']:version(value)
    version(runtime['torch_cuda_version'])
    need(type(runtime['budget_processor_sources']) is list and 1<=len(runtime['budget_processor_sources'])<=64)
    for value in runtime['budget_processor_sources']:
        keys(value,'module sha256');relative_name(value['module']);hexhash(value['sha256'])


def failure_receipt(status):
    need(status in STATUSES and status!='PASS_H0_ONLY')
    return {'schema':'gemma-h0-public-receipt/1','status':status,'source_sha256':DRIVER_SHA,
            'actual_success_verified':False,'actual_call_count_verified':False,
            'raw_logs_exported':False,'external_exact_output_review_completed':False,
            'automatic_schema_review_only':True,'official_score_claimed':False,
            'thinking_clipping_proved':False,'repair_or_speed_gain_proved':False,'retry':False,'submit':False}


def reconstruct(private_output,outer_cleanup_ok,whole_elapsed):
    """Only a fully matching successful triple becomes a positive public receipt."""
    if outer_cleanup_ok is not True:return failure_receipt('HOLD_OUTER_CLEANUP_NOT_VERIFIED')
    try:
        number(whole_elapsed,0,1050)
        root=Path(private_output).resolve(strict=True)
        need(root.is_relative_to(Path('/tmp').resolve()) and not root.is_relative_to(Path('/kaggle/working').resolve()))
        terminal=parse(private_read(root,'H0_TERMINAL_RECEIPT.json'))
        need(type(terminal) is dict and terminal.get('status') in ('PASS_H0_ONLY','HOLD_CLOSED_UNPROMOTABLE'))
        if terminal['status']!='PASS_H0_ONLY':return failure_receipt('HOLD_H0_FAILED')
        keys(terminal,'status reason returncode owned_descendants_alive peak_aggregate_host_rss_bytes elapsed_seconds native_wall_seconds_budget supervisor_runtime owned_wall_seconds_budget whole_provider_physical_gpu_count raw_gpu_seconds_budget conservative_reservation_multiplier provider_billing_factor_verified quota_seconds_budget no_benchmark_no_training_no_submission retry')
        need(terminal['reason'] is None and type(terminal['returncode']) is int and terminal['returncode']==0)
        need(terminal['owned_descendants_alive']==[] and type(terminal['owned_descendants_alive']) is list)
        number(terminal['peak_aggregate_host_rss_bytes'],0,64*1024**3,True)
        number(terminal['elapsed_seconds'],0,900)
        for name,value in {'native_wall_seconds_budget':1050,'owned_wall_seconds_budget':900,'whole_provider_physical_gpu_count':4,'raw_gpu_seconds_budget':4200,'conservative_reservation_multiplier':2,'quota_seconds_budget':8400}.items():
            need(type(terminal[name]) is int and terminal[name]==value)
        need(terminal['provider_billing_factor_verified'] is False and terminal['retry'] is False
             and terminal['no_benchmark_no_training_no_submission'] is True)
        supervisor=terminal['supervisor_runtime'];keys(supervisor,'python_version psutil_version psutil_python_module_sha256')
        # Versions remain private; reject free-form strings rather than forwarding them.
        need(all(type(supervisor[n]) is str and re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}(?:\.[0-9]{1,5})?',supervisor[n]) for n in ('python_version','psutil_version')))
        hexhash(supervisor['psutil_python_module_sha256'])
        child=parse(private_read(root,'H0_CHILD_PASS.json'))
        keys(child,'status arms actual_model_calls thinking_request_forwarding_verified thinking_token_enforcement_proved task_resolution_or_speed_gain_proved official_score_claimed next_gate')
        need(child['status']=='PASS_REAL_COMPILER_ENDPOINT_TOOL_ROUNDTRIP' and type(child['actual_model_calls']) is int and child['actual_model_calls']==4)
        need(child['thinking_request_forwarding_verified'] is True and child['thinking_token_enforcement_proved'] is False and child['task_resolution_or_speed_gain_proved'] is False and child['official_score_claimed'] is False)
        need(child['next_gate']=='Separate paired public-task canary under same exact model/harness hashes.')
        need(type(child['arms']) is list and len(child['arms'])==2)
        elapsed=[]
        for arm,budget in zip(child['arms'],(4096,1024)):
            keys(arm,'thinking_budget actual_model_calls tool_calls final_marker_observed elapsed_seconds')
            need(type(arm['thinking_budget']) is int and arm['thinking_budget']==budget and type(arm['actual_model_calls']) is int and arm['actual_model_calls']==2)
            need(arm['tool_calls']==[{'a':17,'b':25,'sum':42}] and arm['final_marker_observed'] is True)
            elapsed.append(number(arm['elapsed_seconds'],0,180))
        need(sum(elapsed)<=180 and terminal['elapsed_seconds']>=sum(elapsed)
             and whole_elapsed>=terminal['elapsed_seconds'])
        wire=parse(private_read(root,'ACTUAL_WIRE_OBSERVATIONS.json'))
        keys(wire,'requests errors raw_prompts_responses_and_auth_not_recorded')
        need(wire['errors']==[] and type(wire['errors']) is list and wire['raw_prompts_responses_and_auth_not_recorded'] is True)
        need(type(wire['requests']) is list and len(wire['requests'])==4)
        request_elapsed=[]
        for request,budget in zip(wire['requests'],(4096,4096,1024,1024)):
            keys(request,'model thinking_token_budget enable_thinking max_output_tokens tool_names message_count request_bytes_sha256 http_status response_bytes elapsed_seconds')
            need(request['model']==ALIAS and type(request['thinking_token_budget']) is int and request['thinking_token_budget']==budget and request['enable_thinking'] is True)
            need(type(request['max_output_tokens']) is int and request['max_output_tokens']==8192 and request['tool_names']==['h0_sum'])
            number(request['message_count'],1,64,True);hexhash(request['request_bytes_sha256'])
            need(type(request['http_status']) is int and request['http_status']==200)
            number(request['response_bytes'],1,2*1024**2,True)
            request_elapsed.append(number(request['elapsed_seconds'],0,180))
        need(sum(request_elapsed[:2])<=elapsed[0] and sum(request_elapsed[2:])<=elapsed[1])
        private_manifest_checks(root)
        # The frozen core validated these complete manifests before model calls.
        # Only their opaque hashes cross the export boundary, never paths/versions/text.
        hashes={key:hashlib.sha256(private_read(root,name)).hexdigest() for key,name in {
            'model_manifest':'ACTUAL_MODEL_MANIFEST.json','runtime_manifest':'ACTUAL_RUNTIME_MANIFEST.json',
            'terminal_receipt':'H0_TERMINAL_RECEIPT.json','child_receipt':'H0_CHILD_PASS.json',
            'wire_observations':'ACTUAL_WIRE_OBSERVATIONS.json'}.items()}
        return {'schema':'gemma-h0-public-receipt/1','status':'PASS_H0_ONLY','source_sha256':DRIVER_SHA,
          'actual_success_verified':True,'actual_call_count_verified':True,'actual_model_calls':4,
          'tool_calls':2,'thinking_budget_arms':[4096,1024],'arm_elapsed_seconds':elapsed,
          'owned_elapsed_seconds':terminal['elapsed_seconds'],'whole_elapsed_before_export_seconds':whole_elapsed,
          'peak_aggregate_host_rss_bytes':terminal['peak_aggregate_host_rss_bytes'],'owned_descendants_alive_count':0,
          'native_wall_seconds_budget':1050,'owned_wall_seconds_budget':900,'physical_gpu_count':4,
          'raw_gpu_seconds_budget':4200,'conservative_reserved_quota_seconds':8400,
          'provider_billing_factor_verified':False,'manifest_and_receipt_sha256':hashes,
          'raw_logs_exported':False,'external_exact_output_review_completed':False,
          'automatic_schema_review_only':True,'official_score_claimed':False,'thinking_clipping_proved':False,
          'repair_or_speed_gain_proved':False,'retry':False,'submit':False}
    except Exception:
        # Never propagate private exceptions, paths, provider errors or payload strings.
        return failure_receipt('HOLD_SCHEMA_REJECTED')


def public_bytes(receipt):
    """Validate the egress object too, so callers cannot append unreviewed text."""
    need(type(receipt) is dict and receipt.get('status') in STATUSES)
    if receipt['status']!='PASS_H0_ONLY':
        expected=failure_receipt(receipt['status'])
        need(receipt==expected and all(type(receipt[k]) is type(v) for k,v in expected.items()))
    else:
        keys(receipt,'schema status source_sha256 actual_success_verified actual_call_count_verified actual_model_calls tool_calls thinking_budget_arms arm_elapsed_seconds owned_elapsed_seconds whole_elapsed_before_export_seconds peak_aggregate_host_rss_bytes owned_descendants_alive_count native_wall_seconds_budget owned_wall_seconds_budget physical_gpu_count raw_gpu_seconds_budget conservative_reserved_quota_seconds provider_billing_factor_verified manifest_and_receipt_sha256 raw_logs_exported external_exact_output_review_completed automatic_schema_review_only official_score_claimed thinking_clipping_proved repair_or_speed_gain_proved retry submit')
        need(receipt['schema']=='gemma-h0-public-receipt/1' and receipt['source_sha256']==DRIVER_SHA)
        for name in ('actual_success_verified','actual_call_count_verified','automatic_schema_review_only'):
            need(receipt[name] is True)
        for name in ('provider_billing_factor_verified','raw_logs_exported','external_exact_output_review_completed','official_score_claimed','thinking_clipping_proved','repair_or_speed_gain_proved','retry','submit'):
            need(receipt[name] is False)
        for name,value in {'actual_model_calls':4,'tool_calls':2,'owned_descendants_alive_count':0,'native_wall_seconds_budget':1050,'owned_wall_seconds_budget':900,'physical_gpu_count':4,'raw_gpu_seconds_budget':4200,'conservative_reserved_quota_seconds':8400}.items():
            need(type(receipt[name]) is int and receipt[name]==value)
        need(receipt['thinking_budget_arms']==[4096,1024])
        need(type(receipt['arm_elapsed_seconds']) is list and len(receipt['arm_elapsed_seconds'])==2)
        for value in receipt['arm_elapsed_seconds']:number(value,0,180)
        number(receipt['owned_elapsed_seconds'],0,900)
        number(receipt['whole_elapsed_before_export_seconds'],0,1050)
        number(receipt['peak_aggregate_host_rss_bytes'],0,64*1024**3,True)
        keys(receipt['manifest_and_receipt_sha256'],'model_manifest runtime_manifest terminal_receipt child_receipt wire_observations')
        for value in receipt['manifest_and_receipt_sha256'].values():hexhash(value)
    raw=(json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(len(raw)<=MAX_PUBLIC_BYTES)
    return raw


def export(receipt,export_root,include_zip=False):
    """Exclusive fixed-name exports; no recursive copy, raw log or submitted ZIP."""
    raw=public_bytes(receipt)
    destination=Path(export_root)
    need(destination.is_dir() and not destination.is_symlink())
    with(destination/'h0_public_receipt.json').open('xb') as f:f.write(raw)
    if include_zip:
        with zipfile.ZipFile(destination/'h0_public_receipts.zip','x',compression=zipfile.ZIP_STORED) as z:
            info=zipfile.ZipInfo('h0_public_receipt.json',date_time=(1980,1,1,0,0,0))
            z.writestr(info,raw)
