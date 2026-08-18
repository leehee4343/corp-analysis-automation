from datetime import datetime, timezone

import openpyxl
import pytest
from fastapi.testclient import TestClient

from backend import master_list, storage
from backend.app import app
from backend.excel import generator as excel_generator
from backend.models import Company
from backend.routers import upload as upload_router


def _company(**overrides) -> Company:
    base = dict(
        business_no="412-93-13689",
        company_name="농업회사법인옥산농원",  # xlsx 쪽 이름("옥산농원")과 법인형태 노이즈워드만 다름
        credit_grade="bb+",
        parsed_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return Company(**base)


def _write_master_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "전체DB"
    ws.append(["기업체명", "대표자명", "형태", "업종", "법인등록번호", "주소", "연락처", "매출액", "기업등급"])
    for row in rows:
        ws.append(row)
    wb.save(path)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(upload_router, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(excel_generator, "OUTPUT_DIR", tmp_path / "outputs")

    xlsx_path = tmp_path / "검색조회 목록.xlsx"
    _write_master_xlsx(xlsx_path, [
        ["옥산농원", "김종원", "일반법인", "양계업", "412-93-00000", None, None, None, None],
        ["(주)미분석기업", "박대표", "일반법인", "기타제조업", "111-11-11111", None, None, None, None],
    ])
    monkeypatch.setattr(master_list, "MASTER_LIST_PATH", xlsx_path)
    master_list._cache["key"] = None
    return TestClient(app)


def test_normalize_name_strips_corporate_form_noise():
    assert master_list.normalize_name("농업회사법인(주)일등축산") == master_list.normalize_name("농업회사법인일등축산")
    assert master_list.normalize_name("㈜테스트") == master_list.normalize_name("(주) 테스트")


def test_master_list_marks_analyzed_company_by_normalized_name(client):
    storage.save_company(_company())
    res = client.get("/api/master-list")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    by_name = {item["company_name"]: item for item in body["items"]}

    assert by_name["옥산농원"]["analyzed"] is True
    assert by_name["옥산농원"]["business_no"] == "412-93-13689"
    assert by_name["옥산농원"]["credit_grade"] == "bb+"

    assert by_name["(주)미분석기업"]["analyzed"] is False
    assert by_name["(주)미분석기업"]["business_no"] is None
    assert by_name["(주)미분석기업"]["representative"] == "박대표"


def test_master_list_analyzed_only_filter(client):
    storage.save_company(_company())
    res = client.get("/api/master-list", params={"analyzed_only": "true"})
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "옥산농원"


def test_master_list_search_matches_unanalyzed_rows_too(client):
    res = client.get("/api/master-list", params={"q": "미분석기업"})
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["business_no"] is None


def test_master_list_industries_endpoint(client):
    res = client.get("/api/master-list/industries")
    assert res.status_code == 200
    assert res.json() == ["기타제조업", "양계업"]


def test_malformed_xlsx_missing_expected_sheet_returns_empty_not_500(tmp_path, monkeypatch):
    """파일은 있지만 '전체DB' 시트가 없는 경우(손상된 파일 등) — 500 대신 빈 목록."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(upload_router, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(excel_generator, "OUTPUT_DIR", tmp_path / "outputs")

    xlsx_path = tmp_path / "broken.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["dummy"])
    wb.save(xlsx_path)
    monkeypatch.setattr(master_list, "MASTER_LIST_PATH", xlsx_path)
    master_list._cache["key"] = None

    client = TestClient(app)
    res = client.get("/api/master-list")
    assert res.status_code == 200
    assert res.json()["total"] == 0
