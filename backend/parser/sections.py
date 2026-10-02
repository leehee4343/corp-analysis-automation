"""기업종합보고서의 표·영역별 파서 (연도 인식, 문자 값, 전체 추출 확장 — 2026-10-02).

PyMuPDF 텍스트는 "라벨 → 값 → 값 …" 순서의 줄 목록으로 나오므로 공통 규칙으로 읽는다.
- 값 토큰: 숫자 / "-"(값 없음) / 흑자전환·적자전환·적자지속·흑자지속 / CR1~CR9(현금흐름등급) / ▲증가·▼감소
- 라벨은 여러 줄로 나뉠 수 있다(예: "경상활동후의현금" + "흐름") → 값이 나오기 전까지의 줄을 이어붙인다.
- 연도는 표마다 다르다(같은 보고서 안에서도 재무상태표 2022~2024, 현금흐름표 2019~2021 등).
  표 머리글의 날짜(YYYY-MM-DD) 또는 연도(YYYY)를 쓰고, 값 칸이 날짜보다 많으면 오른쪽(최근)부터
  맞춘다. 연도를 알 수 없는 칸은 값이 모두 비어 있으면 버리고, 값이 있으면 "연도미상N"으로 남긴다.
"""
from __future__ import annotations

import re
from collections import Counter

NUM_RE = re.compile(r"^-?[\d,]+\.?\d*$")
TEXT_VALUE_RE = re.compile(r"^((흑자|적자)(전환|지속)|CR\d|NR|[▲▼](증가|감소))$")  # NR: 현금흐름등급 미산정
DATE_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}$")
YEAR_RE = re.compile(r"^(\d{4})$")
OPINION_RE = re.compile(r"^(적정|한정|부적정|의견거절)")
_FURNITURE_RE = re.compile(r"^(조회일시:|COPYRIGHT|\d+/\d+$)")
_NOISE_PREFIXES = ("단위:", "단위 :", "기준일자", "기준년도", "ⓘ")
_NOISE_LINES = {"구분", "계정명", "감사의견", "조회된자료가없습니다.", "업종평균", "전년대비", "조회기업"}

YearlyValues = dict[str, "float | str | None"]


def is_value(token: str) -> bool:
    return token == "-" or bool(NUM_RE.match(token)) or bool(TEXT_VALUE_RE.match(token))


def to_value(token: str) -> float | str | None:
    if token == "-":
        return None
    if NUM_RE.match(token):
        return float(token.replace(",", ""))
    return token


def is_noise(line: str) -> bool:
    return (line in _NOISE_LINES or line.startswith(_NOISE_PREFIXES) or bool(_FURNITURE_RE.match(line))
            or bool(DATE_RE.match(line)) or bool(YEAR_RE.match(line)) or bool(OPINION_RE.match(line)))


def year_of(token: str) -> str | None:
    m = DATE_RE.match(token) or YEAR_RE.match(token)
    return m.group(1) if m else None


def find_line(lines: list[str], target: str, start: int = 0, end: int | None = None) -> int | None:
    for i in range(start, len(lines) if end is None else min(end, len(lines))):
        if lines[i] == target:
            return i
    return None


def column_count(lines: list[str], start: int, end: int) -> int | None:
    """라벨 뒤에 이어지는 값 토큰 개수 중 가장 흔한 값 = 표의 열 수."""
    runs: Counter = Counter()
    i = start
    while i < end and sum(runs.values()) < 15:
        if not is_value(lines[i]) and not is_noise(lines[i]):
            j = i + 1
            while j < end and is_value(lines[j]):
                j += 1
            if j - i - 1 > 0:
                runs[j - i - 1] += 1
            i = j
        else:
            i += 1
    return runs.most_common(1)[0][0] if runs else None


