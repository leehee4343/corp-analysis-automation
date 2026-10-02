"""영업 관리(DM 발송 · 승인/거절) API 테스트 — SQLite(tmp_path)로 격리."""
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.app import app
from backend.models import Company


def _company(bn, name):
    return Company(business_no=bn, company_name=name, representative="홍길동", postal_code="57111", address="전남 함평군",
                   credit_grade="bb", parsed_at=datetime.now(timezone.utc))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    for bn, name in (("111-11-11111", "가농장"), ("222-22-22222", "나농장")):
        storage.save_company(_company(bn, name))
    return TestClient(app)


def _project(client, name="A사업", members=("111-11-11111", "222-22-22222")):
    pid = client.post("/api/projects", json={"name": name}).json()["id"]
    client.post(f"/api/projects/{pid}/companies", json={"business_nos": list(members)})
    return pid


def test_list_defaults_to_unsent_undecided(client):
    pid = _project(client)
    rows = client.get("/api/sales", params={"project_id": pid}).json()
    assert {r["company_name"] for r in rows} == {"가농장", "나농장"}
    assert all(r["dm_sent"] is False and r["decision"] is None and r["project_name"] == "A사업" for r in rows)


def test_update_dm_and_decision_records_dates(client):
    pid = _project(client)
    res = client.patch(f"/api/sales/{pid}/111-11-11111", json={"dm_sent": True})
    assert res.status_code == 200 and res.json()["dm_sent"] and res.json()["dm_sent_at"] == date.today().isoformat()
    res = client.patch(f"/api/sales/{pid}/111-11-11111", json={"decision": "승인"})
    assert res.json()["decision"] == "승인" and res.json()["dm_sent"] is True  # 다른 값은 유지
    res = client.patch(f"/api/sales/{pid}/111-11-11111", json={"decision": None})
    assert res.json()["decision"] is None and res.json()["decided_at"] is None  # 미정으로 되돌림
    assert client.patch(f"/api/sales/{pid}/111-11-11111", json={"decision": "보류"}).status_code == 422
    assert client.patch(f"/api/sales/{pid}/111-11-11111", json={}).status_code == 422


def test_bulk_update_and_membership_checks(client):
    pid = _project(client)
    items = [{"project_id": pid, "business_no": bn} for bn in ("111-11-11111", "222-22-22222")]
    assert client.post("/api/sales/bulk", json={"items": items, "dm_sent": True}).json() == {"updated": 2}
    assert all(r["dm_sent"] for r in client.get("/api/sales", params={"project_id": pid}).json())
    assert client.patch(f"/api/sales/{pid}/999-99-99999", json={"dm_sent": True}).status_code == 404
    assert client.post("/api/sales/bulk", json={"items": [{"project_id": pid, "business_no": "999-99-99999"}], "dm_sent": True}).status_code == 404


def test_status_is_per_project_and_removed_with_membership(client):
    a = _project(client, "A사업")
    b = _project(client, "B사업", members=("111-11-11111",))
    client.patch(f"/api/sales/{a}/111-11-11111", json={"decision": "거절"})
    by_project = {(r["project_id"], r["business_no"]): r for r in client.get("/api/sales").json()}
    assert by_project[(a, "111-11-11111")]["decision"] == "거절"
    assert by_project[(b, "111-11-11111")]["decision"] is None  # 다른 프로젝트는 따로
    client.delete(f"/api/projects/{a}/companies/111-11-11111")
    client.post(f"/api/projects/{a}/companies", json={"business_nos": ["111-11-11111"]})
    row = next(r for r in client.get("/api/sales", params={"project_id": a}).json() if r["business_no"] == "111-11-11111")
    assert row["decision"] is None  # 명단에서 빠질 때 영업 기록도 삭제(cascade)


def test_memo_save_edit_and_clear(client):
    pid = _project(client)
    res = client.patch(f"/api/sales/{pid}/111-11-11111", json={"memo": "  대표 통화 완료, 10월 말 재연락  "})
    assert res.json()["memo"] == "대표 통화 완료, 10월 말 재연락" and res.json()["memo_updated_at"]
    client.patch(f"/api/sales/{pid}/111-11-11111", json={"dm_sent": True})  # 다른 항목을 바꿔도 메모 유지
    row = next(r for r in client.get("/api/sales", params={"project_id": pid}).json() if r["business_no"] == "111-11-11111")
    assert row["memo"] == "대표 통화 완료, 10월 말 재연락" and row["dm_sent"] is True
    res = client.patch(f"/api/sales/{pid}/111-11-11111", json={"memo": "   "})
    assert res.json()["memo"] is None and res.json()["memo_updated_at"] is None  # 빈 메모 = 삭제
    assert client.patch(f"/api/sales/{pid}/111-11-11111", json={"memo": "가" * 2001}).status_code == 422
