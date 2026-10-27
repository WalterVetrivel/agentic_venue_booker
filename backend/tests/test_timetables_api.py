from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import TimetableSlot
from app.services import availability
from app.services.venues import get_venue

pytestmark = pytest.mark.writes_db
FOLDER = get_settings().mock_data_dir / "timetables"
# CSE II-A has DBMS (B1) in CC1 and DS (B2) in CC2 on Mondays 09:00-10:40.
MONDAY = "2026-11-02"


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)


def upload(client, name):
    with (FOLDER / name).open("rb") as f:
        return client.post("/api/timetables/uploads", files={"file": (name, f, "application/pdf")})


def test_oa_uploads_reviews_and_commits(client, login, session_factory):
    login("cseoa@kiot.ac.in")
    res = upload(client, "TT_CSE_II_YR_A.pdf")
    assert res.status_code == 201, res.text
    up = res.json()
    assert up["header"]["section"] == "A" and up["header"]["valid_to"] == "2026-11-30"
    assert up["can_commit"] and len(up["slots"]) == 5
    assert all(s["venue_code"] in {"CC1", "CC2"} for s in up["slots"])

    res = client.post(f"/api/timetables/uploads/{up['id']}/commit")
    assert res.status_code == 200 and res.json()["status"] == "committed"

    check = client.get(
        "/api/availability/check",
        params={"venue": "CC1", "start": f"{MONDAY}T09:30", "end": f"{MONDAY}T10:00"},
    ).json()
    assert check["free"] is False and check["needs_displacement"] is True
    assert check["classes"][0]["label"] == "CSE II-A · DBMS (B1)"

    sections = client.get("/api/timetables/sections").json()
    assert [(s["label"], s["lab_slots"]) for s in sections] == [("CSE II-A", 5)]


def test_reupload_replaces_the_section(client, login, session_factory):
    login("cseoa@kiot.ac.in")
    for _ in range(2):
        up = upload(client, "TT_CSE_II_YR_A.pdf").json()
        assert client.post(f"/api/timetables/uploads/{up['id']}/commit").status_code == 200
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(TimetableSlot)) == 5


def test_clash_with_another_section_blocks_commit(client, login):
    login("cseoa@kiot.ac.in")
    first = upload(client, "TT_CSE_II_YR_A.pdf").json()
    client.post(f"/api/timetables/uploads/{first['id']}/commit")

    # CSE II-B, edited so its Tuesday DS lab lands on CSE II-A's Monday CC1 slot.
    second = upload(client, "TT_CSE_II_YR_B.pdf").json()
    slots = second["slots"]
    slots[0].update(weekday="Mon", start="09:00", end="10:40", venue="CC1")
    res = client.put(
        f"/api/timetables/uploads/{second['id']}", json={"header": second["header"], "slots": slots}
    )
    body = res.json()
    assert body["can_commit"] is False
    assert "already used by CSE II-A" in body["slots"][0]["issues"][0]
    assert client.post(f"/api/timetables/uploads/{second['id']}/commit").status_code == 409


def test_unknown_venue_is_flagged(client, login):
    login("cseoa@kiot.ac.in")
    up = upload(client, "TT_CSE_II_YR_A.pdf").json()
    up["slots"][0]["venue"] = "CC99"
    body = client.put(
        f"/api/timetables/uploads/{up['id']}", json={"header": up["header"], "slots": up["slots"]}
    ).json()
    assert body["slots"][0]["issues"] == ["Unknown venue “CC99”."]
    assert not body["can_commit"]


def test_discard_upload(client, login):
    login("cseoa@kiot.ac.in")
    up = upload(client, "TT_CSE_II_YR_A.pdf").json()
    assert client.delete(f"/api/timetables/uploads/{up['id']}").status_code == 204
    assert client.get(f"/api/timetables/uploads/{up['id']}").status_code == 404


@pytest.mark.parametrize("email", ["swvcse@kiot.ac.in", "prcse@kiot.ac.in"])
def test_faculty_cannot_upload(client, login, email):
    login(email)
    assert upload(client, "TT_CSE_II_YR_A.pdf").status_code == 403


def test_rejects_non_pdf(client, login):
    login("cseoa@kiot.ac.in")
    res = client.post("/api/timetables/uploads", files={"file": ("tt.txt", b"hello", "text/plain")})
    assert res.status_code == 422


def test_rejects_corrupt_pdf(client, login):
    login("cseoa@kiot.ac.in")
    res = client.post(
        "/api/timetables/uploads",
        files={"file": ("tt.pdf", b"not really a pdf", "application/pdf")},
    )
    assert res.status_code == 422


def test_all_mock_timetables_seed_without_clashes(session_factory):
    from app.seed.seed import seed_timetables

    with session_factory() as db:
        assert seed_timetables(db) == 124
        cc1 = get_venue(db, "CC1")
        # Classes only apply inside the term (1 Jul - 30 Nov 2026)
        in_term = availability.check(db, cc1, datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10))
        after = availability.check(db, cc1, datetime(2026, 12, 7, 9), datetime(2026, 12, 7, 10))
        assert in_term.classes and not after.classes


def test_free_venues_exclude_classes(client, session_factory):
    from app.seed.seed import seed_timetables

    with session_factory() as db:
        seed_timetables(db)
    free = client.get(
        "/api/availability/free",
        params={"start": f"{MONDAY}T09:00", "end": f"{MONDAY}T10:40", "type": "lab"},
    ).json()
    codes = {v["code"] for v in free}
    assert "CC1" not in codes and "PGLAB" in codes


def test_reuploading_a_class_replaces_the_pending_upload(client, login):
    login("cseoa@kiot.ac.in")
    first = upload(client, "TT_CSE_II_YR_A.pdf").json()["id"]
    second = upload(client, "TT_CSE_II_YR_A.pdf").json()["id"]
    pending = [
        u["id"] for u in client.get("/api/timetables/uploads").json() if u["status"] == "parsed"
    ]
    assert pending == [second]
    assert client.get(f"/api/timetables/uploads/{first}").status_code == 404