def scan_rows(lines: list[str], start: int, end: int, n: int, *, markers: set[str] | frozenset = frozenset(),
              join_wrapped: bool = True) -> list[tuple[str | None, str, list]]:
    """start~end에서 "라벨(여러 줄 가능) + 값 n개" 행을 모두 읽는다. markers의 줄은 구간 표시(카테고리)로 기억.
    반환: [(marker, label, [값…])]"""
    rows, parts, marker = [], [], None
    i = start
    end = min(end, len(lines))
    while i < end:
        line = lines[i]
        if line in markers:
            marker, parts = line, []
            i += 1
            continue
        if is_noise(line):
            parts = []
            i += 1
            continue
        if is_value(line):
            if parts and i + n <= end and all(is_value(lines[k]) for k in range(i, i + n)):
                label = "".join(parts) if join_wrapped else parts[-1]
                rows.append((marker, label, [to_value(lines[k]) for k in range(i, i + n)]))
                parts = []
                i += n
                continue
            parts = []
            i += 1
            continue
        parts = (parts + [line])[-3:]
        i += 1
    return rows


def assign_years(header_years: list[str], n: int) -> list[str | None]:
    """n개 열에 연도를 붙인다. 머리글 연도가 적으면 오른쪽(최근 열)부터 맞춘다."""
    years: list[str | None] = [None] * n
    for k, y in enumerate(reversed(header_years[-n:])):
        years[n - 1 - k] = y
    return years


def build_table(rows: list[tuple[str | None, str, list]], years: list[str | None]) -> dict[str, YearlyValues]:
    """행 목록 → {라벨: {연도: 값}}. 연도 없는 열은 값이 전부 비어 있으면 버리고, 아니면 연도미상N."""
    names: list[str | None] = []
    unknown = 0
    for k, y in enumerate(years):
        if y is not None:
            names.append(y)
        elif any(r[2][k] is not None for r in rows):
            unknown += 1
            names.append(f"연도미상{unknown}")
        else:
            names.append(None)
    # 같은 계정명이 여러 번 나온다(예: 건물·기계장치 아래 각각 "(감가상각누계액)"). 덮어쓰지 않도록
    # 반복되는 이름에는 바로 위 상위 계정(괄호로 시작하지 않는 직전 행)을 붙여 구분한다.
    table: dict[str, YearlyValues] = {}
    parent = None
    for _, label, values in rows:
        key = label
        if key in table:
            key = f"{parent} · {label}" if parent else label
            n = 2
            while key in table:
                key = f"{label} ({n})"
                n += 1
        table[key] = {name: v for name, v in zip(names, values) if name is not None}
        if not label.startswith("("):
            parent = label.replace("(*)", "")
    return table


def years_in(lines: list[str], start: int, end: int) -> list[str]:
    """구간 안의 첫 "구분/계정명 + 연도들" 머리글에서 연도 목록을 읽는다(날짜·연도 모두)."""
    for i in range(start, min(end, len(lines))):
        if lines[i] in ("구분", "계정명") or lines[i] in ("성장성", "수익성", "안정성", "활동성"):
            ys = []
            j = i + 1
            while j < len(lines) and year_of(lines[j]):
                ys.append(year_of(lines[j]))
                j += 1
            if ys:
                return ys
    return []


def label_values(lines: list[str], start: int, end: int, labels: list[str]) -> dict[str, str | None]:
    """"라벨 → 값" 줄. 값이 비어 있으면 다음 줄이 바로 다른 라벨이므로 None."""
    label_set = set(labels)
    out: dict[str, str | None] = {}
    for i in range(start, min(end, len(lines))):
        if lines[i] in label_set and lines[i] not in out:
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            out[lines[i]] = None if (nxt is None or nxt in label_set) else nxt
    return out


# ---------------------------------------------------------------------------
# 영역별 파서
# ---------------------------------------------------------------------------
def parse_ledger(lines: list[str], idx: int, end: int) -> tuple[dict[str, YearlyValues], dict[str, str]]:
    """상세 재무제표 1개(단위:천원). 반환: (계정표, {연도: 감사의견})."""
    i = idx + 1
    dates: list[str] = []
    opinions: list[str] = []
    while i < end and (is_noise(lines[i]) or lines[i] == "계정명"):
        if DATE_RE.match(lines[i]):
            dates.append(year_of(lines[i]))
        elif OPINION_RE.match(lines[i]):
            opinions.append(lines[i])
        elif lines[i] == "조회된자료가없습니다.":
            return {}, {}
        i += 1
    n = column_count(lines, i, end) or len(dates)
    if not n:
        return {}, {}
    rows = scan_rows(lines, i, end, n, join_wrapped=False)
    years = assign_years(dates, n)
    table = build_table(rows, years)
    known_years = [y for y in years if y]
    audit = dict(zip(known_years[-len(opinions):], opinions)) if opinions else {}
    return table, audit


