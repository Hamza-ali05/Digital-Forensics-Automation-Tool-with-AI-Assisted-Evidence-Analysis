"""Unit tests for OllamaClient with mocked HTTP."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from dfat.ai_engine.llm.client import LLMResponse, OllamaClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.core.exceptions import LLMConnectionError, LLMTimeoutError


def _ollama(mock_audit_logger: MagicMock) -> OllamaClient:
    config = LLMConfig(
        api_url="http://127.0.0.1:11434",
        model="llama3",
        max_retries=2,
        retry_delay_seconds=0.0,
        request_timeout_seconds=5,
    )
    connection = LLMConnectionManager(config, mock_audit_logger)
    return OllamaClient(config, connection, mock_audit_logger)


def _ok_generate_payload() -> dict:
    return {
        "model": "llama3",
        "created_at": "2026-08-07T08:00:00Z",
        "response": "classified HIGH",
        "done": True,
        "prompt_eval_count": 42,
        "eval_count": 7,
        "total_duration": 1_000_000,
        "load_duration": 100_000,
        "eval_duration": 800_000,
    }


@pytest.mark.asyncio
async def test_generate_parses_llm_response_fields(
    mock_audit_logger: MagicMock,
) -> None:
    client = _ollama(mock_audit_logger)
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = _ok_generate_payload()
    response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await client.generate("analyse artefact art-1")

    assert isinstance(result, LLMResponse)
    assert result.text == "classified HIGH"
    assert result.model == "llama3"
    assert result.prompt_tokens == 42
    assert result.completion_tokens == 7
    assert result.total_duration_ns == 1_000_000
    assert result.done is True


@pytest.mark.asyncio
async def test_generate_connect_error_raises_llm_connection_error(
    mock_audit_logger: MagicMock,
) -> None:
    client = _ollama(mock_audit_logger)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMConnectionError):
            await client.generate("prompt")


@pytest.mark.asyncio
async def test_generate_timeout_raises_llm_timeout_error(
    mock_audit_logger: MagicMock,
) -> None:
    client = _ollama(mock_audit_logger)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMTimeoutError):
            await client.generate("prompt")


@pytest.mark.asyncio
async def test_audit_log_does_not_contain_prompt_text(
    mock_audit_logger: MagicMock,
) -> None:
    client = _ollama(mock_audit_logger)
    secret = "EVIDENCE_SECRET_PATH_C:\\Users\\victim\\passwords.txt"
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = _ok_generate_payload()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.generate(secret)

    for call in mock_audit_logger.log_action.call_args_list:
        kwargs = call.kwargs if call.kwargs else {}
        args = call.args
        payload = kwargs.get("details")
        if payload is None and len(args) >= 4:
            payload = args[3] if isinstance(args[3], dict) else None
        # Also check kwargs-style from our calls
        if "details" in kwargs:
            payload = kwargs["details"]
        blob = json.dumps(kwargs) + json.dumps(args, default=str)
        assert secret not in blob
        if isinstance(payload, dict):
            assert secret not in json.dumps(payload)
            assert "prompt" not in payload
            assert "prompt_text" not in payload


def test_compute_token_estimate() -> None:
    assert OllamaClient._compute_token_estimate("abcd") == 1
    assert OllamaClient._compute_token_estimate("a" * 40) == 10


@pytest.mark.asyncio
async def test_generate_success(mock_audit_logger: MagicMock) -> None:
    """Alias: generate success returns LLMResponse."""
    await test_generate_parses_llm_response_fields(mock_audit_logger)


@pytest.mark.asyncio
async def test_generate_connection_error(mock_audit_logger: MagicMock) -> None:
    """Alias: connect errors map to LLMConnectionError."""
    await test_generate_connect_error_raises_llm_connection_error(mock_audit_logger)


@pytest.mark.asyncio
async def test_generate_timeout(mock_audit_logger: MagicMock) -> None:
    """Alias: timeouts map to LLMTimeoutError."""
    await test_generate_timeout_raises_llm_timeout_error(mock_audit_logger)


@pytest.mark.asyncio
async def test_audit_log_excludes_prompt_content(
    mock_audit_logger: MagicMock,
) -> None:
    """Alias: audit details never include prompt/evidence body."""
    await test_audit_log_does_not_contain_prompt_text(mock_audit_logger)


@pytest.mark.asyncio
async def test_retry_on_failure(mock_audit_logger: MagicMock) -> None:
    """Verify generate retries transient failures before succeeding."""
    client = _ollama(mock_audit_logger)
    fail = MagicMock()
    fail.status_code = 500
    fail.request = MagicMock()
    fail.raise_for_status = MagicMock()
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = _ok_generate_payload()
    ok.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("transient"),
            ok,
        ]
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await client.generate("retry me")

    assert isinstance(result, LLMResponse)
    assert result.text == "classified HIGH"
    assert mock_client.post.await_count == 2
