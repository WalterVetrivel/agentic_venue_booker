from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.agent import tools
from app.models import (
    AcademicTerm,
    ClassSection,
    PastEvent,
    SlotOverride,
    TimetableSlot,
    User,
    Venue,
    VenueStatusPeriod,
)
from app.seed.demo_bookings import seed_bookings
from app.services import bookings as svc
from app.services import reports

MON = date(2026, 8, 3)  # a week inside the seeded 2026-27 ODD term
SAT = MON + timedelta(days=5)


def user(db, email):
    return db.scalar(select(User).where(User.email == email))


def venue(db, code):
    return db.scalar(select(Venue).where(Venue.code == code))


def request(code, day, start, end, title="Python workshop", count=30):
    return svc.BookingRequest(code, title, "Workshop", count, day, day, time(start), time(end))


@pytest.mark.parametrize(
    "email,label,codes",
    [
        ("dirim@kiot.ac.in", "All venues", {"CC5", "DSH", "MBASH"}),
        ("hod.cse@kiot.ac.in", "CSE venues", {"CC5", "COE1", "CSEPGSH"}),
        ("swvcse@kiot.ac.in", "Your venues (CC10)", {"CC10"}),
        ("sh.dblock@kiot.ac.in", "Your venues (DSH)", {"DSH"}),
    ],
)
def test_each_role_reports_on_its_own_venues(db, email, label, codes):
    scope = reports.scope_for(db, user(db, email))
    assert scope.label == label
    assert codes <= {v.code for v in scope.venues}
    if email == "hod.cse@kiot.ac.in":
        assert not {"DSH", "ESH", "MBASH"} & {v.code for v in scope.venues}
    if email.startswith(("swv", "sh.")):
        assert {v.code for v in scope.venues} == codes


def test_reports_need_a_reporting_role(client, login):
    assert client.get("/api/reports/summary").status_code == 401
    login("tkcse@kiot.ac.in")
    assert client.get("/api/reports/summary").status_code == 403
    assert client.get("/api/reports/events.csv").status_code == 403


def test_bad_periods_are_explained(client, login):
    login("dirim@kiot.ac.in")
    res = client.get("/api/reports/summary", params={"start": "2026-09-01", "end": "2026-08-01"})
    assert res.status_code == 422 and "before" in res.json()["detail"]
    res = client.get("/api/reports/summary", params={"start": "2024-01-01", "end": "2026-08-01"})
    assert res.status_code == 422 and "at most" in res.json()["detail"]
    assert client.get("/api/reports/nothing.csv").status_code == 404


@pytest.mark.writes_db
def test_utilisation_counts_classes_events_moves_and_closures(db):
    term = db.scalar(select(AcademicTerm))
    section = ClassSection(dept="CSE", year="III", section="Z")
    cc5, cc6 = venue(db, "CC5"), venue(db, "CC6")
    monday = TimetableSlot(
        term=term,
        section=section,
        venue=cc5,
        weekday=0,
        start=time(9),
        end=time(11),
        subject_code="CS1",
        subject_name="Lab",
    )
    # Two batches at once count once.
    monday_b = TimetableSlot(
        term=term,
        section=section,
        venue=cc5,
        weekday=0,
        start=time(10),
        end=time(11),
        subject_code="CS1",
        subject_name="Lab",
        batch="B2",
    )
    thursday = TimetableSlot(
        term=term,
        section=section,
        venue=cc5,
        weekday=3,
        start=time(14),
        end=time(16),
        subject_code="CS2",
        subject_name="Lab",
    )
    db.add_all([monday, monday_b, thursday])
    director = user(db, "dirim@kiot.ac.in")
    # A director's booking is confirmed at once; Tuesday 10-12 in CC5.
    tuesday = svc.submit(
        db, director, request("CC5", MON + timedelta(days=1), 10, 12), now=datetime(2026, 7, 20, 9)
    )
    assert tuesday.status == "confirmed"
    db.add(
        PastEvent(
            title="Alumni talk",
            series_key="alumni",
            event_type="Guest lecture",
            start_date=MON + timedelta(days=2),
            start_time=time(13),
            end_time=time(14),
            venues=[cc5],
        )
    )
    db.flush()
    # Thursday's class moved to CC6 for a confirmed booking.
    db.add(
        SlotOverride(
            slot_id=thursday.id,
            on_date=MON + timedelta(days=3),
            action="relocated",
            new_venue_id=cc6.id,
            booking_id=tuesday.id,
            active=True,
        )
    )
    db.add(
        VenueStatusPeriod(
            venue_id=cc5.id,
            status="maintenance",
            from_date=MON + timedelta(days=4),
            to_date=MON + timedelta(days=4),
        )
    )
    db.flush()

    scope = reports.Scope("test", [cc5, cc6])
    rows = {r["venue"]: r for r in reports.utilisation(db, scope, MON, SAT)["venues"]}
    # Mon-Fri 08:00-18:00 and Saturday 08:00-17:00 is 59 hours; Friday is closed for CC5.
    assert rows["CC5"]["open_hours"] == 49 and rows["CC5"]["closed_hours"] == 10
    assert rows["CC5"]["class_hours"] == 2  # Monday only: Thursday's class moved out
    assert rows["CC5"]["event_hours"] == 3  # the booking and the past event
    assert rows["CC5"]["used_pct"] == round(100 * 5 / 49, 1)
    assert rows["CC6"]["class_hours"] == 2 and rows["CC6"]["open_hours"] == 59


