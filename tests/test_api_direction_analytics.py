from fastapi.testclient import TestClient

from app.main import app, get_repository


def test_direction_analytics_endpoint_reuses_analysis_session_and_queries_matched_directions(tmp_path, monkeypatch):
    for name in (
        "ABOOK_RISK_SNAPSHOT_PATH",
        "ABOOK_MARTINGALE_SNAPSHOT_PATH",
        "ABOOK_AVG_PROFIT_SNAPSHOT_PATH",
        "ABOOK_R4_SNAPSHOT_PATH",
    ):
        monkeypatch.setenv(name, str(tmp_path / f"{name}.json"))

    class SpyRepository:
        def __init__(self):
            self.analysis_calls = 0
            self.direction_calls = 0

        def fetch_analysis(self, request, excluded_logins=None):
            self.analysis_calls += 1
            return []

        def fetch_direction_matched_facts(self, request):
            self.direction_calls += 1
            return []

    repository = SpyRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    try:
        overview = TestClient(app).post("/api/abook/analysis", json={"platforms": ["mt5"]})
        assert overview.status_code == 200
        token = overview.json()["analysis_token"]
        response = TestClient(app).post(
            "/api/abook/direction-analytics",
            json={"analysis": {"platforms": ["mt5"]}, "analysis_token": token},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["accounts"] == []
    assert repository.analysis_calls == 1
    assert repository.direction_calls == 1
