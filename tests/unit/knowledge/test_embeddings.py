"""Unit tests for LocalEmbeddingEngine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact
from dfat.knowledge.embeddings import LocalEmbeddingEngine


@pytest.fixture
def mock_transformer() -> MagicMock:
    model = MagicMock()
    model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384])
    return model


def test_embed_batch_empty_returns_empty_list() -> None:
    engine = LocalEmbeddingEngine()
    assert engine.embed_batch([]) == []


@patch("dfat.knowledge.embeddings.SentenceTransformer")
def test_embed_text_returns_384_dimensions(mock_cls: MagicMock, mock_transformer: MagicMock) -> None:
    mock_cls.return_value = mock_transformer
    mock_transformer.encode.return_value = np.array([0.1] * 384)
    engine = LocalEmbeddingEngine()
    engine._model = mock_transformer
    vector = engine.embed_text("malware process cmd.exe")
    assert len(vector) == 384
    assert all(isinstance(value, float) for value in vector)


@patch("dfat.knowledge.embeddings.SentenceTransformer")
def test_embed_document_includes_metadata(mock_cls: MagicMock, mock_transformer: MagicMock) -> None:
    mock_cls.return_value = mock_transformer
    mock_transformer.encode.return_value = np.array([0.5] * 384)
    engine = LocalEmbeddingEngine()
    vector = engine.embed_document("sample content", {"source": "dataset-a"})
    assert len(vector) == 384
    encoded_text = mock_transformer.encode.call_args[0][0]
    assert "metadata" in encoded_text
    assert "dataset-a" in encoded_text
