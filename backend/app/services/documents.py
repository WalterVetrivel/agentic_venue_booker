"""Circulars and event reports: storing them, turning them into past events, and searching them.

A circular announces an event and its report describes how it went, so the two become one
PastEvent. Each document's text is indexed for keyword search (SQLite FTS5, BM25) and, when
Ollama is running, embedded for meaning-based search; the two rankings are merged with
reciprocal rank fusion. The assistant (Phase 5) cites the documents this finds.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.agent.settings import llm_settings
from app.config import get_settings
from app.ingest.doc_extractor import (
    ExtractedDoc,
    event_type_for,
    extract,
    hall_candidates,
    series_key,
    venue_parts,
)
from app.models import DocChunk, Document, PastEvent, PastEventVenue, User, Venue
from app.services.embeddings import cosine, get_embedder, pack, unpack
from app.services.timetables import resolve_venue
from app.services.venues import get_venue

log = logging.getLogger(__name__)
MATCH_DAYS = 7  # a report's date may differ a little from its circular's
RRF_K = 60
STOPWORDS = frozenset(
    "a an and are at be by did do does for from had has have held how in is it its of on or "
    "the this to was were what when where which who why with any all".split()
)
PLAIN_FIELDS = (
    "audience",
    "expected_count",
    "participants",
    "registered",
    "resource_persons",
    "rating",
)
FTS_DELETE = text(
    "INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, text) VALUES('delete', :id, :t)"
)
FTS_INSERT = text("INSERT INTO doc_chunks_fts(rowid, text) VALUES (:id, :t)")
# Matched words in snippets are wrapped in these (control characters never occur in the PDFs).
MARK, UNMARK = "\x02", "\x03"
KIND_LABELS = {"circular": "Circular", "report": "Report"}


class DocumentError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


# Ingest -----------------------------------------------------------------------------------------


def _fields(doc: ExtractedDoc) -> dict:
    data = asdict(doc)
    for key in ("text", "problems", "kind", "ref_no"):
        data.pop(key)
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in data.items()}


def resolve_venues(db: Session, raw: str | None) -> tuple[list[Venue], list[str]]:
    """Venues named in a circular's venue cell, and the names we couldn't match."""
    if not raw:
        return [], []
    codes, hall = venue_parts(raw)
    found: list[Venue] = []
    unknown = []
    for code in codes:
        v = get_venue(db, code)
        (found.append(v) if v else unknown.append(code))
    if hall:
        v = next((v for n in hall_candidates(hall) if (v := resolve_venue(db, n))), None)
        (found.append(v) if v else unknown.append(hall))
    return list({v.id: v for v in found}.values()), unknown


def ingest(
    db: Session,
    path: Path,
    user: User | None = None,
    filename: str | None = None,
    *,
    embed: bool = True,
) -> Document:
    """Read a PDF, store it, and update its past event. Re-uploading a reference replaces it."""
    doc = extract(path)
    if doc.kind == "unknown":
        raise DocumentError("This doesn't look like a KIOT circular or event report.")
    kept = None
    if doc.ref_no:
        old = db.scalar(
            select(Document).where(Document.kind == doc.kind, Document.ref_no == doc.ref_no)
        )
        if old is not None:  # a corrected copy: keep its event (and any edits to it)
            kept = event_for(db, old.id)
            remove(db, old, keep_event=True)
    row = Document(
        kind=doc.kind,
        filename=filename or path.name,
        stored_path=str(path),
        ref_no=doc.ref_no,
        department=doc.department,
        academic_year=doc.academic_year,
        issued_on=doc.issued_on,
        text=doc.text,
        fields=json.dumps(_fields(doc)),
        problems=json.dumps(doc.problems),
        uploaded_by_id=user.id if user else None,
    )
    db.add(row)
    db.flush()
    event = kept or _match_event(db, doc)
    if event is None:
        event = PastEvent(title=doc.title or row.filename, series_key="", event_type="Other")
        db.add(event)
    setattr(event, f"{doc.kind}_id", row.id)
    db.flush()
    db.expire(event, ["circular", "report"])
    refresh_event(db, event)
    _index(db, row, event, embed=embed)
    return row


def _match_event(db: Session, doc: ExtractedDoc) -> PastEvent | None:
    """The event the other half (circular or report) of this document already created."""
    if not doc.title or not doc.start_date:
        return None
    slot = PastEvent.circular_id if doc.kind == "circular" else PastEvent.report_id
    candidates = db.scalars(
        select(PastEvent).where(
            slot.is_(None),
            PastEvent.series_key == series_key(doc.title),
            PastEvent.start_date.between(
                doc.start_date - timedelta(days=MATCH_DAYS),
                doc.start_date + timedelta(days=MATCH_DAYS),
            ),
        )
    ).all()
    return min(candidates, key=lambda e: abs((e.start_date - doc.start_date).days), default=None)


def _doc_fields(d: Document | None) -> dict:
    return json.loads(d.fields) if d else {}


def refresh_event(db: Session, event: PastEvent) -> None:
    """Rebuild an event from its documents; the report's details win over the circular's."""
    if event.edited:
        return
    merged: dict = {}
    for d in (event.circular, event.report):
        merged |= {k: v for k, v in _doc_fields(d).items() if v not in (None, [], "")}
    if not merged:
        return
    title = merged.get("title") or event.title
    event.title = title
    event.series_key = series_key(title)
    event.event_type = event_type_for(title)
    event.department = merged.get("department")
    event.venue_text = merged.get("venue_text")
    for key in ("start_date", "end_date"):
        setattr(event, key, date.fromisoformat(merged[key]) if merged.get(key) else None)
    for key in ("start_time", "end_time"):
        value = merged.get(key)
        setattr(event, key, datetime.strptime(value[:5], "%H:%M").time() if value else None)
    for key in PLAIN_FIELDS:
        setattr(event, key, merged.get(key))
    event.topics = ", ".join(merged.get("topics") or []) or None
    problems = []
    for d in (event.circular, event.report):
        problems += json.loads(d.problems) if d else []
    venues, unknown = resolve_venues(db, event.venue_text)
    problems += [f"Venue “{name}” isn't in the venue list." for name in unknown]
    set_venues(db, event, venues)
    event.problems = json.dumps(list(dict.fromkeys(problems)))
    event.needs_review = bool(problems)


def set_venues(db: Session, event: PastEvent, venues: list[Venue]) -> None:
    db.execute(delete(PastEventVenue).where(PastEventVenue.event_id == event.id))
    db.add_all(PastEventVenue(event_id=event.id, venue_id=v.id) for v in venues)
    db.flush()
    db.expire(event, ["venues"])


def remove(db: Session, d: Document, *, keep_event: bool = False) -> None:
    """Delete a document, its index entry, and its event if nothing else describes it."""
    for event in db.scalars(
        select(PastEvent).where((PastEvent.circular_id == d.id) | (PastEvent.report_id == d.id))
    ):
        if event.circular_id == d.id:
            event.circular_id = None
        if event.report_id == d.id:
            event.report_id = None
        db.flush()
        db.expire(event, ["circular", "report"])
        if keep_event:
            continue
        if event.circular_id is None and event.report_id is None:
            db.delete(event)
        else:
            refresh_event(db, event)
    for chunk in db.scalars(select(DocChunk).where(DocChunk.document_id == d.id)):
        db.execute(
            FTS_DELETE,
            {"id": chunk.id, "t": chunk.text},
        )
        db.delete(chunk)
    uploads = get_settings().upload_dir.resolve()
    stored = Path(d.stored_path).resolve()
    if uploads in stored.parents:  # never delete the seed's mock files
        stored.unlink(missing_ok=True)
    db.delete(d)
    db.flush()


# Index ------------------------------------------------------------------------------------------


def body_text(d: Document) -> str:
    """The document text without the college letterhead."""
    lines = d.text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(r"(Circular|Report) No\.", ln)), 0)
    body = "\n".join(lines[start:])
    return re.sub(r"\(cid:\d+\)\s*", "• ", body)


def chunk_text(d: Document, event: PastEvent) -> str:
    """A short header of the key facts (helps both search modes), then the body."""
    venues = ", ".join(f"{v.code} {v.name}" for v in event.venues) or event.venue_text or ""
    when = f"{event.start_date:%d %B %Y}" if event.start_date else ""
    if event.end_date and event.end_date != event.start_date:
        when += f" to {event.end_date:%d %B %Y}"
    header = [
        f"{KIND_LABELS[d.kind]} {d.ref_no or ''}: {event.title}",
        f"Type: {event.event_type}. Department: {event.department or ''}.",
        f"Venue: {venues}. Date: {when}.",
    ]
    return "\n".join(header) + "\n\n" + body_text(d)


def _index(db: Session, d: Document, event: PastEvent, *, embed: bool) -> None:
    chunk = DocChunk(document_id=d.id, text=chunk_text(d, event))
    db.add(chunk)
    db.flush()
    db.execute(
        FTS_INSERT,
        {"id": chunk.id, "t": chunk.text},
    )
    if embed:
        embed_chunks(db, [chunk])


def reindex_event(db: Session, event: PastEvent) -> None:
    """Rebuild the search text of an event's documents after a correction."""
    db.flush()
    db.expire(event, ["venues"])
    chunks = []
    for d in (event.circular, event.report):
        if d is None:
            continue
        for chunk in db.scalars(select(DocChunk).where(DocChunk.document_id == d.id)):
            db.execute(FTS_DELETE, {"id": chunk.id, "t": chunk.text})
            chunk.text = chunk_text(d, event)
            chunk.embedding = chunk.embed_model = None
            db.execute(FTS_INSERT, {"id": chunk.id, "t": chunk.text})
            chunks.append(chunk)
    embed_chunks(db, chunks)


