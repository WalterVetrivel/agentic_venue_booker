import json
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.agent import tools
from app.models import User

DAY = "2027-02-09"  # a Tuesday, far enough ahead

PUBLIC = {
    "resolve_dates",
    "list_venues",
    "get_venue",
    "check_availability",
    "find_free_venues",
    "get_timetable",
    "track_student_booking",
}
VISITOR = {"draft_student_booking"}  # students only: staff use the staff form
BOOKER = {
    "search_past_events",
    "recommend_venues",
    "check_clashes",
    "draft_booking",
    "list_my_bookings",
    "propose_cancel",
}
APPROVER = {"list_pending_approvals", "assess_request", "propose_decision"}


def user(db, email):
    return db.scalar(select(User).where(User.email == email))


def names(u):
    return {t.name for t in tools.tools_for(u)}


def test_students_get_public_read_tools_and_the_student_draft():
    listed = tools.tools_for(None)
    assert {t.name for t in listed} == PUBLIC | VISITOR
    assert all(t.kind == "read" for t in listed if t.name not in VISITOR)


@pytest.mark.parametrize(
    "email,expected",
    [
        ("tkcse@kiot.ac.in", PUBLIC | BOOKER),
        (
            "swvcse@kiot.ac.in",
            PUBLIC | BOOKER | APPROVER | {"update_equipment_status", "utilisation_report"},
        ),
        (
            "hod.cse@kiot.ac.in",
            PUBLIC | BOOKER | APPROVER | {"review_timetable_upload", "utilisation_report"},
        ),
        ("cseoa@kiot.ac.in", PUBLIC | {"search_past_events", "review_timetable_upload"}),
        ("dirim@kiot.ac.in", set(tools.REGISTRY) - VISITOR),
    ],
)
def test_tools_follow_the_roles(db, email, expected):
    assert names(user(db, email)) == expected


def test_schemas_are_plain_for_small_models():
    for t in tools.REGISTRY.values():
        text = str(t.schema())
        assert "$defs" not in text and "anyOf" not in text, t.name
        assert all("title" not in p for p in t.schema()["properties"].values()), t.name
        assert t.schema()["type"] == "object"
        # Groq rejects "10:00" against format "time", so times are plain described strings.
        assert '"format"' not in json.dumps(t.schema()), t.name


def test_optional_times_keep_their_description():
    start = tools.REGISTRY["check_availability"].schema()["properties"]["start"]
    assert start["type"] == "string" and "Leave out" in start["description"]
    assert "HH:MM" in start["description"]


def test_unknown_class_lists_the_classes(db):
    with pytest.raises(tools.ToolError, match="There is no class"):
        tools.call(db, None, "get_timetable", {"section": "CSE III-B"})


def test_calling_a_tool_you_cannot_see_is_refused(db):
    args = {"venue": "CC5", "date": DAY, "start": "10:00", "end": "12:00"}
    with pytest.raises(tools.ToolError, match="log in"):
        tools.call(db, None, "draft_booking", args)
    with pytest.raises(tools.ToolError, match="access"):
        tools.call(db, user(db, "tkcse@kiot.ac.in"), "list_pending_approvals", {})
    with pytest.raises(tools.ToolError, match="no tool"):
        tools.call(db, None, "drop_tables", {})


def test_bad_arguments_are_explained(db):
    with pytest.raises(tools.ToolError, match="YYYY-MM-DD"):
        tools.call(db, None, "check_availability", {"venue": "CC5", "date": "someday"})
    with pytest.raises(tools.ToolError, match="No venue called"):
        tools.call(db, None, "check_availability", {"venue": "XYZ9", "date": DAY})


def test_check_availability_and_free_venues(db):
    day = tools.call(db, None, "check_availability", {"venue": "cc5", "date": DAY}).data
    assert day["venue"] == "CC5" and day["day"].startswith("Tuesday")
    assert all(b["kind"] == "class" for b in day["busy"])

    found = tools.call(
        db,
        None,
        "find_free_venues",
        {"date": DAY, "start": "16:30", "end": "17:30", "min_capacity": 100},
    ).data
    assert {v["code"] for v in found["free"]} == {"ASH", "DSH", "ESH", "MBASH"}


def test_venue_by_alias_and_timetable(db):
    v = tools.call(db, None, "get_venue", {"venue": "D Block Seminar Hall"}).data
    assert v["code"] == "DSH" and v["link"] == "/venues/DSH"
    with pytest.raises(tools.ToolError, match="section"):
        tools.call(db, None, "get_timetable", {})


