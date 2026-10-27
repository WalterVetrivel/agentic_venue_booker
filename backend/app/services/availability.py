"""Availability engine.

Each source turns one kind of fact (venue status, seasonal rules, timetabled classes and
bookings) into blocks on a venue's day. The same functions back the availability grid, the
booking form and the assistant's tools.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingOccurrence, SlotOverride, Venue

SLOT_MINUTES = 30
# Booking states that hold a venue (anything else, like a waitlist entry, does not).
HOLDING_STATUSES = ("pending_incharge", "pending_hod", "confirmed", "offered")
# Bookable hours by weekday (Mon=0). Sunday is closed.
OPEN_HOURS: dict[int, tuple[time, time] | None] = {
    **{d: (time(8, 0), time(18, 0)) for d in range(5)},
    5: (time(8, 0), time(17, 0)),
    6: None,
}

STATUS_LABELS = {
    "maintenance": "Under maintenance",
    "renovation": "Under renovation",
    "closed": "Closed",
}


@dataclass
class Block:
    venue_id: int
    start: datetime
    end: datetime
    kind: str  # status | seasonal | closed | class | booking | pending
    label: str
    hard: bool = True
    ref: int | None = None  # timetable slot id for classes, booking id for bookings

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start < end and start < self.end


@dataclass
class Notice:
    venue_id: int
    kind: str
    message: str


@dataclass
class DayView:
    venue: Venue
    open_from: time | None
    open_to: time | None
    blocks: list[Block] = field(default_factory=list)
    warnings: list[Notice] = field(default_factory=list)


@dataclass
class CheckResult:
    free: bool  # nothing at all in the way
    conflicts: list[Block]  # hard blocks: closed, maintenance, booked
    classes: list[Block]  # timetabled classes; an event can displace them with HOD approval
    warnings: list[Notice]

    @property
    def needs_displacement(self) -> bool:
        return not self.conflicts and bool(self.classes)

    @property
    def taken(self) -> list[Block]:
        """Conflicts with other bookings; the requester can join the waitlist for these."""
        return [b for b in self.conflicts if b.kind in BOOKING_KINDS]

    @property
    def blocked(self) -> list[Block]:
        """Conflicts nobody can book around (closed, maintenance, reserved season)."""
        return [b for b in self.conflicts if b.kind not in BOOKING_KINDS]


BOOKING_KINDS = ("booking", "pending")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0, 0))
    return start, start + timedelta(days=1)


def _in_month_range(month: int, start: int, end: int) -> bool:
    return start <= month <= end if start <= end else month >= start or month <= end


def status_source(
    db: Session, venue: Venue, day: date, ignore: frozenset[int]
) -> tuple[list[Block], list[Notice]]:
    start, end = _day_bounds(day)
    blocks = [
        Block(venue.id, start, end, "status", STATUS_LABELS.get(p.status, p.status.title()))
        for p in venue.status_periods
        if p.from_date <= day and (p.to_date is None or day <= p.to_date)
    ]
    return blocks, []


def seasonal_source(
    db: Session, venue: Venue, day: date, ignore: frozenset[int]
) -> tuple[list[Block], list[Notice]]:
    start, end = _day_bounds(day)
    blocks, notices = [], []
    for rule in venue.seasonal_rules:
        if not _in_month_range(day.month, rule.start_month, rule.end_month):
            continue
        if rule.kind == "blocked":
            blocks.append(Block(venue.id, start, end, "seasonal", rule.reason))
        else:
            notices.append(Notice(venue.id, "seasonal", rule.reason))
    return blocks, notices


def closed_day_source(
    db: Session, venue: Venue, day: date, ignore: frozenset[int]
) -> tuple[list[Block], list[Notice]]:
    if OPEN_HOURS[day.weekday()] is None:
        start, end = _day_bounds(day)
        return [Block(venue.id, start, end, "closed", "Closed on Sundays")], []
    return [], []


def class_source(
    db: Session, venue: Venue, day: date, ignore: frozenset[int]
) -> tuple[list[Block], list[Notice]]:
    """Timetabled classes, minus those moved out for a confirmed booking, plus those moved in."""
    from app.services.timetables import as_datetime, slot_label, slots_on

    overrides = [
        o
        for o in db.scalars(
            select(SlotOverride).where(SlotOverride.on_date == day, SlotOverride.active)
        )
        if o.booking_id not in ignore
    ]
    moved_out = {o.slot_id for o in overrides}
    blocks = [
        Block(
            venue.id,
            as_datetime(day, slot.start),
            as_datetime(day, slot.end),
            "class",
            slot_label(slot),
            hard=False,
            ref=slot.id,
        )
        for slot in slots_on(db, venue.id, day)
        if slot.id not in moved_out
    ]
    # A class relocated here can't be moved again, so it is a hard block.
    blocks += [
        Block(
            venue.id,
            as_datetime(day, o.slot.start),
            as_datetime(day, o.slot.end),
            "class",
            f"{slot_label(o.slot)} (moved from {o.slot.venue.code})",
            ref=o.slot_id,
        )
        for o in overrides
        if o.new_venue_id == venue.id
    ]
    return blocks, []


def booking_source(
    db: Session, venue: Venue, day: date, ignore: frozenset[int]
) -> tuple[list[Block], list[Notice]]:
    start, end = _day_bounds(day)
    rows = db.execute(
        select(BookingOccurrence, Booking)
        .join(Booking)
        .where(
            Booking.venue_id == venue.id,
            Booking.status.in_(HOLDING_STATUSES),
            BookingOccurrence.start_dt < end,
            BookingOccurrence.end_dt > start,
        )
    ).all()
    blocks = [
        Block(
            venue.id,
            occ.start_dt,
            occ.end_dt,
            "booking" if b.status == "confirmed" else "pending",
            b.title if b.status == "confirmed" else f"{b.title} (awaiting approval)",
            ref=b.id,
        )
        for occ, b in rows
        if b.id not in ignore
    ]
    return blocks, []


Source = Callable[[Session, Venue, date, frozenset[int]], tuple[list[Block], list[Notice]]]
SOURCES: list[Source] = [
    closed_day_source,
    status_source,
    seasonal_source,
    class_source,
    booking_source,
]


def venue_day(
    db: Session, venue: Venue, day: date, ignore: frozenset[int] = frozenset()
) -> DayView:
    """`ignore` lists booking ids to leave out, e.g. the booking being rescheduled."""
    hours = OPEN_HOURS[day.weekday()]
    view = DayView(venue, *(hours or (None, None)))
    for source in SOURCES:
        blocks, notices = source(db, venue, day, ignore)
        view.blocks += blocks
        view.warnings += notices
    view.blocks.sort(key=lambda b: (b.start, b.end))
    return view


def check(
    db: Session,
    venue: Venue,
    start: datetime,
    end: datetime,
    ignore: frozenset[int] = frozenset(),
) -> CheckResult:
    """Is the venue free for [start, end)? Multi-day ranges are checked day by day."""
    if end <= start:
        raise ValueError("end must be after start")
    conflicts: list[Block] = []
    classes: list[Block] = []
    warnings: list[Notice] = []
    day = start.date()
    while datetime.combine(day, time(0, 0)) < end:
        view = venue_day(db, venue, day, ignore)
        conflicts += [b for b in view.blocks if b.hard and b.overlaps(start, end)]
        classes += [b for b in view.blocks if not b.hard and b.overlaps(start, end)]
        warnings += view.warnings
        if view.open_from and view.open_to:
            day_start = max(start, datetime.combine(day, time(0, 0)))
            day_end = min(end, datetime.combine(day + timedelta(days=1), time(0, 0)))
            if day_start.time() < view.open_from or (
                day_end.time() > view.open_to or day_end.date() > day
            ):
                warnings.append(
                    Notice(
                        venue.id,
                        "hours",
                        f"Outside normal hours ({view.open_from:%H:%M}–{view.open_to:%H:%M}) on "
                        f"{day:%d %b}; the in-charge must agree.",
                    )
                )
        day += timedelta(days=1)
    # Same notice can repeat across days of a multi-day range.
    unique = list({(w.kind, w.message): w for w in warnings}.values())
    return CheckResult(
        free=not conflicts and not classes, conflicts=conflicts, classes=classes, warnings=unique
    )
