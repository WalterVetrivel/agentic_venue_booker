"""Reports: venue utilisation, events, approval turnaround, waitlist and equipment faults.

Everything is worked out from the same tables the rest of the app uses, for the venues the
person may report on (their own venues, CSE venues, or all of them).
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Approval,
    AuditLog,
    Booking,
    BookingOccurrence,
    Equipment,
    PastEvent,
    SeasonalRule,
    SlotOverride,
    TimetableSlot,
    User,
    Venue,
    VenueStatusPeriod,
)
from app.services.access import can
from app.services.availability import OPEN_HOURS

MAX_DAYS = 400  # a little over an academic year
REPORT_CAPABILITIES = ("reports_all", "reports_cse", "reports_own")
OUT_OF_SERVICE = ("faulty", "under_repair")
WAITLIST_OUTCOMES = {
    "confirmed": "Got the venue",
    "pending_guide": "Got the venue",
    "pending_incharge": "Got the venue",
    "pending_hod": "Got the venue",
    "offered": "Offered, waiting for a reply",
    "waitlisted": "Still waiting",
    "expired": "Offer lapsed",
    "cancelled": "Withdrawn",
    "rejected": "Rejected",
}


class ReportError(Exception):
    pass


@dataclass
class Scope:
    label: str
    venues: list[Venue]

    @property
    def ids(self) -> set[int]:
        return {v.id for v in self.venues}


def can_report(user: User | None) -> bool:
    return any(can(user, c) for c in REPORT_CAPABILITIES)


def scope_for(db: Session, user: User | None) -> Scope:
    """The venues this person can report on; their scopes add up when they hold several roles."""
    venues = db.scalars(select(Venue).order_by(Venue.type, Venue.code)).unique().all()
    if can(user, "reports_all"):
        return Scope("All venues", list(venues))
    parts, chosen = [], set()
    if can(user, "reports_cse"):
        parts.append("CSE venues")
        chosen |= {v.id for v in venues if v.department == "CSE"}
    if can(user, "reports_own") and user is not None:
        own = [v for v in venues if v.in_charge_id == user.id]
        new = [v.code for v in own if v.id not in chosen]
        if new:
            parts.append("your venues (" + ", ".join(new) + ")")
        chosen |= {v.id for v in own}
    if not parts:
        raise ReportError("You don't have access to reports.")
    label = " and ".join(parts)
    return Scope(label[0].upper() + label[1:], [v for v in venues if v.id in chosen])


def default_period(db: Session, today: date) -> tuple[date, date, str]:
    """The current semester up to today, or the last 90 days outside the semester."""
    term = db.scalar(
        select(AcademicTerm).where(AcademicTerm.valid_from <= today, AcademicTerm.valid_to >= today)
    )
    if term is not None:
        return term.valid_from, today, f"{term.name} semester so far"
    return today - timedelta(days=89), today, "Last 90 days"


def check_period(start: date, end: date) -> None:
    if end < start:
        raise ReportError("The end date is before the start date.")
    if (end - start).days + 1 > MAX_DAYS:
        raise ReportError(f"Choose a period of at most {MAX_DAYS} days.")


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _union(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for a, b in sorted(s for s in spans if s[1] > s[0]):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def _length(spans: list[tuple[int, int]]) -> int:
    return sum(b - a for a, b in spans)


def _clip(spans, lo: int, hi: int) -> list[tuple[int, int]]:
    return [(max(a, lo), min(b, hi)) for a, b in spans if b > lo and a < hi]


def _hours(minutes: int) -> float:
    return round(minutes / 60, 1)


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


# Utilisation --------------------------------------------------------------------------------------


def _closed_days(db: Session, ids: set[int], start: date, end: date) -> dict[int, set[date]]:
    closed: dict[int, set[date]] = defaultdict(set)
    periods = db.scalars(
        select(VenueStatusPeriod).where(
            VenueStatusPeriod.venue_id.in_(ids),
            VenueStatusPeriod.from_date <= end,
            (VenueStatusPeriod.to_date.is_(None)) | (VenueStatusPeriod.to_date >= start),
        )
    ).all()
    for p in periods:
        for day in _days(max(p.from_date, start), min(p.to_date or end, end)):
            closed[p.venue_id].add(day)
    rules = db.scalars(
        select(SeasonalRule).where(SeasonalRule.venue_id.in_(ids), SeasonalRule.kind == "blocked")
    ).all()
    for r in rules:
        for day in _days(start, end):
            m = day.month
            inside = (
                r.start_month <= m <= r.end_month
                if r.start_month <= r.end_month
                else m >= r.start_month or m <= r.end_month
            )
            if inside:
                closed[r.venue_id].add(day)
    return closed


def _class_spans(db: Session, ids: set[int], start: date, end: date):
    """(venue_id, day) -> class time in minutes, with moved classes taken into account."""
    slots = db.scalars(
        select(TimetableSlot)
        .join(AcademicTerm)
        .where(AcademicTerm.valid_from <= end, AcademicTerm.valid_to >= start)
    ).all()
    by_weekday: dict[int, list[TimetableSlot]] = defaultdict(list)
    for s in slots:
        by_weekday[s.weekday].append(s)
    overrides = db.scalars(
        select(SlotOverride).where(
            SlotOverride.active, SlotOverride.on_date >= start, SlotOverride.on_date <= end
        )
    ).all()
    moved = {(o.slot_id, o.on_date): o for o in overrides}
    spans: dict[tuple[int, date], list[tuple[int, int]]] = defaultdict(list)
    for day in _days(start, end):
        for s in by_weekday.get(day.weekday(), []):
            if not (s.term.valid_from <= day <= s.term.valid_to):
                continue
            span = (_minutes(s.start), _minutes(s.end))
            o = moved.get((s.id, day))
            if o is None:
                if s.venue_id in ids:
                    spans[(s.venue_id, day)].append(span)
            elif o.action == "relocated" and o.new_venue_id in ids:
                spans[(o.new_venue_id, day)].append(span)
    return spans


def _event_spans(db: Session, ids: set[int], start: date, end: date):
    spans: dict[tuple[int, date], list[tuple[int, int]]] = defaultdict(list)
    occurrences = db.execute(
        select(BookingOccurrence.start_dt, BookingOccurrence.end_dt, Booking.venue_id)
        .join(Booking)
        .where(
            Booking.status == "confirmed",
            Booking.venue_id.in_(ids),
            BookingOccurrence.start_dt >= datetime.combine(start, time.min),
            BookingOccurrence.start_dt <= datetime.combine(end, time.max),
        )
    ).all()
    for s, e, venue_id in occurrences:
        spans[(venue_id, s.date())].append((_minutes(s.time()), _minutes(e.time())))
    for ev in _past_events(db, ids, start, end):
        if ev.start_time is None or ev.end_time is None:
            continue
        span = (_minutes(ev.start_time), _minutes(ev.end_time))
        for day in _days(max(ev.start_date, start), min(ev.end_date or ev.start_date, end)):
            for v in ev.venues:
                if v.id in ids:
                    spans[(v.id, day)].append(span)
    return spans


def utilisation(db: Session, scope: Scope, start: date, end: date) -> dict:
    ids = scope.ids
    closed = _closed_days(db, ids, start, end)
    classes = _class_spans(db, ids, start, end)
    events = _event_spans(db, ids, start, end)
    rows = []
    for v in scope.venues:
        open_m = closed_m = class_m = event_m = 0
        for day in _days(start, end):
            hours = OPEN_HOURS[day.weekday()]
            if hours is None:
                continue
            lo, hi = _minutes(hours[0]), _minutes(hours[1])
            if day in closed.get(v.id, ()):
                closed_m += hi - lo
                continue
            open_m += hi - lo
            cls = _union(_clip(classes.get((v.id, day), []), lo, hi))
            both = _union(cls + _clip(events.get((v.id, day), []), lo, hi))
            class_m += _length(cls)
            event_m += _length(both) - _length(cls)
        rows.append(
            {
                "venue": v.code,
                "name": v.name,
                "type": v.type,
                "department": v.department,
                "open_hours": _hours(open_m),
                "closed_hours": _hours(closed_m),
                "class_hours": _hours(class_m),
                "event_hours": _hours(event_m),
                "free_hours": _hours(open_m - class_m - event_m),
                "class_pct": _pct(class_m, open_m),
                "event_pct": _pct(event_m, open_m),
                "used_pct": _pct(class_m + event_m, open_m),
                "_m": (open_m, class_m, event_m),
            }
        )
    open_t = sum(r["_m"][0] for r in rows)
    class_t = sum(r["_m"][1] for r in rows)
    event_t = sum(r["_m"][2] for r in rows)
    for r in rows:
        del r["_m"]
    return {
        "venues": rows,
        "total": {
            "open_hours": _hours(open_t),
            "class_hours": _hours(class_t),
            "event_hours": _hours(event_t),
            "class_pct": _pct(class_t, open_t),
            "event_pct": _pct(event_t, open_t),
            "used_pct": _pct(class_t + event_t, open_t),
        },
    }


# Events -------------------------------------------------------------------------------------------


def _past_events(db: Session, ids: set[int], start: date, end: date) -> list[PastEvent]:
    found = db.scalars(
        select(PastEvent).where(PastEvent.start_date <= end, PastEvent.start_date >= start)
    ).all()
    return [e for e in found if any(v.id in ids for v in e.venues)]


def events(db: Session, scope: Scope, start: date, end: date) -> dict:
    """Held or confirmed events: past events from circulars and reports, plus confirmed bookings."""
    rows = [
        {
            "date": e.start_date.isoformat(),
            "title": e.title,
            "event_type": e.event_type,
            "department": e.department or "Not stated",
            "venues": ", ".join(v.code for v in e.venues),
            "participants": e.participants,
            "source": "Past event",
            "ref": e.circular.ref_no if e.circular else None,
        }
        for e in _past_events(db, scope.ids, start, end)
    ]
    bookings = db.scalars(
        select(Booking).where(
            Booking.status == "confirmed",
            Booking.venue_id.in_(scope.ids),
            Booking.start_dt >= datetime.combine(start, time.min),
            Booking.start_dt <= datetime.combine(end, time.max),
        )
    ).all()
    rows += [
        {
            "date": b.start_dt.date().isoformat(),
            "title": b.title,
            "event_type": b.event_type,
            "department": "CSE",  # bookings are made by CSE staff
            "venues": b.venue.code,
            "participants": b.expected_count,
            "source": "Booking",
            "ref": b.ref,
        }
        for b in bookings
    ]
    rows.sort(key=lambda r: (r["date"], r["title"]))
    months = [f"{d:%Y-%m}" for d in _days(start, end) if d.day == 1 or d == start]
    by_month = Counter(r["date"][:7] for r in rows)
    return {
        "count": len(rows),
        "by_type": _counted(Counter(r["event_type"] for r in rows)),
        "by_department": _counted(Counter(r["department"] for r in rows)),
        "by_month": [{"month": m, "count": by_month.get(m, 0)} for m in months],
        "rows": rows,
    }


def _counted(counter: Counter) -> list[dict]:
    return [
        {"name": k, "count": n} for k, n in sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    ]


# Approval turnaround ------------------------------------------------------------------------------


def _offer_accepted_at(db: Session, booking_ids: set[int]) -> dict[int, datetime]:
    if not booking_ids:
        return {}
    logs = db.scalars(
        select(AuditLog).where(
            AuditLog.entity == "booking",
            AuditLog.action == "accept_offer",
            AuditLog.entity_id.in_(booking_ids),
        )
    ).all()
    return {log.entity_id: log.at for log in logs}


def _stats(hours: list[float]) -> dict:
    if not hours:
        return {"count": 0, "average_hours": None, "median_hours": None}
    return {
        "count": len(hours),
        "average_hours": round(mean(hours), 1),
        "median_hours": round(median(hours), 1),
    }


def turnaround(db: Session, scope: Scope, start: date, end: date) -> dict:
    """How long each approval step took, from when it became that person's turn."""
    decided = db.scalars(
        select(Approval)
        .join(Booking)
        .where(
            Booking.venue_id.in_(scope.ids),
            Approval.decided_at >= datetime.combine(start, time.min),
            Approval.decided_at <= datetime.combine(end, time.max),
        )
        .order_by(Approval.decided_at)
    ).all()
    # Steps approved automatically (the requester, or a student group's guide, could approve
    # them) took no time and would skew the numbers.
    decided = [
        a
        for a in decided
        if a.approver_id != a.booking.requester_id
        and not (a.comment or "").startswith("Approved automatically")
    ]
    accepted = _offer_accepted_at(db, {a.booking_id for a in decided})
    rows = []
    for a in decided:
        b = a.booking
        began = max(
            [b.created_at, accepted.get(b.id, b.created_at)]
            + [p.decided_at for p in b.approvals if p.decided_at < a.decided_at]
        )
        hours = round((a.decided_at - began).total_seconds() / 3600, 1)
        rows.append(
            {
                "ref": b.ref,
                "venue": b.venue.code,
                "step": a.step,
                "decision": a.decision,
                "approver": a.approver.name if a.approver else "",
                "waiting_since": began.isoformat(timespec="minutes"),
                "decided_at": a.decided_at.isoformat(timespec="minutes"),
                "hours": max(hours, 0.0),
            }
        )
    by_step = {
        step: _stats([r["hours"] for r in rows if r["step"] == step])
        for step in ("guide", "incharge", "hod")
    }
    return {
        **_stats([r["hours"] for r in rows]),
        "within_a_day": sum(r["hours"] <= 24 for r in rows),
        "approved": sum(r["decision"] == "approved" for r in rows),
        "rejected": sum(r["decision"] == "rejected" for r in rows),
        "by_step": by_step,
        "rows": rows,
    }


