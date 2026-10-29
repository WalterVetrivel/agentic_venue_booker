"""The agent loop: ask the model, run the tools it calls, feed back the results, repeat.

`run()` yields events for the chat panel:
  {"type": "step", "id", "tool", "label"}           a tool started
  {"type": "step_done", "id", "ok", "error"?}       it finished
  {"type": "card", "card"}                          a draft or proposal for the user
  {"type": "text", "text"}                          part of the answer
  {"type": "done", "content", "steps", "cards", "provider", "model"}
  {"type": "error", "message"}
"""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agent import tools as registry
from app.agent.llm import LLM, LLMError, Reply, tool_call_in_text, tool_specs
from app.agent.prompts import system_prompt
from app.models import User

MAX_STEPS = 8
MAX_RESULT_CHARS = 6000
HISTORY_TURNS = 10  # earlier messages replayed to the model (text only)


@dataclass
class Outcome:
    content: str = ""
    steps: list[dict] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)


def build_messages(
    db: Session, user: User | None, llm: LLM, history: list[dict], message: str
) -> list[dict]:
    messages = [
        {"role": "system", "content": system_prompt(db, user, short=llm.provider == "ollama")}
    ]
    for m in history[-HISTORY_TURNS:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])})
    messages.append({"role": "user", "content": message})
    return messages


async def _stream(llm: LLM, messages: list[dict], specs: list[dict], force: str | None):
    """The model's reply; if it can't be made to use `force`, it answers freely instead."""
    if not force:
        async for item in llm.stream(messages, specs):
            yield item
        return
    try:
        items = [item async for item in llm.stream(messages, specs, force)]
    except LLMError:
        items = None
    if items is None:
        async for item in llm.stream(messages, specs):
            yield item
        return
    for item in items:
        yield item


def _may_be_json(start: str) -> bool:
    return (
        not start
        or start[0] == "{"
        or bool(re.match(r"```(json)?\s*(\{|$)", start))
        or "```json".startswith(start)
    )


# Asking to book or reserve something (not "how do I book…?" or "my bookings").
BOOKING = re.compile(
    r"\b(book|reserve|draft|request)\b(?!ings)|\b(need|want)\b.{0,40}"
    r"\b(lab|hall|venue|room|centre|coe\d?|cc\d+)\b",
    re.I,
)
QUESTION = re.compile(r"^\s*(how|what|why|who|where|which|when)\b", re.I)
CHITCHAT = re.compile(
    r"^\s*(thanks|thank you|ok|okay|cool|great|nice|bye|no|yes|hi|hello)\b[\s\W]*$", re.I
)
# A signed-out member of staff gets a login link instead of a student form.
STAFF = re.compile(
    r"\b(faculty|staff|professor|teacher|lecturer|hod|in-?charge|seminar hall|"
    r"ASH|DSH|ESH|MBASH|CSEPGSH)\b",
    re.I,
)


def form_note(kind: str, fields: dict) -> str:
    """Tells the model what is on the open form, so "add these students" means that form."""
    name = "student request form" if kind == "student" else "booking form"
    tool = "draft_student_booking" if kind == "student" else "draft_booking"
    filled = {k: v for k, v in fields.items() if v not in (None, "", [], {})}
    return (
        f"\n\n[The {name} is open on screen with: {json.dumps(filled, ensure_ascii=False)}. "
        f"If the message adds or changes details, call {tool} with everything already on the "
        "form plus the changes.]"
    )


def draft_tool(message: str, user: User | None, form_open: bool) -> str | None:
    """The draft tool the reply must start with, if the message asks to book something or adds
    details while a booking form is open. The model then can't answer with a list instead."""
    if CHITCHAT.match(message) or QUESTION.match(message):
        return None
    if not (form_open or BOOKING.search(message)):
        return None
    if user is None:
        return None if STAFF.search(message) else "draft_student_booking"
    names = {t.name for t in registry.tools_for(user)}
    return "draft_booking" if "draft_booking" in names else None


async def run(
    db: Session,
    user: User | None,
    llm: LLM,
    messages: list[dict],
    outcome: Outcome | None = None,
    force: str | None = None,
) -> AsyncIterator[dict]:
    outcome = outcome if outcome is not None else Outcome()
    available = registry.tools_for(user)
    specs = tool_specs(available)
    offered = {t.name for t in available}
    texts: list[str] = []
    try:
        for step in range(MAX_STEPS + 1):
            last = step == MAX_STEPS  # out of steps: answer with what we have
            reply = Reply()
            # A reply that opens with JSON may be a tool call written out as text: hold it back
            # until the end rather than show it.
            held: list[str] | None = []
            forced = force if step == 0 and force in offered else None
            async for item in _stream(llm, messages, [] if last else specs, forced):
                if isinstance(item, Reply):
                    reply = item
                elif held is None:
                    yield {"type": "text", "text": item}
                else:
                    held.append(item)
                    if not _may_be_json("".join(held).lstrip()):
                        yield {"type": "text", "text": "".join(held)}
                        held = None
            found = None if reply.tool_calls or last else tool_call_in_text(reply.text, specs)
            if found:
                reply = Reply(found[1], [found[0]])
            if held and reply.text:
                yield {"type": "text", "text": reply.text}
            if reply.text:
                texts.append(reply.text)
            if not reply.tool_calls or last:
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.text or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in reply.tool_calls
                    ],
                }
            )
            for c in reply.tool_calls:
                t = registry.REGISTRY.get(c.name)
                step_id = f"s{len(outcome.steps) + 1}"
                label = t.label if t else c.name
                yield {"type": "step", "id": step_id, "tool": c.name, "label": label}
                record = {"id": step_id, "tool": c.name, "label": label, "args": c.arguments}
                try:
                    result = registry.call(db, user, c.name, c.arguments)
                except registry.ToolError as e:
                    record.update(ok=False, error=str(e))
                    content = json.dumps({"error": str(e)})
                else:
                    record["ok"] = True
                    content = json.dumps(result.data, default=str, ensure_ascii=False)
                    if len(content) > MAX_RESULT_CHARS:
                        content = content[:MAX_RESULT_CHARS] + " …(cut short)"
                    if result.card:
                        outcome.cards.append(result.card)
                        yield {"type": "card", "card": result.card}
                outcome.steps.append(record)
                yield {
                    "type": "step_done",
                    "id": step_id,
                    "ok": record["ok"],
                    **({"error": record["error"]} if not record["ok"] else {}),
                }
                messages.append(
                    {"role": "tool", "tool_call_id": c.id, "name": c.name, "content": content}
                )
            if reply.text:
                # Keep a gap between what the model said before and after its tool calls.
                yield {"type": "text", "text": "\n\n"}
    except LLMError as e:
        outcome.content = "\n\n".join(texts).strip()
        yield {"type": "error", "message": str(e)}
        return
    outcome.content = "\n\n".join(texts).strip()
    yield {
        "type": "done",
        "content": outcome.content,
        "steps": outcome.steps,
        "cards": outcome.cards,
        "provider": llm.provider,
        "model": llm.model,
    }
