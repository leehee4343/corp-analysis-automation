"""배포 환경(예: Render 무료 플랜의 휘발성 파일시스템)에 참고자료 xlsx를 올리기 위한
운영용 엔드포인트. 앱 전체에 로그인이 없는 상태라, 이 엔드포인트만 별도 토큰
(ADMIN_UPLOAD_TOKEN 환경변수)으로 보호한다 — 토큰 미설정 시 항상 거부."""
from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException, UploadFile

from .. import master_list

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _check_token(x_admin_token: str | None) -> None:
    expected = os.environ.get("ADMIN_UPLOAD_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="인증 실패")


def _target_path(key: str):
    # master_list.MASTER_LIST_PATH를 매 요청마다 새로 읽어야 테스트의 monkeypatch가
    # 반영된다 — 모듈 임포트 시점에 값을 복사해두면 갱신되지 않는다.
    # category_list는 더 이상 xlsx를 쓰지 않아(DB 기반으로 전환) 업로드 대상에서 제외.
    if key == "master_list":
        return master_list.MASTER_LIST_PATH
    return None


@router.post("/reference-upload/{key}")
async def upload_reference_file(key: str, file: UploadFile, x_admin_token: str | None = Header(default=None)):
    _check_token(x_admin_token)
    path = _target_path(key)
    if path is None:
        raise HTTPException(status_code=404, detail="알 수 없는 참고자료 종류입니다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())
    return {"saved": path.name, "size": path.stat().st_size}