def test_draft_booking_returns_a_card_and_books_nothing(db):
    from app.models import Booking

    before = db.scalar(select(Booking.id).order_by(Booking.id.desc()))
    args = {
        "venue": "DSH",
        "title": "Cloud computing workshop",
        "event_type": "Workshop",
        "expected_count": 120,
        "date": DAY,
        "start": "10:00",
        "end": "13:00",
        "requirements": "Two microphones",
    }
    result = tools.call(db, user(db, "tkcse@kiot.ac.in"), "draft_booking", args)
    card = result.card
    assert card["kind"] == "draft" and "Free" in card["lines"]
    query = parse_qs(urlparse(card["href"]).query)
    assert query["venue"] == ["DSH"] and query["count"] == ["120"]
    assert query["requirements"] == ["Two microphones"] and query["start"] == ["10:00"]
    assert db.scalar(select(Booking.id).order_by(Booking.id.desc())) == before


def test_draft_booking_opens_the_form_with_partial_details(db):
    args = {"venue": "DSH", "title": "Alumni talk", "date": DAY}
    result = tools.call(db, user(db, "tkcse@kiot.ac.in"), "draft_booking", args)
    query = parse_qs(urlparse(result.card["href"]).query)
    assert query == {"venue": ["DSH"], "title": ["Alumni talk"], "date": [DAY], "via": ["agent"]}
    assert result.data["outcome"] is None and result.card["button"] == "Finish on the form"
    assert result.data["still_to_fill_in"] == [
        "the start and end time",
        "the event type",
        "the expected number of people",
    ]


def test_draft_rejects_unknown_event_types(db):
    args = {
        "venue": "DSH",
        "title": "Something",
        "event_type": "Party",
        "expected_count": 10,
        "date": DAY,
        "start": "10:00",
        "end": "11:00",
    }
    with pytest.raises(tools.ToolError, match="event_type"):
        tools.call(db, user(db, "tkcse@kiot.ac.in"), "draft_booking", args)


def test_recommend_prefers_halls_for_talks(db):
    args = {
        "event_type": "Guest lecture",
        "expected_count": 70,
        "date": DAY,
        "start": "10:00",
        "end": "12:00",
    }
    top = tools.call(db, user(db, "tkcse@kiot.ac.in"), "recommend_venues", args).data["top"]
    assert top and top[0]["type"] == "seminar_hall"
    assert all(v["capacity"] >= 70 for v in top)


@pytest.mark.writes_db
def test_proposals_check_ownership(db):
    from datetime import date, time

    from app.services import bookings as svc

    teacher = user(db, "tkcse@kiot.ac.in")
    req = svc.BookingRequest(
        "DSH", "Seminar", "Seminar", 100, date(2027, 2, 9), date(2027, 2, 9), time(10), time(12)
    )
    b = svc.submit(db, teacher, req)
    db.commit()

    other = user(db, "swvcse@kiot.ac.in")
    with pytest.raises(tools.ToolError, match="Only the person"):
        tools.call(db, other, "propose_cancel", {"booking": b.ref})
    card = tools.call(db, teacher, "propose_cancel", {"booking": b.ref}).card
    assert card["action"] == {
        "method": "POST",
        "url": f"/api/bookings/{b.id}/cancel",
        "body": {"reason": None},
    }

    with pytest.raises(tools.ToolError, match="isn't waiting for your approval"):
        tools.call(db, other, "propose_decision", {"booking": b.ref, "decision": "approve"})
    incharge = user(db, "sh.dblock@kiot.ac.in")
    with pytest.raises(tools.ToolError, match="reason"):
        tools.call(db, incharge, "propose_decision", {"booking": b.ref, "decision": "reject"})
    card = tools.call(
        db, incharge, "propose_decision", {"booking": b.ref, "decision": "approve"}
    ).card
    assert card["action"]["url"] == f"/api/bookings/{b.id}/approve"

    brief = tools.call(db, incharge, "assess_request", {"booking": b.ref}).data
    assert brief["can_you_decide"] and brief["booking"]["ref"] == b.ref
    assert [x["ref"] for x in tools.call(db, incharge, "list_pending_approvals", {}).data] == [
        b.ref
    ]


def test_equipment_proposals_only_for_own_venues(db):
    incharge = user(db, "swvcse@kiot.ac.in")  # in-charge of CC10
    with pytest.raises(tools.ToolError, match="can't update"):
        tools.call(
            db,
            incharge,
            "update_equipment_status",
            {"venue": "CC5", "item": "projector", "status": "faulty"},
        )
    with pytest.raises(tools.ToolError, match="Which one"):
        tools.call(
            db,
            incharge,
            "update_equipment_status",
            {"venue": "CC10", "item": "o", "status": "faulty"},
        )
    result = tools.call(
        db,
        incharge,
        "update_equipment_status",
        {"venue": "CC10", "item": "smart board", "status": "faulty"},
    )
    assert result.card["action"]["method"] == "PATCH"
    assert result.card["action"]["body"] == {"status": "faulty"}
