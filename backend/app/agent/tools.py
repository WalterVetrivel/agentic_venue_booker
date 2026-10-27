"""The assistant's tools: one registry shared by the MCP server (/mcp) and the in-app agent.

Each tool says who may use it (capabilities, or "anyone"), and the functions it calls run the
same permission checks as the REST API. Tools never change data. A "draft" fills in the booking
form and a "proposal" returns a card the user confirms in the app, which then calls the normal
REST endpoint.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.dates import resolve
from app.models import (
    Booking,
    ClassSection,
    Equipment,
    PastEvent,
    PastEventVenue,
    TimetableSlot,
    TimetableUpload,
    User,
    Venue,
)
from app.permissions import capabilities_for
from app.services import availability
from app.services import bookings as booking_svc
from app.services import documents as document_svc
from app.services.access import can, can_update_equipment
from app.services.timetables import resolve_venue, review
from app.services.venues import find_venues, get_venue

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
APPROVER_CAPS = ("approve_own_venues", "approve_cse_venues", "approve_all", "approve_displacement")
HANDS_ON = {
    "Workshop",
    "Hands-on training",
    "Value-added course",
    "Coding contest",
    "Hackathon",
    "Model practical exam",
    "Placement training",
    "Professional elective class",
}
STATUS_TEXT = {
    "pending_incharge": "waiting for the venue in-charge",
    "pending_hod": "waiting for the HOD",
    "confirmed": "confirmed",
    "waitlisted": "on the waitlist",
    "offered": "offered from the waitlist (accept within 24 hours)",
    "rejected": "rejected",
    "cancelled": "cancelled",
    "expired": "expired",
}
TALKS = {
    "Seminar",
    "Guest lecture",
    "Awareness programme",
    "Conference",
    "Inauguration",
    "Valedictory",
    "Admission activity",
    "Address by HOD, Principal or Chairman",
    "Meeting",
}


class ToolError(Exception):
    """A problem the model should see and explain (bad input, no access, not found)."""


@dataclass
class ToolResult:
    data: Any  # JSON-ready; this is what the model reads
    card: dict | None = None  # a draft or proposal for the user to act on


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[[Session, User | None, Any], ToolResult]
    kind: Literal["read", "draft", "proposal"] = "read"
    any_of: tuple[str, ...] = ()  # capabilities; empty means everyone, including students
    login: bool = False  # staff only, even if no capability is needed
    label: str = ""  # shown in the chat while the tool runs, e.g. "Checking availability"

    def allowed(self, user: User | None) -> bool:
        if (self.login or self.any_of) and user is None:
            return False
        if not self.any_of:
            return True
        caps = capabilities_for(user.role_keys if user else None)
        return any(c in caps for c in self.any_of)

    def schema(self) -> dict:
        return _clean_schema(self.args.model_json_schema())


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, *, label: str, **options) -> Callable:
    def register(fn):
        args = fn.__annotations__["args"]
        REGISTRY[name] = Tool(name, description, args, fn, label=label, **options)
        return fn

    return register


def tools_for(user: User | None) -> list[Tool]:
    return [t for t in REGISTRY.values() if t.allowed(user)]


def call(db: Session, user: User | None, name: str, raw: dict | None) -> ToolResult:
    t = REGISTRY.get(name)
    if t is None:
        raise ToolError(f"There is no tool called {name}.")
    if not t.allowed(user):
        raise ToolError("You don't have access to that." if user else "Please log in for that.")
    try:
        args = t.args.model_validate(raw or {})
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(map(str, x['loc'])) or 'input'}: {x['msg']}" for x in e.errors()
        )
        raise ToolError(f"Invalid arguments: {problems}") from e
    try:
        return t.fn(db, user, args)
    except booking_svc.BookingError as e:
        raise ToolError(str(e)) from e


def _clean_schema(schema: dict) -> dict:
    """Small models do better with plain schemas: no titles, no $defs, optional = not required."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            props = node.get("properties")
            node = {k: walk(v) for k, v in node.items() if k not in ("title", "properties")}
            if props is not None:  # property names aren't keywords: a field may be called "title"
                node["properties"] = {name: walk(p) for name, p in props.items()}
            # Groq checks "format": "time" as RFC 3339 (HH:MM:SS+zone), which models don't
            # write. The tools accept HH:MM, so say that instead.
            if node.get("format") == "time":
                node.pop("format")
                node.setdefault("description", "24-hour time, HH:MM")
                node["pattern"] = r"^\d{2}:\d{2}(:\d{2})?$"
            # `x: str | None` becomes anyOf [str, null]; keep just the real type.
            options = [o for o in node.get("anyOf", []) if o.get("type") != "null"]
            if "anyOf" in node and len(options) == 1:
                node.pop("anyOf")
                node.pop("default", None)
                node = {**options[0], **node}  # the field's own description wins
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


