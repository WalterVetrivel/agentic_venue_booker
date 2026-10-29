"""The assistant's chat: streamed replies (Server-Sent Events), saved conversations, attachments."""

import json
import shutil
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agent import runtime
from app.agent.llm import LLMError, make_llm, ollama_models
from app.agent.settings import llm_settings
from app.api import limits
from app.auth import get_current_user, require, user_from_request
from app.config import get_settings
from app.db import get_db, session_for
from app.ingest.doc_extractor import extract
from app.models import Booking, ChatMessage, Conversation, User
from app.schemas import (
    AttachmentOut,
    CardStateIn,
    ChatIn,
    ChatMessageOut,
    ConversationBrief,
    ConversationOut,
    ConversationRename,
    ProviderOut,
    ProvidersOut,
)
from app.services import audit, timetables
from app.services import bookings as booking_svc
from app.services import documents as document_svc
from app.services.access import can

router = APIRouter(prefix="/api/chat", tags=["chat"])

VISITOR_LIMIT = 20  # questions per visitor (by IP) ...
VISITOR_WINDOW = 600  # ... in this many seconds
MAX_BYTES = 5 * 1024 * 1024
_visits: dict[str, deque[float]] = defaultdict(deque)


def _visitor_allowed(ip: str) -> bool:
    now = time.monotonic()
    seen = _visits[ip]
    while seen and now - seen[0] > VISITOR_WINDOW:
        seen.popleft()
    if len(seen) >= VISITOR_LIMIT:
        return False
    seen.append(now)
    return True


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"


def _title(message: str) -> str:
    text = " ".join(message.split())
    return text if len(text) <= 60 else text[:57].rstrip() + "…"


def _drop_last_turn(db: Session, conversation: Conversation, message: str) -> None:
    """Forget the last question and its reply (if one was saved) before asking it again."""
    trail = list(conversation.messages[-2:])
    if trail and trail[-1].role == "assistant":
        reply = trail.pop()
        conversation.messages.remove(reply)
        db.delete(reply)
    if trail and trail[-1].role == "user" and trail[-1].content == message:
        conversation.messages.remove(trail[-1])
        db.delete(trail[-1])
    db.flush()


@router.post("")
async def chat(body: ChatIn, request: Request) -> StreamingResponse:
    """Answer one message. The reply streams as `data: {json}` events (see app.agent.runtime)."""
    with session_for(request.app) as db:
        user = user_from_request(request, db)
    if user is None and limits.enabled():
        ip = request.client.host if request.client else "?"
        if not _visitor_allowed(ip):
            raise HTTPException(429, "Too many questions for now. Try again in a few minutes.")

    async def events():
        with session_for(request.app) as db:
            # Load the user again in this session: the stream outlives the one above.
            me = db.get(User, user.id) if user else None
            conversation = None
            if me is not None:
                if body.conversation_id:
                    conversation = db.get(Conversation, body.conversation_id)
                    if conversation is None or conversation.user_id != me.id:
                        yield _sse({"type": "error", "message": "That conversation was not found."})
                        return
                    if body.regenerate:
                        _drop_last_turn(db, conversation, body.message)
                    history = [
                        {"role": m.role, "content": m.content} for m in conversation.messages
                    ]
                else:
                    conversation = Conversation(user_id=me.id, title=_title(body.message))
                    db.add(conversation)
                    history = []
            else:
                history = [t.model_dump() for t in body.history]

            try:
                llm = make_llm(llm_settings(db), body.provider, body.model)
            except LLMError as e:
                yield _sse({"type": "error", "message": str(e)})
                return

            prompt = body.message
            files = []
            if body.attachment:
                a = body.attachment
                prompt += f"\n\n[Attached file: {a.title}]\n{a.context}"
                files = [{"kind": "file", "title": a.title, "href": a.link}]
            if conversation is not None:
                conversation.provider, conversation.model = llm.provider, llm.model
                db.add(
                    ChatMessage(
                        conversation=conversation,
                        role="user",
                        content=body.message,
                        cards=json.dumps(files),
                    )
                )
                db.commit()
                yield _sse(
                    {"type": "conversation", "id": conversation.id, "title": conversation.title}
                )

            if body.form:
                prompt += runtime.form_note(body.form.kind, body.form.fields)
            messages = runtime.build_messages(db, me, llm, history, prompt)
            outcome = runtime.Outcome()
            force = runtime.draft_tool(body.message, me, body.form is not None)
            async for event in runtime.run(db, me, llm, messages, outcome, force):
                if event["type"] in ("done", "error") and conversation is not None:
                    reply = ChatMessage(
                        conversation=conversation,
                        role="assistant",
                        content=outcome.content or ("" if event["type"] == "done" else "…"),
                        steps=json.dumps(outcome.steps, default=str),
                        cards=json.dumps(outcome.cards),
                    )
                    db.add(reply)
                    conversation.updated_at = datetime.now()
                    db.commit()
                    event = {**event, "message_id": reply.id}
                yield _sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/providers", response_model=ProvidersOut)
