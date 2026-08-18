from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

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
        industry_name="양계업",
        credit_grade="bb+",
        income_summary={"매출액": {"2025": 8307.0}},
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


def test_category_list_item_shape_matches_company_list(client):
    """기업목록(/api/companies)과 항목 구성이 완전히 동일해야 한다(재무진단 제거,
    영업이익/등록일 포함)."""
    storage.save_company(_company())
    res = client.get("/api/category-list/individual")
    item = res.json()["items"][0]
    assert set(item.keys()) == {
        "business_no", "company_name", "industry_name", "credit_grade",
        "status", "revenue_latest", "operating_profit_latest", "parsed_at",
    }
    assert item["revenue_latest"] == 8307.0


def test_category_list_industry_filter(client):
    storage.save_company(_company())
    res = client.get("/api/category-list/individual", params={"industry": "양계업"})
    assert res.json()["total"] == 1
    res2 = client.get("/api/category-list/individual", params={"industry": "없는업종"})
    assert res2.json()["total"] == 0


def test_category_list_grade_band_filter(client):
    storage.save_company(_company(credit_grade="bb+"))
    res = client.get("/api/category-list/individual", params={"grade_band": "BB"})
    assert res.json()["total"] == 1
    res2 = client.get("/api/category-list/individual", params={"grade_band": "A~BBB"})
    assert res2.json()["total"] == 0


def test_category_list_revenue_filter(client):
    storage.save_company(_company())  # 매출액 83.07억
    res = client.get("/api/category-list/individual", params={"revenue_min": 5000})
    assert res.json()["total"] == 1
    res2 = client.get("/api/category-list/individual", params={"revenue_min": 100000})
    assert res2.json()["total"] == 0
