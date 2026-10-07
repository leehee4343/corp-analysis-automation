"""영업 관리: 프로젝트 참여 기업별 우편(DM) 발송 여부, 승인/거절 결과, 메모, 등급별 분류(S·A·B·C), 공문(PPTX) 다운로드.

목록은 프로젝트 참여 명단 전체를 한 번에 돌려주고(수백 건 규모) 검색·필터·페이징은 화면에서 한다(PDF 목록과 같은 방식).
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import storage
from ..letter import generator as letter

router = APIRouter(prefix="/api", tags=["sales"])


class SalesRow(BaseModel):
    project_id: int
    project_name: str
    business_no: str
    company_name: str
    representative: str | None = None
    postal_code: str | None = None
    address: str | None = None
    industry_name: str | None = None
    credit_grade: str | None = None
    email: str | None = None  # PDF 기본정보에서 추출한 이메일(없으면 null)
    dm_sent: bool = False
    dm_sent_at: str | None = None
    decision: Literal["승인", "거절"] | None = None
    decided_at: str | None = None
    updated_at: str | None = None
    memo: str | None = None
    memo_updated_at: str | None = None
    tier: Literal["S", "A", "B", "C"] | None = None


class SalesUpdate(BaseModel):
    """보낸 필드만 바꾼다. decision에 null을 보내면 '미정'으로, memo에 null·빈 값을 보내면 메모 삭제,
    tier(등급별 분류)에 null을 보내면 '미지정'으로."""
    dm_sent: bool | None = None
    decision: Literal["승인", "거절"] | None = None
    memo: str | None = Field(default=None, max_length=2000)
    tier: Literal["S", "A", "B", "C"] | None = None


class SalesTarget(BaseModel):
    project_id: int
    business_no: str


class SalesBulkUpdate(SalesUpdate):
    items: list[SalesTarget] = Field(min_length=1, max_length=5000)


def _changes(data: SalesUpdate) -> dict:
    changes = {k: getattr(data, k) for k in data.model_fields_set if k in ("dm_sent", "decision", "memo", "tier")}
    if changes.get("dm_sent", False) is None:
        raise HTTPException(status_code=422, detail="dm_sent는 true 또는 false여야 합니다.")
    if not changes:
        raise HTTPException(status_code=422, detail="바꿀 항목(dm_sent, decision, memo, tier)이 없습니다.")
    return changes


@router.get("/sales", response_model=list[SalesRow])
def list_sales(project_id: int | None = None):
    return storage.list_sales(project_id)


@router.patch("/sales/{project_id}/{business_no}")
def update_sales(project_id: int, business_no: str, data: SalesUpdate):
    if not storage.is_project_member(project_id, business_no):
        raise HTTPException(status_code=404, detail="해당 프로젝트의 참여 기업이 아닙니다.")
    return storage.update_sales(project_id, business_no, _changes(data))


@router.post("/sales/bulk")
def bulk_update_sales(data: SalesBulkUpdate):
    changes = _changes(data)
    targets = {(t.project_id, t.business_no) for t in data.items}
    missing = [bn for pid, bn in targets if not storage.is_project_member(pid, bn)]
    if missing:
        raise HTTPException(status_code=404, detail=f"참여 기업이 아닌 항목이 있습니다: {', '.join(missing[:5])}")
    for pid, bn in targets:
        storage.update_sales(pid, bn, changes)
    return {"updated": len(targets)}


class LetterRequest(BaseModel):
    items: list[SalesTarget] = Field(min_length=1, max_length=500)


PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]+')  # 파일명에 쓸 수 없는 문자


def _attachment(filename: str) -> dict:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}


@router.post("/sales/letters")
def download_letters(data: LetterRequest):
    """선택한 기업의 공문(PPTX). 1개면 '공문_기업명.pptx', 여러 개면 기업별 파일을 묶은 ZIP.
    문서번호의 일련번호는 요청 순서(화면 목록 순서)를 따른다."""
    targets = list(dict.fromkeys((t.project_id, t.business_no) for t in data.items))  # 순서 유지 중복 제거
    tiers: dict[tuple[int, str], str | None] = {}
    for pid in {pid for pid, _ in targets}:
        tiers.update({(r["project_id"], r["business_no"]): r["tier"] for r in storage.list_sales(pid)})
    missing = [bn for pid, bn in targets if (pid, bn) not in tiers]
    if missing:
        raise HTTPException(status_code=404, detail=f"참여 기업이 아닌 항목이 있습니다: {', '.join(missing[:5])}")
    issued = date.today()
    files: list[tuple[str, bytes]] = []
    used: set[str] = set()
    for seq, key in enumerate(targets, 1):
        company = storage.load_company(key[1])
        if company is None:
            raise HTTPException(status_code=404, detail=f"기업 정보를 찾을 수 없습니다: {key[1]}")
        name = f"공문_{_UNSAFE_FILENAME.sub('', company.company_name) or company.business_no}"
        if name in used:  # 같은 기업명이 여러 프로젝트에서 선택된 경우
            name = f"{name}_{company.business_no}"
        used.add(name)
        content = letter.render_letter(company, doc_no=letter.doc_number(issued, tiers[key], seq), issued=issued)
        files.append((f"{name}.pptx", content))
    if len(files) == 1:
        return Response(files[0][1], media_type=PPTX, headers=_attachment(files[0][0]))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files:
            zf.writestr(filename, content)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers=_attachment(f"공문_{len(files)}개기업_{issued:%Y%m%d}.zip"))
