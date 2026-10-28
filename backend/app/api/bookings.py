from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.api.availability import block_out, notice_out
from app.api.outbox import send_mail_after
from app.auth import get_current_user, get_via, require
from app.db import get_db
from app.models import Approval, Booking, Notification, User
from app.schemas import (
    ApprovalItemOut,
    ApprovalOut,
    BookingCheckOut,
    BookingIn,
    BookingOut,
    BookingSubmitIn,
    CancelIn,
    ClassClashOut,
    DecisionHistoryOut,
    DecisionIn,
    MoveOut,
    NotificationOut,
    OccurrenceOut,
    RelocationOptionOut,
    StudentDecisionIn,
    StudentOut,
    VenueBrief,
)
from app.services import bookings as svc
from app.services.access import can
from app.services.availability import PENDING_STATUSES
from app.services.timetables import slot_label

router = APIRouter(prefix="/api", tags=["bookings"])


def housekeeping(db: Session = Depends(get_db)) -> None:
    """Expire 24-hour waitlist offers that ran out (there is no background scheduler)."""
    if svc.expire_offers(db, datetime.now()):
        db.commit()


def venue_brief(v) -> VenueBrief:
    return VenueBrief(code=v.code, name=v.name, type=v.type, capacity=v.capacity)


def to_request(body: BookingIn) -> svc.BookingRequest:
    return svc.BookingRequest(
        venue_code=body.venue,
        title=body.title,
        event_type=body.event_type,
        expected_count=body.expected_count,
        date_from=body.date_from,
        date_to=body.date_to or body.date_from,
        start_time=body.start_time,
        end_time=body.end_time,
        description=body.description,
        requirements=body.requirements,
        moves=[svc.Move(m.slot_id, m.date, m.action, m.venue_code) for m in body.moves],
    )


def student_out(s) -> StudentOut:
    return StudentOut(
        id=s.id,
        name=s.name,
        register_no=s.register_no,
        class_label=s.class_label,
        decision=s.decision,
        comment=s.comment,
        decided_at=s.decided_at,
    )


def booking_out(db: Session, b: Booking, user: User | None) -> BookingOut:
    parent = db.get(Booking, b.parent_id) if b.parent_id else None
    mine = user is not None and b.requester_id == user.id
    return BookingOut(
        id=b.id,
        ref=b.ref,
        title=b.title,
        event_type=b.event_type,
        description=b.description,
        requirements=b.requirements,
        expected_count=b.expected_count,
        venue=venue_brief(b.venue),
        requester=b.requester_name,
        requester_email=b.requester.email if b.requester else (b.contact_email or ""),
        status=b.status,
        start=b.start_dt,
        end=b.end_dt,
        occurrences=[OccurrenceOut(start=o.start_dt, end=o.end_dt) for o in b.occurrences],
        approvals=[
            ApprovalOut(
                step=a.step,
                decision=a.decision,
                approver=a.approver.name if a.approver else None,
                comment=a.comment,
                decided_at=a.decided_at,
            )
            for a in b.approvals
        ],
        moves=[
            MoveOut(
                slot_id=m.slot_id,
                date=m.on_date,
                label=slot_label(m.slot),
                time=f"{m.slot.start:%H:%M}–{m.slot.end:%H:%M}",
                action=m.action,
                venue=m.new_venue.code if m.new_venue else None,
                faculty_name=m.slot.faculty_name,
            )
            for m in b.displacements
        ],
        steps=svc.steps_for(b),
        waitlist_position=svc.waitlist_position(db, b),
        offer_expires_at=b.offer_expires_at,
        cancel_reason=b.cancel_reason,
        parent_ref=parent.ref if parent else None,
        created_at=b.created_at,
        can_cancel=b.status in svc.OPEN_STATUSES and (mine or can(user, "approve_all")),
        can_reschedule=mine
        and b.status in ("pending_incharge", "pending_hod", "confirmed")
        and b.start_dt > datetime.now(),
        can_approve=svc.can_act(user, b),
        kind=b.kind,
        guide=b.guide.name if b.guide else None,
        students=[student_out(s) for s in b.students],
        # Staff can pass the number on to a group that lost it.
        tracking_code=b.tracking_code if user is not None else None,
        contact_email=b.contact_email if user is not None else None,
    )


