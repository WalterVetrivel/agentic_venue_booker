from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Booking, Notification, SlotOverride, User
from app.services import availability
from app.services import bookings as svc
from app.services.timetables import ingest_and_commit
from app.services.venues import get_venue

pytestmark = pytest.mark.writes_db

NOW = datetime(2026, 10, 27, 9, 0)
# CSE II-A has DBMS (B1) in CC1 and DS (B2) in CC2 on Mondays 09:00-10:40.
MONDAY = date(2026, 11, 2)
TUESDAY = date(2026, 11, 3)


def user(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def req(venue="DSH", day=TUESDAY, start=(10, 0), end=(12, 0), count=50, **kw) -> svc.BookingRequest:
    return svc.BookingRequest(
        venue_code=venue,
        title=kw.pop("title", "AI awareness talk"),
        event_type=kw.pop("event_type", "Seminar"),
        expected_count=count,
        date_from=day,
        date_to=kw.pop("date_to", day),
        start_time=time(*start),
        end_time=time(*end),
        **kw,
    )


def book(db, email="tkcse@kiot.ac.in", r=None, **kw) -> Booking:
    b = svc.submit(db, user(db, email), r or req(), now=NOW, **kw)
    db.commit()
    return b


def inbox(db, email: str) -> list[str]:
    u = user(db, email)
    return [n.kind for n in db.scalars(select(Notification).where(Notification.user_id == u.id))]


# Approval chain ---------------------------------------------------------------------------------


def test_admin_hall_needs_only_the_incharge(db):
    b = book(db)
    assert b.status == "pending_incharge" and b.ref == f"BK-2026-{b.id:04d}"
    assert svc.steps_for(b) == ["incharge"]
    assert "approval_needed" in inbox(db, "sh.dblock@kiot.ac.in")

    svc.approve(db, user(db, "sh.dblock@kiot.ac.in"), b, "Fine", now=NOW)
    assert b.status == "confirmed"
    assert {"approved_step", "confirmed"} <= set(inbox(db, "tkcse@kiot.ac.in"))


def test_cse_venue_goes_to_incharge_then_hod(db):
    b = book(db, r=req("CSEPGSH", count=70))
    assert svc.steps_for(b) == ["incharge", "hod"]
    hod = user(db, "hod.cse@kiot.ac.in")
    with pytest.raises(svc.BookingError) as err:
        svc.approve(db, hod, b, now=NOW)  # not their step yet
    assert err.value.status == 403

    svc.approve(db, user(db, "pvcse@kiot.ac.in"), b, now=NOW)
    assert b.status == "pending_hod"
    assert "approval_needed" in inbox(db, "hod.cse@kiot.ac.in")
    svc.approve(db, hod, b, now=NOW)
    assert b.status == "confirmed"
    assert [a.step for a in b.approvals] == ["incharge", "hod"]


def test_incharge_booking_own_lab_skips_their_step(db):
    b = book(db, "swvcse@kiot.ac.in", req("CC10", count=30))
    assert b.status == "pending_hod"
    assert b.approvals[0].step == "incharge" and "automatically" in b.approvals[0].comment


def test_director_booking_is_confirmed_at_once(db):
    b = book(db, "dirim@kiot.ac.in", req("CC1"))
    assert b.status == "confirmed" and len(b.approvals) == 2


def test_other_incharge_cannot_approve(db):
    b = book(db, r=req("CC1"))
    with pytest.raises(svc.BookingError) as err:
        svc.approve(db, user(db, "swvcse@kiot.ac.in"), b, now=NOW)
    assert err.value.status == 403


def test_reject_needs_a_reason(db):
    b = book(db)
    with pytest.raises(svc.BookingError):
        svc.reject(db, user(db, "sh.dblock@kiot.ac.in"), b, " ", now=NOW)
    svc.reject(db, user(db, "sh.dblock@kiot.ac.in"), b, "Hall is being painted", now=NOW)
    assert b.status == "rejected" and "rejected" in inbox(db, "tkcse@kiot.ac.in")


def test_oa_cannot_book(db):
    with pytest.raises(svc.BookingError) as err:
        book(db, "cseoa@kiot.ac.in")
    assert err.value.status == 403


# Validation -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "r, message",
    [
        (req(day=date(2026, 11, 8)), "Closed on Sundays"),
        (req(count=500), "seats 300"),
        (req(day=date(2026, 10, 1)), "already passed"),
        (req(start=(12, 0), end=(10, 0)), "end time"),
        (req("ASH", day=date(2027, 4, 6)), "admission"),
        (req(event_type="Party"), "event type"),
    ],
)
def test_invalid_requests(db, r, message):
    with pytest.raises(svc.BookingError, match=message):
        book(db, r=r)


