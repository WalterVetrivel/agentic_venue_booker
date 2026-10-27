"""Demo bookings, approvals, waitlist history and equipment faults, so the reports have data.

Everything goes through the booking services with explicit timestamps (their `now=` argument),
so the history is the same as if people had used the app over the past few months.
Dates are relative to today, so the data stays current whenever it is loaded.
"""

import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AcademicTerm, Booking, Equipment, Notification, User, UserRole, Venue
from app.services import audit
from app.services import bookings as svc

TITLES = {
    "Workshop": ["Docker and Kubernetes workshop", "Flutter app development workshop"],
    "Hands-on training": ["Power BI hands-on session", "Git and GitHub hands-on training"],
    "Seminar": ["Seminar on responsible AI", "Seminar on cyber security careers"],
    "Guest lecture": [
        "Guest lecture on cloud-native systems",
        "Guest lecture on Gen-AI in industry",
    ],
    "Coding contest": ["CodeSprint coding contest", "Debugging contest for second years"],
    "Hackathon": ["Smart India Hackathon internal round"],
    "Faculty development programme": ["FDP on outcome-based education"],
    "Value-added course": ["Value-added course on full-stack development"],
    "Placement training": ["Aptitude training for final years", "Mock interview day"],
    "Meeting": ["Department meeting", "Class committee meeting"],
}
HALLS = ["DSH", "ESH", "ASH", "MBASH", "CSEPGSH"]
SMALL = ["COE1", "COE2", "COE3", "COE4", "PGLAB", "IOTLAB"]
TIMES = [(time(9, 30), time(12, 30)), (time(13, 30), time(16, 30)), (time(10), time(12))]
TIMES += [(time(14), time(16)), (time(9), time(16, 30))]
MARKER = "Demo booking"  # in the description, so a second run can tell they are already there


def _users(db: Session, role: str) -> list[User]:
    return list(
        db.scalars(select(User).join(UserRole).where(UserRole.role_key == role).order_by(User.id))
    )


def _working_day(day: date) -> date:
    while day.weekday() == 6:
        day += timedelta(days=1)
    return day


def _at(day: date, hour: float) -> datetime:
    return datetime.combine(day, time()) + timedelta(hours=hour)


def _decide(db: Session, b: Booking, when: datetime, rng: random.Random, reject: bool) -> None:
    """Approve (or reject) every pending step, each a while after the last, up to now."""
    while (step := svc.current_step(b)) is not None:
        when += timedelta(hours=rng.choice([1, 2, 3, 5, 8, 20, 26, 44]) + rng.random())
        if when > datetime.now():
            return  # still waiting for this person
        approver = svc._approvers(db, b, step)[0]
        if reject:
            svc.reject(db, approver, b, "The hall is needed for an exam that day.", now=when)
            break
        svc.approve(db, approver, b, now=when)


