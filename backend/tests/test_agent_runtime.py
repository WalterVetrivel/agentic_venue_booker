import asyncio
import json
from functools import partial

import httpx
import pytest
from sqlalchemy import select

from app.agent import llm as gateway
from app.agent import runtime
from app.agent.fake import ScriptedLLM
from app.agent.llm import LLMError, Reply, ToolCall
from app.models import User

DAY = "2027-02-09"


def collect(db, user, model, message="Is CC5 free?"):
    messages = runtime.build_messages(db, user, model, [], message)

    async def go():
        return [e async for e in runtime.run(db, user, model, messages)]

    return asyncio.run(go()), messages


def test_tool_call_then_answer(db):
    model = ScriptedLLM(
        [
            Reply("", [ToolCall("c1", "check_availability", {"venue": "CC5", "date": DAY})]),
            Reply("CC5 has classes in the morning."),
        ]
    )
    events, messages = collect(db, None, model)
    kinds = [e["type"] for e in events]
    assert kinds[:2] == ["step", "step_done"] and kinds[-1] == "done"
    assert events[0]["label"] == "Checking availability"
    assert events[-1]["content"] == "CC5 has classes in the morning."
    # The second call saw the tool's result.
    tool_msg = model.seen[1][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["venue"] == "CC5"
    assert "Today is" in messages[0]["content"] and "not logged in" in messages[0]["content"]


def test_errors_go_back_to_the_model(db):
    model = ScriptedLLM(
        [
            Reply("", [ToolCall("c1", "draft_booking", {"venue": "CC5"})]),
            Reply("Please log in to book."),
        ]
    )
    events, _ = collect(db, None, model)
    done = next(e for e in events if e["type"] == "step_done")
    assert not done["ok"] and "log in" in done["error"]
    assert "log in" in json.loads(model.seen[1][-1]["content"])["error"]
    assert events[-1]["steps"][0]["ok"] is False


def test_drafts_produce_cards(db):
    teacher = db.scalar(select(User).where(User.email == "tkcse@kiot.ac.in"))
    args = {
        "venue": "DSH",
        "title": "Cloud workshop",
        "event_type": "Workshop",
        "expected_count": 100,
        "date": DAY,
        "start": "10:00",
        "end": "12:00",
    }
    model = ScriptedLLM(
        [Reply("Let me draft that.", [ToolCall("c1", "draft_booking", args)]), Reply("Done.")]
    )
    events, _ = collect(db, teacher, model)
    (card,) = [e["card"] for e in events if e["type"] == "card"]
    assert card["href"].startswith("/book?venue=DSH")
    assert events[-1]["cards"] == [card]
    assert events[-1]["content"] == "Let me draft that.\n\nDone."


def test_the_loop_stops_after_eight_steps(db):
    call = Reply("", [ToolCall("c", "list_venues", {})])
    model = ScriptedLLM([call] * 20)
    events, _ = collect(db, None, model)
    assert sum(e["type"] == "step" for e in events) == runtime.MAX_STEPS
    assert len(model.seen) == runtime.MAX_STEPS + 1  # the last call offers no tools
    assert events[-1]["type"] == "done"


def test_model_errors_become_error_events(db):
    class Broken(ScriptedLLM):
        async def stream(self, messages, tools):
            raise LLMError("Groq rejected the API key.")
            yield  # pragma: no cover

    events, _ = collect(db, None, Broken([]))
    assert events == [{"type": "error", "message": "Groq rejected the API key."}]


def test_history_is_replayed_as_text_only(db):
    model = ScriptedLLM([])
    history = [
        {"role": "user", "content": "Is CC5 free?"},
        {"role": "assistant", "content": "Yes."},
        {"role": "tool", "content": "{}"},
    ]
    messages = runtime.build_messages(db, None, model, history, "And CC6?")
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]


# The Groq and Ollama clients, against recorded-style responses -------------------------------


def _sse(*chunks):
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
    return "".join(lines).encode()


def _patch_http(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        gateway.httpx, "AsyncClient", partial(httpx.AsyncClient, transport=transport)
    )


def _drain(model, tools=()):
    async def go():
        return [x async for x in model.stream([{"role": "user", "content": "hi"}], list(tools))]

    return asyncio.run(go())


def test_groq_streams_text_and_tool_calls(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        body = _sse(
            {"choices": [{"delta": {"content": "Checking"}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_9",
                                    "function": {"name": "check_", "arguments": '{"venue":'},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"name": "availability", "arguments": '"CC5"}'},
                                }
                            ]
                        }
                    }
                ]
            },
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    _patch_http(monkeypatch, handler)
    out = _drain(gateway.GroqLLM("gsk_test", "openai/gpt-oss-20b"))
    assert out[0] == "Checking"
    reply = out[-1]
    assert reply.tool_calls == [ToolCall("call_9", "check_availability", {"venue": "CC5"})]
    assert seen[0]["stream"] is True and seen[0]["model"] == "openai/gpt-oss-20b"


def test_groq_falls_back_when_the_model_is_gone(monkeypatch):
    models = []

    def handler(request):
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "old-model":
            return httpx.Response(404, json={"error": {"code": "model_not_found"}})
        return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "ok"}}]}))

    _patch_http(monkeypatch, handler)
    out = _drain(gateway.GroqLLM("gsk_test", "old-model", "llama-3.3-70b-versatile"))
    assert models == ["old-model", "llama-3.3-70b-versatile"] and out[-1].text == "ok"