async def providers(db: Session = Depends(get_db)) -> ProvidersOut:
    cfg = llm_settings(db)
    pulled = await ollama_models(cfg.ollama_base_url)
    groq_ready = bool(cfg.groq_api_key)
    return ProvidersOut(
        default=cfg.provider,
        demo=cfg.fake,
        providers=[
            ProviderOut(
                key="groq",
                label="Groq (online)",
                ready=groq_ready,
                note="" if groq_ready else "No API key yet: the Director can add one in Settings.",
                models=list(dict.fromkeys([cfg.groq_model, cfg.groq_fallback_model])),
                model=cfg.groq_model,
            ),
            ProviderOut(
                key="ollama",
                label="Ollama (this computer)",
                ready=bool(pulled),
                note="" if pulled else f"Ollama isn't running at {cfg.ollama_base_url}.",
                models=pulled or [cfg.ollama_model],
                model=cfg.ollama_model if cfg.ollama_model in pulled or not pulled else pulled[0],
            ),
        ],
    )


# Saved conversations ---------------------------------------------------------------------------


def _own(db: Session, user: User, conversation_id: int) -> Conversation:
    c = db.get(Conversation, conversation_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    return c


def _settle(db: Session, user: User, card: dict) -> dict:
    """An approve/reject card for a request that was decided since (here, on the approvals page
    or by someone else) shows how it ended instead of offering the buttons again."""
    if card.get("state") or not card.get("booking_id"):
        return card
    b = db.get(Booking, card["booking_id"])
    if b is None or booking_svc.can_act(user, b):
        return card
    mine = [a for a in b.approvals if a.approver_id == user.id]
    if mine:
        outcome = "Approved" if mine[-1].decision == "approved" else "Rejected"
        note = f"{b.ref} {outcome.lower()}."
    else:
        outcome = {"rejected": "Rejected", "cancelled": "Cancelled"}.get(b.status, "Closed")
        note = f"{b.ref} is no longer waiting for your approval."
    return card | {"state": "done", "outcome": outcome, "note": note}


def _message_out(db: Session, user: User, m: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        steps=json.loads(m.steps),
        cards=[_settle(db, user, c) for c in json.loads(m.cards)],
        created_at=m.created_at,
    )


@router.get("/conversations", response_model=list[ConversationBrief])
def list_conversations(
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require("save_chat_history")),
) -> list[Conversation]:
    query = select(Conversation).where(Conversation.user_id == user.id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Conversation.title.ilike(like),
                Conversation.id.in_(
                    select(ChatMessage.conversation_id).where(ChatMessage.content.ilike(like))
                ),
            )
        )
    return list(db.scalars(query.order_by(Conversation.updated_at.desc()).limit(50)))


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("save_chat_history")),
) -> ConversationOut:
    c = _own(db, user, conversation_id)
    return ConversationOut(
        **ConversationBrief.model_validate(c).model_dump(),
        messages=[_message_out(db, user, m) for m in c.messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationBrief)
def rename_conversation(
    conversation_id: int,
    body: ConversationRename,
    db: Session = Depends(get_db),
    user: User = Depends(require("save_chat_history")),
) -> Conversation:
    c = _own(db, user, conversation_id)
    c.title = body.title.strip()
    db.commit()
    return c


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("save_chat_history")),
) -> Response:
    db.delete(_own(db, user, conversation_id))
    db.commit()
    return Response(status_code=204)


