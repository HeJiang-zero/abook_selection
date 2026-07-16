from fastapi.testclient import TestClient

from app.main import app, get_repository


def test_book_analytics_endpoint_returns_four_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("ABOOK_MARTINGALE_SNAPSHOT_PATH", str(tmp_path / "missing.json"))

    class FakeRepository:
        def fetch_analysis(self, request, excluded_logins=None):
            return []

        def fetch_daily_pnl(self, request, excluded_logins=None):
            return []

    app.dependency_overrides[get_repository] = lambda: FakeRepository()
    try:
        response = TestClient(app).post("/api/abook/book-analytics", json={"analysis": {"platforms": ["mt5"]}})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert set(response.json()) >= {"pnl_structure", "user_structure", "risk_exposure", "routing_quality"}
