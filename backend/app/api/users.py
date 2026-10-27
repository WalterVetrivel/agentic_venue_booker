from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require
from app.db import get_db
from app.models import User
from app.schemas import UserBrief

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserBrief])
def list_users(
    db: Session = Depends(get_db), _: User = Depends(require("edit_venue_all"))
) -> list[UserBrief]:
    users = db.scalars(select(User).where(User.active).order_by(User.name)).all()
    return [UserBrief(id=u.id, name=u.name, email=u.email, roles=u.role_keys) for u in users]