def test_multi_day_event_skips_sunday_and_holds_every_day(db):
    b = book(db, r=req(day=date(2026, 11, 6), date_to=date(2026, 11, 9)))
    assert [o.start_dt.date().day for o in b.occurrences] == [6, 7, 9]
    dsh = get_venue(db, "DSH")
    held = availability.check(db, dsh, datetime(2026, 11, 7, 11), datetime(2026, 11, 7, 11, 30))
    assert [c.kind for c in held.conflicts] == ["pending"]


# Waitlist ---------------------------------------------------------------------------------------


def test_clash_needs_waitlist_and_cancel_offers_the_slot(db):
    first = book(db)
    with pytest.raises(svc.BookingError, match="waitlist"):
        book(db, "swvcse@kiot.ac.in")
    second = book(db, "swvcse@kiot.ac.in", join_waitlist=True)
    third = book(db, "prcse@kiot.ac.in", r=req(start=(11, 0), end=(13, 0)), join_waitlist=True)
    assert (second.status, svc.waitlist_position(db, second)) == ("waitlisted", 1)
    assert svc.waitlist_position(db, third) == 2

    svc.cancel(db, user(db, "tkcse@kiot.ac.in"), first, "Speaker unavailable", now=NOW)
    db.commit()
    assert second.status == "offered"
    assert second.offer_expires_at == NOW + timedelta(hours=24)
    assert third.status == "waitlisted"  # still overlaps the offer
    assert "offer" in inbox(db, "swvcse@kiot.ac.in")

    svc.accept_offer(db, user(db, "swvcse@kiot.ac.in"), second, now=NOW + timedelta(hours=2))
    assert second.status == "pending_incharge"


def test_expired_offer_moves_to_the_next_in_line(db):
    first = book(db)
    second = book(db, "swvcse@kiot.ac.in", join_waitlist=True)
    third = book(db, "prcse@kiot.ac.in", join_waitlist=True)
    svc.reject(db, user(db, "sh.dblock@kiot.ac.in"), first, "Clashes with exams", now=NOW)
    assert second.status == "offered"

    later = NOW + timedelta(hours=25)
    assert svc.expire_offers(db, later) == 1
    assert second.status == "expired" and third.status == "offered"
    with pytest.raises(svc.BookingError, match="no open offer"):
        svc.accept_offer(db, user(db, "swvcse@kiot.ac.in"), second, now=later)


def test_only_the_requester_or_director_can_cancel(db):
    b = book(db)
    with pytest.raises(svc.BookingError) as err:
        svc.cancel(db, user(db, "swvcse@kiot.ac.in"), b, now=NOW)
    assert err.value.status == 403
    svc.cancel(db, user(db, "dirim@kiot.ac.in"), b, "Venue needed for an inspection", now=NOW)
    assert b.status == "cancelled"


# Reschedule -------------------------------------------------------------------------------------


def test_reschedule_keeps_the_old_slot_until_the_new_one_is_confirmed(db):
    old = book(db)
    svc.approve(db, user(db, "sh.dblock@kiot.ac.in"), old, now=NOW)
    # An overlapping new time is fine: the booking doesn't clash with itself.
    new = book(db, r=req(start=(11, 0), end=(13, 0)), reschedule=old)
    assert new.parent_id == old.id and new.status == "pending_incharge"
    assert old.status == "confirmed"

    svc.approve(db, user(db, "sh.dblock@kiot.ac.in"), new, now=NOW)
    assert new.status == "confirmed"
    assert old.status == "cancelled" and old.cancel_reason == f"Rescheduled to {new.ref}"


