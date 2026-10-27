from datetime import date, time

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import DocChunk, Document, PastEvent
from app.services import availability
from app.services import bookings as booking_svc
from app.services import documents as svc
from app.services.embeddings import set_embedder
from app.services.venues import get_venue

MOCK = get_settings().mock_data_dir


def pdf(prefix: str):
    folder = MOCK / ("reports" if prefix.startswith("REPORT") else "circulars")
    (path,) = [p for p in folder.glob("*.pdf") if p.name.startswith(prefix)]
    return path


def warnings(db, code: str, day: date) -> list[str]:
    view = availability.venue_day(db, get_venue(db, code), day)
    return [w.message for w in view.warnings if w.kind == "recurring"]


# The whole corpus ---------------------------------------------------------------------------------


def test_every_document_becomes_an_event(docs_db):
    assert docs_db.scalar(select(func.count(Document.id))) == 276
    events = docs_db.scalars(select(PastEvent)).all()
    assert len(events) == 155
    assert sum(1 for e in events if e.circular_id and e.report_id) == 121
    assert all(e.venues for e in events)
    # Only the ten documents with an impossible time range (five events) need a person.
    assert sum(e.needs_review for e in events) == 5


def test_hackathon_in_the_coes_every_september(docs_db):
    for code in ("COE1", "COE2", "COE3"):
        (msg,) = warnings(docs_db, code, date(2027, 9, 17))
        assert msg.startswith("“KIOT In-house Hackathon” is usually held in")
        assert "2023, 2024, 2025 and 2026" in msg
    assert warnings(docs_db, "COE4", date(2027, 9, 17)) == []
    assert warnings(docs_db, "COE1", date(2027, 6, 15)) == []


def test_model_practicals_in_the_cc_labs_every_november(docs_db):
    for code in ("CC1", "CC2", "CC3", "CC4", "CC5", "CC6"):
        (msg,) = warnings(docs_db, code, date(2026, 11, 16))
        assert "Model Practical Examinations" in msg
    assert warnings(docs_db, "CC9", date(2026, 11, 16)) == []


def test_booking_check_warns_and_suggests_other_venues(docs_db):
    req = booking_svc.BookingRequest(
        venue_code="COE1",
        title="AI club meetup",
        event_type="Seminar",
        expected_count=30,
        date_from=date(2027, 9, 17),
        date_to=date(2027, 9, 17),
        start_time=time(10),
        end_time=time(12),
    )
    result = booking_svc.check_request(docs_db, req)
    assert any(w.kind == "recurring" for w in result.warnings)
    codes = [v.code for v in result.alternatives]
    assert codes and not {"COE2", "COE3"} & set(codes)


def test_search_filters(docs_db):
    hits = svc.search(docs_db, "hackathon", kind="report")
    assert hits and all(h.document.kind == "report" for h in hits)
    hits = svc.search(docs_db, "generative AI", venue_code="CC5")
    assert hits and all("CC5" in [v.code for v in h.event.venues] for h in hits)
    hits = svc.search(docs_db, "workshop", year="2024-25", event_type="Workshop")
    assert hits and all(h.document.academic_year == "2024-25" for h in hits)
    assert svc.search(docs_db, "the of and") == []


# Ingest, replace and delete -----------------------------------------------------------------------


@pytest.mark.writes_db
def test_circular_and_report_merge_into_one_event(db):
    svc.ingest(db, pdf("CIRCULAR NO.007 (CSE 2025-26)"))
    report = svc.ingest(db, pdf("REPORT EV0127 "))
    (event,) = db.scalars(select(PastEvent)).all()
    assert event.circular and event.report_id == report.id
    assert event.title == "Hands-on Workshop on Responsible AI"
    assert event.participants  # from the report
    assert [v.code for v in event.venues] == ["CC1"]

    # Uploading the same circular again replaces it but keeps the event.
    svc.ingest(db, pdf("CIRCULAR NO.007 (CSE 2025-26)"))
    assert db.scalar(select(func.count(Document.id))) == 2
    assert db.scalars(select(PastEvent)).all() == [event]

    svc.remove(db, report)
    assert event.report_id is None and event.participants is None
    svc.remove(db, event.circular)
    assert db.scalar(select(func.count(PastEvent.id))) == 0
    assert db.scalar(select(func.count(DocChunk.id))) == 0
    assert svc.search(db, "responsible AI") == []  # the keyword index is cleaned up too


@pytest.mark.writes_db
def test_corrections_survive_a_reupload(db):
    svc.ingest(db, pdf("REPORT EV0115 "))
    event = db.scalar(select(PastEvent))
    assert event.needs_review
    event.end_time, event.edited, event.needs_review = time(15, 55), True, False
    svc.ingest(db, pdf("REPORT EV0115 "))
    assert event.end_time == time(15, 55) and not event.needs_review


class FakeEmbedder:
    """Puts hackathons and 'coding marathon' close together, everything else far away."""

    model = "fake"

    def embed(self, texts, *, query=False):
        def vec(t):
            t = t.lower()
            return [1.0, 0.0] if "hackathon" in t or "marathon" in t else [0.0, 1.0]

        return [vec(t) for t in texts]


@pytest.mark.writes_db
def test_meaning_search_finds_what_keywords_miss(db):
    set_embedder(FakeEmbedder())
    try:
        svc.ingest(db, pdf("CIRCULAR NO.004 (CSE 2023-24)"))  # the 2023 hackathon
        svc.ingest(db, pdf("CIRCULAR NO.002 (IT 2023-24)"))  # an SQL workshop
        assert db.scalar(select(func.count(DocChunk.id)).where(DocChunk.embed_model == "fake")) == 2
        (top, *_) = svc.search(db, "overnight marathon event")
        assert "Hackathon" in top.event.title and top.matched_by == ["meaning"]
    finally:
        set_embedder(None)
    assert svc.embed_missing(db) == 0  # embeddings off: nothing to do
