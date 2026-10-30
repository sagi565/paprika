"""Single-user login: one admin password from the environment, signed session cookie."""

import hmac
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, TimestampSigner

from .config import settings

COOKIE_NAME = "paprika_session"
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60

_signer = TimestampSigner(settings.secret_key, salt="paprika-session")
_failures: dict[str, list[float]] = defaultdict(list)


def _max_age() -> int:
    return settings.session_days * 24 * 3600


def check_login_rate(ip: str) -> None:
    now = time.time()
    recent = [t for t in _failures[ip] if now - t < FAILURE_WINDOW_SECONDS]
    _failures[ip] = recent
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "יותר מדי ניסיונות. נסו שוב בעוד רבע שעה.")


def verify_password(ip: str, password: str) -> bool:
    ok = hmac.compare_digest(password.encode(), settings.admin_password.encode())
    if not ok:
        _failures[ip].append(time.time())
    return ok


def issue_session(response: Response) -> None:
    response.set_cookie(
        COOKIE_NAME,
        _signer.sign(b"admin").decode(),
        max_age=_max_age(),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def require_auth(request: Request) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "נדרשת התחברות")
    try:
        _signer.unsign(token, max_age=_max_age())
    except BadSignature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "נדרשת התחברות") from None
