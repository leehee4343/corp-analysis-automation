"""전체 앱(화면 + 모든 API)에 거는 로그인 — 로그인 화면 + 서명된 세션 쿠키.

APP_LOGIN_PASSWORD 환경변수가 설정된 경우에만 로그인을 강제한다(아이디는 APP_LOGIN_USER, 기본 admin).
변수가 없으면(테스트 등) 기존처럼 인증 없이 동작한다.

예전에는 HTTP Basic 인증(브라우저 기본 팝업)을 썼지만, Basic 인증은 브라우저가 창을 닫을 때까지
아이디·비밀번호를 기억해 '로그아웃'을 만들 수 없어 쿠키 세션으로 바꿨다(2026-10-02, 사용자 요청).
- 로그인: POST /api/login → HttpOnly 쿠키 발급(유효 7일)
- 로그아웃: POST /api/logout → 쿠키 삭제 → 화면은 /login으로 이동
- 쿠키는 '아이디|만료시각'을 HMAC-SHA256으로 서명한다. 서명 키는 APP_SESSION_SECRET(없으면 비밀번호에서
  유도)이라 비밀번호를 바꾸면 기존 로그인은 모두 풀린다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

COOKIE_NAME = "corp_session"
SESSION_SECONDS = 7 * 24 * 3600
# 로그인 없이 열리는 경로: 로그인 화면·로그인/세션 API·화면 이미지
_PUBLIC_PATHS = {"/login", "/api/login", "/api/logout", "/api/session"}
_PUBLIC_PREFIXES = ("/assets/",)


def login_password() -> str | None:
    return os.environ.get("APP_LOGIN_PASSWORD") or None


def login_user() -> str:
    return os.environ.get("APP_LOGIN_USER", "admin")


def _secret() -> bytes:
    explicit = os.environ.get("APP_SESSION_SECRET")
    if explicit:
        return explicit.encode()
    return hashlib.sha256(f"corp-analysis-session|{login_user()}|{login_password()}".encode()).digest()


def check_credentials(username: str, password: str) -> bool:
    expected = login_password()
    if not expected:
        return True
    return secrets.compare_digest(username.encode(), login_user().encode()) and \
        secrets.compare_digest(password.encode(), expected.encode())


def make_session_token(username: str, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + SESSION_SECONDS)
    payload = base64.urlsafe_b64encode(f"{username}|{expires}".encode()).decode()
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def session_user(token: str | None, now: float | None = None) -> str | None:
    """유효한 세션이면 아이디, 아니면 None."""
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        username, expires = base64.urlsafe_b64decode(payload.encode()).decode().rsplit("|", 1)
        if int(expires) < (time.time() if now is None else now):
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    return username if username == login_user() else None


def is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


class LoginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not login_password() or path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)
        if session_user(request.cookies.get(COOKIE_NAME)):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
        return RedirectResponse("/login", status_code=303)
