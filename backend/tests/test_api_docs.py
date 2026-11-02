import re

from fastapi.testclient import TestClient

from app.main import create_app


def test_api_docs_work_offline():
    client = TestClient(create_app())
    for page in ("/docs", "/redoc"):
        html = client.get(page)
        assert html.status_code == 200
        urls = re.findall(r"""(?:src|href)=["']([^"']+)""", html.text)
        assert urls, page
        for url in urls:
            assert not url.startswith(("http:", "https:", "//")), f"{page} loads {url}"
            assert client.get(url).status_code == 200, url
