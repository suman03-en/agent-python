import json
import logging
from typing import Dict, Any

from openai import OpenAI

from app.config import LLM_MODEL, LOCAL
from app.prompts import SYSTEM_PROMPT
from app.tools import TOOL_MAP, TOOL_SCHEMAS
from app.permissions import ask_user_permission
from app.index import ProjectIndex
from app.tools.index_tools import set_index

logger = logging.getLogger("ai_agent")

# Module-level index reference so filesystem tools can trigger updates
_project_index: ProjectIndex | None = None


def get_index() -> ProjectIndex | None:
    """Return the current project index (used by filesystem write hooks)."""
    return _project_index


def dispatch_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch the tool call to the appropriate function after asking for user permission."""

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
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Arguments: {json.dumps(arguments)}")
        result = handler(**arguments)
        logger.debug(f"Result: {json.dumps(result, default=str)[:200]}")

        # Trigger index update for file-modifying tools
        if tool_name in ("Write", "PatchFile") and _project_index is not None:
            file_path = arguments.get("file_path")
            if file_path:
                try:
                    _project_index.update([file_path])
                    logger.info(f"Index updated for: {file_path}")
                except Exception as e:
                    logger.warning(f"Index update failed for {file_path}: {e}")

        return result
    except Exception as e:
        logger.error(f"Tool execution error: {tool_name} — {e}")
        return f"Execution Error: {str(e)}"


def run_agent_loop(client: OpenAI, prompt: str, max_iterations: int = 10):
    """Run the agent loop until the agent has no more tool calls to make."""
    global _project_index

    # Build or load the project-wide AST index
    logger.info("Building project index...")
    _project_index = ProjectIndex()
    _project_index.build_or_load()
    set_index(_project_index)

    # Inject a compact project overview into the system prompt
    overview = _project_index.project_overview()
    enhanced_prompt = (
        SYSTEM_PROMPT
        + "\n\n## Current Project Structure\n\n"
        + overview
    )

    messages = [
        {"role": "system", "content": enhanced_prompt},
        {"role": "user", "content": prompt},
    ]

    # Only pass reasoning extra_body for models that support it
    extra_kwargs = {}
    if not LOCAL:
        extra_kwargs["extra_body"] = {"reasoning": {"enabled": True}}

    iteration = 0
    while True:
        if iteration >= max_iterations:
            logger.warning("Maximum iterations (%d) reached.", max_iterations)
            return "Maximum iterations reached."

        chat = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            **extra_kwargs,
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

    # Save the index at the end of the session
    if _project_index is not None:
        try:
            _project_index.serialize()
        except Exception as e:
            logger.warning(f"Failed to save index: {e}")
