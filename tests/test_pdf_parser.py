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


def test_address_and_postal_code(parsed):
    """PDF의 '주소' 필드가 "광주"로 잘못 표기되는 경우가 있어(참고자료의 검증된 우편발송
    목록과 대조해 확인, PLAN.md 참고) "전남"으로 교정하고 우편번호를 분리해 저장한다."""
    assert parsed.postal_code == "58235"
    assert parsed.address == "전남나주시봉황면옥산유곡길48-19(옥산리)"


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


def test_credit_info_and_certifications(parsed):
    """사용자 요청으로 PDF 전체 내용을 뽑도록 확장(PLAN.md 참고) — 신용정보/인증/지재권."""
    assert parsed.credit_info["행정처분정보"] == "해당사항없음"
    assert parsed.credit_info["당좌개설/카드발급정보"] == "1건 2025-03-05"
    assert parsed.certifications == {
        "벤처": "미인증", "이노비즈": "미인증", "메인비즈": "미인증",
        "연구개발전담부서": "미인증", "부설연구소": "미인증",
    }
    assert parsed.ip_rights == {"특허": "-", "실용신안": "-", "디자인": "-", "상표권": "-"}


def test_ledger_detail_full_line_items(parsed):
    """재무상태표/손익계산서 전체 계정과목(요약표보다 훨씬 상세) — 3페이지 MY재무Data
    요약표의 열 제목("재무상태표"/"손익계산서")과 헷갈리지 않고 12/15페이지의 진짜 상세
    표를 찾아야 한다."""
    balance = parsed.ledger_detail["재무상태표"]
    assert balance["자산(*)"] == {"2023": 3943892, "2024": 3999727, "2025": 4366652}
    assert len(balance) > 40  # 요약표는 4개 항목뿐이지만 상세표는 수십 개

    income = parsed.ledger_detail["손익계산서"]
    assert income["매출액(*)"] == {"2023": 7154489, "2024": 7240823, "2025": 8306768}


def test_ratio_detail_grouped_by_category(parsed):
    ratio = parsed.ratio_detail
    assert set(ratio.keys()) == {"성장성", "수익성", "안정성", "활동성", "생산성"}
    assert ratio["안정성"]["부채비율"] == {"2023": 770.81, "2024": 351.75, "2025": 313.37}
    assert sum(len(v) for v in ratio.values()) > 100  # 요약표는 12개뿐, 상세표는 100개 이상


def test_diagnosis_commentary_full_text_captured(parsed):
    assert parsed.diagnosis_commentary is not None
    assert "양호한성장역량을보유하고있음" in parsed.diagnosis_commentary
    assert "조회일시" not in parsed.diagnosis_commentary  # 페이지 머리말이 안 섞여야 함


def test_soft_sections_no_data_becomes_none_but_populated_stays(parsed):
    assert parsed.soft_sections["종합의견"] is None  # "조회된자료가없습니다."만 있던 경우
    assert "김종원" in parsed.soft_sections["주식소유현황"]  # 실제 내용이 있는 경우


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
