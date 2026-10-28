"""Forgiving argument types for the assistant's tools.

Models differ in how they write values: Groq's models usually send "2026-11-03" and "14:30",
while small local models also send "3/11/2026", "2 pm", "30 students", "Seminar Hall" or a
comma-separated string where a list is expected. The schemas sent to the model stay plain
(strings with a described format, no JSON-Schema "format" or "pattern" that a provider might
enforce), and these validators read what actually arrives.
"""

import re
from datetime import date, datetime, time
from difflib import get_close_matches
from typing import Annotated, Any

from pydantic import BeforeValidator

from app.agent.dates import resolve

DATE_HINT = "YYYY-MM-DD, e.g. 2026-11-03"
TIME_HINT = "24-hour HH:MM, e.g. 14:30"
EMPTY = ("", "null", "none", "n/a")


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in EMPTY)


def to_date(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return value
    text = value.strip()
    if m := re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text):  # also 2026-11-03T10:00
        return date(int(m[1]), int(m[2]), int(m[3]))
    if m := re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text):  # Indian order: D/M/Y
        return date(int(m[3]), int(m[2]), int(m[1]))
    try:
        days = resolve(text, date.today())
    except ValueError:
        raise ValueError(f"Couldn't read the date {value!r}. Use {DATE_HINT}.") from None
    if len(days) != 1:
        raise ValueError(f"{value!r} is more than one day. Give one date, {DATE_HINT}.")
    return days[0]


def to_time(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):  # 14 or 14.5 (hours)
        hours = float(value)
        return time(int(hours), round((hours % 1) * 60))
    if not isinstance(value, str):
        return value
    text = value.strip().lower().replace(".", ":").replace(" ", "")
    text = text.split("t")[-1] if re.match(r"^\d{4}-", text) else text  # an ISO date-time
    if text in ("noon", "midday", "12noon"):
        return time(12)
    m = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?(?::\d{2})?(?:hrs?|h)?(am|pm|a:m:|p:m:)?", text)
    if not m:
        raise ValueError(f"Couldn't read the time {value!r}. Use {TIME_HINT}.")
    hour, minute, half = int(m[1]), int(m[2] or 0), (m[3] or "")[:1]
    if half == "p" and hour < 12:
        hour += 12
    elif half == "a" and hour == 12:
        hour = 0
    elif not half and 1 <= hour <= 7:
        hour += 12  # "2" or "2:00" from a model means 2 pm: venues are closed before 08:00
    if hour > 23 or minute > 59:
        raise ValueError(f"{value!r} isn't a time of day. Use {TIME_HINT}.")
    return time(hour, minute)


def to_int(value: Any) -> Any:
    if isinstance(value, str) and (m := re.search(r"\d+", value.replace(",", ""))):
        return int(m[0])  # "30 students", "about 120"
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def to_list(value: Any) -> Any:
    if isinstance(value, str):
        return [part.strip() for part in re.split(r",|;|\band\b", value) if part.strip()]
    return value


def choice(options: dict[str, str]):
    """Read a value case-insensitively, with spaces or hyphens, or by a known synonym."""

    def read(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        key = re.sub(r"[\s-]+", "_", value.strip().lower())
        return options.get(key, options.get(key.rstrip("s"), value))

    return read


def closest(options: list[str]):
    """Match a free-text value to one of `options`, ignoring case and small typos."""

    by_lower = {o.lower(): o for o in options}

    def read(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip().lower()
        if text in by_lower:
            return by_lower[text]
        found = get_close_matches(text, list(by_lower), n=1, cutoff=0.8)
        return by_lower[found[0]] if found else value.strip()

    return read


Day = Annotated[date, BeforeValidator(to_date)]
Clock = Annotated[time, BeforeValidator(to_time)]
Count = Annotated[int, BeforeValidator(to_int)]
Words = Annotated[list[str], BeforeValidator(to_list)]


def drop_empty(raw: dict) -> dict:
    """Optional arguments sent as "" or "null" mean "not given"."""
    return {k: v for k, v in raw.items() if not _empty(v)}
