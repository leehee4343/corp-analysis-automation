"""KOREA RATING & DATA 기업종합보고서 PDF 파서.

pdfplumber는 이 문서들의 임베드 폰트에서 한글이 mojibake로 깨져 PyMuPDF(fitz)를 사용한다.
표 데이터는 좌표 기반 셀 구조가 아니라 "라벨 -> 값1 -> 값2 -> 값3" 순서의 평문 텍스트 스트림으로
추출되므로, 라벨 뒤에 이어지는 숫자 토큰을 읽어들이는 방식으로 파싱한다. (PLAN.md Phase 1 참고)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

from . import labels as L
from . import sections as S

YEARS_3 = ("2023", "2024", "2025")

_NUMBER_RE = re.compile(r"^-?[\d,]+\.?\d*$")
_PAGE_FURNITURE_RE = re.compile(r"^(조회일시:|COPYRIGHT|\d+/\d+$)")


def _is_page_furniture(line: str) -> bool:
    """페이지마다 반복되는 머리말/꼬리말(조회일시, 저작권 표기, "N/31" 쪽번호) — 자유
    텍스트 구간을 이어붙일 때 섞여 들어가는 걸 걸러낸다."""
    return bool(_PAGE_FURNITURE_RE.match(line))


def _page_lines(page: "fitz.Page") -> list[str]:
    return [line for line in page.get_text().split("\n") if line.strip()]


def _is_number_token(token: str) -> bool:
    return token == "-" or bool(_NUMBER_RE.match(token))


def _to_number(token: str) -> float | None:
    if token == "-":
        return None
    return float(token.replace(",", ""))


def _find_index(lines: list[str], target: str, start: int = 0) -> int | None:
    for i in range(start, len(lines)):
        if lines[i] == target:
            return i
    return None


def _read_numbers(lines: list[str], start_idx: int, count: int) -> list[float | None] | None:
    values: list[float | None] = []
    idx = start_idx
    for _ in range(count):
        if idx >= len(lines) or not _is_number_token(lines[idx]):
            return None
        values.append(_to_number(lines[idx]))
        idx += 1
    return values


def parse_yearly_table(
    lines: list[str], header: str, field_names: list[str], years: tuple[str, ...] = YEARS_3
) -> dict[str, dict[str, float | None]]:
    """header 이후 구간에서 field_names 각각의 뒤에 오는 연도별 숫자를 읽는다."""
    result: dict[str, dict[str, float | None]] = {}
    header_idx = _find_index(lines, header)
    if header_idx is None:
        return result
    for fname in field_names:
        label_idx = _find_index(lines, fname, start=header_idx + 1)
        if label_idx is None:
            continue
        values = _read_numbers(lines, label_idx + 1, len(years))
        if values is None:
            continue
        result[fname] = dict(zip(years, values))
    return result


def parse_cover_page(lines: list[str]) -> dict[str, str]:
    """1페이지 표지: "- 라벨:" 라인들이 먼저 나오고 값들이 뒤이어 나오는 구조."""
    label_lines = [i for i, l in enumerate(lines) if l.startswith("-") and l.endswith(":")]
    if not label_lines:
        return {}
    n = len(label_lines)
    value_start = label_lines[-1] + 1
    values = lines[value_start:value_start + n]
    keys = ["company_name", "business_no", "representative"]
    return dict(zip(keys, values))


def _normalize_address(raw: str) -> tuple[str | None, str]:
    """"(58235)전남나주시…" -> (우편번호, 주소). labels.py의 GWANGJU_DISTRICTS 주석 참고 —
    이 PDF들의 주소 필드가 "광주"로 잘못 나오는 경우를 "전남"으로 교정한다."""
    m = L.ADDRESS_ZIP_RE.match(raw)
    postal_code, rest = (m.group(1), m.group(2)) if m else (None, raw)
    if rest.startswith("광주") and not rest[2:].startswith(L.GWANGJU_DISTRICTS):
        rest = "전남" + rest[2:]
    rest = re.sub(r"\s+\(", "(", rest)  # "222-12 (교촌리)" -> "222-12(교촌리)"
    return postal_code, rest


def parse_basic_info(lines: list[str]) -> dict[str, str]:
    """2페이지 상세 인적/기업 정보."""
    simple_labels = {
        "기업명": "company_name",
        "사업자번호": "business_no",
        "대표자명": "representative",
        "설립년월": "founded_date",
        "기업유형": "company_type",
        "기업규모": "company_size",
        "주소": "address",
    }
    info: dict[str, str] = {}
    for label, key in simple_labels.items():
        idx = _find_index(lines, label)
        if idx is not None and idx + 1 < len(lines):
            info[key] = lines[idx + 1]

    if "address" in info:
        postal_code, address = _normalize_address(info["address"])
        info["address"] = address
        if postal_code:
            info["postal_code"] = postal_code

    idx = _find_index(lines, "표준산업분류(11차)")
    if idx is not None and idx + 1 < len(lines):
        m = re.match(r"\((\w+)\)(.+)", lines[idx + 1])
        if m:
            info["industry_code"], info["industry_name"] = m.group(1), m.group(2)
        else:
            info["industry_name"] = lines[idx + 1]
    return info


def parse_diagnosis(full_text: str) -> dict[str, str | None]:
    """28~31페이지 재무진단 서술 말미의 "...은/는 {등급}함" 패턴에서 등급 추출."""
    result: dict[str, str | None] = {key: None for key in L.DIAGNOSIS_AXES}
    for line in full_text.split("\n"):
        line = line.strip()
        m = L.DIAGNOSIS_RATING_RE.search(line)
        if not m:
            continue
        rating = m.group(1)
        if "성장" in line:
            result["growth"] = rating
        elif "수익" in line:
            result["profitability"] = rating
        elif "재무안정성" in line or "재무구조" in line:
            result["financial_structure"] = rating
        elif "부채상환" in line:
            result["debt_repayment"] = rating
        elif "재무효율성" in line or "활동성" in line:
            result["activity"] = rating
    return result


# 재무진단 페이지의 5축 등급은 텍스트가 아니라 원형 게이지 이미지다(왼쪽부터 L.DIAGNOSIS_AXES 순서).
# 위 parse_diagnosis가 읽는 "…은 양호함" 요약 문장은 우수/양호일 때만 인쇄되어, 보통이하·낮음은
# 텍스트로는 알 수 없다. 게이지 글자는 OCR이 잘 안 되지만(흰 글씨·파란 바탕 등) 고리 색이 등급별로
# 고정되어 있어 색으로 판정한다(65개 실제 PDF의 325개 게이지 전수 확인, 2026-10-01).
_DIAGNOSIS_GAUGE_COLORS = {
    "우수": (0, 117, 219),       # 파랑
    "양호": (109, 169, 103),     # 초록
    "보통이하": (255, 200, 16),  # 노랑
    "낮음": (233, 90, 71),       # 빨강
    None: (238, 238, 238),       # 회색 빈 고리 = 등급없음
}
_GAUGE_COLOR_TOLERANCE = 60


def _classify_gauge_color(rgb: tuple[int, int, int]) -> str | None:
    """가장 가까운 기준색의 등급. 어느 색과도 멀면 판정하지 않는다(None)."""
    best, best_dist = None, None
    for label, ref in _DIAGNOSIS_GAUGE_COLORS.items():
        dist = sum((a - b) ** 2 for a, b in zip(rgb, ref)) ** 0.5
        if best_dist is None or dist < best_dist:
            best, best_dist = label, dist
    return best if best_dist is not None and best_dist <= _GAUGE_COLOR_TOLERANCE else None


def parse_diagnosis_gauges(doc: "fitz.Document") -> dict[str, str | None] | None:
    """재무진단 페이지(분석의견 표)의 정사각형 게이지 5개에서 등급을 읽는다. 게이지가 시작되는
    12시 방향 고리 픽셀의 색으로 판정. 페이지를 못 찾으면 None."""
    for page in doc:
        text = page.get_text()
        if L.DIAGNOSIS_COMMENTARY_HEADER not in text or "재무진단" not in text:
            continue
        infos = [i for i in page.get_image_info(xrefs=True)
                 if i["width"] == i["height"] and 100 <= i["width"] <= 200 and i.get("xref")]
        if len(infos) < len(L.DIAGNOSIS_AXES):
            continue
        infos = sorted(infos, key=lambda i: i["bbox"][0])[:len(L.DIAGNOSIS_AXES)]
        result: dict[str, str | None] = {}
        for key, info in zip(L.DIAGNOSIS_AXES, infos):
            pix = fitz.Pixmap(doc, info["xref"])
            if pix.n - pix.alpha >= 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            # 12시 방향 고리 위 작은 영역의 평균색 (안티앨리어싱 영향 줄이기)
            cx, top = pix.width // 2, max(1, pix.height // 18)
            samples = [pix.pixel(x, y)[:3] for x in range(cx - 2, cx + 3) for y in range(top - 1, top + 2)]
            avg = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))
            result[key] = _classify_gauge_color(avg)
        return result
    return None


def parse_industry_rank(lines: list[str], business_no: str) -> dict[str, int | None]:
    """10페이지 업계순위 표에서 자사 행을 찾아 순위를 읽는다."""
    header_idx = _find_index(lines, L.INDUSTRY_RANK_HEADER)
    if header_idx is None:
        return {"rank": None, "sample_size": None}
    # 각 행은 [순위(예: "74위"), 기업명, 매출액, 결산월, 사업자번호, 대표자명]. 기업명이 길면 두 줄로
    # 나뉘어(예: "…나주평야동강" / "알피씨") 사업자번호 위치가 밀리므로, 순위 뒤 몇 줄 안에서 찾는다.
    max_rank = None
    own_rank = None
    idx = header_idx
    while idx < len(lines):
        if lines[idx].startswith("동종업계내"):
            break
        m = re.match(r"^(\d+)위$", lines[idx])
        bn_idx = next((j for j in range(idx + 1, min(idx + 8, len(lines)))
                       if L.BUSINESS_NO_RE.fullmatch(lines[j])), None) if m else None
        if m and bn_idx is not None:
            rank = int(m.group(1))
            max_rank = rank if max_rank is None else max(max_rank, rank)
            if lines[bn_idx] == business_no:
                own_rank = rank
            idx = bn_idx + 1
        else:
            idx += 1
    return {"rank": own_rank, "sample_size": max_rank}


def parse_peer_comparison(lines: list[str]) -> dict[str, dict[str, float | None]]:
    """11페이지 동종업계내경영규모비교 표."""
    result: dict[str, dict[str, float | None]] = {}
    header_idx = _find_index(lines, L.PEER_COMPARISON_HEADER)
    if header_idx is None:
        return result
    idx = header_idx
    for row_label in L.PEER_COMPARISON_ROWS:
        row_idx = _find_index(lines, row_label, start=idx + 1)
        if row_idx is None:
            continue
        values = _read_numbers(lines, row_idx + 1, len(L.PEER_COMPARISON_FIELDS))
        if values is None:
            continue
        result[row_label] = dict(zip(L.PEER_COMPARISON_FIELDS, values))
        idx = row_idx
    return result


def _parse_label_block_then_values(lines: list[str], start_idx: int, labels: list[str]) -> dict[str, str] | None:
    """N개 라벨이 연속으로 나온 뒤 N개 값이 연속으로 나오는 구조 (표지 페이지와 동일 패턴)."""
    n = len(labels)
    if start_idx < 0 or lines[start_idx:start_idx + n] != labels:
        return None
    values = lines[start_idx + n: start_idx + 2 * n]
    if len(values) < n:
        return None
    return dict(zip(labels, values))


def parse_credit_info(all_lines: list[str]) -> dict[str, str | None]:
    """3페이지 신용정보 — 라벨 뒤에 "해당사항없음" 또는 값(+날짜)이 다음 라벨 전까지 이어짐."""
    header_idx = _find_index(all_lines, L.CREDIT_INFO_HEADER)
    if header_idx is None:
        return {}
    end_idx = _find_index(all_lines, L.CREDIT_INFO_END_MARKER, start=header_idx + 1)
    section = all_lines[header_idx + 1: end_idx if end_idx is not None else len(all_lines)]
    positions = [(lbl, _find_index(section, lbl)) for lbl in L.CREDIT_INFO_LABELS]
    positions = [(lbl, i) for lbl, i in positions if i is not None]
    positions.sort(key=lambda x: x[1])
    result: dict[str, str | None] = {}
    for i, (lbl, idx) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(section)
        value_lines = section[idx + 1:end]
        result[lbl] = " ".join(value_lines) if value_lines else None
    return result


def parse_certifications_and_ip(all_lines: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """4페이지 기업인증・산업재산권현황."""
    cert_idx = _find_index(all_lines, "기업인증")
    certifications = _parse_label_block_then_values(all_lines, cert_idx + 1 if cert_idx is not None else -1, L.CERTIFICATION_LABELS) or {}
    ip_idx = _find_index(all_lines, "산업재산권")
    ip_rights = _parse_label_block_then_values(all_lines, ip_idx + 1 if ip_idx is not None else -1, L.IP_RIGHTS_LABELS) or {}
    return certifications, ip_rights


def parse_relationship_existence(all_lines: list[str]) -> dict[str, str]:
    """4페이지 주요주주/관계회사/주요구매처/주요판매처 — 실제 목록이 아니라 "조회된 자료가
    없습니다" 여부만(상세 목록은 구조가 회사마다 크게 달라 라벨 존재 여부만 기록)."""
    idx = _find_index(all_lines, "주요주주")
    return _parse_label_block_then_values(all_lines, idx if idx is not None else -1, L.RELATIONSHIP_EXISTENCE_LABELS) or {}


