import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record(
    db: Session,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: int | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    via: str = "ui",
    at: datetime | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=json.dumps(before, default=str) if before is not None else None,
            after=json.dumps(after, default=str) if after is not None else None,
            via=via,
            **({"at": at} if at else {}),
        )
    )
