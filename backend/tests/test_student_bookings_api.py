import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.agent import tools
from app.models import ClassSection, OutboxEmail, User

pytestmark = pytest.mark.writes_db

DAY = (date.today() + timedelta(days=14)).isoformat()
while date.fromisoformat(DAY).weekday() == 6:
    DAY = (date.fromisoformat(DAY) + timedelta(days=1)).isoformat()


@pytest.fixture
def sections(session_factory):
    with session_factory() as db:
        rows = [
            ClassSection(dept="CSE", year="III", section="B", advisor="Mrs. E. Kiruthika, AP/CSE"),
            ClassSection(dept="IT", year="II", section="A", advisor="Mrs. S. Deepa, AP/CSE"),
        ]
        db.add_all(rows)
        db.commit()
        return {s.label: s.id for s in rows}


def guide_id(session_factory, email="bacse@kiot.ac.in") -> int:
    with session_factory() as db:
        return db.scalar(select(User.id).where(User.email == email))


def body(session_factory, sections, **kw):
    return {
        "venue": "CC5",
        "date_from": DAY,
        "start_time": "14:00",
        "end_time": "16:00",
        "reason": "Hackathon prep: smart parking app",
        "guide_id": guide_id(session_factory),
        "contact_email": "team@example.com",
        "students": [
            {"name": "Arun K", "section_id": sections["CSE III-B"], "register_no": "611223104001"},
            {"name": "Divya R", "section_id": sections["IT II-A"]},
        ],
    } | kw


def test_options_list_classes_guides_and_labs_only(client, sections):
    data = client.get("/api/student/options").json()
    assert {s["label"] for s in data["sections"]} == {"CSE III-B", "IT II-A"}
    names = {g["name"] for g in data["guides"]}
    assert "Mrs. B. Ashwini" in names and "Mr. T. Karthikeyan" in names
    assert "CSE Office Assistant" not in names and "Dr. V. Kumar" not in names
    types = {v["type"] for v in data["venues"]}
    assert types == {"lab", "coe"}
    assert data["max_students"] == 10 and data["email_domain"] is None


def test_check_a_slot(client):
    ok = client.post(
        "/api/student/check",
        json={"venue": "CC5", "date_from": DAY, "start_time": "14:00", "end_time": "16:00"},
    ).json()
    assert ok["ok"] and ok["problem"] is None
    hall = client.post(
        "/api/student/check",
        json={"venue": "CSEPGSH", "date_from": DAY, "start_time": "14:00", "end_time": "16:00"},
    )
    assert hall.status_code == 422


