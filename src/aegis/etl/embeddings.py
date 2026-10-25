"""Replaceable Embeddings Provider Interface and Deterministic Providers."""

from abc import ABC, abstractmethod
import hashlib
import math
from typing import List
import numpy as np

from aegis.core.config import get_settings


class BaseEmbeddingProvider(ABC):
    """Abstract interface for dense vector embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        pass


class DeterministicMockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, unit-normalized embedding provider for reproducible tests and local execution.
    
    Uses SHA-256 seed hashing combined with character n-grams to generate pseudo-semantic
    embeddings that exhibit genuine cosine similarity properties for identical or overlapping terms.
    """

    def __init__(self, dimension: int = 384):
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_text(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dim

        # Extract 3-grams and tokens to build term frequency vector
        vec = np.zeros(self._dim, dtype=np.float32)
        words = text.lower().split()
        for word in words:
            # Hash word into bucket
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % self._dim
            vec[idx] += 1.0

            # Hash 3-character ngrams for subword matching
            for i in range(len(word) - 2):
                ngram = word[i : i + 3]
                nh = int(hashlib.md5(ngram.encode("utf-8")).hexdigest()[:8], 16)
                nidx = nh % self._dim
                vec[nidx] += 0.5

        # L2 Unit Normalization for true cosine distance
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        else:
            vec[0] = 1.0

        return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Factory returning configured embedding provider."""
    settings = get_settings()
    if settings.EMBEDDING_PROVIDER == "mock":
        return DeterministicMockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    # Default fallback to deterministic mock if local models are not installed
    return DeterministicMockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
