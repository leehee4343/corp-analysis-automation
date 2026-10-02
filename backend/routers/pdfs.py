"""업로드된 원본 PDF 목록·삭제 (PDF 업로드 화면). PDF를 삭제하면 그 기업의 분석 정보와
모든 프로젝트 참여 명단도 함께 삭제된다."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import storage

router = APIRouter(prefix="/api", tags=["pdfs"])


class SourcePdf(BaseModel):
    business_no: str
    company_name: str
    filename: str
    size_bytes: int | None = None
    uploaded_at: str | None = None
    projects: list[str] = []
    missed: int | None = None       # 미추출 값 수
    target: int | None = None       # 추출 대상 값 수


class DeleteInput(BaseModel):
    business_nos: list[str]


@router.get("/pdfs", response_model=list[SourcePdf])
def list_pdfs(project_id: int | None = None):
    items = storage.list_source_pdfs(project_id)
    names = storage.project_names_by_company()
    for item in items:
        item["projects"] = names.get(item["business_no"], [])
    return items


@router.post("/pdfs/delete")
def delete_pdfs(data: DeleteInput):
    """선택 삭제(1건 이상). 반환: {deleted: 삭제 수, not_found: [사업자번호]}"""
    if not data.business_nos:
        raise HTTPException(status_code=422, detail="삭제할 PDF를 선택해 주세요.")
    deleted, not_found = 0, []
    for bn in dict.fromkeys(data.business_nos):
        if storage.delete_company_and_pdf(bn):
            deleted += 1
        else:
            not_found.append(bn)
    return {"deleted": deleted, "not_found": not_found}
