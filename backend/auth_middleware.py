"""전체 앱(프론트엔드 HTML + 모든 API)에 거는 간단한 HTTP Basic 인증.

APP_LOGIN_PASSWORD 환경변수가 설정된 경우에만 인증을 강제한다 — 로컬 개발(run.bat/
프로그램 시작.bat)에서는 아무도 이 변수를 설정하지 않으므로 기존처럼 인증 없이
동작하고, 배포 환경에서만 환경변수를 지정해 활성화한다.
"""
from __future__ import annotations

import base64
import binascii
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REALM = 'Basic realm="Corp Analysis"'  # HTTP 헤더는 latin-1만 허용되어 한글 realm은 쓸 수 없음


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        password = os.environ.get("APP_LOGIN_PASSWORD")
        if not password:
            return await call_next(request)

        username = os.environ.get("APP_LOGIN_USER", "admin")
        auth_header = request.headers.get("authorization", "")

        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                given_user, _, given_pass = decoded.partition(":")
            except (binascii.Error, UnicodeDecodeError):
                given_user, given_pass = "", ""

            if secrets.compare_digest(given_user, username) and secrets.compare_digest(given_pass, password):
                return await call_next(request)

        return Response(status_code=401, headers={"WWW-Authenticate": _REALM})
