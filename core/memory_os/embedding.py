"""
Embedding interface + a dependency-free default (Plan Step 42): "Now
introduce embeddings. But do not make vector search mandatory."

Embedder is a Protocol, the same shape as LLMProvider: vector retrieval
must be exercisable without forcing a model download. HashingEmbedder is
a deterministic, stdlib-only bag-of-words hashing embedding -- NOT a
semantic embedding a real model would produce, since it has no notion of
synonyms or meaning, only shared vocabulary. It exists to make
VectorRetriever's plumbing (similarity, ranking, fusion) provable without
a model; swap in a real model-backed Embedder the same way ClaudeProvider
swaps in for LLMProvider.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Bag-of-words embedding via the hashing trick, L2-normalized."""

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"\w+", text.lower()):
            index = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Assumes both vectors are already L2-normalized (as HashingEmbedder's
    are), so the dot product alone equals cosine similarity."""
    return sum(x * y for x, y in zip(a, b))
