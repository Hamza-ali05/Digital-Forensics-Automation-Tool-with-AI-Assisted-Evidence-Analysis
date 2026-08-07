"""Unit tests for LegacyLocalLLMClient with mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dfat.ai_engine.llm.client import LegacyLocalLLMClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.core.exceptions import LLMConnectionError
from dfat.core.models.artefact import ArtefactSet


def _client(mock_audit_logger: MagicMock) -> LegacyLocalLLMClient:
    """Build a LegacyLocalLLMClient pointed at localhost."""
    config = LLMConfig(
        api_url="http://127.0.0.1:11434/api/generate",
        model="llama3",
        temperature=0.1,
        max_tokens=256,
        request_timeout_seconds=5,
    )
    return LegacyLocalLLMClient(config, mock_audit_logger, ForensicPromptTemplates())


def test_is_available_returns_true_when_http_ok(mock_audit_logger: MagicMock) -> None:
    """Verify is_available is True when the local API responds OK."""
    # Arrange
    client = _client(mock_audit_logger)
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()

    # Act
    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.return_value = response
        available = client.is_available()

    # Assert
    assert available is True


def test_is_available_returns_false_on_connection_error(
    mock_audit_logger: MagicMock,
) -> None:
    """Verify is_available is False when the local API is unreachable."""
    # Arrange
    client = _client(mock_audit_logger)

    # Act
    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.side_effect = OSError("down")
        available = client.is_available()

    # Assert
    assert available is False


def test_client_rejects_non_local_api_url(mock_audit_logger: MagicMock) -> None:
    """Verify non-localhost API URLs are rejected at construction."""
    # Arrange
    config = LLMConfig(
        api_url="http://evil.example:11434/api/generate",
        model="llama3",
    )

    # Act / Assert
    with pytest.raises(LLMConnectionError):
        LegacyLocalLLMClient(config, mock_audit_logger, ForensicPromptTemplates())


def test_analyze_empty_set_returns_empty_list(mock_audit_logger: MagicMock) -> None:
    """Verify analyze returns an empty list for an empty artefact set."""
    # Arrange
    client = _client(mock_audit_logger)
    empty = ArtefactSet(evidence_id="ev-empty", artefacts=[], categories_present=[])

    # Act
    ranked = client.analyze(empty)

    # Assert
    assert ranked == []
