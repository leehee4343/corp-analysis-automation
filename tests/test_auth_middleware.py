"""로그인(세션 쿠키) 테스트. APP_LOGIN_PASSWORD가 있을 때만 로그인을 강제한다."""
import pytest
from fastapi.testclient import TestClient

from backend import auth_middleware as auth
from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "1234")
    monkeypatch.delenv("APP_LOGIN_USER", raising=False)
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)


def test_no_password_env_var_means_no_login_required(client, monkeypatch):
    monkeypatch.delenv("APP_LOGIN_PASSWORD", raising=False)
    assert client.get("/").status_code == 200
    assert client.get("/api/session").json() == {"auth_enabled": False, "user": None}


def test_unauthenticated_page_redirects_to_login_and_api_is_401(client, secured):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/login"
    assert client.get("/api/companies").status_code == 401
    assert client.get("/login").status_code == 200  # 로그인 화면은 열린다


def test_wrong_credentials_rejected(client, secured):
    assert client.post("/api/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"username": "sales", "password": "1234"}).status_code == 401


def test_login_then_logout(client, secured):
    res = client.post("/api/login", json={"username": "admin", "password": "1234"})
    assert res.status_code == 200 and auth.COOKIE_NAME in res.cookies
    assert client.get("/").status_code == 200
    assert client.get("/api/session").json() == {"auth_enabled": True, "user": "admin"}
    assert client.get("/login", follow_redirects=False).status_code == 303  # 이미 로그인했으면 메인으로

    client.post("/api/logout")
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/companies").status_code == 401


def test_custom_username_via_env_var(client, secured, monkeypatch):
    monkeypatch.setenv("APP_LOGIN_USER", "sales")
    assert client.post("/api/login", json={"username": "admin", "password": "1234"}).status_code == 401
    assert client.post("/api/login", json={"username": "sales", "password": "1234"}).status_code == 200


def test_tampered_or_expired_token_rejected(secured):
    token = auth.make_session_token("admin")
    assert auth.session_user(token) == "admin"
    assert auth.session_user(token[:-2] + "00") is None  # 서명 변조
    assert auth.session_user(auth.make_session_token("admin", now=0)) is None  # 만료
    assert auth.session_user("garbage") is None


def test_changing_password_invalidates_sessions(secured, monkeypatch):
    token = auth.make_session_token("admin")
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "5678")
    assert auth.session_user(token) is None
