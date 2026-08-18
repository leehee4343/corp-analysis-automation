from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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
    page: int = 1,
    page_size: int = 20,
):
    companies = storage.filter_companies(
        storage.list_companies(),
        q=q, industry=industry, grade_band_filter=grade_band,
        revenue_min=revenue_min, revenue_max=revenue_max,
    )
    companies.sort(key=lambda c: c.parsed_at, reverse=True)

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
def download_source_pdf(business_no: str):
    company = storage.load_company(business_no)
    if company is None:
        raise HTTPException(status_code=404, detail="등록되지 않은 사업자번호입니다.")
    if not company.source_pdf:
        raise HTTPException(status_code=404, detail="원본 PDF 경로가 저장되어 있지 않습니다.")
    path = Path(company.source_pdf)
    if not path.exists():
        raise HTTPException(status_code=404, detail="원본 PDF 파일을 찾을 수 없습니다.")
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@router.patch("/companies/{business_no}", response_model=Company)
def patch_company(business_no: str, update: CompanyUpdate):
    company = storage.update_company(business_no, update)
    if company is None:
        raise HTTPException(status_code=404, detail="등록되지 않은 사업자번호입니다.")
    return company


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary():
    companies = storage.list_companies()
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
        recent=[storage.to_list_item(c) for c in recent],
    )