# Small helpers ----------------------------------------------------------------------------------


def _venue(db: Session, code: str) -> Venue:
    v = get_venue(db, code.strip())
    if v is None:
        v = resolve_venue(db, code)
    if v is None:
        raise ToolError(f"No venue called {code}. Use list_venues to see the codes.")
    return v


def _booking(db: Session, ref: str) -> Booking:
    m = re.search(r"(\d+)\s*$", ref.strip())
    b = db.get(Booking, int(m.group(1))) if m else None
    if b is None:
        raise ToolError(f"No booking {ref}.")
    return b


def _hm(t: time) -> str:
    return f"{t:%H:%M}"


def _day_text(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d:%d %b %Y}"


def _block(b: availability.Block) -> dict:
    return {"from": _hm(b.start.time()), "to": _hm(b.end.time()), "what": b.label, "kind": b.kind}


def _venue_brief(v: Venue) -> dict:
    return {"code": v.code, "name": v.name, "type": v.type, "capacity": v.capacity}


def _request(a: "EventArgs", venue: str) -> booking_svc.BookingRequest:
    return booking_svc.BookingRequest(
        venue_code=venue,
        title=a.title or "Event",
        event_type=a.event_type or "Other",
        expected_count=a.expected_count,
        date_from=a.date,
        date_to=a.date_to or a.date,
        start_time=a.start,
        end_time=a.end,
    )


def _booking_brief(b: Booking) -> dict:
    occ = b.occurrences
    when = f"{_day_text(occ[0].start_dt.date())}, {occ[0].start_dt:%H:%M}–{occ[0].end_dt:%H:%M}"
    if len(occ) > 1:
        when += f" ({len(occ)} days, to {occ[-1].start_dt:%d %b})"
    return {
        "ref": b.ref,
        "title": b.title,
        "venue": b.venue.code,
        "when": when,
        "status": STATUS_TEXT.get(b.status, b.status),
        "expected": b.expected_count,
        "link": f"/bookings/{b.id}",
    }


# Dates (everyone) ---------------------------------------------------------------------------------


class DatesArgs(BaseModel):
    phrases: list[str] = Field(
        min_length=1,
        max_length=10,
        description="Words for days, e.g. ['next Saturday', 'Friday after next', '3 Nov']",
    )


@tool(
    "resolve_dates",
    "Turn words like 'tomorrow', 'next Saturday', 'Friday after next', 'next week' or '3 Nov' "
    "into exact dates with weekdays. Use it whenever a date isn't in the calendar you were given.",
    label="Working out the dates",
)
def resolve_dates(db: Session, user: User | None, args: DatesArgs) -> ToolResult:
    today = date.today()
    out = {}
    for phrase in args.phrases:
        try:
            out[phrase] = [
                f"{d.isoformat()} ({WEEKDAYS[d.weekday()]})" for d in resolve(phrase, today)
            ]
        except ValueError as e:
            out[phrase] = str(e)
    return ToolResult({"today": f"{today.isoformat()} ({WEEKDAYS[today.weekday()]})", "dates": out})


# Venues and availability (everyone) -------------------------------------------------------------


class ListVenuesArgs(BaseModel):
    type: Literal["lab", "coe", "seminar_hall"] | None = Field(
        None, description="lab = computer lab, coe = centre of excellence"
    )
    min_capacity: int | None = Field(None, ge=1)
    needs: list[str] | None = Field(
        None, description="Software or equipment the venue must have, e.g. ['Power BI', 'Docker']"
    )


