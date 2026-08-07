"""Helpers for selecting the active AI analyser."""

from __future__ import annotations

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.core.interfaces.analyzer import IArtefactAnalyzer


def select_analyzer(
    llm_client: LocalLLMClient,
    fallback: RuleBasedAnalyzer,
    enable_fallback: bool,
) -> IArtefactAnalyzer:
    """Select the local LLM client or rule-based fallback.

    Args:
        llm_client: Primary local LLaMA-3 analyser.
        fallback: Rule-based fallback analyser.
        enable_fallback: Whether to fall back when the LLM is unavailable.

    Returns:
        Active ``IArtefactAnalyzer`` implementation.
    """
    if llm_client.is_available():
        return llm_client
    if enable_fallback:
        return fallback
    return llm_client
