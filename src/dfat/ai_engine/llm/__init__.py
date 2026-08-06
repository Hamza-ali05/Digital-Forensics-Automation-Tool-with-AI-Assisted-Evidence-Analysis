"""DFAT LLM Client — Local LLaMA-3 HTTP API client and prompt templates."""

from dfat.ai_engine.llm.client import LocalLLMClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.prompts import PROMPT_VERSION, ForensicPromptTemplates

__all__ = [
    "PROMPT_VERSION",
    "ForensicPromptTemplates",
    "LLMConfig",
    "LocalLLMClient",
]
