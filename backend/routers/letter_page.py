"""공문(HTML) 공유 화면 /l/{code} — 기업 담당자에게 보내는 짧은 주소. 로그인 없이 열린다(auth_middleware 공개 경로).

링크는 영업 관리에서 만든다(POST /api/sales/{project_id}/{business_no}/letter-link). 문서번호·시행일자는 링크를
만든 날로 고정하고, 재무 수치는 열 때마다 최신 값으로 그린다. 90일이 지나면 안내 화면만 보여 준다.
"""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .. import storage
from ..letter import generator as letter
from ..letter import html_page

router = APIRouter(tags=["letter"])

_CODE = re.compile(r"[A-Za-z0-9]{6,16}")
_HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff"}


def _fmt(d: date) -> str:
    return f"{d.year}. {d.month}. {d.day}."


def _message(status: int, title: str, message: str, label: str) -> HTMLResponse:
    return HTMLResponse(html_page.render_message_html(title, message, label), status_code=status, headers=_HEADERS)


@router.get("/l/{code}", response_class=HTMLResponse, include_in_schema=False)
def letter_page(code: str):
    link = storage.get_letter_link(code) if _CODE.fullmatch(code) else None
    company = storage.load_company(link["business_no"]) if link else None
    if link is None or company is None:
        return _message(404, "공문을 찾을 수 없습니다", "주소가 정확한지 확인하시거나, 공문을 보낸 담당자에게 문의해 주세요.", "404")
    expires = date.fromisoformat(link["expires_at"])
    if expires < date.today():
        return _message(410, "열람 기간이 지났습니다",
                        f"이 공문은 {_fmt(expires)}까지 열람할 수 있었습니다. 다시 보시려면 공문을 보낸 담당자에게 문의해 주세요.", "만료")
    d = letter.build_letter_data(company, doc_no=link["doc_no"], issued=date.fromisoformat(link["issued_at"]))
    return HTMLResponse(html_page.render_letter_html(d, expires_text=_fmt(expires)), headers=_HEADERS)
