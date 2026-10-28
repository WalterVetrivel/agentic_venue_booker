"""Tool arguments as different models write them (Groq usually ISO; small local models less so)."""

import json
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.agent import tools
from app.agent.formats import class_parts, to_date, to_int, to_list, to_time
from app.models import User


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-11-03", date(2026, 11, 3)),
        ("2026-11-03T10:00:00", date(2026, 11, 3)),
        ("2026/11/03", date(2026, 11, 3)),
        ("3/11/2026", date(2026, 11, 3)),  # day first, as written in India
        ("03-11-2026", date(2026, 11, 3)),
        ("3 Nov 2026", date(2026, 11, 3)),
        ("November 3rd 2026", date(2026, 11, 3)),
    ],
)
def test_dates(text, expected):
    assert to_date(text) == expected


def test_relative_dates_and_ranges():
    assert to_date("tomorrow") == date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="more than one day"):
        to_date("next week")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        to_date("someday")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("14:30", time(14, 30)),
        ("14:30:00", time(14, 30)),
        ("9:05", time(9, 5)),
        ("0930", time(9, 30)),
        ("10.30", time(10, 30)),
        ("10am", time(10)),
        ("2 pm", time(14)),
        ("2:30 p.m.", time(14, 30)),
        ("12 PM", time(12)),
        ("noon", time(12)),
        ("2", time(14)),  # a bare small hour is afternoon: venues open at 08:00
        ("16h", time(16)),
        ("2026-11-03T15:00:00", time(15)),
        (14, time(14)),
        (14.5, time(14, 30)),
    ],
)
def test_times(value, expected):
    assert to_time(value) == expected


def test_bad_times_are_explained():
    with pytest.raises(ValueError, match="HH:MM"):
        to_time("after lunch")
    with pytest.raises(ValueError, match="time of day"):
        to_time("25:00")


def test_numbers_and_lists():
    assert to_int("30 students") == 30 and to_int("1,200") == 1200 and to_int(40.0) == 40
    assert to_list("Power BI, Docker and Python") == ["Power BI", "Docker", "Python"]
    assert to_list(["x"]) == ["x"]


def test_schemas_describe_formats_without_enforcing_them():
    for t in tools.REGISTRY.values():
        text = json.dumps(t.schema())
        assert '"format"' not in text and '"pattern"' not in text, t.name
        assert '"hint"' not in text and '"ge"' not in text, t.name
    props = tools.REGISTRY["find_free_venues"].schema()["properties"]
    assert props["date"]["description"] == "YYYY-MM-DD, e.g. 2026-11-03"
    assert "HH:MM" in props["start"]["description"]
    assert (
        props["date_to"]["description"].startswith("Last day")
        and "YYYY" in props["date_to"]["description"]
    )


def test_a_small_model_style_call_works(db):
    loose = {
        "date": "9/2/2027",
        "start": "4:30 pm",
        "end": "5.30pm",
        "min_capacity": "100 people",
        "type": "Seminar Halls",
        "date_to": "",
        "needs": "null",
    }
    found = tools.call(db, None, "find_free_venues", loose).data
    assert found["time"] == "16:30–17:30" and found["days"] == ["Tuesday 09 Feb 2027"]
    assert {v["code"] for v in found["free"]} == {"ASH", "DSH", "ESH", "MBASH"}


def test_names_and_choices_are_read_loosely(db):
    teacher = db.scalar(select(User).where(User.email == "tkcse@kiot.ac.in"))
    args = {
        "venue": "DSH",
        "title": "Cloud talk",
        "event_type": "guest lecture",
        "expected_count": "120",
        "date": "2027-02-09",
        "start": "10:00",
        "end": "12:00",
    }
    card = tools.call(db, teacher, "draft_booking", args).card
    assert "type=Guest+lecture" in card["href"]
    incharge = db.scalar(select(User).where(User.email == "swvcse@kiot.ac.in"))
    result = tools.call(
        db,
        incharge,
        "update_equipment_status",
        {"venue": "CC10", "item": "smart board", "status": "Under Repair"},
    )
    assert result.card["action"]["body"] == {"status": "under_repair"}
    hits = tools.call(db, teacher, "search_past_events", {"query": "workshop", "year": 2024})
    assert hits is not None


@pytest.mark.parametrize(
    "text",
    ["CSE II-D", "II CSE D", "II CSE-D", "D-II-CSE", "2nd year CSE D", "cse 2d", "CSE IID", "II D"],
)
def test_classes_in_any_order(text):
    assert class_parts(text, ["AI&DS", "CSBS", "CSE", "IT"]) == ("CSE", "II", "D")


def test_class_departments_and_first_years():
    depts = ["AI&DS", "CSBS", "CSE", "IT"]
    assert class_parts("AIDS 3 B", depts) == ("AI&DS", "III", "B")
    assert class_parts("first year IT section A", depts) == ("IT", "I", "A")
    assert class_parts("CSBS IV-A", depts) == ("CSBS", "IV", "A")
    with pytest.raises(ValueError, match="Which section"):
        class_parts("CSE I-I", depts)
