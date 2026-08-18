from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import category_list, master_list, storage
from ..excel.generator import generate_category_excel
from ..models import CategoryList, CategoryListItem, Company

router = APIRouter(prefix="/api", tags=["category-list"])


def _name_index() -> dict[str, Company]:
    return {master_list.normalize_name(c.company_name): c for c in storage.list_companies()}


def _business_no_index() -> dict[str, Company]:
    return {c.business_no: c for c in storage.list_companies()}


def _require_category(category: str) -> dict:
    meta = category_list.CATEGORIES.get(category)
    if meta is None:
        raise HTTPException(status_code=404, detail="알 수 없는 카테고리입니다.")
    return meta


@router.get("/category-list/{category}", response_model=CategoryList)
def list_category(
    category: str,
    q: str | None = None,
    analyzed_only: bool | None = None,
    page: int = 1,
    page_size: int = 20,
):
    meta = _require_category(category)
    name_idx = _name_index()
    biz_no_idx = _business_no_index() if meta["reg_no_is_business_no"] else {}

    items = []
    for row in category_list.load_category_rows(category):
        company = None
        if meta["reg_no_is_business_no"] and row.get("reg_no"):
            company = biz_no_idx.get(str(row["reg_no"]))
        if company is None:
            company = name_idx.get(master_list.normalize_name(row["company_name"]))

        items.append(CategoryListItem(
            no=row["no"],
            company_name=row["company_name"],
            representative=row.get("representative"),
            address=row.get("address"),
            industry=row.get("industry"),
            reg_no=row.get("reg_no"),
            credit_grade_ref=str(row["credit_grade"]) if row.get("credit_grade") is not None else None,
            revenue_ref=str(row["revenue"]) if row.get("revenue") is not None else None,
            analyzed=company is not None,
            business_no=company.business_no if company else None,
            credit_grade=company.credit_grade if company else None,
            revenue_latest=storage.latest_revenue(company) if company else None,
        ))

    if q:
        needle = q.strip()
        items = [
            i for i in items
            if needle in i.company_name
            or (i.representative and needle in i.representative)
            or (i.reg_no and needle in str(i.reg_no))
        ]
    if analyzed_only is True:
        items = [i for i in items if i.analyzed]
    elif analyzed_only is False:
        items = [i for i in items if not i.analyzed]

    total = len(items)
    start = max(page - 1, 0) * page_size
    page_items = items[start:start + page_size]

    return CategoryList(
        category=category, label=meta["label"],
        total=total, page=page, page_size=page_size, items=page_items,
    )


@router.get("/category-list/{category}/excel")
def category_list_excel(category: str):
    _require_category(category)
    path = generate_category_excel(category)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
