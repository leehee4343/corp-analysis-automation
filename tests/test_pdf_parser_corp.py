"""법인(주식회사) 샘플로 파서의 페이지-무관성을 검증한다.

개인사업자 샘플(옥산농원, 31p)은 업계순위/동종업계비교/재무진단 섹션이 각각
10p/11p/28~31p에 있었지만, 이 법인 샘플(36p)은 같은 섹션이 13p/14p/34~36p에 있다.
고정 페이지 인덱스로 찾던 최초 구현은 이 샘플에서 전부 빈 값을 반환했었다 —
헤더 텍스트를 전체 문서에서 검색하도록 고친 회귀 방지 테스트.
tests/sample_pdfs/10_주삼진지에프.pdf 는 민감정보라 git에는 없음(.gitignore).
"""
from pathlib import Path

import pytest

from backend.parser.pdf_parser import parse_pdf

SAMPLE = Path(__file__).parent / "sample_pdfs" / "10_주삼진지에프.pdf"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="샘플 PDF 없음")


@pytest.fixture(scope="module")
def parsed():
    return parse_pdf(str(SAMPLE))


def test_basic_info(parsed):
    assert parsed.business_no == "412-81-00110"
    assert parsed.company_type == "일반법인"
    assert parsed.missing_fields == []


def test_page_count_differs_from_first_sample(parsed):
    assert parsed.page_count == 36


def test_diagnosis_found_despite_different_page_layout(parsed):
    assert all(v is not None for v in parsed.diagnosis.values())


def test_industry_rank_found_despite_different_page_layout(parsed):
    assert parsed.industry_rank["rank"] is not None
    assert parsed.industry_rank["sample_size"] is not None


def test_peer_comparison_found_despite_different_page_layout(parsed):
    assert parsed.peer_comparison.get("조회기업", {}).get("매출액") == parsed.income_summary["매출액"]["2024"]
