"""KOREA RATING & DATA 기업종합보고서 PDF의 라벨 앵커 · 정규식 정의.

`1 옥산농원.pdf`(31페이지) 구조 분석 결과를 기준으로 함 (PLAN.md Phase 1 참고).
같은 발급처의 보고서는 페이지 구성·라벨 문구가 동일하다는 전제.
"""
import re

BUSINESS_NO_RE = re.compile(r"\d{3}-\d{2}-\d{5}")

# 3개년 요약 표 (백만원 단위) — 각 라벨 뒤에 연도순(2023,2024,2025) 숫자 3개가 이어짐
BALANCE_SUMMARY_HEADER = "요약재무상태표"
BALANCE_SUMMARY_FIELDS = ["자산총계", "부채총계", "자본금", "자본총계"]

INCOME_SUMMARY_HEADER = "요약손익계산서"
INCOME_SUMMARY_FIELDS = ["매출액", "영업이익", "당기순이익"]

RATIO_SUMMARY_HEADER = "요약재무비율"
RATIO_SUMMARY_FIELDS = [
    "총자산증가율", "매출액증가율", "순이익증가율",
    "영업이익률", "ROE", "ROIC", "부채비율",
    "이자보상배수(배)", "차입금의존도",
    "매출채권회전율(회)", "재고자산회전율(회)", "총자본회전율(회)",
]

# 재무진단 5축 — 각 카테고리 페이지 말미에 "...은/는 {등급}함" 형태로 등장
DIAGNOSIS_AXES = {
    "growth": "성장성",
    "profitability": "수익성",
    "financial_structure": "재무구조",
    "debt_repayment": "부채상환능력",
    "activity": "활동성",
}
DIAGNOSIS_RATING_RE = re.compile(r"(양호|우수|보통|미흡|취약)함$")

PEER_COMPARISON_HEADER = "동종업계내경영규모비교"
PEER_COMPARISON_ROWS = ["조회기업", "상위25%", "평균", "하위25%"]
PEER_COMPARISON_FIELDS = ["총자산", "자본총계", "납입자본금", "매출액", "영업이익", "당기순이익"]

INDUSTRY_RANK_HEADER = "업계순위"

# 매 페이지 상단에 반복되는 보고서 조회 시각 — 같은 사업자번호로 재조회했는지(=중복 의심) 판단용
REPORT_QUERY_DATETIME_RE = re.compile(r"조회일시:(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2})")
EVALUATION_DATE_RE = re.compile(r"평가일자:(\d{4}-\d{2}-\d{2})")
SETTLEMENT_DATE_RE = re.compile(r"결산일자:(\d{4}-\d{2}-\d{2})")
