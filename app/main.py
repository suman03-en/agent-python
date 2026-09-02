import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
LOCAL = os.getenv("LOCAL", default="False").lower() == "true"

if LOCAL:
    LLM_MODEL = "minimax/minimax-m3:free"
else:
    LLM_MODEL = "anthropic/claude-haiku-4.5"


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
        tools={
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
    )

    if not chat.choices or len(chat.choices) == 0:
        raise RuntimeError("no choices in response")

    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    print(chat.choices[0].message.content)


if __name__ == "__main__":
    main()
