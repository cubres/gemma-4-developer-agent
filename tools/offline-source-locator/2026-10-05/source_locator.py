#!/usr/bin/env python3
"""Read-only, offline BM25 retrieval over UTF-8 Python AST source units."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any

VERSION = "original-stdlib-ast-bm25-v2"
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CAMEL = re.compile(r"_|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
IGNORED_DIRS = frozenset({".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules"})


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tokenize(text: str) -> list[str]:
    return [part.lower() for word in TOKEN.findall(text) for part in CAMEL.split(word) if len(part) > 1]


@dataclass(frozen=True)
class Limits:
    max_files: int = 2048
    max_file_bytes: int = 1_048_576
    max_total_bytes: int = 16_777_216
    max_units: int = 50_000
    max_entries: int = 100_000
    max_directories: int = 4096
    max_depth: int = 64
    max_top_k: int = 20
    max_query_chars: int = 4096
    max_snippet_chars: int = 1200
    max_snippet_lines: int = 20

    def validate(self) -> None:
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in vars(self).values()):
            raise ValueError("All resource limits must be positive integers")


@dataclass
class Unit:
    path: str
    kind: str
    qualified_name: str
    start_line: int
    end_line: int
    source_sha256: str
    frequencies: Counter
    lines: list[str]

    @property
    def key(self) -> tuple:
        return (self.path, self.start_line, self.end_line, self.kind, self.qualified_name)


class ScanStopped(Exception):
    pass


def explicit_root(value: str | Path) -> Path:
    raw = os.fspath(value)
    if not isinstance(raw, str) or raw.startswith("//"):
        raise ValueError("repo_root must use one leading slash; ambiguous // paths are refused")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("repo_root must be an explicit absolute path")
    if ".." in path.parts:
        raise ValueError("repo_root must not contain parent traversal components")
    fd = directory_fd_without_symlinks(path)
    os.close(fd)
    return path


def directory_fd_without_symlinks(path: Path) -> int:
    if str(path).startswith("//"):
        raise ValueError("Ambiguous double-leading absolute paths are refused")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("This descriptor-based implementation requires POSIX O_NOFOLLOW and O_DIRECTORY")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def ast_units(text: str, path: str, sha256: str, max_units: int) -> list[Unit]:
    tree = ast.parse(text, filename=path)
    lines = text.splitlines()
    if not lines:
        return []
    spans = [("module", "<module>", 1, len(lines))]

    def walk(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            nested = scope
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nested = (*scope, child.name)
                decorators = [item.lineno for item in child.decorator_list]
                start = min([child.lineno, *decorators])
                kind = "class" if isinstance(child, ast.ClassDef) else "async_function" if isinstance(child, ast.AsyncFunctionDef) else "function"
                spans.append((kind, ".".join(nested), start, child.end_lineno))
                if len(spans) > max_units:
                    raise ScanStopped("max_units; this file and remaining source not indexed")
            walk(child, nested)

    walk(tree, ())
    result = []
    for kind, name, start, end in spans:
        body = "\n".join(lines[start - 1:end])
        # Weight a declared name twice and its path once; no target labels or
        # precomputed competition graph/embedding data participate.
        frequencies = Counter(tokenize(body) + tokenize(name) * 2 + tokenize(path))
        result.append(Unit(path, kind, name, start, end, sha256, frequencies, lines))
    return sorted(result, key=lambda unit: unit.key)


class SourceIndex:
    def __init__(self, repo_root: str | Path, limits: Limits | None = None):
        self.root = explicit_root(repo_root)
        self.limits = limits or Limits()
        self.limits.validate()
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            raise ValueError("This descriptor-based implementation requires POSIX O_NOFOLLOW and O_DIRECTORY")
        self.units: list[Unit] = []
        self.files: list[dict] = []
        self.directory_events: list[dict] = []
        self.total_bytes = 0
        self.directory_entries_seen = 0
        self.directories_visited = 0
        self.deepest_directory_depth = 0
        self.complete = True
        self.scan_stopped_reason: str | None = None
        root_fd = directory_fd_without_symlinks(self.root)
        try:
            root_metadata = os.fstat(root_fd)
            self.root_identity = (root_metadata.st_dev, root_metadata.st_ino)
            try:
                self._walk(root_fd, "")
            except ScanStopped as error:
                self.complete = False
                self.scan_stopped_reason = str(error)
        finally:
            os.close(root_fd)
        self.units.sort(key=lambda unit: unit.key)
        self.files.sort(key=lambda record: record["path"])
        self.directory_events.sort(key=lambda record: (record["path"], record["status"]))
        self.manifest_sha256 = digest(canonical_json({"files": self.files, "directory_events": self.directory_events, "scan_stopped_reason": self.scan_stopped_reason, "directory_entries_seen": self.directory_entries_seen, "directories_visited": self.directories_visited, "deepest_directory_depth": self.deepest_directory_depth}))
        self.df = Counter(term for unit in self.units for term in unit.frequencies)
        self.average_length = sum(sum(unit.frequencies.values()) for unit in self.units) / max(1, len(self.units))

    def _walk(self, directory_fd: int, relative: str, depth: int = 0) -> None:
        if depth > self.limits.max_depth:
            self.directory_events.append({"path": relative or ".", "status": "max_depth"})
            raise ScanStopped("max_depth; deeper and remaining source coverage unknown")
        if self.directories_visited >= self.limits.max_directories:
            self.directory_events.append({"path": relative or ".", "status": "max_directories"})
            raise ScanStopped("max_directories; remaining source coverage unknown")
        self.directories_visited += 1
        self.deepest_directory_depth = max(self.deepest_directory_depth, depth)
        try:
            names = []
            with os.scandir(directory_fd) as entries:
                while True:
                    # Do not fetch an extra entry after the hard global cap.
                    # At the exact ceiling, EOF cannot be established without
                    # another fetch, so completeness is conservatively refused.
                    if self.directory_entries_seen >= self.limits.max_entries:
                        self.directory_events.append({"path": relative or ".", "status": "max_entries"})
                        raise ScanStopped("max_entries; remaining directory entries and source coverage unknown")
                    try:
                        entry = next(entries)
                    except StopIteration:
                        break
                    self.directory_entries_seen += 1
                    names.append(entry.name)
            names.sort()
        except OSError as error:
            self.complete = False
            self.directory_events.append({"path": relative or ".", "status": "directory_read_error", "errno": error.errno})
            return
        for name in names:
            path = f"{relative}/{name}" if relative else name
            try:
                metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as error:
                self.complete = False
                self.directory_events.append({"path": path, "status": "stat_error", "errno": error.errno})
                continue
            if stat.S_ISLNK(metadata.st_mode):
                self.directory_events.append({"path": path, "status": "excluded_symlink"})
                continue
            if stat.S_ISDIR(metadata.st_mode):
                if name in IGNORED_DIRS:
                    self.directory_events.append({"path": path, "status": "excluded_directory"})
                    continue
                try:
                    child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                except OSError as error:
                    self.complete = False
                    self.directory_events.append({"path": path, "status": "directory_open_error", "errno": error.errno})
                    continue
                try:
                    self._walk(child_fd, path, depth + 1)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(metadata.st_mode) or not name.endswith(".py"):
                continue
            if len(self.files) >= self.limits.max_files:
                raise ScanStopped("max_files; remaining source coverage unknown")
            self._source(directory_fd, name, path, metadata)

    def _source(self, directory_fd: int, name: str, path: str, metadata: os.stat_result) -> None:
        record = {"path": path, "status": "pending", "bytes": metadata.st_size, "sha256": None, "units": 0}
        self.files.append(record)
        if not metadata.st_mode & 0o444:
            record["status"] = "unreadable_mode_bits"
            self.complete = False
            return
        if metadata.st_size > self.limits.max_file_bytes:
            record["status"] = "max_file_bytes"
            self.complete = False
            return
        if self.total_bytes + metadata.st_size > self.limits.max_total_bytes:
            record["status"] = "max_total_bytes"
            raise ScanStopped("max_total_bytes; remaining source coverage unknown")
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("Source changed to a non-regular file")
                remaining = min(self.limits.max_file_bytes, self.limits.max_total_bytes - self.total_bytes)
                data = stream.read(remaining + 1)
                after = os.fstat(stream.fileno())
            identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if identity(before) != identity(after) or before.st_size != len(data):
                record["status"] = "source_changed_during_read"
                self.complete = False
                return
            if len(data) > remaining:
                record["status"] = "read_byte_cap"
                self.complete = False
                return
            self.total_bytes += len(data)
            record.update(bytes=len(data), sha256=digest(data))
            text = data.decode("utf-8-sig", errors="strict")
            try:
                candidates = ast_units(text, path, record["sha256"], self.limits.max_units - len(self.units))
            except ScanStopped:
                record["status"] = "max_units"
                raise
            if len(self.units) + len(candidates) > self.limits.max_units:
                record["status"] = "max_units"
                raise ScanStopped("max_units; this file and remaining source not indexed")
            self.units.extend(candidates)
            record.update(status="indexed", units=len(candidates))
        except OSError as error:
            record.update(status="read_error", errno=error.errno)
            self.complete = False
        except UnicodeDecodeError as error:
            record.update(status="decode_error", error_start=error.start)
            self.complete = False
        except (SyntaxError, ValueError, RecursionError) as error:
            record.update(status="parse_error" if isinstance(error, SyntaxError) else "source_or_ast_error", error_type=type(error).__name__)
            if isinstance(error, SyntaxError):
                record["error_line"] = error.lineno
            self.complete = False

    def _snippet(self, unit: Unit, query_terms: set[str]) -> dict:
        # Select a bounded window near the first matching line. AST coordinates
        # and source hashes always identify the full unmodified original unit.
        anchor = unit.start_line
        for position in range(unit.start_line, unit.end_line + 1):
            if query_terms.intersection(tokenize(unit.lines[position - 1])):
                anchor = position
                break
        start = max(unit.start_line, anchor - 2)
        end = min(unit.end_line, start + self.limits.max_snippet_lines - 1)
        full = "\n".join(unit.lines[start - 1:end])
        snippet = full[:self.limits.max_snippet_chars]
        actual_lines = snippet.count("\n") + 1
        return {"text": snippet, "start_line": start, "end_line": start + actual_lines - 1, "truncated": len(full) > len(snippet) or start > unit.start_line or end < unit.end_line}

    def search(self, query: str, top_k: int = 5) -> dict:
        if not isinstance(query, str) or len(query) > self.limits.max_query_chars:
            raise ValueError("Query must be text within max_query_chars")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= self.limits.max_top_k:
            raise ValueError("top_k exceeds the configured positive bound")
        terms = set(tokenize(query))
        if not terms:
            raise ValueError("Query has no usable identifier or word tokens")
        k1, b = 1.5, 0.75
        count = len(self.units)
        scored = []
        for unit in self.units:
            length = sum(unit.frequencies.values())
            score = 0.0
            for term in sorted(terms.intersection(unit.frequencies)):
                frequency = unit.frequencies[term]
                idf = math.log1p((count - self.df[term] + 0.5) / (self.df[term] + 0.5))
                norm = k1 * (1 - b + b * length / max(1.0, self.average_length))
                score += idf * frequency * (k1 + 1) / (frequency + norm)
            if score > 0:
                scored.append((score, unit))
        scored.sort(key=lambda pair: (-pair[0], *pair[1].key))
        matches = []
        for score, unit in scored[:top_k]:
            matches.append({"path": unit.path, "kind": unit.kind, "qualified_name": unit.qualified_name, "start_line": unit.start_line, "end_line": unit.end_line, "source_sha256": unit.source_sha256, "score": score, "snippet": self._snippet(unit, terms)})
        statuses = Counter(record["status"] for record in self.files)
        return {"version": VERSION, "status": "OK" if self.complete else "INCOMPLETE", "repo_root": str(self.root), "query": query, "query_tokens": sorted(terms), "bm25": {"k1": k1, "b": b, "name_weight": 2, "path_weight": 1}, "limits": vars(self.limits), "coverage": {"index_complete_within_declared_scope": self.complete, "indexed_root_identity": {"device": self.root_identity[0], "inode": self.root_identity[1]}, "source_files_seen": len(self.files), "source_files_indexed": statuses["indexed"], "units_indexed": len(self.units), "bytes_read": self.total_bytes, "directory_entries_seen": self.directory_entries_seen, "directories_visited": self.directories_visited, "deepest_directory_depth": self.deepest_directory_depth, "statuses": dict(sorted(statuses.items())), "scan_stopped_reason": self.scan_stopped_reason, "files": self.files, "directory_events": self.directory_events, "source_manifest_sha256": self.manifest_sha256}, "matches": matches}


def _directory_identity_without_symlinks(path: Path) -> tuple[int, int]:
    fd = directory_fd_without_symlinks(path)
    try:
        metadata = os.fstat(fd)
        return metadata.st_dev, metadata.st_ino
    finally:
        os.close(fd)


def _reject_indexed_root_ancestry(parent_fd: int, indexed_root_identity: tuple[int, int], max_ancestors: int = 256) -> None:
    """Refuse physical root aliases and any ancestry that cannot be validated.

    Only directory descriptors are inspected. Caller retains its parent_fd;
    this bounded walk owns and closes a duplicate and its ancestor descriptors.
    This is a stable-namespace check, not an atomic filesystem transaction.
    """
    if not isinstance(max_ancestors, int) or isinstance(max_ancestors, bool) or max_ancestors < 1:
        raise ValueError("max_ancestors must be a positive integer")
    current_fd = os.dup(parent_fd)
    try:
        for _ in range(max_ancestors):
            current_metadata = os.fstat(current_fd)
            current_identity = (current_metadata.st_dev, current_metadata.st_ino)
            if current_identity == indexed_root_identity:
                raise ValueError("report parent is inside indexed root by descriptor identity")
            ancestor_fd = os.open("..", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current_fd)
            try:
                ancestor_metadata = os.fstat(ancestor_fd)
                ancestor_identity = (ancestor_metadata.st_dev, ancestor_metadata.st_ino)
            except BaseException:
                os.close(ancestor_fd)
                raise
            if ancestor_identity == indexed_root_identity:
                os.close(ancestor_fd)
                raise ValueError("report ancestor is indexed root by descriptor identity")
            if ancestor_identity == current_identity:
                os.close(ancestor_fd)
                return
            os.close(current_fd)
            current_fd = ancestor_fd
        raise ValueError("report ancestry exceeded bounded validation depth")
    finally:
        os.close(current_fd)


def write_exclusive_report(path: str, result: dict, repo_root: Path, indexed_root_identity: tuple[int, int] | None = None) -> None:
    raw = os.fspath(path)
    if not isinstance(raw, str) or raw.startswith("//"):
        raise ValueError("report path must use one leading slash; ambiguous // paths are refused")
    destination = Path(raw)
    repo_root = explicit_root(repo_root)
    if indexed_root_identity is None:
        captured = result.get("coverage", {}).get("indexed_root_identity", {})
        indexed_root_identity = (captured.get("device"), captured.get("inode"))
    if not isinstance(indexed_root_identity, tuple) or len(indexed_root_identity) != 2 or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in indexed_root_identity
    ):
        raise ValueError("report requires captured indexed root device/inode identity")
    if _directory_identity_without_symlinks(repo_root) != indexed_root_identity:
        raise ValueError("indexed root path identity changed before report")
    if not destination.is_absolute():
        raise ValueError("report path must be absolute")
    if ".." in destination.parts:
        raise ValueError("report path must not contain parent traversal components")
    parent = destination.parent
    if parent == repo_root or repo_root in parent.parents:
        raise ValueError("report must be outside repo_root")
    # Descriptor traversal refuses symlink ancestors; O_EXCL refuses any existing
    # leaf. No parent directories are made and no indexed source is written.
    parent_fd = directory_fd_without_symlinks(parent)
    try:
        _reject_indexed_root_ancestry(parent_fd, indexed_root_identity)
        if _directory_identity_without_symlinks(repo_root) != indexed_root_identity:
            raise ValueError("indexed root path identity changed before report creation")
        fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(canonical_json(result).decode("utf-8") + "\n")
    finally:
        os.close(parent_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report", help="Optional fresh exclusive absolute path outside repo_root")
    parser.add_argument("--max-entries", type=int, default=Limits.max_entries)
    parser.add_argument("--max-directories", type=int, default=Limits.max_directories)
    parser.add_argument("--max-depth", type=int, default=Limits.max_depth)
    arguments = parser.parse_args()
    try:
        limits = Limits(max_entries=arguments.max_entries, max_directories=arguments.max_directories, max_depth=arguments.max_depth)
        index = SourceIndex(arguments.repo_root, limits)
        result = index.search(arguments.query, arguments.top_k)
        if arguments.report:
            write_exclusive_report(arguments.report, result, index.root, index.root_identity)
        print(canonical_json(result).decode("utf-8"))
        return 0 if index.complete else 2
    except (OSError, ValueError, RecursionError) as error:
        print(canonical_json({"version": VERSION, "status": "ERROR", "error_type": type(error).__name__, "message": str(error)}).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
