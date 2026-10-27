import pytest

pytestmark = pytest.mark.writes_db

DIRECTOR = "dirim@kiot.ac.in"
CC10_INCHARGE = "swvcse@kiot.ac.in"  # Walter
OTHER_FACULTY = "prcse@kiot.ac.in"


def test_director_creates_venue(client, login):
    login(DIRECTOR)
    res = client.post(
        "/api/venues",
        json={
            "code": "cc13",
            "name": "Computer Centre 13",
            "type": "lab",
            "capacity": 40,
            "needs_hod_approval": True,
            "in_charge_email": "tkcse@kiot.ac.in",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["code"] == "CC13" and body["in_charge"]["email"] == "tkcse@kiot.ac.in"
    assert client.post("/api/venues", json={**res.json(), "code": "CC13"}).status_code in (
        409,
        422,
    )


@pytest.mark.parametrize("email", [CC10_INCHARGE, OTHER_FACULTY, "hod.cse@kiot.ac.in"])
def test_only_director_creates_venue(client, login, email):
    login(email)
    res = client.post(
        "/api/venues", json={"code": "X1", "name": "X", "type": "lab", "capacity": 10}
    )
    assert res.status_code == 403


def test_incharge_edits_own_venue_but_not_others(client, login):
    login(CC10_INCHARGE)
    assert client.get("/api/venues/CC10").json()["can_edit"] is True
    assert client.get("/api/venues/CC9").json()["can_edit"] is False
    assert client.patch("/api/venues/CC10", json={"notes": "New projector"}).status_code == 200
    assert client.patch("/api/venues/CC9", json={"notes": "x"}).status_code == 403


def test_incharge_cannot_change_capacity(client, login):
    login(CC10_INCHARGE)
    res = client.patch("/api/venues/CC10", json={"capacity": 80})
    assert res.status_code == 403


def test_director_reassigns_incharge(client, login):
    login(DIRECTOR)
    res = client.patch(
        "/api/venues/CC10", json={"in_charge_email": "tkcse@kiot.ac.in", "capacity": 45}
    )
    assert res.status_code == 200
    assert res.json()["in_charge"]["email"] == "tkcse@kiot.ac.in"
    assert res.json()["capacity"] == 45


def test_equipment_lifecycle(client, login):
    login(CC10_INCHARGE)
    item = client.post(
        "/api/venues/CC10/equipment", json={"name": "Kubernetes (minikube)", "category": "software"}
    ).json()
    assert item["status"] == "working"
    res = client.patch(f"/api/equipment/{item['id']}", json={"status": "faulty"})
    assert res.json()["status"] == "faulty"
    # Faulty equipment no longer satisfies a "needs" filter
    codes = [v["code"] for v in client.get("/api/venues", params={"needs": "minikube"}).json()]
    assert "CC10" not in codes
    assert client.delete(f"/api/equipment/{item['id']}").status_code == 204


def test_faculty_cannot_touch_equipment(client, login):
    login(OTHER_FACULTY)
    cc10 = client.get("/api/venues/CC10").json()
    item_id = cc10["equipment"][0]["id"]
    assert client.patch(f"/api/equipment/{item_id}", json={"status": "faulty"}).status_code == 403
    assert client.delete(f"/api/equipment/{item_id}").status_code == 403


def test_maintenance_blocks_availability(client, login):
    login(CC10_INCHARGE)
    res = client.post(
        "/api/venues/CC10/status-periods",
        json={
            "status": "maintenance",
            "from_date": "2026-11-02",
            "to_date": "2026-11-04",
            "reason": "AC repair",
        },
    )
    assert res.status_code == 201
    period_id = res.json()["id"]

    def is_free(day):
        return client.get(
            "/api/availability/check",
            params={"venue": "CC10", "start": f"{day}T10:00", "end": f"{day}T11:00"},
        ).json()["free"]

    assert not is_free("2026-11-03")
    assert is_free("2026-11-05")
    assert client.delete(f"/api/status-periods/{period_id}").status_code == 204
    assert is_free("2026-11-03")


def test_status_period_dates_validated(client, login):
    login(CC10_INCHARGE)
    res = client.post(
        "/api/venues/CC10/status-periods",
        json={"status": "maintenance", "from_date": "2026-11-05", "to_date": "2026-11-01"},
    )
    assert res.status_code == 422


def test_seasonal_rules_director_only(client, login):
    rule = {"start_month": 12, "end_month": 1, "kind": "soft_warning", "reason": "Year-end exams"}
    login(CC10_INCHARGE)
    assert client.post("/api/venues/CC10/seasonal-rules", json=rule).status_code == 403
    login(DIRECTOR)
    assert client.post("/api/venues/CC10/seasonal-rules", json=rule).status_code == 201
    check = client.get(
        "/api/availability/check",
        params={"venue": "CC10", "start": "2026-12-14T10:00", "end": "2026-12-14T11:00"},
    ).json()
    assert check["free"] and check["warnings"][0]["message"] == "Year-end exams"


def test_changes_are_audited(client, login, session_factory):
    from sqlalchemy import select

    from app.models import AuditLog

    login(CC10_INCHARGE)
    client.patch("/api/venues/CC10", json={"notes": "Audited"})
    with session_factory() as db:
        entry = db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert (entry.entity, entry.action) == ("venue", "update")


def test_users_list_is_director_only(client, login):
    login(CC10_INCHARGE)
    assert client.get("/api/users").status_code == 403
    login(DIRECTOR)
    assert len(client.get("/api/users").json()) == 51
