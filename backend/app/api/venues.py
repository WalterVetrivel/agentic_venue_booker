from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Venue
from app.schemas import VenueDetailOut, VenueOut

router = APIRouter(prefix="/api/venues", tags=["venues"])

TYPE_ORDER = {"lab": 0, "coe": 1, "seminar_hall": 2}


@router.get("", response_model=list[VenueOut])
def list_venues(type: str | None = None, db: Session = Depends(get_db)) -> list[Venue]:
    query = select(Venue)
    if type:
        query = query.where(Venue.type == type)
    venues = db.scalars(query).all()
    return sorted(venues, key=lambda v: (TYPE_ORDER.get(v.type, 9), v.id))


@router.get("/{code}", response_model=VenueDetailOut)
def get_venue(code: str, db: Session = Depends(get_db)) -> VenueDetailOut:
    venue = db.scalar(select(Venue).where(Venue.code == code.upper()))
    if venue is None:
        raise HTTPException(404, "Venue not found")
    return VenueDetailOut(
        **VenueOut.model_validate(venue).model_dump(),
        equipment=venue.equipment,
        aliases=[a.alias for a in venue.aliases],
    )
