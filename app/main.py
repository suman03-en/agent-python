import argparse
import os
import json
import sys
import subprocess
from pathlib import Path

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

def read_file(file_path: str) -> str:
    if not file_path:
        raise RuntimeError("file_path argument is required for Read function")

    try:
        path = resolve_path(file_path)

        if not path.is_file():
            return f"{file_path} does not exist."

        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except ValueError as e:
        return str(e)

def write_files(file_path: str, content: str):
    try:
        path = resolve_path(file_path)
        with open(path, 'w', encoding="utf-8") as f:
            f.write(content)
            return f"Successfully wrote {file_path}"
    except ValueError as e:
        return str(e)
    
def execute_command(command):
    result = subprocess.run(["bash", "-c", command], capture_output=True, text=True, cwd=PROJECT_ROOT)
    return json.dumps({
                        "stderr": result.stderr,
                        "stdout": result.stdout,
                        "returncode": result.returncode,
                        }
                    )

#tools mapping to functions
TOOL_MAP = {
    "Read": read_file,
    "Write": write_files,
    "Bash": execute_command
}

def ask_user_permission(tool_name: str, arguments: dict) -> bool:
    """CLI prompt to grant or reject tool execution."""
    print("\n" + "=" * 50)
    print(f"⚠️  PERMISSION REQUIRED: The agent wants to execute `{tool_name}`")
    print("Arguments:")
    print(json.dumps(arguments, indent=2))
    print("=" * 50)
    
    while True:
        choice = input("Allow this action? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("", "n", "no"):
            return False
        print("Please enter 'y' for yes or 'n' for no.")

def dispatch_tool(tool_name: str, arguments: Dict[str, Any]):
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
        

def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    messages = [{"role": "user", "content": args.p}]
    tools = [{
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
                    "description": "The path to the file to read"
                    }
                },
                "required": ["file_path"]
                }
            }
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
                    "description": "The path of the file to write to"
                    },
                    "content": {
                    "type": "string",
                    "description": "The content to write to the file"
                    }
                }
                }
            }
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
                    "description": "The command to execute"
                    }
                }
                }
            }
        },
    ]

    while True:
        chat = client.chat.completions.create(
            model=LLM_MODEL,
            # model="anthropic/claude-haiku-4.5",
            messages=messages,
            extra_body={"reasoning": {"enabled": True}},
            tools=tools
        )

        if not chat.choices or len(chat.choices) == 0:
            raise RuntimeError("no choices in response")


        message = chat.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if message.content:
            print(message.content)
        

        if not message.tool_calls or len(message.tool_calls) == 0:
            # print(message.content)
            break

        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            output = dispatch_tool(function_name, arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content":output
            })
        
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)



if __name__ == "__main__":
    main()