def parse_summary(lines: list[str], idx: int, end: int, fallback_years: list[str]) -> dict[str, YearlyValues]:
    """요약 재무표(요약재무상태표·요약손익계산서·요약재무비율·요약현금흐름분석, MY 재무Data).
    연도 머리글이 값 뒤에 나오므로 구간 끝 이후 몇 줄까지 찾는다. 없으면 상세 재무제표 연도를 쓴다."""
    n = column_count(lines, idx + 1, end)
    if not n:
        return {}
    header = years_in(lines, idx + 1, end + 8)
    years = assign_years(header or fallback_years, n)
    rows = scan_rows(lines, idx + 1, end, n, markers={"성장성", "수익성", "안정성", "활동성"})
    return build_table(rows, years)


def parse_ratio_detail(lines: list[str], idx: int, end: int) -> dict[str, dict[str, YearlyValues]]:
    header = years_in(lines, idx + 1, end)
    n = column_count(lines, idx + 1, end) or len(header)
    if not n:
        return {}
    rows = scan_rows(lines, idx + 1, end, n, markers={"성장성", "수익성", "안정성", "활동성", "생산성"}, join_wrapped=False)
    years = assign_years(header, n)
    out: dict[str, dict[str, YearlyValues]] = {}
    for marker, label, values in rows:
        if marker:
            out.setdefault(marker, {}).update(build_table([(marker, label, values)], years))
    return out


DIAGNOSIS_AXIS_NAMES = {"growth": "성장성", "profitability": "수익성", "financial_structure": "재무구조",
                        "debt_repayment": "부채상환능력", "activity": "활동성"}


def parse_diagnosis_details(lines: list[str]) -> dict[str, dict]:
    """재무진단 5축 상세 페이지: 축마다 지표 3개의 [업종평균, 전년대비(▲증가/▼감소), 조회기업] + 3개년 추이.
    반환: {axis_key: {"base_date", "summary", "indicators": [{name, industry_avg, yoy, company, history}]}}"""
    starts = []
    for i in range(len(lines) - 1):
        if lines[i] in DIAGNOSIS_AXIS_NAMES.values() and lines[i + 1].replace(" ", "").startswith("기준일자:"):
            starts.append(i)
    out: dict[str, dict] = {}
    for n, s in enumerate(starts):
        e = starts[n + 1] if n + 1 < len(starts) else min(len(lines), s + 60)
        key = next(k for k, v in DIAGNOSIS_AXIS_NAMES.items() if v == lines[s])
        rows = scan_rows(lines, s + 2, e, 3)
        half = len(rows) // 2
        compare, history = rows[:half], rows[half:]
        years = assign_years(years_in(lines, s + 2, e), 3)
        # 요약 문장: "성장역량은양호함" 또는 "성장역량은보통이하임"
        summary = next((l for l in lines[s + 2:e] if re.search(r"(은|는)\S+(함|임)$", l) and not is_value(l)), None)
        indicators = []
        for (_, name, (avg, yoy, company)), (_, _, hist) in zip(compare, history):
            indicators.append({
                "name": name, "industry_avg": avg, "yoy": yoy, "company": company,
                "history": {y: v for y, v in zip(years, hist) if y},
            })
        out[key] = {"base_date": lines[s + 1].split(":", 1)[1].strip(), "summary": summary, "indicators": indicators}
    return out


_RANK_RE = re.compile(r"^(\d+)위$")
_MONTH_RE = re.compile(r"^\d{1,2}월$")
_BN_RE = re.compile(r"^\d{3}-\d{2}-\d{5}$")


