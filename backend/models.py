"""회사 데이터 저장 스키마. backend/parser의 파싱 결과(dataclass)를 저장용 pydantic
모델로 변환한다 — 파서는 PDF 구조에 종속적이고, 이 모델은 API/프론트엔드가 보는
안정된 계약이라 분리한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# 연도별 값. 숫자 외에 "흑자전환"·"적자전환"·"CR3"(현금흐름등급)·"▲증가" 같은 원문 문자 값도 그대로 보존한다.
YearlyValues = dict[str, float | str | None]


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
    personal_info: dict[str, str | None] = Field(default_factory=dict)
    soft_sections: dict[str, str | None] = Field(default_factory=dict)
    """연혁/사업목적/종합의견/경영진현황/주식소유현황/주요주주현황/관계회사현황/사업장현황/
    구매처현황/판매처현황/매출구성 — 완전한 표 구조화 대신 원문 텍스트로 보존(데이터
    없으면 None)."""

    # ===== 2026-10-02 확장: 연도 인식 + 미추출 영역 전부 =====
    basic_extra: dict[str, str | None] = Field(default_factory=dict)
    """2페이지 추가 항목: 영문기업명, 법인번호, 종업원수, 전화·팩스·이메일·홈페이지, 주채권기관, 당좌거래은행 등."""
    my_financial_data: dict[str, YearlyValues] = Field(default_factory=dict)
    """3페이지 MY 재무Data (백만원, 최근 2개년)."""
    cash_flow_summary: dict[str, YearlyValues] = Field(default_factory=dict)
    """요약현금흐름분석 (백만원) + 현금흐름등급(CR1~)."""
    cash_flow_base_date: str | None = None
    audit_opinions: dict[str, dict[str, str]] = Field(default_factory=dict)
    """재무표별 {연도: 감사의견}."""
    diagnosis_details: dict[str, dict] = Field(default_factory=dict)
    """재무진단 5축별 {base_date, summary, indicators: [{name, industry_avg, yoy, company, history}]}."""
    industry_rank_list: list[dict] = Field(default_factory=list)
    """업계순위 표의 조회기업 앞뒤 기업들 [{rank, company_name, revenue, settlement_month, business_no, representative}]."""
    industry_top5: list[dict] = Field(default_factory=list)
    industry_base_year: str | None = None
    peer_base_year: str | None = None
    partners: dict[str, list[dict]] = Field(default_factory=dict)
    """{"구매처"|"판매처": [{company_name, business_no, representative, share_pct, fiscal_year, capital, total_assets, revenue, net_income}]}"""
    history: list[dict] = Field(default_factory=list)
    """연혁 [{date, content}]."""
    bid_summary: dict[str, str | None] = Field(default_factory=dict)
    tech_info: dict[str, str | None] = Field(default_factory=dict)
    extraction_coverage: dict = Field(default_factory=dict)
    """추출 완성도 {target: 추출 대상 값 수, missed: 미추출 수, missed_items: [미추출 원문 ≤50]} — 빈 칸은 추출된 것으로 봄."""

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
    fiscal_year: str | None = None             # 아래 최근값들의 결산연도
    revenue_latest: float | None = None        # 매출액(백만원)
    operating_profit_latest: float | None = None
    net_income_latest: float | None = None     # 당기순이익(백만원)
    debt_ratio_latest: float | None = None     # 부채비율(%)
    parsed_at: datetime


class CompanyList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CompanyListItem]


class CategoryList(BaseModel):
    """법인형태별 분류(개인사업자/일반법인/농업회사법인/영농조합법인) 목록 — 항목
    구성은 기업목록(CompanyList)과 완전히 동일하고, category/label만 추가로 붙는다."""
    category: str
    label: str
    total: int
    page: int
    page_size: int
    items: list[CompanyListItem]


class MailingListEntry(BaseModel):
    no: int
    business_no: str
    postal_code: str | None = None
    address: str | None = None
    company_name: str
    representative: str | None = None


class MailingList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MailingListEntry]


class IssueEntry(BaseModel):
    business_no: str
    company_name: str
    issue: ValidationIssue


class IssueList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[IssueEntry]


class DashboardSummary(BaseModel):
    total_companies: int
    parsing_success_rate: float
    pending_issues: int
    by_industry: dict[str, int]
    by_credit_grade_band: dict[str, int]
    by_credit_grade: dict[str, int] = {}   # 실제 등급별(우량 순, 미평가는 맨 뒤)
    recent: list[CompanyListItem]


ProjectStatus = Literal["준비", "진행중", "종료"]


class ProjectInput(BaseModel):
    """프로젝트 등록/수정 입력. 날짜는 YYYY-MM-DD."""
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    region: str | None = Field(default=None, max_length=100)
    start_date: str | None = None
    end_date: str | None = None
    status: ProjectStatus | None = None


class Project(BaseModel):
    id: int
    name: str
    description: str | None = None
    region: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str
    created_at: str
    company_count: int = 0


class ProjectCompaniesInput(BaseModel):
    business_nos: list[str]


class ProjectRef(BaseModel):
    id: int
    name: str
    status: str
