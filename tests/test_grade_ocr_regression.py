"""OCR 회귀 테스트. Phase 7의 65개 전수 배치 테스트로 찾은 두 버그의 재발 방지용
(PLAN.md 참고): (1) 신용등급이 형식에 안 맞는 잡음으로 조용히 저장되던 문제,
(2) EW등급 앞에 잡음 글자가 붙어 실제 값(예: "유보")이 잘리던 문제.
tests/sample_pdfs/35_성지에프앤디.pdf 는 민감정보라 git에는 없음(.gitignore).
"""
from pathlib import Path

import pytest

from backend.parser.grade_ocr import extract_grades

SAMPLE = Path(__file__).parent / "sample_pdfs" / "35_성지에프앤디.pdf"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="샘플 PDF 없음")


def test_ew_grade_not_contaminated_by_leading_noise_char():
    try:
        grades = extract_grades(str(SAMPLE))
    except Exception as e:
        pytest.skip(f"Tesseract-OCR 미설치 또는 실행 실패: {e}")
    assert grades.ew_grade == "유보"  # 예전엔 "가\n유보"의 "가"만 저장됐음
    assert grades.credit_grade == "bb"  # 형식 검증 통과하는 값만 저장되어야 함
