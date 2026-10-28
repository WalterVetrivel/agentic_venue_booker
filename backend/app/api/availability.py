from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.venues import split_csv, venue_or_404
from app.db import get_db
from app.schemas import (
    BlockOut,
    CheckOut,
    DayAvailabilityOut,
    NoticeOut,
    VenueDayOut,
    VenueOut,
    VenueRangeDayOut,
    VenueRangeOut,
)
from app.services import availability
from app.services.venues import find_venues

router = APIRouter(prefix="/api/availability", tags=["availability"])


def block_out(b: availability.Block) -> BlockOut:
    return BlockOut(start=b.start, end=b.end, kind=b.kind, label=b.label, hard=b.hard)


def notice_out(n: availability.Notice) -> NoticeOut:
    return NoticeOut(kind=n.kind, message=n.message)


@router.get("", response_model=DayAvailabilityOut)
def day_availability(
    day: date = Query(alias="date"),
    type: str | None = None,
    min_capacity: int | None = Query(default=None, ge=1),
    needs: str | None = None,
    db: Session = Depends(get_db),
) -> DayAvailabilityOut:
    venues = find_venues(db, type=type, min_capacity=min_capacity, needs=split_csv(needs))
    hours = availability.OPEN_HOURS[day.weekday()]
    out = []
    for v in venues:
        view = availability.venue_day(db, v, day)
        out.append(
            VenueDayOut(
                code=v.code,
                name=v.name,
                type=v.type,
                capacity=v.capacity,
                byod=v.byod,
                blocks=[block_out(b) for b in view.blocks],
                warnings=[notice_out(n) for n in view.warnings],
            )
        )
    return DayAvailabilityOut(
        date=day,
        open_from=hours[0] if hours else None,
        open_to=hours[1] if hours else None,
        slot_minutes=availability.SLOT_MINUTES,
        venues=out,
    )


MAX_RANGE_DAYS = 45  # a month view with its leading and trailing days


@router.get("/venue/{code}", response_model=VenueRangeOut)
def venue_range(
    code: str,
    start: date,
    end: date,
    db: Session = Depends(get_db),
) -> VenueRangeOut:
    """One venue's classes, bookings and closures for each day from `start` to `end`."""
    v = venue_or_404(db, code)
    if end < start:
        raise HTTPException(422, "end must not be before start")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(422, f"Choose at most {MAX_RANGE_DAYS} days")
    days = []
    day = start
    while day <= end:
        view = availability.venue_day(db, v, day)
        hours = availability.OPEN_HOURS[day.weekday()]
        days.append(
            VenueRangeDayOut(
                date=day,
                open_from=hours[0] if hours else None,
                open_to=hours[1] if hours else None,
                blocks=[block_out(b) for b in view.blocks],
                warnings=[notice_out(n) for n in view.warnings],
            )
        )
        day += timedelta(days=1)
    return VenueRangeOut(code=v.code, name=v.name, days=days)


@router.get("/check", response_model=CheckOut)
def check(venue: str, start: datetime, end: datetime, db: Session = Depends(get_db)) -> CheckOut:
    v = venue_or_404(db, venue)
    if end <= start:
        raise HTTPException(422, "end must be after start")
    result = availability.check(db, v, start, end)
    return CheckOut(
        venue=v.code,
        start=start,
        end=end,
        free=result.free,
        needs_displacement=result.needs_displacement,
        conflicts=[block_out(b) for b in result.conflicts],
        classes=[block_out(b) for b in result.classes],
        warnings=[notice_out(n) for n in result.warnings],
    )


@router.get("/free", response_model=list[VenueOut])
def free_venues(
    start: datetime,
    end: datetime,
    type: str | None = None,
    min_capacity: int | None = Query(default=None, ge=1),
    needs: str | None = None,
    db: Session = Depends(get_db),
):
    if end <= start:
        raise HTTPException(422, "end must be after start")
    venues = find_venues(db, type=type, min_capacity=min_capacity, needs=split_csv(needs))
    return [v for v in venues if availability.check(db, v, start, end).free]
