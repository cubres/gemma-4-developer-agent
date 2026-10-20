#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""E07 model-free package producer; no launch, model, endpoint or submission."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import stat
import zipfile

SOURCE_PINS = {'LICENSE': {'bytes': 11358, 'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'}, 'NOTICE': {'bytes': 1549, 'sha256': '386b610774c1c13e3adefd8b4af92741f26eab33af65c0ee2734abf720b5aeb1'}, 'README.md': {'bytes': 3102, 'sha256': 'b32cb17f67e556477cbfdf44b2b4e60a7f23b9532bf6f2ba58ef7b7f4ce734c8'}, 'agent.yaml': {'bytes': 245, 'sha256': '6ad913b0c0cb67d669116a4074d7b520b3a69c8d5aa960b6abe51f9850b45227'}, 'eval_config.yaml': {'bytes': 94, 'sha256': '916cf6cb34a6cc3de39837fa72cac681599b9ac2a3ee0b893adadfd36474c531'}, 'sampling.yaml': {'bytes': 119, 'sha256': '571a934e89911734927533f1d36cbcc7b8d493592febe63b217e911cf7ed4926'}, 'system.md': {'bytes': 6862, 'sha256': '811d013466d5a89b7e4aac44e7629c5ee73830bcdb13ff67e5f81de8b5b9c386'}}
GRADED = {'agent.yaml': 'agent.yaml', 'configs/sampling.yaml': 'sampling.yaml',
          'eval_config.yaml': 'eval_config.yaml', 'prompts/system.md': 'system.md'}
ENTRYPOINT = 'e07_cpu_packager.py'
MAX_ARCHIVE = 32768
MAX_RECEIPT = 4096


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, code):
    if not ok:
        raise ValueError(code)


def read_regular(root, name, expected):
    require(name in SOURCE_PINS or name == ENTRYPOINT, 'E07_FIXED_SOURCE_NAME')
    path = root / name
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        cap = expected['bytes'] if expected else 65536
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= cap, 'E07_SOURCE_REGULAR_SIZE')
        data = os.read(fd, cap + 1)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'E07_SOURCE_CHANGED')
        require(len(data) == before.st_size, 'E07_SOURCE_READ_LENGTH')
    finally:
        os.close(fd)
    if expected:
        require(len(data) == expected['bytes'] and sha(data) == expected['sha256'], 'E07_SOURCE_PIN')
    return data


def validate_source(source_root):
    source_root = Path(source_root)
    require(not source_root.is_symlink(), 'E07_SOURCE_ROOT_SYMLINK')
    root = source_root.resolve(strict=True)
    require(root.is_dir(), 'E07_SOURCE_ROOT_DIRECTORY')
    require({p.name for p in root.iterdir()} == set(SOURCE_PINS) | {ENTRYPOINT}, 'E07_SOURCE_MEMBERSHIP')
    data = {name: read_regular(root, name, pin) for name, pin in SOURCE_PINS.items()}
    entrypoint = read_regular(root, ENTRYPOINT, None)
    return {name: data[flat] for name, flat in GRADED.items()}, sha(entrypoint)


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
    require(path.read_bytes() == data, 'E07_OUTPUT_READBACK')


def build(source_root, output_root):
    # Validate every fixed source member before constructing any ZIP bytes.
    files, entrypoint_sha = validate_source(source_root)
    output_root = Path(output_root)
    require(not output_root.is_symlink() and output_root.is_dir(), 'E07_OUTPUT_ROOT')
    root = output_root.resolve(strict=True)
    source = Path(source_root).resolve(strict=True)
    require(root != source and not root.is_relative_to(source), 'E07_OUTPUT_INSIDE_SOURCE')
    require(not any(os.path.lexists(root / name) for name in ('submission.zip', 'e07_public_contract.json')),
            'E07_OUTPUT_ALREADY_PRESENT')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    payload = buf.getvalue()
    require(0 < len(payload) <= MAX_ARCHIVE, 'E07_ARCHIVE_BOUND')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        require(len(archive.infolist()) == 4 and archive.namelist() == sorted(GRADED)
                and archive.testzip() is None, 'E07_ARCHIVE_LAYOUT')
        require(all(archive.read(name) == data for name, data in files.items()), 'E07_ARCHIVE_ROUNDTRIP')
    receipt = {'schema': 'gemma-e07-public-package-contract/1',
               'status': 'PACKAGE_ONLY_NO_QUALITY_CLAIM', 'experiment': 'E07_VERIFICATION_SIX_TOOLS',
               'archive_bytes': len(payload), 'archive_sha256': sha(payload),
               'members': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())},
               'source_entrypoint_sha256': entrypoint_sha,
               'producer_model_calls': 0, 'producer_tool_calls': 0,
               'quality': 'UNMEASURED', 'submission_started': False}
    encoded = (json.dumps(receipt, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    require(len(encoded) <= MAX_RECEIPT, 'E07_RECEIPT_BOUND')
    write_new(root / 'submission.zip', payload)
    write_new(root / 'e07_public_contract.json', encoded)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-only', action='store_true', required=True)
    parser.parse_args()
    result = build(Path(__file__).absolute().parent, Path('/kaggle/working'))
    print(json.dumps({'status': result['status'], 'experiment': result['experiment'],
                      'archive_bytes': result['archive_bytes'], 'archive_sha256': result['archive_sha256']},
                     sort_keys=True, separators=(',', ':')))
