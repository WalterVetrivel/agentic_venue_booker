import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import require
from app.config import get_settings
from app.db import get_db
from app.ingest.timetable_parser import WEEKDAYS
from app.models import ClassSection, TimetableSlot, TimetableUpload, User
from app.schemas import (
    ClassSlotOut,
    SectionOut,
    TimetableReviewIn,
    TimetableUploadBrief,
    TimetableUploadOut,
)
from app.services import audit, timetables
from app.services.venues import get_venue

router = APIRouter(prefix="/api/timetables", tags=["timetables"])
MAX_BYTES = 5 * 1024 * 1024


def upload_out(u: TimetableUpload) -> TimetableUploadOut:
    data = json.loads(u.parsed)
    return TimetableUploadOut(
        id=u.id,
        filename=u.filename,
        status=u.status,
        uploaded_at=u.uploaded_at,
        header=data["header"],
        periods=data.get("periods", []),
        grid=data.get("grid", {}),
        slots=data["slots"],
        problems=data.get("problems", []),
        can_commit=data.get("can_commit", False) and u.status != "committed",
    )


def upload_or_404(db: Session, upload_id: int) -> TimetableUpload:
    upload = db.get(TimetableUpload, upload_id)
    if upload is None:
        raise HTTPException(404, "Upload not found")
    return upload


@router.post("/uploads", response_model=TimetableUploadOut, status_code=201)
def upload_timetable(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require("upload_timetables")),
) -> TimetableUploadOut:
    name = Path(file.filename or "timetable.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(422, "Please upload a PDF")
    folder = get_settings().upload_dir / "timetables"
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}.pdf"
    with stored.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    if stored.stat().st_size > MAX_BYTES:
        stored.unlink()
        raise HTTPException(413, "PDF is larger than 5 MB")
    try:
        upload = timetables.create_upload(db, user, name, stored)
    except Exception as exc:  # unreadable or not a PDF
        stored.unlink(missing_ok=True)
        raise HTTPException(422, f"Couldn't read this PDF: {exc}") from exc
    db.commit()
    return upload_out(upload)


@router.get("/uploads", response_model=list[TimetableUploadBrief])
def list_uploads(
    db: Session = Depends(get_db), _: User = Depends(require("upload_timetables"))
) -> list[TimetableUploadBrief]:
    uploads = db.scalars(select(TimetableUpload).order_by(TimetableUpload.id.desc())).all()
    out = []
    for u in uploads:
        data = json.loads(u.parsed)
        h = data["header"]
        label = f"{h['dept']} {h['year']}-{h['section']}" if h.get("section") else None
        out.append(
            TimetableUploadBrief(
                id=u.id,
                filename=u.filename,
                status=u.status,
                uploaded_at=u.uploaded_at,
                section=label,
                slots=len(data["slots"]),
                can_commit=data.get("can_commit", False) and u.status != "committed",
            )
        )
    return out


@router.get("/uploads/{upload_id}", response_model=TimetableUploadOut)
def get_upload(
    upload_id: int, db: Session = Depends(get_db), _: User = Depends(require("upload_timetables"))
) -> TimetableUploadOut:
    return upload_out(upload_or_404(db, upload_id))


@router.put("/uploads/{upload_id}", response_model=TimetableUploadOut)
def review_upload(
    upload_id: int,
    body: TimetableReviewIn,
    db: Session = Depends(get_db),
    _: User = Depends(require("upload_timetables")),
) -> TimetableUploadOut:
    upload = upload_or_404(db, upload_id)
    try:
        timetables.update_upload(
            db, upload, body.header.model_dump(), [s.model_dump() for s in body.slots]
        )
    except timetables.TimetableError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return upload_out(upload)


@router.post("/uploads/{upload_id}/commit", response_model=TimetableUploadOut)
def commit_upload(
    upload_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("upload_timetables")),
) -> TimetableUploadOut:
    upload = upload_or_404(db, upload_id)
    try:
        timetables.commit_upload(db, upload, user)
    except timetables.TimetableError as exc:
        db.commit()  # keep the refreshed review results
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return upload_out(upload)


@router.delete("/uploads/{upload_id}", status_code=204)
def discard_upload(
    upload_id: int, db: Session = Depends(get_db), _: User = Depends(require("upload_timetables"))
) -> Response:
    upload = upload_or_404(db, upload_id)
    if upload.status == "committed":
        raise HTTPException(
            409, "Committed timetables can't be discarded; remove the section instead"
        )
    Path(upload.stored_path).unlink(missing_ok=True)
    db.delete(upload)
    db.commit()
    return Response(status_code=204)


# Read-only views (public) -------------------------------------------------------------------


@router.get("/sections", response_model=list[SectionOut])
def list_sections(db: Session = Depends(get_db)) -> list[SectionOut]:
    counts = dict(
        db.execute(
            select(TimetableSlot.section_id, func.count()).group_by(TimetableSlot.section_id)
        ).all()
    )
    # Only classes that have had a timetable; the others exist so students can name them.
    uploaded = select(TimetableUpload.section_id).where(TimetableUpload.section_id.is_not(None))
    sections = db.scalars(
        select(ClassSection)
        .where(ClassSection.id.in_(uploaded) | ClassSection.id.in_(counts))
        .order_by(ClassSection.dept, ClassSection.year, ClassSection.section)
    ).all()
    return [
        SectionOut(
            id=s.id,
            label=s.label,
            dept=s.dept,
            year=s.year,
            section=s.section,
            advisor=s.advisor,
            lab_slots=counts.get(s.id, 0),
        )
        for s in sections
    ]


@router.delete("/sections/{section_id}", status_code=204)
def clear_section(
    section_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("upload_timetables")),
) -> Response:
    section = db.get(ClassSection, section_id)
    if section is None:
        raise HTTPException(404, "Section not found")
    removed = db.execute(
        delete(TimetableSlot).where(TimetableSlot.section_id == section_id)
    ).rowcount
    audit.record(db, user, "clear", "timetable", section_id, before={"slots": removed})
    db.commit()
    return Response(status_code=204)


@router.get("/slots", response_model=list[ClassSlotOut])
def list_slots(
    venue: str | None = None, section_id: int | None = None, db: Session = Depends(get_db)
) -> list[ClassSlotOut]:
    query = select(TimetableSlot)
    if venue:
        v = get_venue(db, venue)
        if v is None:
            raise HTTPException(404, "Venue not found")
        query = query.where(TimetableSlot.venue_id == v.id)
    if section_id:
        query = query.where(TimetableSlot.section_id == section_id)
    slots = db.scalars(query.order_by(TimetableSlot.weekday, TimetableSlot.start)).all()
    return [
        ClassSlotOut(
            id=s.id,
            section=s.section.label,
            term=s.term.name,
            venue=s.venue.code,
            weekday=WEEKDAYS[s.weekday],
            start=s.start,
            end=s.end,
            subject_code=s.subject_code,
            subject_name=s.subject_name,
            faculty_name=s.faculty_name,
            batch=s.batch,
        )
        for s in slots
    ]
