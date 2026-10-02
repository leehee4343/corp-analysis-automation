"""영업 관리: 프로젝트 참여 기업별 우편(DM) 발송 여부와 승인/거절 결과.

목록은 프로젝트 참여 명단 전체를 한 번에 돌려주고(수백 건 규모) 검색·필터·페이징은 화면에서 한다(PDF 목록과 같은 방식).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage

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
    dm_sent: bool = False
    dm_sent_at: str | None = None
    decision: Literal["승인", "거절"] | None = None
    decided_at: str | None = None
    updated_at: str | None = None


class SalesUpdate(BaseModel):
    """보낸 필드만 바꾼다. decision에 null을 보내면 '미정'으로 되돌린다."""
    dm_sent: bool | None = None
    decision: Literal["승인", "거절"] | None = None


class SalesTarget(BaseModel):
    project_id: int
    business_no: str


class SalesBulkUpdate(SalesUpdate):
    items: list[SalesTarget] = Field(min_length=1, max_length=5000)


def _changes(data: SalesUpdate) -> dict:
    changes = {k: getattr(data, k) for k in data.model_fields_set if k in ("dm_sent", "decision")}
    if changes.get("dm_sent", False) is None:
        raise HTTPException(status_code=422, detail="dm_sent는 true 또는 false여야 합니다.")
    if not changes:
        raise HTTPException(status_code=422, detail="바꿀 항목(dm_sent, decision)이 없습니다.")
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
