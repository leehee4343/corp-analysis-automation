"""API 레이어 테스트. storage.DATA_DIR을 tmp_path로 바꿔치기해서 실제 data/ 폴더를 건드리지 않는다."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.app import app
from backend.excel import generator as excel_generator
from backend.models import Company, DiagnosisRatings, IndustryRank, ValidationIssue
from backend.routers import upload as upload_router

SAMPLE_PDF = Path(__file__).parent / "sample_pdfs" / "1_옥산농원.pdf"


def _sample_company(**overrides) -> Company:
    base = dict(
        business_no="412-93-13689",
        company_name="옥산농원",
        representative="김종원",
        address="광주 나주시 봉황면 옥산유곡길 48-19",
        industry_name="양계업",
        credit_grade="bb+",
        income_summary={"매출액": {"2023": 7154, "2024": 7241, "2025": 8307}},
        diagnosis=DiagnosisRatings(growth="양호"),
        industry_rank=IndustryRank(rank=74, sample_size=79),
        parsed_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return Company(**base)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(upload_router, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(excel_generator, "OUTPUT_DIR", tmp_path / "outputs")
    return TestClient(app)


def test_list_companies_empty(client):
    res = client.get("/api/companies")
    assert res.status_code == 200
    assert res.json() == {"total": 0, "page": 1, "page_size": 20, "items": []}


def test_list_and_get_company(client):
    storage.save_company(_sample_company())

    res = client.get("/api/companies")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "옥산농원"
    assert body["items"][0]["revenue_latest"] == 8307

    res = client.get("/api/companies/412-93-13689")
    assert res.status_code == 200
    assert res.json()["representative"] == "김종원"


def test_get_company_not_found(client):
    res = client.get("/api/companies/000-00-00000")
    assert res.status_code == 404


def test_search_by_name(client):
    storage.save_company(_sample_company())
    storage.save_company(_sample_company(business_no="303-81-54893", company_name="농업회사법인 동일농장"))

    res = client.get("/api/companies", params={"q": "옥산"})
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["company_name"] == "옥산농원"


def test_filter_by_grade_band_and_revenue(client):
    storage.save_company(_sample_company())  # bb+ -> BB band, revenue 8307
    storage.save_company(_sample_company(
        business_no="303-81-54893", company_name="농업회사법인 동일농장",
        credit_grade="a-", income_summary={"매출액": {"2023": 1000, "2024": 1500, "2025": 2000}},
    ))

    res = client.get("/api/companies", params={"grade_band": "A~BBB"})
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["company_name"] == "농업회사법인 동일농장"

    res = client.get("/api/companies", params={"revenue_min": 5000})
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["company_name"] == "옥산농원"


def test_download_source_pdf(client, tmp_path):
    pdf_path = tmp_path / "1_옥산농원.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    storage.save_company(_sample_company(source_pdf=str(pdf_path)))

    res = client.get("/api/companies/412-93-13689/source-pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"


def test_download_source_pdf_missing_file_404s(client):
    storage.save_company(_sample_company(source_pdf="uploads/does-not-exist.pdf"))
    res = client.get("/api/companies/412-93-13689/source-pdf")
    assert res.status_code == 404


def test_download_excel(client):
    storage.save_company(_sample_company())
    res = client.get("/api/companies/412-93-13689/excel")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_patch_company_clears_matching_issue(client):
    company = _sample_company(issues=[
        ValidationIssue(type="format_suspect", field="representative", message="숫자 포함 의심"),
    ])
    storage.save_company(company)

    res = client.patch("/api/companies/412-93-13689", json={"representative": "김종원"})
    assert res.status_code == 200
    body = res.json()
    assert body["representative"] == "김종원"
    assert body["issues"] == []


def test_delete_company(client):
    storage.save_company(_sample_company())

    res = client.delete("/api/companies/412-93-13689")
    assert res.status_code == 204
    assert client.get("/api/companies/412-93-13689").status_code == 404
    assert client.get("/api/companies").json()["total"] == 0


def test_delete_company_not_found(client):
    res = client.delete("/api/companies/000-00-00000")
    assert res.status_code == 404


def test_issues_endpoint(client):
    storage.save_company(_sample_company(issues=[
        ValidationIssue(type="missing_field", field="address", message="주소 없음"),
    ]))
    res = client.get("/api/issues")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["company_name"] == "옥산농원"
    assert body[0]["issue"]["type"] == "missing_field"


def test_dashboard_summary(client):
    storage.save_company(_sample_company())
    storage.save_company(_sample_company(
        business_no="303-81-54893", company_name="농업회사법인 동일농장",
        credit_grade="ccc", industry_name="농업법인",
        issues=[ValidationIssue(type="missing_field", field="address", message="주소 없음")],
    ))

    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["total_companies"] == 2
    assert body["pending_issues"] == 1
    assert body["by_industry"] == {"양계업": 1, "농업법인": 1}
    assert body["by_credit_grade_band"] == {"BB": 1, "CCC 이하": 1}  # bb+ -> BB, ccc -> CCC 이하
    assert body["parsing_success_rate"] == 50.0


def test_upload_rejects_non_pdf(client):
    res = client.post("/api/upload", files={"file": ("readme.txt", b"hello", "text/plain")})
    assert res.status_code == 400


def test_upload_corrupt_pdf_returns_clean_422_not_a_crash(client):
    res = client.post("/api/upload", files={"file": ("broken.pdf", b"not a real pdf", "application/pdf")})
    assert res.status_code == 422
    assert "detail" in res.json()


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="샘플 PDF 없음")
def test_upload_real_pdf_end_to_end(client):
    with open(SAMPLE_PDF, "rb") as f:
        res = client.post("/api/upload", files={"file": (SAMPLE_PDF.name, f, "application/pdf")})
    assert res.status_code == 200
    body = res.json()
    assert body["business_no"] == "412-93-13689"
    assert body["company_name"] == "옥산농원"

    # 목록/상세/엑셀 다운로드까지 실제로 이어지는지 확인
    assert client.get("/api/companies/412-93-13689").status_code == 200
    excel_res = client.get("/api/companies/412-93-13689/excel")
    assert excel_res.status_code == 200
