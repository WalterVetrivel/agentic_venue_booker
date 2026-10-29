import json
from pathlib import Path

import pytest
from sqlalchemy import select

import app.api.chat as chat_api
from app.agent import fake
from app.agent.llm import Reply, ToolCall
from app.config import get_settings
from app.models import AuditLog

MCP_HEADERS = {
    "accept": "application/json, text/event-stream",
    "mcp-protocol-version": "2025-06-18",
}
MOCK = get_settings().mock_data_dir


def mcp(client, method, params=None, token=None):
    headers = dict(MCP_HEADERS)
    if token:
        headers["authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    res = client.post("/mcp/", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["result"]


def events(res):
    return [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(chat_api, "make_llm", lambda cfg, p=None, m=None: fake.DemoLLM())


# MCP -------------------------------------------------------------------------------------------


def test_mcp_lists_public_tools_for_visitors(client):
    init = mcp(
        client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    )
    assert init["serverInfo"]["name"] == "kiot-venue-booker"
    tools = mcp(client, "tools/list")["tools"]
    assert {t["name"] for t in tools} == {
        "resolve_dates",
        "list_venues",
        "get_venue",
        "check_availability",
        "find_free_venues",
        "get_timetable",
        "track_student_booking",
        "draft_student_booking",
    }
    assert all(t["annotations"]["readOnlyHint"] for t in tools)


def test_mcp_acts_as_the_token_holder(client, login):
    login("tkcse@kiot.ac.in")
    token = client.get("/api/auth/mcp-token").json()["token"]
    client.cookies.clear()
    names = {t["name"] for t in mcp(client, "tools/list", token=token)["tools"]}
    assert "draft_booking" in names and "propose_decision" not in names

    args = {
        "venue": "DSH",
        "title": "Cloud workshop",
        "event_type": "Workshop",
        "expected_count": 100,
        "date": "2027-02-09",
        "start": "10:00",
        "end": "12:00",
    }
    result = mcp(client, "tools/call", {"name": "draft_booking", "arguments": args}, token)
    assert not result.get("isError")
    assert "/book?venue=DSH" in result["content"][1]["text"]

    denied = mcp(client, "tools/call", {"name": "draft_booking", "arguments": args})
    assert denied["isError"] and "log in" in denied["content"][0]["text"]


def test_mcp_tool_call_reads_live_data(client):
    result = mcp(
        client,
        "tools/call",
        {"name": "check_availability", "arguments": {"venue": "CC5", "date": "2027-02-09"}},
    )
    assert json.loads(result["content"][0]["text"])["venue"] == "CC5"


def test_mcp_token_needs_login(client):
    assert client.get("/api/auth/mcp-token").status_code == 401


# Chat ------------------------------------------------------------------------------------------


def test_details_given_with_a_form_open_go_on_that_form(client, demo):
    form = {"kind": "student", "fields": {"venue": "CC5", "reason": "Smart parking app"}}
    got = events(client.post("/api/chat", json={"message": "Add Arun from CSE II-D", "form": form}))
    (card,) = [e["card"] for e in got if e["type"] == "card"]
    assert card["href"].startswith("/book/student?")


def test_visitors_chat_without_saving(client, demo):
    res = client.post("/api/chat", json={"message": "Is CC5 free on 2027-02-09 10:00 to 11:00?"})
    assert res.headers["content-type"].startswith("text/event-stream")
    got = events(res)
    assert got[0]["type"] == "step" and got[-1]["type"] == "done"
    assert "message_id" not in got[-1]
    assert client.get("/api/chat/conversations").status_code == 401


def test_visitors_are_rate_limited(client, demo, monkeypatch, rate_limits):
    monkeypatch.setattr(chat_api, "VISITOR_LIMIT", 2)
    monkeypatch.setattr(chat_api, "_visits", chat_api.defaultdict(chat_api.deque))
    for _ in range(2):
        assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 429


def test_visitor_limits_are_off_by_default(client, demo, monkeypatch):
    monkeypatch.setattr(chat_api, "VISITOR_LIMIT", 2)
    monkeypatch.setattr(chat_api, "_visits", chat_api.defaultdict(chat_api.deque))
    for _ in range(3):
        assert client.post("/api/chat", json={"message": "hi"}).status_code == 200


@pytest.mark.writes_db
def test_staff_conversations_are_saved(client, login, demo):
    login("tkcse@kiot.ac.in")
    first = events(client.post("/api/chat", json={"message": "Book CC5 on 2027-02-09"}))
    conv = first[0]
    assert conv["type"] == "conversation" and conv["title"] == "Book CC5 on 2027-02-09"
    assert any(e["type"] == "card" for e in first)
    done = first[-1]

    events(client.post("/api/chat", json={"message": "list labs", "conversation_id": conv["id"]}))
    saved = client.get(f"/api/chat/conversations/{conv['id']}").json()
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"] * 2
    assert saved["messages"][1]["cards"][0]["kind"] == "draft"
    assert saved["messages"][1]["steps"][0]["tool"] == "draft_booking"

    res = client.post(f"/api/chat/messages/{done['message_id']}/cards/0", json={"state": "done"})
    assert res.status_code == 204
    saved = client.get(f"/api/chat/conversations/{conv['id']}").json()
    assert saved["messages"][1]["cards"][0]["state"] == "done"

    assert [c["id"] for c in client.get("/api/chat/conversations?q=labs").json()] == [conv["id"]]
    assert client.get("/api/chat/conversations?q=nothing-like-this").json() == []
    client.patch(f"/api/chat/conversations/{conv['id']}", json={"title": "CC5 workshop"})
    assert client.get("/api/chat/conversations").json()[0]["title"] == "CC5 workshop"

    login("swvcse@kiot.ac.in")
    assert client.get(f"/api/chat/conversations/{conv['id']}").status_code == 404
    other = events(client.post("/api/chat", json={"message": "hi", "conversation_id": conv["id"]}))
    assert other == [{"type": "error", "message": "That conversation was not found."}]

    login("tkcse@kiot.ac.in")
    assert client.delete(f"/api/chat/conversations/{conv['id']}").status_code == 204
    assert client.get("/api/chat/conversations").json() == []


@pytest.mark.writes_db
def test_saved_history_is_sent_to_the_model(client, login, monkeypatch):
    model = fake.ScriptedLLM([Reply("First answer."), Reply("Second answer.")])
    monkeypatch.setattr(chat_api, "make_llm", lambda cfg, p=None, m=None: model)
    login("tkcse@kiot.ac.in")
    conv = events(client.post("/api/chat", json={"message": "Question one"}))[0]
    client.post("/api/chat", json={"message": "Question two", "conversation_id": conv["id"]})
    roles = [(m["role"], m["content"]) for m in model.seen[1][1:]]
    assert roles == [
        ("user", "Question one"),
        ("assistant", "First answer."),
        ("user", "Question two"),
    ]


@pytest.mark.writes_db
def test_regenerate_replaces_the_last_reply(client, login, monkeypatch):
    model = fake.ScriptedLLM(
        [Reply("First answer."), Reply("Rate limited."), Reply("Better answer.")]
    )
    monkeypatch.setattr(chat_api, "make_llm", lambda cfg, p=None, m=None: model)
    login("tkcse@kiot.ac.in")
    conv = events(client.post("/api/chat", json={"message": "Question one"}))[0]
    ask = {"message": "Question two", "conversation_id": conv["id"]}
    client.post("/api/chat", json=ask)
    client.post("/api/chat", json={**ask, "regenerate": True})

    # The rerun sees the first turn only, not the reply it replaces.
    roles = [(m["role"], m["content"]) for m in model.seen[2][1:]]
    assert roles == [
        ("user", "Question one"),
        ("assistant", "First answer."),
        ("user", "Question two"),
    ]
    saved = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
    assert [m["content"] for m in saved] == [
        "Question one",
        "First answer.",
        "Question two",
        "Better answer.",
    ]


@pytest.mark.writes_db
def test_regenerate_after_a_lost_reply_keeps_one_question(client, login, monkeypatch, db):
    from app.models import ChatMessage

    model = fake.ScriptedLLM([Reply("First answer."), Reply("Second answer.")])
    monkeypatch.setattr(chat_api, "make_llm", lambda cfg, p=None, m=None: model)
    login("tkcse@kiot.ac.in")
    conv = events(client.post("/api/chat", json={"message": "Question one"}))[0]
    # The reply never arrived (the stream was cut): only the question was saved.
    reply = db.scalars(select(ChatMessage).where(ChatMessage.content == "First answer.")).one()
    db.delete(reply)
    db.commit()
    body = {"message": "Question one", "conversation_id": conv["id"], "regenerate": True}
    client.post("/api/chat", json=body)
    saved = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
    assert [m["content"] for m in saved] == ["Question one", "Second answer."]


def test_missing_groq_key_is_explained(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    monkeypatch.setattr(get_settings(), "llm_fake", False)
    got = events(client.post("/api/chat", json={"message": "hi", "provider": "groq"}))
    assert got[-1]["type"] == "error" and "Settings" in got[-1]["message"]


def test_providers_report_what_is_ready(client, monkeypatch):
    async def no_ollama(url):
        return []

    monkeypatch.setattr(chat_api, "ollama_models", no_ollama)
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    out = client.get("/api/chat/providers").json()
    groq, ollama = out["providers"]
    assert not groq["ready"] and "Director" in groq["note"]
    assert not ollama["ready"] and ollama["models"] == [get_settings().ollama_model]


@pytest.mark.writes_db
def test_cards_confirmed_from_chat_are_audited_as_agent(client, login, db):
    login("tkcse@kiot.ac.in")
    body = {
        "venue": "DSH",
        "title": "Cloud workshop",
        "event_type": "Workshop",
        "expected_count": 100,
        "date_from": "2027-02-09",
        "start_time": "10:00",
        "end_time": "12:00",
    }
    b = client.post("/api/bookings", json=body, headers={"X-Via": "agent"}).json()
    client.post(f"/api/bookings/{b['id']}/cancel", json={}, headers={"X-Via": "agent"})
    vias = db.scalars(select(AuditLog.via).where(AuditLog.entity_id == b["id"])).all()
    assert set(vias) == {"agent"}


# Attachments -----------------------------------------------------------------------------------


def _pdf(folder, index=0):
    return sorted((MOCK / folder).glob("*.pdf"))[index]


def _attach(client, path: Path):
    with path.open("rb") as f:
        return client.post(
            "/api/chat/attachments", files={"file": (path.name, f, "application/pdf")}
        )


@pytest.mark.writes_db
def test_attached_timetable_is_parsed_for_review(client, login, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    login("cseoa@kiot.ac.in")
    res = _attach(client, _pdf("timetables"))
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["kind"] == "timetable" and out["link"].startswith("/timetables/")
    assert "review_timetable_upload" in out["context"]


@pytest.mark.writes_db
def test_attached_circular_goes_to_the_archive_for_uploaders(client, login, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    login("hod.cse@kiot.ac.in")
    out = _attach(client, _pdf("circulars")).json()
    assert out["kind"] == "document" and json.loads(out["context"])["added_to_archive"]

    login("tkcse@kiot.ac.in")  # faculty can't add to the archive: the text is only read
    out = _attach(client, _pdf("circulars", 1)).json()
    assert out["kind"] == "text" and out["context"].startswith("Text of the file")


def test_attachments_need_login(client):
    assert _attach(client, _pdf("circulars")).status_code == 401


def test_attachment_context_reaches_the_model(client, monkeypatch):
    model = fake.ScriptedLLM([Reply("Noted.")])
    monkeypatch.setattr(chat_api, "make_llm", lambda cfg, p=None, m=None: model)
    attachment = {"kind": "text", "title": "notes.pdf", "context": "Text of the file:\nHello"}
    client.post("/api/chat", json={"message": "Summarise", "attachment": attachment})
    assert model.seen[0][-1]["content"].endswith(
        "[Attached file: notes.pdf]\nText of the file:\nHello"
    )


# Settings --------------------------------------------------------------------------------------


@pytest.mark.writes_db
def test_director_manages_llm_settings(client, login, monkeypatch, db):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    login("hod.cse@kiot.ac.in")
    assert client.get("/api/settings/llm").status_code == 403

    login("dirim@kiot.ac.in")
    out = client.get("/api/settings/llm").json()
    assert out["groq_key_source"] == "none" and not out["groq_key_set"]

    out = client.put(
        "/api/settings/llm",
        json={"groq_api_key": "gsk_abcdefghijklmnop1234", "provider": "ollama"},
    ).json()
    assert out["groq_key_masked"] == "gsk_…1234" and out["groq_key_source"] == "settings"
    assert out["provider"] == "ollama"
    assert "gsk_abcdefghijklmnop1234" not in client.get("/api/settings/llm").text
    logged = db.scalars(select(AuditLog.after).where(AuditLog.entity == "settings")).all()
    assert logged and "gsk_abc" not in logged[-1]

    monkeypatch.setattr(get_settings(), "groq_api_key", "gsk_from_env_file_0000")
    out = client.put("/api/settings/llm", json={"groq_api_key": ""}).json()
    assert out["groq_key_source"] == "env" and out["groq_key_masked"] == "gsk_…0000"


def test_connection_test_reports_problems(client, login, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    login("dirim@kiot.ac.in")
    out = client.post("/api/settings/llm/test", json={"provider": "groq"}).json()
    assert out == {"ok": False, "message": out["message"]} and "Groq isn't set up" in out["message"]


def test_demo_model_answers_scripted_questions():
    import asyncio

    async def ask(text, tools):
        return [x async for x in fake.DemoLLM().stream([{"role": "user", "content": text}], tools)]

    spec = [{"function": {"name": n}} for n in ("draft_booking", "check_availability")]
    reply = asyncio.run(ask("Can I book COE1 on 2027-02-09 2pm to 4pm?", spec))[-1]
    assert reply.tool_calls == [
        ToolCall(
            "call_1",
            "draft_booking",
            {
                "venue": "COE1",
                "title": "Python workshop",
                "event_type": "Workshop",
                "expected_count": 30,
                "date": "2027-02-09",
                "start": "14:00",
                "end": "16:00",
            },
        )
    ]


def test_signed_out_staff_are_sent_to_log_in(client, demo):
    from app.agent.prompts import LOGIN_LINK, system_prompt

    assert LOGIN_LINK in system_prompt(None, None)
    res = client.post("/api/chat", json={"message": "I'm faculty, book DSH tomorrow 10 to 12"})
    done = events(res)[-1]
    assert done["type"] == "done" and "/login?next=/book" in done["content"]
