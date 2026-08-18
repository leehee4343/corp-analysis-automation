import pytest
from fastapi.testclient import TestClient

from backend import category_list, master_list, storage
from backend.app import app
from backend.excel import generator as excel_generator
from backend.routers import upload as upload_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(upload_router, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(excel_generator, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(master_list, "MASTER_LIST_PATH", tmp_path / "참고자료" / "검색조회 목록.xlsx")
    monkeypatch.setattr(category_list, "CATEGORY_LIST_PATH", tmp_path / "참고자료" / "추가메뉴.xlsx")
    master_list._cache["key"] = None
    category_list._cache.clear()
    return TestClient(app)


def _dummy_xlsx_bytes() -> bytes:
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["dummy"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_without_token_env_var_is_rejected(client, monkeypatch):
    monkeypatch.delenv("ADMIN_UPLOAD_TOKEN", raising=False)
    res = client.post(
        "/api/admin/reference-upload/master_list",
        headers={"x-admin-token": "anything"},
        files={"file": ("m.xlsx", _dummy_xlsx_bytes())},
    )
    assert res.status_code == 403


def test_upload_with_wrong_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv("ADMIN_UPLOAD_TOKEN", "correct-token")
    res = client.post(
        "/api/admin/reference-upload/master_list",
        headers={"x-admin-token": "wrong-token"},
        files={"file": ("m.xlsx", _dummy_xlsx_bytes())},
    )
    assert res.status_code == 403


def test_upload_with_correct_token_writes_file(client, monkeypatch):
    monkeypatch.setenv("ADMIN_UPLOAD_TOKEN", "correct-token")
    res = client.post(
        "/api/admin/reference-upload/master_list",
        headers={"x-admin-token": "correct-token"},
        files={"file": ("m.xlsx", _dummy_xlsx_bytes())},
    )
    assert res.status_code == 200
    assert master_list.MASTER_LIST_PATH.exists()


def test_unknown_key_returns_404(client, monkeypatch):
    monkeypatch.setenv("ADMIN_UPLOAD_TOKEN", "correct-token")
    res = client.post(
        "/api/admin/reference-upload/does_not_exist",
        headers={"x-admin-token": "correct-token"},
        files={"file": ("m.xlsx", _dummy_xlsx_bytes())},
    )
    assert res.status_code == 404
