from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import category_list, storage
from ..excel.generator import generate_category_excel
from ..models import CategoryList, CategoryListItem

router = APIRouter(prefix="/api", tags=["category-list"])


def _require_category(category: str) -> dict:
    meta = category_list.CATEGORIES.get(category)
    if meta is None:
        raise HTTPException(status_code=404, detail="알 수 없는 카테고리입니다.")
    return meta


def _matching_companies(category: str):
    return [c for c in storage.list_companies() if category_list.classify(c) == category]


@router.get("/category-list/{category}", response_model=CategoryList)
def list_category(
    category: str,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    meta = _require_category(category)
    companies = _matching_companies(category)

    if q:
        needle = q.strip()
        companies = [
            c for c in companies
            if needle in c.company_name
            or (c.representative and needle in c.representative)
            or needle in c.business_no
        ]

    companies.sort(key=lambda c: c.parsed_at, reverse=True)

    total = len(companies)
    start = max(page - 1, 0) * page_size
    page_items = companies[start:start + page_size]

    items = [
        CategoryListItem(
            no=i,
            business_no=c.business_no,
            company_name=c.company_name,
            representative=c.representative,
            address=c.address,
            industry_name=c.industry_name,
            credit_grade=c.credit_grade,
            revenue_latest=storage.latest_revenue(c),
            diagnosis_summary=storage.overall_diagnosis(c),
            parsed_at=c.parsed_at,
        )
        for i, c in enumerate(page_items, start=start + 1)
    ]

    return CategoryList(
        category=category, label=meta["label"],
        total=total, page=page, page_size=page_size, items=items,
    )


@router.get("/category-list/{category}/excel")
def category_list_excel(category: str):
    _require_category(category)
    path = generate_category_excel(category, _matching_companies(category))
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
