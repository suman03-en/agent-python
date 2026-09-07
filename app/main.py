import argparse
import os
import json
import sys
import subprocess
from pathlib import Path
import ast  # abstract syntax tree module for parsing Python code

from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
LOCAL = os.getenv("LOCAL", default="False").lower() == "true"
PROJECT_ROOT = Path.cwd().resolve()

# codecrafters uses the claude-haiku-4.5 model, but im using the minimax-m3 model for local testing because it is free and has a similar API. You can change this to any other model you want to use.
if LOCAL:
    LLM_MODEL = "minimax/minimax-m3:free"
else:
    LLM_MODEL = "anthropic/claude-haiku-4.5"


def resolve_path(file_path: str) -> Path:
    path = (PROJECT_ROOT / file_path).resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise ValueError(
            f"Access denied: {file_path} is outside the project directory."
        )
    return path


def read_file(file_path: str) -> Dict[str, Any]:
    if not file_path:
        raise RuntimeError("file_path argument is required for Read function")

    try:
        path = resolve_path(file_path)

        if not path.is_file():
            return {"success": False, "message": f"{file_path} does not exist."}
        with open(path, "r", encoding="utf-8") as f:
            result = f.read()
        return {"success": True, "message": result}
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {
            "success": False,
            "message": f"Error reading file {file_path}: {str(e)}",
        }


def write_file(file_path: str, content: str) -> Dict[str, Any]:
    try:
        path = resolve_path(file_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            return {"success": True, "message": f"Successfully wrote {file_path}"}
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {
            "success": False,
            "message": f"Error writing file {file_path}: {str(e)}",
        }


def find_function_in_file(file_path: str, function_name: str) -> Dict[str, Any]:
    file_content = read_file(file_path)
    if not file_content.get("success"):
        return {
            "success": False,
            "message": file_content.get("message", "Unknown error reading file."),
        }

    tree = ast.parse(file_content.get("message", ""))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return {
                "success": True,
                "message": {
                    "function_name": node.name,
                    "line_number": node.lineno,
                    "end_line_number": node.end_lineno,
                },
            }

def patch_file(file_path: str, search_block: str, replacement_block: str) -> Dict[str, Any]:
    try:
        path = resolve_path(file_path=file_path)
        if not path.exists():
            return {"success": False, "message": f"{file_path} does not exist."}
        content = read_file(file_path=file_path)
        if not content.get("success"):
            return {
                "success": False,
                "message": content.get("message", "Unknown error reading file."),
            }
        normalized_content = content["message"].replace("\r\n", "\n")
        normalized_search = search_block.replace("\r\n", "\n")
        normalized_replacement = replacement_block.replace("\r\n", "\n")
 
        match_count = normalized_content.count(normalized_search)
        if match_count == 0:
            return {
                "success": False,
                "message": f"Search block not found in {file_path}.",
            }
        if match_count > 1:
            return {
                "success": False,
                "message": f"Search block found {match_count} times in {file_path}. resolve it first before patching.",
            }
        new_content = normalized_content.replace(normalized_search, normalized_replacement)
        write_result = write_file(file_path=file_path, content=new_content)
        if not write_result.get("success"):
            return {
                "success": False,
                "message": write_result.get("message", "Unknown error writing file."),
            }
    except ValueError as e:
        return {"success": False, "message": str(e)}


def execute_command(command):
    result = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=100,
    )
    return {
        "stderr": result.stderr,    
        "stdout": result.stdout,
        "returncode": result.returncode,
    }


# tools mapping to functions
TOOL_MAP = {
    "Read": read_file,
    "Write": write_file,
    "WritePatch": patch_file,
    "Bash": execute_command,
    "ReadFunction": find_function_in_file,
}

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
            "description": """
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
            "description": """
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


def ask_user_permission(tool_name: str, arguments: dict) -> bool:
    """CLI prompt to grant or reject tool execution."""
    print("\n" + "=" * 50)
    print(f"⚠️  PERMISSION REQUIRED: The agent wants to execute `{tool_name}`")
    print("Arguments:")
    print(json.dumps(arguments, indent=2))
    print("=" * 50)

    #loop until user provides valid input
    while True:
        choice = input("Allow this action? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("", "n", "no"):
            return False
        print("Please enter 'y' for yes or 'n' for no.")


def dispatch_tool(tool_name: str, arguments: Dict[str, Any]):
    """dispatch the tool call to the appropriate function after asking for user permission."""

    if tool_name not in TOOL_MAP:
        return f"Error: Tool '{tool_name}' not found."
    allowed = ask_user_permission(tool_name, arguments)
    if not allowed:
        return (
            f"Action Denied: The user declined permission to execute `{tool_name}` "
            f"with arguments {json.dumps(arguments)}. "
            "Ask the user what they would prefer to do instead or suggest an alternative."
        )
    try:
        handler = TOOL_MAP[tool_name]
        return handler(**arguments)
    except Exception as e:
        return f"Execution Error: {str(e)}"


def run_agent_loop(client: OpenAI, prompt: str, max_iterations: int = 10):
    """Run the agent loop until the agent has no more tool calls to make."""

    messages = [{"role": "user", "content": prompt}]

    iteration = 0
    while True:
        if iteration >= max_iterations:
            return "Maximum iterations reached."

        chat = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            extra_body={"reasoning": {"enabled": True}},
            tools=TOOL_SCHEMAS,
        )
        if not chat.choices or len(chat.choices) == 0:
            raise RuntimeError("no choices in response")

        message = chat.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        # comment this out if final output is only needed
        if message.content:
            print(message.content)

        if not message.tool_calls or len(message.tool_calls) == 0:
            # uncomment this for the final output only
            # print(message.content)
            break

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            output = dispatch_tool(tool_name, arguments)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(output),
                }
            )

        iteration += 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        sys.exit("Error: API Key is not set.")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    logo = r"""
                    █████╗ ██╗       █████╗   ██████╗ ███████╗███╗   ██╗████████╗
                    ██╔══██╗██║      ██╔══██╗ ██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
                    ███████║██║      ███████║ ██║  ███╗█████╗  ██╔██╗ ██║   ██║
                    ██╔══██║██║      ██╔══██║ ██║   ██║██╔══╝  ██║╚██╗██║   ██║
                    ██║  ██║███ ██║  ██║ ╚██████╔╝███████╗██║ ╚████║   ██║
                    ╚═╝  ╚═╝╚══════╝ ╚═╝  ╚═╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝

                                            by Suman
     """
    print(logo)

    run_agent_loop(client, args.p)


if __name__ == "__main__":
    main()
