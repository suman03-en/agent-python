import argparse
import os
import json
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
LOCAL = os.getenv("LOCAL", default="False").lower() == "true"


# codecrafters uses the claude-haiku-4.5 model, but im using the minimax-m3 model for local testing because it is free and has a similar API. You can change this to any other model you want to use.
if LOCAL:
    LLM_MODEL = "minimax/minimax-m3:free"
else:
    LLM_MODEL = "anthropic/claude-haiku-4.5"

def read_file(file_path: str) -> str:
    with open(file_path, "r") as f:
        return f.read()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    chat = client.chat.completions.create(
        model=LLM_MODEL,

        # model="anthropic/claude-haiku-4.5",
        messages=[{"role": "user", "content": args.p}],
        extra_body={"reasoning": {"enabled": True}},
        tools=[{
                "type": "function",
                "function": {
                    "name": "Read",
                    "description": "Read and return the contents of a file",
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
            }
        ]
    )

    if not chat.choices or len(chat.choices) == 0:
        raise RuntimeError("no choices in response")

    message = chat.choices[0].message

    if message.tool_calls:
        tool_call = message.tool_calls[0]
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        if function_name == "Read":
            file_path = arguments.get("file_path")
            if not file_path:
                raise RuntimeError("file_path argument is required for Read function")
            file_contents = read_file(file_path)
            print(file_contents)
            return
        else:
            raise RuntimeError(f"Unknown function call: {function_name}")
        
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    print(chat.choices[0].message.content)


if __name__ == "__main__":
    main()
