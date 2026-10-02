from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ._filters import MetricRanges
from .. import category_list, storage
from ..models import CategoryList

router = APIRouter(prefix="/api", tags=["category-list"])


def _require_category(category: str) -> dict:
    meta = category_list.CATEGORIES.get(category)
    if meta is None:
        raise HTTPException(status_code=404, detail="알 수 없는 카테고리입니다.")
    return meta


@router.get("/category-list/{category}", response_model=CategoryList)
def list_category(
    category: str,
    q: str | None = None,
    industry: str | None = None,
    grade_band: str | None = None,
    revenue_min: float | None = None,
    revenue_max: float | None = None,
    ranges: MetricRanges = Depends(),
    sort: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    page: int = 1,
    page_size: int = 20,
):
    meta = _require_category(category)

    companies = [c for c in storage.list_companies() if category_list.classify(c) == category]
    companies = storage.filter_companies(
        companies,
        q=q, industry=industry, grade_band_filter=grade_band,
        revenue_min=revenue_min, revenue_max=revenue_max, ranges=ranges.as_dict(),
    )
    companies = storage.sort_companies(companies, sort, order)

    total = len(companies)
    start = max(page - 1, 0) * page_size
    page_items = companies[start:start + page_size]

    return CategoryList(
        category=category, label=meta["label"],
        total=total, page=page, page_size=page_size,
        items=[storage.to_list_item(c) for c in page_items],
    )
