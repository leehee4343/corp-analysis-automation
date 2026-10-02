"""Company 데이터를 엑셀 기업종합보고서로 변환한다 (openpyxl).

outputs/{기업명}_기업종합보고서.xlsx 로 저장 (목업 로그 문구와 동일한 파일명 규칙 —
다운로드용 파일명이라 사업자번호 대신 회사명을 써도 무방, backend/storage.py의
data/{사업자번호}.json 저장 키와는 별개).
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from ..models import Company
from ..paths import OUTPUT_DIR

_TITLE_FONT = Font(size=16, bold=True)
_SECTION_FONT = Font(size=12, bold=True, color="FFFFFF")
_SECTION_FILL = PatternFill("solid", fgColor="1741A6")
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill("solid", fgColor="E6EEFD")
_LABEL_FONT = Font(bold=True)

_YEARS = ("2023", "2024", "2025")


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "기업"


def _section_title(ws: Worksheet, row: int, text: str, span: int = 5) -> int:
    ws.cell(row=row, column=1, value=text).font = _SECTION_FONT
    for col in range(1, span + 1):
        ws.cell(row=row, column=col).fill = _SECTION_FILL
    return row + 1


def _kv_row(ws: Worksheet, row: int, label: str, value) -> int:
    ws.cell(row=row, column=1, value=label).font = _LABEL_FONT
    ws.cell(row=row, column=2, value=value if value is not None else "-")
    return row + 1


def _years_of(rows: dict[str, dict]) -> list[str]:
    """표의 실제 연도 열(표마다 다름: 2022~2024, 2019~2021 등). 숫자 연도 오름차순, 그 외(연도미상)는 뒤."""
    keys = {k for values in rows.values() for k in values}
    return sorted(k for k in keys if k.isdigit()) + sorted(k for k in keys if not k.isdigit())


def _yearly_table(ws: Worksheet, row: int, rows: dict[str, dict[str, float | str | None]]) -> int:
    years = _years_of(rows) or list(_YEARS)
    ws.cell(row=row, column=1, value="구분").font = _HEADER_FONT
    for i, year in enumerate(years, start=2):
        cell = ws.cell(row=row, column=i, value=year)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
    row += 1
    for label, values in rows.items():
        ws.cell(row=row, column=1, value=label).font = _LABEL_FONT
        for i, year in enumerate(years, start=2):
            ws.cell(row=row, column=i, value=values.get(year))
        row += 1
    return row + 1


def _list_table(ws: Worksheet, row: int, headers: list[str], keys: list[str], items: list[dict]) -> int:
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=i, value=h)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
    row += 1
    for item in items:
        for i, k in enumerate(keys, start=1):
            ws.cell(row=row, column=i, value=item.get(k))
        row += 1
    return row + 1


def _build_summary_sheet(ws: Worksheet, company: Company) -> None:
    ws.column_dimensions["A"].width = 20
    for col in "BCDE":
        ws.column_dimensions[col].width = 16

    ws.cell(row=1, column=1, value=f"기업종합보고서 — {company.company_name}").font = _TITLE_FONT
    row = 3

    row = _section_title(ws, row, "기본정보")
    for label, value in [
        ("기업명", company.company_name),
        ("사업자번호", company.business_no),
        ("대표자명", company.representative),
        ("주소", company.address),
        ("설립년월", company.founded_date),
        ("업종", company.industry_name),
        ("기업유형", company.company_type),
        ("기업규모", company.company_size),
    ]:
        row = _kv_row(ws, row, label, value)
    row += 1

    row = _section_title(ws, row, "등급")
    for label, value in [
        ("기업신용등급", company.credit_grade),
        ("EW등급", company.ew_grade),
        ("기업성장등급", company.growth_grade),
    ]:
        row = _kv_row(ws, row, label, value)
    row += 1

    row = _section_title(ws, row, "재무진단 (5축)")
    diag = company.diagnosis
    for label, value in [
        ("성장성", diag.growth),
        ("수익성", diag.profitability),
        ("재무구조", diag.financial_structure),
        ("부채상환능력", diag.debt_repayment),
        ("활동성", diag.activity),
    ]:
        row = _kv_row(ws, row, label, value)
    row += 1

    row = _section_title(ws, row, "업계 비교")
    row = _kv_row(ws, row, "업계 순위", (
        f"매출액 {company.industry_rank.rank}위 (기준년도 {company.industry_base_year or '-'})"
        if company.industry_rank.rank else "-"
    ))
    row = _kv_row(ws, row, "보고서 기준", (
        f"평가일자 {company.evaluation_date} · 결산일자 {company.settlement_date}"
        if company.evaluation_date or company.settlement_date else "-"
    ))


def _build_financials_sheet(ws: Worksheet, company: Company) -> None:
    ws.column_dimensions["A"].width = 22
    for col in "BCD":
        ws.column_dimensions[col].width = 14

    row = 1
    ws.cell(row=row, column=1, value="재무상태표 요약 (백만원)").font = _TITLE_FONT
    row += 2
    row = _yearly_table(ws, row, company.balance_summary)

    ws.cell(row=row, column=1, value="손익계산서 요약 (백만원)").font = _TITLE_FONT
    row += 2
    row = _yearly_table(ws, row, company.income_summary)

    ws.cell(row=row, column=1, value="재무비율 (%)").font = _TITLE_FONT
    row += 2
    _yearly_table(ws, row, company.ratio_summary)


def _build_industry_sheet(ws: Worksheet, company: Company) -> None:
    ws.column_dimensions["A"].width = 16
    for col in "BCDEFG":
        ws.column_dimensions[col].width = 14

    row = 1
    ws.cell(row=row, column=1, value="동종업계 내 경영규모 비교 (백만원)").font = _TITLE_FONT
    row += 2

    fields = ["총자산", "자본총계", "납입자본금", "매출액", "영업이익", "당기순이익"]
    ws.cell(row=row, column=1, value="구분").font = _HEADER_FONT
    for i, field in enumerate(fields, start=2):
        cell = ws.cell(row=row, column=i, value=field)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
    row += 1
    for row_label in ["조회기업", "상위25%", "평균", "하위25%"]:
        values = company.peer_comparison.get(row_label, {})
        ws.cell(row=row, column=1, value=row_label).font = _LABEL_FONT
        for i, field in enumerate(fields, start=2):
            ws.cell(row=row, column=i, value=values.get(field))
        row += 1


def _build_ledger_detail_sheet(ws: Worksheet, ledger_detail: dict[str, dict[str, dict[str, float | None]]]) -> None:
    """재무상태표/손익계산서/현금흐름표/자본변동표/이익잉여금처분계산서/제조원가명세서
    전체 계정과목 (단위: 천원, 요약 시트의 반올림된 백만원 단위와 다름에 유의)."""
    ws.column_dimensions["A"].width = 28
    for col in "BCD":
        ws.column_dimensions[col].width = 14
    row = 1
    for table_name, items in ledger_detail.items():
        if not items:
            continue
        ws.cell(row=row, column=1, value=f"{table_name} (천원)").font = _TITLE_FONT
        row += 2
        row = _yearly_table(ws, row, items)


def _build_ratio_detail_sheet(ws: Worksheet, ratio_detail: dict[str, dict[str, dict[str, float | None]]]) -> None:
    """성장성/수익성/안정성/활동성/생산성 카테고리별 재무비율 상세(요약 시트의 12개보다
    훨씬 많은 80~140여 개 지표)."""
    ws.column_dimensions["A"].width = 26
    for col in "BCD":
        ws.column_dimensions[col].width = 12
    row = 1
    ws.cell(row=row, column=1, value="재무비율 상세 (%)").font = _TITLE_FONT
    row += 2
    for category in ("성장성", "수익성", "안정성", "활동성", "생산성"):
        items = ratio_detail.get(category)
        if not items:
            continue
        row = _section_title(ws, row, category, span=4)
        row = _yearly_table(ws, row, items)


def _build_credit_info_sheet(ws: Worksheet, company: Company) -> None:
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 42

    row = 1
    ws.cell(row=row, column=1, value="신용정보・인증 현황").font = _TITLE_FONT
    row += 2

    row = _section_title(ws, row, "신용정보", span=2)
    for label, value in company.credit_info.items():
        row = _kv_row(ws, row, label, value)
    row += 1

    row = _section_title(ws, row, "기업인증", span=2)
    for label, value in company.certifications.items():
        row = _kv_row(ws, row, label, value)
    row += 1

    row = _section_title(ws, row, "산업재산권", span=2)
    for label, value in company.ip_rights.items():
        row = _kv_row(ws, row, label, value)


_PERSONAL_INFO_LABELS_KO = {"name_position": "성명/직위", "birth_gender": "생년월일/성별"}


def _build_other_info_sheet(ws: Worksheet, company: Company) -> None:
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 90

    row = 1
    ws.cell(row=row, column=1, value="기타 정보").font = _TITLE_FONT
    row += 2

    row = _section_title(ws, row, "대표자 인적사항", span=2)
    for key, value in company.personal_info.items():
        row = _kv_row(ws, row, _PERSONAL_INFO_LABELS_KO.get(key, key), value)
    row += 1

    if company.diagnosis_commentary:
        row = _section_title(ws, row, "재무진단 분석의견", span=2)
        cell = ws.cell(row=row, column=1, value=company.diagnosis_commentary)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = 60
        row += 2

    row = _section_title(ws, row, "주요주주 / 관계회사 / 거래처 현황", span=2)
    for label, value in company.relationship_existence.items():
        row = _kv_row(ws, row, label, value)
    row += 1

    row = _section_title(ws, row, "기타 (연혁 · 경영진현황 · 사업장현황 등)", span=2)
    for label, value in company.soft_sections.items():
        cell_row = row
        row = _kv_row(ws, row, label, value if value else "데이터 없음")
        ws.cell(row=cell_row, column=2).alignment = Alignment(wrap_text=True, vertical="top")


def _build_extended_sheet(ws: Worksheet, company: Company) -> None:
    """2026-10-02 확장 추출 항목: 기본정보 추가, 현금흐름·감사의견, MY 재무Data, 기술력·입찰."""
    ws.column_dimensions["A"].width = 26
    for col in "BCDEF":
        ws.column_dimensions[col].width = 16
    row = 1
    ws.cell(row=row, column=1, value="추가 정보").font = _TITLE_FONT
    row += 2
    row = _section_title(ws, row, "기본정보 추가 항목", span=3)
    for label, value in company.basic_extra.items():
        row = _kv_row(ws, row, label, value)
    for label, value in {**company.tech_info, **company.bid_summary}.items():
        row = _kv_row(ws, row, label, value)
    row += 1
    if company.cash_flow_summary:
        ws.cell(row=row, column=1, value=f"요약현금흐름분석 (백만원, 기준일자 {company.cash_flow_base_date or '-'})").font = _HEADER_FONT
        row = _yearly_table(ws, row + 1, company.cash_flow_summary)
    if company.my_financial_data:
        ws.cell(row=row, column=1, value="MY 재무Data (백만원)").font = _HEADER_FONT
        row = _yearly_table(ws, row + 1, company.my_financial_data)
    if company.audit_opinions:
        row = _section_title(ws, row, "감사의견", span=3)
        for table, by_year in company.audit_opinions.items():
            for year, opinion in by_year.items():
                row = _kv_row(ws, row, f"{table} {year}", opinion)


def _build_diagnosis_detail_sheet(ws: Worksheet, company: Company) -> None:
    ws.column_dimensions["A"].width = 24
    for col in "BCDEFG":
        ws.column_dimensions[col].width = 13
    row = 1
    ws.cell(row=row, column=1, value="재무진단 상세").font = _TITLE_FONT
    row += 2
    names = {"growth": "성장성", "profitability": "수익성", "financial_structure": "재무구조",
             "debt_repayment": "부채상환능력", "activity": "활동성"}
    for key, detail in company.diagnosis_details.items():
        rating = getattr(company.diagnosis, key, None) or "-"
        row = _section_title(ws, row, f"{names.get(key, key)} — {rating} (기준일자 {detail.get('base_date') or '-'})", span=7)
        years = sorted({y for ind in detail["indicators"] for y in ind["history"]})
        items = [{"name": i["name"], "industry_avg": i["industry_avg"], "yoy": i["yoy"], "company": i["company"],
                  **{f"y{y}": i["history"].get(y) for y in years}} for i in detail["indicators"]]
        row = _list_table(ws, row, ["지표", "업종평균", "전년대비", "조회기업"] + years,
                          ["name", "industry_avg", "yoy", "company"] + [f"y{y}" for y in years], items)


def _build_market_sheet(ws: Worksheet, company: Company) -> None:
    """업계순위 목록·상위 5개사, 구매처·판매처, 연혁."""
    for col, width in zip("ABCDEFGHI", (8, 30, 14, 10, 16, 12, 12, 14, 14)):
        ws.column_dimensions[col].width = width
    row = 1
    ws.cell(row=row, column=1, value="업계 · 거래처 · 연혁").font = _TITLE_FONT
    row += 2
    rank_keys = ["rank", "company_name", "revenue", "settlement_month", "business_no", "representative"]
    rank_headers = ["순위", "기업명", "매출액(백만원)", "결산월", "사업자번호", "대표자명"]
    if company.industry_rank_list:
        row = _section_title(ws, row, f"업계순위 (기준년도 {company.industry_base_year or '-'})", span=6)
        row = _list_table(ws, row, rank_headers, rank_keys, company.industry_rank_list)
    if company.industry_top5:
        row = _section_title(ws, row, "동종업계 매출액 상위 5개사", span=6)
        row = _list_table(ws, row, rank_headers, rank_keys, company.industry_top5)
    for kind, rows in company.partners.items():
        row = _section_title(ws, row, f"{kind} 현황 (백만원, %)", span=9)
        row = _list_table(ws, row,
                          ["기업명", "사업자번호", "대표자명", "거래비중(%)", "결산년도", "자본금", "자산총계", "매출액", "순이익"],
                          ["company_name", "business_no", "representative", "share_pct", "fiscal_year", "capital",
                           "total_assets", "revenue", "net_income"], rows)
    if company.history:
        row = _section_title(ws, row, "연혁", span=2)
        _list_table(ws, row, ["일자", "내용"], ["date", "content"], company.history)


def generate_excel(company: Company, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    _build_summary_sheet(wb.active, company)
    wb.active.title = "요약"
    _build_financials_sheet(wb.create_sheet("재무제표"), company)
    _build_industry_sheet(wb.create_sheet("업계비교"), company)
    if company.ledger_detail:
        _build_ledger_detail_sheet(wb.create_sheet("재무제표(상세)"), company.ledger_detail)
    if company.ratio_detail:
        _build_ratio_detail_sheet(wb.create_sheet("재무비율(상세)"), company.ratio_detail)
    _build_credit_info_sheet(wb.create_sheet("신용정보・인증"), company)
    _build_other_info_sheet(wb.create_sheet("기타정보"), company)
    _build_extended_sheet(wb.create_sheet("추가정보"), company)
    if company.diagnosis_details:
        _build_diagnosis_detail_sheet(wb.create_sheet("재무진단(상세)"), company)
    if company.industry_rank_list or company.partners or company.history:
        _build_market_sheet(wb.create_sheet("업계·거래처·연혁"), company)

    filename = f"{_sanitize_filename(company.company_name)}_기업종합보고서.xlsx"
    path = output_dir / filename
    wb.save(path)
    return path


def generate_mailing_list_excel(companies: list[Company], output_dir: Path | None = None) -> Path:
    """참고자료/우편발송용 목록(샘플).xlsx과 동일한 형식(시트명·컬럼)으로 생성한다."""
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "우편 발송용"

    headers = ["No.", "우편번호", "주소", "상호명", "대표자 성명"]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=text)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL

    for i, company in enumerate(companies, start=1):
        ws.cell(row=i + 1, column=1, value=i)
        ws.cell(row=i + 1, column=2, value=company.postal_code or "")
        ws.cell(row=i + 1, column=3, value=company.address or "")
        ws.cell(row=i + 1, column=4, value=company.company_name)
        ws.cell(row=i + 1, column=5, value=company.representative or "")

    widths = {"A": 6, "B": 10, "C": 46, "D": 30, "E": 14}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    path = output_dir / "우편발송용_목록.xlsx"
    wb.save(path)
    return path