def _scan_labeled_number_triples(lines: list[str], start: int, end: int) -> dict[str, dict[str, float | None]]:
    """start~end 구간에서 "라벨 -> 숫자3개(연도순)" 패턴을 전부 훑는다. 라벨이 아닌 줄
    (페이지 푸터, 컬럼 헤더, 카테고리 구분 등)은 조건이 안 맞아 자동으로 건너뛴다."""
    result: dict[str, dict[str, float | None]] = {}
    idx = max(start, 0)
    end = min(end, len(lines))
    while idx < end:
        label = lines[idx]
        values = _read_numbers(lines, idx + 1, len(YEARS_3))
        if values is not None:
            result[label] = dict(zip(YEARS_3, values))
            idx += 1 + len(YEARS_3)
        else:
            idx += 1
    return result


def _find_ledger_header(lines: list[str], header: str) -> int | None:
    """"재무상태표"/"손익계산서"는 3페이지 MY재무Data 요약표의 열 제목으로도 먼저 등장해
    단순 첫 매치로는 잘못 걸린다 — 상세 표 헤더 뒤엔 항상 "단위:천원"이 바로 이어지는
    것으로 진짜 위치를 구분한다."""
    idx = 0
    while True:
        idx = _find_index(lines, header, start=idx)
        if idx is None:
            return None
        if idx + 1 < len(lines) and lines[idx + 1] == "단위:천원":
            return idx
        idx += 1