@tool(
    "list_venues",
    "List venues (labs, centres of excellence, seminar halls) with capacity. Filter by type, "
    "size or the software/equipment they must have.",
    label="Looking up venues",
)
def list_venues(db: Session, user: User | None, args: ListVenuesArgs) -> ToolResult:
    venues = find_venues(db, type=args.type, min_capacity=args.min_capacity, needs=args.needs)
    return ToolResult([{**_venue_brief(v), "block": v.block} for v in venues])


class VenueArgs(BaseModel):
    venue: str = Field(description="Venue code such as CC5, COE1 or DSH, or its name")


@tool(
    "get_venue",
    "Details of one venue: capacity, software and equipment (with working status), in-charge, "
    "and any maintenance or seasonal restrictions.",
    label="Reading venue details",
)
def get_venue_details(db: Session, user: User | None, args: VenueArgs) -> ToolResult:
    v = _venue(db, args.venue)
    today = date.today()
    return ToolResult(
        {
            **_venue_brief(v),
            "block": v.block,
            "byod": v.byod,
            "in_charge": v.in_charge.name if v.in_charge else None,
            "equipment": [
                {"name": e.name, "quantity": e.quantity, "status": e.status} for e in v.equipment
            ],
            "status_periods": [
                {"status": p.status, "from": str(p.from_date), "to": str(p.to_date or "")}
                for p in v.status_periods
                if p.to_date is None or p.to_date >= today
            ],
            "seasonal_rules": [
                {"months": f"{r.start_month}-{r.end_month}", "kind": r.kind, "reason": r.reason}
                for r in v.seasonal_rules
            ],
            "link": f"/venues/{v.code}",
        }
    )


class AvailabilityArgs(BaseModel):
    venue: str
    date: date
    start: time | None = Field(None, description="HH:MM; leave out to see the whole day")
    end: time | None = None


@tool(
    "check_availability",
    "Is a venue free? With start and end, checks that time; without them, lists everything on "
    "the venue that day (classes, bookings, closures). Always use this instead of guessing.",
    label="Checking availability",
)
def check_availability(db: Session, user: User | None, args: AvailabilityArgs) -> ToolResult:
    v = _venue(db, args.venue)
    if args.start and args.end:
        if args.end <= args.start:
            raise ToolError("The end time must be after the start time.")
        r = availability.check(
            db, v, datetime.combine(args.date, args.start), datetime.combine(args.date, args.end)
        )
        return ToolResult(
            {
                "venue": v.code,
                "day": _day_text(args.date),
                "time": f"{_hm(args.start)}–{_hm(args.end)}",
                "free": r.free,
                "conflicts": [_block(b) for b in r.conflicts],
                "classes_that_would_need_to_move": [_block(b) for b in r.classes],
                "warnings": [w.message for w in r.warnings],
            }
        )
    view = availability.venue_day(db, v, args.date)
    return ToolResult(
        {
            "venue": v.code,
            "day": _day_text(args.date),
            "open": f"{_hm(view.open_from)}–{_hm(view.open_to)}" if view.open_from else "closed",
            "busy": [_block(b) for b in view.blocks],
            "warnings": [w.message for w in view.warnings],
        }
    )


class FreeVenuesArgs(BaseModel):
    date: date
    start: time
    end: time
    date_to: date | None = Field(None, description="Last day, for an event over several days")
    min_capacity: int | None = Field(None, ge=1)
    needs: list[str] | None = Field(None, description="Software or equipment, e.g. ['Power BI']")
    type: Literal["lab", "coe", "seminar_hall"] | None = None


