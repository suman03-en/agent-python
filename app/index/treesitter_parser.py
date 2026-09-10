"""Tree-sitter-based multi-language source parser.

This is the primary parser backend.  It supports Python, JavaScript,
TypeScript, Go, Rust, Java, C, C++, and Ruby out of the box.  For
unsupported languages it falls back to regex-based heuristics.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Parser, Node

from app.index.models import FileRecord, SymbolRecord

logger = logging.getLogger("ai_agent.index")

# ---------------------------------------------------------------------------
# Language registry — maps file extension to tree-sitter language
# ---------------------------------------------------------------------------

_LANGUAGE_CACHE: dict[str, Language] = {}

# Extension → (tree-sitter-<lang> module name, language function)
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",  # uses typescript for tsx
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
}


def _get_language(lang_name: str) -> Optional[Language]:
    """Lazily load and cache a tree-sitter Language object."""
    if lang_name in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[lang_name]

    try:
        # tree-sitter-python exposes language() at module level
        mod = __import__(f"tree_sitter_{lang_name}", fromlist=["language"])
        lang_obj = Language(mod.language())
        _LANGUAGE_CACHE[lang_name] = lang_obj
        return lang_obj
    except (ImportError, AttributeError, Exception) as exc:
        logger.debug("Could not load tree-sitter language %s: %s", lang_name, exc)
        return None


def _detect_language(file_path: str) -> Optional[str]:
    """Return the tree-sitter language name for a file, or None."""
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext)


# ---------------------------------------------------------------------------
# Node text helper
# ---------------------------------------------------------------------------

def _node_text(node: Node, source: bytes) -> str:
    """Extract the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _first_child_of_type(node: Node, *types: str) -> Optional[Node]:
    """Return the first child matching one of the given types."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def _children_of_type(node: Node, *types: str) -> list[Node]:
    """Return all children matching one of the given types."""
    return [c for c in node.children if c.type in types]


# ---------------------------------------------------------------------------
# Docstring extraction
# ---------------------------------------------------------------------------

def _extract_docstring(node: Node, source: bytes, lang: str) -> Optional[str]:
    """Try to extract a docstring from the first statement of a body."""
    if lang == "python":
        body = _first_child_of_type(node, "block")
        if body and body.children:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement":
                expr = first_stmt.children[0] if first_stmt.children else None
                if expr and expr.type == "string":
                    raw = _node_text(expr, source)
                    # Strip triple quotes
                    for q in ('"""', "'''", '"', "'"):
                        if raw.startswith(q) and raw.endswith(q):
                            return raw[len(q):-len(q)].strip()
                    return raw
    elif lang in ("javascript", "typescript"):
        # Look for JSDoc comment before the node
        if node.prev_sibling and node.prev_sibling.type == "comment":
            text = _node_text(node.prev_sibling, source)
            if text.startswith("/**"):
                return text.strip("/* \n\t")
    return None


# ---------------------------------------------------------------------------
# Call extraction
# ---------------------------------------------------------------------------

def _extract_calls(node: Node, source: bytes) -> list[str]:
    """Walk descendants and collect all function call names."""
    calls = set()

    def _walk(n: Node):
        if n.type == "call":
            func_node = _first_child_of_type(n, "identifier", "attribute")
            if func_node:
                calls.add(_node_text(func_node, source))
        for child in n.children:
            _walk(child)

    _walk(node)
    return sorted(calls)


# ---------------------------------------------------------------------------
# Decorator extraction
# ---------------------------------------------------------------------------

def _extract_decorators(node: Node, source: bytes) -> list[str]:
    """Extract decorator names from a function/class definition."""
    decorators = []
    for child in node.children:
        if child.type == "decorator":
            # Get the decorator expression (skip the '@')
            expr = child.children[1] if len(child.children) > 1 else None
            if expr:
                decorators.append(_node_text(expr, source))
    return decorators


# ---------------------------------------------------------------------------
# Signature extraction
# ---------------------------------------------------------------------------

def _extract_function_signature(node: Node, source: bytes, lang: str) -> str:
    """Extract the function signature (parameters + return type)."""
    params_node = _first_child_of_type(node, "parameters", "formal_parameters",
                                        "parameter_list")
    params = _node_text(params_node, source) if params_node else "()"

    ret = ""
    if lang == "python":
        ret_node = _first_child_of_type(node, "type")
        if ret_node:
            ret = f" -> {_node_text(ret_node, source)}"
    elif lang in ("typescript", "go", "rust", "java"):
        # Look for return type annotation
        for child in node.children:
            if child.type in ("type_annotation", "return_type", "type_identifier",
                              "result"):
                ret = f" -> {_node_text(child, source)}"
                break

    return f"{params}{ret}"


