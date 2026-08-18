"""회사별 JSON 저장/조회 및 검증 이슈 판정.

data/{사업자번호}.json 한 파일에 회사 하나의 최신 파싱 결과를 저장한다 (사업자번호는
안정적인 고유키라 파일명으로 씀 — 회사명은 특수문자/중복 가능성이 있어 부적합).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import Company, CompanyUpdate, DiagnosisRatings, IndustryRank, ValidationIssue
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


_DIAGNOSIS_RANK = {"취약": 0, "미흡": 1, "보통": 2, "양호": 3, "우수": 4}


def overall_diagnosis(company: Company) -> str | None:
    """목록에 한 단어로 보여줄 대표 재무진단 — 5축 중 가장 낮은 등급(약점)을 보여준다."""
    ratings = [v for v in company.diagnosis.model_dump().values() if v]
    if not ratings:
        return None
    return min(ratings, key=lambda r: _DIAGNOSIS_RANK.get(r, 2))


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