@tool(
    "find_free_venues",
    "Venues that are completely free for a time (every day, for a range), optionally filtered "
    "by size, type and needed software or equipment.",
    label="Finding free venues",
)
def find_free_venues(db: Session, user: User | None, args: FreeVenuesArgs) -> ToolResult:
    if args.end <= args.start:
        raise ToolError("The end time must be after the start time.")
    days = _days(args.date, args.date_to)
    found = []
    for v in find_venues(db, type=args.type, min_capacity=args.min_capacity, needs=args.needs):
        results = [
            availability.check(
                db, v, datetime.combine(d, args.start), datetime.combine(d, args.end)
            )
            for d in days
        ]
        if all(r.free for r in results):
            notes = sorted({w.message for r in results for w in r.warnings})
            found.append({**_venue_brief(v), "warnings": notes})
    return ToolResult(
        {
            "days": [_day_text(d) for d in days],
            "time": f"{_hm(args.start)}–{_hm(args.end)}",
            "free": found,
        }
    )


def _days(first: date, last: date | None) -> list[date]:
    last = last or first
    if last < first:
        raise ToolError("The last day is before the first day.")
    if (last - first).days > 14:
        raise ToolError("Ask about at most two weeks at a time.")
    return [
        first + timedelta(n)
        for n in range((last - first).days + 1)
        if (first + timedelta(n)).weekday() != 6
    ]


class TimetableArgs(BaseModel):
    section: str | None = Field(None, description="Class, e.g. 'CSE III-B' or 'III B'")
    venue: str | None = Field(None, description="Venue code, to see which classes use it")


@tool(
    "get_timetable",
    "The weekly lab timetable of a class (section) or of a venue.",
    label="Reading the timetable",
)
def get_timetable(db: Session, user: User | None, args: TimetableArgs) -> ToolResult:
    query = select(TimetableSlot).order_by(TimetableSlot.weekday, TimetableSlot.start)
    if args.venue:
        v = _venue(db, args.venue)
        query = query.where(TimetableSlot.venue_id == v.id)
        scope = v.code
    elif args.section:
        section = _section(db, args.section)
        query = query.where(TimetableSlot.section_id == section.id)
        scope = section.label
    else:
        raise ToolError("Give a section (e.g. CSE III-B) or a venue code.")
    slots = db.scalars(query).all()
    return ToolResult(
        {
            "for": scope,
            "slots": [
                {
                    "day": WEEKDAYS[s.weekday],
                    "time": f"{_hm(s.start)}–{_hm(s.end)}",
                    "class": s.section.label,
                    "subject": f"{s.subject_code} {s.subject_name}",
                    "batch": s.batch,
                    "venue": s.venue.code,
                    "faculty": s.faculty_name,
                }
                for s in slots
            ],
            "note": None if slots else "No timetable has been committed for this yet.",
        }
    )


def _section(db: Session, text: str) -> ClassSection:
    m = re.search(
        r"([A-Za-z&]+)?\s*\b(I{1,3}V?|IV|[1-4])\s*[- ]?\s*([A-Z])\b", text.strip().upper()
    )
    if not m:
        raise ToolError(f"Couldn't read the class {text!r}; write it like 'CSE III-B'.")
    roman = {"1": "I", "2": "II", "3": "III", "4": "IV"}
    dept, year, sec = (m.group(1) or "CSE"), roman.get(m.group(2), m.group(2)), m.group(3)
    section = db.scalar(
        select(ClassSection).where(
            func.upper(ClassSection.dept) == dept,
            ClassSection.year == year,
            ClassSection.section == sec,
        )
    )
    if section is None:
        known = db.scalars(
            select(ClassSection).order_by(ClassSection.dept, ClassSection.year)
        ).all()
        listed = ", ".join(s.label for s in known) or "none yet"
        raise ToolError(
            f"No timetable has been committed for {dept} {year}-{sec}. "
            f"Classes with timetables: {listed}."
        )
    return section


# Past events (staff) ----------------------------------------------------------------------------


class SearchArgs(BaseModel):
    query: str = Field(min_length=2)
    venue: str | None = None
    event_type: str | None = None
    year: str | None = Field(None, description="Academic year such as 2024-25")


