# SPDX-License-Identifier: MIT
# MIT License
#
# Copyright (c) 2026 cubres
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""Scalar CLI for an owned locator copied beside this file in an ADK skill.

The repository root is fixed to /workspace. ADK changes cwd to the temporary
skill directory, so cwd is never used to choose repository source. JSON stdout
is one line and at most 4500 UTF-8 bytes; handled failures also return JSON.
This is a standalone mechanics wrapper, without an agent configuration or
evaluation claim. The inspected ADK route still requires integration testing.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.abc
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import sys

_TRUSTED_ROOT = "/workspace"
_CORE_SHA256 = "2ed99d4296e273543df986cb05dec1e5570443a1aac4da59f7f1843afd8b2eae"
_MAX_STDOUT_BYTES = 4500
_MAX_CORE_BYTES = 65536


class _ArgumentError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ArgumentError(message)


class _VerifiedLoader(importlib.abc.SourceLoader):
    """Load only already-verified owned bytes; never consult cwd or write pyc."""
    def __init__(self, filename: str, source: bytes):
        self.filename, self.source = filename, source

    def get_filename(self, fullname: str) -> str:
        return self.filename

    def get_data(self, path: str) -> bytes:
        if path != self.filename:
            raise OSError("only the verified owned source is available")
        return self.source


