"""Supabase Storage 클라이언트 — 원본 PDF 파일 보관용.

personal-projects 프로젝트는 여러 앱이 함께 쓰므로(docs/SUPABASE_STRUCTURE.md), 프로젝트
전체 권한 키(secret/service_role)를 쓰지 않는다. 대신 이 앱 전용 서비스 계정
(STORAGE_SERVICE_EMAIL)으로 로그인해 받은 토큰으로 접근하고, Storage 접근 정책이 이 계정을
자기 버킷(STORAGE_BUCKET, 기본 corp-analysis)에만 묶어 둔다.

설정값은 모두 호출 시점에 환경변수에서 읽는다(테스트가 지워서 비활성화할 수 있도록).
"""
from __future__ import annotations

import os
import threading
import time
from urllib.parse import quote

import httpx

_REQUIRED = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "STORAGE_SERVICE_EMAIL", "STORAGE_SERVICE_PASSWORD")
_lock = threading.Lock()
_token: str | None = None
_token_expires_at = 0.0


def enabled() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED)


def _base() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/")


def _bucket() -> str:
    return os.environ.get("STORAGE_BUCKET", "corp-analysis")


def _access_token() -> str:
    """서비스 계정 로그인 토큰. 만료 1분 전까지 재사용한다."""
    global _token, _token_expires_at
    with _lock:
        if _token and time.time() < _token_expires_at - 60:
            return _token
        res = httpx.post(
            f"{_base()}/auth/v1/token?grant_type=password",
            headers={"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"]},
            json={"email": os.environ["STORAGE_SERVICE_EMAIL"], "password": os.environ["STORAGE_SERVICE_PASSWORD"]},
            timeout=20,
        )
        res.raise_for_status()
        body = res.json()
        _token = body["access_token"]
        _token_expires_at = time.time() + float(body.get("expires_in", 3600))
        return _token


def _headers() -> dict[str, str]:
    return {"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"], "Authorization": f"Bearer {_access_token()}"}


def _object_url(path: str, *, authenticated: bool = False) -> str:
    prefix = "object/authenticated" if authenticated else "object"
    return f"{_base()}/storage/v1/{prefix}/{_bucket()}/{quote(path)}"


def upload(path: str, content: bytes, content_type: str = "application/pdf") -> None:
    """같은 경로가 있으면 덮어쓴다(같은 사업자번호 재업로드 = 최신본 교체)."""
    res = httpx.post(
        _object_url(path),
        headers={**_headers(), "Content-Type": content_type, "x-upsert": "true"},
        content=content,
        timeout=60,
    )
    res.raise_for_status()


def download(path: str) -> bytes | None:
    res = httpx.get(_object_url(path, authenticated=True), headers=_headers(), timeout=60)
    if res.status_code in (400, 404):
        return None
    res.raise_for_status()
    return res.content
