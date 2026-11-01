from pathlib import Path


HTML = (Path(__file__).parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def test_metric_range_form_blocks_reversed_values_and_shows_inline_error():
    assert "if(!validateMetricRanges(screen.form)) return;" in HTML
    assert "최소값은 최대값보다 클 수 없습니다." in HTML
    assert "metric-range-error" in HTML
    assert "aria-invalid" in HTML


def test_compact_layout_uses_overlay_sidebar_and_fluid_range_inputs():
    compact = HTML.split("@media (max-width:1100px){", 1)[1].split("@media (max-width:760px){", 1)[0]
    mobile = HTML.split("@media (max-width:760px){", 1)[1].split("@media (max-width:420px){", 1)[0]
    assert ".sidebar{position:fixed" in compact
    assert "transform:translateX(-100%)" in compact
    assert ".main-content{width:100%; max-width:100%;}" in compact
    assert ".filter-input.range-input{flex:1 1 0; width:0; min-width:0;}" in mobile
    assert "compactQuery.matches || storageGet('sidebarCollapsed') === '1'" in HTML
