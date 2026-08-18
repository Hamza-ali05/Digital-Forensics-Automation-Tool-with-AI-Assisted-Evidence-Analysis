"""Local-only LLM constraint and audit-log hygiene tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.classification import (
    ClassificationPromptBuilder,
    ClassificationResponseParser,
    DefaultConfidenceScorer,
    LLMArtefactClassifier,
)
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing import ArtefactBatcher, ArtefactSerializer
from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact


def test_external_llm_url_rejected(mock_audit_logger: MagicMock) -> None:
    """Non-local LLM API URLs are rejected during connection setup."""
    with pytest.raises(ValueError, match="Non-local|forbidden|chain-of-custody"):
        LLMConnectionManager(
            LLMConfig(api_url="https://api.openai.com"),
            mock_audit_logger,
        )


@pytest.mark.asyncio
async def test_prompt_content_not_logged(mock_audit_logger: MagicMock) -> None:
    """Classification audit records metadata only — never artefact bodies."""
    secret = "UNIQUE_ARTEFACT_SECRET_DO_NOT_LOG_XYZ"
    artefact = Artefact(
        artefact_id="art-sec-1",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev-sec-1",
        raw_data={"path": f"/tmp/{secret}.dll", "identifier": secret},
        source_path=f"/Windows/System32/{secret}.dll",
    )
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text=(
                '[{"artefact_id":"art-sec-1","suspicion_level":"LOW",'
                '"confidence":0.4,"reasoning":"benign"}]'
            ),
            model="llama3",
        )
    )
    serializer = ArtefactSerializer()
    classifier = LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=ClassificationPromptBuilder(
            templates=ForensicPromptTemplates(),
            serializer=serializer,
            batcher=ArtefactBatcher(
                max_tokens_per_batch=5000,
                serializer=serializer,
            ),
        ),
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(model="llama3"),
    )

    results = await classifier.classify([artefact])
    assert len(results) == 1
    mock_audit_logger.log_action.assert_called()
    logged = str(mock_audit_logger.log_action.call_args_list)
    assert secret not in logged
    assert artefact.source_path not in logged
    details = mock_audit_logger.log_action.call_args.kwargs.get("details") or {}
    assert "prompt" not in details
    assert secret not in str(details)
