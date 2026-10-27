from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models import Notification, User


def notify(
    db: Session,
    users: Iterable[User | None],
    kind: str,
    message: str,
    link: str | None = None,
    skip: User | None = None,
) -> None:
    """Send one in-app notification to each distinct user (never to `skip`, usually the actor)."""
    seen: set[int] = set()
    for user in users:
        if user is None or user.id in seen or (skip is not None and user.id == skip.id):
            continue
        seen.add(user.id)
        db.add(Notification(user_id=user.id, kind=kind, message=message, link=link))
