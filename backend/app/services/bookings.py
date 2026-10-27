"""Booking workflow: submit, approve, reject, cancel, reschedule, waitlist and class displacement.

State machine (see docs/PLAN.md):

    submit -> pending_incharge -> pending_hod* -> confirmed -> cancelled
                     |                |
                  rejected         rejected
    submit while the slot is held -> waitlisted -> offered (24 h) -> pending_incharge ...
                                                       └─ expired / declined

    * only for venues that need HOD approval, or when a class has to be moved.

A step is skipped when the requester can approve it themselves (an in-charge booking their own
lab, the HOD booking a CSE venue, the Director). The skip is still recorded as an approval.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    Booking,
    BookingOccurrence,
    SlotOverride,
    TimetableSlot,
    User,
    UserRole,
    Venue,
)
from app.services import audit
from app.services.access import can
from app.services.availability import HOLDING_STATUSES, Block, Notice, check
from app.services.notifications import notify
from app.services.timetables import slot_label
from app.services.venues import find_venues, get_venue

EVENT_TYPES = [
    "Workshop",
    "Hands-on training",
    "Seminar",
    "Guest lecture",
    "Awareness programme",
    "Value-added course",
    "Faculty development programme",
    "Conference",
    "Coding contest",
    "Hackathon",
    "Inauguration",
    "Valedictory",
    "Model practical exam",
    "Placement training",
    "Admission activity",
    "Address by HOD, Principal or Chairman",
    "Professional elective class",
    "Meeting",
    "Other",
]
OFFER_HOURS = 24
MAX_DAYS = 14
OPEN_STATUSES = (*HOLDING_STATUSES, "waitlisted")  # the requester can still cancel these
STEP_LABELS = {"incharge": "venue in-charge", "hod": "HOD"}


class BookingError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


# Requests and checks --------------------------------------------------------------------------


@dataclass
class Move:
    """How to handle one class that clashes with the booking on one date."""

    slot_id: int
    on_date: date
    action: str  # relocated | byod_classroom
    venue_code: str | None = None


@dataclass
class BookingRequest:
    venue_code: str
    title: str
    event_type: str
    expected_count: int
    date_from: date
    date_to: date
    start_time: time
    end_time: time
    description: str | None = None
    requirements: str | None = None
    moves: list[Move] = field(default_factory=list)


@dataclass
class RelocationOption:
    venue: Venue
    software_match: float  # share of the original lab's software the option also has
    missing_software: list[str]


@dataclass
class ClassClash:
    slot: TimetableSlot
    on_date: date
    options: list[RelocationOption]


@dataclass
class RequestCheck:
    venue: Venue
    occurrences: list[tuple[datetime, datetime]]
    blocked: list[Block]
    taken: list[Block]
    clashes: list[ClassClash]
    warnings: list[Notice]
    alternatives: list[Venue]

    @property
    def outcome(self) -> str:
        if self.blocked:
            return "blocked"
        if self.taken:
            return "waitlist"
        if self.clashes:
            return "displace"
        return "free"


def occurrences_for(req: BookingRequest) -> list[tuple[datetime, datetime]]:
    if req.end_time <= req.start_time:
        raise BookingError("The end time must be after the start time.", 422)
    if req.date_to < req.date_from:
        raise BookingError("The last day can't be before the first day.", 422)
    if (req.date_to - req.date_from).days >= MAX_DAYS:
        raise BookingError(f"An event can run for at most {MAX_DAYS} days.", 422)
    days = [
        req.date_from + timedelta(days=i) for i in range((req.date_to - req.date_from).days + 1)
    ]
    # Multi-day events skip Sundays; a single Sunday is reported as closed by the check.
    if len(days) > 1:
        days = [d for d in days if d.weekday() != 6]
    return [(datetime.combine(d, req.start_time), datetime.combine(d, req.end_time)) for d in days]


def _software(venue: Venue) -> set[str]:
    return {e.name for e in venue.equipment if e.category == "software"}


def batch_size(slot: TimetableSlot) -> int:
    strength = slot.section.strength or 60
    return strength if slot.batch == "all" else math.ceil(strength / 2)


def relocation_options(
    db: Session, slot: TimetableSlot, on_date: date, exclude: set[int], limit: int = 5
) -> list[RelocationOption]:
    """Labs free during the class, big enough for the batch, ranked by matching software."""
    needed = _software(slot.venue)
    start = datetime.combine(on_date, slot.start)
    end = datetime.combine(on_date, slot.end)
    options = []
    for v in find_venues(db, min_capacity=batch_size(slot)):
        if v.id in exclude or v.id == slot.venue_id or v.type == "seminar_hall":
            continue
        if not check(db, v, start, end).free:
            continue
        have = _software(v)
        missing = sorted(needed - have)
        match = 1.0 if not needed else (len(needed) - len(missing)) / len(needed)
        options.append(RelocationOption(v, match, missing))
    options.sort(key=lambda o: (-o.software_match, o.venue.capacity))
    return options[:limit]


def check_request(
    db: Session, req: BookingRequest, ignore: frozenset[int] = frozenset()
) -> RequestCheck:
    venue = get_venue(db, req.venue_code)
    if venue is None:
        raise BookingError(f"Unknown venue {req.venue_code}.", 404)
    occ = occurrences_for(req)
    blocked: list[Block] = []
    taken: list[Block] = []
    clashes: list[ClassClash] = []
    warnings: list[Notice] = []
    for start, end in occ:
        result = check(db, venue, start, end, ignore)
        blocked += result.blocked
        taken += result.taken
        warnings += result.warnings
        for b in result.classes:
            slot = db.get(TimetableSlot, b.ref)
            if slot is not None:
                options = relocation_options(db, slot, start.date(), exclude={venue.id})
                clashes.append(ClassClash(slot, start.date(), options))
    if req.expected_count > venue.capacity:
        warnings.append(
            Notice(
                venue.id,
                "capacity",
                f"{venue.code} seats {venue.capacity}, fewer than the {req.expected_count} "
                "expected.",
            )
        )
    unique = list({(w.kind, w.message): w for w in warnings}.values())
    alternatives = []
    recurring = any(w.kind == "recurring" for w in unique)
    if blocked or taken or clashes or recurring or req.expected_count > venue.capacity:
        alternatives = suggest_venues(db, req, occ, exclude=venue.id, like=venue)
    return RequestCheck(venue, occ, blocked, taken, clashes, unique, alternatives)


def suggest_venues(
    db: Session,
    req: BookingRequest,
    occ: list[tuple[datetime, datetime]],
    exclude: int | None = None,
    like: Venue | None = None,
    limit: int = 3,
) -> list[Venue]:
    """Venues free for every occurrence that seat everyone, same kind of venue first."""
    found = []
    for v in find_venues(db, min_capacity=req.expected_count):
        if v.id == exclude:
            continue
        results = [check(db, v, s, e) for s, e in occ]
        # Skip venues that are free but where a yearly event usually happens then.
        if all(r.free and not any(w.kind == "recurring" for w in r.warnings) for r in results):
            found.append(v)
    if like is not None:
        found.sort(key=lambda v: (v.type != like.type, v.capacity))
    else:
        found.sort(key=lambda v: v.capacity)
    return found[:limit]


# Approval routing ------------------------------------------------------------------------------


def steps_for(booking: Booking) -> list[str]:
    needs_hod = booking.venue.needs_hod_approval or booking.needs_displacement
    return ["incharge", "hod"] if needs_hod else ["incharge"]


def current_step(booking: Booking) -> str | None:
    return (
        booking.status.removeprefix("pending_") if booking.status.startswith("pending_") else None
    )


def can_approve_step(user: User | None, booking: Booking, step: str) -> bool:
    if user is None:
        return False
    if can(user, "approve_all"):
        return True
    if step == "incharge":
        return can(user, "approve_own_venues") and booking.venue.in_charge_id == user.id
    if step == "hod":
        return (booking.venue.needs_hod_approval and can(user, "approve_cse_venues")) or (
            booking.needs_displacement and can(user, "approve_displacement")
        )
    return False


def can_act(user: User | None, booking: Booking) -> bool:
    step = current_step(booking)
    return step is not None and can_approve_step(user, booking, step)


def _approvers(db: Session, booking: Booking, step: str) -> list[User]:
    if step == "incharge":
        return [booking.venue.in_charge] if booking.venue.in_charge else _directors(db)
    return list(db.scalars(select(User).join(UserRole).where(UserRole.role_key == "hod")))


def _directors(db: Session) -> list[User]:
    return list(db.scalars(select(User).join(UserRole).where(UserRole.role_key == "director")))


def _link(booking: Booking) -> str:
    return f"/bookings/{booking.id}"


def _describe(booking: Booking) -> str:
    first = booking.occurrences[0].start_dt if booking.occurrences else booking.start_dt
    days = len(booking.occurrences)
    when = f"{first:%d %b}" + (f" (+{days - 1} more days)" if days > 1 else "")
    return f"{booking.ref} “{booking.title}” in {booking.venue.code} on {when}"


def _route(db: Session, booking: Booking, after: str | None, now: datetime) -> None:
    """Move to the next approval step, skipping steps the requester can approve themselves."""
    steps = steps_for(booking)
    remaining = steps[steps.index(after) + 1 :] if after in steps else steps
    for step in remaining:
        if can_approve_step(booking.requester, booking, step):
            booking.approvals.append(
                Approval(
                    step=step,
                    approver_id=booking.requester_id,
                    decision="approved",
                    comment="Approved automatically: the requester approves this step.",
                    decided_at=now,
                )
            )
            continue
        booking.status = f"pending_{step}"
        notify(
            db,
            _approvers(db, booking, step),
            "approval_needed",
            f"{booking.requester.name} asks for {_describe(booking)}. Your approval is needed.",
            "/approvals",
        )
        return
    _confirm(db, booking, now)


def _confirm(db: Session, booking: Booking, now: datetime) -> None:
    booking.status = "confirmed"
    for move in booking.displacements:
        move.active = True
    db.flush()
    notify(
        db, [booking.requester], "confirmed", f"{_describe(booking)} is confirmed.", _link(booking)
    )
    notify(
        db,
        [booking.venue.in_charge, booking.venue.technician],
        "event_in_venue",
        f"New event in {booking.venue.code}: {_describe(booking)}"
        + (f". Requirements: {booking.requirements}" if booking.requirements else "."),
        _link(booking),
        skip=booking.requester,
    )
    for move in booking.displacements:
        slot = move.slot
        if move.action == "relocated" and move.new_venue is not None:
            what = f"moves to {move.new_venue.code}"
            extra = [move.new_venue.in_charge, move.new_venue.technician]
        else:
            what = "runs as BYOD in the classroom"
            extra = []
        message = (
            f"On {move.on_date:%a %d %b}, {slot_label(slot)} "
            f"({slot.start:%H:%M}–{slot.end:%H:%M}) {what}, because {slot.venue.code} is "
            f"booked for “{booking.title}”."
        )
        notify(
            db,
            [*faculty_matching(db, slot.faculty_name), slot.venue.technician, *extra],
            "class_moved",
            message,
            _link(booking),
        )
    if booking.parent_id:
        parent = db.get(Booking, booking.parent_id)
        if parent is not None and parent.status in OPEN_STATUSES:
            _release(db, parent, "cancelled", f"Rescheduled to {booking.ref}", now)


_TITLES = re.compile(r"\b(dr|mr|mrs|ms|prof)\b\.?", re.I)


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", _TITLES.sub("", name.lower()))


def faculty_matching(db: Session, name: str | None) -> list[User]:
    """Users whose name matches a timetable's faculty column, ignoring titles and punctuation."""
    if not name:
        return []
    key = _name_key(name)
    return [u for u in db.scalars(select(User).where(User.active)) if _name_key(u.name) == key]


