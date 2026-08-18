"""회사별 데이터 저장/조회 및 검증 이슈 판정.

SQLite 한 파일(`paths.DB_PATH`)의 companies 테이블에 회사 하나당 행 하나로 저장한다
(사업자번호가 안정적인 고유키). `data` 컬럼에 Company 전체를 JSON으로 저장하고,
company_name/industry_name/credit_grade/status/parsed_at은 DB Browser 등으로 직접
열어봐도 바로 보이도록 중복 저장하는 조회용 컬럼이다 — 필터링/정렬 자체는 여전히
호출 측(라우터)에서 파이썬으로 한다.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .models import Company, CompanyListItem, CompanyUpdate, DiagnosisRatings, IndustryRank, ValidationIssue
from .parser.grade_ocr import GradeResult
from .parser.pdf_parser import ParsedCompany
from .paths import DB_PATH

_FIELD_LABELS_KO = {
    "business_no": "사업자번호",
    "company_name": "기업명",
    "representative": "대표자명",
    "address": "주소",
    "financials": "재무제표 요약",
}


def _get_conn() -> sqlite3.Connection:
    # DB_PATH를 함수 안에서 읽어야 테스트의 monkeypatch(storage.DB_PATH)가 반영된다 —
    # 모듈 임포트 시점에 값을 미리 캡처해두면 갱신되지 않는다(admin.py에서 겪은 버그와 동일 유형).
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            business_no TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            industry_name TEXT,
            credit_grade TEXT,
            status TEXT NOT NULL,
            parsed_at TEXT NOT NULL,
            data TEXT NOT NULL
        )
    """)
    return conn


