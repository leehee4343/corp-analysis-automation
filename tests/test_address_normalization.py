"""주소 정규화 단위 테스트. 실제 PDF 샘플이 없어도 항상 실행된다 (SAMPLE 스킵 대상 아님).
배경(PLAN.md 참고): 이 PDF들의 '주소' 필드가 전남 지역 회사인데도 "광주"로 잘못 표기되는
경우가 있음을 참고자료/우편발송용 목록(샘플).xlsx과 대조해 확인했다(65개 중 62개에서 재현).
진짜 광주광역시 주소(구 이름이 뒤따름)는 건드리면 안 된다.
"""
from backend.parser.pdf_parser import _normalize_address


def test_mislabeled_gwangju_becomes_jeonnam():
    postal_code, address = _normalize_address("(58235)광주나주시봉황면옥산유곡길48-19(옥산리)")
    assert postal_code == "58235"
    assert address == "전남나주시봉황면옥산유곡길48-19(옥산리)"


def test_real_gwangju_address_untouched():
    postal_code, address = _normalize_address("(62053)광주서구풍암신흥로")
    assert postal_code == "62053"
    assert address == "광주서구풍암신흥로"


def test_strips_space_before_parenthesis():
    _, address = _normalize_address("(58519)전남무안군무안읍창포로222-12 (교촌리)")
    assert address == "전남무안군무안읍창포로222-12(교촌리)"


def test_no_postal_code_prefix():
    postal_code, address = _normalize_address("광주나주시이창동175-14")
    assert postal_code is None
    assert address == "전남나주시이창동175-14"