# Waitlist --------------------------------------------------------------------------------------


def _release(db: Session, booking: Booking, status: str, reason: str | None, now: datetime) -> None:
    """End a booking and offer its slot to the waitlist if it was holding one."""
    was_holding = booking.status in HOLDING_STATUSES
    booking.status = status
    booking.cancel_reason = reason
    booking.offer_expires_at = None
    for move in booking.displacements:
        move.active = False
    db.flush()
    if was_holding:
        promote_waitlist(db, booking.venue, now)


def promote_waitlist(db: Session, venue: Venue, now: datetime) -> list[Booking]:
    """Offer freed slots to waitlisted requests, oldest first."""
    offered = []
    waiting = db.scalars(
        select(Booking)
        .where(Booking.venue_id == venue.id, Booking.status == "waitlisted")
        .order_by(Booking.created_at, Booking.id)
    ).all()
    for b in waiting:
        results = [check(db, venue, o.start_dt, o.end_dt, frozenset({b.id})) for o in b.occurrences]
        if any(r.conflicts for r in results):
            continue
        b.status = "offered"
        b.offer_expires_at = now + timedelta(hours=OFFER_HOURS)
        db.flush()  # the offer now holds the slot for later entries in this loop
        notify(
            db,
            [b.requester],
            "offer",
            f"{_describe(b)} is free now. Confirm by {b.offer_expires_at:%d %b %H:%M} "
            "or the slot goes to the next person waiting.",
            _link(b),
        )
        offered.append(b)
    return offered