@tool(
    "search_past_events",
    "Search past circulars and event reports (what was held where and when, attendance, "
    "speakers). Cite the reference numbers it returns.",
    label="Searching past circulars and reports",
    login=True,
)
def search_past_events(db: Session, user: User | None, args: SearchArgs) -> ToolResult:
    hits = document_svc.search(
        db, args.query, venue_code=args.venue, event_type=args.event_type, year=args.year, limit=6
    )
    out = []
    for h in hits:
        e = h.event
        out.append(
            {
                "ref": h.document.ref_no,
                "kind": h.document.kind,
                "title": e.title if e else h.document.filename,
                "dates": f"{e.start_date} to {e.end_date}" if e and e.start_date else None,
                "venues": [v.code for v in e.venues] if e else [],
                "participants": e.participants if e else None,
                "excerpt": re.sub("[\x02\x03]", "", h.snippet)[:300],
                "pdf": f"/api/documents/{h.document.id}/file",
                "event_link": f"/documents/events/{e.id}" if e else None,
            }
        )
    return ToolResult({"results": out})


# Booking help (people who can book) -------------------------------------------------------------


class EventArgs(BaseModel):
    event_type: str = Field(description=f"One of: {', '.join(booking_svc.EVENT_TYPES)}")
    expected_count: int = Field(ge=1)
    date: date
    start: time
    end: time
    date_to: date | None = Field(None, description="Last day, for an event over several days")
    needs: list[str] | None = Field(None, description="Software or equipment needed")
    title: str | None = None


@tool(
    "recommend_venues",
    "Rank the best venues for an event: free at that time, big enough, has the needs, suits the "
    "event type, used before for similar events, and no yearly event usually held there then. "
    "Returns the top 3 with reasons and warnings.",
    label="Comparing venues",
    any_of=("book",),
)
def recommend_venues(db: Session, user: User | None, args: EventArgs) -> ToolResult:
    if args.end <= args.start:
        raise ToolError("The end time must be after the start time.")
    days = _days(args.date, args.date_to)
    ranked = []
    for v in find_venues(db, min_capacity=args.expected_count, needs=args.needs):
        results = [
            availability.check(
                db, v, datetime.combine(d, args.start), datetime.combine(d, args.end)
            )
            for d in days
        ]
        if any(r.conflicts for r in results):
            continue
        score, reasons, warnings = 100, [], []
        ratio = v.capacity / args.expected_count
        if ratio > 2.5:
            score -= 20
            reasons.append(f"Seats {v.capacity}, far more than {args.expected_count} needed")
        else:
            score += 5
            reasons.append(f"Seats {v.capacity} for {args.expected_count}")
        if args.event_type in HANDS_ON:
            score += 15 if v.type in ("lab", "coe") else -15
        elif args.event_type in TALKS:
            score += 15 if v.type == "seminar_hall" else -10
        if args.needs:
            reasons.append(f"Has {', '.join(args.needs)}")
        if any(r.classes for r in results):
            score -= 25
            warnings.append(
                "A timetabled class uses it then and would need to move (HOD approval)."
            )
        notes = {w.message: w.kind for r in results for w in r.warnings}
        for message, kind in notes.items():
            if kind == "recurring":
                score -= 30
            warnings.append(message)
        past = _past_use(db, v, args.event_type)
        if past:
            score += min(3 * len(past), 15)
            reasons.append(f"Used for {len(past)} earlier {args.event_type.lower()} event(s)")
        ranked.append(
            {
                **_venue_brief(v),
                "score": score,
                "reasons": reasons,
                "warnings": warnings,
                "past_use": past[:2],
            }
        )
    ranked.sort(key=lambda r: -r["score"])
    return ToolResult(
        {
            "days": [_day_text(d) for d in days],
            "time": f"{_hm(args.start)}–{_hm(args.end)}",
            "top": ranked[:3],
            "considered": len(ranked),
        }
    )


def _past_use(db: Session, v: Venue, event_type: str) -> list[dict]:
    events = db.scalars(
        select(PastEvent)
        .join(PastEventVenue, PastEventVenue.event_id == PastEvent.id)
        .where(PastEventVenue.venue_id == v.id, PastEvent.event_type == event_type)
        .order_by(PastEvent.start_date.desc())
    ).all()
    out = []
    for e in events:
        doc = e.report or e.circular
        out.append(
            {
                "title": e.title,
                "date": str(e.start_date),
                "participants": e.participants,
                "ref": doc.ref_no if doc else None,
            }
        )
    return out


