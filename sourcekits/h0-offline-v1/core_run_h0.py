#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""H0 source: own a local official vLLM server and exercise the actual ADK compiler.

Not a competition submission, benchmark, model-quality test or launch dispatcher.
It never edits a notebook, installs packages, fetches weights or submits anything.
The coordinator must admit one fresh native canary on the verified public model version.
Only invented sum-tool inputs are sent to a new, loopback-only owned endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import sysconfig
import threading
import time
import urllib.request
import zipfile

# Native invocations use -S to avoid executing unrelated/broken global .pth hooks.
# Append base package locations explicitly, without site.addsitedir or hook execution.
for _path in dict.fromkeys(sysconfig.get_paths()[k] for k in ('purelib', 'platlib')):
    if _path not in sys.path:
        sys.path.append(_path)

ALIAS = 'gemma-4-31b-it-qat-w4a16-ct'
MODEL_REFERENCE = 'google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2'
NATIVE_SECONDS = 1050
OWNED_SECONDS = 900
STARTUP_SECONDS = 600
REQUEST_SECONDS = 45
PROBE_SECONDS = 180
CLEANUP_SECONDS = 60
GPU_COUNT = 4
RAW_GPU_SECONDS = NATIVE_SECONDS * GPU_COUNT
RSS_LIMIT = 64 * 1024**3
MAX_POSTS = 4
MAX_HTTP_BYTES = 2 * 1024**2
WHEELS = {
    'adk_submission-0.2.13-py3-none-any.whl':
        'f156f0bd84580ccb9334726d114d7a5481f16d3a6e2887cc4d276ced0ef8d99d',
    'swegemma-0.2.11-py3-none-any.whl':
        '9ad876581f3acde8ec3c369858f0834e2b9f41a3cffce3ca42f09cb090aea9d3',
    'adk_eval_core-0.1.0-py3-none-any.whl':
        'e614e1b2fe8d886a634871e4c57f9887e1cc66e8c27300f8503a43c6e3ca82f3',
}


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(b)
    return h.hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def admission(path):
    d = json.loads(Path(path).read_text())
    require(d['status'] == 'ROOT_AUTHORIZED_ONE_H0_NATIVE_CANARY', 'ROOT_ADMISSION')
    require(d['coordinator'] == 'root', 'SINGLE_COORDINATOR')
    require(d['source_sha256'] == sha_file(__file__), 'SOURCE_PIN')
    require(d['model_identity_mode'] == 'CAPTURE_IMMUTABLE_PUBLIC_V2_BEFORE_CALLS', 'MODEL_IDENTITY_MODE')
    require(d['external_native_model_version_verified'] == 2, 'EXTERNAL_MODEL_VERSION_BINDING')
    require(d['root_fresh_identity_status_capacity_quota_checks_required_at_dispatch'] is True,
            'EXTERNAL_FRESH_DISPATCH_GATE_REQUIRED')
    require(d['model_reference'] == MODEL_REFERENCE, 'MODEL_REFERENCE')
    require(d['physical_gpu_count'] == GPU_COUNT, 'WHOLE_PROVIDER_GPU_COUNT')
    require(d['gpu_type'] == 'NVIDIA L4', 'WHOLE_PROVIDER_GPU_TYPE')
    require(d['native_wall_seconds'] == NATIVE_SECONDS, 'NATIVE_BUDGET')
    require(d['raw_gpu_seconds_budget'] == RAW_GPU_SECONDS, 'WHOLE_ALLOCATION_BUDGET')
    require(d['quota_unit'] == 'conservative_reserved_gpu_seconds', 'RESERVATION_UNIT')
    rate = d['conservative_reservation_multiplier']
    require(rate == 2, 'RESERVE_TWO_TIMES_WHOLE_ALLOCATION')
    require(d['required_quota_seconds'] == RAW_GPU_SECONDS * rate, 'QUOTA_ARITHMETIC')
    require(d['available_quota_seconds'] >= d['required_quota_seconds'], 'QUOTA_AVAILABLE')
    require(d['active_or_ambiguous_gemma_jobs'] == 0, 'NO_STACKED_GEMMA_JOB')
    require(d['global_gpu_commit_slot_admitted'] is True, 'GLOBAL_CAPACITY')
    require(d['public_model_rights_and_rules_checked'] is True, 'RIGHTS_AND_RULES')
    require(d['native_profile_available'] is True, 'PROFILE_AVAILABILITY')
    require(d['runtime_qualification_is_goal_not_prior_claim'] is True, 'H0_SCOPE')
    require(d['retry'] is False and d['submit'] is False, 'NO_RETRY_OR_SUBMIT')
    age = time.time() - d['observed_unix_seconds']
    # This is one-run authorization carried through the native queue, not a claim
    # that an old dataset file proves live capacity. Root's launcher must independently
    # refresh all required dispatch evidence within300s before its single safe_push.
    require(0 <= age <= 4650, 'ROOT_AUTHORIZATION_QUEUE_EXPIRY')
    return d