@router.post("/messages/{message_id}/cards/{index}", status_code=204)
def set_card_state(
    message_id: int,
    index: int,
    body: CardStateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Remember that a card was confirmed or dismissed, so the history shows it."""
    m = db.get(ChatMessage, message_id)
    if m is None or m.conversation.user_id != user.id:
        raise HTTPException(404, "Message not found")
    cards = json.loads(m.cards)
    if not 0 <= index < len(cards):
        raise HTTPException(404, "Card not found")
    cards[index] |= {"state": body.state, "note": body.note}
    if body.outcome:
        cards[index]["outcome"] = body.outcome
    m.cards = json.dumps(cards)
    db.commit()
    return Response(status_code=204)


# Attachments -----------------------------------------------------------------------------------


@router.post("/attachments", response_model=AttachmentOut)
def attach(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AttachmentOut:
    """Read a PDF dropped into the chat.

    A timetable is parsed for review (people who upload timetables), a circular or report is
    added to the archive (people who upload documents), and anything else is only read so the
    assistant can answer questions about it.
    """
    name = Path(file.filename or "file.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(422, "Please attach a PDF")
    folder = get_settings().upload_dir / "chat"
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}.pdf"
    with stored.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    if stored.stat().st_size > MAX_BYTES:
        stored.unlink()
        raise HTTPException(413, "PDF is larger than 5 MB")
    try:
        return _read_attachment(db, user, name, stored)
    except HTTPException:
        stored.unlink(missing_ok=True)
        raise
    except Exception as exc:  # unreadable or not a PDF
        db.rollback()
        stored.unlink(missing_ok=True)
        raise HTTPException(422, f"Couldn't read this PDF: {exc}") from exc


def _read_attachment(db: Session, user: User, name: str, stored: Path) -> AttachmentOut:
    doc = extract(stored)
    if doc.kind in ("circular", "report") and can(user, "upload_documents"):
        final = stored.parent.parent / "documents" / stored.name
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(stored, final)
        try:
            d = document_svc.ingest(db, final, user, name)
        except document_svc.DocumentError as e:
            final.unlink(missing_ok=True)
            raise HTTPException(422, str(e)) from e
        audit.record(db, user, "upload", "document", d.id, after={"ref_no": d.ref_no}, via="agent")
        db.commit()
        event = document_svc.event_for(db, d.id)
        summary = {
            "added_to_archive": True,
            "kind": d.kind,
            "ref": d.ref_no,
            "event": event.title if event else None,
            "dates": f"{event.start_date} to {event.end_date}" if event else None,
            "venues": [v.code for v in event.venues] if event else [],
            "needs_review": bool(event and event.needs_review),
        }
        link = f"/documents/events/{event.id}" if event else "/documents?tab=manage"
        return AttachmentOut(kind="document", title=name, context=json.dumps(summary), link=link)

    if can(user, "upload_timetables") and doc.kind not in ("circular", "report"):
        data = timetables.parse_upload(db, stored)
        if data["header"].get("section") and data["slots"]:
            final = stored.parent.parent / "timetables" / stored.name
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(stored, final)
            upload = timetables.create_upload(db, user, name, final)
            db.commit()
            context = (
                f"A class timetable was uploaded for review (upload_id {upload.id}). "
                "Call review_timetable_upload to see what was read and any problems."
            )
            return AttachmentOut(
                kind="timetable", title=name, context=context, link=f"/timetables/{upload.id}"
            )

    text = doc.text.strip()
    stored.unlink(missing_ok=True)
    if not text:
        raise HTTPException(422, "There's no text in this PDF (is it a scan?)")
    return AttachmentOut(kind="text", title=name, context=f"Text of the file:\n{text[:6000]}")
