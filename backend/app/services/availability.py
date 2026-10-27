"""Availability engine.

Each source turns one kind of fact (venue status, seasonal rules, and later timetables and
bookings) into blocks on a venue's day. The same functions back the availability grid, the
booking form and the assistant's tools.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import Venue

SLOT_MINUTES = 30
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
    kind: str  # status | seasonal | closed | (later) class | booking
    label: str
    hard: bool = True

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
    free: bool
    conflicts: list[Block]
    warnings: list[Notice]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0, 0))
    return start, start + timedelta(days=1)


def _in_month_range(month: int, start: int, end: int) -> bool:
    return start <= month <= end if start <= end else month >= start or month <= end


def status_source(db: Session, venue: Venue, day: date) -> tuple[list[Block], list[Notice]]:
    start, end = _day_bounds(day)
    blocks = [
        Block(venue.id, start, end, "status", STATUS_LABELS.get(p.status, p.status.title()))
        for p in venue.status_periods
        if p.from_date <= day and (p.to_date is None or day <= p.to_date)
    ]
    return blocks, []


def seasonal_source(db: Session, venue: Venue, day: date) -> tuple[list[Block], list[Notice]]:
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


def closed_day_source(db: Session, venue: Venue, day: date) -> tuple[list[Block], list[Notice]]:
    if OPEN_HOURS[day.weekday()] is None:
        start, end = _day_bounds(day)
        return [Block(venue.id, start, end, "closed", "Closed on Sundays")], []
    return [], []


Source = Callable[[Session, Venue, date], tuple[list[Block], list[Notice]]]
SOURCES: list[Source] = [closed_day_source, status_source, seasonal_source]


def venue_day(db: Session, venue: Venue, day: date) -> DayView:
    hours = OPEN_HOURS[day.weekday()]
    view = DayView(venue, *(hours or (None, None)))
    for source in SOURCES:
        blocks, notices = source(db, venue, day)
        view.blocks += blocks
        view.warnings += notices
    view.blocks.sort(key=lambda b: (b.start, b.end))
    return view


def check(db: Session, venue: Venue, start: datetime, end: datetime) -> CheckResult:
    """Is the venue free for [start, end)? Multi-day ranges are checked day by day."""
    if end <= start:
        raise ValueError("end must be after start")
    conflicts: list[Block] = []
    warnings: list[Notice] = []
    day = start.date()
    while datetime.combine(day, time(0, 0)) < end:
        view = venue_day(db, venue, day)
        conflicts += [b for b in view.blocks if b.hard and b.overlaps(start, end)]
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
    return CheckResult(free=not conflicts, conflicts=conflicts, warnings=unique)