class ClashArgs(EventArgs):
    venue: str


@tool(
    "check_clashes",
    "Everything that stands in the way of booking a venue: closures, other bookings (and the "
    "waitlist), classes that would have to move (with relocation options) and warnings such as "
    "a yearly event usually held there then.",
    label="Checking for clashes",
    any_of=("book",),
)
def check_clashes(db: Session, user: User | None, args: ClashArgs) -> ToolResult:
    v = _venue(db, args.venue)
    result = booking_svc.check_request(db, _request(args, v.code))
    return ToolResult(
        {
            "venue": v.code,
            "outcome": {
                "free": "free to book",
                "blocked": "cannot be booked then",
                "waitlist": "already booked; the user can join the waitlist",
                "displace": "a class uses it; it can move with HOD approval",
            }[result.outcome],
            "blocked_by": [b.label for b in result.blocked],
            "booked_by": [b.label for b in result.taken],
            "classes": [
                {
                    "class": f"{c.slot.section.label} {c.slot.subject_name}",
                    "date": str(c.on_date),
                    "time": f"{_hm(c.slot.start)}–{_hm(c.slot.end)}",
                    "move_to": [o.venue.code for o in c.options[:3]] or ["BYOD in the classroom"],
                }
                for c in result.clashes
            ],
            "warnings": [w.message for w in result.warnings],
            "alternatives": [a.code for a in result.alternatives],
        }
    )


class DraftArgs(EventArgs):
    venue: str
    title: str = Field(min_length=3)
    description: str | None = None
    requirements: str | None = None


@tool(
    "draft_booking",
    "Fill in the booking form for the user to review and submit. Nothing is booked until they "
    "submit it themselves.",
    label="Drafting the booking",
    kind="draft",
    any_of=("book",),
)
def draft_booking(db: Session, user: User | None, args: DraftArgs) -> ToolResult:
    v = _venue(db, args.venue)
    if args.event_type not in booking_svc.EVENT_TYPES:
        raise ToolError(f"event_type must be one of: {', '.join(booking_svc.EVENT_TYPES)}")
    result = booking_svc.check_request(db, _request(args, v.code))
    params = {
        "venue": v.code,
        "date": str(args.date),
        "start": _hm(args.start),
        "end": _hm(args.end),
        "title": args.title,
        "type": args.event_type,
        "count": str(args.expected_count),
        "via": "agent",
    }
    if args.date_to and args.date_to != args.date:
        params["to"] = str(args.date_to)
    if args.description:
        params["description"] = args.description
    if args.requirements:
        params["requirements"] = args.requirements
    when = f"{_day_text(args.date)}, {_hm(args.start)}–{_hm(args.end)}"
    if args.date_to and args.date_to != args.date:
        when += f" to {_day_text(args.date_to)}"
    outcome = {
        "free": "Free",
        "blocked": "Can't be booked then",
        "waitlist": "Already booked: you can join the waitlist",
        "displace": "A class uses it then: choose where it moves on the form",
    }[result.outcome]
    card = {
        "kind": "draft",
        "title": f"Draft booking: {args.title}",
        "lines": [f"{v.code} · {v.name}", when, f"{args.expected_count} expected", outcome]
        + [w.message for w in result.warnings],
        "href": f"/book?{urlencode(params)}",
        "button": "Review & submit",
    }
    return ToolResult(
        {
            "drafted": True,
            "outcome": result.outcome,
            "note": "The user reviews and submits the form.",
        },
        card,
    )


class NoArgs(BaseModel):
    pass


@tool(
    "list_my_bookings",
    "The user's own booking requests with their status (waiting, confirmed, waitlisted…).",
    label="Reading your bookings",
    any_of=("book",),
)
def list_my_bookings(db: Session, user: User | None, args: NoArgs) -> ToolResult:
    rows = db.scalars(
        select(Booking)
        .where(Booking.requester_id == user.id)
        .order_by(Booking.start_dt.desc())
        .limit(20)
    ).all()
    return ToolResult([_booking_brief(b) for b in rows])


