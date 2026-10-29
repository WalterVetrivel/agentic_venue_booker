import httpx

from app.services import embeddings
from app.services.embeddings import OllamaEmbedder


def fake_post(response=None, error=None):
    calls = []

    def post(url, json, timeout):
        calls.append((url, timeout, json))
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
    assert calls[0][:2] == ("http://127.0.0.1:11434/api/embed", embeddings.QUERY_TIMEOUT)
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
                "embed_keep_alive": "8h",
            },
        )(),
    )
    assert embeddings.get_embedder().base_url == "http://localhost:11434"
    assert embeddings.get_embedder("http://127.0.0.1:11434/").base_url == "http://127.0.0.1:11434"
    assert embeddings.get_embedder().keep_alive == "8h"


def test_asks_ollama_to_keep_the_model_loaded(monkeypatch):
    post, calls = fake_post((200, {"embeddings": [[0.1]]}))
    monkeypatch.setattr(httpx, "post", post)
    OllamaEmbedder("http://localhost:11434", "nomic-embed-text", "8h").embed(["x"])
    OllamaEmbedder("http://localhost:11434", "nomic-embed-text", "-1").embed(["x"])
    OllamaEmbedder("http://localhost:11434", "nomic-embed-text", "").embed(["x"])
    assert [c[2].get("keep_alive") for c in calls] == ["8h", -1, None]
    assert "keep_alive" not in calls[2][2]  # empty: Ollama's own default


def test_warm_up_does_nothing_when_embeddings_are_off(monkeypatch):
    from app.services import documents

    def fail(*_):
        raise AssertionError("should not touch the database")

    monkeypatch.setattr(documents, "embedder_for", fail)
    documents.warm_up()  # tests run with embeddings off
