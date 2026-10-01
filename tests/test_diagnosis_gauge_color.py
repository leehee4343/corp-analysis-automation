"""재무진단 게이지 색 → 등급 판정 (샘플 PDF 없이 항상 실행)."""
from backend.parser.pdf_parser import _classify_gauge_color


def test_known_gauge_colors():
    assert _classify_gauge_color((0, 117, 219)) == "우수"
    assert _classify_gauge_color((109, 169, 103)) == "양호"
    assert _classify_gauge_color((255, 200, 16)) == "보통이하"
    assert _classify_gauge_color((233, 90, 71)) == "낮음"


def test_gray_ring_means_no_grade():
    assert _classify_gauge_color((238, 238, 238)) is None


def test_slightly_off_color_still_matches():
    assert _classify_gauge_color((10, 120, 210)) == "우수"


def test_unknown_color_is_not_guessed():
    assert _classify_gauge_color((120, 0, 160)) is None  # 보라 — 어느 등급도 아님
