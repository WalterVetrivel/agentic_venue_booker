"""Timetable ingestion: parsed PDF -> reviewed slots -> committed rows in timetable_slots."""

import json
import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ingest.timetable_parser import WEEKDAYS, parse_time, parse_timetable
from app.models import (
    AcademicTerm,
    ClassSection,
    TimetableSlot,
    TimetableUpload,
    User,
    Venue,
    VenueAlias,
)
from app.services import audit


class TimetableError(ValueError):
    pass


def resolve_venue(db: Session, name: str) -> Venue | None:
    key = re.sub(r"\s+", " ", name).strip().lower()
    alias = db.scalar(select(VenueAlias).where(func.lower(VenueAlias.alias) == key))
    if alias:
        return alias.venue
    return db.scalar(select(Venue).where(func.lower(Venue.code) == key.replace(" ", "")))


def default_term_end(name: str, start: date) -> date:
    if "EVEN" in name.upper():
        return date(start.year if start.month <= 4 else start.year + 1, 4, 30)
    return date(start.year, 11, 30)


def get_or_create_term(
    db: Session, name: str, valid_from: date, valid_to: date | None
) -> AcademicTerm:
    term = db.scalar(select(AcademicTerm).where(AcademicTerm.name == name))
    if term is None:
        term = AcademicTerm(
            name=name,
            valid_from=valid_from,
            valid_to=valid_to or default_term_end(name, valid_from),
        )
        db.add(term)
        db.flush()
    elif valid_to and term.valid_to != valid_to:
        term.valid_to = valid_to
    return term


def get_or_create_section(db: Session, dept: str, year: str, section: str, advisor: str | None):
    sec = db.scalar(
        select(ClassSection).where(
            ClassSection.dept == dept, ClassSection.year == year, ClassSection.section == section
        )
    )
    if sec is None:
        sec = ClassSection(dept=dept, year=year, section=section, advisor=advisor)
        db.add(sec)
        db.flush()
    elif advisor:
        sec.advisor = advisor
    return sec


def _overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return a_start < b_end and b_start < a_end


def review(db: Session, data: dict) -> dict:
    """Resolve venues and find clashes. Returns the data with per-slot results and a verdict."""
    header = data["header"]
    problems = list(data.get("problems", []))
    for key in ("dept", "year", "section", "term_name", "valid_from"):
        if not header.get(key):
            problems.append(f"Missing {key.replace('_', ' ')}.")

    slots = data["slots"]
    for s in slots:
        venue = resolve_venue(db, s["venue"]) if s.get("venue") else None
        s["venue_code"] = venue.code if venue else None
        s["issues"] = [] if venue else [f"Unknown venue “{s.get('venue')}”."]
        if s.get("weekday") not in WEEKDAYS:
            s["issues"].append("Unknown weekday.")
        try:
            if parse_time(s["start"]) >= parse_time(s["end"]):
                s["issues"].append("Start must be before end.")
        except (KeyError, ValueError):
            s["issues"].append("Times must look like 09:00.")

    # Clashes inside this timetable (two batches in one lab at once)
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            if (
                a["venue_code"]
                and a["venue_code"] == b["venue_code"]
                and a["weekday"] == b["weekday"]
                and _overlap(a["start"], a["end"], b["start"], b["end"])
            ):
                a["issues"].append(
                    f"Clashes with {b['subject_code']} ({b['batch']}) in this timetable."
                )

    # Clashes with other sections already committed for the same term
    term = db.scalar(select(AcademicTerm).where(AcademicTerm.name == header.get("term_name")))
    if term:
        others = db.scalars(select(TimetableSlot).where(TimetableSlot.term_id == term.id)).all()
        own = (header.get("dept"), header.get("year"), header.get("section"))
        for s in slots:
            if not s["venue_code"] or s["weekday"] not in WEEKDAYS:
                continue
            day = WEEKDAYS.index(s["weekday"])
            for o in others:
                if (o.section.dept, o.section.year, o.section.section) == own:
                    continue  # being replaced
                if (
                    o.venue.code == s["venue_code"]
                    and o.weekday == day
                    and _overlap(s["start"], s["end"], f"{o.start:%H:%M}", f"{o.end:%H:%M}")
                ):
                    s["issues"].append(
                        f"{o.venue.code} is already used by {o.section.label} "
                        f"({o.subject_code}, {o.batch}) {o.start:%H:%M}–{o.end:%H:%M}."
                    )

    data["problems"] = problems
    data["can_commit"] = not problems and all(not s["issues"] for s in slots)
    return data


