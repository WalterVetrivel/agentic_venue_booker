"""Rule-based extraction of event details from KIOT circulars and event reports.

Both kinds are generated from fixed templates: a circular has a "Name of the Programme | Venue |
Date | Resource Persons" table, a report a two-column "Name of the Event / Organised by / ..."
table. The text inside the cells is free-form (dates as "18.09.2026" or "9 August 2025", times
as "09.30 AM" or "16:00", venues written many ways), so each field gets its own parser.
Nothing here needs an LLM; the assistant (Phase 5) only reads the results.
"""

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
    )
}
DATE_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})|(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", re.I
)
TIME_RE = re.compile(r"(\d{1,2})[.:](\d{2})\s*(AM|PM)?", re.I)
CODE_RE = re.compile(
    r"(?:Centre of Excellence\s*\(\s*)?\b(CC\d{1,2}|COE\d)\b\)?(?:\s+(?:Lab|Laboratory)\b)?", re.I
)

EVENT_TYPES = [
    (r"guest lecture", "Guest lecture"),
    (r"hands-on workshop|workshop", "Workshop"),
    (r"value-added course", "Value-added course"),
    (r"faculty development programme", "Faculty development programme"),
    (r"hackathon", "Hackathon"),
    (r"codesprint|coding contest", "Coding contest"),
    (r"model practical", "Model practical exam"),
    (r"placement training", "Placement training"),
    (r"admission counselling", "Admission activity"),
    (r"address to", "Address by HOD, Principal or Chairman"),
    (r"inauguration", "Inauguration"),
    (r"valedictory|graduation day", "Valedictory"),
    (r"interaction session|seminar", "Seminar"),
    (r"conference", "Conference"),
]


