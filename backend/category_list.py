"""법인형태별 분류(개인사업자/일반법인/농업회사법인/영농조합법인).

PDF로 분석되어 DB(storage.py)에 저장된 회사만을 대상으로 한다 — 외부 참고자료
xlsx는 쓰지 않는다(이전 버전은 '추가메뉴...xlsx'를 읽었으나, "파싱되어 DB에 저장된
정보를 조회조건에 따라 목록으로 구성하는 기능"으로 재정의됨). PDF의 company_type
필드는 "개인사업자"/"일반법인"/"외감"만 구분해 농업회사법인·영농조합법인을 따로
가려낼 수 없어, 회사명 패턴으로 분류한다.
"""
from __future__ import annotations

from .models import Company

CATEGORIES: dict[str, dict] = {
    "individual": {"label": "개인사업자"},
    "general_corp": {"label": "일반법인"},
    "agri_corp": {"label": "농업회사법인"},
    "farm_partnership": {"label": "영농조합법인"},
}


def classify(company: Company) -> str:
    if company.company_type == "개인사업자":
        return "individual"
    if "농업회사법인" in company.company_name:
        return "agri_corp"
    if "영농조합법인" in company.company_name:
        return "farm_partnership"
    return "general_corp"