def parse_rank_rows(lines: list[str], start: int, end: int) -> list[dict]:
    """[순위, 기업명(줄바꿈 가능), 매출액, 결산월, 사업자번호, 대표자명] 행들."""
    rows = []
    i = start
    while i < end:
        m = _RANK_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        name_parts = []
        while j < end and not NUM_RE.match(lines[j]) and not _RANK_RE.match(lines[j]) and len(name_parts) < 3:
            name_parts.append(lines[j])
            j += 1
        if j >= end or not NUM_RE.match(lines[j]):
            i += 1
            continue
        revenue = to_value(lines[j])
        k = j + 1
        month = lines[k] if k < end and _MONTH_RE.match(lines[k]) else None
        k += 1 if month else 0
        bn = lines[k] if k < end and _BN_RE.match(lines[k]) else None
        k += 1 if bn else 0
        rep = None
        if k < end and not _RANK_RE.match(lines[k]) and not is_noise(lines[k]) and not lines[k].startswith("동종업계"):
            rep = lines[k]
            k += 1
        rows.append({"rank": int(m.group(1)), "company_name": "".join(name_parts), "revenue": revenue,
                     "settlement_month": month, "business_no": bn, "representative": rep})
        i = k
    return rows


def base_year_after(lines: list[str], idx: int, span: int = 6) -> str | None:
    for l in lines[idx: idx + span]:
        m = re.match(r"^기준년도:\s*(\d{4})", l)
        if m:
            return m.group(1)
    return None


def parse_partner_rows(lines: list[str], start: int, end: int) -> list[dict]:
    """구매처/판매처 현황: [기업명, 사업자번호, 대표자명, 거래비중, (결산년도, 자본금, 자산총계, 매출액, 순이익)].
    "기타 | 78.69"처럼 사업자번호 없는 합계 행도 남긴다."""
    header_end = find_line(lines, "순이익", start, end)
    i = (header_end + 1) if header_end is not None else start
    rows = []
    name_parts: list[str] = []
    while i < end:
        line = lines[i]
        if is_noise(line):
            i += 1
            continue
        if _BN_RE.match(line):
            row = {"company_name": "".join(name_parts), "business_no": line, "representative": None,
                   "share_pct": None, "fiscal_year": None, "capital": None, "total_assets": None,
                   "revenue": None, "net_income": None}
            k = i + 1
            if k < end and not is_value(lines[k]):
                row["representative"] = lines[k]
                k += 1
            if k < end and is_value(lines[k]):
                row["share_pct"] = to_value(lines[k])
                k += 1
            if k + 4 < end and year_of(lines[k]) and all(is_value(lines[x]) for x in range(k + 1, k + 5)):
                row["fiscal_year"] = year_of(lines[k])
                row["capital"], row["total_assets"], row["revenue"], row["net_income"] = \
                    [to_value(lines[x]) for x in range(k + 1, k + 5)]
                k += 5
            rows.append(row)
            name_parts = []
            i = k
            continue
        if line == "기타" and i + 1 < end and is_value(lines[i + 1]):
            rows.append({"company_name": "기타", "business_no": None, "representative": None,
                         "share_pct": to_value(lines[i + 1]), "fiscal_year": None, "capital": None,
                         "total_assets": None, "revenue": None, "net_income": None})
            name_parts = []
            i += 2
            continue
        if not is_value(line):
            name_parts = (name_parts + [line])[-2:]
        i += 1
    return rows


_HISTORY_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def parse_history(lines: list[str], start: int, end: int) -> list[dict]:
    """연혁: [날짜(YYYY-MM 또는 YYYY-MM-DD), 내용(여러 줄 가능)]."""
    items: list[dict] = []
    for line in lines[start:end]:
        if line in ("연혁일자", "내용") or _FURNITURE_RE.match(line):
            continue
        if _HISTORY_DATE_RE.match(line):
            items.append({"date": line, "content": ""})
        elif items:
            items[-1]["content"] += line
    return items


BASIC_INFO_EXTRA_LABELS = [
    "영문기업명", "법인(주민)번호", "종업원수", "설립형태", "전화번호", "팩스번호", "홈페이지", "이메일", "결산월",
    "기업공개일자", "표준산업분류(10차)", "주요제품(상품)", "무역업허가번호", "소속그룹", "주채권기관", "당좌거래은행",
    "휴폐업정보", "법인등기정보",
]
_BASIC_ALL_LABELS = BASIC_INFO_EXTRA_LABELS + [
    "기업명", "사업자번호", "대표자명", "설립년월", "기업유형", "기업규모", "주소", "표준산업분류(11차)", "기업개요",
]


