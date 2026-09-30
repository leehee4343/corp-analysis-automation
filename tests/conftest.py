import pytest


@pytest.fixture(autouse=True)
def _never_touch_real_database(monkeypatch):
    """테스트가 실제 Supabase(DATABASE_URL)에 쓰거나 지우지 않도록 항상 SQLite(tmp_path)로 격리한다.
    과거 테스트가 실제 참고자료 파일을 덮어쓴 사고가 있었다(PLAN.md 2026-08-18 참고)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