def bootstrap_offline_overlay(wheelhouse, output, overlay_path=None):
    """Use original mounted public wheels in a new overlay, never alter host files."""
    # Keep runtime dependencies out of public notebook outputs. Original mounted
    # wheels are not redistributed and this temporary directory is never removed.
    overlay = Path(overlay_path) if overlay_path is not None else Path('/tmp/gemma_h0_site_20261019')
    overlay.mkdir()
    wheels = sorted(Path(wheelhouse).glob('*.whl'))
    require(wheels, 'OFFICIAL_PUBLIC_WHEELHOUSE_EMPTY')
    inventory = []
    for wheel in wheels:
        if 'cutlass' in wheel.name.lower():
            inventory.append({'name': wheel.name, 'skipped': 'same wheel exclusion as official starter; no files deleted'})
            continue
        inventory.append({'name': wheel.name, 'sha256': sha_file(wheel), 'bytes': wheel.stat().st_size})
        with zipfile.ZipFile(wheel) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                if info.filename.endswith('.ipynb'):
                    continue  # Documentation notebooks are not needed or created in the overlay.
                parts = Path(info.filename).parts
                require(parts and not Path(info.filename).is_absolute() and '..' not in parts,
                        'WHEEL_PATH_ESCAPE')
                if parts[0].endswith('.data'):
                    if len(parts) < 3 or parts[1] not in ('purelib', 'platlib'):
                        continue
                    parts = parts[2:]
                target = overlay.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    require(hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(z.read(info)).digest(),
                            'OVERLAY_COLLISION:' + info.filename)
                    continue
                with z.open(info) as source, target.open('xb') as dest:
                    for chunk in iter(lambda: source.read(8 * 1024**2), b''):
                        dest.write(chunk)
    sys.path.insert(0, str(overlay))
    os.environ['PYTHONPATH'] = os.pathsep.join(dict.fromkeys([str(overlay)] + sys.path))
    import importlib
    importlib.invalidate_caches()
    write_new(output / 'MOUNTED_PUBLIC_WHEEL_INVENTORY.json', inventory)
    return overlay


