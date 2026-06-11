"""Embedding service for RAG.

Uses sentence-transformers with a lightweight multilingual model.
The model path is resolved relative to the project root so that it works
offline without downloading at runtime.
"""
from pathlib import Path
from typing import Sequence

import numpy as np

from sentence_transformers import SentenceTransformer

# Default model – multilingual, 384 dims, fast on CPU
DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _resolve_model_path(name: str, project_root: Path | None = None) -> str:
    """If a local directory with the same name exists, use it; otherwise let
    sentence-transformers download from Hugging Face (requires network)."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent
    local_dir = project_root / Path(name).name
    if local_dir.exists() and any(local_dir.iterdir()):
        return str(local_dir)
    return name


class EmbeddingService:
    """Thread-safe wrapper around a sentence-transformer model.

    The model is loaded lazily on first call to avoid heavy import at startup.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, project_root: Path | None = None):
        self._model_path = _resolve_model_path(model_name, project_root)
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_path)
        return self._model

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def encode(self, texts: Sequence[str], normalize: bool = True) -> np.ndarray:
        """Encode a batch of texts into dense vectors.

        Returns a float32 ndarray of shape (len(texts), dimension).
        """
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        vectors = self.model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return vectors.astype(np.float32)

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        """Encode a single string."""
        return self.encode([text], normalize=normalize)[0]


# Global singleton – initialized lazily
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
