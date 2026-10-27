from datetime import date

import pytest

from app.agent import tools
from app.agent.dates import calendar_line, resolve
from app.agent.prompts import system_prompt

TUESDAY = date(2026, 10, 27)


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("today", "2026-10-27"),
        ("tomorrow", "2026-10-28"),
        ("day after tomorrow", "2026-10-29"),
        ("next Saturday", "2026-10-31"),  # the first Saturday after today
        ("Saturday", "2026-10-31"),
        ("coming sat", "2026-10-31"),
        ("Saturday after next", "2026-11-07"),
        ("Saturday next week", "2026-11-07"),
        ("next Tuesday", "2026-11-03"),  # never today
        ("this Tuesday", "2026-10-27"),
        ("in 10 days", "2026-11-06"),
        ("31 Oct", "2026-10-31"),
        ("3rd November", "2026-11-03"),
        ("Nov 3, 2027", "2027-11-03"),
        ("Jan 5", "2027-01-05"),  # already past this year
        ("2026-12-01", "2026-12-01"),
    ],
)
def test_phrases(phrase, expected):
    assert resolve(phrase, TUESDAY)[0].isoformat() == expected


def test_weeks_are_working_days():
    week = resolve("next week", TUESDAY)
    assert [d.isoformat() for d in (week[0], week[-1])] == ["2026-11-02", "2026-11-07"]
    assert resolve("this week", TUESDAY)[0] == TUESDAY


def test_unreadable_phrases_say_how_to_write_them():
    with pytest.raises(ValueError, match="next Friday"):
        resolve("sometime soon", TUESDAY)


def test_calendar_line_names_every_day():
    line = calendar_line(TUESDAY)
    assert line.startswith("Tue 2026-10-27 (today); Wed 2026-10-28 (tomorrow)")
    assert "Sat 2026-10-31" in line and line.count(";") == 13


def test_prompt_carries_the_calendar(db):
    prompt = system_prompt(db, None)
    assert "Calendar for the next two weeks" in prompt and "resolve_dates" in prompt


def test_tool_reports_dates_with_weekdays(db):
    data = tools.call(db, None, "resolve_dates", {"phrases": ["tomorrow", "whenever"]}).data
    assert data["dates"]["tomorrow"][0].endswith(")")
    assert "Couldn't read" in data["dates"]["whenever"]
