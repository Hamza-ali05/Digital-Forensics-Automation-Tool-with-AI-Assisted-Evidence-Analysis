"""DFAT AI Engine — Local LLM triage, classification, ranking, and summarisation (stage 3)."""

from dfat.ai_engine.fallback import RuleBasedAnalyzer
from dfat.ai_engine.llm import (
    PROMPT_VERSION,
    ForensicPromptTemplates,
    LLMConfig,
    LocalLLMClient,
)
from dfat.ai_engine.triage import (
    ArtefactClassifier,
    InvestigativeSummarizer,
    RelevanceRanker,
)

__all__ = [
    "PROMPT_VERSION",
    "ArtefactClassifier",
    "ForensicPromptTemplates",
    "InvestigativeSummarizer",
    "LLMConfig",
    "LocalLLMClient",
    "RelevanceRanker",
    "RuleBasedAnalyzer",
]