def parse_basic_extra(lines: list[str]) -> dict[str, str | None]:
    """2페이지(기본정보) 추가 항목. 휴폐업·법인등기정보는 "(조회일자:…)"까지 붙인다."""
    vals = label_values(lines, 0, len(lines), _BASIC_ALL_LABELS)
    out = {k: vals.get(k) for k in BASIC_INFO_EXTRA_LABELS if k in vals}
    for key in ("휴폐업정보", "법인등기정보"):
        i = find_line(lines, key)
        if i is not None and i + 2 < len(lines) and lines[i + 2].startswith("(조회일자"):
            out[key] = f"{lines[i + 1]} {lines[i + 2]}"
    for line in lines:
        if line.startswith("등급산출일:"):
            out["등급산출일"] = line.split(":", 1)[1]
    i = find_line(lines, "연계기업")
    if i is not None and i + 1 < len(lines):
        out["연계기업"] = lines[i + 1]
    # 기업관계망: "EW등급 | 정상 | ?건 | 유보~부도 | ?건 | 휴폐업/ | 청산해산 | ?건" (건수 비공개면 "?건")
    i = find_line(lines, "기업관계망")
    if i is not None:
        seg = lines[i:i + 40]
        counts = [(n, l) for n, l in enumerate(seg) if re.fullmatch(r"[\d?]+건", l)]
        labels_seen = []
        for n, l in counts:
            name_parts = []
            k = n - 1
            while k >= 0 and not re.fullmatch(r"[\d?]+건", seg[k]) and seg[k] not in ("EW등급",) and len(name_parts) < 2:
                name_parts.insert(0, seg[k])
                k -= 1
            labels_seen.append(("".join(name_parts), l))
        for name, cnt in labels_seen:
            if name in ("정상", "유보~부도", "휴폐업/청산해산"):  # 관계망 연계기업의 EW 상태별 건수
                out[f"기업관계망({name})"] = cnt
    return out


PERSONAL_LABELS = ["성명/직위", "생년월일/성별", "거주지", "주소지", "상훈", "경영실권자와의관계", "출신학교", "자격증"]


def parse_personal(lines: list[str], start: int, end: int) -> dict[str, str | None]:
    return label_values(lines, start, end, PERSONAL_LABELS + ["주요경력사항"])


def parse_bid_summary(lines: list[str]) -> dict[str, str | None]:
    """나라장터입찰정보요약: 입찰건수 · 낙찰건수 · 총낙찰금액(백만원), 최근 1년."""
    i = find_line(lines, "나라장터입찰정보요약")
    if i is None:
        return {}
    seg = lines[i + 1:i + 12]
    counts = [l for l in seg if re.fullmatch(r"[\d,]+건|-", l)]
    out: dict[str, str | None] = {}
    if len(counts) >= 2:
        out["입찰건수"], out["낙찰건수"] = counts[0], counts[1]
    j = find_line(seg, "총낙찰금액")
    if j is not None and j + 1 < len(seg):
        out["총낙찰금액(백만원)"] = None if seg[j + 1] == "-" else seg[j + 1]
    out["집계기준"] = "최근 1년" if "최근1년기준집계" in seg else None
    return out


def parse_tech(lines: list[str]) -> dict[str, str | None]:
    """기술력: "기술력 | 기업인증・산업재산권현황 | 양호 | 평가기준연도:2025" 또는 "평가기준연도정보없음"."""
    i = find_line(lines, "기술력")
    if i is None:
        return {}
    seg = lines[i + 1:i + 5]
    year = next((l.split(":", 1)[1] for l in seg if l.startswith("평가기준연도:")), None)
    grade = next((l for l in seg if l not in ("기업인증・산업재산권현황",) and not l.startswith("평가기준연도")
                  and l != "기업인증"), None)
    return {"기술력등급": grade if year else None, "평가기준연도": year}
