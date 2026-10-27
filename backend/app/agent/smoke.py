"""Live smoke test: ~15 real questions against Groq or Ollama, checking which tools get used.

    python -m app.agent.smoke                       # the default provider from Settings / .env
    python -m app.agent.smoke --provider ollama     # e.g. qwen3.5:4b on this computer
    python -m app.agent.smoke --provider groq --model llama-3.3-70b-versatile --only 6

Needs a seeded database with timetables and documents
(python -m app.seed --timetables --documents). Tools never change data, so this is
safe to run against your normal database. It prints one line per question and a summary.
"""

import argparse
import asyncio
import time
from dataclasses import dataclass, field

from sqlalchemy import select

from app.agent import runtime
from app.agent.llm import LLMError, make_llm
from app.agent.settings import llm_settings
from app.db import SessionLocal
from app.models import User

FACULTY = "tkcse@kiot.ac.in"


@dataclass
class Case:
    question: str
    email: str | None  # None = a student (not logged in)
    tools: set[str] = field(default_factory=set)  # one of these must be called
    card: str | None = None  # "draft" / "confirm" expected, or "none" for no card


CASES = [
    Case("Is CC5 free tomorrow from 10 to 12?", None, {"check_availability"}),
    Case("Which labs have Docker installed?", None, {"list_venues", "get_venue"}),
    Case("Show me the lab timetable for CSE III-B.", None, {"get_timetable"}),
    Case("Book CC3 for me tomorrow 2 to 4 pm.", None, set(), card="none"),
    Case(
        "Find a lab for 35 students with Power BI next Friday 2 to 4 pm.",
        FACULTY,
        {"recommend_venues", "find_free_venues"},
    ),
    Case(
        "Book COE1 next Tuesday 10:00 to 12:00 for a Python workshop, 30 students.",
        FACULTY,
        {"draft_booking"},
        card="draft",
    ),
    Case("Where were Gen-AI workshops held before?", FACULTY, {"search_past_events"}),
    Case("What are my bookings?", FACULTY, {"list_my_bookings"}),
    Case(
        "Any clashes if I hold a guest lecture for 200 people in DSH next Wednesday 10 to 1?",
        FACULTY,
        {"check_clashes", "check_availability", "recommend_venues"},
    ),
    Case("Book CC5 next Monday.", FACULTY, set(), card="none"),
    Case("What is waiting for my approval?", "hod.cse@kiot.ac.in", {"list_pending_approvals"}),
    Case(
        "Mark the projector in CC10 as faulty.",
        "swvcse@kiot.ac.in",
        {"update_equipment_status"},
        card="confirm",
    ),
    Case("Which labs does CSE II-A use on Monday?", "cseoa@kiot.ac.in", {"get_timetable"}),
    Case("Which seminar halls seat more than 150 people?", FACULTY, {"list_venues"}),
    Case(
        "Recommend a venue for a hackathon for 60 people next Saturday 9 am to 5 pm.",
        "dirim@kiot.ac.in",
        {"recommend_venues", "find_free_venues"},
    ),
]


async def run_case(db, case: Case, provider: str | None, model: str | None) -> tuple[bool, str]:
    user = db.scalar(select(User).where(User.email == case.email)) if case.email else None
    llm = make_llm(llm_settings(db), provider, model)
    messages = runtime.build_messages(db, user, llm, [], case.question)
    used, cards, answer, error = [], [], "", ""
    async for event in runtime.run(db, user, llm, messages):
        if event["type"] == "step":
            used.append(event["tool"])
        elif event["type"] == "card":
            cards.append(event["card"]["kind"])
        elif event["type"] == "done":
            answer = event["content"]
        elif event["type"] == "error":
            error = event["message"]
    problems = []
    if error:
        problems.append(f"error: {error}")
    if case.tools and not case.tools & set(used):
        problems.append(f"expected one of {sorted(case.tools)}")
    if case.card == "none" and cards:
        problems.append(f"unexpected {cards[0]} card")
    elif case.card and case.card != "none" and case.card not in cards:
        problems.append(f"no {case.card} card")
    if not answer.strip() and not error:
        problems.append("empty answer")
    detail = f"tools={used or '-'}"
    if problems:
        detail += " | " + "; ".join(problems)
    short = " ".join(answer.split())[:140]
    return not problems, f"{detail}\n      → {short}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--provider", choices=["groq", "ollama"])
    parser.add_argument("--model")
    parser.add_argument("--only", type=int, help="run just this question (1-based)")
    args = parser.parse_args()

    cases = [CASES[args.only - 1]] if args.only else CASES
    passed = 0
    with SessionLocal() as db:
        try:
            llm = make_llm(llm_settings(db), args.provider, args.model)
        except LLMError as e:
            print(e)
            return 2
        print(f"Smoke test: {llm.provider} · {llm.model} · {len(cases)} questions\n")
        for n, case in enumerate(cases, start=args.only or 1):
            started = time.monotonic()
            ok, detail = await run_case(db, case, args.provider, args.model)
            seconds = time.monotonic() - started
            passed += ok
            who = case.email or "student"
            print(f"{'PASS' if ok else 'FAIL'} {n:>2}. [{who}] {case.question} ({seconds:.1f}s)")
            print(f"      {detail}")
            db.rollback()
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