# Waitlist -----------------------------------------------------------------------------------------


def waitlist(db: Session, scope: Scope, start: date, end: date) -> dict:
    """Requests that joined a waitlist in the period, and what became of them."""
    joined = db.scalars(
        select(AuditLog).where(
            AuditLog.entity == "booking",
            AuditLog.action.in_(("submit", "reschedule")),
            AuditLog.at >= datetime.combine(start, time.min),
            AuditLog.at <= datetime.combine(end, time.max),
        )
    ).all()
    ids = {
        log.entity_id
        for log in joined
        if log.after and json.loads(log.after).get("status") == "waitlisted"
    }
    bookings = (
        db.scalars(
            select(Booking)
            .where(Booking.id.in_(ids), Booking.venue_id.in_(scope.ids))
            .order_by(Booking.created_at)
        ).all()
        if ids
        else []
    )
    accepted = _offer_accepted_at(db, {b.id for b in bookings})
    rows = [
        {
            "ref": b.ref,
            "venue": b.venue.code,
            "title": b.title,
            "requester": b.requester_name,
            "joined": b.created_at.isoformat(timespec="minutes"),
            "status": b.status,
            "outcome": WAITLIST_OUTCOMES.get(b.status, b.status.replace("_", " ").capitalize()),
            "converted": b.id in accepted,
        }
        for b in bookings
    ]
    converted = sum(r["converted"] for r in rows)
    return {
        "count": len(rows),
        "converted": converted,
        "conversion_pct": _pct(converted, len(rows)),
        "outcomes": _counted(Counter(r["outcome"] for r in rows)),
        "rows": rows,
    }