def parse_upload(db: Session, path: Path) -> dict:
    tt = parse_timetable(path)
    data = {
        "header": {
            "dept": tt.dept,
            "year": tt.year,
            "section": tt.section,
            "term_name": tt.term_name,
            "valid_from": tt.valid_from,
            "valid_to": None,
            "class_advisor": tt.class_advisor,
        },
        "periods": tt.periods,
        "grid": tt.grid,
        "subjects": tt.subjects,
        "slots": [s.__dict__ for s in tt.slots],
        "problems": tt.problems,
    }
    term = db.scalar(select(AcademicTerm).where(AcademicTerm.name == tt.term_name))
    if term:
        data["header"]["valid_to"] = term.valid_to.isoformat()
    elif tt.term_name and tt.valid_from:
        end = default_term_end(tt.term_name, date.fromisoformat(tt.valid_from))
        data["header"]["valid_to"] = end.isoformat()
    return review(db, data)


def create_upload(db: Session, user: User | None, filename: str, stored: Path) -> TimetableUpload:
    data = parse_upload(db, stored)
    _drop_pending_for_section(db, data["header"])
    upload = TimetableUpload(
        filename=filename,
        stored_path=str(stored),
        uploaded_by_id=user.id if user else None,
        parsed=json.dumps(data),
    )
    db.add(upload)
    db.flush()
    return upload


def _drop_pending_for_section(db: Session, header: dict) -> None:
    """A new upload for a class replaces any earlier upload of it still waiting for review."""
    key = (header.get("dept"), header.get("year"), header.get("section"))
    if None in key:
        return
    for old in db.scalars(select(TimetableUpload).where(TimetableUpload.status == "parsed")):
        h = json.loads(old.parsed)["header"]
        if (h.get("dept"), h.get("year"), h.get("section")) == key:
            Path(old.stored_path).unlink(missing_ok=True)
            db.delete(old)


def update_upload(db: Session, upload: TimetableUpload, header: dict, slots: list[dict]) -> dict:
    if upload.status == "committed":
        raise TimetableError("This timetable is already committed. Upload it again to change it.")
    data = json.loads(upload.parsed)
    data["header"] = {**data["header"], **header}
    data["slots"] = slots
    data["problems"] = []  # the reviewer has seen and fixed the parser's notes
    data = review(db, data)
    upload.parsed = json.dumps(data)
    return data


def commit_upload(db: Session, upload: TimetableUpload, user: User | None) -> int:
    if upload.status == "committed":
        raise TimetableError("Already committed.")
    data = review(db, json.loads(upload.parsed))
    if not data["can_commit"]:
        upload.parsed = json.dumps(data)
        raise TimetableError("Fix the highlighted problems before committing.")
    h = data["header"]
    term = get_or_create_term(
        db,
        h["term_name"],
        date.fromisoformat(h["valid_from"]),
        date.fromisoformat(h["valid_to"]) if h.get("valid_to") else None,
    )
    section = get_or_create_section(db, h["dept"], h["year"], h["section"], h.get("class_advisor"))
    removed = db.execute(
        delete(TimetableSlot).where(
            TimetableSlot.term_id == term.id, TimetableSlot.section_id == section.id
        )
    ).rowcount
    for s in data["slots"]:
        db.add(
            TimetableSlot(
                term_id=term.id,
                section_id=section.id,
                venue_id=resolve_venue(db, s["venue_code"]).id,
                upload_id=upload.id,
                weekday=WEEKDAYS.index(s["weekday"]),
                start=parse_time(s["start"]),
                end=parse_time(s["end"]),
                subject_code=s["subject_code"],
                subject_name=s.get("subject_name") or s["subject_code"],
                faculty_name=s.get("faculty_name") or None,
                batch=s.get("batch") or "all",
            )
        )
    upload.status = "committed"
    upload.term_id, upload.section_id = term.id, section.id
    upload.parsed = json.dumps(data)
    audit.record(
        db,
        user,
        "commit",
        "timetable",
        section.id,
        before={"slots": removed},
        after={"section": section.label, "term": term.name, "slots": len(data["slots"])},
    )
    return len(data["slots"])


def ingest_and_commit(db: Session, path: Path, user: User | None = None) -> int:
    """Parse and commit in one go (seeding and tests). Raises if the PDF needs review."""
    upload = create_upload(db, user, path.name, path)
    return commit_upload(db, upload, user)


def slots_on(db: Session, venue_id: int, day: date) -> list[TimetableSlot]:
    return db.scalars(
        select(TimetableSlot)
        .join(AcademicTerm)
        .where(
            TimetableSlot.venue_id == venue_id,
            TimetableSlot.weekday == day.weekday(),
            AcademicTerm.valid_from <= day,
            AcademicTerm.valid_to >= day,
        )
        .order_by(TimetableSlot.start)
    ).all()


def slot_label(slot: TimetableSlot) -> str:
    batch = "" if slot.batch == "all" else f" ({slot.batch})"
    return f"{slot.section.label} · {slot.subject_code}{batch}"


def as_datetime(day: date, t) -> datetime:
    return datetime.combine(day, t)
