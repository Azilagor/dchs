import secrets
import time
from collections import defaultdict, deque
from typing import Iterable

from fastapi import HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
_login_attempts: dict[str, deque[float]] = defaultdict(deque)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_roles(request: Request, db: Session, roles: Iterable[str]) -> User:
    user = require_user(request, db)
    if user.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return user


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, token: str) -> None:
    session_token = get_csrf_token(request)
    if not token or not secrets.compare_digest(token, session_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недействительный CSRF токен")


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _attempt_keys(request: Request, email: str) -> list[str]:
    normalized_email = email.strip().lower()
    return [f"ip:{_client_ip(request)}", f"email:{normalized_email}"]


def _prune_attempts(queue: deque[float], now: float) -> None:
    while queue and now - queue[0] > LOGIN_WINDOW_SECONDS:
        queue.popleft()


def ensure_login_allowed(request: Request, email: str) -> None:
    now = time.time()
    for key in _attempt_keys(request, email):
        queue = _login_attempts[key]
        _prune_attempts(queue, now)
        if len(queue) >= LOGIN_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много попыток входа. Повторите позже.",
            )


def register_failed_login(request: Request, email: str) -> None:
    now = time.time()
    for key in _attempt_keys(request, email):
        queue = _login_attempts[key]
        _prune_attempts(queue, now)
        queue.append(now)


def clear_login_attempts(request: Request, email: str) -> None:
    for key in _attempt_keys(request, email):
        _login_attempts.pop(key, None)
