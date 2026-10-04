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
"""Bounded source localization; static call candidates are never runtime proof.

``locate(allowed_root, query)`` requires an absolute, canonical directory. It
reads only regular .py files through directory descriptors, without following
symlinks, importing source, executing commands, or writing repository files.
Ranking and output order are deterministic for a completed scan. Global budget
exhaustion returns no locations or edges, rather than a traversal-biased subset.
The time limit is cooperative: an individual filesystem operation or AST parse
cannot be interrupted. Skipped oversized/invalid files remain explicit gaps.
"""

from __future__ import annotations

import ast
import math
import os
from pathlib import Path
import re
import stat
import time

_SKIP_DIRS = frozenset({"tests", "test", "node_modules", "venv", "__pycache__"})
_WORDS = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+")


def _tokens(text: str) -> set[str]:
    words = _WORDS.findall(text)
    return {part.lower() for word in words for part in (word, *_CAMEL.findall(word.replace("_", " ")))}


def _positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


class _Limit(Exception):
    pass


class _Budget:
    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + seconds
        self.files = self.bytes = self.entries = self.nodes = 0

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            raise _Limit("time")


class _Index(ast.NodeVisitor):
    def __init__(self, filepath: str, source: str, budget: _Budget, max_nodes: int):
        self.filepath, self.source, self.lines = filepath, source, source.splitlines()
        self.budget, self.max_nodes = budget, max_nodes
        self.scope: list[str] = []
        self.class_stack: list[tuple[str, tuple[str, ...]]] = []
        self.receiver: str | None = None
        self.caller: str | None = None
        self.parameters: list[set[str]] = []
        self.defs: list[dict] = []
        self.calls: list[dict] = []

    def visit(self, node: ast.AST):
        self.budget.check()
        self.budget.nodes += 1
        if self.budget.nodes > self.max_nodes:
            raise _Limit("AST nodes")
        return super().visit(node)

    def _definition(self, node, kind: str):
        old_caller, old_receiver = self.caller, self.receiver
        self.scope.append(node.name)
        name = ".".join(self.scope)
        first = node.lineno - 1
        body = "\n".join(self.lines[first:min(node.end_lineno, first + 12)])[:4096]
        self.defs.append({"filepath": self.filepath, "symbol": name,
                          "kind": kind, "start_line": node.lineno,
                          "end_line": node.end_lineno, "_body": body})
        self.caller = name
        if isinstance(node, ast.ClassDef):
            bases = tuple(b.id for b in node.bases if isinstance(b, ast.Name))
            self.class_stack.append((name, bases))
            self.receiver = None
        else:
            args = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            parameters = {arg.arg for arg in args}
            parameters.update(arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
            self.parameters.append(parameters)
            if self.class_stack and len(self.scope) == len(self.class_stack[-1][0].split(".")) + 1:
                static = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list)
                positional = (*node.args.posonlyargs, *node.args.args)
                self.receiver = positional[0].arg if positional and not static else None
            elif self.receiver in parameters:
                self.receiver = None
        for child in node.body:
            self.visit(child)
        if isinstance(node, ast.ClassDef):
            self.class_stack.pop()
        else:
            self.parameters.pop()
        self.scope.pop()
        self.caller, self.receiver = old_caller, old_receiver

    def visit_ClassDef(self, node: ast.ClassDef):
        self._definition(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._definition(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._definition(node, "async_function")

    def visit_Call(self, node: ast.Call):
        if self.caller is not None:
            expression = ast.get_source_segment(self.source, node.func) or ""
            self.calls.append({"filepath": self.filepath, "caller": self.caller,
                               "line": node.lineno, "expression": expression[:160],
                               "_func": node.func, "_receiver": self.receiver,
                               "_class": self.class_stack[-1] if self.class_stack else None,
                               "_class_names": tuple(c[0] for c in self.class_stack),
                               "_parameters": set().union(*self.parameters),
                               "_in_function": bool(self.parameters)})
        self.generic_visit(node)


def _resolve(call: dict, symbols: set[str]) -> dict:
    """Resolve literal same-file candidates; rebinding/MRO remain uncertain."""
    fn, target, evidence = call["_func"], None, "unresolved_dynamic_or_external"
    if isinstance(fn, ast.Name):
        if fn.id in call["_parameters"]:
            evidence = "unresolved_parameter"
        scope = call["caller"].split(".")
        for count in range(len(scope), -1, -1):
            if fn.id in call["_parameters"]:
                break
            if call["_in_function"] and ".".join(scope[:count]) in call["_class_names"]:
                continue  # A class body is not a function's lexical closure.
            candidate = ".".join([*scope[:count], fn.id])
            if candidate in symbols:
                target, evidence = candidate, "literal_same_file_name"
                break
    elif isinstance(fn, ast.Attribute):
        cls = call["_class"]
        candidates: list[str] = []
        if isinstance(fn.value, ast.Name):
            if cls and fn.value.id == call["_receiver"]:
                candidates = [f"{cls[0]}.{fn.attr}"]
                evidence = "method_receiver_candidate"
            elif fn.value.id in call["_parameters"]:
                evidence = "unresolved_parameter"
            else:
                candidates = [f"{fn.value.id}.{fn.attr}"]
                evidence = "literal_class_candidate"
        elif (cls and isinstance(fn.value, ast.Call)
              and isinstance(fn.value.func, ast.Name)
              and fn.value.func.id == "super" and not fn.value.args and not fn.value.keywords):
            candidates = [f"{base}.{fn.attr}" for base in cls[1]]
            evidence = "literal_base_candidates"
        matches = sorted({c for c in candidates if c in symbols})
        if len(matches) == 1:
            target = matches[0]
        elif len(matches) > 1:
            evidence = "ambiguous_bases"
        elif evidence != "unresolved_parameter":
            evidence = "unresolved_dynamic_or_external"
    return {k: call[k] for k in ("filepath", "caller", "line", "expression")} | {
        "target": target, "evidence": evidence,
        "uncertainty": "Static syntax only: rebinding, dynamic dispatch, imports and MRO are not proved."}


def locate(allowed_root: str | Path, query: str, *, max_results: int = 6,
           max_files: int = 2048, max_bytes: int = 8 * 1024 * 1024,
           max_file_bytes: int = 256 * 1024, max_entries: int = 20000,
           max_ast_nodes: int = 300000, seconds: float = 3.0) -> dict:
    """Return <=6 ranked definitions and <=24 directed call candidates.

    Query matching uses names, paths and the first twelve definition lines
    (at most 4096 characters); scores are lexical
    relevance, not confidence. Tests/hidden directories are excluded. Locations
    use exact root-relative paths and separate integer line fields. No trained
    model, task identifiers, gold patches or persistent index are required.
    """
    root = Path(allowed_root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("allowed_root must be an absolute canonical directory")
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("allowed_root must be canonical, without symlink components")
    if not isinstance(query, str) or not query.strip() or len(query) > 4000:
        raise ValueError("query must be nonempty text of at most 4000 characters")
    for key, value in (("max_results", max_results), ("max_files", max_files),
                       ("max_bytes", max_bytes), ("max_file_bytes", max_file_bytes),
                       ("max_entries", max_entries), ("max_ast_nodes", max_ast_nodes)):
        _positive_int(key, value)
    if max_results > 6:
        raise ValueError("max_results cannot exceed 6")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("seconds must be positive and finite")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("this platform cannot enforce descriptor-based symlink protection")
    budget = _Budget(seconds)
    definitions, calls, gaps = [], [], []
    nofollow = os.O_RDONLY | os.O_NOFOLLOW

    def walk(directory_fd: int, relative: str = ""):
        budget.check()
        names = []
        with os.scandir(directory_fd) as iterator:
            for entry in iterator:
                budget.check()
                budget.entries += 1
                if budget.entries > max_entries:
                    raise _Limit("directory entries")
                names.append(entry.name)
        for name in sorted(names):
            budget.check()
            path = f"{relative}/{name}" if relative else name
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    gaps.append({"filepath": path, "reason": "symlink skipped"})
                elif stat.S_ISDIR(info.st_mode):
                    if name.startswith(".") or name in _SKIP_DIRS:
                        continue
                    child_fd = os.open(name, nofollow | os.O_DIRECTORY, dir_fd=directory_fd)
                    try:
                        walk(child_fd, path)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(info.st_mode) and name.endswith(".py"):
                    budget.files += 1
                    if budget.files > max_files:
                        raise _Limit("source files")
                    if info.st_size > max_file_bytes:
                        gaps.append({"filepath": path, "reason": "file byte limit"})
                        continue
                    # If a regular file is swapped for a FIFO before open,
                    # nonblocking mode permits fstat to reject it immediately.
                    fd = os.open(name, nofollow | os.O_NONBLOCK, dir_fd=directory_fd)
                    try:
                        opened = os.fstat(fd)
                        if not stat.S_ISREG(opened.st_mode):
                            gaps.append({"filepath": path, "reason": "not a regular file"})
                            continue
                        size = opened.st_size
                        if size > max_file_bytes:
                            gaps.append({"filepath": path, "reason": "file byte limit"})
                            continue
                        if size > max_bytes - budget.bytes:
                            raise _Limit("total source bytes")
                        chunks, read = [], 0
                        while read < size:
                            budget.check()
                            chunk = os.read(fd, min(16384, size - read))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            read += len(chunk)
                            budget.bytes += len(chunk)
                        if os.fstat(fd).st_size != size or read != size:
                            gaps.append({"filepath": path, "reason": "file changed during read"})
                            continue
                    finally:
                        os.close(fd)
                    budget.check()
                    source = b"".join(chunks).decode("utf-8")
                    tree = ast.parse(source, filename=path)
                    index = _Index(path, source, budget, max_ast_nodes)
                    index.visit(tree)
                    definitions.extend(index.defs)
                    symbols = {d["symbol"] for d in index.defs}
                    calls.extend(_resolve(c, symbols) for c in index.calls)
            except (OSError, UnicodeError, SyntaxError, RecursionError) as error:
                gaps.append({"filepath": path, "reason": type(error).__name__})

    # Open every root component separately; a symlink swap in an ancestor
    # between canonical validation and opening cannot redirect the scan.
    root_fd = os.open(os.sep, nofollow | os.O_DIRECTORY)
    try:
        for component in root.parts[1:]:
            next_fd = os.open(component, nofollow | os.O_DIRECTORY, dir_fd=root_fd)
            os.close(root_fd)
            root_fd = next_fd
    except BaseException:
        os.close(root_fd)
        raise
    limit = None
    try:
        try:
            walk(root_fd)
            query_tokens = _tokens(query)
            for definition in definitions:
                budget.check()
                name_hits = len(query_tokens & _tokens(definition["symbol"]))
                path_hits = len(query_tokens & _tokens(definition["filepath"]))
                body_hits = len(query_tokens & _tokens(definition["_body"]))
                definition["score"] = 8 * name_hits + 2 * path_hits + body_hits
            selected = sorted((d for d in definitions if d["score"] > 0),
                              key=lambda d: (-d["score"], d["filepath"], d["start_line"], d["symbol"]))[:max_results]
            keys = {(d["filepath"], d["symbol"]) for d in selected}
            edges = sorted((c for c in calls if (c["filepath"], c["caller"]) in keys
                            or (c["filepath"], c["target"]) in keys),
                           key=lambda c: (c["filepath"], c["line"], c["caller"], c["expression"]))[:24]
            locations = [{k: d[k] for k in ("filepath", "symbol", "kind", "start_line", "end_line", "score")}
                         | {"excerpt": d["_body"][:360]} for d in selected]
            budget.check()
        except _Limit as error:
            limit, locations, edges = str(error), [], []
    finally:
        os.close(root_fd)
    return {"status": "LIMIT" if limit else "OK", "limit": limit,
            "locations": locations, "edges": edges,
            "coverage": {"files_considered": min(budget.files, max_files),
                         "bytes_read": budget.bytes, "entries_considered": min(budget.entries, max_entries),
                         "ast_nodes_visited": min(budget.nodes, max_ast_nodes),
                         "skipped": sorted(gaps, key=lambda g: (g["filepath"], g["reason"])),
                         "complete": limit is None and not gaps},
            "interpretation": "Lexical candidates and static call hints; absent results do not prove absent behavior."}
