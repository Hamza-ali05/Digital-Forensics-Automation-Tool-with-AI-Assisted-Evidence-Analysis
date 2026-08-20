"""Local sentence-transformer embedding generation for forensic knowledge."""

from __future__ import annotations

import json
from typing import Any

from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.models.artefact import Artefact

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # noqa: BLE001 — optional dependency
    SentenceTransformer = None  # type: ignore[assignment,misc]


class LocalEmbeddingEngine:
    """Generates embeddings locally using sentence-transformers.

    Model: all-MiniLM-L6-v2 (~80MB, runs on CPU, 384-dim output).
    NO cloud API calls. All inference is local.
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION = 384

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: Any | None = None
        self._serializer = ArtefactSerializer()

    def _load_model(self) -> None:
        """Lazy-load the sentence-transformer model on first use."""
        if self._model is not None:
            return
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Install with: pip install 'dfat[intelligence]'"
            )
        self._model = SentenceTransformer(self._model_name)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string into a 384-dimensional vector."""
        self._load_model()
        assert self._model is not None
        vector = self._model.encode(text, convert_to_numpy=True, show_progress_bar=False)
        return [float(value) for value in vector.tolist()]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings."""
        if not texts:
            return []
        self._load_model()
        assert self._model is not None
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [[float(value) for value in row.tolist()] for row in vectors]

    def embed_artefact(self, artefact: Artefact) -> list[float]:
        """Serialize a forensic artefact to text and embed it."""
        text = self._serializer.serialize_artefact(artefact)
        return self.embed_text(text)

    def embed_document(self, content: str, metadata: dict[str, Any]) -> list[float]:
        """Embed document content enriched with lightweight metadata context."""
        metadata_text = json.dumps(metadata, sort_keys=True, default=str)
        combined = f"{content}\n\nmetadata: {metadata_text}"
        return self.embed_text(combined)
