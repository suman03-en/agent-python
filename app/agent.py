import json
import logging
from typing import Dict, Any

from openai import OpenAI

from app.config import LLM_MODEL, LOCAL
from app.prompts import SYSTEM_PROMPT
from app.tools import TOOL_MAP, TOOL_SCHEMAS
from app.permissions import ask_user_permission

logger = logging.getLogger("ai_agent")


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
        return result
    except Exception as e:
        logger.error(f"Tool execution error: {tool_name} — {e}")
        return f"Execution Error: {str(e)}"


def run_agent_loop(client: OpenAI, prompt: str, max_iterations: int = 10):
    """Run the agent loop until the agent has no more tool calls to make."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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
