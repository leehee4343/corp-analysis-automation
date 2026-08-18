from __future__ import annotations

from fastapi import APIRouter

from .. import storage
from ..models import IssueEntry, IssueList

router = APIRouter(prefix="/api", tags=["validation"])


@router.get("/issues", response_model=IssueList)
def list_issues(page: int = 1, page_size: int = 10):
    entries = [
        IssueEntry(business_no=company.business_no, company_name=company.company_name, issue=issue)
        for company, issue in storage.list_issues()
    ]
    total = len(entries)
    start = max(page - 1, 0) * page_size
    return IssueList(total=total, page=page, page_size=page_size, items=entries[start:start + page_size])