def test_groq_rejected_key_is_explained(monkeypatch):
    _patch_http(monkeypatch, lambda r: httpx.Response(401, json={"error": {"message": "x"}}))
    with pytest.raises(LLMError, match="rejected the API key"):
        _drain(gateway.GroqLLM("gsk_test", "m"))


def test_groq_waits_out_a_short_rate_limit(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            message = "Rate limit reached for model. Please try again in 10ms."
            return httpx.Response(429, json={"error": {"message": message}})
        return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "ok"}}]}))

    _patch_http(monkeypatch, handler)
    assert _drain(gateway.GroqLLM("gsk_test", "m"))[-1].text == "ok" and len(calls) == 2


def test_groq_reports_a_long_rate_limit(monkeypatch):
    message = "Rate limit reached (tokens per day). Please try again in 7m12.5s."
    _patch_http(monkeypatch, lambda r: httpx.Response(429, json={"error": {"message": message}}))
    with pytest.raises(LLMError, match="limit was reached"):
        _drain(gateway.GroqLLM("gsk_test", "m"))


def test_groq_asks_again_after_a_malformed_tool_call(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            error = {"code": "tool_use_failed", "message": "Tool call validation failed"}
            return httpx.Response(200, content=_sse({"error": error}))
        return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "ok"}}]}))

    _patch_http(monkeypatch, handler)
    assert _drain(gateway.GroqLLM("gsk_test", "m"))[-1].text == "ok" and len(calls) == 2


def test_groq_reads_the_call_out_of_a_parsing_failure(monkeypatch):
    # gpt-oss sometimes writes the call in its own format, which Groq then refuses.
    generation = (
        "<|channel|>commentary to=functions.draft_booking <|constrain|>json<|message|>"
        '{"venue": "CC5", "date": "2027-02-09", "expected_count": 12}'
    )
    error = {
        "code": "output_parse_failed",
        "message": "Parsing failed. The model generated output that could not be parsed.",
        "failed_generation": generation,
    }
    _patch_http(monkeypatch, lambda r: httpx.Response(400, json={"error": error}))
    tools = gateway.tool_specs([runtime.registry.REGISTRY["draft_booking"]])
    (reply,) = _drain(gateway.GroqLLM("gsk_test", "m"), tools)
    (call,) = reply.tool_calls
    assert call.name == "draft_booking"
    assert call.arguments == {"venue": "CC5", "date": "2027-02-09", "expected_count": 12}


def test_groq_gives_up_on_repeated_unreadable_calls(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        error = {"code": "output_parse_failed", "message": "Parsing failed."}
        return httpx.Response(400, json={"error": error})

    _patch_http(monkeypatch, handler)
    with pytest.raises(LLMError, match="rephrasing"):
        _drain(gateway.GroqLLM("gsk_test", "m"))
    assert len(calls) == 3


def test_a_tool_call_written_as_json_is_made_and_not_shown(db):
    text = (
        '```json\n{"venue": "", "date": "2027-02-09", "start": "10:30", "end": "12:30", '
        '"reason": "Capstone project for DBMS", "guide": "", '
        '"students": [{"name": "", "class": ""}, {"name": "", "class": ""}], '
        '"contact_email": ""}\n```'
    )
    model = ScriptedLLM([Reply(text), Reply("I've opened the form. Which lab?")])
    events, _ = collect(db, None, model, "Book a lab tomorrow for our DBMS capstone")
    assert not any(e["type"] == "text" and "{" in e["text"] for e in events)
    step = next(e for e in events if e["type"] == "step")
    assert step["tool"] == "draft_student_booking"
    card = next(e["card"] for e in events if e["type"] == "card")
    assert "reason=Capstone+project+for+DBMS" in card["href"] and "students" not in card["href"]
    assert events[-1]["content"] == "I've opened the form. Which lab?"


def test_json_that_is_not_a_tool_call_is_still_shown(db):
    model = ScriptedLLM([Reply('{"note": "just data"}')])
    events, _ = collect(db, None, model)
    assert "".join(e["text"] for e in events if e["type"] == "text") == '{"note": "just data"}'


def test_groq_needs_a_key():
    with pytest.raises(LLMError, match="Settings"):
        gateway.GroqLLM("", "m")


def test_ollama_streams_ndjson(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        lines = [
            {"message": {"content": "Hi "}, "done": False},
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "list_venues", "arguments": {}}}],
                },
                "done": True,
            },
        ]
        return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())

    _patch_http(monkeypatch, handler)
    out = _drain(gateway.OllamaLLM("http://localhost:11434", "qwen3.5:4b"))
    assert out[0] == "Hi " and out[-1].tool_calls[0].name == "list_venues"
    assert seen[0]["options"]["num_ctx"] == 8192 and seen[0]["think"] is False


def test_ollama_down_is_explained(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused")

    _patch_http(monkeypatch, handler)
    with pytest.raises(LLMError, match="isn't running"):
        _drain(gateway.OllamaLLM("http://localhost:11434", "qwen3.5:4b"))


def test_ollama_tool_messages_are_converted():
    m = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "1", "function": {"name": "x", "arguments": '{"a": 1}'}}],
    }
    assert gateway._to_ollama(m) == {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "x", "arguments": {"a": 1}}}],
    }
