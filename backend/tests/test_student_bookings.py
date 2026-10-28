from datetime import date, datetime, time

import pytest
from sqlalchemy import select

from app.models import Booking, ClassSection, Notification, OutboxEmail, User
from app.services import bookings as svc
from app.services import student_bookings as student_svc
from app.services.people import faculty_matching, name_key

pytestmark = pytest.mark.writes_db

NOW = datetime(2026, 10, 27, 9, 0)
TUESDAY = date(2026, 11, 3)
GUIDE = "bacse@kiot.ac.in"  # Mrs. B. Ashwini
INCHARGE = "mkscse@kiot.ac.in"  # CC5
HOD = "hod.cse@kiot.ac.in"


def user(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def section(db, dept: str, year: str, sec: str, advisor: str) -> ClassSection:
    row = ClassSection(dept=dept, year=year, section=sec, advisor=advisor)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def classes(db):
    """Two classes whose advisors (as the timetables print them) have logins."""
    return {
        "III-B": section(db, "CSE", "III", "B", "Mrs. E. Kiruthika, AP/CSE"),
        "II-A": section(db, "CSE", "II", "A", "Mrs. V. Anitha, AP/CSE"),
    }


def request(db, classes, venue="CC5", guide=GUIDE, students=None, **kw):
    students = (
        students
        if students is not None
        else [
            student_svc.StudentIn("Arun K", classes["III-B"].id, "611223104001"),
            student_svc.StudentIn("Bala S", classes["III-B"].id),
            student_svc.StudentIn("Charu M", classes["II-A"].id),
        ]
    )
    return student_svc.StudentRequest(
        venue_code=venue,
        date_from=kw.pop("day", TUESDAY),
        date_to=kw.pop("day_to", TUESDAY),
        start_time=time(14, 0),
        end_time=time(16, 0),
        reason=kw.pop("reason", "Mini project: attendance app"),
        guide_id=user(db, guide).id,
        contact_email=kw.pop("email", "arun@example.com"),
        students=students,
        **kw,
    )


def submit(db, classes, **kw) -> Booking:
    b = student_svc.submit_student(db, request(db, classes, **kw), now=NOW)
    db.commit()
    return b


def inbox(db, email: str) -> list[Notification]:
    u = user(db, email)
    return list(db.scalars(select(Notification).where(Notification.user_id == u.id)))


def emails(db, b: Booking) -> list[str]:
    rows = db.scalars(select(OutboxEmail).where(OutboxEmail.booking_id == b.id))
    return [e.subject for e in rows]


def by_name(b: Booking) -> dict:
    return {s.name: s for s in b.students}


# Submitting -------------------------------------------------------------------------------------


def test_a_request_waits_for_the_guide_and_gets_a_tracking_number(db, classes):
    b = submit(db, classes)
    assert b.kind == "student" and b.requester is None
    assert b.status == "pending_guide"
    assert svc.steps_for(b) == ["guide", "incharge", "hod"]
    assert b.expected_count == 3
    assert b.tracking_code.startswith("ST-") and len(b.tracking_code) == 12
    assert student_svc.find_by_code(db, b.tracking_code.lower().replace("-", " ")) == b
    assert b.requester_name == "Student group (Arun K, Bala S +1)"
    assert [n.kind for n in inbox(db, GUIDE)] == ["approval_needed"]
    assert inbox(db, INCHARGE) == []
    (subject,) = emails(db, b)
    assert subject.startswith("Request received for CC5") and b.tracking_code in subject
    # The slot is held while the guide decides.
    assert b.status in svc.HOLDING_STATUSES


def test_tracking_numbers_are_not_sequential(db, classes):
    codes = {new for new in (student_svc.new_code() for _ in range(200))}
    assert len(codes) == 200
    assert all(set(c[3:].replace("-", "")) <= set(student_svc.CODE_ALPHABET) for c in codes)


@pytest.mark.parametrize("venue", ["CSEPGSH", "ASH"])
def test_seminar_halls_are_refused(db, classes, venue):
    with pytest.raises(svc.BookingError, match="labs and centres of excellence"):
        submit(db, classes, venue=venue)


@pytest.mark.parametrize(
    "change,message",
    [
        ({"reason": "  "}, "what the group will work on"),
        ({"email": "not-an-email"}, "valid contact email"),
        ({"students": []}, "Add the students"),
        ({"guide": "cseoa@kiot.ac.in"}, "faculty guide"),
        ({"day": date(2026, 10, 20), "day_to": date(2026, 10, 20)}, "already passed"),
    ],
)
def test_bad_requests_are_refused(db, classes, change, message):
    with pytest.raises(svc.BookingError, match=message):
        submit(db, classes, **change)


def test_too_many_or_duplicate_students(db, classes):
    sid = classes["II-A"].id
    many = [student_svc.StudentIn(f"Student {i}", sid) for i in range(11)]
    with pytest.raises(svc.BookingError, match="at most 10"):
        submit(db, classes, students=many)
    twice = [student_svc.StudentIn("Arun K", sid), student_svc.StudentIn("arun  k", sid)]
    with pytest.raises(svc.BookingError, match="listed twice"):
        submit(db, classes, students=twice)


def test_students_cannot_take_a_held_slot_or_join_the_waitlist(db, classes):
    submit(db, classes)
    with pytest.raises(svc.BookingError, match="already booked"):
        submit(db, classes, email="other@example.com")


def test_students_cannot_move_a_class(db, classes):
    from app.config import get_settings
    from app.services.timetables import ingest_and_commit

    # CSE II-A has DBMS in CC1 on Mondays 09:00-10:40.
    ingest_and_commit(db, get_settings().mock_data_dir / "timetables" / "TT_CSE_II_YR_A.pdf")
    db.commit()
    req = request(db, classes, venue="CC1", day=date(2026, 11, 2), day_to=date(2026, 11, 2))
    req.start_time, req.end_time = time(9, 0), time(10, 0)
    with pytest.raises(svc.BookingError, match="has a class then"):
        student_svc.submit_student(db, req, now=NOW)


def test_one_email_sends_at_most_three_requests_a_day(db, classes):
    for day in (4, 5, 6):
        submit(db, classes, day=date(2026, 11, day), day_to=date(2026, 11, day))
    with pytest.raises(svc.BookingError, match="3 requests today") as e:
        submit(db, classes, day=date(2026, 11, 10), day_to=date(2026, 11, 10))
    assert e.value.status == 429


def test_the_email_domain_can_be_enforced(db, classes, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "student_email_domain", "kiot.ac.in")
    with pytest.raises(svc.BookingError, match="@kiot.ac.in"):
        submit(db, classes)
    b = submit(db, classes, email="Arun.K@KIOT.ac.in")
    assert b.contact_email == "arun.k@kiot.ac.in"


# The guide's decision ---------------------------------------------------------------------------


def test_only_the_chosen_guide_decides(db, classes):
    b = submit(db, classes)
    for email in ("tkcse@kiot.ac.in", "dirim@kiot.ac.in", INCHARGE):
        assert not svc.can_act(user(db, email), b)
        with pytest.raises(svc.BookingError) as e:
            svc.approve(db, user(db, email), b, now=NOW)
        assert e.value.status == 403
    assert svc.can_act(user(db, GUIDE), b)


def test_the_guide_approves_some_students_and_rejects_others(db, classes):
    b = submit(db, classes)
    s = by_name(b)
    guide = user(db, GUIDE)
    with pytest.raises(svc.BookingError, match="Say why Charu M"):
        svc.decide_students(db, guide, b, [(s["Charu M"].id, "rejected", "")], now=NOW)
    with pytest.raises(svc.BookingError, match="still waiting"):
        svc.decide_students(db, guide, b, [(s["Arun K"].id, "approved", None)], now=NOW)
    svc.decide_students(
        db,
        guide,
        b,
        [
            (s["Arun K"].id, "approved", None),
            (s["Bala S"].id, "approved", None),
            (s["Charu M"].id, "rejected", "Not in this project"),
        ],
        now=NOW,
    )
    db.commit()
    assert b.status == "pending_incharge" and b.expected_count == 2
    assert [a.step for a in b.approvals] == ["guide"]
    assert b.approvals[0].comment.startswith("Approved 2 of 3 students.")
    assert [n.kind for n in inbox(db, INCHARGE)] == ["approval_needed"]
    # Charu's advisor hears now; the approved students' advisor waits for the final outcome.
    (note,) = inbox(db, "vacse@kiot.ac.in")
    assert "not approved for Charu M (CSE II-A)" in note.message
    assert inbox(db, "ekcse@kiot.ac.in") == []
    assert any("approved 2 of 3 students" in e for e in emails(db, b))


def test_the_whole_chain_and_advisors(db, classes):
    b = submit(db, classes)
    s = by_name(b)
    svc.decide_students(
        db,
        user(db, GUIDE),
        b,
        [
            (s["Arun K"].id, "approved", None),
            (s["Bala S"].id, "approved", None),
            (s["Charu M"].id, "rejected", "Not in this project"),
        ],
        now=NOW,
    )
    svc.approve(db, user(db, INCHARGE), b, "OK", now=NOW)
    assert b.status == "pending_hod"
    svc.approve(db, user(db, HOD), b, None, now=NOW)
    db.commit()
    assert b.status == "confirmed"
    (note,) = inbox(db, "ekcse@kiot.ac.in")  # CSE III-B's advisor, one note for both students
    assert note.kind == "student_request"
    assert "approved for Arun K, Bala S (CSE III-B)" in note.message
    assert [n.message.count("Charu") for n in inbox(db, "vacse@kiot.ac.in")] == [1]
    assert "confirmed" in [n.kind for n in inbox(db, GUIDE)]
    subjects = emails(db, b)
    assert subjects[-1].startswith("Confirmed: CC5")
    assert any(e.startswith("The venue in-charge approved") for e in subjects)


def test_approve_all_and_reject_all(db, classes):
    b = submit(db, classes)
    svc.approve(db, user(db, GUIDE), b, "Good team", now=NOW)
    assert b.status == "pending_incharge"
    assert {x.decision for x in b.students} == {"approved"}

    other = submit(db, classes, day=date(2026, 11, 5), day_to=date(2026, 11, 5))
    with pytest.raises(svc.BookingError, match="Say why"):
        svc.reject(db, user(db, GUIDE), other, "", now=NOW)
    svc.reject(db, user(db, GUIDE), other, "Not my students", now=NOW)
    db.commit()
    assert other.status == "rejected"
    assert {x.decision for x in other.students} == {"rejected"}
    assert {x.advisor_told for x in other.students} == {"rejected"}
    assert emails(db, other)[-1].startswith("Your request was not approved")


def test_a_later_rejection_tells_the_advisors_of_approved_students(db, classes):
    b = submit(db, classes)
    svc.approve(db, user(db, GUIDE), b, None, now=NOW)
    svc.reject(db, user(db, INCHARGE), b, "Lab maintenance that afternoon", now=NOW)
    db.commit()
    assert b.status == "rejected"
    (note,) = inbox(db, "ekcse@kiot.ac.in")
    assert "not approved for Arun K, Bala S (CSE III-B)" in note.message
    assert "rejected" in [n.kind for n in inbox(db, GUIDE)]


def test_a_guide_who_runs_the_lab_also_covers_the_incharge_step(db, classes):
    b = submit(db, classes, guide=INCHARGE)
    svc.approve(db, user(db, INCHARGE), b, None, now=NOW)
    assert b.status == "pending_hod"
    assert [(a.step, a.approver_id) for a in b.approvals] == [
        ("guide", user(db, INCHARGE).id),
        ("incharge", user(db, INCHARGE).id),
    ]
    assert b.approvals[1].comment.startswith("Approved automatically")


# Cancelling -------------------------------------------------------------------------------------


def test_the_group_cancels_with_its_tracking_number(db, classes):
    b = submit(db, classes)
    with pytest.raises(svc.BookingError):
        svc.cancel(db, None, b, "Changed plans", now=NOW, tracking_code="ST-XXXX-XXXX")
    svc.cancel(db, None, b, "Changed plans", now=NOW, tracking_code=b.tracking_code)
    db.commit()
    assert b.status == "cancelled" and b.cancel_reason == "Changed plans"
    assert emails(db, b)[-1].startswith("Your request was cancelled")
    # Nobody was told it was approved, so advisors hear nothing.
    assert inbox(db, "ekcse@kiot.ac.in") == []


def test_cancelling_a_confirmed_request_tells_the_advisors(db, classes):
    b = submit(db, classes)
    svc.approve(db, user(db, GUIDE), b, None, now=NOW)
    svc.approve(db, user(db, INCHARGE), b, None, now=NOW)
    svc.approve(db, user(db, HOD), b, None, now=NOW)
    svc.cancel(db, None, b, None, now=NOW, tracking_code=b.tracking_code)
    db.commit()
    notes = [n.message for n in inbox(db, "vacse@kiot.ac.in")]
    assert len(notes) == 2 and "cancelled by the group for Charu M" in notes[1]


# People -----------------------------------------------------------------------------------------


def test_timetable_advisor_names_match_accounts(db):
    assert name_key("Mr. G. Babu, AP/CSE") == name_key("Mr. G. Babu")
    (babu,) = faculty_matching(db, "Mr. G. Babu, AP/CSE")
    assert babu.email == "gbcse@kiot.ac.in"
    (kumar,) = faculty_matching(db, "Dr. V. Kumar, Prof/CSE")
    assert kumar.email == "dirim@kiot.ac.in"
