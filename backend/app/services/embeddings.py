"""Optional text embeddings for document search.

nomic-embed-text runs in Ollama on the CPU, so it works on the department's laptops. Search
never depends on it: when Ollama is off or unreachable, documents are found by keywords alone.
"""

import logging
import math
import struct
import time
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
RETRY_AFTER_SECONDS = 300


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]] | None: ...


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._down_until = 0.0

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]] | None:
        """None when Ollama can't be reached; we then wait a while before trying again."""
        if not texts or time.monotonic() < self._down_until:
            return None
        # nomic-embed-text is trained with these task prefixes.
        prefix = "search_query: " if query else "search_document: "
        try:
            res = httpx.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": [prefix + t for t in texts]},
                timeout=self.timeout,
            )
            res.raise_for_status()
            return res.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("Embeddings unavailable (%s); using keyword search only", exc)
            self._down_until = time.monotonic() + RETRY_AFTER_SECONDS
            return None


_embedder: Embedder | None = None
_override: list[Embedder | None] = []  # set by tests


def get_embedder() -> Embedder | None:
    global _embedder
    if _override:
        return _override[0]
    settings = get_settings()
    if settings.embeddings.lower() != "ollama":
        return None
    if _embedder is None:
        _embedder = OllamaEmbedder(settings.ollama_base_url, settings.embed_model)
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """For tests: swap in a fake embedder (or None to force keyword search)."""
    _override[:] = [embedder]


def reset_embedder() -> None:
    _override.clear()


def pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
