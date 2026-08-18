from __future__ import annotations

from fastapi import APIRouter

from .. import master_list, storage
from ..models import MasterList, MasterListItem

router = APIRouter(prefix="/api", tags=["master-list"])


def _analyzed_index() -> dict[str, "storage.Company"]:
    return {master_list.normalize_name(c.company_name): c for c in storage.list_companies()}


@router.get("/master-list", response_model=MasterList)
def list_master(
    q: str | None = None,
    industry: str | None = None,
    grade_band: str | None = None,
    revenue_min: float | None = None,
    revenue_max: float | None = None,
    analyzed_only: bool | None = None,
    page: int = 1,
    page_size: int = 20,
):
    idx = _analyzed_index()
    items = []
    for row in master_list.load_master_rows():
        company = idx.get(master_list.normalize_name(row["company_name"]))
        items.append(MasterListItem(
            no=row["no"],
            company_name=row["company_name"],
            representative=row["representative"],
            biz_type=row["biz_type"],
            industry=row["industry"],
            corp_reg_no=row["corp_reg_no"],
            analyzed=company is not None,
            business_no=company.business_no if company else None,
            credit_grade=company.credit_grade if company else None,
            revenue_latest=storage.latest_revenue(company) if company else None,
            diagnosis_summary=storage.overall_diagnosis(company) if company else None,
        ))

    if q:
        needle = q.strip()
        items = [
            i for i in items
            if needle in i.company_name
            or (i.representative and needle in i.representative)
            or (i.corp_reg_no and needle in i.corp_reg_no)
        ]
    if industry:
        items = [i for i in items if i.industry == industry]
    if grade_band:
        items = [i for i in items if i.analyzed and storage.grade_band(i.credit_grade) == grade_band]
    if revenue_min is not None:
        items = [i for i in items if i.analyzed and (i.revenue_latest or 0) >= revenue_min]
    if revenue_max is not None:
        items = [i for i in items if i.analyzed and (i.revenue_latest or 0) < revenue_max]
    if analyzed_only is True:
        items = [i for i in items if i.analyzed]
    elif analyzed_only is False:
        items = [i for i in items if not i.analyzed]

    total = len(items)
    start = max(page - 1, 0) * page_size
    page_items = items[start:start + page_size]

    return MasterList(total=total, page=page, page_size=page_size, items=page_items)


@router.get("/master-list/industries", response_model=list[str])
def master_list_industries():
    industries = {row["industry"] for row in master_list.load_master_rows() if row["industry"]}
    return sorted(industries)
