import base64

import pytest
from fastapi.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


def _basic(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_no_password_env_var_means_no_auth_required(client, monkeypatch):
    monkeypatch.delenv("APP_LOGIN_PASSWORD", raising=False)
    res = client.get("/")
    assert res.status_code == 200


def test_password_set_blocks_unauthenticated_request(client, monkeypatch):
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "1234")
    res = client.get("/")
    assert res.status_code == 401
    assert "WWW-Authenticate" in res.headers


def test_password_set_blocks_wrong_credentials(client, monkeypatch):
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "1234")
    res = client.get("/", headers=_basic("admin", "wrong"))
    assert res.status_code == 401


def test_password_set_allows_correct_credentials(client, monkeypatch):
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "1234")
    res = client.get("/", headers=_basic("admin", "1234"))
    assert res.status_code == 200


def test_custom_username_via_env_var(client, monkeypatch):
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "1234")
    monkeypatch.setenv("APP_LOGIN_USER", "sales")
    assert client.get("/", headers=_basic("admin", "1234")).status_code == 401
    assert client.get("/", headers=_basic("sales", "1234")).status_code == 200
