"""DFAT AI Engine — Local LLM triage, classification, ranking, and summarisation (stage 3)."""

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.fallback import RuleBasedAnalyzer
from dfat.ai_engine.llm import (
    FORENSIC_SYSTEM_PROMPT,
    PROMPT_VERSION,
    ForensicPromptTemplates,
    LLMConfig,
    LLMConnectionManager,
    LLMHealthStatus,
    LLMResponse,
    OllamaClient,
)
from dfat.ai_engine.preprocessing import (
    ArtefactBatcher,
    ArtefactSerializer,
    TokenTruncator,
)
from dfat.ai_engine.triage import (
    ArtefactClassifier,
    InvestigativeSummarizer,
    RelevanceRanker,
)

__all__ = [
    "FORENSIC_SYSTEM_PROMPT",
    "PROMPT_VERSION",
    "ArtefactBatcher",
    "ArtefactClassifier",
    "ArtefactSerializer",
    "ForensicPromptTemplates",
    "InvestigativeSummarizer",
    "LLMConfig",
    "LLMConnectionManager",
    "LLMHealthStatus",
    "LLMResponse",
    "LocalLLMClient",
    "OllamaClient",
    "RelevanceRanker",
    "RuleBasedAnalyzer",
    "TokenTruncator",
]
