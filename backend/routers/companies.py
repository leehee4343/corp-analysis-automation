from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from ._filters import MetricRanges
from .. import storage
from ..excel.generator import generate_excel
from ..models import Company, CompanyList, CompanyUpdate, DashboardSummary

router = APIRouter(prefix="/api", tags=["companies"])


@router.get("/companies", response_model=CompanyList)
def list_companies(
    q: str | None = None,
    industry: str | None = None,
    grade_band: str | None = None,
    revenue_min: float | None = None,
    revenue_max: float | None = None,
    ranges: MetricRanges = Depends(),
    project_id: int | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    page: int = 1,
    page_size: int = 20,
):
    companies = storage.filter_companies(
        storage.list_companies(project_id),
        q=q, industry=industry, grade_band_filter=grade_band,
        revenue_min=revenue_min, revenue_max=revenue_max, ranges=ranges.as_dict(),
    )
    companies = storage.sort_companies(companies, sort, order)

    total = len(companies)
    start = max(page - 1, 0) * page_size
    page_items = companies[start:start + page_size]

    return CompanyList(
        total=total, page=page, page_size=page_size,
        items=[storage.to_list_item(c) for c in page_items],
    )


@router.get("/companies/{business_no}", response_model=Company)
def get_company(business_no: str):
    company = storage.load_company(business_no)
    if company is None:
        raise HTTPException(status_code=404, detail="등록되지 않은 사업자번호입니다.")
    return company


@router.get("/companies/{business_no}/excel")
def download_excel(business_no: str):
    company = storage.load_company(business_no)
    if company is None:
        raise HTTPException(status_code=404, detail="등록되지 않은 사업자번호입니다.")
    path = generate_excel(company)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/companies/{business_no}/source-pdf")
def download_source_pdf(business_no: str, download: bool = False):
    """원본 PDF. 기본은 브라우저에서 바로 열기(inline), download=true면 파일로 내려받기(attachment)."""
    company = storage.load_company(business_no)
    if company is None:
        raise HTTPException(status_code=404, detail="등록되지 않은 사업자번호입니다.")
    source = storage.load_source_pdf(company)
    if source is None:
        raise HTTPException(status_code=404, detail="원본 PDF 파일을 찾을 수 없습니다.")
    filename, content = source
    # 한글 파일명은 RFC 5987 형식으로 전달
    disposition = f"{'attachment' if download else 'inline'}; filename*=UTF-8''{quote(filename)}"
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": disposition})


@router.patch("/companies/{business_no}", response_model=Company)
def patch_company(business_no: str, update: CompanyUpdate):
    company = storage.update_company(business_no, update)
    if company is None:
        raise HTTPException(status_code=404, detail="등록되지 않은 사업자번호입니다.")
    return company


@router.delete("/companies/{business_no}", status_code=204)
def delete_company(business_no: str):
    """기업 상세의 삭제: PDF 목록의 삭제와 같이 원본 PDF(Storage·source_pdfs)까지 지운다 — 예전에는 기업 정보만
    지워 Storage에 주인 없는 PDF가 남았다. 참여 명단·영업 기록은 cascade로 함께 삭제."""
    if not storage.delete_company_and_pdf(business_no):
        raise HTTPException(status_code=404, detail="등록되지 않은 사업자번호입니다.")


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(project_id: int | None = None):
    companies = storage.list_companies(project_id)
    total = len(companies)
    complete = sum(1 for c in companies if c.status == "complete")

    by_industry: dict[str, int] = {}
    by_grade_band: dict[str, int] = {}
    for c in companies:
        industry = c.industry_name or "미분류"
        by_industry[industry] = by_industry.get(industry, 0) + 1
        band = storage.grade_band(c.credit_grade)
        by_grade_band[band] = by_grade_band.get(band, 0) + 1

    recent = sorted(companies, key=lambda c: c.parsed_at, reverse=True)[:10]

    return DashboardSummary(
        total_companies=total,
        parsing_success_rate=round(100 * complete / total, 1) if total else 0.0,
        pending_issues=sum(len(c.issues) for c in companies),
        by_industry=by_industry,
        by_credit_grade_band=by_grade_band,
        by_credit_grade=storage.credit_grade_counts(companies),
        by_revenue_band=storage.revenue_band_counts(companies),
        recent=[storage.to_list_item(c) for c in recent],
    )
