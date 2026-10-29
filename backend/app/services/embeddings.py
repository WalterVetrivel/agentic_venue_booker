"""Optional text embeddings for document search.

nomic-embed-text runs in Ollama on the CPU, so it works on the department's laptops. Search
never depends on it: when Ollama is off or unreachable, documents are found by keywords alone.
"""

import logging
import math
import re
import struct
import time
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
# After a failure, search uses keywords alone for this long before trying Ollama again. Short,
# so that starting Ollama after the backend takes effect within a minute.
RETRY_AFTER_SECONDS = 60
# The first call loads the model (several seconds on a laptop CPU) and a batch of documents
# takes a while to embed; a search query is one short text, and someone is waiting for it.
DOCUMENT_TIMEOUT = 120.0
QUERY_TIMEOUT = 20.0


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]] | None: ...


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, keep_alive: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keep_alive = _keep_alive(keep_alive)
        self._down_until = 0.0
        self.last_error: str | None = None

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]] | None:
        """None when Ollama can't be reached; we then wait a while before trying again."""
        if not texts or time.monotonic() < self._down_until:
            return None
        # nomic-embed-text is trained with these task prefixes.
        prefix = "search_query: " if query else "search_document: "
        try:
            res = httpx.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": [prefix + t for t in texts],
                    **({"keep_alive": self.keep_alive} if self.keep_alive is not None else {}),
                },
                timeout=QUERY_TIMEOUT if query else DOCUMENT_TIMEOUT,
            )
            if res.status_code == 404:
                raise LookupError(f"model {self.model!r} isn't installed: ollama pull {self.model}")
            res.raise_for_status()
            vectors = res.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError, LookupError) as exc:
            self.last_error = _describe(exc, self.base_url)
            log.warning("Embeddings unavailable (%s); using keyword search only", self.last_error)
            self._down_until = time.monotonic() + RETRY_AFTER_SECONDS
            return None
        self.last_error = None
        return vectors


def _keep_alive(value: str | None) -> str | int | None:
    """Ollama takes a duration ("8h") or a number of seconds (-1 keeps the model loaded)."""
    value = (value or "").strip()
    if not value:
        return None
    return int(value) if re.fullmatch(r"-?\d+", value) else value


def _describe(exc: Exception, base_url: str) -> str:
    if isinstance(exc, httpx.ConnectError):
        return f"Ollama isn't running at {base_url}"
    if isinstance(exc, httpx.TimeoutException):
        return f"Ollama at {base_url} took too long to answer"
    return str(exc) or type(exc).__name__


_embedder: Embedder | None = None
_override: list[Embedder | None] = []  # set by tests


def get_embedder(base_url: str | None = None) -> Embedder | None:
    """The embedder, or None when embeddings are off. `base_url` is the Ollama address from the
    Settings page, which wins over OLLAMA_BASE_URL in backend/.env (the chat uses it too)."""
    global _embedder
    if _override:
        return _override[0]
    settings = get_settings()
    if settings.embeddings.lower() != "ollama":
        return None
    url = (base_url or settings.ollama_base_url).rstrip("/")
    if not isinstance(_embedder, OllamaEmbedder) or _embedder.base_url != url:
        _embedder = OllamaEmbedder(url, settings.embed_model, settings.embed_keep_alive)
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