def embedder_for(db: Session):
    """The embedder, using the Ollama address the assistant uses (Settings page, then .env)."""
    return get_embedder(llm_settings(db).ollama_base_url)


def warm_up() -> None:
    """Load the embedding model in Ollama when the backend starts, so the first search after
    starting doesn't wait for it. Runs in the background; does nothing if Ollama is off."""
    if get_embedder() is None:
        return
    from app.db import SessionLocal

    try:
        with SessionLocal() as db:
            embedder = embedder_for(db)
        if embedder is not None and embedder.embed(["warm-up"]) is not None:
            log.info("Embedding model %s is loaded in Ollama", embedder.model)
    except Exception:  # never let a warm-up stop the backend (e.g. before migrations ran)
        log.exception("Couldn't warm up the embedding model")


def embed_chunks(db: Session, chunks: list[DocChunk], batch: int = 16) -> int:
    """Store embeddings when Ollama is reachable. Returns how many were embedded."""
    embedder = embedder_for(db)
    if embedder is None:
        return 0
    done = 0
    for i in range(0, len(chunks), batch):
        part = chunks[i : i + batch]
        vectors = embedder.embed([c.text for c in part])
        if vectors is None:
            break
        for c, v in zip(part, vectors, strict=True):
            c.embedding, c.embed_model = pack(v), embedder.model
        done += len(part)
    db.flush()
    return done


