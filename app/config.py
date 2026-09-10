import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
LOCAL = os.getenv("LOCAL", default="False").lower() == "true"
PROJECT_ROOT = Path.cwd().resolve()

# codecrafters uses the claude-haiku-4.5 model, but im using the minimax-m3 model
# for local testing because it is free and has a similar API.
# You can change this to any other model you want to use.
if LOCAL:
    LLM_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
else:
    LLM_MODEL = "anthropic/claude-haiku-4.5"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("ai_agent")
