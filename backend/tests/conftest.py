import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.limits import Window
from app.db import Base, get_db, make_engine
from app.main import create_app
from app.seed.seed import seed_all, seed_documents
from app.services import mailer
from app.services.embeddings import reset_embedder, set_embedder


@pytest.fixture(autouse=True)
def sent_mail():
    """Tests never send real email (even with SMTP set in backend/.env): this records it."""
    sent = []

    def record(cfg, msg, email_id):
        sent.append(msg)
        return "sent"

    mailer.set_transport(record)
    Window.reset_all()
    yield sent
    mailer.set_transport(None)


@pytest.fixture(scope="session", autouse=True)
def keyword_search_only():
    """Tests never call Ollama; the embedding path is tested with a fake embedder."""
    set_embedder(None)
    yield
    reset_embedder()


def _seeded_factory(db_file):
    engine = make_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_all(db)
    return factory


@pytest.fixture(scope="session")
def shared_factory(tmp_path_factory):
    return _seeded_factory(tmp_path_factory.mktemp("db") / "test.db")


@pytest.fixture
def session_factory(request, shared_factory, tmp_path):
    """Read-only tests share one seeded DB; tests marked `writes_db` get a fresh one."""
    if request.node.get_closest_marker("writes_db"):
        return _seeded_factory(tmp_path / "test.db")
    return shared_factory


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture(scope="session")
def docs_factory(tmp_path_factory, keyword_search_only):
    """Read-only DB with every mock circular and report loaded (takes ~15 s, built once)."""
    factory = _seeded_factory(tmp_path_factory.mktemp("docs") / "docs.db")
    with factory() as db:
        seed_documents(db, embed=False)
    return factory


@pytest.fixture
def docs_db(docs_factory):
    with docs_factory() as session:
        yield session


def _client(factory):
    app = create_app()

    def _get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


@pytest.fixture
def client(session_factory):
    with _client(session_factory) as c:
        yield c


@pytest.fixture
def docs_client(docs_factory):
    with _client(docs_factory) as c:
        yield c


def _login_with(client):
    def _login(email: str, password: str = "password"):
        res = client.post("/api/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.text
        return res.json()

    return _login


@pytest.fixture
def login(client):
    return _login_with(client)


@pytest.fixture
def docs_login(docs_client):
    return _login_with(docs_client)


@pytest.fixture
def rate_limits(monkeypatch):
    """Our own visitor limits are off by default (RATE_LIMITS); tests of them turn them on."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limits", True)
