import pytest

pytestmark = pytest.mark.writes_db

# Far enough ahead that the API's "date has passed" check never trips.
DAY = "2027-02-09"
BODY = {
    "venue": "DSH",
    "title": "Cloud computing workshop",
    "event_type": "Workshop",
    "expected_count": 120,
    "date_from": DAY,
    "start_time": "10:00",
    "end_time": "13:00",
    "requirements": "Two cordless microphones",
}


def test_students_cannot_book(client):
    assert client.post("/api/bookings", json=BODY).status_code == 401
    assert client.get("/api/bookings/event-types").status_code == 200


def test_book_approve_and_see_it_on_the_grid(client, login):
    login("tkcse@kiot.ac.in")
    check = client.post("/api/bookings/check", json=BODY).json()
    assert check["outcome"] == "free" and check["days"] == [DAY]

    res = client.post("/api/bookings", json=BODY)
    assert res.status_code == 201, res.text
    b = res.json()
    assert b["status"] == "pending_incharge" and b["steps"] == ["incharge"]
    assert b["can_cancel"] and b["can_reschedule"] and not b["can_approve"]
    assert [m["ref"] for m in client.get("/api/bookings/mine").json()] == [b["ref"]]

    login("gbcse@kiot.ac.in")  # in-charge of another venue
    assert client.get("/api/approvals").json() == []
    assert client.post(f"/api/bookings/{b['id']}/approve", json={}).status_code == 403

    login("sh.dblock@kiot.ac.in")
    (item,) = client.get("/api/approvals").json()
    assert item["step"] == "incharge" and item["booking"]["can_approve"]
    assert any("Capacity fits" in n for n in item["notes"])
    notes = client.get("/api/notifications").json()
    assert notes[0]["kind"] == "approval_needed" and notes[0]["read_at"] is None
    assert client.post("/api/notifications/read", json={}).status_code == 204
    assert client.get("/api/notifications").json()[0]["read_at"] is not None

    assert client.get("/api/approvals/history").json() == []
    res = client.post(f"/api/bookings/{b['id']}/approve", json={"comment": "OK"})
    assert res.json()["status"] == "confirmed"
    (decided,) = client.get("/api/approvals/history").json()
    assert decided["decision"] == "approved" and decided["comment"] == "OK"
    assert decided["booking"]["ref"] == b["ref"] and decided["step"] == "incharge"

    grid = client.get("/api/availability", params={"date": DAY, "type": "seminar_hall"}).json()
    dsh = next(v for v in grid["venues"] if v["code"] == "DSH")
    assert [(blk["kind"], blk["label"]) for blk in dsh["blocks"]] == [
        ("booking", "Cloud computing workshop")
    ]


def test_clash_offers_waitlist_and_cancel_promotes(client, login):
    login("tkcse@kiot.ac.in")
    first = client.post("/api/bookings", json=BODY).json()

    login("swvcse@kiot.ac.in")
    check = client.post("/api/bookings/check", json=BODY).json()
    assert check["outcome"] == "waitlist" and check["alternatives"]
    res = client.post("/api/bookings", json=BODY)
    assert res.status_code == 409 and "waitlist" in res.json()["detail"]
    waiting = client.post("/api/bookings", json={**BODY, "join_waitlist": True}).json()
    assert waiting["status"] == "waitlisted" and waiting["waitlist_position"] == 1

    login("tkcse@kiot.ac.in")
    res = client.post(f"/api/bookings/{first['id']}/cancel", json={"reason": "Postponed"})
    assert res.json()["status"] == "cancelled"

    login("swvcse@kiot.ac.in")
    offered = client.get(f"/api/bookings/{waiting['id']}").json()
    assert offered["status"] == "offered" and offered["offer_expires_at"]
    res = client.post(f"/api/bookings/{waiting['id']}/accept-offer")
    assert res.json()["status"] == "pending_incharge"


def test_reject_needs_a_comment(client, login):
    login("tkcse@kiot.ac.in")
    b = client.post("/api/bookings", json=BODY).json()
    login("sh.dblock@kiot.ac.in")
    assert client.post(f"/api/bookings/{b['id']}/reject", json={}).status_code == 422
    res = client.post(f"/api/bookings/{b['id']}/reject", json={"comment": "Exams that day"})
    assert res.json()["status"] == "rejected"
    assert res.json()["approvals"][0]["comment"] == "Exams that day"


def test_bad_requests_are_explained(client, login):
    login("tkcse@kiot.ac.in")
    res = client.post("/api/bookings", json={**BODY, "venue": "NOPE"})
    assert res.status_code == 404
    res = client.post("/api/bookings", json={**BODY, "date_from": "2027-02-07"})  # Sunday
    assert res.status_code == 409 and "Sundays" in res.json()["detail"]
    res = client.post("/api/bookings", json={**BODY, "venue": "COE1", "expected_count": 50})
    assert res.status_code == 422 and "seats 30" in res.json()["detail"]