# ---------------------------------------------------------------------------
# Language-specific parsers
# ---------------------------------------------------------------------------

def _parse_python(root: Node, source: bytes, file_path: str) -> FileRecord:
    """Parse a Python file tree-sitter AST into a FileRecord."""
    symbols: list[SymbolRecord] = []
    imports: list[str] = []

    def _process_node(node: Node, parent_class: Optional[str] = None):
        if node.type in ("import_statement", "import_from_statement"):
            imports.append(_node_text(node, source))

        elif node.type == "function_definition":
            name_node = _first_child_of_type(node, "identifier")
            name = _node_text(name_node, source) if name_node else "<anonymous>"
            kind = "method" if parent_class else "function"
            symbols.append(SymbolRecord(
                file_path=file_path,
                kind=kind,
                name=name,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=_extract_function_signature(node, source, "python"),
                docstring=_extract_docstring(node, source, "python"),
                decorators=_extract_decorators(node, source),
                calls=_extract_calls(node, source),
                parent=parent_class,
            ))

        elif node.type == "class_definition":
            name_node = _first_child_of_type(node, "identifier")
            cls_name = _node_text(name_node, source) if name_node else "<anonymous>"

            # Bases
            bases = ""
            arg_list = _first_child_of_type(node, "argument_list")
            if arg_list:
                bases = _node_text(arg_list, source)

            symbols.append(SymbolRecord(
                file_path=file_path,
                kind="class",
                name=cls_name,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=bases if bases else None,
                docstring=_extract_docstring(node, source, "python"),
                decorators=_extract_decorators(node, source),
                calls=[],
                parent=None,
            ))

            # Recurse into the class body for methods
            body = _first_child_of_type(node, "block")
            if body:
                for child in body.children:
                    _process_node(child, parent_class=cls_name)
            return  # Don't recurse further for class

        elif node.type == "expression_statement" and parent_class is None:
            # Module-level variable assignment
            child = node.children[0] if node.children else None
            if child and child.type == "assignment":
                left = child.children[0] if child.children else None
                if left and left.type == "identifier":
                    symbols.append(SymbolRecord(
                        file_path=file_path,
                        kind="variable",
                        name=_node_text(left, source),
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    ))

        # Recurse for top-level nodes (not inside functions)
        if parent_class is None and node.type not in (
            "function_definition", "class_definition"
        ):
            for child in node.children:
                _process_node(child)

    for child in root.children:
        _process_node(child)

    return FileRecord(
        file_path=file_path,
        language="python",
        imports=imports,
        symbols=symbols,
        parse_confidence="treesitter",
    )


def _parse_generic(root: Node, source: bytes, file_path: str, lang: str) -> FileRecord:
    """Generic tree-sitter parser for JS/TS/Go/Rust/Java/C/C++/Ruby.

    Extracts functions and classes from the top-level and one level deep
    (class methods).  Not as detailed as the Python parser but covers
    the essential structure.
    """
    symbols: list[SymbolRecord] = []
    imports: list[str] = []

    # Node types that represent functions across languages
    FUNC_TYPES = {
        "function_declaration", "function_definition", "method_definition",
        "arrow_function", "function", "method_declaration",
        "function_item",  # Rust
        "func_declaration",  # Go (function_declaration already covered)
    }

    CLASS_TYPES = {
        "class_declaration", "class_definition", "struct_item",
        "impl_item", "interface_declaration", "type_declaration",
    }

    IMPORT_TYPES = {
        "import_statement", "import_declaration", "use_declaration",
        "include_directive", "require_statement",
    }

    def _get_name(node: Node) -> str:
        name_node = _first_child_of_type(
            node, "identifier", "property_identifier",
            "type_identifier", "name",
        )
        return _node_text(name_node, source) if name_node else "<anonymous>"

    def _process_node(node: Node, parent_class: Optional[str] = None):
        if node.type in IMPORT_TYPES:
            imports.append(_node_text(node, source))

        elif node.type in FUNC_TYPES:
            name = _get_name(node)
            kind = "method" if parent_class else "function"
            symbols.append(SymbolRecord(
                file_path=file_path,
                kind=kind,
                name=name,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=_extract_function_signature(node, source, lang),
                docstring=_extract_docstring(node, source, lang),
                calls=_extract_calls(node, source),
                parent=parent_class,
            ))

        elif node.type in CLASS_TYPES:
            cls_name = _get_name(node)
            symbols.append(SymbolRecord(
                file_path=file_path,
                kind="class",
                name=cls_name,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                docstring=_extract_docstring(node, source, lang),
            ))
            # Recurse for methods
            body = _first_child_of_type(node, "class_body", "declaration_list",
                                         "block", "body")
            if body:
                for child in body.children:
                    _process_node(child, parent_class=cls_name)
            return

        # Recurse top-level
        if parent_class is None and node.type not in FUNC_TYPES | CLASS_TYPES:
            for child in node.children:
                _process_node(child)

    for child in root.children:
        _process_node(child)

    return FileRecord(
        file_path=file_path,
        language=lang,
        imports=imports,
        symbols=symbols,
        parse_confidence="treesitter",
    )


