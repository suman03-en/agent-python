"""Project-wide AST index with lookup, search, and call-graph queries.

The index is built once at startup and incrementally updated when files
change.  It can be serialized to/from JSON for persistence across runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from app.index.models import FileRecord, SymbolRecord
from app.index.treesitter_parser import parse_file

logger = logging.getLogger("ai_agent.index")

# Extensions we know how to parse (tree-sitter or regex)
_PARSEABLE_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cxx", ".cc", ".hpp",
    ".rb",
}

# Directories to always skip
_SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules", ".tox",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    ".ai_sessions", ".ai_index",
}

# Index persistence file name
INDEX_FILE = ".ai_index.json"


class ProjectIndex:
    """In-memory, queryable index of every symbol in the project."""

    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            from app.config import PROJECT_ROOT
            project_root = PROJECT_ROOT
        self.project_root = project_root
        self.files: dict[str, FileRecord] = {}  # relative path -> FileRecord
        self._reverse_calls: dict[str, list[str]] = {}  # symbol -> callers

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _discover_files(self) -> list[str]:
        """Walk the project and return relative paths for parseable files.

        Respects .gitignore by checking git ls-files first; falls back to
        filesystem walk if git is unavailable.
        """
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                capture_output=True, text=True, cwd=self.project_root,
                timeout=10,
            )
            if result.returncode == 0:
                all_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
                return [
                    f for f in all_files
                    if Path(f).suffix.lower() in _PARSEABLE_EXTENSIONS
                ]
        except Exception:
            pass

        # Fallback: manual walk
        found = []
        for path in self.project_root.rglob("*"):
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            if path.is_file() and path.suffix.lower() in _PARSEABLE_EXTENSIONS:
                found.append(str(path.relative_to(self.project_root)))
        return found

    def build(self) -> ProjectIndex:
        """Full scan of the project.  Returns self for chaining."""
        files_to_parse = self._discover_files()
        logger.info("Indexing %d files...", len(files_to_parse))

        for rel_path in files_to_parse:
            try:
                record = parse_file(rel_path, project_root=self.project_root)
                self.files[rel_path] = record
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", rel_path, exc)

        self._build_reverse_calls()
        logger.info("Index built: %d files, %d symbols.",
                     len(self.files), sum(len(f.symbols) for f in self.files.values()))
        return self

    def _build_reverse_calls(self):
        """Build reverse call-graph: for each symbol, who calls it."""
        self._reverse_calls.clear()
        for record in self.files.values():
            for sym in record.symbols:
                caller = f"{record.file_path}::{sym.qualified_name}"
                for callee in sym.calls:
                    self._reverse_calls.setdefault(callee, []).append(caller)

    # ------------------------------------------------------------------
    # Incremental update
    # ------------------------------------------------------------------

    def update(self, changed_files: list[str]) -> None:
        """Re-parse only the files that changed (checksum comparison)."""
        for rel_path in changed_files:
            abs_path = (self.project_root / rel_path).resolve()
            if not abs_path.is_file():
                # File deleted
                self.files.pop(rel_path, None)
                continue

            source = abs_path.read_bytes()
            new_checksum = hashlib.sha256(source).hexdigest()

            existing = self.files.get(rel_path)
            if existing and existing.checksum == new_checksum:
                continue  # No change

            try:
                record = parse_file(rel_path, source=source,
                                    project_root=self.project_root)
                self.files[rel_path] = record
            except Exception as exc:
                logger.warning("Failed to re-parse %s: %s", rel_path, exc)

        self._build_reverse_calls()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def lookup(self, name: str) -> list[SymbolRecord]:
        """Find all symbols matching a name (exact or qualified)."""
        results = []
        for record in self.files.values():
            for sym in record.symbols:
                if sym.name == name or sym.qualified_name == name:
                    results.append(sym)
        return results

    def get_file_summary(self, file_path: str) -> Optional[str]:
        """Return a compact summary of a file (symbols + signatures, no bodies)."""
        record = self.files.get(file_path)
        if not record:
            return None
        return record.to_summary()

    def get_file_symbols(self, file_path: str) -> list[SymbolRecord]:
        """Return all symbols in a file."""
        record = self.files.get(file_path)
        return record.symbols if record else []

    def get_callers(self, symbol_name: str) -> list[str]:
        """Return all callers of a symbol (reverse call graph)."""
        return self._reverse_calls.get(symbol_name, [])

    def get_callees(self, symbol_name: str) -> list[str]:
        """Return all functions a symbol calls (forward call graph)."""
        for record in self.files.values():
            for sym in record.symbols:
                if sym.name == symbol_name or sym.qualified_name == symbol_name:
                    return sym.calls
        return []

    def search(self, query: str) -> list[SymbolRecord]:
        """Fuzzy substring search across symbol names and docstrings."""
        query_lower = query.lower()
        results = []
        for record in self.files.values():
            for sym in record.symbols:
                if query_lower in sym.name.lower():
                    results.append(sym)
                elif sym.docstring and query_lower in sym.docstring.lower():
                    results.append(sym)
                elif sym.qualified_name and query_lower in sym.qualified_name.lower():
                    results.append(sym)
        return results

    def get_symbol_source(self, file_path: str, symbol_name: str) -> Optional[str]:
        """Read the source code of a specific symbol from disk.

        Uses the line range from the index to extract exactly the symbol's
        code without reading/sending the entire file.
        """
        record = self.files.get(file_path)
        if not record:
            return None

        target = None
        for sym in record.symbols:
            if sym.name == symbol_name or sym.qualified_name == symbol_name:
                target = sym
                break
        if not target:
            return None

        abs_path = (self.project_root / file_path).resolve()
        if not abs_path.is_file():
            return None

        lines = abs_path.read_text(encoding="utf-8").splitlines()
        # line_start and line_end are 1-indexed, inclusive
        start = max(0, target.line_start - 1)
        end = min(len(lines), target.line_end)
        return "\n".join(lines[start:end])

    def project_overview(self) -> str:
        """High-level map of the entire project.

        Returns a compact string: files → classes → functions.
        Suitable for injection into the system prompt.
        """
        lines = [f"# Project Overview ({len(self.files)} files)\n"]
        for rel_path in sorted(self.files.keys()):
            record = self.files[rel_path]
            sym_counts = {}
            for sym in record.symbols:
                sym_counts[sym.kind] = sym_counts.get(sym.kind, 0) + 1
            counts_str = ", ".join(f"{v} {k}{'s' if v > 1 else ''}"
                                   for k, v in sorted(sym_counts.items()))
            lines.append(f"## {rel_path} ({record.language})")
            if counts_str:
                lines.append(f"  {counts_str}")
            for sym in record.symbols:
                lines.append(f"  {sym.to_summary_line()}")
            lines.append("")
        return "\n".join(lines)

    def list_files(self) -> list[dict]:
        """List all indexed files with symbol counts."""
        result = []
        for rel_path in sorted(self.files.keys()):
            record = self.files[rel_path]
            result.append({
                "file": rel_path,
                "language": record.language,
                "symbols": len(record.symbols),
                "confidence": record.parse_confidence,
            })
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def serialize(self) -> None:
        """Save the index to disk as JSON."""
        data = {
            rel_path: record.to_dict()
            for rel_path, record in self.files.items()
        }
        index_path = self.project_root / INDEX_FILE
        index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Index saved to %s", index_path)

    def deserialize(self) -> bool:
        """Load the index from disk.  Returns True if successful."""
        index_path = self.project_root / INDEX_FILE
        if not index_path.is_file():
            return False
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            self.files = {
                rel_path: FileRecord.from_dict(record_data)
                for rel_path, record_data in data.items()
            }
            self._build_reverse_calls()
            logger.info("Index loaded from %s: %d files", index_path, len(self.files))
            return True
        except Exception as exc:
            logger.warning("Failed to load index: %s", exc)
            return False

    def build_or_load(self) -> ProjectIndex:
        """Load from cache if available and fresh, otherwise full build."""
        if self.deserialize():
            # Verify checksums for a few files to decide if cache is stale
            stale_files = []
            for rel_path, record in list(self.files.items()):
                abs_path = (self.project_root / rel_path).resolve()
                if not abs_path.is_file():
                    stale_files.append(rel_path)
                    continue
                current_hash = hashlib.sha256(abs_path.read_bytes()).hexdigest()
                if current_hash != record.checksum:
                    stale_files.append(rel_path)

            if stale_files:
                logger.info("Updating %d stale files in index...", len(stale_files))
                self.update(stale_files)
                self.serialize()
        else:
            self.build()
            self.serialize()
        return self
