"""Parse a KIOT class timetable PDF into lab slots.

The PDFs are a single table: a header (department, term, section), a period row with times,
one row per weekday, then a subject key mapping acronyms to subject names and faculty. A lab
session names its venue inside the cell, either for the whole class (`OOP LAB (CC1)`) or per
batch (`DBMS (B1, CC1) / DS (B2, CC2)`). A merged cell spans the empty cells to its right,
up to the next break.
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import IO

import pdfplumber

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DEPARTMENTS = {
    "computer science and engineering": "CSE",
    "information technology": "IT",
    "artificial intelligence and data science": "AI&DS",
    "computer science and business systems": "CSBS",
}
YEARS = {"I": "I", "II": "II", "III": "III", "IV": "IV"}

# "DBMS (B1, CC1)", "OOP LAB (CC1)", "ML (B2, CC10)", "DS (CC3)"
VENUE_SEGMENT = re.compile(
    r"^\s*(?P<subject>[A-Za-z][^()/]*?)\s*(?:LAB\s*)?\(\s*(?:(?P<batch>B\d)\s*,\s*)?"
    r"(?P<venue>[A-Za-z]+\s*\d*[A-Za-z]*)\s*\)\s*$",
    re.IGNORECASE,
)
# Anything that looks like it mentions a venue, used to flag cells the rules could not read.
VENUE_HINT = re.compile(r"\b(CC\s?\d+|COE\s?\d|PG\s?LAB|IOT\s?LAB|LAB)\b", re.IGNORECASE)


@dataclass
class ParsedSlot:
    weekday: str
    start: str  # HH:MM
    end: str
    subject_code: str
    subject_name: str
    faculty_name: str
    batch: str  # all | B1 | B2
    venue: str  # as written in the PDF; resolved to a venue later


@dataclass
class ParsedTimetable:
    dept: str | None = None
    year: str | None = None
    section: str | None = None
    term_name: str | None = None
    valid_from: str | None = None  # ISO date
    class_advisor: str | None = None
    periods: list[dict] = field(default_factory=list)  # [{no, start, end}]
    grid: dict[str, list[str | None]] = field(default_factory=dict)  # weekday -> period cells
    subjects: dict[str, dict] = field(default_factory=dict)  # code -> {name, faculty}
    slots: list[ParsedSlot] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(cell: str | None) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def _to_time(text: str) -> time:
    """'01.25' -> 13:25. Classes run 08:00-17:00, so hours below 8 are afternoon."""
    h, m = (int(x) for x in re.split(r"[.:]", text.strip()))
    if h < 8:
        h += 12
    return time(h, m)


def _period_times(cell: str) -> tuple[time, time] | None:
    match = re.match(
        r"^\s*(\d{1,2}[.:]\d{2})\s*-\s*(\d{1,2}[.:]\d{2})", _clean(cell).replace(" ", "")
    )
    if not match:
        return None
    return _to_time(match.group(1)), _to_time(match.group(2))


def _parse_date(text: str) -> str | None:
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if not match:
        return None
    d, m, y = (int(x) for x in match.groups())
    return date(y, m, d).isoformat()


def _subject_name(name: str) -> str:
    return re.sub(r"\s*\((theory cum practical|lab|practical)\)\s*$", "", name, flags=re.I).strip()


def _parse_header(rows: list[list[str | None]], tt: ParsedTimetable) -> None:
    text = " | ".join(_clean(c) for r in rows for c in r if c)
    if m := re.search(r"Department of ([A-Za-z &]+?)(?:\s*\||$)", text):
        tt.dept = DEPARTMENTS.get(m.group(1).strip().lower().replace("&", "and"))
    if m := re.search(r"TIME TABLE \(([^)]+)\)", text, re.I):
        tt.term_name = m.group(1).strip()
    if m := re.search(r"Wef:?\s*([\d./-]+)", text, re.I):
        tt.valid_from = _parse_date(m.group(1))
    if m := re.search(r"Yr/Sem/Sec:\s*([IV]+)\s*YR\s*/\s*[IVX]+\s*SEM\s*/\s*([A-Z])", text, re.I):
        tt.year, tt.section = YEARS.get(m.group(1).upper()), m.group(2).upper()
    if m := re.search(r"Class Advisor:\s*([^|]+?)(?:\s*\||$)", text, re.I):
        tt.class_advisor = m.group(1).strip()


def _venue_segments(cell: str) -> list[tuple[str, str, str]] | None:
    """Return (subject, batch, venue) for each part of a lab cell, or None if not a lab cell."""
    parts = [p for p in cell.split("/") if p.strip()]
    found = []
    for part in parts:
        m = VENUE_SEGMENT.match(part)
        if not m:
            return None
        venue = re.sub(r"\s+", "", m.group("venue")).upper()
        if not re.search(r"\d|LAB", venue):  # "(T)" marks a tutorial, not a venue
            return None
        found.append(
            (
                m.group("subject").strip().upper(),
                (m.group("batch") or "all").replace("b", "B"),
                venue,
            )
        )
    return found or None


def parse_timetable(source: str | Path | IO[bytes]) -> ParsedTimetable:
    tt = ParsedTimetable()
    with pdfplumber.open(source) as pdf:
        tables = [t for page in pdf.pages for t in page.extract_tables()]
    if not tables:
        tt.problems.append("No table found in the PDF.")
        return tt

    main = tables[0]
    period_idx = next((i for i, r in enumerate(main) if _clean(r[0]).lower() == "period"), None)
    if period_idx is None or period_idx + 1 >= len(main):
        tt.problems.append("Could not find the period header row.")
        return tt
    _parse_header(main[:period_idx], tt)

    period_row, time_row = main[period_idx], main[period_idx + 1]
    columns: list[tuple[int, int | None, time, time]] = []  # (col, period_no or None for breaks)
    for col in range(1, len(period_row)):
        times = _period_times(time_row[col] or "")
        if not times:
            continue
        label = _clean(period_row[col])
        columns.append((col, int(label) if label.isdigit() else None, *times))
    tt.periods = [
        {"no": no, "start": f"{s:%H:%M}", "end": f"{e:%H:%M}"} for _, no, s, e in columns if no
    ]

    # Subject key (second table, or rows after the grid)
    for table in tables[1:]:
        for row in table:
            cells = [_clean(c) for c in row]
            if len(cells) >= 4 and cells[0].isdigit():
                tt.subjects[cells[1].upper()] = {
                    "name": _subject_name(cells[2]),
                    "faculty": re.sub(r"(, (AP|Prof|ASP)/\w+)+$", "", cells[3]).strip(),
                }

    for row in main[period_idx + 2 :]:
        day = _clean(row[0])[:3].title()
        if day not in WEEKDAYS:
            continue
        tt.grid[day] = [_clean(row[col]) or None for col, no, *_ in columns if no]
        for i, (col, no, start, _end) in enumerate(columns):
            cell = _clean(row[col])
            if no is None or not cell:
                continue
            # Extend across empty merged cells to the right, stopping at a break column.
            end = _end
            for col2, no2, _s2, e2 in columns[i + 1 :]:
                if no2 is None or _clean(row[col2]):
                    break
                end = e2
            segments = _venue_segments(cell)
            if segments is None:
                if VENUE_HINT.search(cell):
                    tt.problems.append(f"{day} period {no}: couldn't read “{cell}”.")
                continue
            for subject, batch, venue in segments:
                info = tt.subjects.get(subject, {})
                if not info:
                    tt.problems.append(f"{day} period {no}: subject {subject} is not in the key.")
                tt.slots.append(
                    ParsedSlot(
                        weekday=day,
                        start=f"{start:%H:%M}",
                        end=f"{end:%H:%M}",
                        subject_code=subject,
                        subject_name=info.get("name", subject),
                        faculty_name=info.get("faculty", ""),
                        batch=batch,
                        venue=venue,
                    )
                )

    for attr, label in [("dept", "department"), ("year", "year"), ("section", "section")]:
        if not getattr(tt, attr):
            tt.problems.append(f"Couldn't find the {label} in the header.")
    return tt


def slot_key(dept, year, section, slot: ParsedSlot | dict) -> tuple:
    s = slot if isinstance(slot, dict) else asdict(slot)
    return (dept, year, section, s["weekday"], s["start"], s["end"], s["batch"], s["venue"])


def parse_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()
