#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-only deliverable. A future admitted run calls the original V1 helper once.

This observer never changes an H0 result. It prints one fixed enum, not private
file contents. The original helper owns all model work, limits and cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

INPUT_ROOT = Path('/kaggle/input')
TMP_ROOT = Path('/tmp')
MANIFEST_SHA = '086c33d929204d42616e1589b74d1ad83fe21985546ab6f5f3ffa52f98329325'
PINS = {
    'BUNDLE_MANIFEST.json': MANIFEST_SHA,
    'private_h0_flat_bootstrap.py': '49dea7e5d52f5c43e55083c4829f02bad4d76782be29ee75f6219d253c4fd79a',
    'core_run_h0.py': 'cd9154a22e6139289dabdada6610acb3f4f781f304e3d72351a85da00f8a9090',
    'public_receipt_serializer.py': '45f3418bf33901fdb12545be0672ff739f66e5c315bd9cda3eb71b88c0ae1abf',
}
# Original private_output filenames, in their original creation order.
MILESTONES = (
    ('H0_ATTEMPT_CONSUMED.json', 4096, dict, 'CORE_ATTEMPT_FILE_PRESENT'),
    ('MOUNTED_PUBLIC_WHEEL_INVENTORY.json', 131072, list, 'WHEEL_INVENTORY_PRESENT'),
    ('ACTUAL_MODEL_MANIFEST.json', 524288, dict, 'MODEL_MANIFEST_PRESENT'),
    ('ACTUAL_RUNTIME_MANIFEST.json', 262144, dict, 'RUNTIME_MANIFEST_PRESENT'),
    ('SERVER_CONFIGURATION.json', 524288, dict, 'SERVER_CONFIG_PRESENT'),
    ('ACTUAL_WIRE_OBSERVATIONS.json', 32768, dict, 'WIRE_OBSERVATIONS_PRESENT'),
    ('H0_CHILD_PASS.json', 32768, dict, 'CHILD_PASS_FILE_PRESENT'),
)
ENUMS = {'NO_CORE_ATTEMPT_FILE', 'OBSERVER_REJECTED'} | {x[3] for x in MILESTONES}
MAX_TOTAL_BYTES = 1048576
OBSERVER_SECONDS = 1.0
PREFIX = 'H0_DIAGNOSTIC_STAGE='


def need(ok):
    if not ok:
        raise ValueError()


def directory_at(parent_fd, name, private=False):
    need(name == Path(name).name and name not in ('', '.', '..'))
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        s = os.fstat(fd)
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid())
        if private:
            need(stat.S_IMODE(s.st_mode) == 0o700)
        return fd
    except BaseException:
        os.close(fd)
        raise


def regular_at(parent_fd, name, cap, deadline, private=True):
    need(name == Path(name).name and time.monotonic() <= deadline)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= cap)
        if private:
            need(before.st_uid == os.geteuid() and before.st_nlink == 1)
        raw = bytearray()
        while len(raw) < before.st_size:
            need(time.monotonic() <= deadline)
            block = os.read(fd, min(65536, before.st_size - len(raw)))
            if not block:
                break
            raw.extend(block)
        after = os.fstat(fd)
        need(len(raw) == before.st_size and time.monotonic() <= deadline
             and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
        return bytes(raw)
    finally:
        os.close(fd)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result


def reject_constant(_):
    raise ValueError()


def parsed_json(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def experiment_id(raw):
    need(type(raw) is str and len(raw.encode()) <= 16384)
    c = parsed_json(raw.encode())
    need(type(c) is dict and c.get('status') == 'ROOT_AUTHORIZE_DISTINCT_OFFLINE_H0_CANARY'
         and c.get('coordinator') == 'root' and c.get('source_id') == 12718547
         and c.get('source_version') == 1)
    value = c.get('experiment_id')
    need(type(value) is str and re.fullmatch('[0-9a-f]{32}', value) is not None)
    return value  # Original helper still validates the complete certificate/time/all11 checks.


class QuietParser(argparse.ArgumentParser):
    def error(self, _):
        raise ValueError()


def validated_request(argv):
    need(len(argv) <= 20 and all(type(x) is str and len(x.encode()) <= 16384 for x in argv))
    p = QuietParser(add_help=False, allow_abbrev=False)
    p.add_argument('--execute', action='store_true')
    for name in ('bundle-root', 'manifest-sha256', 'certificate-json'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--model-dir')
    p.add_argument('--official-wheels')
    args = p.parse_args(argv)
    need(args.execute and args.manifest_sha256 == MANIFEST_SHA)
    eid = experiment_id(args.certificate_json)
    root = Path(args.bundle_root).resolve(strict=True)
    need(root.is_relative_to(INPUT_ROOT.resolve(strict=True)))
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        deadline = time.monotonic() + OBSERVER_SECONDS
        for name, expected in PINS.items():
            need(hashlib.sha256(regular_at(fd, name, 65536, deadline, private=False)).hexdigest() == expected)
    finally:
        os.close(fd)
    return root, eid


def observe_stage(eid):
    need(type(eid) is str and re.fullmatch('[0-9a-f]{32}', eid) is not None)
    fds = []
    try:
        base = os.open(TMP_ROOT.resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(base)
        try:
            work = directory_at(base, 'h0_private_' + eid, private=True)
            fds.append(work)
            output = directory_at(work, 'private_output')
            fds.append(output)
        except FileNotFoundError:
            return 'NO_CORE_ATTEMPT_FILE'
        deadline = time.monotonic() + OBSERVER_SECONDS
        stage, missing, total = 'NO_CORE_ATTEMPT_FILE', False, 0
        for name, cap, shape, token in MILESTONES:
            try:
                raw = regular_at(output, name, min(cap, MAX_TOTAL_BYTES - total), deadline)
            except FileNotFoundError:
                missing = True
                continue
            need(not missing)
            total += len(raw)
            need(total <= MAX_TOTAL_BYTES and type(parsed_json(raw)) is shape)
            stage = token
        return stage
    finally:
        for fd in reversed(fds):
            os.close(fd)


def invoke_helper(root, argv):
    # Exact original argv, no shell, retries, new timeout, install or runtime patch.
    # Original helper raw stdout/stderr is not forwarded; its /tmp logs remain intact.
    return subprocess.run([sys.executable, '-I', '-S', str(root / 'private_h0_flat_bootstrap.py'), *argv],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode


def emit(stage):
    need(stage in ENUMS)
    line = PREFIX + stage + '\n'
    need(line.isascii() and len(line.encode('ascii')) <= 80)
    sys.stdout.write(line)
    sys.stdout.flush()


def run_diagnostic(argv):
    try:
        root, eid = validated_request(argv)
        code = invoke_helper(root, argv)  # Exactly one invocation; no rerun on failure.
    except BaseException:
        emit('OBSERVER_REJECTED')
        return 2  # No helper return code exists if validation/spawn failed.
    try:
        stage = observe_stage(eid)
    except BaseException:
        stage = 'OBSERVER_REJECTED'
    emit(stage)
    return code  # Observer rejection cannot promote or rewrite the helper result.


def exit_like_helper(code):
    if code < 0:
        sig = -code
        if sig not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(sig, signal.SIG_DFL)
        os.kill(os.getpid(), sig)  # Reproduce only the helper's signal on this wrapper itself.
        raise SystemExit(128 + sig)
    raise SystemExit(code)


if __name__ == '__main__':
    exit_like_helper(run_diagnostic(sys.argv[1:]))
