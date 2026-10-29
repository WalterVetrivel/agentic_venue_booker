import json
import shutil
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require
from app.config import get_settings
from app.db import get_db
from app.ingest.doc_extractor import EVENT_TYPES
from app.models import DocChunk, Document, PastEvent, PastEventVenue, User
from app.schemas import (
    DocRef,
    DocumentDetailOut,
    DocumentOut,
    EventFacetsOut,
    PastEventBrief,
    PastEventOut,
    PastEventUpdate,
    SearchHitOut,
    SearchOut,
    UploadResultOut,
    VenueBrief,
)
from app.services import audit
from app.services import documents as svc
from app.services.venues import get_venue

router = APIRouter(prefix="/api", tags=["documents"])
MAX_BYTES = 5 * 1024 * 1024
ALL_EVENT_TYPES = sorted({t for _, t in EVENT_TYPES} | {"Other"})


def doc_ref(d: Document) -> DocRef:
    return DocRef(
        id=d.id,
        kind=d.kind,
        ref_no=d.ref_no,
        filename=d.filename,
        file_url=f"/api/documents/{d.id}/file",
    )


def event_brief(e: PastEvent | None) -> PastEventBrief | None:
    if e is None:
        return None
    return PastEventBrief(
        id=e.id,
        title=e.title,
        event_type=e.event_type,
        start_date=e.start_date,
        end_date=e.end_date,
        venues=[v.code for v in e.venues],
        needs_review=e.needs_review,
    )


def document_out(db: Session, d: Document) -> DocumentOut:
    return DocumentOut(
        **doc_ref(d).model_dump(),
        department=d.department,
        academic_year=d.academic_year,
        issued_on=d.issued_on,
        uploaded_at=d.uploaded_at,
        problems=json.loads(d.problems),
        event=event_brief(svc.event_for(db, d.id)),
    )


def event_out(e: PastEvent) -> PastEventOut:
    return PastEventOut(
        id=e.id,
        title=e.title,
        series_key=e.series_key,
        event_type=e.event_type,
        department=e.department,
        venue_text=e.venue_text,
        venues=[
            VenueBrief(code=v.code, name=v.name, type=v.type, capacity=v.capacity) for v in e.venues
        ],
        start_date=e.start_date,
        end_date=e.end_date,
        start_time=e.start_time,
        end_time=e.end_time,
        audience=e.audience,
        expected_count=e.expected_count,
        participants=e.participants,
        registered=e.registered,
        resource_persons=e.resource_persons,
        topics=[t.strip() for t in (e.topics or "").split(",") if t.strip()],
        rating=e.rating,
        needs_review=e.needs_review,
        problems=json.loads(e.problems),
        edited=e.edited,
        circular=doc_ref(e.circular) if e.circular else None,
        report=doc_ref(e.report) if e.report else None,
    )


def document_or_404(db: Session, doc_id: int) -> Document:
    d = db.get(Document, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    return d


# Documents --------------------------------------------------------------------------------------


@router.post("/documents", response_model=list[UploadResultOut], status_code=201)
def upload_documents(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require("upload_documents")),
) -> list[UploadResultOut]:
    """Upload circulars and event reports; each file is read and indexed on its own."""
    folder = get_settings().upload_dir / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for file in files:
        name = Path(file.filename or "document.pdf").name
        if not name.lower().endswith(".pdf"):
            results.append(UploadResultOut(filename=name, error="Not a PDF"))
            continue
        stored = folder / f"{uuid.uuid4().hex}.pdf"
        with stored.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
        if stored.stat().st_size > MAX_BYTES:
            stored.unlink()
            results.append(UploadResultOut(filename=name, error="Larger than 5 MB"))
            continue
        before = db.scalar(select(func.count(Document.id)))
        try:
            d = svc.ingest(db, stored, user, name)
        except svc.DocumentError as exc:
            stored.unlink(missing_ok=True)
            results.append(UploadResultOut(filename=name, error=str(exc)))
            continue
        except Exception as exc:  # unreadable PDF
            db.rollback()
            stored.unlink(missing_ok=True)
            results.append(UploadResultOut(filename=name, error=f"Couldn't read this PDF: {exc}"))
            continue
        replaced = db.scalar(select(func.count(Document.id))) == before
        audit.record(db, user, "upload", "document", d.id, after={"ref_no": d.ref_no})
        db.commit()
        results.append(
            UploadResultOut(filename=name, document=document_out(db, d), replaced=replaced)
        )
    return results


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    kind: str | None = None,
    year: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[DocumentOut]:
    query = select(Document).order_by(Document.issued_on.desc(), Document.id.desc())
    if kind:
        query = query.where(Document.kind == kind)
    if year:
        query = query.where(Document.academic_year == year)
    return [document_out(db, d) for d in db.scalars(query)]


