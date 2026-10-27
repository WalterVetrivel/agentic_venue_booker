import pytest

from app.config import get_settings

MOCK = get_settings().mock_data_dir


def pdf(prefix: str):
    folder = MOCK / ("reports" if prefix.startswith("REPORT") else "circulars")
    (path,) = [p for p in folder.glob("*.pdf") if p.name.startswith(prefix)]
    return path


def upload(client, *prefixes: str):
    files = [("files", (pdf(p).name, pdf(p).read_bytes(), "application/pdf")) for p in prefixes]
    return client.post("/api/documents", files=files)


# Read-only, over the full corpus ------------------------------------------------------------------


def test_documents_need_a_login(docs_client):
    assert docs_client.get("/api/documents").status_code == 401
    assert docs_client.get("/api/search", params={"q": "hackathon"}).status_code == 401


def test_search_and_browse(docs_client, docs_login):
    docs_login("tkcse@kiot.ac.in")
    res = docs_client.get("/api/search", params={"q": "hackathon in the COE labs"}).json()
    assert res["mode"] == "keywords"
    top = res["hits"][0]
    assert "Hackathon" in top["event"]["title"] and "COE1" in top["event"]["venues"]
    assert top["document"]["file_url"].endswith("/file")

    pdf_res = docs_client.get(top["document"]["file_url"])
    assert pdf_res.status_code == 200 and pdf_res.content.startswith(b"%PDF")

    facets = docs_client.get("/api/events/facets").json()
    assert facets["events"] == 155 and facets["needs_review"] == 5
    assert facets["embeddings"] == "off" and "2025-26" in facets["years"]

    events = docs_client.get(
        "/api/events", params={"venue": "COE1", "event_type": "Hackathon"}
    ).json()
    assert [e["start_date"][:4] for e in events] == ["2026", "2025", "2024", "2023"]
    assert events[0]["circular"] and events[0]["report"]
    review = docs_client.get("/api/events", params={"needs_review": True}).json()
    assert len(review) == 5 and all(e["problems"] for e in review)
    year = docs_client.get("/api/events", params={"year": "2024-25", "q": "hackathon"}).json()
    assert [e["start_date"] for e in year] == ["2024-09-13"]


def test_recurring_warning_reaches_the_booking_form(docs_client, docs_login):
    docs_login("tkcse@kiot.ac.in")
    body = {
        "venue": "CC1",
        "title": "Python bootcamp",
        "event_type": "Workshop",
        "expected_count": 40,
        "date_from": "2026-11-16",
        "start_time": "10:00",
        "end_time": "12:00",
    }
    check = docs_client.post("/api/bookings/check", json=body).json()
    assert any("Model Practical" in w["message"] for w in check["warnings"])
    assert check["alternatives"]


# Writes -----------------------------------------------------------------------------------------


@pytest.mark.writes_db
def test_upload_correct_and_delete(client, login, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    login("tkcse@kiot.ac.in")
    assert upload(client, "REPORT EV0115 ").status_code == 403  # faculty can't upload

    login("cseoa@kiot.ac.in")
    res = upload(client, "REPORT EV0115 ", "CIRCULAR NO.003 (IT 2025-26)")
    assert res.status_code == 201, res.text
    report, circular = res.json()
    assert report["document"]["problems"] and report["document"]["event"]["needs_review"]
    assert circular["document"]["ref_no"] == "KIOT/IT/2025-26/003"
    bad = client.post(
        "/api/documents", files=[("files", ("notes.txt", b"hello", "text/plain"))]
    ).json()
    assert bad[0]["error"] == "Not a PDF"

    again = upload(client, "CIRCULAR NO.003 (IT 2025-26)").json()[0]
    assert again["replaced"]
    assert len(client.get("/api/documents").json()) == 2

    event_id = report["document"]["event"]["id"]
    fix = {
        "title": "Guest Lecture on Malware analysis basics",
        "event_type": "Guest lecture",
        "venue_codes": ["DSH"],
        "start_date": "2025-09-15",
        "start_time": "13:25",
        "end_time": "15:55",
    }
    assert (
        client.put(f"/api/events/{event_id}", json={**fix, "venue_codes": ["NOPE"]}).status_code
        == 422
    )
    fixed = client.put(f"/api/events/{event_id}", json=fix).json()
    assert fixed["edited"] and not fixed["needs_review"] and fixed["end_time"] == "15:55:00"
    hits = client.get("/api/search", params={"q": "malware"}).json()["hits"]
    assert hits[0]["event"]["id"] == event_id

    doc_id = report["document"]["id"]
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404
    assert client.get(f"/api/events/{event_id}").status_code == 404
    assert len(list(tmp_path.glob("documents/*.pdf"))) == 1  # the deleted PDF is gone too
