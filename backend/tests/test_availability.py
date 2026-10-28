from datetime import date, datetime, timedelta

import pytest

from app.services import availability
from app.services.venues import get_venue

# 2026-11-02 is a Monday, 2026-11-08 a Sunday.
MONDAY = date(2026, 11, 2)


def test_free_on_a_normal_weekday(db):
    cc1 = get_venue(db, "CC1")
    result = availability.check(db, cc1, datetime(2026, 11, 2, 10), datetime(2026, 11, 2, 12))
    assert result.free and result.conflicts == [] and result.warnings == []


def test_sunday_is_closed(db):
    cc1 = get_venue(db, "CC1")
    result = availability.check(db, cc1, datetime(2026, 11, 8, 10), datetime(2026, 11, 8, 12))
    assert not result.free
    assert result.conflicts[0].kind == "closed"


def test_outside_hours_is_a_warning_not_a_block(db):
    cc1 = get_venue(db, "CC1")
    result = availability.check(db, cc1, datetime(2026, 11, 2, 17), datetime(2026, 11, 2, 20))
    assert result.free
    assert [w.kind for w in result.warnings] == ["hours"]


@pytest.mark.parametrize("month,blocked", [(2, False), (3, True), (5, True), (7, True), (8, False)])
def test_a_block_admissions_season(db, month, blocked):
    ash = get_venue(db, "ASH")
    start = datetime(2027, month, 10, 10)
    result = availability.check(db, ash, start, start.replace(hour=12))
    assert result.free is not blocked


def test_wrapping_month_range():
    assert availability._in_month_range(12, 11, 2)
    assert availability._in_month_range(1, 11, 2)
    assert not availability._in_month_range(5, 11, 2)


def test_day_grid_endpoint(client):
    res = client.get("/api/availability", params={"date": MONDAY.isoformat()})
    body = res.json()
    assert res.status_code == 200
    assert body["open_from"] == "08:00:00" and body["open_to"] == "18:00:00"
    assert len(body["venues"]) == 23
    assert all(v["blocks"] == [] for v in body["venues"])


def test_grid_filters(client):
    body = client.get(
        "/api/availability",
        params={"date": MONDAY.isoformat(), "needs": "power bi", "min_capacity": 40},
    ).json()
    assert {v["code"] for v in body["venues"]} == {"CC5", "CC6", "CC7", "CC8"}


def test_check_endpoint(client):
    res = client.get(
        "/api/availability/check",
        params={"venue": "asH", "start": "2027-04-01T10:00", "end": "2027-04-01T12:00"},
    )
    body = res.json()
    assert body["venue"] == "ASH" and body["free"] is False
    assert "admission" in body["conflicts"][0]["label"].lower()


def test_check_rejects_bad_range(client):
    res = client.get(
        "/api/availability/check",
        params={"venue": "CC1", "start": "2026-11-02T12:00", "end": "2026-11-02T10:00"},
    )
    assert res.status_code == 422


def test_free_venues(client):
    halls = client.get(
        "/api/availability/free",
        params={
            "start": "2027-04-01T10:00",
            "end": "2027-04-01T12:00",
            "type": "seminar_hall",
            "min_capacity": 100,
        },
    ).json()
    assert {v["code"] for v in halls} == {"DSH", "ESH", "MBASH"}


def test_venue_range_endpoint(client):
    start = MONDAY
    end = MONDAY + timedelta(days=6)
    body = client.get(
        "/api/availability/venue/CC1", params={"start": start.isoformat(), "end": end.isoformat()}
    ).json()
    assert body["code"] == "CC1" and len(body["days"]) == 7
    sunday = body["days"][6]
    assert sunday["open_from"] is None and sunday["blocks"][0]["kind"] == "closed"
    assert body["days"][0]["open_from"] == "08:00:00"

    too_long = {"start": start.isoformat(), "end": (start + timedelta(days=60)).isoformat()}
    assert client.get("/api/availability/venue/CC1", params=too_long).status_code == 422
    backwards = {"start": end.isoformat(), "end": start.isoformat()}
    assert client.get("/api/availability/venue/CC1", params=backwards).status_code == 422
    assert client.get("/api/availability/venue/NOPE", params=backwards).status_code == 404
