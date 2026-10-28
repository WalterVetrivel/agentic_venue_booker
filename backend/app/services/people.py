"""Matching names on timetables (faculty, class advisors) to staff accounts."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserRole

_TITLES = re.compile(r"\b(dr|mr|mrs|ms|prof)\b\.?", re.I)


def name_key(name: str) -> str:
    """Compare names without titles, punctuation or a trailing designation (", AP/CSE")."""
    name = name.split(",")[0]
    return re.sub(r"[^a-z]", "", _TITLES.sub("", name.lower()))


def faculty_matching(db: Session, name: str | None) -> list[User]:
    """Users whose name matches a timetable's faculty or advisor column."""
    if not name:
        return []
    key = name_key(name)
    return [u for u in db.scalars(select(User).where(User.active)) if name_key(u.name) == key]


def guides(db: Session) -> list[User]:
    """Staff a student group can name as its faculty guide: CSE faculty and the HOD."""
    rows = db.scalars(
        select(User)
        .join(UserRole)
        .where(User.active, UserRole.role_key.in_(("faculty", "hod")))
        .order_by(User.name)
    ).unique()
    return list(rows)