def waitlist_position(db: Session, booking: Booking) -> int | None:
    if booking.status != "waitlisted":
        return None
    earlier = db.scalars(
        select(Booking).where(
            Booking.venue_id == booking.venue_id,
            Booking.status == "waitlisted",
            Booking.id != booking.id,
            Booking.created_at <= booking.created_at,
            Booking.start_dt < booking.end_dt,
            Booking.end_dt > booking.start_dt,
        )
    ).all()
    ahead = [
        b
        for b in earlier
        if (b.created_at, b.id) < (booking.created_at, booking.id)
        and any(
            o.start_dt < mine.end_dt and mine.start_dt < o.end_dt
            for o in b.occurrences
            for mine in booking.occurrences
        )
    ]
    return len(ahead) + 1


def expire_offers(db: Session, now: datetime) -> int:
    expired = db.scalars(
        select(Booking).where(Booking.status == "offered", Booking.offer_expires_at < now)
    ).all()
    for b in expired:
        notify(
            db,
            [b.requester],
            "offer_expired",
            f"The offer for {_describe(b)} ran out after {OFFER_HOURS} hours.",
            _link(b),
        )
        _release(db, b, "expired", "Offer not confirmed in time", now)
    return len(expired)


# Actions ---------------------------------------------------------------------------------------


