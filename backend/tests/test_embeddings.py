import httpx

from app.services import embeddings
from app.services.embeddings import OllamaEmbedder


def fake_post(response=None, error=None):
    calls = []

    def post(url, json, timeout):
        calls.append((url, timeout))
        if error:
            raise error
        return httpx.Response(response[0], json=response[1], request=httpx.Request("POST", url))

    return post, calls


def test_embeds_and_uses_a_short_timeout_for_queries(monkeypatch):
    post, calls = fake_post((200, {"embeddings": [[0.1, 0.2]]}))
    monkeypatch.setattr(httpx, "post", post)
    e = OllamaEmbedder("http://127.0.0.1:11434/", "nomic-embed-text")
    assert e.embed(["guest lecture"], query=True) == [[0.1, 0.2]]
    e.embed(["a circular"])
    assert calls[0] == ("http://127.0.0.1:11434/api/embed", embeddings.QUERY_TIMEOUT)
    assert calls[1][1] == embeddings.DOCUMENT_TIMEOUT


def test_says_why_and_backs_off_briefly(monkeypatch):
    post, calls = fake_post(error=httpx.ConnectError("refused"))
    monkeypatch.setattr(httpx, "post", post)
    e = OllamaEmbedder("http://localhost:11434", "nomic-embed-text")
    assert e.embed(["x"]) is None
    assert e.last_error == "Ollama isn't running at http://localhost:11434"
    assert e.embed(["x"]) is None and len(calls) == 1  # not retried straight away
    assert embeddings.RETRY_AFTER_SECONDS <= 60


def test_a_missing_model_says_how_to_install_it(monkeypatch):
    post, _ = fake_post((404, {"error": "model not found"}))
    monkeypatch.setattr(httpx, "post", post)
    e = OllamaEmbedder("http://localhost:11434", "nomic-embed-text")
    assert e.embed(["x"]) is None
    assert "ollama pull nomic-embed-text" in e.last_error


def test_follows_the_ollama_address_from_settings(monkeypatch):
    monkeypatch.setattr(embeddings, "_override", [])
    monkeypatch.setattr(embeddings, "_embedder", None)
    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "embeddings": "ollama",
                "ollama_base_url": "http://localhost:11434",
                "embed_model": "nomic-embed-text",
            },
        )(),
    )
    assert embeddings.get_embedder().base_url == "http://localhost:11434"
    assert embeddings.get_embedder("http://127.0.0.1:11434/").base_url == "http://127.0.0.1:11434"
