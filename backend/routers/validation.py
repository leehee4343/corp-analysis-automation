from __future__ import annotations

from fastapi import APIRouter

from .. import storage
from ..models import IssueEntry

router = APIRouter(prefix="/api", tags=["validation"])


@router.get("/issues", response_model=list[IssueEntry])
def list_issues():
    return [
        IssueEntry(business_no=company.business_no, company_name=company.company_name, issue=issue)
        for company, issue in storage.list_issues()
    ]