def embed_missing(db: Session) -> int:
    """Embed documents added while Ollama was off (or with another model)."""
    embedder = embedder_for(db)
    if embedder is None:
        return 0
    chunks = db.scalars(
        select(DocChunk).where(
            (DocChunk.embedding.is_(None)) | (DocChunk.embed_model != embedder.model)
        )
    ).all()
    return embed_chunks(db, list(chunks))


# Search -----------------------------------------------------------------------------------------


@dataclass
class SearchHit:
    document: Document
    event: PastEvent | None
    score: float
    snippet: str
    matched_by: list[str]  # "keywords", "meaning"


def fts_query(query: str) -> str | None:
    """Turn free text into an FTS5 query: any of the words, each quoted so nothing is syntax."""
    words = [w for w in re.findall(r"\w+", query.lower()) if w not in STOPWORDS]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words)) or None


def _keyword_ranking(db: Session, query: str) -> list[tuple[int, str]]:
    q = fts_query(query)
    if q is None:
        return []
    rows = db.execute(
        text(
            "SELECT c.document_id, snippet(doc_chunks_fts, 0, :mark, :unmark, ' … ', 24) "
            "FROM doc_chunks_fts JOIN doc_chunks c ON c.id = doc_chunks_fts.rowid "
            "WHERE doc_chunks_fts MATCH :q ORDER BY bm25(doc_chunks_fts)"
        ),
        {"q": q, "mark": MARK, "unmark": UNMARK},
    ).all()
    return [(r[0], r[1]) for r in rows]


