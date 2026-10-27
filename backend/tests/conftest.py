import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db, make_engine
from app.main import create_app
from app.seed.seed import seed_all


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


@pytest.fixture
def client(session_factory):
    app = create_app()

    def _get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client):
    def _login(email: str, password: str = "password"):
        res = client.post("/api/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.text
        return res.json()

    return _login