def capture_identities(model_dir, output):
    """H0 binds actual immutable mounted files; it does not invent prior weight hashes."""
    root = Path(model_dir).resolve(strict=True)
    files = {p.relative_to(root).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha_file(p)}
             for p in sorted(root.rglob('*')) if p.is_file()}
    require(any(n.endswith('.safetensors') for n in files), 'MOUNTED_WEIGHTS_REQUIRED')
    write_new(output / 'ACTUAL_MODEL_MANIFEST.json', {'model_reference': MODEL_REFERENCE,
              'files': files, 'identity_scope': 'Exact mounted immutablepublicV2; upstream scored weight bytes not acquired'})
    wanted = {
      'google-adk': ('lite_llm.py', 'run_config.py', 'base_llm_flow.py', 'runners.py'),
      'google-genai': ('types.py',), 'litellm': ('main.py',), 'openai': ('_base_client.py',),
      'vllm': ('api_server.py',), 'transformers': ('modeling_gemma4.py',),
      'tokenizers': ('__init__.py',), 'torch': ('version.py',), 'psutil': ('__init__.py',)}
    packages = {}
    processor = []
    for name, suffixes in wanted.items():
        d = importlib.metadata.distribution(name)
        critical = {}
        for item in d.files or []:
            n = str(item)
            if n.endswith(suffixes):
                critical[n] = sha_file(d.locate_file(item))
            if name == 'vllm' and n.endswith('.py') and any(x in n for x in ('reason', 'think', 'logits')):
                raw = Path(d.locate_file(item)).read_bytes()
                if b'class ThinkingTokenBudgetLogitsProcessor' in raw:
                    critical[n] = hashlib.sha256(raw).hexdigest()
                    processor.append({'module': n, 'sha256': critical[n]})
        require(critical, 'ACTUAL_RUNTIME_CRITICAL_SOURCES:' + name)
        info = {'version': d.version, 'critical_files': critical}
        for leaf in ('METADATA', 'RECORD'):
            paths = [x for x in d.files or [] if str(x).endswith('.dist-info/' + leaf)]
            require(len(paths) == 1, 'ACTUAL_RUNTIME_DIST_INFO:' + name)
            info[leaf.lower() + '_sha256'] = sha_file(d.locate_file(paths[0]))
        packages[name] = info
    require(processor, 'ACTUAL_VLLM_BUDGET_PROCESSOR_SOURCE_REQUIRED')
    r = subprocess.run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                       capture_output=True, text=True, check=True, timeout=10)
    import torch
    write_new(output / 'ACTUAL_RUNTIME_MANIFEST.json', {'packages': packages,
      'driver_versions': sorted(set(r.stdout.split())), 'torch_cuda_version': torch.version.cuda,
      'vllm_budget_processor_source_verified': True, 'budget_processor_sources': processor,
      'real_generation_budget_clipping_observed': False})
    return output / 'ACTUAL_MODEL_MANIFEST.json', output / 'ACTUAL_RUNTIME_MANIFEST.json'


def installed_official_sources(wheels_dir):
    """Require exact original official modules, rather than a patched local copy."""
    import importlib.util
    summary = {}
    for name, digest in WHEELS.items():
        p = Path(wheels_dir) / name
        require(sha_file(p) == digest, 'OFFICIAL_WHEEL_PIN:' + name)
        package = name.split('-')[0]
        spec = importlib.util.find_spec(package)
        require(spec is not None and spec.origin is not None, 'MISSING_PACKAGE:' + package)
        root = Path(spec.origin).parent
        count = 0
        with zipfile.ZipFile(p) as z:
            for member in z.namelist():
                if member.startswith(package + '/') and member.endswith('.py'):
                    target = root / member[len(package) + 1:]
                    require(target.read_bytes() == z.read(member), 'INSTALLED_SOURCE_DRIFT:' + member)
                    count += 1
        summary[name] = {'sha256': digest, 'verified_python_modules': count}
    return summary


def verify_model(model_dir, manifest_path):
    """Recheck the just-captured immutable mounted identity before the model starts."""
    root = Path(model_dir).resolve(strict=True)
    m = json.loads(Path(manifest_path).read_text())
    require(m['model_reference'] == MODEL_REFERENCE, 'MODEL_MANIFEST_REFERENCE')
    expected = m['files']
    actual = {p.relative_to(root).as_posix(): p for p in root.rglob('*') if p.is_file()}
    require(set(actual) == set(expected), 'COMPLETE_MODEL_FILE_SET')
    require(any(n.endswith('.safetensors') for n in actual), 'WEIGHTS_REQUIRED')
    require('config.json' in actual, 'MODEL_CONFIG_REQUIRED')
    for name, p in actual.items():
        require(root in p.resolve().parents, 'MODEL_FILE_ESCAPES_MOUNT')
        require(p.stat().st_size == expected[name]['bytes'], 'MODEL_FILE_SIZE:' + name)
        require(sha_file(p) == expected[name]['sha256'], 'MODEL_FILE_HASH:' + name)
    return {'manifest_sha256': sha_file(manifest_path), 'files': len(actual),
            'bytes': sum(p.stat().st_size for p in actual.values())}


