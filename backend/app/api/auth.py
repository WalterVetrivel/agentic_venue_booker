from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import authenticate, create_token, get_optional_user
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.permissions import capabilities_for
from app.schemas import LoginIn, MeOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        initials=user.initials,
        designation=user.designation,
        roles=user.role_keys,
        capabilities=sorted(capabilities_for(user.role_keys)),
    )


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    user = authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    settings = get_settings()
    response.set_cookie(
        settings.cookie_name,
        create_token(user.id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_ttl_hours * 3600,
    )
    return user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(get_settings().cookie_name)


@router.get("/me", response_model=MeOut)
def me(user: User | None = Depends(get_optional_user)) -> MeOut:
    if user is None:
        return MeOut(user=None, capabilities=sorted(capabilities_for(None)))
    out = user_out(user)
    return MeOut(user=out, capabilities=out.capabilities)