@dataclass
class ExtractedDoc:
    kind: str  # circular | report
    ref_no: str | None = None
    issued_on: date | None = None
    title: str | None = None
    department: str | None = None
    venue_text: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    audience: str | None = None
    expected_count: int | None = None
    participants: int | None = None
    registered: int | None = None
    resource_persons: str | None = None
    topics: list[str] = field(default_factory=list)
    rating: float | None = None
    text: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def academic_year(self) -> str | None:
        m = re.search(r"(20\d\d-\d\d)", self.ref_no or "")
        return m.group(1) if m else None


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _open(path: Path):
    """The generator writes slightly broken xref tables; pypdf repairs them for pdfplumber."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    buf = io.BytesIO()
    PdfWriter(clone_from=PdfReader(path)).write(buf)
    buf.seek(0)
    return pdfplumber.open(buf)


def parse_dates(s: str) -> tuple[date | None, date | None]:
    found = []
    for m in DATE_RE.finditer(s):
        try:
            if m.group(1):
                found.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
            else:
                found.append(date(int(m.group(6)), MONTHS[m.group(5).lower()], int(m.group(4))))
        except ValueError:
            continue
    if not found:
        return None, None
    return found[0], found[-1]


def parse_times(s: str) -> tuple[time | None, time | None]:
    s = DATE_RE.sub(" ", s)  # "15.09.2023" must not read as a time
    found = []
    for m in TIME_RE.finditer(s):
        h, mi, ampm = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
        if ampm == "PM" and h < 12:
            h += 12
        if ampm == "AM" and h == 12:
            h = 0
        if h < 24 and mi < 60:
            found.append(time(h, mi))
    if not found:
        return None, None
    return found[0], found[-1] if len(found) > 1 else None


def event_type_for(title: str) -> str:
    low = title.lower()
    return next((t for pattern, t in EVENT_TYPES if re.search(pattern, low)), "Other")


def series_key(title: str) -> str:
    """Group recurring events: drop years, phases, batches and punctuation."""
    s = title.lower()
    s = re.sub(r"\(.*?batch\)", " ", s)
    s = re.sub(r"\b20\d\d(-\d\d)?\b", " ", s)
    s = re.sub(r"\bphase\s*\d+\b", " ", s)
    s = re.sub(r"[’']s\b", "s", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def venue_parts(raw: str) -> tuple[list[str], str | None]:
    """Split a venue cell into lab/COE codes and at most one hall name."""
    text = clean(raw)
    codes = [m.group(1).upper() for m in CODE_RE.finditer(text)]
    rest = clean(CODE_RE.sub(" ", text).replace(",", " "))
    if not rest:
        return codes, None
    m = re.match(r"Seminar Hall,?\s*(\w+)[ -]Block$", clean(raw.replace("\n", " ")), re.I)
    if m:
        rest = f"{m.group(1)} Block Seminar Hall"
    m = re.match(r"PG Seminar Hall \(CSE\)", rest, re.I)
    if m:
        rest = "CSE PG Seminar Hall"
    return codes, rest


def hall_candidates(name: str) -> list[str]:
    dehyphen = re.sub(r"(\w)-Block", r"\1 Block", name)
    return list(dict.fromkeys([name, dehyphen, dehyphen.replace(" Block", "")]))


def _cell_table(tables: list, first: str) -> list | None:
    return next((t for t in tables if t and t[0] and clean(t[0][0]) == first), None)


def _int(s: str | None) -> int | None:
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def extract(path: Path) -> ExtractedDoc:
    with _open(path) as pdf:
        tables = [t for p in pdf.pages for t in p.extract_tables()]
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    if _cell_table(tables, "Name of the Event"):
        doc = _report(tables, text)
    elif _cell_table(tables, "Name of the Programme"):
        doc = _circular(tables, text)
    else:
        return ExtractedDoc(kind="unknown", text=text, problems=["Not a KIOT circular or report."])
    doc.text = text
    for key in ("title", "venue_text", "start_date"):
        if getattr(doc, key) is None:
            doc.problems.append(f"Could not find the {key.replace('_text', '').replace('_', ' ')}.")
    if doc.start_time and doc.end_time and doc.end_time <= doc.start_time:
        doc.problems.append(
            f"The end time {doc.end_time:%H:%M} is not after the start time {doc.start_time:%H:%M}."
        )
    if doc.start_date and doc.end_date and doc.end_date < doc.start_date:
        doc.problems.append("The last day is before the first day.")
    return doc


def _header(tables: list, doc: ExtractedDoc, label: str) -> None:
    for t in tables:
        for row in t:
            cells = [clean(c) for c in row if c]
            if any(c.startswith(label) for c in cells):
                ref = next(c for c in cells if c.startswith(label))
                doc.ref_no = ref.removeprefix(label).strip()
                issued = [c for c in cells if DATE_RE.fullmatch(c)]
                doc.issued_on = parse_dates(issued[0])[0] if issued else None
                return


def _report(tables: list, text: str) -> ExtractedDoc:
    doc = ExtractedDoc(kind="report")
    _header(tables, doc, "Report No.")
    kv = {clean(r[0]): clean(r[1]) for r in _cell_table(tables, "Name of the Event") if r[0]}
    doc.title = kv.get("Name of the Event") or None
    doc.department = kv.get("Organised by") or None
    doc.start_date, doc.end_date = parse_dates(kv.get("Date(s)", ""))
    doc.start_time, doc.end_time = parse_times(kv.get("Time", ""))
    doc.venue_text = kv.get("Venue") or None
    doc.resource_persons = kv.get("Resource Person(s)") or None
    doc.audience = kv.get("Target Audience") or None
    parts = kv.get("No. of Participants", "")
    doc.participants = _int(parts)
    m = re.search(r"registered:\s*(\d+)", parts)
    doc.registered = int(m.group(1)) if m else None
    m = re.search(r"Topics covered\n(.*?)\nOutcome", text, re.S)
    if m:
        doc.topics = [clean(re.sub(r"^\(cid:\d+\)|^[•*-]", "", t)) for t in m.group(1).splitlines()]
        doc.topics = [t for t in doc.topics if t]
    m = re.search(r"average rating (\d(?:\.\d)?)/5", text)
    doc.rating = float(m.group(1)) if m else None
    return doc


def _circular(tables: list, text: str) -> ExtractedDoc:
    doc = ExtractedDoc(kind="circular")
    _header(tables, doc, "Circular No.")
    for t in tables:
        for row in t:
            cells = [clean(c) for c in row if c]
            if len(cells) >= 2 and cells[0] == "To":
                doc.audience = cells[1]
            if len(cells) >= 2 and cells[0] == "Circular issued by":
                doc.department = cells[1].removeprefix("Department of ").strip()
    prog = _cell_table(tables, "Name of the Programme")
    row = prog[1] if prog and len(prog) > 1 else [None] * 4
    doc.title = clean(row[0]) or None
    doc.venue_text = row[1] or None
    when = row[2] or ""
    doc.start_date, doc.end_date = parse_dates(when)
    doc.start_time, doc.end_time = parse_times(when)
    persons = clean(row[3])
    doc.resource_persons = persons if persons not in ("", "-") else None
    m = re.search(r"expected about (\d+) participants", text)
    doc.expected_count = int(m.group(1)) if m else None
    m = re.search(r"session will cover (.*?)\.\n", text, re.S)
    if m:
        doc.topics = [clean(t) for t in clean(m.group(1)).split(",") if clean(t)]
    return doc