@pytest.mark.writes_db
def test_turnaround_waitlist_and_events(db):
    teacher, other = user(db, "tkcse@kiot.ac.in"), user(db, "swvcse@kiot.ac.in")
    incharge = user(db, "sh.dblock@kiot.ac.in")
    day = MON + timedelta(days=1)
    asked = datetime(2026, 7, 27, 9)
    first = svc.submit(db, teacher, request("DSH", day, 10, 12, count=100), now=asked)
    svc.approve(db, incharge, first, now=asked + timedelta(hours=5))
    late = svc.submit(
        db,
        other,
        request("DSH", day, 10, 12, count=80),
        join_waitlist=True,
        now=asked + timedelta(hours=6),
    )
    assert late.status == "waitlisted"
    svc.cancel(db, teacher, first, now=asked + timedelta(days=1))
    assert late.status == "offered"
    svc.accept_offer(db, other, late, now=asked + timedelta(days=1, hours=2))
    svc.reject(db, incharge, late, "Exam day", now=asked + timedelta(days=1, hours=12))
    db.flush()

    scope = reports.scope_for(db, incharge)
    turn = reports.turnaround(db, scope, date(2026, 7, 1), SAT)
    assert [r["hours"] for r in turn["rows"]] == [5.0, 10.0]  # the second counts from the accept
    assert turn["approved"] == 1 and turn["rejected"] == 1 and turn["median_hours"] == 7.5

    wait = reports.waitlist(db, scope, date(2026, 7, 1), SAT)
    assert wait["count"] == 1 and wait["converted"] == 1 and wait["conversion_pct"] == 100
    assert wait["rows"][0]["outcome"] == "Rejected"

    held = reports.events(db, scope, date(2026, 7, 1), SAT)
    assert held["count"] == 0  # neither booking went ahead
    assert [m["month"] for m in held["by_month"]] == ["2026-07", "2026-08"]


@pytest.mark.writes_db
def test_equipment_faults_and_csv(client, login, db):
    login("swvcse@kiot.ac.in")
    item = next(e for e in venue(db, "CC10").equipment if e.category == "hardware")
    res = client.patch(
        f"/api/equipment/{item.id}", json={"status": "faulty"}, headers={"X-Via": "agent"}
    )
    assert res.status_code == 200

    data = client.get("/api/reports/summary").json()
    assert data["scope"] == "Your venues (CC10)" and data["period_label"]
    kit = data["equipment"]
    assert kit["count"] == 1 and kit["rows"][0]["via"] == "Assistant"
    assert kit["out_of_service"][0]["item"] == item.name
    assert {r["venue"] for r in data["utilisation"]["venues"]} == {"CC10"}

    res = client.get("/api/reports/equipment.csv")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    lines = res.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "Date,Venue,Item,Status,Reported by,Via"
    assert ",CC10," in lines[1] and lines[1].endswith(",Assistant")


@pytest.mark.writes_db
def test_demo_seed_fills_every_report_and_runs_once(db):
    made = seed_bookings(db)
    assert made["demo_bookings"] > 30 and made["equipment_faults"] == 10
    assert seed_bookings(db) == {"demo_bookings": 0}
    today = date.today()
    data = reports.summary(db, user(db, "dirim@kiot.ac.in"), today - timedelta(days=150), today)
    assert data["utilisation"]["total"]["event_hours"] > 0
    assert data["events"]["count"] > 10 and data["turnaround"]["count"] > 10
    assert data["waitlist"]["count"] >= 3 and data["waitlist"]["converted"] >= 1
    assert data["equipment"]["count"] == 10 and data["equipment"]["out_of_service"]


@pytest.mark.writes_db
def test_assistant_report_tool_keeps_to_the_users_venues(db):
    seed_bookings(db)
    incharge = user(db, "sh.dblock@kiot.ac.in")
    data = tools.call(db, incharge, "utilisation_report", {}).data
    assert data["scope"] == "Your venues (DSH)" and [v["venue"] for v in data["venues"]] == ["DSH"]
    assert data["report_link"].startswith("/reports?start=")
    with pytest.raises(tools.ToolError, match="isn't one of the venues"):
        tools.call(db, incharge, "utilisation_report", {"venue": "CC5"})
    hod = tools.call(db, user(db, "hod.cse@kiot.ac.in"), "utilisation_report", {"venue": "cc5"})
    assert hod.data["scope"] == "CC5"
    with pytest.raises(tools.ToolError, match="access"):
        tools.call(db, user(db, "tkcse@kiot.ac.in"), "utilisation_report", {})
