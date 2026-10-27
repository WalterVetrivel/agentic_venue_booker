from datetime import date, time

import pytest

from app.config import get_settings
from app.ingest.doc_extractor import (
    event_type_for,
    extract,
    parse_dates,
    parse_times,
    series_key,
    venue_parts,
)
from app.services.documents import resolve_venues

MOCK = get_settings().mock_data_dir


# Hand-checked against the PDFs: (file prefix, venues, first day, last day, start, end).
TRUTH = [
    ("CIRCULAR NO.006 (AIDS 2024-25)", ["DSH"], "2024-12-25", "2024-12-25", "10:55", "12:35"),
    ("REPORT EV0001 ", ["ESH"], "2023-07-03", "2023-07-03", "10:00", "12:00"),
    ("CIRCULAR NO.002 (IT 2023-24)", ["CC10"], "2023-09-23", "2023-09-23", "09:30", "16:00"),
    ("REPORT EV0057 ", ["CC4"], "2024-11-18", "2024-11-22", "09:00", "16:40"),
    ("CIRCULAR NO.003 (IT 2025-26)", ["ASH"], "2025-11-10", "2025-11-10", "10:55", "12:35"),
    ("CIRCULAR NO.002 (CSE 2024-25)", ["CC5"], "2024-08-01", "2024-08-08", "15:10", "16:40"),
    ("CIRCULAR NO.001 (CSBS 2024-25)", ["ASH"], "2024-11-21", "2024-11-21", "13:25", "15:55"),
    ("REPORT EV0060 ", ["DSH"], "2024-12-09", "2024-12-13", "09:30", "16:30"),
    ("CIRCULAR NO.011 (CSE 2024-25)", ["CSEPGSH"], "2025-06-09", "2025-06-11", "09:30", "16:30"),
    ("CIRCULAR NO.005 (CSE 2024-25)", ["COE3"], "2024-11-02", "2024-11-02", "10:00", "13:00"),
    ("REPORT EV0035 ", ["CC1"], "2024-02-24", "2024-02-24", "09:30", "16:00"),
    ("CIRCULAR NO.009 (CSE 2023-24)", ["CSEPGSH"], "2023-12-09", "2023-12-09", "10:00", "12:35"),
    ("CIRCULAR NO.003 (PRIN 2025-26)", ["ESH"], "2025-08-18", "2025-08-18", "09:30", "13:00"),
    ("CIRCULAR NO.002 (IT 2025-26)", ["CC11"], "2025-09-15", "2025-09-22", "15:10", "16:40"),
    ("CIRCULAR NO.007 (CSE 2025-26)", ["CC1"], "2025-09-13", "2025-09-13", "09:30", "16:00"),
    ("CIRCULAR NO.006 (COE-EXAM 2023-24)", ["CC6"], "2023-11-13", "2023-11-17", "09:00", "16:40"),
    (
        "CIRCULAR NO.002 (PAT 2025-26)",
        ["COE1", "COE2", "COE3"],
        "2026-02-07",
        "2026-02-07",
        "09:00",
        "16:00",
    ),
    ("REPORT EV0059 ", ["CC6"], "2024-11-18", "2024-11-22", "09:00", "16:40"),
    ("REPORT EV0081 ", ["CC1"], "2024-11-09", "2024-11-09", "09:30", "16:00"),
    ("CIRCULAR NO.001 (MBA 2025-26)", ["MBASH"], "2025-07-16", "2025-07-16", "14:10", "15:55"),
]


def pdf(prefix: str):
    folder = MOCK / ("reports" if prefix.startswith("REPORT") else "circulars")
    (path,) = [p for p in folder.glob("*.pdf") if p.name.startswith(prefix)]
    return path


def test_extraction_matches_the_hand_checked_set(db):
    wrong = []
    for prefix, codes, first, last, start, end in TRUTH:
        doc = extract(pdf(prefix))
        venues, unknown = resolve_venues(db, doc.venue_text)
        got = (
            sorted(v.code for v in venues),
            str(doc.start_date),
            str(doc.end_date),
            f"{doc.start_time:%H:%M}",
            f"{doc.end_time:%H:%M}",
        )
        if got != (sorted(codes), first, last, start, end) or unknown or doc.problems:
            wrong.append((prefix, got, unknown, doc.problems))
    accuracy = 1 - len(wrong) / len(TRUTH)
    assert accuracy >= 0.95, wrong


def test_report_details():
    doc = extract(pdf("REPORT EV0081 "))
    assert doc.kind == "report" and doc.ref_no == "EV0081/2024-25"
    assert doc.academic_year == "2024-25"
    assert (doc.participants, doc.registered) == (57, 55)
    assert doc.topics == [
        "Generative AI for developers",
        "Machine learning pipelines",
        "Prompt engineering",
    ]


def test_impossible_times_are_flagged_not_guessed():
    doc = extract(pdf("REPORT EV0115 "))
    assert doc.start_time == time(13, 25) and doc.end_time == time(12, 35)
    assert doc.problems == ["The end time 12:35 is not after the start time 13:25."]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("18.09.2026 09.30 AM", (date(2026, 9, 18), date(2026, 9, 18))),
        ("15 September 2025 to 22.09.2025", (date(2025, 9, 15), date(2025, 9, 22))),
        ("no date", (None, None)),
    ],
)
def test_parse_dates(text, expected):
    assert parse_dates(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10.00 AM to 12.00 PM", (time(10), time(12))),
        ("15.09.2023 09:30 to 04.30 PM", (time(9, 30), time(16, 30))),
        ("12.30 AM", (time(0, 30), None)),
    ],
)
def test_parse_times(text, expected):
    assert parse_times(text) == expected


@pytest.mark.parametrize(
    "raw, codes, hall",
    [
        ("COE1\nCentre of\nExcellence (COE2)\nCOE3 Lab", ["COE1", "COE2", "COE3"], None),
        ("Seminar Hall, E\nBlock", [], "E Block Seminar Hall"),
        ("PG Seminar Hall\n(CSE)", [], "CSE PG Seminar Hall"),
        ("CC11 Laboratory", ["CC11"], None),
    ],
)
def test_venue_parts(raw, codes, hall):
    assert venue_parts(raw) == (codes, hall)


def test_series_and_type():
    a = series_key("Placement Training Programme - Phase 1 (2025-26 batch)")
    assert a == series_key("Placement Training Programme - Phase 3 (2023-24 batch)")
    assert series_key("KIOT In-house Hackathon 2024") == "kiot-in-house-hackathon"
    assert event_type_for("Hands-on Workshop on Secure coding") == "Workshop"
    assert event_type_for("Graduation Day") == "Valedictory"