def booking_or_404(db: Session, booking_id: int) -> Booking:
    b = db.get(Booking, booking_id)
    if b is None:
        raise HTTPException(404, "Booking not found")
    return b


def run(db: Session, fn, *args, **kwargs):
    try:
        result = fn(db, *args, **kwargs)
    except svc.BookingError as e:
        db.rollback()
        raise HTTPException(e.status, str(e)) from e
    db.commit()
    return result


# Booking form ----------------------------------------------------------------------------------


@router.get("/bookings/event-types")
def event_types() -> list[str]:
    return svc.EVENT_TYPES


@router.post(
    "/bookings/check", response_model=BookingCheckOut, dependencies=[Depends(housekeeping)]
)
def check_booking(
    body: BookingIn,
    reschedule_of: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require("book")),
) -> BookingCheckOut:
    ignore = frozenset({reschedule_of}) if reschedule_of else frozenset()
    try:
        result = svc.check_request(db, to_request(body), ignore)
    except svc.BookingError as e:
        raise HTTPException(e.status, str(e)) from e
    return BookingCheckOut(
        venue=venue_brief(result.venue),
        outcome=result.outcome,
        days=[s.date() for s, _ in result.occurrences],
        blocked=[block_out(b) for b in result.blocked],
        taken=[block_out(b) for b in result.taken],
        clashes=[
            ClassClashOut(
                slot_id=c.slot.id,
                date=c.on_date,
                label=slot_label(c.slot),
                subject_name=c.slot.subject_name,
                faculty_name=c.slot.faculty_name,
                start=c.slot.start,
                end=c.slot.end,
                batch_size=svc.batch_size(c.slot),
                options=[
                    RelocationOptionOut(
                        code=o.venue.code,
                        name=o.venue.name,
                        capacity=o.venue.capacity,
                        software_match=round(o.software_match, 2),
                        missing_software=o.missing_software,
                    )
                    for o in c.options
                ],
            )
            for c in result.clashes
        ],
        warnings=[notice_out(n) for n in result.warnings],
        alternatives=[venue_brief(v) for v in result.alternatives],
    )


@router.post("/bookings", response_model=BookingOut, status_code=201)
def create_booking(
    body: BookingSubmitIn,
    db: Session = Depends(get_db),
    user: User = Depends(require("book")),
    via: str = Depends(get_via),
) -> BookingOut:
    svc.expire_offers(db, datetime.now())
    parent = booking_or_404(db, body.reschedule_of) if body.reschedule_of else None
    b = run(
        db,
        svc.submit,
        user,
        to_request(body),
        join_waitlist=body.join_waitlist,
        reschedule=parent,
        via=via,
    )
    return booking_out(db, b, user)


