"""Turning words like "next Saturday" into dates, so the model never does calendar arithmetic.

Conventions (documented in the system prompt too):
- "Saturday", "this Saturday", "next Saturday", "coming Saturday": the first Saturday after today
  (today itself if today is Saturday and the word "this" is used).
- "Saturday after next" / "Saturday next week": seven days after that.
- "next week" / "this week": the working days (Monday to Saturday) of that week.
"""

import re
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SHORT_DAYS = {d[:3]: i for i, d in enumerate(WEEKDAYS)} | {"tues": 1, "thur": 3, "thurs": 3}
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}


def _weekday(word: str) -> int | None:
    word = word.lower()
    if word in WEEKDAYS:
        return WEEKDAYS.index(word)
    return SHORT_DAYS.get(word)


def _month(word: str) -> int | None:
    return MONTHS.get(word.lower()[:3]) if len(word) >= 3 else None


def _week_of(day: date) -> list[date]:
    monday = day - timedelta(days=day.weekday())
    return [monday + timedelta(days=n) for n in range(6)]


def resolve(phrase: str, today: date) -> list[date]:
    """Dates meant by `phrase`; raises ValueError when it can't tell."""
    text = " ".join(phrase.lower().replace(",", " ").split())

    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text):
        return [date(int(m[1]), int(m[2]), int(m[3]))]
    if text == "today":
        return [today]
    if text == "tomorrow":
        return [today + timedelta(days=1)]
    if text in ("day after tomorrow", "the day after tomorrow"):
        return [today + timedelta(days=2)]
    if m := re.fullmatch(r"in (\d+) days?", text):
        return [today + timedelta(days=int(m[1]))]
    if text == "this week":
        return [d for d in _week_of(today) if d >= today]
    if text in ("next week", "the coming week"):
        return _week_of(today + timedelta(days=7))

    # "next saturday", "saturday after next", "saturday next week", "this sat"
    m = re.fullmatch(
        r"(?:(this|next|coming|the coming|on)\s+)?([a-z]+)"
        r"(\s+after next|\s+next week|\s+of next week)?",
        text,
    )
    if m and (wd := _weekday(m[2])) is not None:
        ahead = (wd - today.weekday()) % 7
        if ahead == 0 and m[1] != "this":
            ahead = 7
        day = today + timedelta(days=ahead)
        if m[3] and "after next" in m[3]:
            day += timedelta(days=7)
        elif m[3]:  # "saturday next week": that weekday in the following calendar week
            day = _week_of(today + timedelta(days=7))[0] + timedelta(days=wd)
        return [day]

    # "31 oct", "31st october 2026", "oct 31", "october 31st"
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:\s+(\d{4}))?", text) or None
    if m:
        day_num, month_word, year = m[1], m[2], m[3]
    elif m := re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", text):
        month_word, day_num, year = m[1], m[2], m[3]
    if m and (month := _month(month_word)):
        if year:
            return [date(int(year), month, int(day_num))]
        candidate = date(today.year, month, int(day_num))
        if candidate < today:  # a date already past this year means next year
            candidate = date(today.year + 1, month, int(day_num))
        return [candidate]

    raise ValueError(
        f"Couldn't read {phrase!r}. Try 'tomorrow', 'next Friday', 'Friday after next', "
        "'next week', '3 Nov' or 2026-11-03."
    )


def calendar_line(today: date, days: int = 14) -> str:
    """A compact two-week calendar for the system prompt."""
    out = []
    for n in range(days):
        d = today + timedelta(days=n)
        label = "today" if n == 0 else "tomorrow" if n == 1 else ""
        out.append(f"{d:%a} {d.isoformat()}" + (f" ({label})" if label else ""))
    return "; ".join(out)
