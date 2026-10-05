#!/usr/bin/env python3
"""Inspect notebook configuration locations locally; emit JSON without execution.

Usage: python notebook_execution_map.py path/to/notebook.ipynb
The command writes only to stdout. It never imports or executes notebook code.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

MAX_BYTES = 2 * 1024 * 1024
MAX_CELLS = 256
MAX_CODE_CHARS = 1024 * 1024
MAX_CELL_CHARS = 256 * 1024
MAX_AST_NODES = 20000
MAX_ASSIGNMENTS = 512
LIMITS = {
    "input_bytes": MAX_BYTES,
    "cells": MAX_CELLS,
    "code_characters": MAX_CODE_CHARS,
    "cell_code_characters": MAX_CELL_CHARS,
    "ast_nodes_per_cell": MAX_AST_NODES,
    "reported_assignments": MAX_ASSIGNMENTS,
}
HEURISTICS = [
    "Locations use zero-based cell indices and one-based code line numbers.",
    "Only uppercase module bindings and bindings inside CFG/Config/Configuration classes are listed.",
    "Function bodies and non-configuration class bodies are excluded.",
    "Budget categories come from identifier names; they do not establish actual execution cost.",
    "Conditional bindings and repeated bindings are reported without resolving control flow.",
    "Arithmetic, calls, attributes and environment lookups are dynamic; no expressions are evaluated.",
    "Only scalar booleans and finite numbers may be displayed; strings and compound literal values are omitted.",
    "Notebook metadata, outputs, attachments and embedded script strings are not inspected.",
    "This is an interface map, not a dependency check, execution plan, score or runtime estimate.",
]
SENSITIVE_BINDING = re.compile(
    r"(?:^|_)(?:PASSWORD|PASSWD|SECRET|CREDENTIALS?|API_KEY|ACCESS_TOKEN|AUTH_TOKEN|PRIVATE_KEY)(?:_|$)",
    re.I,
)
BUDGET_PATTERNS = (
    ("execution_switch", re.compile(r"^(?:RUN|ENABLE|BUILD)_|^(?:DEBUG|DRY_RUN|MODE|RERUN_MODE|TRUE_SUBMISSION)$")),
    ("time_budget", re.compile(r"TIMEOUT|BUDGET|DEADLINE|(?:MAX|LIMIT).*?(?:TIME|SECONDS|MINUTES|HOURS)|END_TIME|RUNTIME")),
    ("work_budget", re.compile(r"EPOCH|FOLD|BATCH|CONCURRENCY|MAX_.*(?:TASK|STEP|CALL|TURN|ACTION|TOKEN|SEQ)|LIMIT")),
    ("reproducibility", re.compile(r"SEED|RANDOM_STATE")),
    ("hardware", re.compile(r"^(?:DEVICE|GPU|TPU|USE_GPU|USE_TPU|KERAS_BACKEND)$")),
)


class InputError(Exception):
    def __init__(self, code: str):
        self.code = code


def base_report(source: bytes | None = None) -> dict:
    return {
        "schema_version": 1,
        "status": "INVALID_INPUT",
        "source_sha256": hashlib.sha256(source).hexdigest() if source is not None else None,
        "limits": LIMITS,
        "heuristic_limits": HEURISTICS,
        "execution": "never_executed",
        "input_mutation": "none",
    }


def literal_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "boolean"
        if isinstance(node.value, (int, float)):
            return "number"
        if isinstance(node.value, str):
            return "string"
        if node.value is None:
            return "null"
        return "other_literal"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return "number" if literal_kind(node.operand) == "number" else None
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return "compound" if all(literal_kind(item) for item in node.elts) else None
    if isinstance(node, ast.Dict):
        return "compound" if all(key is not None and literal_kind(key) and literal_kind(value)
                                 for key, value in zip(node.keys, node.values)) else None
    return None


def binding_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in binding_names(item)]
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        if target.value.id in {"CFG", "Config", "Configuration"}:
            return [target.attr]
    return []


def assignments(tree: ast.Module, cell: int) -> list[dict]:
    found = []

    def visit(statements: list[ast.stmt], scope: str, conditional: bool = False) -> None:
        for node in statements:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(node, ast.ClassDef):
                if node.name == "CFG" or node.name.lower() in {"config", "configuration"}:
                    visit(node.body, node.name, conditional)
                continue
            targets = []
            value = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            elif isinstance(node, ast.AugAssign):
                targets, value = [node.target], None
            for target in targets:
                for name in binding_names(target):
                    if SENSITIVE_BINDING.search(name):
                        continue
                    if scope == "module" and name != name.upper():
                        continue
                    kind = literal_kind(value) if value is not None else None
                    row = {"name": name, "scope": scope, "cell_index": cell,
                           "line": node.lineno, "conditional": conditional,
                           "assignment_kind": "literal" if kind else "dynamic",
                           "expression_kind": type(value).__name__ if value is not None else "Unknown",
                           "literal_kind": kind,
                           "categories": [label for label, pattern in BUDGET_PATTERNS if pattern.search(name.upper())]}
                    # Literal scalars are read directly from the AST, never evaluated.
                    if isinstance(value, ast.Constant) and isinstance(value.value, (bool, int, float)):
                        if not isinstance(value.value, float) or math.isfinite(value.value):
                            row["scalar_value"] = value.value
                    found.append(row)
                    if len(found) > MAX_ASSIGNMENTS:
                        raise InputError("assignment_limit")
            # Traverse structural control flow, while retaining its uncertainty.
            for _, child in ast.iter_fields(node):
                if isinstance(child, list) and child and all(isinstance(item, ast.stmt) for item in child):
                    visit(child, scope, True)
                elif isinstance(child, ast.ExceptHandler):
                    visit(child.body, scope, True)
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, ast.ExceptHandler):
                            visit(item.body, scope, True)

    visit(tree.body, "module")
    return found


def inspect_bytes(source: bytes) -> dict:
    report = base_report(source)
    try:
        if len(source) > MAX_BYTES:
            raise InputError("input_too_large")
        try:
            text = source.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            raise InputError("invalid_utf8") from None
        try:
            notebook = json.loads(text)
        except (ValueError, RecursionError):
            raise InputError("invalid_json") from None
        if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
            raise InputError("missing_cells")
        cells = notebook["cells"]
        if len(cells) > MAX_CELLS:
            raise InputError("cell_limit")
        rows, diagnostics, code_count, code_chars = [], [], 0, 0
        for index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                raise InputError("invalid_cell")
            if cell.get("cell_type") != "code":
                continue
            code_count += 1
            raw = cell.get("source", "")
            if isinstance(raw, str):
                code = raw
            elif isinstance(raw, list) and all(isinstance(part, str) for part in raw):
                code = "".join(raw)
            else:
                raise InputError("invalid_code_source")
            code_chars += len(code)
            if len(code) > MAX_CELL_CHARS or code_chars > MAX_CODE_CHARS:
                raise InputError("code_size_limit")
            try:
                tree = ast.parse(code)
            except (SyntaxError, ValueError, RecursionError) as exc:
                diagnostics.append({"cell_index": index, "kind": "not_plain_python",
                                    "line": getattr(exc, "lineno", None)})
                continue
            if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
                raise InputError("ast_node_limit")
            try:
                rows.extend(assignments(tree, index))
            except RecursionError:
                raise InputError("ast_depth_limit") from None
            if len(rows) > MAX_ASSIGNMENTS:
                raise InputError("assignment_limit")
        report.update(status="PARTIAL" if diagnostics else "MAPPED", cell_count=len(cells),
                      code_cell_count=code_count, code_characters=code_chars,
                      assignments=rows, execution_budget_flags=[row for row in rows if row["categories"]],
                      diagnostics=diagnostics)
    except InputError as exc:
        report["error"] = exc.code
    return report


def inspect_path(path: Path) -> dict:
    try:
        # Opening the exact user-supplied file is the only filesystem operation.
        # Refuse links, directories, FIFOs and devices; bound the read itself.
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise InputError("not_regular_file")
            if info.st_size > MAX_BYTES:
                raise InputError("input_too_large")
            source = stream.read(MAX_BYTES + 1)
        return inspect_bytes(source)
    except (OSError, InputError) as exc:
        report = base_report()
        report["error"] = exc.code if isinstance(exc, InputError) else "cannot_read_input"
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    args = parser.parse_args(argv)
    report = inspect_path(args.notebook)
    json.dump(report, sys.stdout, ensure_ascii=False, allow_nan=False, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if report["status"] == "INVALID_INPUT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
