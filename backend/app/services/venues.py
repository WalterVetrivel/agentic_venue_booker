from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Venue

TYPE_ORDER = {"lab": 0, "coe": 1, "seminar_hall": 2}


def missing_needs(venue: Venue, needs: list[str]) -> list[str]:
    """Needs (case-insensitive substrings) not met by any working equipment in the venue."""
    working = [e.name.lower() for e in venue.equipment if e.status == "working"]
    return [n for n in needs if not any(n.lower() in w for w in working)]


def find_venues(
    db: Session,
    *,
    type: str | None = None,
    min_capacity: int | None = None,
    needs: list[str] | None = None,
    codes: list[str] | None = None,
) -> list[Venue]:
    query = select(Venue)
    if type:
        query = query.where(Venue.type == type)
    if min_capacity:
        query = query.where(Venue.capacity >= min_capacity)
    if codes:
        query = query.where(Venue.code.in_([c.upper() for c in codes]))
    venues = db.scalars(query).unique().all()
    if needs:
        venues = [v for v in venues if not missing_needs(v, needs)]
    return sorted(venues, key=lambda v: (TYPE_ORDER.get(v.type, 9), v.id))


def get_venue(db: Session, code: str) -> Venue | None:
    return db.scalar(select(Venue).where(Venue.code == code.upper()))
