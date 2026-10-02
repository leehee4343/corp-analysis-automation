"""PDF 업로드 화면의 업로드 PDF 목록·삭제 (삭제 시 기업 정보·프로젝트 참여도 삭제)."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.app import app
from backend.models import Company


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    for bn, name in [("111-11-11111", "가농장"), ("222-22-22222", "나농장"), ("333-33-33333", "다농장")]:
        pdf = uploads / f"{name}.pdf"
        pdf.write_bytes(b"%PDF-1.4 " + name.encode())
        storage.save_company(Company(business_no=bn, company_name=name, source_pdf=str(pdf), parsed_at=datetime.now(timezone.utc)))
    c = TestClient(app)
    c.uploads = uploads
    return c


def _project(client, name):
    return client.post("/api/projects", json={"name": name}).json()["id"]


def test_list_pdfs_by_project(client):
    a, b = _project(client, "A사업"), _project(client, "B사업")
    client.post(f"/api/projects/{a}/companies", json={"business_nos": ["111-11-11111", "222-22-22222"]})
    client.post(f"/api/projects/{b}/companies", json={"business_nos": ["222-22-22222"]})
    items = client.get("/api/pdfs", params={"project_id": a}).json()
    assert sorted(i["company_name"] for i in items) == ["가농장", "나농장"]
    shared = next(i for i in items if i["business_no"] == "222-22-22222")
    assert sorted(shared["projects"]) == ["A사업", "B사업"]  # 다른 프로젝트 참여 여부 안내용
    assert shared["filename"] == "나농장.pdf" and shared["size_bytes"] > 0
    assert len(client.get("/api/pdfs").json()) == 3  # 전체 프로젝트


def test_delete_selected_removes_pdf_company_and_membership(client):
    a = _project(client, "A사업")
    client.post(f"/api/projects/{a}/companies", json={"business_nos": ["111-11-11111", "222-22-22222"]})
    res = client.post("/api/pdfs/delete", json={"business_nos": ["111-11-11111", "222-22-22222", "999-99-99999"]})
    assert res.json() == {"deleted": 2, "not_found": ["999-99-99999"]}
    assert storage.load_company("111-11-11111") is None and storage.load_company("222-22-22222") is None
    assert not (client.uploads / "가농장.pdf").exists()
    assert client.get(f"/api/projects/{a}").json()["company_count"] == 0
    assert [i["company_name"] for i in client.get("/api/pdfs").json()] == ["다농장"]


def test_delete_requires_selection(client):
    assert client.post("/api/pdfs/delete", json={"business_nos": []}).status_code == 422


def test_source_pdf_inline_or_download(client):
    view = client.get("/api/companies/111-11-11111/source-pdf")
    assert view.status_code == 200 and view.headers["content-disposition"].startswith("inline")
    down = client.get("/api/companies/111-11-11111/source-pdf", params={"download": "true"})
    assert down.headers["content-disposition"].startswith("attachment") and down.content.startswith(b"%PDF")