def parse_ledger_detail(all_lines: list[str]) -> dict[str, dict[str, dict[str, float | None]]]:
    """재무상태표/손익계산서/현금흐름표/자본변동표/이익잉여금처분계산서/제조원가명세서
    (12~21p) 전체 계정과목을 연도별로 추출한다. 회사마다 결측 섹션(예: 현금흐름표 자료
    없음)이 있을 수 있어 실제 문서에 존재하는 헤더만 포함한다."""
    positions = [(h, _find_ledger_header(all_lines, h)) for h in L.LEDGER_HEADERS]
    positions = [(h, i) for h, i in positions if i is not None]
    positions.sort(key=lambda x: x[1])
    if not positions:
        return {}
    ratio_idx = _find_index(all_lines, L.RATIO_DETAIL_HEADER, start=positions[-1][1] + 1)
    result: dict[str, dict[str, dict[str, float | None]]] = {}
    for i, (header, idx) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else (ratio_idx if ratio_idx is not None else len(all_lines))
        table = _scan_labeled_number_triples(all_lines, idx + 1, end)
        if table:
            result[header] = table
    return result


def parse_ratio_detail(all_lines: list[str]) -> dict[str, dict[str, dict[str, float | None]]]:
    """22~27페이지 재무비율 상세 80여 개 항목을 성장성/수익성/안정성/활동성/생산성
    카테고리별로 묶어 추출한다."""
    header_idx = _find_index(all_lines, L.RATIO_DETAIL_HEADER)
    if header_idx is None:
        return {}
    end_idx = _find_index(all_lines, "재무진단", start=header_idx + 1)
    end = end_idx if end_idx is not None else len(all_lines)
    result: dict[str, dict[str, dict[str, float | None]]] = {}
    current_category: str | None = None
    idx = header_idx + 1
    while idx < end:
        line = all_lines[idx]
        if line in L.RATIO_CATEGORIES:
            current_category = line
            idx += 1
            continue
        values = _read_numbers(all_lines, idx + 1, len(YEARS_3))
        if values is not None and current_category:
            result.setdefault(current_category, {})[line] = dict(zip(YEARS_3, values))
            idx += 1 + len(YEARS_3)
        else:
            idx += 1
    return result


