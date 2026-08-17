from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .. import storage
from ..excel.generator import generate_mailing_list_excel
from ..models import Company, MailingListEntry

router = APIRouter(prefix="/api", tags=["mailing"])


def _sorted_companies() -> list[Company]:
    # 우편번호순 정렬 — 우체국 대량발송 접수 시 통상 요구되는 순서.
    return sorted(storage.list_companies(), key=lambda c: (c.postal_code or "99999", c.company_name))


@router.get("/mailing-list", response_model=list[MailingListEntry])
def mailing_list():
    return [
        MailingListEntry(
            no=i,
            business_no=c.business_no,
            postal_code=c.postal_code,
            address=c.address,
            company_name=c.company_name,
            representative=c.representative,
        )
        for i, c in enumerate(_sorted_companies(), start=1)
    ]


@router.get("/mailing-list/excel")
def mailing_list_excel():
    path = generate_mailing_list_excel(_sorted_companies())
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
