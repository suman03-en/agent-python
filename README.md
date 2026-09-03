# AI Assistant

A lightweight command-line coding assistant built in Python. It sends prompts
to an OpenAI-compatible API and can inspect files, write changes, and execute
shell commands through tool calls.

This project was built as a solution for the CodeCrafters Claude Code challenge.

## Features

- File reading through the `Read` tool
- File writing through the `Write` tool
- Shell command execution through the `Bash` tool
- Configurable OpenRouter-compatible model and API endpoint
- Local testing with a free model when `LOCAL=true`

## Requirements

- Python 3.14 or newer
- `uv`
- An OpenRouter API key

## Setup

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=your_api_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Install the project dependencies:

```sh
uv sync
```

## Usage

Pass a coding request with the `-p` option:

```sh
./your_program.sh -p "Explain the files in this project"
```

On Windows, run the module through `uv` if needed:

```powershell
uv run -m app.main -p "Read README.md and summarize it"
```

For local testing with the configured free model:

```env
LOCAL=true
```

The assistant runs in a tool-calling loop until the model returns a final
response.
