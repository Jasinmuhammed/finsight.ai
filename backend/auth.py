import hashlib
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import AuthSession, User

router = APIRouter(prefix="/auth", tags=["authentication"])
password_hash = PasswordHash.recommended()
COOKIE_NAME = "finsight_session"
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "168"))
COOKIE_SECURE = os.getenv(
    "SESSION_COOKIE_SECURE",
    "true" if os.getenv("ENVIRONMENT", "").lower() == "production" else "false",
).lower() == "true"
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.getenv(
        "AUTH_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RATE_WINDOW_SECONDS = 60
RATE_LIMIT = 12
attempts: dict[str, list[float]] = {}
attempts_lock = threading.Lock()


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    def normalized_email(self) -> str:
        email = self.email.strip().lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise HTTPException(status_code=422, detail="Enter a valid email address")
        return email


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime


def _rate_limit(request: Request) -> None:
    address = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with attempts_lock:
        recent = [
            stamp
            for stamp in attempts.get(address, [])
            if now - stamp < RATE_WINDOW_SECONDS
        ]
        if len(recent) >= RATE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again shortly.",
                headers={"Retry-After": str(RATE_WINDOW_SECONDS)},
            )
        recent.append(now)
        attempts[address] = recent


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def verify_request_origin(request: Request) -> None:
    _check_origin(request)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def get_current_user(
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    database: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    session_record = database.scalar(
        select(AuthSession).where(AuthSession.token_hash == _token_digest(token))
    )
    if not session_record:
        raise HTTPException(status_code=401, detail="Authentication required")
    expiry = session_record.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        database.delete(session_record)
        database.commit()
        raise HTTPException(status_code=401, detail="Session expired")
    user = database.get(User, session_record.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    credentials: Credentials,
    request: Request,
    response: Response,
    database: Session = Depends(get_db),
) -> User:
    _rate_limit(request)
    _check_origin(request)
    email = credentials.normalized_email()
    if database.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(email=email, password_hash=password_hash.hash(credentials.password))
    token = secrets.token_urlsafe(32)
    auth_session = AuthSession(
        user=user,
        token_hash=_token_digest(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
    )
    database.add_all([user, auth_session])
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from error
    database.refresh(user)
    _set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserResponse)
def login(
    credentials: Credentials,
    request: Request,
    response: Response,
    database: Session = Depends(get_db),
) -> User:
    _rate_limit(request)
    _check_origin(request)
    email = credentials.normalized_email()
    user = database.scalar(select(User).where(User.email == email))
    if not user or not password_hash.verify(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    database.add(
        AuthSession(
            user_id=user.id,
            token_hash=_token_digest(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
        )
    )
    database.commit()
    _set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    request: Request,
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    database: Session = Depends(get_db),
) -> Response:
    _check_origin(request)
    if token:
        session_record = database.scalar(
            select(AuthSession).where(AuthSession.token_hash == _token_digest(token))
        )
        if session_record:
            database.delete(session_record)
            database.commit()
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    response.status_code = 204
    return response


@router.get("/me", response_model=UserResponse)
def current_user(user: User = Depends(get_current_user)) -> User:
    return user
