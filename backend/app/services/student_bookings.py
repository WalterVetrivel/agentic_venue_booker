"""Student requests: no login, a faculty guide approves each student, tracked by a number.

A group names its faculty guide, lists its students with their classes and gives one contact
email. The request then goes guide -> venue in-charge -> HOD (app.services.bookings routes it).
Students can only ask for labs and centres of excellence that are free: they can't move a class
or join the waitlist.
"""

import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Booking, BookingOccurrence, BookingStudent, ClassSection, User
from app.services import audit, student_notices
from app.services.bookings import (
    STUDENT_EVENT_TYPE,
    BookingError,
    BookingRequest,
    RequestCheck,
    _route,
    check_request,
)
from app.services.people import guides

MAX_STUDENTS = 10
EMAILS_PER_DAY = 3  # requests one contact address can send in 24 hours
STUDENT_VENUE_TYPES = ("lab", "coe")
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O, 1/I/L
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class StudentIn:
    name: str
    section_id: int
    register_no: str | None = None


@dataclass
class StudentRequest:
    venue_code: str
    date_from: date
    date_to: date
    start_time: time
    end_time: time
    reason: str
    guide_id: int
    contact_email: str
    students: list[StudentIn] = field(default_factory=list)

    def as_booking_request(self) -> BookingRequest:
        return BookingRequest(
            venue_code=self.venue_code,
            title=title_for(self.reason),
            event_type=STUDENT_EVENT_TYPE,
            expected_count=max(len(self.students), 1),
            date_from=self.date_from,
            date_to=self.date_to,
            start_time=self.start_time,
            end_time=self.end_time,
        )


def title_for(reason: str) -> str:
    line = " ".join(reason.split())
    return line if len(line) <= 80 else line[:77].rstrip() + "…"


def new_code() -> str:
    pick = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"ST-{pick[:4]}-{pick[4:]}"


def normalise_code(text: str) -> str:
    """'st 7k3p9qxa', 'ST-7K3P-9QXA' and '7K3P9QXA' all mean ST-7K3P-9QXA."""
    raw = re.sub(r"[^A-Z0-9]", "", text.upper())
    raw = raw.removeprefix("ST") if len(raw) == 10 else raw
    return f"ST-{raw[:4]}-{raw[4:]}" if len(raw) == 8 else text.strip().upper()


def find_by_code(db: Session, text: str) -> Booking | None:
    return db.scalar(select(Booking).where(Booking.tracking_code == normalise_code(text)))


def check_student_request(db: Session, req: StudentRequest) -> RequestCheck:
    """The staff check, refusing venues students can't book. Alternatives are labs and CoEs."""
    result = check_request(db, req.as_booking_request())
    if result.venue.type not in STUDENT_VENUE_TYPES:
        raise BookingError("Students can book labs and centres of excellence only.", 422)
    result.alternatives = [v for v in result.alternatives if v.type in STUDENT_VENUE_TYPES]
    return result


def outcome_text(result: RequestCheck) -> str | None:
    """Why a student group can't have this slot, or None if it can."""
    v = result.venue
    if result.blocked:
        return f"{v.code} can't be booked then: {result.blocked[0].label}."
    if result.taken:
        return f"{v.code} is already booked then ({result.taken[0].label})."
    if result.clashes:
        c = result.clashes[0]
        return f"{v.code} has a class then ({c.slot.section.label} {c.slot.subject_name})."
    return None


def _check_email(db: Session, email: str, now: datetime) -> str:
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise BookingError("Give a valid contact email.", 422)
    domain = get_settings().student_email_domain.strip().lower().lstrip("@")
    if domain and not email.endswith("@" + domain):
        raise BookingError(f"Use your @{domain} email address.", 422)
    recent = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.contact_email == email, Booking.created_at >= now - timedelta(days=1)
        )
    )
    if recent >= EMAILS_PER_DAY and get_settings().rate_limits:
        raise BookingError(
            f"This email has sent {EMAILS_PER_DAY} requests today. Try again tomorrow.", 429
        )
    return email


def _students(db: Session, req: StudentRequest) -> list[BookingStudent]:
    if not req.students:
        raise BookingError("Add the students who need the venue.", 422)
    if len(req.students) > MAX_STUDENTS:
        raise BookingError(f"A request can have at most {MAX_STUDENTS} students.", 422)
    seen: set[tuple[str, int]] = set()
    rows = []
    for s in req.students:
        name = " ".join(s.name.split())
        if len(name) < 2:
            raise BookingError("Give each student's name.", 422)
        section = db.get(ClassSection, s.section_id)
        if section is None:
            raise BookingError(f"Choose a class for {name}.", 422)
        key = (name.lower(), section.id)
        if key in seen:
            raise BookingError(f"{name} ({section.label}) is listed twice.", 422)
        seen.add(key)
        reg = (s.register_no or "").strip().upper() or None
        rows.append(
            BookingStudent(name=name, register_no=reg, section=section, class_label=section.label)
        )
    return rows


def submit_student(
    db: Session, req: StudentRequest, via: str = "ui", now: datetime | None = None
) -> Booking:
    now = now or datetime.now()
    reason = req.reason.strip()
    if len(reason) < 5:
        raise BookingError("Say what the group will work on.", 422)
    guide = db.get(User, req.guide_id)
    if guide is None or guide not in guides(db):
        raise BookingError("Choose your faculty guide from the list.", 422)
    email = _check_email(db, req.contact_email, now)
    students = _students(db, req)
    if req.date_from < now.date():
        raise BookingError("That date has already passed.", 422)
    result = check_student_request(db, req)
    problem = outcome_text(result)
    if problem:
        raise BookingError(problem + " Choose another time or lab.")
    venue = result.venue
    if len(students) > venue.capacity:
        raise BookingError(f"{venue.code} seats {venue.capacity}.", 422)

    code = new_code()
    while db.scalar(select(Booking.id).where(Booking.tracking_code == code)):
        code = new_code()
    booking = Booking(
        ref="pending",
        kind="student",
        requester=None,
        guide=guide,
        venue=venue,
        title=title_for(reason),
        event_type=STUDENT_EVENT_TYPE,
        description=reason,
        expected_count=len(students),
        start_dt=result.occurrences[0][0],
        end_dt=result.occurrences[-1][1],
        status="draft",
        created_via="assistant" if via == "agent" else "form",
        tracking_code=code,
        contact_email=email,
        created_at=now,
        occurrences=[BookingOccurrence(start_dt=s, end_dt=e) for s, e in result.occurrences],
        students=students,
    )
    db.add(booking)
    db.flush()
    booking.ref = f"BK-{now.year}-{booking.id:04d}"
    _route(db, booking, None, now)
    student_notices.submitted(db, booking)
    audit.record(
        db,
        None,
        "submit",
        "booking",
        booking.id,
        after={"ref": booking.ref, "venue": venue.code, "kind": "student", "status": "submitted"},
        via=via,
        at=now,
    )
    return booking


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    user, domain = email.split("@", 1)
    return f"{user[:2]}{'•' * max(len(user) - 2, 1)}@{domain}"