def parse_diagnosis_commentary(all_lines: list[str]) -> str | None:
    """28페이지 재무진단 분석의견 서술 전체(등급 단어만 아니라 문장 전체)."""
    marker_idx = _find_index(all_lines, L.DIAGNOSIS_COMMENTARY_HEADER)
    if marker_idx is None:
        return None
    # "분석의견" 뒤에 5축 라벨이 표 헤더로 한 번 더 나온 다음 실제 서술이 시작된다.
    block_end = marker_idx + 1
    for axis in L.DIAGNOSIS_AXES.values():
        idx = _find_index(all_lines, axis, start=block_end)
        if idx is None or idx > block_end + 5:
            break
        block_end = idx + 1
    boundary_idx = _find_index(all_lines, "성장성", start=block_end)
    end = boundary_idx if boundary_idx is not None else min(block_end + 20, len(all_lines))
    body = [line for line in all_lines[block_end:end] if not _is_page_furniture(line)]
    text = " ".join(body).strip()
    return text or None


def parse_personal_info(all_lines: list[str]) -> dict[str, str]:
    """7페이지 대표자 인적사항 — 값이 안정적으로 채워지는 2개 필드만(나머지는 값이 없을 때
    라벨만 남아 라벨-값 경계가 모호해 신뢰도 낮음)."""
    result: dict[str, str] = {}
    for label, key in L.PERSONAL_INFO_LABELS.items():
        idx = _find_index(all_lines, label)
        if idx is not None and idx + 1 < len(all_lines):
            result[key] = all_lines[idx + 1]
    return result