@router.post("/documents/embed")
def embed_documents(
    db: Session = Depends(get_db), _: User = Depends(require("upload_documents"))
) -> dict[str, int]:
    """Embed documents added while Ollama was off."""
    done = svc.embed_missing(db)
    db.commit()
    return {"embedded": done}


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
def get_document(
    doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> DocumentDetailOut:
    d = document_or_404(db, doc_id)
    return DocumentDetailOut(
        **document_out(db, d).model_dump(), text=d.text, fields=json.loads(d.fields)
    )


@router.get("/documents/{doc_id}/file")
def document_file(
    doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> FileResponse:
    d = document_or_404(db, doc_id)
    path = Path(d.stored_path)
    if not path.is_file():
        raise HTTPException(404, "The PDF is no longer on the server")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=d.filename,
        content_disposition_type="inline",
    )


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(require("upload_documents"))
) -> Response:
    d = document_or_404(db, doc_id)
    audit.record(db, user, "delete", "document", d.id, before={"ref_no": d.ref_no})
    svc.remove(db, d)
    db.commit()
    return Response(status_code=204)


# Past events ------------------------------------------------------------------------------------


@router.get("/events/facets", response_model=EventFacetsOut)
def event_facets(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> EventFacetsOut:
    years = db.scalars(
        select(Document.academic_year)
        .where(Document.academic_year.is_not(None))
        .distinct()
        .order_by(Document.academic_year.desc())
    ).all()
    return EventFacetsOut(
        event_types=ALL_EVENT_TYPES,
        years=list(years),
        documents=db.scalar(select(func.count(Document.id))),
        events=db.scalar(select(func.count(PastEvent.id))),
        needs_review=db.scalar(select(func.count(PastEvent.id)).where(PastEvent.needs_review)),
        embedded=db.scalar(select(func.count(DocChunk.id)).where(DocChunk.embedding.is_not(None))),
        embeddings="on" if svc.embedder_for(db) else "off",
    )


def academic_year_bounds(year: str) -> tuple[date, date]:
    """'2024-25' runs from June 2024 to May 2025."""
    first = int(year[:4])
    return date(first, 6, 1), date(first + 1, 5, 31)


@router.get("/events", response_model=list[PastEventOut])
def list_events(
    q: str | None = None,
    venue: str | None = None,
    event_type: str | None = None,
    year: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    needs_review: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PastEventOut]:
    query = select(PastEvent).order_by(PastEvent.start_date.desc().nulls_last())
    if q:
        query = query.where(PastEvent.title.ilike(f"%{q.strip()}%"))
    if venue:
        v = get_venue(db, venue)
        if v is None:
            return []
        query = query.join(PastEventVenue, PastEventVenue.event_id == PastEvent.id).where(
            PastEventVenue.venue_id == v.id
        )
    if event_type:
        query = query.where(PastEvent.event_type == event_type)
    if year:
        start, end = academic_year_bounds(year)
        query = query.where(PastEvent.start_date.between(start, end))
    if needs_review is not None:
        query = query.where(PastEvent.needs_review == needs_review)
    return [event_out(e) for e in db.scalars(query).unique()]


@router.get("/events/{event_id}", response_model=PastEventOut)
def get_event(
    event_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> PastEventOut:
    e = db.get(PastEvent, event_id)
    if e is None:
        raise HTTPException(404, "Event not found")
    return event_out(e)


@router.put("/events/{event_id}", response_model=PastEventOut)
def correct_event(
    event_id: int,
    body: PastEventUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("upload_documents")),
) -> PastEventOut:
    """Fix what the extractor got wrong. Later re-uploads won't overwrite a corrected event."""
    e = db.get(PastEvent, event_id)
    if e is None:
        raise HTTPException(404, "Event not found")
    if body.event_type not in ALL_EVENT_TYPES:
        raise HTTPException(422, f"Unknown event type {body.event_type}")
    venues = []
    for code in body.venue_codes:
        v = get_venue(db, code)
        if v is None:
            raise HTTPException(422, f"Unknown venue {code}")
        venues.append(v)
    if not venues:
        raise HTTPException(422, "Choose at least one venue")
    before = event_out(e).model_dump(mode="json")
    e.title = body.title.strip()
    e.event_type = body.event_type
    e.start_date, e.end_date = body.start_date, body.end_date or body.start_date
    e.start_time, e.end_time = body.start_time, body.end_time
    e.participants, e.resource_persons = body.participants, body.resource_persons
    e.series_key = svc.series_key(e.title)
    svc.set_venues(db, e, venues)
    e.edited, e.needs_review, e.problems = True, False, "[]"
    svc.reindex_event(db, e)
    audit.record(db, user, "update", "past_event", e.id, before=before, after=body.model_dump())
    db.commit()
    db.refresh(e)
    return event_out(e)


# Search -----------------------------------------------------------------------------------------


@router.get("/search", response_model=SearchOut)
def search_documents(
    q: str = Query(min_length=2, max_length=300),
    kind: str | None = None,
    venue: str | None = None,
    event_type: str | None = None,
    year: str | None = None,
    limit: int = Query(8, ge=1, le=25),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SearchOut:
    hits = svc.search(
        db, q, kind=kind, venue_code=venue, event_type=event_type, year=year, limit=limit
    )
    meaning = any("meaning" in h.matched_by for h in hits)
    return SearchOut(
        query=q,
        mode="hybrid" if meaning else "keywords",
        hits=[
            SearchHitOut(
                document=doc_ref(h.document),
                event=event_brief(h.event),
                snippet=h.snippet,
                score=round(h.score, 5),
                matched_by=h.matched_by,
            )
            for h in hits
        ],
    )
