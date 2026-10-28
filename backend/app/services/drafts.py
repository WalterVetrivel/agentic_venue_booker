"""Booking forms saved without submitting.

A draft holds nothing. If someone else books the slot while it waits, the draft's owner gets a
notification, the draft shows that the slot was taken since it was saved, and submitting it can
only join the waitlist (the normal submit refuses a taken slot unless it joins the waitlist).
"""

from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingDraft, User
from app.services import bookings as booking_svc
from app.services.access import can
from app.services.notifications import notify
from app.services.venues import get_venue

MAX_DRAFTS = 50


@dataclass
class DraftFields:
    venue: str | None = None
    title: str = ""
    event_type: str | None = None
    expected_count: int | None = None
    description: str | None = None
    requirements: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    start_time: time | None = None
    end_time: time | None = None


def request_for(d: BookingDraft) -> booking_svc.BookingRequest | None:
    """The request the draft would make, or None while the venue, date or times are missing."""
    if not (d.venue and d.date_from and d.start_time and d.end_time):
        return None
    return booking_svc.BookingRequest(
        venue_code=d.venue.code,
        title=d.title or "Event",
        event_type=d.event_type or "Other",
        expected_count=d.expected_count or 1,
        date_from=d.date_from,
        date_to=d.date_to or d.date_from,
        start_time=d.start_time,
        end_time=d.end_time,
    )


def outcome(db: Session, d: BookingDraft) -> str:
    """free | waitlist | displace | blocked, or incomplete / invalid when it can't be checked."""
    req = request_for(d)
    if req is None:
        return "incomplete"
    try:
        return booking_svc.check_request(db, req).outcome
    except booking_svc.BookingError:
        return "invalid"


def taken_since_saved(d: BookingDraft, now_outcome: str) -> bool:
    return now_outcome == "waitlist" and d.saved_outcome in ("free", "displace")


def save(
    db: Session, user: User, fields: DraftFields, draft: BookingDraft | None = None
) -> BookingDraft:
    if not can(user, "book"):
        raise booking_svc.BookingError("You can't book venues.", 403)
    if draft is None:
        mine = select(func.count()).where(BookingDraft.user_id == user.id)
        if db.scalar(mine) >= MAX_DRAFTS:
            raise booking_svc.BookingError(
                f"You have {MAX_DRAFTS} drafts. Delete some before saving another.", 422
            )
        draft = BookingDraft(user=user)
        db.add(draft)
    venue = get_venue(db, fields.venue) if fields.venue else None
    if fields.venue and venue is None:
        raise booking_svc.BookingError(f"Unknown venue {fields.venue}.", 404)
    draft.venue = venue
    draft.title = fields.title.strip()
    draft.event_type = fields.event_type or None
    draft.expected_count = fields.expected_count
    draft.description = fields.description or None
    draft.requirements = fields.requirements or None
    draft.date_from = fields.date_from
    draft.date_to = fields.date_to
    draft.start_time = fields.start_time
    draft.end_time = fields.end_time
    draft.saved_outcome = outcome(db, draft)
    draft.taken_notified = False
    db.flush()
    return draft


def notify_taken(db: Session, booking: Booking) -> int:
    """Tell other people whose drafts for this venue and time can now only join the waitlist."""
    start, end = booking.start_dt, booking.end_dt
    drafts = db.scalars(
        select(BookingDraft).where(
            BookingDraft.venue_id == booking.venue_id,
            BookingDraft.user_id != booking.requester_id,
            BookingDraft.taken_notified.is_(False),
            BookingDraft.date_from <= end.date(),
        )
    ).all()
    told = 0
    for d in drafts:
        if (d.date_to or d.date_from) < start.date():
            continue
        if not taken_since_saved(d, outcome(db, d)):
            continue
        d.taken_notified = True
        notify(
            db,
            [d.user],
            "draft_taken",
            f"{booking.venue.code} was booked for {d.date_from:%d %b} while your draft "
            f"“{d.title or 'Untitled'}” was waiting. It can now only join the waitlist.",
            f"/book?draft={d.id}",
        )
        told += 1
    return told
