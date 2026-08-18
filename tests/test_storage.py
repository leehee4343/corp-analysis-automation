from backend import storage
from backend.parser.grade_ocr import GradeResult
from backend.parser.pdf_parser import ParsedCompany


def _sample_parsed(**overrides) -> ParsedCompany:
    base = dict(
        business_no="412-93-13689",
        company_name="옥산농원",
        representative="김종원",
        address="광주 나주시 봉황면 옥산유곡길 48-19",
        balance_summary={"자산총계": {"2023": 3944, "2024": 4000, "2025": 4367}},
        income_summary={"매출액": {"2023": 7154, "2024": 7241, "2025": 8307}},
        diagnosis={"growth": "양호", "profitability": "우수", "financial_structure": None,
                   "debt_repayment": None, "activity": None},
        industry_rank={"rank": 74, "sample_size": 79},
        report_query_datetime="2026-07-24 12:31:25",
        source_pdf="tests/sample_pdfs/1_옥산농원.pdf",
        page_count=31,
    )
    base.update(overrides)
    return ParsedCompany(**base)


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    company = storage.build_company(_sample_parsed(), GradeResult(credit_grade="bb+", ew_grade="정상"))
    storage.save_company(company)

    loaded = storage.load_company("412-93-13689")
    assert loaded is not None
    assert loaded.company_name == "옥산농원"
    assert loaded.credit_grade == "bb+"
    assert loaded.status == "complete"
    assert loaded.issues == []


def test_full_extraction_fields_survive_save_and_load(tmp_path, monkeypatch):
    """PDF 전체 추출 필드(사용자 요청, PLAN.md 참고)가 JSON 저장/로딩을 거쳐도 보존되는지."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    parsed = _sample_parsed(
        credit_info={"행정처분정보": "해당사항없음"},
        certifications={"벤처": "미인증"},
        ledger_detail={"재무상태표": {"자산(*)": {"2023": 3943892, "2024": 3999727, "2025": 4366652}}},
        ratio_detail={"안정성": {"부채비율": {"2023": 770.81, "2024": 351.75, "2025": 313.37}}},
        diagnosis_commentary="동사의매출액증가율과영업이익증가율모두양호함",
        personal_info={"name_position": "김종원/대표자"},
        soft_sections={"종합의견": None, "주식소유현황": "대표자 김종원"},
    )
    company = storage.build_company(parsed)
    storage.save_company(company)

    loaded = storage.load_company("412-93-13689")
    assert loaded.credit_info == {"행정처분정보": "해당사항없음"}
    assert loaded.ledger_detail["재무상태표"]["자산(*)"]["2023"] == 3943892
    assert loaded.ratio_detail["안정성"]["부채비율"]["2025"] == 313.37
    assert loaded.diagnosis_commentary == "동사의매출액증가율과영업이익증가율모두양호함"
    assert loaded.personal_info == {"name_position": "김종원/대표자"}
    assert loaded.soft_sections["종합의견"] is None
    assert loaded.soft_sections["주식소유현황"] == "대표자 김종원"


def test_missing_field_creates_issue(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    parsed = _sample_parsed(address=None, missing_fields=["address"])
    company = storage.build_company(parsed)
    assert company.status == "needs_review"
    assert any(i.type == "missing_field" and i.field == "address" for i in company.issues)


def test_representative_with_digits_flagged_as_format_suspect(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    company = storage.build_company(_sample_parsed(representative="정혜선2"))
    assert any(i.type == "format_suspect" and i.field == "representative" for i in company.issues)


def test_reupload_with_different_report_date_flagged_as_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    first = storage.build_company(_sample_parsed(report_query_datetime="2026-07-01 09:00:00"))
    storage.save_company(first)

    second = storage.build_company(_sample_parsed(report_query_datetime="2026-07-24 12:31:25"))
    assert any(i.type == "duplicate_suspect" for i in second.issues)


def test_parse_error_creates_visible_issue_but_company_still_registers(tmp_path, monkeypatch):
    """섹션 하나가 파싱 중 예외를 던져도(부분 실패) 회사 자체는 등록되고, 실패한 부분만
    검증 대기열에 뜬다 — 사용자 버그 리포트 대응(PLAN.md 참고)."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    parsed = _sample_parsed(parse_errors=["업계순위: IndexError: 의도적으로 발생시킨 테스트용 오류"])
    company = storage.build_company(parsed)
    assert company.company_name == "옥산농원"  # 회사는 정상 등록됨
    assert company.status == "needs_review"
    assert any("업계순위" in i.message for i in company.issues)


def test_list_companies_and_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.save_company(storage.build_company(_sample_parsed()))
    storage.save_company(storage.build_company(_sample_parsed(
        business_no="303-81-54893", company_name="농업회사법인 동일농장",
        representative="정혜선2",
    )))

    companies = storage.list_companies()
    assert len(companies) == 2

    issues = storage.list_issues()
    assert any(c.company_name == "농업회사법인 동일농장" for c, _ in issues)


def test_save_company_upserts_same_business_no(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    c1 = storage.build_company(_sample_parsed(company_name="옛날이름"))
    storage.save_company(c1)
    c2 = storage.build_company(_sample_parsed(company_name="새이름"))
    storage.save_company(c2)  # 같은 business_no로 재저장

    assert storage.load_company("412-93-13689").company_name == "새이름"
    assert len(storage.list_companies()) == 1  # 중복 행 생기지 않음


def test_delete_company_removes_record_and_allows_readd(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.save_company(storage.build_company(_sample_parsed()))

    assert storage.delete_company("412-93-13689") is True
    assert storage.load_company("412-93-13689") is None
    assert storage.list_companies() == []

    # 삭제 후 재업로드하면 다시 정상 등록된다.
    storage.save_company(storage.build_company(_sample_parsed()))
    assert storage.load_company("412-93-13689") is not None


def test_delete_unknown_business_no_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    assert storage.delete_company("000-00-00000") is False
