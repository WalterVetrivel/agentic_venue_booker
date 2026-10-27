import csv

import pytest

from app.config import get_settings
from app.ingest.timetable_parser import parse_timetable

FOLDER = get_settings().mock_data_dir / "timetables"
PDFS = sorted(FOLDER.glob("*.pdf"))


def truth_rows() -> list[dict]:
    with (FOLDER / "lab_slots_truth.csv").open() as f:
        return list(csv.DictReader(f))


def key(dept, year, section, weekday, start, end, batch, venue, subject):
    return (dept, year, section, weekday, start, end, batch, venue, subject)


def test_all_mock_timetables_match_the_answer_key():
    expected = {
        key(
            *(r[k] for k in ("dept", "year", "section", "weekday", "start", "end")),
            r["batch"],
            r["venue"],
            r["subject"],
        )
        for r in truth_rows()
    }
    got = set()
    for pdf in PDFS:
        tt = parse_timetable(pdf)
        assert tt.problems == [], (pdf.name, tt.problems)
        for s in tt.slots:
            got.add(
                key(
                    tt.dept,
                    tt.year,
                    tt.section,
                    s.weekday,
                    s.start,
                    s.end,
                    s.batch,
                    s.venue,
                    s.subject_code,
                )
            )
    assert len(PDFS) == 22
    assert got == expected  # all 124 lab slots, nothing extra


def test_subject_names_and_faculty_come_from_the_key():
    names = {
        (r["file"], r["weekday"], r["start"], r["batch"]): r["subject_name"] for r in truth_rows()
    }
    for pdf in PDFS:
        tt = parse_timetable(pdf)
        for s in tt.slots:
            assert s.subject_name == names[(pdf.name, s.weekday, s.start, s.batch)]
            assert s.faculty_name


def test_header_fields():
    tt = parse_timetable(FOLDER / "TT_CSE_II_YR_A.pdf")
    assert (tt.dept, tt.year, tt.section) == ("CSE", "II", "A")
    assert tt.term_name == "2026-27 ODD" and tt.valid_from == "2026-07-01"
    assert tt.class_advisor == "Mrs. V. Anitha, AP/CSE"
    assert [p["start"] for p in tt.periods][:3] == ["09:00", "09:50", "10:55"]
    assert tt.periods[-1] == {"no": 8, "start": "15:55", "end": "16:40"}


def test_special_characters_in_subject_codes():
    tt = parse_timetable(FOLDER / "TT_CSE_III_YR_A.pdf")
    assert {"C#&.N", "ES&IOT"} <= {s.subject_code for s in tt.slots}


@pytest.mark.parametrize(
    "name", ["TT_AIDS_II_YR_A.pdf", "TT_CSBS_III_YR_A.pdf", "TT_IT_II_YR_B.pdf"]
)
def test_other_departments(name):
    tt = parse_timetable(FOLDER / name)
    assert tt.dept in {"AI&DS", "CSBS", "IT"} and tt.slots