_SOFT_SECTION_HEADERS = [
    "인적사항", "경영진현황", "주식소유현황", "주요주주현황",
    "관계회사현황", "사업장현황", "구매처현황", "판매처현황", "매출구성",
    "연혁", "사업목적", "종합의견",
]
_SOFT_SECTION_EXTRA_BOUNDARIES = (L.INDUSTRY_RANK_HEADER,)


def parse_soft_sections(all_lines: list[str]) -> dict[str, str | None]:
    """완벽한 표 구조화 대신 "아무것도 안 빠뜨리는" 것을 우선하는 나머지 섹션들
    (연혁/사업목적/종합의견/경영진현황/주식소유현황/주요주주현황/관계회사현황/사업장현황/
    거래처현황/매출구성) — 헤더 사이 원문을 그대로 이어붙이고, "조회된 자료가 없습니다"만
    있으면 None으로 저장한다."""
    all_markers = list(_SOFT_SECTION_HEADERS) + list(_SOFT_SECTION_EXTRA_BOUNDARIES)
    positions = []
    for h in all_markers:
        idx = _find_index(all_lines, h)
        if idx is not None:
            positions.append((h, idx))
    positions.sort(key=lambda x: x[1])
    result: dict[str, str | None] = {}
    for i, (h, idx) in enumerate(positions):
        if h not in _SOFT_SECTION_HEADERS:
            continue
        end = positions[i + 1][1] if i + 1 < len(positions) else len(all_lines)
        body = [line for line in all_lines[idx + 1:end] if not _is_page_furniture(line)]
        text = " ".join(body).strip()
        result[h] = None if (not text or text.replace(" ", "") == L.NO_DATA_TEXT) else text
    return result


@dataclass
class ParsedCompany:
    business_no: str | None = None
    company_name: str | None = None
    representative: str | None = None
    address: str | None = None
    postal_code: str | None = None
    founded_date: str | None = None
    industry_code: str | None = None
    industry_name: str | None = None
    company_type: str | None = None
    company_size: str | None = None
    balance_summary: dict = field(default_factory=dict)
    income_summary: dict = field(default_factory=dict)
    ratio_summary: dict = field(default_factory=dict)
    diagnosis: dict = field(default_factory=dict)
    industry_rank: dict = field(default_factory=dict)
    peer_comparison: dict = field(default_factory=dict)
    cross_check_mismatch: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    report_query_datetime: str | None = None
    evaluation_date: str | None = None
    settlement_date: str | None = None
    source_pdf: str | None = None
    page_count: int = 0

    # ===== PDF 전체 추출 (사용자 요청, PLAN.md 참고) =====
    credit_info: dict = field(default_factory=dict)
    certifications: dict = field(default_factory=dict)
    ip_rights: dict = field(default_factory=dict)
    relationship_existence: dict = field(default_factory=dict)
    ledger_detail: dict = field(default_factory=dict)
    ratio_detail: dict = field(default_factory=dict)
    diagnosis_commentary: str | None = None
    personal_info: dict = field(default_factory=dict)
    soft_sections: dict = field(default_factory=dict)

    # ===== 2026-10-02 확장: 연도 인식 + 미추출 영역 전부 =====
    basic_extra: dict = field(default_factory=dict)
    my_financial_data: dict = field(default_factory=dict)
    cash_flow_summary: dict = field(default_factory=dict)
    cash_flow_base_date: str | None = None
    audit_opinions: dict = field(default_factory=dict)
    diagnosis_details: dict = field(default_factory=dict)
    industry_rank_list: list = field(default_factory=list)
    industry_top5: list = field(default_factory=list)
    industry_base_year: str | None = None
    peer_base_year: str | None = None
    partners: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    bid_summary: dict = field(default_factory=dict)
    tech_info: dict = field(default_factory=dict)


