"""Data models for the project-wide AST index."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class SymbolRecord:
    """A single symbol extracted from a source file."""

    file_path: str  # relative to PROJECT_ROOT
    kind: str  # "function" | "class" | "method" | "variable" | "import"
    name: str  # symbol name (qualified for methods: "ClassName.method")
    line_start: int  # 1-indexed
    line_end: int  # 1-indexed, inclusive
    signature: Optional[str] = None  # e.g. "(self, x: int) -> str"
    docstring: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)  # functions/methods this symbol calls
    parent: Optional[str] = None  # enclosing class name if method

    @property
    def qualified_name(self) -> str:
        """Return the fully qualified name (e.g. 'ClassName.method')."""
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name

    def to_summary_line(self) -> str:
        """One-line summary for context-efficient listing."""
        prefix = {
            "function": "def",
            "method": "def",
            "class": "class",
            "variable": "var",
            "import": "import",
        }.get(self.kind, self.kind)

        sig = self.signature or ""
        loc = f"L{self.line_start}-{self.line_end}"

        parts = [f"{prefix} {self.qualified_name}{sig}"]
        if self.decorators:
            parts.append(f"@{','.join(self.decorators)}")
        parts.append(f"[{loc}]")

        if self.docstring:
            # First line of docstring only, truncated
            first_line = self.docstring.split("\n")[0].strip()
            if len(first_line) > 60:
                first_line = first_line[:57] + "..."
            parts.append(f'  # {first_line}')

        return " ".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SymbolRecord:
        return cls(**data)


@dataclass
class FileRecord:
    """All extracted information for a single source file."""

    file_path: str  # relative to PROJECT_ROOT
    language: str  # "python" | "javascript" | "typescript" | etc.
    imports: list[str] = field(default_factory=list)
    symbols: list[SymbolRecord] = field(default_factory=list)
    checksum: str = ""  # SHA-256 of file contents for incremental updates
    parse_confidence: str = "ast"  # "ast" | "treesitter" | "heuristic"

    def to_summary(self) -> str:
        """Compact file summary listing all symbols (no bodies)."""
        lines = [f"# {self.file_path} ({self.language})"]
        if self.imports:
            lines.append(f"  imports: {', '.join(self.imports[:10])}")
            if len(self.imports) > 10:
                lines.append(f"  ... and {len(self.imports) - 10} more imports")
        for sym in self.symbols:
            lines.append(f"  {sym.to_summary_line()}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> FileRecord:
        symbols = [SymbolRecord.from_dict(s) for s in data.pop("symbols", [])]
        return cls(**data, symbols=symbols)
