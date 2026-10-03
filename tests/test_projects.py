"""프로젝트 기반 관리 (PLAN.md Phase 9)."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.app import app
from backend.excel import generator as excel_generator
from backend.models import Company, ValidationIssue
from backend.routers import upload as upload_router


def _company(bn, name, **kw) -> Company:
    base = dict(business_no=bn, company_name=name, representative="홍길동", address="전남 나주시",
                postal_code="58200", income_summary={"매출액": {"2025": 1000}}, parsed_at=datetime.now(timezone.utc))
    base.update(kw)
    return Company(**base)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(upload_router, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(excel_generator, "OUTPUT_DIR", tmp_path / "outputs")
    storage.save_company(_company("111-11-11111", "가농장"))
    storage.save_company(_company("222-22-22222", "나농장", issues=[ValidationIssue(type="missing_field", field="credit_grade", message="x")]))
    storage.save_company(_company("333-33-33333", "다농장"))
    return TestClient(app)


def _create(client, **kw):
    body = {"name": "2026년 하반기 충북 스마트팜 지원사업", "start_date": "2026-07-01", "end_date": "2026-12-31"}
    body.update(kw)
    return client.post("/api/projects", json=body)


def test_create_and_list_project(client):
    res = _create(client)
    assert res.status_code == 201
    p = res.json()
    assert p["name"] == "2026년 하반기 충북 스마트팜 지원사업" and p["company_count"] == 0
    assert p["status"] == storage.project_status("2026-07-01", "2026-12-31") and "region" not in p
    assert [x["id"] for x in client.get("/api/projects").json()] == [p["id"]]


def test_project_validation(client):
    assert _create(client, name="  ").status_code == 422
    assert _create(client, start_date="2026-12-31", end_date="2026-01-01").status_code == 422
    assert _create(client, start_date="2026/07/01").status_code == 422
    assert _create(client).status_code == 201
    assert _create(client).status_code == 409  # 같은 이름


def test_add_remove_companies_and_filter_all_menus(client):
    pid = _create(client).json()["id"]
    assert client.post(f"/api/projects/{pid}/companies", json={"business_nos": ["111-11-11111", "222-22-22222"]}).json() == {"added": 2}
    assert client.post(f"/api/projects/{pid}/companies", json={"business_nos": ["111-11-11111"]}).json() == {"added": 0}
    assert client.post(f"/api/projects/{pid}/companies", json={"business_nos": ["999-99-99999"]}).status_code == 404

    names = lambda res: sorted(i["company_name"] for i in res.json()["items"])
    assert names(client.get("/api/companies", params={"project_id": pid})) == ["가농장", "나농장"]
    assert client.get("/api/companies").json()["total"] == 3  # 전체 프로젝트
    assert client.get("/api/dashboard/summary", params={"project_id": pid}).json()["total_companies"] == 2
    assert client.get("/api/mailing-list", params={"project_id": pid}).json()["total"] == 2
    assert client.get("/api/issues", params={"project_id": pid}).json()["total"] == 1
    assert client.get("/api/category-list/general_corp", params={"project_id": pid}).json()["total"] == 2
    assert client.get(f"/api/projects/{pid}").json()["company_count"] == 2
    assert [p["id"] for p in client.get("/api/companies/111-11-11111/projects").json()] == [pid]

    assert client.delete(f"/api/projects/{pid}/companies/111-11-11111").status_code == 204
    assert names(client.get("/api/companies", params={"project_id": pid})) == ["나농장"]
    assert storage.load_company("111-11-11111") is not None  # 기업 데이터는 유지


def test_company_can_join_multiple_projects(client):
    a = _create(client, name="A사업").json()["id"]
    b = _create(client, name="B사업").json()["id"]
    for pid in (a, b):
        client.post(f"/api/projects/{pid}/companies", json={"business_nos": ["333-33-33333"]})
    assert {p["name"] for p in client.get("/api/companies/333-33-33333/projects").json()} == {"A사업", "B사업"}


def test_delete_project_keeps_companies(client):
    pid = _create(client).json()["id"]
    client.post(f"/api/projects/{pid}/companies", json={"business_nos": ["111-11-11111"]})
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.get("/api/companies").json()["total"] == 3


def test_deleting_company_removes_membership(client):
    pid = _create(client).json()["id"]
    client.post(f"/api/projects/{pid}/companies", json={"business_nos": ["111-11-11111"]})
    client.delete("/api/companies/111-11-11111")
    assert client.get(f"/api/projects/{pid}").json()["company_count"] == 0


def test_update_project(client):
    pid = _create(client).json()["id"]
    res = client.patch(f"/api/projects/{pid}", json={"start_date": "2020-01-01", "end_date": "2020-12-31", "status": "준비"})
    assert res.json()["status"] == "종료"  # 상태는 입력값이 아니라 지원기간으로 계산
    res = client.patch(f"/api/projects/{pid}", json={"start_date": "2999-01-01", "end_date": "2999-12-31"})
    assert res.json()["status"] == "준비"
    assert client.patch(f"/api/projects/{pid}", json={"end_date": "2026-01-01"}).status_code == 422  # 시작일보다 빠름


def test_project_status_follows_support_period():
    from datetime import date
    today = date(2026, 10, 2)
    assert storage.project_status("2026-11-01", "2026-12-31", today) == "준비"
    assert storage.project_status("2026-07-01", "2026-12-31", today) == "진행중"
    assert storage.project_status("2026-07-01", "2026-10-02", today) == "진행중"  # 종료일 당일까지 진행중
    assert storage.project_status("2026-01-01", "2026-10-01", today) == "종료"
    assert storage.project_status(None, None, today) == "진행중"  # 기간 미입력
    assert storage.project_status(None, "2026-09-30", today) == "종료"
    assert storage.project_status("2026-10-03", None, today) == "준비"


def test_upload_rejects_unknown_project(client):
    res = client.post("/api/upload", params={"project_id": 999}, files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert res.status_code == 404


def test_purge_project_requires_credentials_and_deletes_everything(client, monkeypatch):
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "1234")
    login = client.post("/api/login", json={"username": "admin", "password": "1234"})
    assert login.status_code == 200
    a = _create(client, name="A사업").json()["id"]
    b = _create(client, name="B사업").json()["id"]
    client.post(f"/api/projects/{a}/companies", json={"business_nos": ["111-11-11111", "222-22-22222"]})
    client.post(f"/api/projects/{b}/companies", json={"business_nos": ["222-22-22222"]})  # 나농장은 B에도 참여
    client.patch(f"/api/sales/{a}/111-11-11111", json={"dm_sent": True, "memo": "통화함"})
    client.patch(f"/api/sales/{a}/222-22-22222", json={"decision": "승인"})
    client.patch(f"/api/sales/{b}/222-22-22222", json={"memo": "B사업 메모"})

    preview = client.get(f"/api/projects/{a}/purge-preview").json()
    assert preview["companies"] == 2 and preview["exclusive_companies"] == 1 and preview["shared_companies"] == 1
    assert preview["sales_records"] == 2 and preview["dm_sent"] == 1 and preview["decisions"] == 1 and preview["memos"] == 1

    assert client.post(f"/api/projects/{a}/purge", json={"username": "admin", "password": "wrong"}).status_code == 403
    assert client.get(f"/api/projects/{a}").status_code == 200  # 비밀번호가 틀리면 아무것도 지우지 않음

    res = client.post(f"/api/projects/{a}/purge", json={"username": "admin", "password": "1234"})
    assert res.status_code == 200 and res.json()["deleted_companies"] == 1
    assert client.get(f"/api/projects/{a}").status_code == 404
    assert storage.load_company("111-11-11111") is None  # A에만 있던 기업은 완전히 삭제
    assert storage.load_company("222-22-22222") is not None  # B에도 있는 기업은 유지
    b_rows = client.get("/api/sales", params={"project_id": b}).json()
    assert [r["memo"] for r in b_rows] == ["B사업 메모"]  # 다른 프로젝트의 영업 기록은 그대로
    assert storage.list_sales(a) == []


def test_purge_refused_without_password_configured(client):
    pid = _create(client).json()["id"]
    res = client.post(f"/api/projects/{pid}/purge", json={"username": "admin", "password": "1234"})
    assert res.status_code == 409 and client.get(f"/api/projects/{pid}").status_code == 200
