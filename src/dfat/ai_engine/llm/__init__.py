"""DFAT LLM Client — Local LLaMA-3 HTTP API client and prompt templates."""

from dfat.ai_engine.llm.client import (
    LLMResponse,
    LegacyLocalLLMClient,
    OllamaClient,
)
from dfat.ai_engine.llm.config import (
    FORENSIC_SYSTEM_PROMPT,
    PROMPT_VERSION,
    LLMConfig,
)
from dfat.ai_engine.llm.connection import LLMConnectionManager, LLMHealthStatus
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.llm.response_parser import LLMResponseParser, StructuredOutputParser

__all__ = [
    "FORENSIC_SYSTEM_PROMPT",
    "PROMPT_VERSION",
    "ForensicPromptTemplates",
    "LLMConfig",
    "LLMConnectionManager",
    "LLMHealthStatus",
    "LLMResponse",
    "LLMResponseParser",
    "LegacyLocalLLMClient",
    "OllamaClient",
    "StructuredOutputParser",
]