@router.get("/bookings/mine", response_model=list[BookingOut], dependencies=[Depends(housekeeping)])
def my_bookings(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[BookingOut]:
    rows = db.scalars(
        select(Booking).where(Booking.requester_id == user.id).order_by(Booking.start_dt.desc())
    ).all()
    return [booking_out(db, b, user) for b in rows]


@router.get(
    "/bookings/guiding", response_model=list[BookingOut], dependencies=[Depends(housekeeping)]
)
def guiding(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[BookingOut]:
    """Student requests that named this person as their faculty guide."""
    rows = db.scalars(
        select(Booking).where(Booking.guide_id == user.id).order_by(Booking.start_dt.desc())
    ).all()
    return [booking_out(db, b, user) for b in rows]


@router.get(
    "/bookings/{booking_id}", response_model=BookingOut, dependencies=[Depends(housekeeping)]
)
def get_booking(
    booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> BookingOut:
    return booking_out(db, booking_or_404(db, booking_id), user)


@router.post(
    "/bookings/{booking_id}/cancel",
    response_model=BookingOut,
    dependencies=[Depends(send_mail_after)],
)
def cancel_booking(
    booking_id: int,
    body: CancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    via: str = Depends(get_via),
) -> BookingOut:
    b = run(db, svc.cancel, user, booking_or_404(db, booking_id), body.reason, via=via)
    return booking_out(db, b, user)


@router.post("/bookings/{booking_id}/accept-offer", response_model=BookingOut)
def accept_offer(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    via: str = Depends(get_via),
) -> BookingOut:
    b = run(db, svc.accept_offer, user, booking_or_404(db, booking_id), via=via)
    return booking_out(db, b, user)


@router.post(
    "/bookings/{booking_id}/approve",
    response_model=BookingOut,
    dependencies=[Depends(send_mail_after)],
)
def approve_booking(
    booking_id: int,
    body: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    via: str = Depends(get_via),
) -> BookingOut:
    b = run(db, svc.approve, user, booking_or_404(db, booking_id), body.comment, via=via)
    return booking_out(db, b, user)


@router.post(
    "/bookings/{booking_id}/reject",
    response_model=BookingOut,
    dependencies=[Depends(send_mail_after)],
)
def reject_booking(
    booking_id: int,
    body: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    via: str = Depends(get_via),
) -> BookingOut:
    b = run(db, svc.reject, user, booking_or_404(db, booking_id), body.comment or "", via=via)
    return booking_out(db, b, user)


@router.post(
    "/bookings/{booking_id}/students",
    response_model=BookingOut,
    dependencies=[Depends(send_mail_after)],
)
def decide_students(
    booking_id: int,
    body: StudentDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    via: str = Depends(get_via),
) -> BookingOut:
    """The faculty guide approves or rejects each student in a student request."""
    decisions = [(d.student_id, d.decision, d.comment) for d in body.decisions]
    b = run(db, svc.decide_students, user, booking_or_404(db, booking_id), decisions, via=via)
    return booking_out(db, b, user)


# Approvals queue -------------------------------------------------------------------------------


@router.get(
    "/approvals", response_model=list[ApprovalItemOut], dependencies=[Depends(housekeeping)]
)
def approval_queue(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ApprovalItemOut]:
    pending = db.scalars(
        select(Booking).where(Booking.status.in_(PENDING_STATUSES)).order_by(Booking.start_dt)
    ).all()
    return [
        ApprovalItemOut(
            booking=booking_out(db, b, user),
            step=svc.current_step(b) or "",
            notes=svc.approval_notes(db, b),
            waiting_behind=svc.waiting_behind(db, b),
        )
        for b in pending
        if svc.can_act(user, b)
    ]


@router.get("/approvals/history", response_model=list[DecisionHistoryOut])
def decision_history(
    limit: int = 100, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[DecisionHistoryOut]:
    """Requests this person has already approved or rejected, newest first."""
    decided = db.scalars(
        select(Approval)
        .where(Approval.approver_id == user.id)
        .order_by(Approval.decided_at.desc(), Approval.id.desc())
        .limit(min(max(limit, 1), 500))
    ).all()
    return [
        DecisionHistoryOut(
            booking=booking_out(db, a.booking, user),
            step=a.step,
            decision=a.decision,
            comment=a.comment,
            decided_at=a.decided_at,
        )
        for a in decided
    ]


# Notifications ---------------------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.id.desc())
            .limit(50)
        )
    )


@router.post("/notifications/read", status_code=204)
def mark_read(
    ids: list[int] | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Mark the given notifications (or all of them) as read."""
    query = update(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if ids:
        query = query.where(or_(*(Notification.id == i for i in ids)))
    db.execute(query.values(read_at=datetime.now()))
    db.commit()
    return Response(status_code=204)
