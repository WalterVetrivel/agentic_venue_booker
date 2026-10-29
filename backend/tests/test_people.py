import pytest
from sqlalchemy import select

from app.agent import tools
from app.config import get_settings
from app.models import TimetableSlot
from app.services.people import find_people, refers_to, staff
from app.services.timetables import ingest_and_commit


def names(db, text):
    return sorted(u.name for u in find_people(staff(db), text))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Walter sir", ["Mr. S. Walter Vetrivel"]),
        ("walter vetrivel sir", ["Mr. S. Walter Vetrivel"]),
        ("HOD sir", ["Mr. T. Karthikeyan"]),
        ("our HOD", ["Mr. T. Karthikeyan"]),
        ("EK ma'am", ["Mrs. E. Kiruthika"]),
        ("KS mam", ["Mrs. K. Saranya"]),
        ("ks ma’am", ["Mrs. K. Saranya"]),
        ("Kiruthika madam", ["Mrs. E. Kiruthika"]),
        ("Sowndarya ma'am", ["Mrs. S. Sowndarya", "Mrs. T. Sowndharya"]),
        ("T. Sowndarya", ["Mrs. T. Sowndharya"]),
        ("Saranya ma'am", ["Mrs. K. Saranya", "Mrs. M. Saranya", "Mrs. R. Saranya"]),
        ("Sathiya Priya ma'am", ["Mrs. V. SathiyaPriya"]),
        ("Ravi sir", ["Mr. K. Ravikumar"]),
        ("Karthikeyan sir", ["Mr. T. Karthikeyan"]),  # one person, though they have two logins
        ("Mr. G. Babu", ["Mr. G. Babu"]),
        ("Nobody sir", []),
    ],
)
def test_informal_references(db, text, expected):
    assert names(db, text) == expected


def test_a_timetable_spelling_still_matches():
    assert refers_to("Mrs. E. Kiruthika", "Mrs E Kiruthika, AP/CSE")
    assert not refers_to("Mrs. K. Saranya", "Mrs. R. Saranya")


def test_find_faculty_asks_when_several_match(db):
    data = tools.call(db, None, "find_faculty", {"who": "Sowndarya ma'am"}).data
    assert len(data["matches"]) == 2 and "ask which one" in data["note"]
    assert "email" not in data["matches"][0]  # visitors don't get addresses
    (hod,) = tools.call(db, None, "find_faculty", {"who": "HOD sir"}).data["matches"]
    assert "hod" in hod["roles"]


def test_student_guide_from_a_nickname(db):
    card = tools.call(
        db, None, "draft_student_booking", {"guide": "EK ma'am", "reason": "Project work"}
    ).card
    assert "Kiruthika" in str(card)
    result = tools.call(db, None, "draft_student_booking", {"guide": "Saranya ma'am"})
    assert "Mrs. K. Saranya" in str(result.data) and "Ask which one" in str(result.data)


@pytest.mark.writes_db
def test_timetable_of_a_faculty_member(db):
    ingest_and_commit(db, get_settings().mock_data_dir / "timetables" / "TT_CSE_II_YR_A.pdf")
    db.commit()
    teacher = db.scalar(select(TimetableSlot.faculty_name).where(TimetableSlot.faculty_name != ""))
    (person,) = find_people(staff(db), teacher)
    nickname = f"{person.initials} sir"
    data = tools.call(db, None, "get_timetable", {"faculty": nickname}).data
    assert data["for"] == person.name
    assert data["slots"] and all(s["faculty"] == teacher for s in data["slots"])
    with pytest.raises(tools.ToolError, match="Ask which one"):
        tools.call(db, None, "get_timetable", {"faculty": "Saranya ma'am"})
