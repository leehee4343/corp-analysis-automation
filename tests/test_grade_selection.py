"""신용등급 다수결·아치 색 교차검증, EW등급 보정 (샘플 PDF·Tesseract 없이 항상 실행)."""
from collections import Counter

from backend.parser.grade_ocr import _ARC_COLOR_BANDS, _choose_credit_grade, _normalize_ew

GREEN = _ARC_COLOR_BANDS[(110, 170, 100)]
BLUE = _ARC_COLOR_BANDS[(0, 120, 220)]


def test_color_band_rejects_misread_d_for_green_gauge():
    # 실제 사례: 'a' 게이지를 단일 OCR이 'd'(부도 등급)로 읽었음 — 초록 아치에서 d는 불가능
    assert _choose_credit_grade(Counter({"d": 9, "a": 4}), GREEN) == "a"


def test_prefers_grade_with_thin_modifier_when_often_seen():
    # 실제 사례: 'aa-'의 가는 '-'를 놓쳐 'aa'가 근소하게 많이 나옴
    assert _choose_credit_grade(Counter({"aa": 3, "aa-": 2}), BLUE) == "aa-"


def test_rare_modifier_noise_does_not_win():
    assert _choose_credit_grade(Counter({"bbb": 15, "bbb+": 1}), None) == "bbb"


def test_no_candidate_consistent_with_color_returns_none():
    assert _choose_credit_grade(Counter({"d": 5}), GREEN) is None


def test_unknown_color_falls_back_to_majority():
    assert _choose_credit_grade(Counter({"bb+": 15, "bbb+": 3}), None) == "bb+"


def test_ew_known_values_unchanged():
    for v in ("정상", "관심", "유보"):
        assert _normalize_ew(v) == v


def test_ew_misread_corrected_by_jamo_similarity():
    assert _normalize_ew("과시") == "관심"  # 실제 사례: 받침 누락


def test_ew_unrelated_text_kept_as_is():
    assert _normalize_ew("가나다라") == "가나다라"