_SECTION_STOPS = {
    "신용정보", "MY 재무Data", "기술력", "요약재무상태표", "요약손익계산서", "요약현금흐름분석", "요약재무비율",
    "연혁", "사업목적", "종합의견", "인적사항", "경영진현황", "주요주주현황", "관계회사현황", "사업장현황",
    "거래처현황", "구매처현황", "판매처현황", "매출구성", "업계순위", "동종업계내매출액분포", "동종업계내경영규모비교",
    "재무진단",
}


def _section(lines: list[str], header: str, start: int = 0) -> tuple[int, int] | None:
    """header 줄 위치와 다음 영역 헤더 직전까지의 끝 위치."""
    idx = S.find_line(lines, header, start)
    if idx is None:
        return None
    end = next((i for i in range(idx + 1, len(lines)) if lines[i] in _SECTION_STOPS and lines[i] != header), len(lines))
    return idx, end


def _basic_info_page(doc: "fitz.Document") -> int:
    """기본정보(기업명·대표자명·주소) 페이지. 보통 2페이지지만 앞 페이지가 하나 더 있는 보고서는 3페이지."""
    for i in range(1, min(doc.page_count, 5)):
        lines = _page_lines(doc[i])
        if "대표자명" in lines and "주소" in lines:
            return i
    return 1


def _parse_tables(all_lines: list[str], result: "ParsedCompany", errors: list[str]) -> None:
    """재무 표 전부를 실제 연도로 읽는다(sections.py 규칙)."""
    # 상세 재무제표(천원) — 표마다 자기 머리글 연도 + 감사의견
    positions = [(h, _find_ledger_header(all_lines, h)) for h in L.LEDGER_HEADERS]
    positions = sorted([(h, i) for h, i in positions if i is not None], key=lambda x: x[1])
    ratio_idx = None
    if positions:
        ratio_idx = S.find_line(all_lines, L.RATIO_DETAIL_HEADER, positions[-1][1] + 1)
    for n, (header, idx) in enumerate(positions):
        end = positions[n + 1][1] if n + 1 < len(positions) else (ratio_idx or len(all_lines))
        parsed = _safe(errors, f"{header}(상세)", lambda: S.parse_ledger(all_lines, idx, end))
        if parsed:
            table, audit = parsed
            if table:
                result.ledger_detail[header] = table
            if audit:
                result.audit_opinions[header] = audit

    # 요약표의 연도를 못 찾을 때 쓸 결산연도: 상세 재무상태표 → 결산일자 기준 3개년
    bs_years = sorted({y for row in result.ledger_detail.get("재무상태표", {}).values() for y in row if y.isdigit()})
    if not bs_years and result.settlement_date:
        last = int(result.settlement_date[:4])
        bs_years = [str(last - 2), str(last - 1), str(last)]

    def summary(header):
        sec = _section(all_lines, header)
        return S.parse_summary(all_lines, sec[0], sec[1], bs_years) if sec else {}

    result.balance_summary = _safe(errors, "요약재무상태표", lambda: summary(L.BALANCE_SUMMARY_HEADER)) or {}
    result.income_summary = _safe(errors, "요약손익계산서", lambda: summary(L.INCOME_SUMMARY_HEADER)) or {}
    result.ratio_summary = _safe(errors, "요약재무비율", lambda: summary(L.RATIO_SUMMARY_HEADER)) or {}
    result.cash_flow_summary = _safe(errors, "요약현금흐름분석", lambda: summary("요약현금흐름분석")) or {}
    sec = _section(all_lines, "요약현금흐름분석")
    if sec:
        result.cash_flow_base_date = next((l.split(":", 1)[1].strip() for l in all_lines[sec[0]:sec[1]]
                                           if l.replace(" ", "").startswith("기준일자:")), None)

    def my_data():
        idx = S.find_line(all_lines, "MY 재무Data")
        if idx is None:
            return {}
        end = S.find_line(all_lines, "재무상태표", idx + 1) or idx + 40
        return S.parse_summary(all_lines, idx, end, bs_years[-2:])
    result.my_financial_data = _safe(errors, "MY 재무Data", my_data) or {}

    if ratio_idx is not None:
        end = S.find_line(all_lines, "재무진단", ratio_idx + 1) or len(all_lines)
        result.ratio_detail = _safe(errors, "재무비율 상세", lambda: S.parse_ratio_detail(all_lines, ratio_idx, end)) or {}


