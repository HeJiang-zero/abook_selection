from fastapi.testclient import TestClient

from app.main import app, get_repository


def test_sweep_endpoint_returns_ranked_results_from_one_fake_dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("ABOOK_MARTINGALE_SNAPSHOT_PATH", str(tmp_path / "missing.json"))

    class FakeRepository:
        def fetch_analysis(self, request, excluded_logins=None):
            return []

        def fetch_daily_pnl(self, request, excluded_logins=None):
            return []

    app.dependency_overrides[get_repository] = lambda: FakeRepository()
    try:
        response = TestClient(app).post("/api/abook/sweep", json={
            "analysis": {"platforms": ["mt5"]},
            "grid": {"min_win_rate": [0.5, 0.6]},
            "objective": "validation_increment",
        })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["combinations"] == 2
    assert len(response.json()["results"]) == 2