def submit(
    db: Session,
    user: User,
    req: BookingRequest,
    *,
    join_waitlist: bool = False,
    reschedule: Booking | None = None,
    via: str = "ui",
    now: datetime | None = None,
) -> Booking:
    now = now or datetime.now()
    if not can(user, "book"):
        raise BookingError("You can't book venues.", 403)
    if reschedule is not None:
        if reschedule.requester_id != user.id:
            raise BookingError("You can only reschedule your own bookings.", 403)
        if reschedule.status not in ("pending_incharge", "pending_hod", "confirmed"):
            raise BookingError("Only pending or confirmed bookings can be rescheduled.")
    if not req.title.strip():
        raise BookingError("Give the event a title.", 422)
    if req.event_type not in EVENT_TYPES:
        raise BookingError("Choose an event type from the list.", 422)
    if req.expected_count < 1:
        raise BookingError("Expected attendance must be at least 1.", 422)
    if req.date_from < now.date():
        raise BookingError("That date has already passed.", 422)

    ignore = frozenset({reschedule.id}) if reschedule else frozenset()
    result = check_request(db, req, ignore)
    venue = result.venue
    if result.blocked:
        raise BookingError(
            f"{venue.code} can't be booked then: {result.blocked[0].label}. "
            "Try another date or venue."
        )
    if req.expected_count > venue.capacity:
        raise BookingError(
            f"{venue.code} seats {venue.capacity}; {req.expected_count} are expected.", 422
        )
    if result.taken and not join_waitlist:
        raise BookingError(
            f"{venue.code} is already booked then ({result.taken[0].label}). "
            "You can join the waitlist instead."
        )
    moves = _plan_moves(db, result, req.moves)

    booking = Booking(
        ref="pending",
        requester=user,
        venue=venue,
        title=req.title.strip(),
        event_type=req.event_type,
        description=req.description,
        expected_count=req.expected_count,
        requirements=req.requirements,
        start_dt=result.occurrences[0][0],
        end_dt=result.occurrences[-1][1],
        status="waitlisted" if result.taken else "draft",
        created_via="assistant" if via == "agent" else "form",
        parent_id=reschedule.id if reschedule else None,
        created_at=now,
        occurrences=[BookingOccurrence(start_dt=s, end_dt=e) for s, e in result.occurrences],
        displacements=moves,
    )
    db.add(booking)
    db.flush()
    booking.ref = f"BK-{now.year}-{booking.id:04d}"
    if booking.status == "waitlisted":
        notify(
            db,
            [user],
            "waitlisted",
            f"{_describe(booking)} is on the waitlist (position "
            f"{waitlist_position(db, booking)}). You'll get an offer if the slot frees up.",
            _link(booking),
        )
    else:
        _route(db, booking, None, now)
    audit.record(
        db,
        user,
        "reschedule" if reschedule else "submit",
        "booking",
        booking.id,
        before={"ref": reschedule.ref} if reschedule else None,
        after={"ref": booking.ref, "venue": venue.code, "status": booking.status},
        via=via,
        at=now,
    )
    return booking