def _parse_extended(all_lines: list[str], basic_lines: list[str], result: "ParsedCompany", errors: list[str]) -> None:
    result.basic_extra = _safe(errors, "기본정보 추가 항목", lambda: S.parse_basic_extra(basic_lines)) or {}
    result.diagnosis_details = _safe(errors, "재무진단 상세", lambda: S.parse_diagnosis_details(all_lines)) or {}

    rank_sec = _section(all_lines, L.INDUSTRY_RANK_HEADER)
    if rank_sec:
        result.industry_base_year = S.base_year_after(all_lines, rank_sec[0])
        result.industry_rank_list = _safe(errors, "업계순위 목록",
                                          lambda: S.parse_rank_rows(all_lines, rank_sec[0], rank_sec[1])) or []
    top_sec = _section(all_lines, "동종업계내매출액분포")
    if top_sec:
        result.industry_top5 = sorted(_safe(errors, "동종업계 상위 기업",
                                            lambda: S.parse_rank_rows(all_lines, top_sec[0], top_sec[1])) or [],
                                      key=lambda r: r["rank"])
    peer_idx = S.find_line(all_lines, L.PEER_COMPARISON_HEADER)
    if peer_idx is not None:
        result.peer_base_year = S.base_year_after(all_lines, peer_idx)

    for key, header in (("구매처", "구매처현황"), ("판매처", "판매처현황")):
        sec = _section(all_lines, header)
        if sec:
            rows = _safe(errors, f"{header} 표", lambda: S.parse_partner_rows(all_lines, sec[0], sec[1])) or []
            if rows:
                result.partners[key] = rows
    sec = _section(all_lines, "연혁")
    if sec:
        result.history = _safe(errors, "연혁 표", lambda: S.parse_history(all_lines, sec[0] + 1, sec[1])) or []
    sec = _section(all_lines, "인적사항")
    if sec:
        personal = _safe(errors, "대표자 인적사항", lambda: S.parse_personal(all_lines, sec[0], sec[1])) or {}
        result.personal_info = {k: v for k, v in personal.items() if k != "주요경력사항"}
    result.bid_summary = _safe(errors, "나라장터 입찰정보", lambda: S.parse_bid_summary(all_lines)) or {}
    result.tech_info = _safe(errors, "기술력", lambda: S.parse_tech(all_lines)) or {}

    # 주요주주·관계회사·구매처·판매처 존재 여부: 상세 영역(원문/표) 기준으로 판정
    def exists(text_key=None, rows=None):
        if rows:
            return f"있음 ({len([r for r in rows if r.get('business_no')])}개사)"
        if text_key and result.soft_sections.get(text_key):
            return "있음"
        return "조회된 자료가 없습니다"
    result.relationship_existence = {
        "주요주주": exists("주요주주현황"), "관계회사": exists("관계회사현황"),
        "주요구매처": exists(rows=result.partners.get("구매처")),
        "주요판매처": exists(rows=result.partners.get("판매처")),
    }


def _safe(errors: list[str], label: str, fn):
    """섹션 하나가 실패해도 문서 전체 파싱을 중단시키지 않는다 — 실패한 섹션은
    빈 결과로 두고 사유를 parse_errors에 남겨 검증 대기열에서 보이게 한다."""
    try:
        return fn()
    except Exception as e:
        errors.append(f"{label}: {type(e).__name__}: {e}")
        return None