class CancelArgs(BaseModel):
    booking: str = Field(description="Booking reference such as BK-2026-0042")
    reason: str | None = None


@tool(
    "propose_cancel",
    "Offer to cancel one of the user's bookings. The user confirms it in the app.",
    label="Preparing a cancellation",
    kind="proposal",
    any_of=("book",),
)
def propose_cancel(db: Session, user: User | None, args: CancelArgs) -> ToolResult:
    b = _booking(db, args.booking)
    if b.requester_id != user.id and not can(user, "approve_all"):
        raise ToolError("Only the person who made a booking (or the Director) can cancel it.")
    if b.status not in booking_svc.OPEN_STATUSES:
        raise ToolError(f"{b.ref} is already {b.status.replace('_', ' ')}.")
    brief = _booking_brief(b)
    card = {
        "kind": "confirm",
        "title": f"Cancel {b.ref}?",
        "lines": [b.title, f"{brief['venue']} · {brief['when']}"]
        + ([f"Reason: {args.reason}"] if args.reason else []),
        "action": {
            "method": "POST",
            "url": f"/api/bookings/{b.id}/cancel",
            "body": {"reason": args.reason},
        },
        "button": "Cancel booking",
        "danger": True,
        "done": f"{b.ref} cancelled.",
    }
    return ToolResult({"proposed": True, "booking": brief}, card)


# Approvals ---------------------------------------------------------------------------------------


@tool(
    "list_pending_approvals",
    "Booking requests waiting for this user's approval.",
    label="Reading your approval queue",
    any_of=APPROVER_CAPS,
)
def list_pending_approvals(db: Session, user: User | None, args: NoArgs) -> ToolResult:
    pending = db.scalars(
        select(Booking)
        .where(Booking.status.in_(("pending_incharge", "pending_hod")))
        .order_by(Booking.start_dt)
    ).all()
    return ToolResult(
        [
            {
                **_booking_brief(b),
                "step": booking_svc.current_step(b),
                "requester": b.requester.name,
            }
            for b in pending
            if booking_svc.can_act(user, b)
        ]
    )


class BookingArgs(BaseModel):
    booking: str = Field(description="Booking reference such as BK-2026-0042")


@tool(
    "assess_request",
    "A briefing for an approver on one request: clashes, classes that move, waitlist, similar "
    "past events in that venue (attendance against capacity), yearly events, and the "
    "requester's recent cancellations.",
    label="Preparing a briefing",
    any_of=APPROVER_CAPS,
)
def assess_request(db: Session, user: User | None, args: BookingArgs) -> ToolResult:
    b = _booking(db, args.booking)
    notes = booking_svc.approval_notes(db, b)
    similar = _past_use(db, b.venue, b.event_type)[:3]
    cancelled = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.requester_id == b.requester_id,
            Booking.status == "cancelled",
            Booking.created_at >= datetime.now() - timedelta(days=90),
        )
    )
    concerns = [n for n in notes if not n.startswith("Capacity fits")]
    return ToolResult(
        {
            "booking": {
                **_booking_brief(b),
                "requester": b.requester.name,
                "event_type": b.event_type,
            },
            "can_you_decide": booking_svc.can_act(user, b),
            "notes": notes,
            "waiting_behind": booking_svc.waiting_behind(db, b),
            "similar_past_events_here": [{**p, "capacity": b.venue.capacity} for p in similar],
            "requester_cancellations_last_90_days": cancelled,
            "suggestion": "approve"
            if len(concerns) == 0
            else "check the concerns before approving",
        }
    )


class DecisionArgs(BaseModel):
    booking: str
    decision: Literal["approve", "reject"]
    comment: str | None = Field(None, description="Required when rejecting")


