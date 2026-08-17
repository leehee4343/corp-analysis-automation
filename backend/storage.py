"""회사별 JSON 저장/조회 및 검증 이슈 판정.

data/{사업자번호}.json 한 파일에 회사 하나의 최신 파싱 결과를 저장한다 (사업자번호는
안정적인 고유키라 파일명으로 씀 — 회사명은 특수문자/중복 가능성이 있어 부적합).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import Company, DiagnosisRatings, IndustryRank, ValidationIssue
from .parser.grade_ocr import GradeResult
from .parser.pdf_parser import ParsedCompany

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

_FIELD_LABELS_KO = {
    "business_no": "사업자번호",
    "company_name": "기업명",
    "representative": "대표자명",
    "address": "주소",
    "financials": "재무제표 요약",
}


def _path_for(business_no: str) -> Path:
    return DATA_DIR / f"{business_no}.json"


def _build_issues(parsed: ParsedCompany) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

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
    return Company(
        business_no=parsed.business_no or "",
        company_name=parsed.company_name or "",
        representative=parsed.representative,
        address=parsed.address,
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
        parsed_at=datetime.now(timezone.utc),
        issues=_build_issues(parsed),
    )


def save_company(company: Company) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(company.business_no)
    path.write_text(company.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_company(business_no: str) -> Company | None:
    path = _path_for(business_no)
    if not path.exists():
        return None
    return Company.model_validate_json(path.read_text(encoding="utf-8"))


def list_companies() -> list[Company]:
    if not DATA_DIR.exists():
        return []
    return [
        Company.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(DATA_DIR.glob("*.json"))
    ]


def list_issues() -> list[tuple[Company, ValidationIssue]]:
    return [(company, issue) for company in list_companies() for issue in company.issues]