def test_submit_track_and_cancel(client, session_factory, sections, sent_mail):
    res = client.post("/api/student/bookings", json=body(session_factory, sections))
    assert res.status_code == 201, res.text
    data = res.json()
    code = data["tracking_code"]
    assert data["status"] == "pending_guide"
    assert data["contact_email"] == "te••@example.com"
    assert [s["state"] for s in data["steps"]] == ["current", "waiting", "waiting"]
    assert [s["class_label"] for s in data["students"]] == ["CSE III-B", "IT II-A"]
    # The confirmation email went out after the response, with the tracking number.
    (msg,) = sent_mail
    assert msg["To"] == "team@example.com" and code in msg["Subject"]
    assert f"/track?code={code}" in msg.get_content()

    tracked = client.get(f"/api/student/bookings/{code.lower()}").json()
    assert tracked["ref"] == data["ref"]
    assert client.get("/api/student/bookings/ST-AAAA-BBBB").status_code == 404

    cancelled = client.post(f"/api/student/bookings/{code}/cancel", json={"reason": "Sorted"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert not cancelled.json()["can_cancel"]
    assert "cancelled" in sent_mail[-1]["Subject"]


def test_submissions_are_rate_limited_by_ip(client, session_factory, sections, rate_limits):
    for i in range(5):
        day = (date.fromisoformat(DAY) + timedelta(days=i + 1)).isoformat()
        res = client.post(
            "/api/student/bookings",
            json=body(session_factory, sections, date_from=day, contact_email=f"t{i}@example.com"),
        )
        assert res.status_code in (201, 409, 422), res.text
    res = client.post("/api/student/bookings", json=body(session_factory, sections))
    assert res.status_code == 429


def test_guide_decides_each_student(client, session_factory, sections, login, sent_mail):
    code = client.post("/api/student/bookings", json=body(session_factory, sections)).json()[
        "tracking_code"
    ]
    login("bacse@kiot.ac.in")
    (item,) = client.get("/api/approvals").json()
    b = item["booking"]
    assert item["step"] == "guide" and b["kind"] == "student"
    assert b["guide"] == "Mrs. B. Ashwini" and b["tracking_code"] == code
    assert b["requester"] == "Student group (Arun K, Divya R)"
    assert [g["id"] for g in client.get("/api/bookings/guiding").json()] == [b["id"]]

    arun, divya = b["students"]
    res = client.post(
        f"/api/bookings/{b['id']}/students",
        json={
            "decisions": [
                {"student_id": arun["id"], "decision": "approved"},
                {"student_id": divya["id"], "decision": "rejected", "comment": "Other team"},
            ]
        },
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["status"] == "pending_incharge" and out["expected_count"] == 1
    assert [s["decision"] for s in out["students"]] == ["approved", "rejected"]
    assert "approved 1 of 2 students" in sent_mail[-1]["Subject"]

    tracked = client.get(f"/api/student/bookings/{code}").json()
    assert [s["state"] for s in tracked["steps"]] == ["done", "current", "waiting"]
    assert tracked["steps"][0]["approver"] == "Mrs. B. Ashwini"

    login("sdcse@kiot.ac.in")  # Divya's advisor (IT II-A)
    (note,) = client.get("/api/notifications").json()
    assert "not approved for Divya R (IT II-A)" in note["message"]


def test_someone_else_cannot_decide(client, session_factory, sections, login):
    client.post("/api/student/bookings", json=body(session_factory, sections))
    login("tkcse@kiot.ac.in")
    assert client.get("/api/approvals").json() == []
    booking_id = client.get("/api/bookings/guiding").json()
    assert booking_id == []


def test_email_settings(client, login):
    login("tkcse@kiot.ac.in")
    assert client.get("/api/settings/email").status_code == 403
    login("dirim@kiot.ac.in")
    assert client.get("/api/settings/email").json()["configured"] is False
    res = client.put(
        "/api/settings/email",
        json={
            "host": "smtp.gmail.com",
            "port": 587,
            "user": "venues@example.com",
            "password": "abcd efgh ijkl mnop",
        },
    )
    data = res.json()
    assert data["configured"] and data["password_set"] and data["password_source"] == "settings"
    assert data["from_addr"] == "venues@example.com"
    assert "abcd" not in res.text
    ok = client.post("/api/settings/email/test", json={"to": "me@example.com"}).json()
    assert ok == {"ok": True, "message": "Sent to me@example.com."}
    data = client.put("/api/settings/email", json={"host": "", "password": ""}).json()
    assert data["configured"] is False and data["password_set"] is False


def test_failed_sends_are_kept(session_factory, sent_mail):
    from app.services import mailer

    def broken(cfg, msg, email_id):
        raise OSError("connection refused")

    with session_factory() as db:
        mailer.queue(db, "x@example.com", "Hi", "Body")
        db.commit()
        mailer.set_transport(broken)
        assert mailer.send_queued(db) == 0
        email = db.scalars(select(OutboxEmail).order_by(OutboxEmail.id.desc())).first()
        assert email.status == "failed" and "refused" in email.error


# Assistant ------------------------------------------------------------------------------------


def test_assistant_drafts_a_student_request(db, sections):
    args = {
        "venue": "CC5",
        "date": DAY,
        "start": "14:00",
        "end": "16:00",
        "reason": "Mini project",
        "guide": "Ashwini",
        "students": [{"name": "Arun K", "class": "CSE III-B"}],
    }
    result = tools.call(db, None, "draft_student_booking", args)
    card = result.card
    assert card["kind"] == "draft" and card["href"].startswith("/book/student?")
    query = parse_qs(urlparse(card["href"]).query)
    assert query["venue"] == ["CC5"] and query["reason"] == ["Mini project"]
    (student,) = json.loads(query["students"][0])
    assert student["name"] == "Arun K" and student["section_id"] == sections["CSE III-B"]
    assert result.data["still_to_fill_in"] == ["a contact email"]
    assert "Faculty guide: Mrs. B. Ashwini" in card["lines"]

    with pytest.raises(tools.ToolError, match="labs and centres"):
        tools.call(db, None, "draft_student_booking", args | {"venue": "CSEPGSH"})
    with pytest.raises(tools.ToolError, match="Several faculty"):
        tools.call(db, None, "draft_student_booking", args | {"guide": "Saranya"})


def test_assistant_tracks_a_request(client, db, session_factory, sections):
    code = client.post("/api/student/bookings", json=body(session_factory, sections)).json()[
        "tracking_code"
    ]
    data = tools.call(db, None, "track_student_booking", {"tracking_number": code}).data
    assert data["status"] == "waiting for the faculty guide"
    assert data["faculty_guide"] == "Mrs. B. Ashwini"
    assert [s["guide_decision"] for s in data["students"]] == ["pending", "pending"]
    with pytest.raises(tools.ToolError, match="No request"):
        tools.call(db, None, "track_student_booking", {"tracking_number": "ST-AAAA-BBBB"})