def _plan_moves(db: Session, result: RequestCheck, chosen: list[Move]) -> list[SlotOverride]:
    by_key = {(m.slot_id, m.on_date): m for m in chosen}
    overrides = []
    for clash in result.clashes:
        move = by_key.get((clash.slot.id, clash.on_date))
        what = f"{slot_label(clash.slot)} on {clash.on_date:%d %b}"
        if move is None:
            raise BookingError(
                f"{what} uses {result.venue.code} then. Choose whether it moves to another lab "
                "or runs as BYOD in the classroom.",
                422,
            )
        if move.action == "byod_classroom":
            overrides.append(
                SlotOverride(slot_id=clash.slot.id, on_date=clash.on_date, action=move.action)
            )
        elif move.action == "relocated":
            target = get_venue(db, move.venue_code or "")
            if target is None or target.id not in {o.venue.id for o in clash.options}:
                raise BookingError(
                    f"{move.venue_code or 'That lab'} isn't free or big enough for {what}.", 422
                )
            overrides.append(
                SlotOverride(
                    slot_id=clash.slot.id,
                    on_date=clash.on_date,
                    action="relocated",
                    new_venue_id=target.id,
                )
            )
        else:
            raise BookingError("Unknown way to move a class.", 422)
    return overrides


def approve(
    db: Session,
    user: User,
    booking: Booking,
    comment: str | None = None,
    via: str = "ui",
    now: datetime | None = None,
) -> Booking:
    now = now or datetime.now()
    step = current_step(booking)
    if step is None:
        raise BookingError(f"{booking.ref} isn't waiting for approval.")
    if not can_approve_step(user, booking, step):
        raise BookingError(f"This step needs the {STEP_LABELS[step]}.", 403)
    booking.approvals.append(
        Approval(step=step, approver=user, decision="approved", comment=comment, decided_at=now)
    )
    notify(
        db,
        [booking.requester],
        "approved_step",
        f"{user.name} approved {_describe(booking)}" + (f": “{comment}”" if comment else "."),
        _link(booking),
    )
    _route(db, booking, step, now)
    audit.record(
        db,
        user,
        "approve",
        "booking",
        booking.id,
        after={"step": step, "status": booking.status},
        via=via,
        at=now,
    )
    return booking


def reject(
    db: Session,
    user: User,
    booking: Booking,
    comment: str,
    via: str = "ui",
    now: datetime | None = None,
) -> Booking:
    now = now or datetime.now()
    step = current_step(booking)
    if step is None:
        raise BookingError(f"{booking.ref} isn't waiting for approval.")
    if not can_approve_step(user, booking, step):
        raise BookingError(f"This step needs the {STEP_LABELS[step]}.", 403)
    if not comment or not comment.strip():
        raise BookingError("Say why the request is rejected.", 422)
    booking.approvals.append(
        Approval(step=step, approver=user, decision="rejected", comment=comment, decided_at=now)
    )
    notify(
        db,
        [booking.requester],
        "rejected",
        f"{user.name} rejected {_describe(booking)}: “{comment}”",
        _link(booking),
    )
    _release(db, booking, "rejected", None, now)
    audit.record(db, user, "reject", "booking", booking.id, after={"step": step}, via=via, at=now)
    return booking