def verify_runtime(path):
    """Bind actual serving dependencies; the three official wheels are insufficient."""
    m = json.loads(Path(path).read_text())
    packages = m['packages']
    require(set(packages) == {'google-adk', 'google-genai', 'litellm', 'openai',
                             'vllm', 'transformers', 'tokenizers', 'torch', 'psutil'},
            'COMPLETE_SERVING_RUNTIME_PACKAGE_SET')
    for name, expected in packages.items():
        dist = importlib.metadata.distribution(name)
        require(dist.version == expected['version'], 'RUNTIME_VERSION:' + name)
        for leaf in ('METADATA', 'RECORD'):
            candidates = [p for p in (dist.files or []) if str(p).endswith('.dist-info/' + leaf)]
            require(len(candidates) == 1, 'RUNTIME_DIST_INFO:' + name + ':' + leaf)
            require(sha_file(dist.locate_file(candidates[0])) == expected[leaf.lower() + '_sha256'],
                    'RUNTIME_DIST_INFO_PIN:' + name + ':' + leaf)
        require(expected['critical_files'], 'RUNTIME_CRITICAL_SOURCE_PINS:' + name)
        for relative, digest in expected['critical_files'].items():
            require(relative in {str(p) for p in dist.files or []}, 'RUNTIME_FILE_NOT_IN_DISTRIBUTION')
            require(sha_file(dist.locate_file(relative)) == digest, 'RUNTIME_SOURCE_PIN:' + relative)
    require(m['vllm_budget_processor_source_verified'] is True, 'BUDGET_PROCESSOR_SOURCE_PREREQUISITE')
    # CUDA/driver values are observations, separately bound by the root manifest.
    result = subprocess.run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                            capture_output=True, text=True, check=True, timeout=10)
    require(sorted(set(result.stdout.split())) == m['driver_versions'], 'DRIVER_PIN')
    import torch
    require(torch.version.cuda == m['torch_cuda_version'], 'CUDA_RUNTIME_PIN')
    return {'runtime_manifest_sha256': sha_file(path), 'packages': packages,
            'driver_versions': m['driver_versions'], 'torch_cuda_version': torch.version.cuda}


def gpu_inventory():
    r = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total',
                        '--format=csv,noheader,nounits'], capture_output=True,
                       text=True, check=True, timeout=10)
    rows = [x.strip().split(',') for x in r.stdout.splitlines() if x.strip()]
    require(len(rows) == GPU_COUNT, 'EXACT_FOUR_GPU_ALLOCATION_REQUIRED')
    require(all('L4' in x[0] and 22000 <= int(x[1]) <= 25000 for x in rows), 'L4_TOPOLOGY')
    return [{'name': x[0].strip(), 'memory_mib': int(x[1])} for x in rows]


def unused_loopback_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def owned_listener_ready(process, port):
    """Do not attach to a pre-existing or competing service on a raced port."""
    import psutil
    leader = psutil.Process(process.pid)
    owned = {leader.pid} | {p.pid for p in leader.children(recursive=True)}
    listeners = [c for c in psutil.net_connections(kind='inet')
                 if c.status == psutil.CONN_LISTEN and c.laddr.port == port]
    require(all(c.pid in owned and c.laddr.ip == '127.0.0.1' for c in listeners),
            'SERVER_LISTENER_NOT_OWNED')
    return bool(listeners)