def _load_core():
    """Ignore same-named modules on sys.path; attest the published sibling."""
    source_path = Path(__file__).resolve().with_name("bounded_ast_locator.py")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(source_path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("owned locator must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            source = stream.read(_MAX_CORE_BYTES + 1)
    finally:
        os.close(fd)
    if len(source) > _MAX_CORE_BYTES or hashlib.sha256(source).hexdigest() != _CORE_SHA256:
        raise ValueError("owned locator does not match its published source hash")
    loader = _VerifiedLoader(str(source_path), source)
    specification = importlib.util.spec_from_loader("_owned_bounded_ast_locator", loader)
    if specification is None:
        raise RuntimeError("cannot load the verified owned locator")
    core = importlib.util.module_from_spec(specification)
    loader.exec_module(core)
    return core


def _integer(name: str, maximum: int):
    def parse(value: str) -> int:
        try:
            result = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from error
        if not 1 <= result <= maximum:
            raise argparse.ArgumentTypeError(f"{name} must be between 1 and {maximum}")
        return result
    return parse


def _seconds(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("seconds must be a number") from error
    if not math.isfinite(result) or not 0 < result <= 3:
        raise argparse.ArgumentTypeError("seconds must be positive, finite and at most 3")
    return result


def _arguments(argv):
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--query", required=True)
    for name, maximum in (("max_results", 6), ("max_files", 2048),
                          ("max_bytes", 8 * 1024 * 1024),
                          ("max_file_bytes", 256 * 1024),
                          ("max_entries", 20000), ("max_ast_nodes", 300000)):
        parser.add_argument("--" + name.replace("_", "-"), "--" + name,
                            dest=name, type=_integer(name, maximum), default=maximum)
    parser.add_argument("--seconds", type=_seconds, default=3.0)
    values = vars(parser.parse_args(argv))
    if not values["query"].strip() or len(values["query"]) > 4000:
        raise _ArgumentError("query must contain 1 to 4000 characters of nonempty text")
    return values


def _error(status: str, error: Exception) -> dict:
    return {"status": status, "error": {"type": type(error).__name__,
            "message": str(error)}, "locations": [], "edges": []}


def _view(result: dict) -> dict:
    """Summarize gaps and reduce display text while keeping retained IDs exact."""
    omitted = {"locations": 0, "edges": 0, "skipped_examples": 0,
               "skipped_reason_kinds": 0, "excerpt_characters": 0,
               "edge_expression_characters": 0, "error_message_characters": 0}
    locations = []
    for item in result.get("locations", [])[:6]:
        entry = {key: item[key] for key in
                 ("filepath", "symbol", "kind", "start_line", "end_line", "score") if key in item}
        excerpt = item.get("excerpt", "")
        entry["excerpt"] = excerpt[:180]
        omitted["excerpt_characters"] += len(excerpt) - len(entry["excerpt"])
        locations.append(entry)
    omitted["locations"] = max(0, len(result.get("locations", [])) - len(locations))
    edges = []
    for item in result.get("edges", [])[:12]:
        entry = {key: item[key] for key in
                 ("filepath", "caller", "line", "target", "evidence") if key in item}
        expression = item.get("expression", "")
        entry["expression"] = expression[:100]
        omitted["edge_expression_characters"] += len(expression) - len(entry["expression"])
        edges.append(entry)
    omitted["edges"] = max(0, len(result.get("edges", [])) - len(edges))
    view = {"status": result.get("status", "ERROR"), "locations": locations, "edges": edges,
            "omitted": omitted, "output_truncated": False,
            "interpretation": "Lexical candidates; static call hints do not prove runtime dispatch or absent behavior."}
    if "limit" in result:
        view["limit"] = result["limit"]
    if "error" in result:
        error = result["error"]
        message = str(error.get("message", ""))
        view["error"] = {"type": str(error.get("type", "Error"))[:80], "message": message[:400]}
        omitted["error_message_characters"] = max(0, len(message) - 400)
    if "coverage" in result:
        coverage = result["coverage"]
        gaps = coverage.get("skipped", [])
        reasons = Counter(gap["reason"] for gap in gaps)
        reason_names = sorted(reasons)
        examples = [{"filepath": gap["filepath"], "reason": gap["reason"]}
                    for gap in gaps[:2]]
        view["coverage"] = {key: coverage[key] for key in
                            ("files_considered", "bytes_read", "entries_considered",
                             "ast_nodes_visited", "complete") if key in coverage}
        view["coverage"].update(skipped_count=len(gaps),
                                skipped_reasons=[{"reason": name, "count": reasons[name]}
                                                 for name in reason_names[:8]],
                                skipped_examples=examples)
        omitted["skipped_examples"] = len(gaps) - len(examples)
        omitted["skipped_reason_kinds"] = max(0, len(reasons) - 8)
    return view


def _emit(result: dict) -> None:
    """Emit deterministic complete JSON <=4500 UTF-8 bytes, including newline."""
    view = _view(result)
    omitted = view["omitted"]
    while True:
        view["output_truncated"] = any(omitted.values())
        # Escapes also cover surrogateescaped filesystem names, which cannot
        # otherwise be encoded as UTF-8; decoded JSON retains each exact path.
        encoded = json.dumps(view, ensure_ascii=True, allow_nan=False, sort_keys=True,
                             separators=(",", ":"))
        if len(encoded.encode("utf-8")) + 1 <= _MAX_STDOUT_BYTES:
            print(encoded)
            return
        coverage = view.get("coverage", {})
        if coverage.get("skipped_examples"):
            coverage["skipped_examples"].pop()
            omitted["skipped_examples"] += 1
        elif view["edges"]:
            entry = view["edges"].pop()
            omitted["edges"] += 1
            omitted["edge_expression_characters"] += len(entry["expression"])
        elif any(entry["excerpt"] for entry in view["locations"]):
            for entry in view["locations"]:
                current = entry["excerpt"]
                keep = 80 if len(current) > 80 else 0
                entry["excerpt"] = current[:keep]
                omitted["excerpt_characters"] += len(current) - keep
        elif view["locations"]:
            view["locations"].pop()
            omitted["locations"] += 1
        elif coverage.get("skipped_reasons"):
            coverage["skipped_reasons"].pop()
            omitted["skipped_reason_kinds"] += 1
        elif len(view.get("error", {}).get("message", "")) > 100:
            message = view["error"]["message"]
            view["error"]["message"] = message[:100]
            omitted["error_message_characters"] += len(message) - 100
        else:
            # Owned locator status/limit fields are short fixed strings. This
            # branch also makes a malformed unexpected result fail as JSON.
            _emit(_error("ERROR", ValueError("unexpected oversized result metadata")))
            return


def main(argv=None) -> int:
    """Accept ADK's scalar --key/value argv; return 0 OK, 1 limit, 2 error."""
    try:
        values = _arguments(sys.argv[1:] if argv is None else argv)
    except (ValueError, argparse.ArgumentError) as error:
        _emit(_error("INVALID_ARGUMENTS", error))
        return 2
    try:
        core = _load_core()
        query = values.pop("query")
        result = core.locate(_TRUSTED_ROOT, query, **values)
        _emit(result)
        return 0 if result["status"] == "OK" else 1
    except Exception as error:
        _emit(_error("ERROR", error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