def cancel(
    db: Session,
    user: User,
    booking: Booking,
    reason: str | None = None,
    via: str = "ui",
    now: datetime | None = None,
) -> Booking:
    now = now or datetime.now()
    if booking.requester_id != user.id and not can(user, "approve_all"):
        raise BookingError("Only the person who booked can cancel this.", 403)
    if booking.status not in OPEN_STATUSES:
        raise BookingError(f"{booking.ref} is already {booking.status.replace('_', ' ')}.")
    was_confirmed = booking.status == "confirmed"
    _release(db, booking, "cancelled", reason, now)
    if was_confirmed:
        notify(
            db,
            [booking.venue.in_charge, booking.venue.technician, booking.requester],
            "cancelled",
            f"{_describe(booking)} was cancelled" + (f": {reason}" if reason else "."),
            _link(booking),
            skip=user,
        )
    audit.record(
        db, user, "cancel", "booking", booking.id, after={"reason": reason}, via=via, at=now
    )
    return booking


def accept_offer(
    db: Session, user: User, booking: Booking, via: str = "ui", now: datetime | None = None
) -> Booking:
    now = now or datetime.now()
    if booking.requester_id != user.id:
        raise BookingError("Only the person who asked can accept this offer.", 403)
    expire_offers(db, now)
    if booking.status != "offered":
        raise BookingError(f"{booking.ref} has no open offer.")
    booking.offer_expires_at = None
    _route(db, booking, None, now)
    audit.record(db, user, "accept_offer", "booking", booking.id, via=via, at=now)
    return booking


# Approver briefing -----------------------------------------------------------------------------


def request_from(booking: Booking) -> BookingRequest:
    first, last = booking.occurrences[0], booking.occurrences[-1]
    return BookingRequest(
        venue_code=booking.venue.code,
        title=booking.title,
        event_type=booking.event_type,
        expected_count=booking.expected_count,
        date_from=first.start_dt.date(),
        date_to=last.start_dt.date(),
        start_time=first.start_dt.time(),
        end_time=first.end_dt.time(),
    )


def waiting_behind(db: Session, booking: Booking) -> int:
    """Waitlisted requests for an overlapping time in the same venue."""
    waiting = db.scalars(
        select(Booking).where(
            Booking.venue_id == booking.venue_id,
            Booking.status == "waitlisted",
            Booking.start_dt < booking.end_dt,
            Booking.end_dt > booking.start_dt,
        )
    ).all()
    return sum(
        any(
            o.start_dt < mine.end_dt and mine.start_dt < o.end_dt
            for o in w.occurrences
            for mine in booking.occurrences
        )
        for w in waiting
    )


def approval_notes(db: Session, booking: Booking) -> list[str]:
    """Plain-language points for the approver, worked out without the assistant."""
    venue = booking.venue
    notes = []
    spare = venue.capacity - booking.expected_count
    if spare < 0:
        notes.append(
            f"Too small: {venue.code} seats {venue.capacity}, {booking.expected_count} expected."
        )
    else:
        notes.append(f"Capacity fits: {booking.expected_count} expected, {venue.capacity} seats.")
    result = check_request(db, request_from(booking), frozenset({booking.id}))
    if result.blocked:
        notes.append(f"Now clashes with: {result.blocked[0].label}.")
    if result.taken:
        notes.append(f"Overlaps another booking: {result.taken[0].label}.")
    notes += [w.message for w in result.warnings if w.kind != "capacity"]
    for move in booking.displacements:
        slot = move.slot
        what = (
            f"{slot_label(slot)} on {move.on_date:%a %d %b} ({slot.start:%H:%M}–{slot.end:%H:%M})"
        )
        if move.action == "relocated" and move.new_venue:
            option = next(
                (
                    o
                    for o in relocation_options(db, slot, move.on_date, {venue.id}, limit=20)
                    if o.venue.id == move.new_venue_id
                ),
                None,
            )
            if option is None:
                notes.append(f"{what} moves to {move.new_venue.code}, which is no longer free.")
            elif option.missing_software:
                notes.append(
                    f"{what} moves to {move.new_venue.code}, which lacks "
                    f"{', '.join(option.missing_software)}."
                )
            else:
                notes.append(f"{what} moves to {move.new_venue.code}, which has the same software.")
        else:
            notes.append(f"{what} runs as BYOD in the classroom; students bring laptops.")
    first = booking.occurrences[0].start_dt
    if first - booking.created_at < timedelta(days=2):
        notes.append("Short notice: less than two days between the request and the event.")
    behind = waiting_behind(db, booking)
    if behind:
        notes.append(f"{behind} other request(s) are on the waitlist for this slot.")
    return notes