def forwarded_facts(body, expected_budget):
    """LiteLLM merges extra_body into actual OpenAI wire JSON at the top level."""
    require(isinstance(body, dict), 'HTTP_JSON_OBJECT')
    require(body.get('model') == ALIAS, 'ACTUAL_WIRE_MODEL')
    require(body.get('stream', False) is False, 'H0_REQUIRES_NONSTREAM_REQUEST')
    require(body.get('thinking_token_budget') == expected_budget, 'ACTUAL_WIRE_THINKING_BUDGET')
    require(body.get('chat_template_kwargs', {}).get('enable_thinking') is True,
            'ACTUAL_WIRE_ENABLE_THINKING')
    require(body.get('max_tokens', body.get('max_completion_tokens')) == 8192,
            'ACTUAL_WIRE_OUTPUT_CAP')
    tools = body.get('tools', [])
    require([x.get('function', {}).get('name') for x in tools] == ['h0_sum'], 'ACTUAL_TOOL_SCHEMA')
    return {'model': ALIAS, 'thinking_token_budget': expected_budget,
            'enable_thinking': True, 'max_output_tokens': 8192,
            'tool_names': ['h0_sum'], 'message_count': len(body.get('messages', [])),
            'request_bytes_sha256': hashlib.sha256(json.dumps(body, sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()}


class WireProxy:
    """One owned loopback proxy. It forwards unchanged bytes and records no secrets."""
    def __init__(self, upstream_port):
        self.upstream_port = upstream_port
        self.records = []
        self.expected_budget = None
        self.errors = []
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                conn = None
                try:
                    require(self.path == '/v1/chat/completions', 'ONLY_CHAT_ENDPOINT')
                    require(self.headers.get('Authorization', 'Bearer EMPTY') == 'Bearer EMPTY',
                            'NO_REAL_CREDENTIALS_ALLOWED')
                    length = int(self.headers.get('Content-Length', '0'))
                    require(0 < length <= MAX_HTTP_BYTES, 'REQUEST_BYTE_LIMIT')
                    payload = self.rfile.read(length)
                    with owner.lock:
                        require(not owner.errors, 'CLOSED_AFTER_ANY_PROXY_FAILURE')
                        facts = forwarded_facts(json.loads(payload), owner.expected_budget)
                        require(len(owner.records) < MAX_POSTS, 'MAX_FOUR_ACTUAL_MODEL_CALLS')
                        owner.records.append(facts)
                    conn = http.client.HTTPConnection('127.0.0.1', owner.upstream_port,
                                                       timeout=REQUEST_SECONDS)
                    begin = time.monotonic()
                    conn.request('POST', self.path, body=payload,
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer EMPTY'})
                    response = conn.getresponse()
                    data = response.read(MAX_HTTP_BYTES + 1)
                    require(len(data) <= MAX_HTTP_BYTES, 'RESPONSE_BYTE_LIMIT')
                    require(response.status == 200, 'REAL_ENDPOINT_HTTP_STATUS:' + str(response.status))
                    require('application/json' in response.getheader('Content-Type', ''),
                            'H0_REQUIRES_NONSTREAM_JSON_RESPONSE')
                    facts['http_status'] = response.status
                    facts['response_bytes'] = len(data)
                    facts['elapsed_seconds'] = time.monotonic() - begin
                    # H0 explicitly disables streaming. Unexpected SSE is refused,
                    # rather than being converted into a successful compatibility result.
                    self.send_response(response.status)
                    self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as exc:
                    with owner.lock:
                        owner.errors.append(type(exc).__name__ + ':' + str(exc))
                    self.send_error(502, 'H0_FORWARDING_FAILED')
                finally:
                    if conn is not None:
                        conn.close()

        # Sequential H0 requests: no request can be in flight when the next is admitted.
        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def base_url(self):
        return 'http://127.0.0.1:' + str(self.server.server_port) + '/v1'


async def actual_compiler_probe(proxy, output):
    from adk_submission.compiler import compile_submission
    from adk_submission.registry import ModelRegistry
    from adk_submission.resolvers.generation import install_litellm_reasoning_patch
    from swegemma.config import build_submission_limits
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.genai import types
    import litellm

    litellm.telemetry = False
    litellm.suppress_debug_info = True
    litellm.drop_params = True
    litellm.num_retries = 0
    require(install_litellm_reasoning_patch() is True, 'OFFICIAL_REASONING_PATCH_REQUIRED')
    results = []
    for budget in (4096, 1024):
        calls = []

        def h0_sum(a: int, b: int) -> dict:
            """Return the sum of two integers for an invented compatibility fixture."""
            require(type(a) is int and type(b) is int and (a, b) == (17, 25), 'FIXTURE_TOOL_ARGUMENTS')
            calls.append({'a': a, 'b': b, 'sum': a + b})
            require(len(calls) == 1, 'EXACTLY_ONE_FIXTURE_TOOL_CALL')
            return {'sum': a + b}

        directory = output / ('fixture_' + str(budget))
        directory.mkdir()
        configuration = ('name: h0_agent\nmodel: ' + ALIAS + '\ninstruction: >-\n'
                         '  This is an invented tool-compatibility check. You must call h0_sum\n'
                         '  once with a=17 and b=25. After the tool returns, output H0_42 and stop.\n'
                         'tools:\n  - h0_sum\ngenerate_content_config:\n'
                         '  temperature: 0.2\n  top_p: 0.95\n  max_output_tokens: 8192\n'
                         '  thinking_config:\n    thinking_budget: ' + str(budget) + '\n'
                         '    include_thoughts: true\n')
        # This is an H0-only agent.yaml, not a notebook, competition identity or submitted package.
        with (directory / 'agent.yaml').open('x') as f:
            f.write(configuration)
        registry = ModelRegistry()
        registry.register(ALIAS, LiteLlm(model='openai/' + ALIAS, api_base=proxy.base_url,
                          api_key='EMPTY', num_retries=0, timeout=REQUEST_SECONDS))
        limits, constraints = build_submission_limits()
        agent = compile_submission(directory, {'h0_sum': h0_sum}, registry,
                                   limits=limits, generation_constraints=constraints)
        sessions = InMemorySessionService()
        sid = 'h0_' + str(budget)
        await sessions.create_session(app_name='h0_compat', user_id='invented_user', session_id=sid)
        runner = Runner(agent=agent, app_name='h0_compat', session_service=sessions)
        with proxy.lock:
            proxy.expected_budget = budget
        before = len(proxy.records)
        final = []
        begin = time.monotonic()
        async for event in runner.run_async(user_id='invented_user', session_id=sid,
                       new_message=types.Content(role='user', parts=[types.Part(text='Run the fixture now.')]),
                       run_config=RunConfig(max_llm_calls=2, streaming_mode=StreamingMode.NONE)):
            if event.is_final_response() and event.content:
                final.extend(p.text for p in event.content.parts if p.text and not p.thought)
        require(calls == [{'a': 17, 'b': 25, 'sum': 42}], 'REAL_TOOL_EXECUTION_REQUIRED')
        require('H0_42' in '\n'.join(final), 'FINAL_REAL_MODEL_MARKER_REQUIRED')
        require(len(proxy.records) - before == 2, 'EXACT_TWO_REAL_REQUESTS_PER_ARM')
        require(not proxy.errors, 'PROXY_ERROR')
        results.append({'thinking_budget': budget, 'actual_model_calls': 2,
                        'tool_calls': calls, 'final_marker_observed': True,
                        'elapsed_seconds': time.monotonic() - begin})
    return results


def child(args):
    output = Path(args.output)
    bootstrap_offline_overlay(args.official_wheels, output)
    args.model_manifest, args.runtime_manifest = capture_identities(args.model_dir, output)
    pins = installed_official_sources(args.official_wheels)
    runtime = verify_runtime(args.runtime_manifest)
    model = verify_model(args.model_dir, args.model_manifest)
    gpu = gpu_inventory()
    from adk_submission.server import VllmConfig, VllmServer
    port = unused_loopback_port()
    cfg = VllmConfig(model=str(Path(args.model_dir).resolve()), port=port, host='127.0.0.1',
              tool_call_parser='gemma4', reasoning_parser='gemma4',
              reasoning_config={'reasoning_start_str': '<|channel>', 'reasoning_end_str': '<channel|>'},
              default_chat_template_kwargs={'enable_thinking': True},
              tensor_parallel_size=GPU_COUNT, max_model_len=32768,
              gpu_memory_utilization=.90, enable_auto_tool_choice=True,
              scheduler_reserve_full_isl=False, enable_lora=False,
              startup_timeout=STARTUP_SECONDS, extra_args=['--served-model-name', ALIAS])
    server = VllmServer(cfg)
    command = server.build_cmd()
    command.insert(1, '-S')  # Skip global .pth hooks; preserve all original host files.
    require('--tensor-parallel-size' in command and command[command.index('--tensor-parallel-size') + 1] == '4',
            'ACTUAL_SERVER_TP4')
    require('--reasoning-config' in command, 'ACTUAL_SERVER_REASONING_CONFIG')
    write_new(output / 'SERVER_CONFIGURATION.json', {
              'server_flags': {'tensor_parallel_size': 4, 'host': '127.0.0.1',
                   'tool_call_parser': 'gemma4', 'reasoning_parser': 'gemma4',
                   'reasoning_config': cfg.reasoning_config, 'max_model_len': 32768,
                   'gpu_memory_utilization': .9, 'enable_lora': False,
                   'served_model_name': ALIAS, 'python_no_site_hooks': True},
              'gpu_inventory': gpu,
              'official_source_pins': pins, 'model_identity': model, 'runtime_identity': runtime,
              'scorer_equivalence_claimed': False, 'swegemma_task_benchmark_run': False})
    with (output / 'private_server.log').open('xb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   env=server.build_env())
        try:
            end = time.monotonic() + STARTUP_SECONDS
            while True:
                require(process.poll() is None, 'SERVER_EARLY_EXIT')
                require(time.monotonic() < end, 'SERVER_STARTUP_TIMEOUT')
                if not owned_listener_ready(process, port):
                    time.sleep(.5)
                    continue
                try:
                    with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/health', timeout=2) as r:
                        if r.status == 200:
                            break
                except OSError:
                    pass
                time.sleep(.5)
            with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/v1/models', timeout=5) as r:
                models = json.loads(r.read(MAX_HTTP_BYTES))
            require([x['id'] for x in models['data']] == [ALIAS], 'REAL_SERVED_ALIAS')
            with WireProxy(port) as proxy:
                try:
                    results = asyncio.run(asyncio.wait_for(actual_compiler_probe(proxy, output), PROBE_SECONDS))
                finally:
                    write_new(output / 'ACTUAL_WIRE_OBSERVATIONS.json',
                              {'requests': proxy.records, 'errors': proxy.errors,
                               'raw_prompts_responses_and_auth_not_recorded': True})
            write_new(output / 'H0_CHILD_PASS.json', {'status': 'PASS_REAL_COMPILER_ENDPOINT_TOOL_ROUNDTRIP',
                      'arms': results, 'actual_model_calls': len(proxy.records),
                      'thinking_request_forwarding_verified': True,
                      'thinking_token_enforcement_proved': False,
                      'task_resolution_or_speed_gain_proved': False,
                      'official_score_claimed': False,
                      'next_gate': 'Separate paired public-task canary under same exact model/harness hashes.'})
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def supervise(args):
    begin = time.monotonic()
    import psutil
    supervisor_runtime = {'python_version': sys.version.split()[0],
                          'psutil_version': psutil.__version__,
                          'psutil_python_module_sha256': sha_file(psutil.__file__)}
    decision = admission(args.root_admission)
    output = Path(args.output)
    output.mkdir(exist_ok=False)
    write_new(output / 'H0_ATTEMPT_CONSUMED.json', {'status': 'CONSUMED_BEFORE_CHILD_START',
              'retry': False, 'root_admission_sha256': sha_file(args.root_admission),
              'source_sha256': sha_file(__file__), 'raw_gpu_seconds_budget': RAW_GPU_SECONDS,
              'required_quota_seconds': decision['required_quota_seconds']})
    argv = [sys.executable, '-S', str(Path(__file__).resolve()), '--child', '--model-dir', args.model_dir,
            '--official-wheels', args.official_wheels,
            '--output', str(output)]
    env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               HF_HUB_DISABLE_TELEMETRY='1', LITELLM_TELEMETRY='False', DO_NOT_TRACK='1',
               LITELLM_LOCAL_MODEL_COST_MAP='True', LITELLM_LOG='ERROR',
               VLLM_NO_USAGE_STATS='1', VLLM_WORKER_MULTIPROC_METHOD='spawn',
               TRANSFORMERS_NO_TF='1', TRANSFORMERS_NO_FLAX='1',
               PYTHONPATH=os.pathsep.join(sys.path))
    tracked = {}
    peak = 0
    reason = None
    with (output / 'private_child.log').open('xb') as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, env=env)
        try:
            while process.poll() is None:
                try:
                    leader = psutil.Process(process.pid)
                    owned = [leader] + leader.children(recursive=True)
                except psutil.NoSuchProcess:
                    process.wait(timeout=2)
                    break
                rss = 0
                for p in owned:
                    try:
                        tracked[p.pid] = p.create_time()
                        rss += p.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                peak = max(peak, rss)
                if rss > RSS_LIMIT:
                    reason = 'AGGREGATE_HOST_RSS_LIMIT'
                    break
                if time.monotonic() - begin > OWNED_SECONDS - CLEANUP_SECONDS:
                    reason = 'OWNED_DEADLINE_WITH_CLEANUP_RESERVE'
                    break
                time.sleep(.1)
        except BaseException as exc:
            reason = 'SUPERVISOR_EXCEPTION:' + type(exc).__name__
        finally:
            # Only this new process group and recorded descendants with the same birth time.
            # No unrelated agent/server/job is touched. Nothing on disk is deleted.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    pass
                for pid, birth in list(tracked.items()):
                    try:
                        p = psutil.Process(pid)
                        if p.create_time() == birth and p.status() != psutil.STATUS_ZOMBIE:
                            p.send_signal(sig)
                    except psutil.NoSuchProcess:
                        pass
                try:
                    process.wait(timeout=15 if sig == signal.SIGTERM else 10)
                except subprocess.TimeoutExpired:
                    pass
            survivors = []
            for pid, birth in tracked.items():
                try:
                    p = psutil.Process(pid)
                    if p.create_time() == birth and p.status() != psutil.STATUS_ZOMBIE:
                        survivors.append(pid)
                except psutil.NoSuchProcess:
                    pass
            ok = (reason is None and process.returncode == 0 and not survivors
                  and (output / 'H0_CHILD_PASS.json').is_file())
            write_new(output / 'H0_TERMINAL_RECEIPT.json', {
                'status': 'PASS_H0_ONLY' if ok else 'HOLD_CLOSED_UNPROMOTABLE',
                'reason': reason, 'returncode': process.returncode,
                'owned_descendants_alive': survivors, 'peak_aggregate_host_rss_bytes': peak,
                'elapsed_seconds': time.monotonic() - begin,
                'native_wall_seconds_budget': NATIVE_SECONDS,
                'supervisor_runtime': supervisor_runtime,
                'owned_wall_seconds_budget': OWNED_SECONDS,
                'whole_provider_physical_gpu_count': GPU_COUNT,
                'raw_gpu_seconds_budget': RAW_GPU_SECONDS,
                'conservative_reservation_multiplier': decision['conservative_reservation_multiplier'],
                'provider_billing_factor_verified': decision.get('provider_billing_factor_verified', False),
                'quota_seconds_budget': decision['required_quota_seconds'],
                'no_benchmark_no_training_no_submission': True, 'retry': False})
            require(ok, 'H0_CLOSED_UNPROMOTABLE')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--model-dir', default='/kaggle/input/models/google/gemma-4/other/' + ALIAS + '/2')
    p.add_argument('--model-manifest')
    p.add_argument('--runtime-manifest')
    p.add_argument('--official-wheels', default='/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
    p.add_argument('--output', required=True)
    p.add_argument('--root-admission')
    return p


if __name__ == '__main__':
    arguments = parser().parse_args()
    if arguments.child:
        child(arguments)
    else:
        require(arguments.root_admission is not None, 'ROOT_ADMISSION_REQUIRED')
        supervise(arguments)
