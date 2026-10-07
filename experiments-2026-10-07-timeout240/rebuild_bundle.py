#!/usr/bin/env python3
"""Reconstruct this experiment's six-file bundles offline. No upload or model run."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

MEMBERS = (
    "agent.yaml", "configs/sampling.yaml", "eval_config.yaml",
    "prompts/engineer.md", "sub_agents/scout.md", "sub_agents/scout.yaml",
)
EXPECTED = {
    "candidate": "1ebbb3e76e2dc2577436f2e52a31f667f750bc26f9139f7fb10098db710808b9",
    "baseline": "d43f47063a4df557325d3e9e3cf28fddeb00ddbbcd49150e50a200d50a52d6fa",
}


def reconstruct(root: Path, variant: str) -> bytes:
    manifest = json.loads((root / "artifact_manifest.json").read_text())
    payloads = []
    for name in MEMBERS:
        data = (root / "candidate" / name).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        wanted = manifest["candidate_members"][name]["sha256"]
        if actual != wanted:
            raise ValueError(f"Candidate member has changed: {name}")
        if variant == "baseline" and name == "eval_config.yaml":
            data = (root / "baseline" / "eval_config.yaml").read_bytes()
        baseline_wanted = manifest["baseline_members"][name]["sha256"]
        if variant == "baseline" and hashlib.sha256(data).hexdigest() != baseline_wanted:
            raise ValueError(f"Baseline member has changed: {name}")
        payloads.append((name, data))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in payloads:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compresslevel=9)
    result = stream.getvalue()
    if hashlib.sha256(result).hexdigest() != EXPECTED[variant]:
        raise ValueError("Archive hash differs; inspect Python/zlib versions and member bytes")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("candidate", "baseline"), default="candidate")
    parser.add_argument("--output", type=Path, help="Optional NEW .zip path; existing paths are never overwritten")
    args = parser.parse_args()
    result = reconstruct(Path(__file__).resolve().parent, args.variant)
    if args.output is not None:
        if args.output.suffix != ".zip":
            parser.error("--output must end in .zip")
        with args.output.open("xb") as destination:
            destination.write(result)
    print(json.dumps({
        "variant": args.variant, "bytes": len(result),
        "sha256": hashlib.sha256(result).hexdigest(), "status": "EXACT_ARCHIVE_MATCH",
        "python": sys.version.split()[0], "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        "written": str(args.output) if args.output is not None else None,
        "submission_performed": False, "model_run_performed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
