"""추출 완성도: PDF의 값(숫자·텍스트 칸) 중 파싱 결과에 저장되지 않은 것을 센다.

- 추출 대상: PDF 텍스트 줄 중 정보가 아닌 줄(제목·단위·표 머리글·쪽번호·조회일시 등)을 뺀 값 줄.
- 빈 칸("-", "조회된자료가없습니다." 등)은 원본에 값이 없는 것이므로 추출된 것으로 본다.
- 판정: 숫자는 저장된 숫자 집합에, 텍스트는 저장된 모든 문자열(키 포함)을 이어 붙인 본문에 있으면 추출됨.
  "라벨:값" 줄은 값 부분, "N위"는 숫자 N, "(코드)이름"은 코드·이름 각각으로 대조한다.
"""
from __future__ import annotations

import re

from . import sections as S

_NUM_RE = re.compile(r"^-?[\d,]+\.?\d*%?$")
_RANK_RE = re.compile(r"^(\d+)위$")
_CODE_NAME_RE = re.compile(r"^\((\w+)\)(.+)$")
_LABEL_VALUE_RE = re.compile(r"^[^:：]{1,20}[:：]\s*(.+)$")

# 정보가 아닌 줄: 영역 제목·표 머리글·안내 문구 (값이 아니므로 추출 대상에서 제외)
STRUCTURAL = {
    "기업종합보고서", "- 기업명:", "- 사업자번호:", "- 대표자:", "기업개요", "기업신용등급", "EW 등급", "EW등급", "기업성장등급",
    "기업관계망", "기업성장성을", "10단계등급으로", "평가하여제공", "연계기업", "유보~부도", "휴폐업/", "청산해산",
    "신용정보", "MY 재무Data", "재무상태표", "손익계산서", "현금흐름표", "자본변동표", "이익잉여금처분계산서", "제조원가명세서",
    "기술력", "기업인증・산업재산권현황", "기업인증", "산업재산권", "평가기준연도정보없음", "나라장터입찰정보요약",
    "입찰건수", "낙찰건수", "총낙찰금액", "최근1년기준집계", "요약재무상태표", "요약손익계산서", "요약현금흐름분석", "요약재무비율",
    "성장성", "수익성", "안정성", "활동성", "생산성", "재무구조", "부채상환능력", "재무비율", "재무진단", "분석의견",
    "연혁", "연혁일자", "내용", "사업목적", "종합의견", "인적사항", "경영진현황", "주식소유현황", "주요주주현황", "관계회사현황",
    "사업장현황", "사업장세부현황", "거래처현황", "구매처현황", "판매처현황", "매출구성", "업계순위", "상위/하위기업및조회기업순위",
    "동종업계내매출액분포", "동종업계내경영규모비교", "순위", "순위(상위5)", "기업명", "매출액", "결산월", "사업자번호", "대표자명",
    "주요주주", "관계회사", "주요구매처", "주요판매처", "주요경력사항",
    # 2페이지 기본정보 라벨
    "영문기업명", "법인(주민)번호", "대표자명", "종업원수", "설립형태", "설립년월", "기업유형", "기업규모", "전화번호", "팩스번호",
    "홈페이지", "이메일", "기업공개일자", "주소", "표준산업분류(10차)", "표준산업분류(11차)", "주요제품(상품)", "무역업허가번호",
    "소속그룹", "주채권기관", "당좌거래은행", "휴폐업정보", "법인등기정보", "기간", "근무기업", "근무업종", "최종직위", "담당업무",
}
_STRUCTURAL_PREFIXES = ("ⓘ", "※")


def _is_structural(line: str) -> bool:
    if line in STRUCTURAL or line.startswith(_STRUCTURAL_PREFIXES) or S.is_noise(line) or re.fullmatch(r"/\d+", line):
        return True
    return False


def _is_empty_value(line: str) -> bool:
    return line in ("-", "조회된자료가없습니다.", "해당사항없음", "?", "?건")


def _collect(obj, strings: list[str], numbers: set[float]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            strings.append(str(k))
            _collect(v, strings, numbers)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, strings, numbers)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        numbers.add(round(float(obj), 4))
    else:
        strings.append(str(obj))


def compute(lines: list[str], extracted: dict) -> dict:
    """lines: PDF 전체 텍스트 줄(쪽 순서). extracted: 파싱 결과(dict). 반환: {target, missed, missed_items[≤50]}."""
    strings: list[str] = []
    numbers: set[float] = set()
    _collect(extracted, strings, numbers)
    blob = "\n".join(strings).replace(" ", "")

    def found_text(text: str) -> bool:
        return text.replace(" ", "") in blob

    def found(line: str) -> bool:
        if _NUM_RE.match(line):
            try:
                return round(float(line.replace(",", "").rstrip("%")), 4) in numbers or found_text(line)
            except ValueError:
                return found_text(line)
        if found_text(line):
            return True
        if m := _RANK_RE.match(line):
            return float(m.group(1)) in numbers
        if (m := _CODE_NAME_RE.match(line)) and found_text(m.group(1)) and found_text(m.group(2)):
            return True
        if m := _LABEL_VALUE_RE.match(line):
            return found_text(m.group(1))
        if line.startswith("(") and "광주" in line:  # 주소의 '광주'→'전남' 교정 저장(pdf_parser._normalize_address)
            return found_text(line.replace("광주", "전남", 1)) or found_text(re.sub(r"^\(\d{5}\)", "", line).replace("광주", "전남", 1))
        return False

    target = 0
    missed: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or _is_structural(line):
            continue
        target += 1
        if _is_empty_value(line):
            continue
        if not found(line):
            missed.append(line)
    return {"target": target, "missed": len(missed), "missed_items": missed[:50]}
