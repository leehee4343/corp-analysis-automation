"""파서 회귀 테스트. tests/sample_pdfs/1_옥산농원.pdf는 민감정보라 git에는 없음(.gitignore) —
로컬에 원본 PDF/1 옥산농원.pdf 를 tests/sample_pdfs/1_옥산농원.pdf 로 복사해야 실행된다.
기대값은 기존 index.html 목업(옥산농원 상세 페이지)에 하드코딩된 값과 대조해 확정한 것.
"""
from pathlib import Path

import pytest

from backend.parser.grade_ocr import extract_grades
from backend.parser.pdf_parser import parse_pdf

SAMPLE = Path(__file__).parent / "sample_pdfs" / "1_옥산농원.pdf"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="샘플 PDF 없음 — PLAN.md Phase 1 참고")


@pytest.fixture(scope="module")
def parsed():
    return parse_pdf(str(SAMPLE))


def test_basic_info(parsed):
    assert parsed.business_no == "412-93-13689"
    assert parsed.company_name == "옥산농원"
    assert parsed.representative == "김종원"
    assert parsed.industry_name == "양계업"
    assert parsed.company_type == "개인사업자"
    assert parsed.company_size == "소기업"
    assert parsed.cross_check_mismatch == []
    assert parsed.missing_fields == []


def test_balance_summary(parsed):
    assert parsed.balance_summary["자산총계"] == {"2023": 3944, "2024": 4000, "2025": 4367}
    assert parsed.balance_summary["부채총계"] == {"2023": 3491, "2024": 3114, "2025": 3310}
    assert parsed.balance_summary["자본총계"] == {"2023": 453, "2024": 885, "2025": 1056}


def test_income_summary(parsed):
    assert parsed.income_summary["매출액"] == {"2023": 7154, "2024": 7241, "2025": 8307}
    assert parsed.income_summary["영업이익"] == {"2023": 329, "2024": 1052, "2025": 1351}
    assert parsed.income_summary["당기순이익"] == {"2023": 261, "2024": 1032, "2025": 1375}


def test_diagnosis(parsed):
    assert parsed.diagnosis == {
        "growth": "양호",
        "profitability": "우수",
        "financial_structure": "양호",
        "debt_repayment": "우수",
        "activity": "우수",
    }


def test_industry_rank(parsed):
    assert parsed.industry_rank == {"rank": 74, "sample_size": 79}


def test_peer_comparison(parsed):
    assert parsed.peer_comparison["조회기업"]["매출액"] == 7241
    assert parsed.peer_comparison["평균"]["매출액"] == 7335
    assert parsed.peer_comparison["상위25%"]["매출액"] == 9968


def test_section_failure_does_not_abort_whole_parse(monkeypatch):
    """한 섹션 파싱이 예외를 던져도 나머지 필드는 그대로 추출되어야 한다
    (사용자 버그 리포트 대응 — 부분 실패 시 통째로 실패시키지 않기로 함, PLAN.md 참고)."""
    from backend.parser import pdf_parser

    def _boom(*a, **kw):
        raise IndexError("의도적으로 발생시킨 테스트용 오류")

    monkeypatch.setattr(pdf_parser, "parse_industry_rank", _boom)
    result = pdf_parser.parse_pdf(str(SAMPLE))

    assert result.company_name == "옥산농원"  # 다른 섹션은 정상 추출
    assert result.balance_summary  # 다른 섹션은 정상 추출
    assert result.industry_rank == {}  # 실패한 섹션만 빈 값
    assert any("업계순위" in e for e in result.parse_errors)


def test_grade_ocr():
    """Tesseract-OCR 미설치 환경에서는 스킵 (README.md 설치 안내 참고)."""
    try:
        grades = extract_grades(str(SAMPLE))
    except Exception as e:  # pytesseract.TesseractNotFoundError 등
        pytest.skip(f"Tesseract-OCR 미설치 또는 실행 실패: {e}")
    assert grades.credit_grade == "bb+"
    assert grades.ew_grade == "정상"
    assert grades.growth_grade is None
