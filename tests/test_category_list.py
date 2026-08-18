from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend import category_list, storage
from backend.app import app
from backend.excel import generator as excel_generator
from backend.models import Company
from backend.routers import upload as upload_router


def _company(**overrides) -> Company:
    base = dict(
        business_no="412-93-13689",
        company_name="옥산농원",
        representative="김종원",
        company_type="개인사업자",
        credit_grade="bb+",
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


def test_classify_individual_by_company_type():
    company = _company(company_type="개인사업자", company_name="아무개농장")
    assert category_list.classify(company) == "individual"


def test_classify_agri_corp_by_name_pattern():
    company = _company(company_type="일반법인", company_name="농업회사법인참누리")
    assert category_list.classify(company) == "agri_corp"


def test_classify_farm_partnership_by_name_pattern():
    company = _company(company_type="일반법인", company_name="덕성종돈영농조합법인")
    assert category_list.classify(company) == "farm_partnership"


def test_classify_general_corp_is_default():
    company = _company(company_type="외감", company_name="㈜테스트법인")
    assert category_list.classify(company) == "general_corp"


def test_category_list_only_shows_matching_companies(client):
    storage.save_company(_company())  # 개인사업자, 옥산농원
    storage.save_company(_company(
        business_no="204311-0000000", company_name="농업회사법인테스트",
        company_type="일반법인",
    ))

    res = client.get("/api/category-list/individual")
    assert res.status_code == 200
    body = res.json()
    assert body["label"] == "개인사업자"
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "옥산농원"
    assert body["items"][0]["business_no"] == "412-93-13689"

    res2 = client.get("/api/category-list/agri_corp")
    assert res2.json()["total"] == 1
    assert res2.json()["items"][0]["company_name"] == "농업회사법인테스트"


def test_category_list_empty_when_no_companies(client):
    res = client.get("/api/category-list/general_corp")
    assert res.status_code == 200
    assert res.json()["total"] == 0


def test_unknown_category_returns_404(client):
    res = client.get("/api/category-list/does_not_exist")
    assert res.status_code == 404


def test_category_search(client):
    storage.save_company(_company())
    res = client.get("/api/category-list/individual", params={"q": "옥산"})
    assert res.json()["total"] == 1
    res2 = client.get("/api/category-list/individual", params={"q": "없는이름"})
    assert res2.json()["total"] == 0


def test_category_excel_export(client):
    storage.save_company(_company())
    res = client.get("/api/category-list/individual/excel")
    assert res.status_code == 200

    import io
    wb = load_workbook(io.BytesIO(res.content))
    ws = wb.active
    assert [c.value for c in ws[1]] == ["No.", "사업자번호", "기업체명", "대표자명", "업종", "신용등급", "매출액(백만)"]
    assert ws["B2"].value == "412-93-13689"
    assert ws["C2"].value == "옥산농원"
