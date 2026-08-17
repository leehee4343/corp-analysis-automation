from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import storage
from ..excel.generator import generate_excel
from ..models import Company, CompanyList, CompanyListItem, CompanyUpdate, DashboardSummary

router = APIRouter(prefix="/api", tags=["companies"])


def _to_list_item(company: Company) -> CompanyListItem:
    return CompanyListItem(
        business_no=company.business_no,
        company_name=company.company_name,
        industry_name=company.industry_name,
        credit_grade=company.credit_grade,
        status=company.status,
        revenue_latest=storage.latest_revenue(company),
        parsed_at=company.parsed_at,
    )


@router.get("/companies", response_model=CompanyList)
def list_companies(q: str | None = None, industry: str | None = None, page: int = 1, page_size: int = 20):
    companies = storage.list_companies()

    if q:
        needle = q.strip()
        companies = [c for c in companies if needle in c.company_name or needle in c.business_no]
    if industry:
        companies = [c for c in companies if c.industry_name == industry]

    companies.sort(key=lambda c: c.parsed_at, reverse=True)

    total = len(companies)
    start = max(page - 1, 0) * page_size
    page_items = companies[start:start + page_size]

    return CompanyList(
        total=total, page=page, page_size=page_size,
        items=[_to_list_item(c) for c in page_items],
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
        recent=[_to_list_item(c) for c in recent],
    )