def seed_bookings(db: Session, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    if db.scalar(select(Booking.id).where(Booking.description.startswith(MARKER))) is not None:
        return {"demo_bookings": 0}
    rng = random.Random(6)
    faculty = _users(db, "faculty")
    first_notification = db.scalar(select(Notification.id).order_by(Notification.id.desc())) or 0
    term = db.scalar(
        select(AcademicTerm).where(AcademicTerm.valid_from <= today, AcademicTerm.valid_to >= today)
    )
    history_from = max(term.valid_from if term else today, today - timedelta(days=120))
    if history_from >= today:
        history_from = today - timedelta(days=90)
    made: list[Booking] = []

    def book(
        venue: str,
        day: date,
        span: tuple[time, time],
        asked: datetime,
        who: User | None = None,
        waitlist: bool = False,
        event_type: str | None = None,
    ) -> Booking | None:
        event_type = event_type or rng.choice(list(TITLES))
        v = db.scalar(select(Venue).where(Venue.code == venue))
        count = min(v.capacity, rng.choice([25, 30, 40, 60, 90, 120, 180]))
        req = svc.BookingRequest(
            venue,
            rng.choice(TITLES[event_type]),
            event_type,
            count,
            day,
            day,
            *span,
            description=f"{MARKER}: {event_type.lower()} for CSE students.",
        )
        try:
            b = svc.submit(db, who or rng.choice(faculty), req, join_waitlist=waitlist, now=asked)
        except svc.BookingError:
            return None  # clashes with a class or another booking: just skip it
        made.append(b)
        return b

    # Past events: requested a few days ahead, approved over hours or days, a few rejected.
    day = history_from
    while day < today - timedelta(days=1):
        day = _working_day(day + timedelta(days=rng.choice([1, 2, 2, 3])))
        if day >= today:
            break
        venue = rng.choice(HALLS + SMALL)
        asked = _at(day - timedelta(days=rng.randint(3, 12)), 9 + rng.random() * 7)
        if asked.date() < history_from - timedelta(days=14):
            continue
        b = book(venue, day, rng.choice(TIMES), asked)
        if b is not None:
            _decide(db, b, asked, rng, reject=rng.random() < 0.1)
        db.flush()

    # Waitlist stories in the past: one converted, one lapsed, one withdrawn.
    for n, ending in enumerate(["converted", "lapsed", "withdrawn"]):
        day = _working_day(today - timedelta(days=30 - 8 * n))
        asked = _at(day - timedelta(days=10), 10)
        first = book("ESH", day, (time(10), time(13)), asked, event_type="Guest lecture")
        if first is None:
            continue
        _decide(db, first, asked, rng, reject=False)
        late = book("ESH", day, (time(10), time(13)), asked + timedelta(days=1), waitlist=True)
        if late is None:
            continue
        if ending == "withdrawn":
            svc.cancel(
                db, late.requester, late, "Moved the event online", now=asked + timedelta(days=2)
            )
            continue
        freed = asked + timedelta(days=3)
        svc.cancel(db, first.requester, first, "Speaker postponed", now=freed)
        if ending == "lapsed":
            svc.expire_offers(db, freed + timedelta(hours=svc.OFFER_HOURS + 1))
        else:
            accepted = freed + timedelta(hours=5)
            svc.accept_offer(db, late.requester, late, now=accepted)
            _decide(db, late, accepted, rng, reject=False)
        db.flush()

    # Coming up: some confirmed, some still waiting for the in-charge or the HOD.
    now = datetime.now().replace(second=0, microsecond=0)
    for n in range(12):
        day = _working_day(today + timedelta(days=2 + n * 2))
        asked = now - timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 6))
        b = book(rng.choice(HALLS + SMALL), day, rng.choice(TIMES), asked)
        if b is not None and n % 3:
            _decide(db, b, asked, rng, reject=False)
    # A request on the waitlist right now, behind a confirmed booking.
    day = _working_day(today + timedelta(days=9))
    asked = now - timedelta(days=2)
    held = book("DSH", day, (time(10), time(13)), asked, event_type="Seminar")
    if held is not None:
        _decide(db, held, asked, rng, reject=False)
        book("DSH", day, (time(10), time(13)), asked + timedelta(hours=6), waitlist=True)

    faults = _equipment_history(db, rng, history_from, today)

    # Keep notifications only for what is still open; the rest is history nobody needs pinged.
    open_ids = {b.id for b in made if b.status.startswith("pending_") or b.status == "offered"}
    keep = {f"/bookings/{i}" for i in open_ids} | {"/approvals"}
    db.execute(
        delete(Notification).where(
            Notification.id > first_notification, Notification.link.not_in(keep)
        )
    )
    db.commit()
    return {"demo_bookings": len(made), "equipment_faults": faults}


def _equipment_history(db: Session, rng: random.Random, start: date, today: date) -> int:
    """Faults reported by technicians and in-charges; most were fixed, a few are still out."""
    items = db.scalars(
        select(Equipment)
        .join(Venue)
        .where(Equipment.category.in_(("hardware", "av")))
        .order_by(Equipment.id)
    ).all()
    span = (today - start).days
    count = 0
    for n, item in enumerate(rng.sample(list(items), min(10, len(items)))):
        reporter = item.venue.technician or item.venue.in_charge
        when = _at(start + timedelta(days=rng.randint(0, max(span - 3, 0))), 9 + rng.random() * 8)
        status = "faulty" if n % 3 else "under_repair"
        via = "agent" if n % 4 == 1 else "ui"
        audit.record(
            db,
            reporter,
            "update",
            "equipment",
            item.id,
            before={"status": "working"},
            after={"status": status},
            via=via,
            at=when,
        )
        count += 1
        if n < 7:  # fixed a few days later
            fixed = when + timedelta(days=rng.randint(1, 5))
            if fixed.date() < today:
                audit.record(
                    db,
                    reporter,
                    "update",
                    "equipment",
                    item.id,
                    before={"status": status},
                    after={"status": "working"},
                    at=fixed,
                )
                continue
        item.status = status
        item.updated_at = when
        item.updated_by_id = reporter.id if reporter else None
    return count
