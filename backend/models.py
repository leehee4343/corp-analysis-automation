"""회사 데이터 저장 스키마. backend/parser의 파싱 결과(dataclass)를 저장용 pydantic
모델로 변환한다 — 파서는 PDF 구조에 종속적이고, 이 모델은 API/프론트엔드가 보는
안정된 계약이라 분리한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

YearlyValues = dict[str, float | None]


class DiagnosisRatings(BaseModel):
    growth: str | None = None
    profitability: str | None = None
    financial_structure: str | None = None
    debt_repayment: str | None = None
    activity: str | None = None


class IndustryRank(BaseModel):
    rank: int | None = None
    sample_size: int | None = None


class ValidationIssue(BaseModel):
    type: Literal["missing_field", "format_suspect", "duplicate_suspect"]
    field: str | None = None
    message: str


class Company(BaseModel):
    business_no: str
    company_name: str
    representative: str | None = None
    address: str | None = None
    postal_code: str | None = None
    founded_date: str | None = None
    industry_code: str | None = None
    industry_name: str | None = None
    company_type: str | None = None
    company_size: str | None = None

    credit_grade: str | None = None
    ew_grade: str | None = None
    growth_grade: str | None = None

    balance_summary: dict[str, YearlyValues] = Field(default_factory=dict)
    income_summary: dict[str, YearlyValues] = Field(default_factory=dict)
    ratio_summary: dict[str, YearlyValues] = Field(default_factory=dict)
    diagnosis: DiagnosisRatings = Field(default_factory=DiagnosisRatings)
    industry_rank: IndustryRank = Field(default_factory=IndustryRank)
    peer_comparison: dict[str, YearlyValues] = Field(default_factory=dict)

    report_query_datetime: str | None = None
    evaluation_date: str | None = None
    settlement_date: str | None = None
    source_pdf: str | None = None
    page_count: int = 0

    # ===== PDF 전체 추출 (사용자 요청, PLAN.md 참고) =====
    credit_info: dict[str, str | None] = Field(default_factory=dict)
    certifications: dict[str, str] = Field(default_factory=dict)
    ip_rights: dict[str, str] = Field(default_factory=dict)
    relationship_existence: dict[str, str] = Field(default_factory=dict)
    ledger_detail: dict[str, dict[str, YearlyValues]] = Field(default_factory=dict)
    """재무상태표/손익계산서/현금흐름표/자본변동표/이익잉여금처분계산서/제조원가명세서 전체
    계정과목. 표 이름(예: "재무상태표") -> {계정명: {연도: 값}}."""
    ratio_detail: dict[str, dict[str, YearlyValues]] = Field(default_factory=dict)
    """성장성/수익성/안정성/활동성/생산성 카테고리 -> {비율명: {연도: 값}}."""
    diagnosis_commentary: str | None = None
    personal_info: dict[str, str] = Field(default_factory=dict)
    soft_sections: dict[str, str | None] = Field(default_factory=dict)
    """연혁/사업목적/종합의견/경영진현황/주식소유현황/주요주주현황/관계회사현황/사업장현황/
    구매처현황/판매처현황/매출구성 — 완전한 표 구조화 대신 원문 텍스트로 보존(데이터
    없으면 None)."""

    parsed_at: datetime
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def status(self) -> Literal["complete", "needs_review"]:
        return "needs_review" if self.issues else "complete"


class CompanyUpdate(BaseModel):
    """PATCH /companies/{business_no} — 검증 대기열에서 수동 수정할 때 쓰는 부분 업데이트."""
    company_name: str | None = None
    representative: str | None = None
    address: str | None = None
    postal_code: str | None = None
    founded_date: str | None = None
    industry_name: str | None = None
    company_type: str | None = None
    company_size: str | None = None
    credit_grade: str | None = None
    ew_grade: str | None = None
    growth_grade: str | None = None


class CompanyListItem(BaseModel):
    business_no: str
    company_name: str
    industry_name: str | None = None
    credit_grade: str | None = None
    status: Literal["complete", "needs_review"]
    revenue_latest: float | None = None
    operating_profit_latest: float | None = None
    diagnosis_summary: str | None = None
    parsed_at: datetime


class CompanyList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CompanyListItem]


class CategoryListItem(BaseModel):
    """법인형태별 분류(개인사업자/일반법인/농업회사법인/영농조합법인) 목록 한 건 —
    전부 PDF로 분석되어 DB에 저장된 회사이므로(외부 참고자료 없음) 항상 실제 파싱
    데이터를 담는다."""
    no: int
    business_no: str
    company_name: str
    representative: str | None = None
    address: str | None = None
    industry_name: str | None = None
    credit_grade: str | None = None
    revenue_latest: float | None = None
    diagnosis_summary: str | None = None
    parsed_at: datetime


class CategoryList(BaseModel):
    category: str
    label: str
    total: int
    page: int
    page_size: int
    items: list[CategoryListItem]


class MailingListEntry(BaseModel):
    no: int
    business_no: str
    postal_code: str | None = None
    address: str | None = None
    company_name: str
    representative: str | None = None


class IssueEntry(BaseModel):
    business_no: str
    company_name: str
    issue: ValidationIssue


class DashboardSummary(BaseModel):
    total_companies: int
    parsing_success_rate: float
    pending_issues: int
    by_industry: dict[str, int]
    by_credit_grade_band: dict[str, int]
    recent: list[CompanyListItem]
