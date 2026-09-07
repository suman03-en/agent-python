from app.tools.filesystem import (
    read_file,
    write_file,
    patch_file,
    find_function_in_file,
)
from app.tools.shell import execute_command

# ---------------------------------------------------------------------------
# Tool name -> handler mapping
# ---------------------------------------------------------------------------
TOOL_MAP = {
    "Read": read_file,
    "Write": write_file,
    "PatchFile": patch_file,
    "Bash": execute_command,
    "ReadFunction": find_function_in_file,
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
                "Do not use absolute paths or paths outside the project."
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
                        Read a specific function from a source file.

                        This tool uses AST parsing to locate the requested function and
                        returns ONLY that function's source code.

                        Use this tool when you need to inspect a specific function.
                        Do NOT call Read on the same file afterward just to obtain the
                        function source, because ReadFunction already provides it.

                        If additional surrounding context is genuinely required, then
                        Read may be used separately.
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
                    Read may be used separately.
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
]
