import pytest

pytestmark = pytest.mark.writes_db

DAY = "2027-02-09"
BODY = {
    "venue": "DSH",
    "title": "Cloud computing workshop",
    "event_type": "Workshop",
    "expected_count": 120,
    "date_from": DAY,
    "start_time": "10:00",
    "end_time": "13:00",
}


def test_save_a_partial_draft_and_finish_it_later(client, login):
    login("tkcse@kiot.ac.in")
    res = client.post("/api/booking-drafts", json={"title": "Alumni talk"})
    assert res.status_code == 201, res.text
    draft = res.json()
    assert draft["outcome"] == "incomplete" and draft["venue"] is None

    res = client.put(f"/api/booking-drafts/{draft['id']}", json=BODY)
    assert res.json()["outcome"] == "free" and res.json()["venue_name"] == "D Block Seminar Hall"
    assert [d["id"] for d in client.get("/api/booking-drafts").json()] == [draft["id"]]

    # Submitting it books the venue and removes the draft.
    res = client.post("/api/bookings", json=BODY | {"draft_id": draft["id"]})
    assert res.status_code == 201, res.text
    assert client.get("/api/booking-drafts").json() == []


def test_drafts_are_private(client, login):
    login("tkcse@kiot.ac.in")
    draft = client.post("/api/booking-drafts", json=BODY).json()
    login("gbcse@kiot.ac.in")
    assert client.get("/api/booking-drafts").json() == []
    assert client.get(f"/api/booking-drafts/{draft['id']}").status_code == 404
    assert client.delete(f"/api/booking-drafts/{draft['id']}").status_code == 404
    # A different person's draft id in a booking doesn't delete it.
    client.post("/api/bookings", json=BODY | {"draft_id": draft["id"]})
    login("tkcse@kiot.ac.in")
    assert len(client.get("/api/booking-drafts").json()) == 1
    assert client.delete(f"/api/booking-drafts/{draft['id']}").status_code == 204
    assert client.get("/api/booking-drafts").json() == []


def test_a_draft_whose_slot_is_taken_can_only_join_the_waitlist(client, login):
    login("tkcse@kiot.ac.in")
    draft = client.post("/api/booking-drafts", json=BODY).json()
    assert draft["outcome"] == "free"

    login("gbcse@kiot.ac.in")
    other = BODY | {"title": "Placement talk", "start_time": "11:00", "end_time": "12:00"}
    assert client.post("/api/bookings", json=other).status_code == 201

    login("tkcse@kiot.ac.in")
    (now,) = client.get("/api/booking-drafts").json()
    assert now["outcome"] == "waitlist" and now["taken_since_saved"]
    (note,) = [n for n in client.get("/api/notifications").json() if n["kind"] == "draft_taken"]
    assert "can now only join the waitlist" in note["message"]
    assert note["link"] == f"/book?draft={draft['id']}"

    res = client.post("/api/bookings", json=BODY | {"draft_id": draft["id"]})
    assert res.status_code == 409 and "waitlist" in res.json()["detail"]
    assert len(client.get("/api/booking-drafts").json()) == 1  # kept when submitting fails
    res = client.post("/api/bookings", json=BODY | {"draft_id": draft["id"], "join_waitlist": True})
    assert res.json()["status"] == "waitlisted"
    assert client.get("/api/booking-drafts").json() == []


def test_students_cannot_save_drafts(client):
    assert client.post("/api/booking-drafts", json=BODY).status_code == 401
