"""'추가메뉴(개인사업자 일반법인 농업회사법인 영농조합법인).xlsx' 로더.

'검색조회 목록.xlsx'(master_list.py)와는 다른 참고자료라 별도 모듈로 분리했다.
법인형태별 4개 시트가 각각 하나의 메뉴다. 이 시트는 이미 조사된 상세 데이터(대표자
연령/기업등급/매출액/영업이익 등 20개 컬럼)가 채워져 있어, PDF 분석 여부와 무관하게
그 자체로 표시 가능하다 — 우리 쪽 PDF 파싱 데이터가 있으면(매칭 성공 시) "분석완료"
배지로 더 상세한 우리 상세 페이지도 함께 연결해준다.

컬럼 위치(A~T, 0-indexed)는 4개 시트 전부 동일하고 헤더 문구만 미세하게 다르다
(예: 개인사업자 시트만 "사업자 번호", 나머지는 "법인등록번호").
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

CATEGORY_LIST_PATH = (
    Path(__file__).resolve().parents[1] / "참고자료"
    / "추가메뉴(개인사업자 일반법인 농업회사법인 영농조합법인).xlsx"
)

# category key -> (시트명, 화면 표시명, reg_no 컬럼이 사업자번호 형식인지 법인등록번호
# 형식인지). 사업자번호는 우리 시스템의 business_no와 동일 형식이라 그대로 매칭 가능하지만,
# 법인등록번호는 별개 식별자라 회사명 정규화로만 매칭할 수 있다(master_list.py 참고).
CATEGORIES: dict[str, dict] = {
    "individual": {"sheet": "개인사업자(106)", "label": "개인사업자", "reg_no_is_business_no": True},
    "general_corp": {"sheet": "일반법인(261)", "label": "일반법인", "reg_no_is_business_no": False},
    "agri_corp": {"sheet": "농업회사법인(219)", "label": "농업회사법인", "reg_no_is_business_no": False},
    "farm_partnership": {"sheet": "영농조합법인(108)", "label": "영농조합법인", "reg_no_is_business_no": False},
}

_FIELD_NAMES = (
    "company_name", "representative", "address", "representative_age", "succession",
    "biz_type", "industry", "reg_no", "founded_date", "detail_industry",
    "credit_grade", "main_bank", "revenue", "operating_profit", "net_income",
    "insurance_premium", "dividend", "corp_management", "tax_reduction", "etc",
)

_cache: dict[str, dict] = {}


def load_category_rows(category: str) -> list[dict]:
    """지정한 카테고리 시트를 파싱해 반환. 파일이 안 바뀌었으면 캐시를 재사용한다."""
    meta = CATEGORIES[category]
    if not CATEGORY_LIST_PATH.exists():
        return []
    key = (str(CATEGORY_LIST_PATH), CATEGORY_LIST_PATH.stat().st_mtime)
    cached = _cache.get(category)
    if cached and cached["key"] == key:
        return cached["rows"]  # type: ignore[return-value]

    wb = openpyxl.load_workbook(CATEGORY_LIST_PATH, data_only=True)
    ws = wb[meta["sheet"]]
    rows: list[dict] = []
    no = 0
    for values in ws.iter_rows(min_row=2, values_only=True):
        if not values or not values[0]:
            continue
        no += 1
        row = dict(zip(_FIELD_NAMES, values))
        row["no"] = no
        rows.append(row)

    _cache[category] = {"key": key, "rows": rows}
    return rows
