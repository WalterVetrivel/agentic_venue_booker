"""What a student group and its class advisors hear about a student request.

The group has no login, so it hears by email at the contact address it gave. Class advisors
get an in-app notification when their students' outcome is final.
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Booking, BookingStudent, User
from app.services import mailer
from app.services.notifications import notify
from app.services.people import faculty_matching

OUTCOME_TEXT = {
    "approved": "approved",
    "rejected": "not approved",
    "cancelled": "cancelled by the group",
}


def track_url(booking: Booking) -> str:
    return f"{get_settings().public_url.rstrip('/')}/track?code={booking.tracking_code}"


def when(booking: Booking) -> str:
    occ = booking.occurrences
    if not occ:
        return f"{booking.start_dt:%a %d %b %Y}"
    first = occ[0]
    text = f"{first.start_dt:%a %d %b %Y}, {first.start_dt:%H:%M}–{first.end_dt:%H:%M}"
    if len(occ) > 1:
        text += f" ({len(occ)} days, to {occ[-1].start_dt:%a %d %b})"
    return text


def _summary(booking: Booking) -> str:
    students = "\n".join(f"  - {s.name} ({s.class_label}){_decision(s)}" for s in booking.students)
    return (
        f"Tracking number: {booking.tracking_code}\n"
        f"Venue: {booking.venue.code} · {booking.venue.name}\n"
        f"When: {when(booking)}\n"
        f"Faculty guide: {booking.guide.name if booking.guide else '-'}\n"
        f"Reason: {booking.description or booking.title}\n"
        f"Students:\n{students}\n\n"
        f"Track it any time: {track_url(booking)}\n"
    )


def _decision(s: BookingStudent) -> str:
    if s.decision == "approved":
        return " - approved"
    if s.decision == "rejected":
        return " - not approved" + (f": {s.comment}" if s.comment else "")
    return ""


def _email(db: Session, booking: Booking, subject: str, opening: str) -> None:
    if not booking.contact_email:
        return
    body = f"Hello,\n\n{opening}\n\n{_summary(booking)}\n-- KIOT Venue Booking (do not reply)\n"
    subject = f"{subject} [{booking.tracking_code}]"
    mailer.queue(db, booking.contact_email, subject, body, booking.id)


def submitted(db: Session, booking: Booking) -> None:
    guide = booking.guide.name if booking.guide else "your faculty guide"
    _email(
        db,
        booking,
        f"Request received for {booking.venue.code}",
        f"We got your request for {booking.venue.code}. It now goes to {guide}, who approves "
        "or rejects each student, then to the venue in-charge and the HOD. You'll get an email "
        "at each step. Keep the tracking number below.",
    )


def _next(booking: Booking) -> str:
    return {"pending_hod": "the HOD", "pending_incharge": "the venue in-charge"}.get(
        booking.status, "the next approver"
    )


def guide_decided(db: Session, booking: Booking, guide: User) -> None:
    approved = sum(s.decision == "approved" for s in booking.students)
    _email(
        db,
        booking,
        f"{guide.name} approved {approved} of {len(booking.students)} students",
        f"{guide.name} has decided on each student (below). The request now waits for "
        f"{_next(booking)}.",
    )


def step_approved(
    db: Session, booking: Booking, user: User, label: str, comment: str | None
) -> None:
    _email(
        db,
        booking,
        f"The {label} approved your request",
        f"{user.name} ({label}) approved your request"
        + (f": “{comment}”" if comment else ".")
        + f" It now waits for {_next(booking)}.",
    )


def confirmed(db: Session, booking: Booking) -> None:
    _email(
        db,
        booking,
        f"Confirmed: {booking.venue.code} on {booking.start_dt:%d %b}",
        f"Your request is confirmed. {booking.venue.code} is yours for the time below, for the "
        "approved students only.",
    )
    advisors(db, booking, [s for s in booking.students if s.decision == "approved"], "approved")


def rejected(db: Session, booking: Booking, user: User, label: str, comment: str | None) -> None:
    _email(
        db,
        booking,
        "Your request was not approved",
        f"{user.name} ({label}) did not approve your request"
        + (f": “{comment}”" if comment else ".")
        + " The slot has been released. You can send a new request.",
    )
    told = [s for s in booking.students if s.decision == "approved" and not s.advisor_told]
    advisors(db, booking, told, "rejected")


def cancelled(
    db: Session, booking: Booking, reason: str | None, was_confirmed: bool, by_group: bool
) -> None:
    who = "Your group" if by_group else "The Director"
    _email(
        db,
        booking,
        "Your request was cancelled",
        f"{who} cancelled this request"
        + (f": {reason}" if reason else ".")
        + " The slot has been released.",
    )
    if was_confirmed:
        told = [s for s in booking.students if s.advisor_told == "approved"]
        advisors(db, booking, told, "cancelled")


def advisors(db: Session, booking: Booking, students: list[BookingStudent], outcome: str) -> None:
    """Tell each class advisor the outcome for their own students, one notification each."""
    by_advisor: dict[int, tuple[User, list[BookingStudent]]] = {}
    for s in students:
        s.advisor_told = outcome
        advisor_name = s.section.advisor if s.section else None
        for user in faculty_matching(db, advisor_name):
            by_advisor.setdefault(user.id, (user, []))[1].append(s)
    for user, mine in by_advisor.values():
        names = _names_by_class(mine)
        guide = booking.guide.name if booking.guide else "a faculty guide"
        notify(
            db,
            [user],
            "student_request",
            f"Student request {booking.ref} for {booking.venue.code} on {when(booking)} under "
            f"{guide}: {OUTCOME_TEXT[outcome]} for {names}.",
            f"/bookings/{booking.id}",
        )


def _names_by_class(students: list[BookingStudent]) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for s in students:
        grouped[s.class_label].append(s.name)
    return "; ".join(f"{', '.join(names)} ({label})" for label, names in grouped.items())