def _vector_ranking(db: Session, query: str) -> list[int]:
    embedder = embedder_for(db)
    if embedder is None:
        return []
    vectors = embedder.embed([query], query=True)
    if not vectors:
        return []
    rows = db.execute(
        select(DocChunk.document_id, DocChunk.embedding).where(
            DocChunk.embed_model == embedder.model, DocChunk.embedding.is_not(None)
        )
    ).all()
    scored = sorted(((cosine(vectors[0], unpack(e)), doc_id) for doc_id, e in rows), reverse=True)
    return [doc_id for _, doc_id in scored[:50]]


def event_for(db: Session, doc_id: int) -> PastEvent | None:
    return db.scalar(
        select(PastEvent).where((PastEvent.circular_id == doc_id) | (PastEvent.report_id == doc_id))
    )


def _allowed(
    event: PastEvent | None,
    d: Document,
    kind: str | None,
    venue: Venue | None,
    event_type: str | None,
    year: str | None,
) -> bool:
    if kind and d.kind != kind:
        return False
    if year and d.academic_year != year:
        return False
    if venue and not (event and any(v.id == venue.id for v in event.venues)):
        return False
    return not (event_type and not (event and event.event_type == event_type))


def search(
    db: Session,
    query: str,
    *,
    kind: str | None = None,
    venue_code: str | None = None,
    event_type: str | None = None,
    year: str | None = None,
    limit: int = 8,
) -> list[SearchHit]:
    """Hybrid search: BM25 keywords plus (when available) embeddings, merged by rank."""
    keyword = _keyword_ranking(db, query)
    meaning = _vector_ranking(db, query)
    snippets = dict(keyword)
    scores: dict[int, float] = {}
    how: dict[int, list[str]] = {}
    for label, ids in (("keywords", [k for k, _ in keyword]), ("meaning", meaning)):
        for rank, doc_id in enumerate(ids):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            how.setdefault(doc_id, []).append(label)
    venue = get_venue(db, venue_code) if venue_code else None
    hits = []
    for doc_id in sorted(scores, key=scores.get, reverse=True):
        d = db.get(Document, doc_id)
        event = event_for(db, doc_id)
        if d is None or not _allowed(event, d, kind, venue, event_type, year):
            continue
        snippet = snippets.get(doc_id) or body_text(d)[:240]
        hits.append(SearchHit(d, event, scores[doc_id], clean_snippet(snippet), how[doc_id]))
        if len(hits) == limit:
            break
    return hits


def clean_snippet(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# Recurring events -------------------------------------------------------------------------------

RECURRING_WINDOW_DAYS = 14
RECURRING_MIN_YEARS = 2


def _days_apart(a: date, b: date) -> int:
    """Distance between two dates ignoring the year (so 28 Dec and 3 Jan are 6 days apart)."""
    best = 366
    for year in (b.year - 1, b.year, b.year + 1):
        try:
            other = a.replace(year=year)
        except ValueError:  # 29 Feb
            other = a.replace(year=year, day=28)
        best = min(best, abs((other - b).days))
    return best


@dataclass
class RecurringEvent:
    title: str
    series_key: str
    years: list[int]
    refs: list[str]


def recurring_at(db: Session, venue: Venue, day: date) -> list[RecurringEvent]:
    """Series held in this venue around this time of year in at least two earlier years."""
    events = db.scalars(
        select(PastEvent)
        .join(PastEventVenue, PastEventVenue.event_id == PastEvent.id)
        # Earlier years only: this year's run of the series, if any, doesn't predict anything.
        .where(PastEventVenue.venue_id == venue.id, PastEvent.start_date < day - timedelta(days=60))
        .order_by(PastEvent.start_date)
    ).all()
    series: dict[str, list[PastEvent]] = {}
    for e in events:
        ends = [d for d in (e.start_date, e.end_date) if d]
        if ends and min(_days_apart(d, day) for d in ends) <= RECURRING_WINDOW_DAYS:
            series.setdefault(e.series_key, []).append(e)
    found = []
    for key, group in series.items():
        years = sorted({e.start_date.year for e in group})
        if len(years) >= RECURRING_MIN_YEARS:
            refs = [d.ref_no for e in group for d in (e.circular, e.report) if d and d.ref_no]
            title = re.sub(r"\s*\b20\d\d(-\d\d)?\b", "", group[-1].title).strip(" -")
            found.append(RecurringEvent(title, key, years, refs))
    return found
