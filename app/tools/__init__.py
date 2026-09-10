from app.tools.filesystem import (
    read_file,
    write_file,
    patch_file,
    find_function_in_file,
)
from app.tools.shell import execute_command
from app.tools.index_tools import (
    list_files,
    list_symbols,
    read_symbol,
    find_references,
    find_definition,
    project_overview,
    search_symbols,
)

# ---------------------------------------------------------------------------
# Tool name -> handler mapping
# ---------------------------------------------------------------------------
TOOL_MAP = {
    # Original tools
    "Read": read_file,
    "Write": write_file,
    "PatchFile": patch_file,
    "Bash": execute_command,
    "ReadFunction": find_function_in_file,
    # New index-backed tools
    "ListFiles": list_files,
    "ListSymbols": list_symbols,
    "ReadSymbol": read_symbol,
    "FindReferences": find_references,
    "FindDefinition": find_definition,
    "ProjectOverview": project_overview,
    "SearchSymbols": search_symbols,
}

# ---------------------------------------------------------------------------
# OpenAI function-calling schemas
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": (
                "Read a file inside the current project directory. "
                "file_path must be relative to the project directory. "
                "Do not use absolute paths or paths outside the project. "
                "PREFER ListSymbols or ReadSymbol for code files — they are "
                "cheaper and more targeted. Use Read only for config files, "
                "text files, or when you need the ENTIRE file content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to read",
                    }
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Write",
            "description": (
                "Write a file inside the current project directory. "
                "file_path must be relative to the project directory. "
                "Do not use absolute paths or paths outside the project."
            ),
            "parameters": {
                "type": "object",
                "required": ["file_path", "content"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path of the file to write to",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": (
                "Execute a shell command in the current project directory. "
                "Use Bash commands to find files and run programs. "
                "The environment is Windows with Git Bash available. "
                "Do not use WSL paths such as /mnt/c/. "
                "Use relative paths from the current working directory."
            ),
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ReadFunction",
            "description": """\
Read a specific function from a Python source file using AST parsing.
Returns ONLY that function's source code.
NOTE: Prefer ReadSymbol instead — it works for any language, not just Python,
and supports qualified names like "ClassName.method".\
""",
            "parameters": {
                "type": "object",
                "required": ["file_path", "function_name"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path of the file to read from",
                    },
                    "function_name": {
                        "type": "string",
                        "description": "The name of the function to find",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "PatchFile",
            "description": """\
Replace an exact block of text in a file with new code.
If additional surrounding context is genuinely required, then
Read may be used separately.\
""",
            "parameters": {
                "type": "object",
                "required": ["file_path", "search_block", "replacement_block"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path of the file to patch",
                    },
                    "search_block": {
                        "type": "string",
                        "description": "The block of text to search for",
                    },
                    "replacement_block": {
                        "type": "string",
                        "description": "The block of text to replace the search block with",
                    },
                },
            },
        },
    },
    # ---------------------------------------------------------------
    # New index-backed tools
    # ---------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "ListFiles",
            "description": (
                "List all project source files with their language and symbol count. "
                "Use this FIRST to understand the project structure before reading files."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ListSymbols",
            "description": (
                "List all functions, classes, methods, and variables in a file. "
                "Returns names, signatures, and line ranges ONLY — no source code bodies. "
                "This is ~90% cheaper than Read. Use this to understand a file's structure "
                "before deciding which specific symbols to read."
            ),
            "parameters": {
                "type": "object",
                "required": ["file_path"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file to inspect",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ReadSymbol",
            "description": (
                "Read the source code of a specific function, class, or method. "
                "Uses the AST index to extract exactly the requested symbol — nothing more. "
                "Supports qualified names like 'ClassName.method'. "
                "Much cheaper than Read since it returns only the targeted code."
            ),
            "parameters": {
                "type": "object",
                "required": ["file_path", "symbol_name"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file",
                    },
                    "symbol_name": {
                        "type": "string",
                        "description": (
                            "Name of the symbol to read. "
                            "Use qualified names for methods: 'ClassName.method_name'"
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "FindReferences",
            "description": (
                "Find all callers/references of a symbol across the entire project. "
                "Uses the AST call-graph — much faster and more accurate than grep. "
                "Returns a list of 'file::function' that call the given symbol."
            ),
            "parameters": {
                "type": "object",
                "required": ["symbol_name"],
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "The name of the symbol to find references for",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "FindDefinition",
            "description": (
                "Jump to the definition of a symbol. Returns the file, line range, "
                "and signature — without the full source code. "
                "Use ReadSymbol afterward if you need the actual source."
            ),
            "parameters": {
                "type": "object",
                "required": ["symbol_name"],
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "The name of the symbol to find",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ProjectOverview",
            "description": (
                "Get a high-level structural map of the entire project. "
                "Shows all files with their classes and functions (signatures only). "
                "Use this to understand project architecture without reading any file."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SearchSymbols",
            "description": (
                "Search for symbols by name or docstring substring. "
                "Returns matching symbols with their metadata. "
                "More structured than grep — returns symbol info, not raw text."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (substring match against symbol names and docstrings)",
                    },
                },
            },
        },
    },
]