# Equipment ----------------------------------------------------------------------------------------


def equipment(db: Session, scope: Scope, start: date, end: date) -> dict:
    """Faults reported in the period, and what is out of service now."""
    items = {
        e.id: e
        for e in db.scalars(select(Equipment).where(Equipment.venue_id.in_(scope.ids))).all()
    }
    logs = (
        db.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity == "equipment",
                AuditLog.action == "update",
                AuditLog.entity_id.in_(items),
                AuditLog.at >= datetime.combine(start, time.min),
                AuditLog.at <= datetime.combine(end, time.max),
            )
            .order_by(AuditLog.at)
        ).all()
        if items
        else []
    )
    names = {
        u.id: u.name
        for u in db.scalars(select(User).where(User.id.in_({log.actor_id for log in logs})))
    }
    reports = []
    for log in logs:
        status = json.loads(log.after or "{}").get("status")
        if status not in OUT_OF_SERVICE:
            continue
        item = items[log.entity_id]
        reports.append(
            {
                "date": log.at.isoformat(timespec="minutes"),
                "venue": item.venue.code,
                "item": item.name,
                "status": status,
                "reported_by": names.get(log.actor_id, ""),
                "via": "Assistant" if log.via == "agent" else "App",
            }
        )
    out_now = [
        {
            "venue": e.venue.code,
            "item": e.name,
            "status": e.status,
            "since": e.updated_at.isoformat(timespec="minutes") if e.updated_at else None,
        }
        for e in sorted(items.values(), key=lambda e: (e.venue.code, e.name))
        if e.status in OUT_OF_SERVICE
    ]
    return {
        "count": len(reports),
        "by_venue": _counted(Counter(r["venue"] for r in reports)),
        "out_of_service": out_now,
        "rows": reports,
    }