# ---------------------------------------------------------------------------
# Regex fallback for unsupported languages
# ---------------------------------------------------------------------------

# Common patterns for function/class definitions across languages
_FUNC_PATTERNS = [
    # Python: def func_name(
    re.compile(r"^(\s*)def\s+(\w+)\s*\(", re.MULTILINE),
    # JS/TS: function funcName(
    re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE),
    # Go: func funcName(
    re.compile(r"^(\s*)func\s+(\w+)\s*\(", re.MULTILINE),
    # Rust: fn func_name(
    re.compile(r"^(\s*)(?:pub\s+)?fn\s+(\w+)\s*\(", re.MULTILINE),
    # Ruby: def method_name
    re.compile(r"^(\s*)def\s+(\w+)", re.MULTILINE),
]

_CLASS_PATTERNS = [
    re.compile(r"^(\s*)class\s+(\w+)", re.MULTILINE),
    re.compile(r"^(\s*)struct\s+(\w+)", re.MULTILINE),
    re.compile(r"^(\s*)interface\s+(\w+)", re.MULTILINE),
]


def _parse_with_regex(source_text: str, file_path: str) -> FileRecord:
    """Last-resort regex parser for files without tree-sitter support."""
    symbols: list[SymbolRecord] = []
    lines = source_text.split("\n")

    for pattern in _FUNC_PATTERNS:
        for match in pattern.finditer(source_text):
            line_num = source_text[:match.start()].count("\n") + 1
            name = match.group(2)
            symbols.append(SymbolRecord(
                file_path=file_path,
                kind="function",
                name=name,
                line_start=line_num,
                line_end=line_num,  # Can't determine end without deeper analysis
            ))

    for pattern in _CLASS_PATTERNS:
        for match in pattern.finditer(source_text):
            line_num = source_text[:match.start()].count("\n") + 1
            name = match.group(2)
            symbols.append(SymbolRecord(
                file_path=file_path,
                kind="class",
                name=name,
                line_start=line_num,
                line_end=line_num,
            ))

    # Deduplicate by (name, line_start)
    seen = set()
    deduped = []
    for s in symbols:
        key = (s.name, s.line_start)
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    ext = Path(file_path).suffix.lower()
    lang_guess = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".go": "go", ".rs": "rust", ".java": "java", ".c": "c",
        ".cpp": "cpp", ".rb": "ruby",
    }.get(ext, "unknown")

    return FileRecord(
        file_path=file_path,
        language=lang_guess,
        imports=[],
        symbols=deduped,
        parse_confidence="heuristic",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(file_path: str, source: Optional[bytes] = None,
               project_root: Optional[Path] = None) -> FileRecord:
    """Parse a source file and return a structured FileRecord.

    Tries tree-sitter first, falls back to regex heuristics.

    Args:
        file_path: Path relative to project root.
        source: Raw file bytes.  If None, reads from disk.
        project_root: Absolute path to project root (needed when source is None).

    Returns:
        FileRecord with all extracted symbols.
    """
    if source is None:
        if project_root is None:
            from app.config import PROJECT_ROOT
            project_root = PROJECT_ROOT
        abs_path = (project_root / file_path).resolve()
        source = abs_path.read_bytes()

    # Compute checksum
    checksum = hashlib.sha256(source).hexdigest()

    # Try tree-sitter
    lang_name = _detect_language(file_path)
    if lang_name:
        lang_obj = _get_language(lang_name)
        if lang_obj:
            parser = Parser(lang_obj)
            tree = parser.parse(source)
            if lang_name == "python":
                record = _parse_python(tree.root_node, source, file_path)
            else:
                record = _parse_generic(tree.root_node, source, file_path, lang_name)
            record.checksum = checksum
            return record

    # Fallback to regex
    source_text = source.decode("utf-8", errors="replace")
    record = _parse_with_regex(source_text, file_path)
    record.checksum = checksum
    return record
