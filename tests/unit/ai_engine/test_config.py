"""Unit tests for LLMConfig and forensic system prompt (Prompt 5.20)."""

from __future__ import annotations

import pytest

from dfat.ai_engine.llm.config import FORENSIC_SYSTEM_PROMPT, LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager


def test_default_config_values() -> None:
    """Verify LLMConfig defaults are local and conservative."""
    config = LLMConfig()
    assert "localhost" in config.api_url or "127.0.0.1" in config.api_url
    assert config.model == "llama3"
    assert config.temperature == pytest.approx(0.1) or config.temperature <= 0.3
    assert config.max_tokens > 0
    assert config.max_retries >= 1


def test_local_url_validation_accepts_localhost(mock_audit_logger) -> None:
    """Verify localhost / 127.0.0.1 URLs are accepted."""
    for url in (
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://0.0.0.0:11434",
    ):
        config = LLMConfig(api_url=url)
        manager = LLMConnectionManager(config, mock_audit_logger)
        assert manager._is_local_url(url) is True


def test_local_url_validation_rejects_external(mock_audit_logger) -> None:
    """Verify external LLM endpoints are rejected."""
    with pytest.raises(ValueError, match="Non-local|forbidden|chain-of-custody"):
        LLMConnectionManager(
            LLMConfig(api_url="https://api.openai.com/v1"),
            mock_audit_logger,
        )


def test_forensic_system_prompt_content() -> None:
    """Verify the forensic system prompt encodes key safety rules."""
    prompt = FORENSIC_SYSTEM_PROMPT.lower()
    assert "forensic" in prompt or "artefact" in prompt or "artifact" in prompt
    assert "do not fabricate" in prompt or "never fabricate" in prompt
    assert "uncertain" in prompt
    assert "critical" in prompt and "informational" in prompt
