"""'검색조회 목록.xlsx' (영업 대상 마스터 목록) 로더 — 기업 목록 화면의 데이터 소스.

`참고자료/` 폴더는 민감한 사업자 정보라 git 추적 대상이 아니지만(.gitignore), 이 파일은
샘플 참고용이 아니라 실행 시점에 직접 읽어 화면에 표시하는 실데이터다. PDF 분석 완료
기업(`storage.list_companies()`)과는 이름으로 매칭해 "분석완료" 여부를 표시한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl

MASTER_LIST_PATH = Path(__file__).resolve().parents[1] / "참고자료" / "검색조회 목록.xlsx"
SHEET_NAME = "전체DB"

# 회사명 비교용 노이즈 단어 — 출처마다 "농업회사법인"/"(주)"/"㈜" 위치·표기가 달라
# 공백만 제거해서는 매칭 안 되는 사례가 많았다(실측: 매칭률 64%→72%, 오매칭 0건).
_NOISE_WORDS = ["농업회사법인", "영농조합법인", "유한회사", "주식회사", "㈜", "(주)", "(유)", "(유한)", "(외감)"]

_cache: dict[str, object] = {"key": None, "rows": []}


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = re.sub(r"\s+", "", name)
    for word in _NOISE_WORDS:
        s = s.replace(word, "")
    return s


def load_master_rows() -> list[dict]:
    """'전체DB' 시트를 파싱해 반환. 파일이 안 바뀌었으면 캐시를 재사용한다."""
    if not MASTER_LIST_PATH.exists():
        return []
    key = (str(MASTER_LIST_PATH), MASTER_LIST_PATH.stat().st_mtime)
    if _cache["key"] == key:
        return _cache["rows"]  # type: ignore[return-value]

    wb = openpyxl.load_workbook(MASTER_LIST_PATH, data_only=True)
    ws = wb[SHEET_NAME]
    rows: list[dict] = []
    no = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        company_name = row[0]
        if not company_name:
            continue
        no += 1
        rows.append({
            "no": no,
            "company_name": company_name,
            "representative": row[1],
            "biz_type": row[2],
            "industry": row[3],
            "corp_reg_no": row[4],
        })

    _cache["key"] = key
    _cache["rows"] = rows
    return rows
