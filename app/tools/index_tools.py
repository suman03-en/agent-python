"""Index-backed tools that provide surgical, context-efficient code access.

These tools replace brute-force file reads with structured queries against
the AST-based project index, reducing context token usage by 70-90%.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.index.project_index import ProjectIndex


# The global index instance is injected by the agent loop at startup.
_index: Optional[ProjectIndex] = None


def set_index(index: ProjectIndex) -> None:
    """Called by the agent loop to make the index available to tools."""
    global _index
    _index = index


def _get_index() -> ProjectIndex:
    if _index is None:
        raise RuntimeError("Project index not initialized. Call set_index() first.")
    return _index


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def list_files() -> Dict[str, Any]:
    """List all indexed project files with symbol counts."""
    idx = _get_index()
    files = idx.list_files()
    if not files:
        return {"success": True, "message": "No indexed files found."}

    lines = [f"{f['file']}  ({f['language']}, {f['symbols']} symbols)" for f in files]
    return {
        "success": True,
        "message": "\n".join(lines),
        "file_count": len(files),
    }


def list_symbols(file_path: str) -> Dict[str, Any]:
    """List all functions/classes/variables in a file — names and signatures only.

    This is drastically cheaper than reading the entire file.
    """
    idx = _get_index()
    summary = idx.get_file_summary(file_path)
    if summary is None:
        return {"success": False, "message": f"File '{file_path}' is not in the index."}
    return {"success": True, "message": summary}


def read_symbol(file_path: str, symbol_name: str) -> Dict[str, Any]:
    """Read the source code of a specific function/class/method.

    Uses the AST index line ranges to extract exactly the requested symbol,
    without sending the entire file into context.
    """
    idx = _get_index()
    source = idx.get_symbol_source(file_path, symbol_name)
    if source is None:
        # Try qualified lookup across all files
        matches = idx.lookup(symbol_name)
        if matches:
            # Try the first match
            match = matches[0]
            source = idx.get_symbol_source(match.file_path, symbol_name)
            if source:
                return {
                    "success": True,
                    "file": match.file_path,
                    "symbol": match.qualified_name,
                    "lines": f"L{match.line_start}-{match.line_end}",
                    "message": source,
                }
        return {
            "success": False,
            "message": f"Symbol '{symbol_name}' not found in '{file_path}'.",
        }

    # Find the symbol record for metadata
    symbols = idx.get_file_symbols(file_path)
    for sym in symbols:
        if sym.name == symbol_name or sym.qualified_name == symbol_name:
            return {
                "success": True,
                "file": file_path,
                "symbol": sym.qualified_name,
                "kind": sym.kind,
                "lines": f"L{sym.line_start}-{sym.line_end}",
                "signature": sym.signature,
                "docstring": sym.docstring,
                "message": source,
            }

    return {"success": True, "message": source}


def find_references(symbol_name: str) -> Dict[str, Any]:
    """Find all callers/references of a symbol across the project.

    Uses the reverse call-graph from the AST index — no grep needed.
    """
    idx = _get_index()
    callers = idx.get_callers(symbol_name)
    if not callers:
        return {
            "success": True,
            "message": f"No references found for '{symbol_name}'.",
            "count": 0,
        }
    return {
        "success": True,
        "message": "\n".join(callers),
        "count": len(callers),
    }


def find_definition(symbol_name: str) -> Dict[str, Any]:
    """Jump to the definition of a symbol.

    Returns the file, line range, and signature — without the full source.
    """
    idx = _get_index()
    matches = idx.lookup(symbol_name)
    if not matches:
        return {
            "success": False,
            "message": f"Symbol '{symbol_name}' not found in the project.",
        }

    results = []
    for sym in matches:
        results.append({
            "file": sym.file_path,
            "kind": sym.kind,
            "name": sym.qualified_name,
            "lines": f"L{sym.line_start}-{sym.line_end}",
            "signature": sym.signature,
            "docstring": sym.docstring,
        })

    if len(results) == 1:
        return {"success": True, **results[0]}
    return {"success": True, "matches": results, "count": len(results)}


def project_overview() -> Dict[str, Any]:
    """Get a high-level structural map of the entire project.

    Returns files → classes → functions with signatures.
    Ideal for understanding project architecture without reading any file.
    """
    idx = _get_index()
    overview = idx.project_overview()
    return {"success": True, "message": overview}


def search_symbols(query: str) -> Dict[str, Any]:
    """Search for symbols by name or docstring substring.

    Faster and more structured than grep — returns symbol metadata
    instead of raw text matches.
    """
    idx = _get_index()
    matches = idx.search(query)
    if not matches:
        return {
            "success": True,
            "message": f"No symbols matching '{query}'.",
            "count": 0,
        }

    lines = [sym.to_summary_line() for sym in matches]
    return {
        "success": True,
        "message": "\n".join(lines),
        "count": len(matches),
    }