def test_cannot_reschedule_someone_elses_booking(db):
    old = book(db)
    with pytest.raises(svc.BookingError) as err:
        book(db, "swvcse@kiot.ac.in", r=req(start=(14, 0), end=(15, 0)), reschedule=old)
    assert err.value.status == 403


# Class displacement -----------------------------------------------------------------------------


@pytest.fixture
def cse_ii_a(db):
    ingest_and_commit(db, get_settings().mock_data_dir / "timetables" / "TT_CSE_II_YR_A.pdf")
    db.commit()


def test_class_clash_needs_a_plan_and_hod_approval(db, cse_ii_a):
    r = req("CC1", day=MONDAY, start=(9, 0), end=(10, 40), count=40)
    result = svc.check_request(db, r)
    assert result.outcome == "displace"
    (clash,) = result.clashes
    assert clash.slot.subject_code == "DBMS" and clash.slot.batch == "B1"
    # CC2 has the same software but holds B2 then; the options are free, big enough labs.
    codes = [o.venue.code for o in clash.options]
    assert "CC2" not in codes and codes[0] in {"CC3", "CC4"}
    assert clash.options[0].software_match == 1.0

    with pytest.raises(svc.BookingError, match="Choose whether"):
        book(db, r=r)

    r.moves = [svc.Move(clash.slot.id, MONDAY, "relocated", codes[0])]
    b = book(db, r=r)
    assert svc.steps_for(b) == ["incharge", "hod"] and b.needs_displacement
    notes = svc.approval_notes(db, b)
    assert any(f"moves to {codes[0]}, which has the same software" in n for n in notes)

    svc.approve(db, user(db, "gbcse@kiot.ac.in"), b, now=NOW)
    svc.approve(db, user(db, "hod.cse@kiot.ac.in"), b, now=NOW)
    db.commit()
    assert b.status == "confirmed"
    assert db.scalar(select(SlotOverride)).active

    cc1 = availability.venue_day(db, get_venue(db, "CC1"), MONDAY)
    labels = [blk.label for blk in cc1.blocks if blk.start.hour == 9]
    assert labels == ["AI awareness talk"]
    target = availability.venue_day(db, get_venue(db, codes[0]), MONDAY)
    assert any("moved from CC1" in blk.label for blk in target.blocks)
    assert "event_in_venue" in inbox(db, "gbcse@kiot.ac.in")
    (teacher,) = svc.faculty_matching(db, clash.slot.faculty_name)
    assert "class_moved" in inbox(db, teacher.email)

    # Cancelling puts the class back.
    svc.cancel(db, user(db, "tkcse@kiot.ac.in"), b, now=NOW)
    db.commit()
    cc1 = availability.venue_day(db, get_venue(db, "CC1"), MONDAY)
    assert any(blk.kind == "class" for blk in cc1.blocks)


def test_byod_option_and_bad_relocation(db, cse_ii_a):
    r = req("CC1", day=MONDAY, start=(9, 0), end=(10, 40), count=40)
    slot_id = svc.check_request(db, r).clashes[0].slot.id
    r.moves = [svc.Move(slot_id, MONDAY, "relocated", "CC2")]
    with pytest.raises(svc.BookingError, match="isn't free"):
        book(db, r=r)
    r.moves = [svc.Move(slot_id, MONDAY, "byod_classroom")]
    b = book(db, r=r)
    assert b.displacements[0].action == "byod_classroom" and b.status == "pending_incharge"


def test_faculty_name_matching_ignores_titles_and_spacing(db):
    (match,) = svc.faculty_matching(db, "Mrs V. Sathiya Priya")
    assert match.email == "vspcse@kiot.ac.in"
    assert svc.faculty_matching(db, "Someone Else") == []