@tool(
    "propose_decision",
    "Offer to approve or reject a request (a reason is needed to reject). The user confirms it "
    "in the app.",
    label="Preparing a decision",
    kind="proposal",
    any_of=APPROVER_CAPS,
)
def propose_decision(db: Session, user: User | None, args: DecisionArgs) -> ToolResult:
    b = _booking(db, args.booking)
    if not booking_svc.can_act(user, b):
        raise ToolError(f"{b.ref} isn't waiting for your approval.")
    if args.decision == "reject" and not (args.comment or "").strip():
        raise ToolError("Give a reason for rejecting.")
    brief = _booking_brief(b)
    verb = "Approve" if args.decision == "approve" else "Reject"
    card = {
        "kind": "confirm",
        "title": f"{verb} {b.ref}?",
        "lines": [
            b.title,
            f"{brief['venue']} · {brief['when']}",
            f"Requested by {b.requester.name}",
        ]
        + ([f"Comment: {args.comment}"] if args.comment else []),
        "action": {
            "method": "POST",
            "url": f"/api/bookings/{b.id}/{args.decision}",
            "body": {"comment": args.comment},
        },
        "button": verb,
        "danger": args.decision == "reject",
        "done": f"{b.ref} {'approved' if args.decision == 'approve' else 'rejected'}.",
    }
    return ToolResult({"proposed": True, "booking": brief}, card)


# Venue upkeep ------------------------------------------------------------------------------------


class EquipmentArgs(BaseModel):
    venue: str
    item: str = Field(description="Equipment name or part of it, e.g. 'projector'")
    status: Literal["working", "faulty", "under_repair"]


@tool(
    "update_equipment_status",
    "Offer to mark equipment in a venue as working, faulty or under repair. The user "
    "confirms it in the app.",
    label="Preparing an equipment update",
    kind="proposal",
    any_of=("update_equipment_own", "update_equipment_all"),
)
def update_equipment_status(db: Session, user: User | None, args: EquipmentArgs) -> ToolResult:
    v = _venue(db, args.venue)
    if not can_update_equipment(user, v):
        raise ToolError(f"You can't update equipment in {v.code}.")
    matches = [e for e in v.equipment if args.item.lower() in e.name.lower()]
    if not matches:
        raise ToolError(
            f"No equipment like {args.item!r} in {v.code}: {', '.join(e.name for e in v.equipment)}"
        )
    if len(matches) > 1:
        raise ToolError(f"Which one? {', '.join(e.name for e in matches)}")
    item: Equipment = matches[0]
    label = args.status.replace("_", " ")
    card = {
        "kind": "confirm",
        "title": f"Mark {item.name} in {v.code} as {label}?",
        "lines": [f"Now: {item.status.replace('_', ' ')}"],
        "action": {
            "method": "PATCH",
            "url": f"/api/equipment/{item.id}",
            "body": {"status": args.status},
        },
        "button": "Update",
        "done": f"{item.name} in {v.code} marked {label}.",
    }
    return ToolResult({"proposed": True, "item": item.name, "status": args.status}, card)


# Timetables --------------------------------------------------------------------------------------


class UploadArgs(BaseModel):
    upload_id: int


@tool(
    "review_timetable_upload",
    "What was read from an uploaded timetable PDF: the class, its lab slots, and any problems "
    "to fix before committing it.",
    label="Reading the uploaded timetable",
    any_of=("upload_timetables",),
)
def review_timetable_upload(db: Session, user: User | None, args: UploadArgs) -> ToolResult:
    upload = db.get(TimetableUpload, args.upload_id)
    if upload is None:
        raise ToolError("No such upload.")
    data = review(db, json.loads(upload.parsed))
    h = data["header"]
    return ToolResult(
        {
            "class": f"{h.get('dept')} {h.get('year')}-{h.get('section')}",
            "term": h.get("term_name"),
            "status": upload.status,
            "lab_slots": [
                {
                    "day": s.get("weekday"),
                    "time": f"{s.get('start')}–{s.get('end')}",
                    "subject": f"{s.get('subject_code')} {s.get('subject_name')}",
                    "venue": s.get("venue_code") or s.get("venue"),
                    "batch": s.get("batch"),
                    "issues": s.get("issues", []),
                }
                for s in data["slots"]
            ],
            "problems": data["problems"],
            "ready_to_commit": data["can_commit"],
            "review_link": f"/timetables/{upload.id}",
        }
    )
