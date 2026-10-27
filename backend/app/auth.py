from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.permissions import has_capability

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: int) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.app_secret, algorithm=ALGORITHM)


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return None
    return user


def user_from_request(request: Request, db: Session) -> User | None:
    """The logged-in user, from the session cookie or an `Authorization: Bearer` token."""
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    if not token:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() or None
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.app_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(payload["sub"]))
    return user if user and user.active else None


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return user_from_request(request, db)


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


def require(capability: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_capability(user.role_keys, capability):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this")
        return user

    return dependency


def get_via(request: Request) -> str:
    """ "agent" when the assistant's chat card made this call (it sends X-Via: agent), else "ui"."""
    return "agent" if request.headers.get("x-via", "").lower() == "agent" else "ui"
