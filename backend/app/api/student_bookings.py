"""Student requests: public (no login), tracked by the number each request gets."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.availability import notice_out
from app.api.bookings import run, student_out, venue_brief
from app.api.limits import Window
from app.api.outbox import send_mail_after
from app.auth import get_via
from app.config import get_settings
from app.db import get_db
from app.models import Booking, ClassSection
from app.schemas import (
    CancelIn,
    ClassOptionOut,
    GuideOut,
    OccurrenceOut,
    StudentBookingIn,
    StudentCheckOut,
    StudentOptionsOut,
    StudentSlotIn,
    StudentTrackOut,
    TrackStepOut,
)
from app.services import bookings as svc
from app.services import student_bookings as student_svc
from app.services.people import guides
from app.services.venues import find_venues

router = APIRouter(prefix="/api/student", tags=["student bookings"])

SUBMITS = Window(5, 3600, "Too many requests from here for now. Try again in an hour.")
LOOKUPS = Window(60, 600, "Too many lookups for now. Try again in a few minutes.")


def track_out(db: Session, b: Booking) -> StudentTrackOut:
    decided = {a.step: a for a in b.approvals}
    current = svc.current_step(b)
    steps = []
    for step in svc.steps_for(b):
        a = decided.get(step)
        if a is not None:
            state = "done" if a.decision == "approved" else "rejected"
        elif step == current:
            state = "current"
        elif b.status in ("rejected", "cancelled"):
            state = "skipped"
        else:
            state = "waiting"
        steps.append(
            TrackStepOut(
                step=step,
                label=svc.STEP_LABELS[step].capitalize(),
                state=state,
                approver=a.approver.name if a and a.approver else None,
                comment=a.comment if a else None,
                decided_at=a.decided_at if a else None,
            )
        )
    return StudentTrackOut(
        ref=b.ref,
        tracking_code=b.tracking_code or "",
        status=b.status,
        venue=venue_brief(b.venue),
        reason=b.description or b.title,
        guide=b.guide.name if b.guide else None,
        contact_email=student_svc.mask_email(b.contact_email),
        occurrences=[OccurrenceOut(start=o.start_dt, end=o.end_dt) for o in b.occurrences],
        students=[student_out(s) for s in b.students],
        steps=steps,
        created_at=b.created_at,
        cancel_reason=b.cancel_reason,
        can_cancel=b.status in svc.OPEN_STATUSES,
    )


def by_code_or_404(db: Session, code: str) -> Booking:
    b = student_svc.find_by_code(db, code)
    if b is None:
        raise HTTPException(404, "No request has that tracking number. Check it and try again.")
    return b


@router.get("/options", response_model=StudentOptionsOut)
def options(db: Session = Depends(get_db)) -> StudentOptionsOut:
    """What the student form chooses from: classes, faculty guides and bookable venues."""
    sections = db.scalars(
        select(ClassSection).order_by(ClassSection.dept, ClassSection.year, ClassSection.section)
    ).all()
    venues = [v for v in find_venues(db) if v.type in student_svc.STUDENT_VENUE_TYPES]
    return StudentOptionsOut(
        sections=[
            ClassOptionOut(id=s.id, label=s.label, dept=s.dept, year=s.year, section=s.section)
            for s in sections
        ],
        guides=[GuideOut(id=u.id, name=u.name, designation=u.designation) for u in guides(db)],
        venues=[venue_brief(v) for v in venues],
        max_students=student_svc.MAX_STUDENTS,
        email_domain=get_settings().student_email_domain.strip().lstrip("@") or None,
    )


@router.post("/check", response_model=StudentCheckOut)
def check(body: StudentSlotIn, db: Session = Depends(get_db)) -> StudentCheckOut:
    req = student_svc.StudentRequest(
        venue_code=body.venue,
        date_from=body.date_from,
        date_to=body.date_to or body.date_from,
        start_time=body.start_time,
        end_time=body.end_time,
        reason="",
        guide_id=0,
        contact_email="",
        students=[student_svc.StudentIn("", 0)] * body.count,
    )
    try:
        result = student_svc.check_student_request(db, req)
    except svc.BookingError as e:
        raise HTTPException(e.status, str(e)) from e
    problem = student_svc.outcome_text(result)
    return StudentCheckOut(
        venue=venue_brief(result.venue),
        ok=problem is None,
        problem=problem,
        days=[s.date() for s, _ in result.occurrences],
        warnings=[notice_out(n) for n in result.warnings],
        alternatives=[venue_brief(v) for v in result.alternatives],
    )


@router.post(
    "/bookings",
    response_model=StudentTrackOut,
    status_code=201,
    dependencies=[Depends(send_mail_after)],
)
def submit(
    body: StudentBookingIn,
    request: Request,
    db: Session = Depends(get_db),
    via: str = Depends(get_via),
) -> StudentTrackOut:
    SUBMITS.check(request)
    req = student_svc.StudentRequest(
        venue_code=body.venue,
        date_from=body.date_from,
        date_to=body.date_to or body.date_from,
        start_time=body.start_time,
        end_time=body.end_time,
        reason=body.reason,
        guide_id=body.guide_id,
        contact_email=body.contact_email,
        students=[
            student_svc.StudentIn(s.name, s.section_id, s.register_no) for s in body.students
        ],
    )
    b = run(db, student_svc.submit_student, req, via=via)
    return track_out(db, b)


@router.get("/bookings/{code}", response_model=StudentTrackOut)
def track(code: str, request: Request, db: Session = Depends(get_db)) -> StudentTrackOut:
    LOOKUPS.check(request)
    return track_out(db, by_code_or_404(db, code))


@router.post(
    "/bookings/{code}/cancel",
    response_model=StudentTrackOut,
    dependencies=[Depends(send_mail_after)],
)
def cancel(
    code: str,
    body: CancelIn,
    request: Request,
    db: Session = Depends(get_db),
    via: str = Depends(get_via),
) -> StudentTrackOut:
    LOOKUPS.check(request)
    b = by_code_or_404(db, code)
    run(db, svc.cancel, None, b, body.reason, via=via, tracking_code=b.tracking_code)
    return track_out(db, b)