def parse_pdf(path: str) -> ParsedCompany:
    doc = fitz.open(path)  # 파일 자체를 못 열면(진짜 PDF가 아님) 여기서만 그대로 실패시킨다.
    try:
        result = ParsedCompany(source_pdf=path, page_count=doc.page_count)
        errors = result.parse_errors

        cover = _safe(errors, "표지 파싱", lambda: parse_cover_page(_page_lines(doc[0])) if doc.page_count > 0 else {}) or {}
        basic_page = _basic_info_page(doc) if doc.page_count > 1 else None
        basic_lines = _page_lines(doc[basic_page]) if basic_page is not None else []
        detail = _safe(errors, "상세정보 파싱", lambda: parse_basic_info(basic_lines)) or {}

        for key in ("company_name", "business_no", "representative"):
            cover_val, detail_val = cover.get(key), detail.get(key)
            if cover_val and detail_val and cover_val != detail_val:
                result.cross_check_mismatch.append(key)
        merged = {**cover, **detail}  # 상세 페이지 값을 우선
        result.business_no = merged.get("business_no")
        result.company_name = merged.get("company_name")
        result.representative = merged.get("representative")
        result.address = detail.get("address")
        result.postal_code = detail.get("postal_code")
        result.founded_date = detail.get("founded_date")
        result.industry_code = detail.get("industry_code")
        result.industry_name = detail.get("industry_name")
        result.company_type = detail.get("company_type")
        result.company_size = detail.get("company_size")

        # 섹션 페이지 번호는 문서마다 다르다 (예: 개인사업자 31p본은 업계순위가 10p,
        # 법인 36p본은 13p) — 고정 페이지 인덱스 대신 전체 문서를 한 줄 리스트로 이어붙여
        # 헤더 라벨을 검색한다. (PLAN.md Phase 2 로그 참고)
        all_lines = _safe(errors, "전체 텍스트 추출", lambda: [line for page in doc for line in _page_lines(page)]) or []

        if m := L.SETTLEMENT_DATE_RE.search("\n".join(all_lines)):
            result.settlement_date = m.group(1)
        _parse_tables(all_lines, result, errors)
        result.industry_rank = _safe(errors, "업계순위",
            lambda: parse_industry_rank(all_lines, result.business_no or "")) or {}
        result.peer_comparison = _safe(errors, "동종업계비교",
            lambda: parse_peer_comparison(all_lines)) or {}

        result.credit_info = _safe(errors, "신용정보", lambda: parse_credit_info(all_lines)) or {}
        certs_ip = _safe(errors, "기업인증・산업재산권", lambda: parse_certifications_and_ip(all_lines))
        result.certifications, result.ip_rights = certs_ip if certs_ip else ({}, {})
        result.personal_info = _safe(errors, "대표자 인적사항",
            lambda: parse_personal_info(all_lines)) or {}
        result.soft_sections = _safe(errors, "연혁/경영진현황 등 기타 섹션",
            lambda: parse_soft_sections(all_lines)) or {}
        _parse_extended(all_lines, basic_lines, result, errors)

        full_text = _safe(errors, "재무진단 텍스트 추출", lambda: "\n".join(page.get_text() for page in doc)) or ""
        result.diagnosis = _safe(errors, "재무진단", lambda: parse_diagnosis(full_text)) or {}
        # 게이지 이미지 판정이 우선(보통이하·낮음까지 읽힘), 판정 못 한 축만 텍스트 결과를 남긴다.
        gauges = _safe(errors, "재무진단 게이지", lambda: parse_diagnosis_gauges(doc)) or {}
        result.diagnosis = {key: gauges.get(key) or result.diagnosis.get(key) for key in L.DIAGNOSIS_AXES}
        result.diagnosis_commentary = _safe(errors, "재무진단 분석의견",
            lambda: parse_diagnosis_commentary(all_lines))

        if m := L.REPORT_QUERY_DATETIME_RE.search(full_text):
            result.report_query_datetime = m.group(1)
        if m := L.EVALUATION_DATE_RE.search(full_text):
            result.evaluation_date = m.group(1)
        if m := L.SETTLEMENT_DATE_RE.search(full_text):
            result.settlement_date = m.group(1)

        required = ["business_no", "company_name", "representative", "address"]
        result.missing_fields = [f for f in required if not getattr(result, f)]

        return result
    finally:
        doc.close()