# Everything ---------------------------------------------------------------------------------------

SECTIONS = {
    "utilisation": utilisation,
    "events": events,
    "turnaround": turnaround,
    "waitlist": waitlist,
    "equipment": equipment,
}


def summary(db: Session, user: User | None, start: date, end: date) -> dict:
    check_period(start, end)
    scope = scope_for(db, user)
    return {
        "scope": scope.label,
        "venues": [v.code for v in scope.venues],
        "from": start.isoformat(),
        "to": end.isoformat(),
        **{name: fn(db, scope, start, end) for name, fn in SECTIONS.items()},
    }


# CSV columns per section: (key, heading)
CSV_COLUMNS = {
    "utilisation": [
        ("venue", "Venue"),
        ("name", "Name"),
        ("department", "Department"),
        ("open_hours", "Open hours"),
        ("class_hours", "Class hours"),
        ("event_hours", "Event hours"),
        ("free_hours", "Free hours"),
        ("closed_hours", "Closed hours"),
        ("class_pct", "Class %"),
        ("event_pct", "Event %"),
        ("used_pct", "Used %"),
    ],
    "events": [
        ("date", "Date"),
        ("title", "Title"),
        ("event_type", "Type"),
        ("department", "Department"),
        ("venues", "Venues"),
        ("participants", "Participants"),
        ("source", "Source"),
        ("ref", "Reference"),
    ],
    "turnaround": [
        ("ref", "Booking"),
        ("venue", "Venue"),
        ("step", "Step"),
        ("decision", "Decision"),
        ("approver", "Approver"),
        ("waiting_since", "Waiting since"),
        ("decided_at", "Decided at"),
        ("hours", "Hours taken"),
    ],
    "waitlist": [
        ("ref", "Booking"),
        ("venue", "Venue"),
        ("title", "Title"),
        ("requester", "Requested by"),
        ("joined", "Joined waitlist"),
        ("outcome", "Outcome"),
        ("converted", "Accepted an offer"),
    ],
    "equipment": [
        ("date", "Date"),
        ("venue", "Venue"),
        ("item", "Item"),
        ("status", "Status"),
        ("reported_by", "Reported by"),
        ("via", "Via"),
    ],
}


def section_rows(db: Session, user: User | None, section: str, start: date, end: date) -> list:
    if section not in SECTIONS:
        raise ReportError(f"There is no {section} report.")
    check_period(start, end)
    data = SECTIONS[section](db, scope_for(db, user), start, end)
    return data["venues"] if section == "utilisation" else data["rows"]