def _build_issues(parsed: ParsedCompany, grades: GradeResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for error in parsed.parse_errors:
        issues.append(ValidationIssue(
            type="missing_field", field=None,
            message=f"일부 항목 파싱 중 오류가 발생해 건너뛰었습니다 ({error}). 원본 PDF에서 직접 확인하세요.",
        ))

    for key in parsed.missing_fields:
        label = _FIELD_LABELS_KO.get(key, key)
        issues.append(ValidationIssue(
            type="missing_field", field=key, message=f"'{label}' 값을 찾지 못했습니다."
        ))

    for key in parsed.cross_check_mismatch:
        label = _FIELD_LABELS_KO.get(key, key)
        issues.append(ValidationIssue(
            type="format_suspect", field=key,
            message=f"표지와 상세 페이지의 '{label}' 값이 서로 다릅니다.",
        ))

    if parsed.representative and any(ch.isdigit() for ch in parsed.representative):
        issues.append(ValidationIssue(
            type="format_suspect", field="representative",
            message="'대표자명' 필드에 숫자가 포함되어 있습니다. OCR 오인식 가능성이 있습니다.",
        ))

    if not parsed.balance_summary or not parsed.income_summary:
        issues.append(ValidationIssue(
            type="missing_field", field="financials",
            message="재무상태표/손익계산서 요약 값을 찾지 못했습니다. 표 구조를 확인하세요.",
        ))

    if not grades.credit_grade:
        issues.append(ValidationIssue(
            type="missing_field", field="credit_grade",
            message="기업신용등급 값을 인식하지 못했습니다 (게이지 이미지 OCR 실패 가능성). 원본 PDF에서 확인하세요.",
        ))

    if parsed.business_no:
        existing = load_company(parsed.business_no)
        if (
            existing
            and existing.report_query_datetime
            and parsed.report_query_datetime
            and existing.report_query_datetime != parsed.report_query_datetime
        ):
            issues.append(ValidationIssue(
                type="duplicate_suspect", field=None,
                message=(
                    f"동일 사업자번호로 {existing.report_query_datetime} 보고서가 이미 등록되어 "
                    "있습니다. 최신본으로 교체하시겠습니까?"
                ),
            ))

    return issues


def build_company(parsed: ParsedCompany, grades: GradeResult | None = None) -> Company:
    grades = grades or GradeResult()
    issues = _build_issues(parsed, grades)
    return Company(
        business_no=parsed.business_no or "",
        company_name=parsed.company_name or "",
        representative=parsed.representative,
        address=parsed.address,
        postal_code=parsed.postal_code,
        founded_date=parsed.founded_date,
        industry_code=parsed.industry_code,
        industry_name=parsed.industry_name,
        company_type=parsed.company_type,
        company_size=parsed.company_size,
        credit_grade=grades.credit_grade,
        ew_grade=grades.ew_grade,
        growth_grade=grades.growth_grade,
        balance_summary=parsed.balance_summary,
        income_summary=parsed.income_summary,
        ratio_summary=parsed.ratio_summary,
        diagnosis=DiagnosisRatings(**parsed.diagnosis),
        industry_rank=IndustryRank(**parsed.industry_rank),
        peer_comparison=parsed.peer_comparison,
        report_query_datetime=parsed.report_query_datetime,
        evaluation_date=parsed.evaluation_date,
        settlement_date=parsed.settlement_date,
        source_pdf=parsed.source_pdf,
        page_count=parsed.page_count,
        credit_info=parsed.credit_info,
        certifications=parsed.certifications,
        ip_rights=parsed.ip_rights,
        relationship_existence=parsed.relationship_existence,
        ledger_detail=parsed.ledger_detail,
        ratio_detail=parsed.ratio_detail,
        diagnosis_commentary=parsed.diagnosis_commentary,
        personal_info=parsed.personal_info,
        soft_sections=parsed.soft_sections,
        parsed_at=datetime.now(timezone.utc),
        issues=issues,
    )


def save_company(company: Company) -> None:
    conn = _get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO companies (business_no, company_name, industry_name, credit_grade, status, parsed_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_no) DO UPDATE SET
                company_name=excluded.company_name,
                industry_name=excluded.industry_name,
                credit_grade=excluded.credit_grade,
                status=excluded.status,
                parsed_at=excluded.parsed_at,
                data=excluded.data
            """,
            (
                company.business_no,
                company.company_name,
                company.industry_name,
                company.credit_grade,
                company.status,
                company.parsed_at.isoformat(),
                company.model_dump_json(),
            ),
        )
    conn.close()


def load_company(business_no: str) -> Company | None:
    conn = _get_conn()
    row = conn.execute("SELECT data FROM companies WHERE business_no = ?", (business_no,)).fetchone()
    conn.close()
    if row is None:
        return None
    return Company.model_validate_json(row[0])


def list_companies() -> list[Company]:
    conn = _get_conn()
    rows = conn.execute("SELECT data FROM companies ORDER BY business_no").fetchall()
    conn.close()
    return [Company.model_validate_json(row[0]) for row in rows]


def list_issues() -> list[tuple[Company, ValidationIssue]]:
    return [(company, issue) for company in list_companies() for issue in company.issues]


def update_company(business_no: str, update: CompanyUpdate) -> Company | None:
    """검증 대기열의 "직접 수정" — 수정한 필드와 관련된 이슈는 해결된 것으로 보고 제거한다."""
    company = load_company(business_no)
    if company is None:
        return None
    changed_fields = update.model_dump(exclude_unset=True)
    for key, value in changed_fields.items():
        setattr(company, key, value)
    company.issues = [i for i in company.issues if i.field not in changed_fields]
    save_company(company)
    return company


def latest_value(company: Company, field: str, table: str = "income_summary") -> float | None:
    series = getattr(company, table).get(field, {})
    if not series:
        return None
    latest_year = max(series)
    return series[latest_year]


def latest_revenue(company: Company) -> float | None:
    return latest_value(company, "매출액")


def to_list_item(company: Company) -> CompanyListItem:
    """기업목록/영업 대상 분류 화면이 공통으로 쓰는 요약 행. 두 화면이 완전히 동일한
    항목 구성을 쓰기로 해서 여기 한 곳에서만 정의한다."""
    return CompanyListItem(
        business_no=company.business_no,
        company_name=company.company_name,
        industry_name=company.industry_name,
        credit_grade=company.credit_grade,
        status=company.status,
        revenue_latest=latest_revenue(company),
        operating_profit_latest=latest_value(company, "영업이익"),
        parsed_at=company.parsed_at,
    )


def filter_companies(
    companies: list[Company],
    *,
    q: str | None = None,
    industry: str | None = None,
    grade_band_filter: str | None = None,
    revenue_min: float | None = None,
    revenue_max: float | None = None,
) -> list[Company]:
    """기업목록/영업 대상 분류 화면이 공통으로 쓰는 검색·필터 로직."""
    if q:
        needle = q.strip()
        companies = [c for c in companies if needle in c.company_name or needle in c.business_no]
    if industry:
        companies = [c for c in companies if c.industry_name == industry]
    if grade_band_filter:
        companies = [c for c in companies if grade_band(c.credit_grade) == grade_band_filter]
    if revenue_min is not None:
        companies = [c for c in companies if (latest_revenue(c) or 0) >= revenue_min]
    if revenue_max is not None:
        companies = [c for c in companies if (latest_revenue(c) or 0) < revenue_max]
    return companies


def grade_band(credit_grade: str | None) -> str:
    """대시보드 신용등급 분포용 구간 — 목업 도넛 범례(A~BBB/BB/B/CCC 이하)와 동일."""
    if not credit_grade:
        return "미평가"
    g = credit_grade.lower()
    if g.startswith("a") or g.startswith("bbb"):
        return "A~BBB"
    if g.startswith("bb"):
        return "BB"
    if g.startswith("b"):
        return "B"
    return "CCC 이하"
