"""추출 완성도(미추출 / 추출대상) 규칙."""
from backend.parser import coverage


def test_structural_lines_are_not_targets_and_empty_counts_as_extracted():
    lines = ["요약재무상태표", "단위:백만원", "자산총계", "1,000", "-", "조회된자료가없습니다.", "구분", "2025"]
    c = coverage.compute(lines, {"balance_summary": {"자산총계": {"2025": 1000.0}}})
    assert c["target"] == 3 and c["missed"] == 0   # 자산총계·1,000·"-"(빈 칸은 추출 인정). 자료없음 안내 문구는 대상 아님


def test_missing_value_is_counted():
    c = coverage.compute(["주요제품(상품)", "김치류"], {"basic_extra": {}})
    assert (c["missed"], c["target"], c["missed_items"]) == (1, 1, ["김치류"])


def test_normalized_address_and_rank_and_label_value_are_recognized():
    extracted = {"address": "전남나주시산포면산남로96(등정리)", "postal_code": "58212", "rank": 48, "evaluation_date": "2026-06-26"}
    lines = ["(58212)광주나주시산포면산남로96(등정리)", "48위", "평가일자: 2026-06-26"]
    assert coverage.compute(lines, extracted)["missed"] == 0
