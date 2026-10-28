"""Stand-in models that never touch the network.

`ScriptedLLM` replays a fixed list of replies (unit tests). `DemoLLM` reads the question with a
few keyword rules and calls real tools, so the chat panel can be tested end to end (LLM_FAKE=1)
and shown without a Groq key. It is not meant to be clever.
"""

import json
import re
from datetime import date, timedelta

from app.agent.llm import LLM, Reply, ToolCall
from app.agent.prompts import LOGIN_LINK

VENUE = re.compile(r"\b(CC\d{1,2}|COE\d|PGLAB|IOTLAB|CSEPGSH|ASH|DSH|ESH|MBASH)\b", re.I)
TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)
BOOKING = re.compile(r"\bBK-\d{4}-\d+\b", re.I)
STAFF = re.compile(
    r"\b(faculty|staff|professor|teacher|lecturer|hod|in-?charge)\b|\bmy bookings\b|\bapprov",
    re.I,
)
HALL = re.compile(r"\b(ASH|DSH|ESH|MBASH|CSEPGSH)\b|seminar hall", re.I)
TRACKING = re.compile(r"\bST-[A-Z0-9]{4}-[A-Z0-9]{4}\b", re.I)


class ScriptedLLM(LLM):
    provider, model = "fake", "scripted"

    def __init__(self, replies: list[Reply]):
        self.replies = list(replies)
        self.seen: list[list[dict]] = []  # the messages sent on each call
        self.forced: list[str | None] = []  # the tool each call had to use, if any

    async def stream(self, messages, tools, force=None):
        self.forced.append(force)
        self.seen.append([dict(m) for m in messages])
        reply = self.replies.pop(0) if self.replies else Reply("(no more scripted replies)")
        for word in re.findall(r"\S+\s*", reply.text):
            yield word
        yield reply


class DemoLLM(LLM):
    provider, model = "fake", "demo"

    async def stream(self, messages, tools, force=None):
        names = {t["function"]["name"] for t in tools}
        last = messages[-1]
        if last["role"] == "tool":
            reply = Reply(_summarise(messages))
        else:
            reply = _plan(last["content"], names)
            if force and not any(c.name == force for c in reply.tool_calls):
                venue = VENUE.search(last["content"])
                args = {"venue": venue.group(0).upper()} if venue else {}
                reply = Reply("", [ToolCall("call_1", force, args)])
        for word in re.findall(r"\S+\s*", reply.text):
            yield word
        yield reply


def _plan(text: str, tools: set[str]) -> Reply:
    venue = VENUE.search(text)
    day = _day(text)
    start, end = _times(text)
    lower = text.lower()
    call = None
    if (ref := BOOKING.search(text)) and "cancel" in lower and "propose_cancel" in tools:
        call = ("propose_cancel", {"booking": ref.group(0).upper()})
    elif (code := TRACKING.search(text)) and "track_student_booking" in tools:
        call = ("track_student_booking", {"tracking_number": code.group(0).upper()})
    elif "draft_booking" not in tools and (
        STAFF.search(text) or ("book" in lower and HALL.search(text))
    ):
        return Reply(
            f"Staff need to log in to book: {LOGIN_LINK}. You'll come back to the booking form "
            "after. Students can request a lab without logging in."
        )
    elif venue and "book" in lower and "draft_student_booking" in tools:
        call = (
            "draft_student_booking",
            {
                "venue": venue.group(0).upper(),
                "date": day.isoformat(),
                "start": start or "14:00",
                "end": end or "16:00",
                "reason": "Mini project work",
            },
        )
    elif venue and "book" in lower:
        if "draft_booking" not in tools:
            return Reply("Please log in as staff to book a venue. I can still check availability.")
        call = (
            "draft_booking",
            {
                "venue": venue.group(0).upper(),
                "title": "Python workshop",
                "event_type": "Workshop",
                "expected_count": 30,
                "date": day.isoformat(),
                "start": start or "10:00",
                "end": end or "12:00",
            },
        )
    elif venue and ("free" in lower or "available" in lower):
        args = {"venue": venue.group(0).upper(), "date": day.isoformat()}
        if start and end:
            args |= {"start": start, "end": end}
        call = ("check_availability", args)
    elif "my bookings" in lower and "list_my_bookings" in tools:
        call = ("list_my_bookings", {})
    elif re.search(r"\b(venues|labs|halls)\b", lower):
        call = ("list_venues", {})
    if call is None:
        return Reply(
            "I'm the demo assistant. Ask me whether a venue is free (e.g. “Is CC5 free tomorrow "
            "10:00 to 12:00?”), to list the labs, or to book a venue."
        )
    return Reply("", [ToolCall("call_1", call[0], call[1])])


def _summarise(messages: list[dict]) -> str:
    calls = {}
    for m in messages:
        for c in m.get("tool_calls") or []:
            calls[c["id"]] = c["function"]["name"]
    last = messages[-1]
    name = calls.get(last["tool_call_id"], "")
    data = json.loads(last["content"])
    if isinstance(data, dict) and "error" in data:
        return f"I couldn't do that: {data['error']}"
    if name == "check_availability":
        if "free" in data:
            if data["free"]:
                return f"{data['venue']} is free on {data['day']}, {data['time']}."
            busy = "; ".join(
                c["what"] for c in data["conflicts"] + data["classes_that_would_need_to_move"]
            )
            return f"{data['venue']} is not free on {data['day']}, {data['time']}: {busy}."
        busy = ", ".join(f"{b['from']}–{b['to']} {b['what']}" for b in data["busy"]) or "nothing"
        return f"On {data['day']}, {data['venue']} has: {busy}."
    if name == "draft_booking":
        return "I've filled in the booking form. Check the details and submit it when you're ready."
    if name == "draft_student_booking":
        return (
            "I've started the student request form. Add your guide, the students and a contact "
            "email, then submit it to get a tracking number."
        )
    if name == "track_student_booking":
        return f"{data['ref']} ({data['tracking_number']}) is {data['status']}."
    if name == "propose_cancel":
        return "Confirm the cancellation on the card if you want to go ahead."
    if name == "list_venues":
        return "Venues: " + ", ".join(f"{v['code']} ({v['capacity']})" for v in data) + "."
    if name == "list_my_bookings":
        if not data:
            return "You have no bookings."
        return "Your bookings: " + "; ".join(
            f"{b['ref']} {b['title']} ({b['status']})" for b in data
        )
    return "Done."


def _day(text: str) -> date:
    if m := re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        return date.fromisoformat(m.group(1))
    day = date.today()
    if "tomorrow" in text.lower():
        day += timedelta(days=1)
    if day.weekday() == 6:
        day += timedelta(days=1)
    return day


def _times(text: str) -> tuple[str | None, str | None]:
    found = []
    for h, m, ampm in TIME.findall(
        re.sub(r"\d{4}-\d{2}-\d{2}|BK-\d{4}-\d+|[A-Z]+\d+", "", text, flags=re.I)
    ):
        hour = int(h)
        if ampm.lower() == "pm" and hour < 12:
            hour += 12
        if 7 <= hour <= 19:
            found.append(f"{hour:02d}:{m or '00'}")
    return (found[0], found[1]) if len(found) >= 2 else (None, None)
