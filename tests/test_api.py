from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app, get_repository


client = TestClient(app)


def test_dashboard_shell_is_served():
    response = client.get("/")

    assert response.status_code == 200
    assert "三个月账户回溯" in response.text


def test_health_endpoint_reports_service_status():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_rejects_unsupported_lookback_months():
    response = client.post("/api/abook/analysis", json={"lookback_months": 4})

    assert response.status_code == 422


def test_analysis_returns_dashboard_payload_from_repository_rows():
    class FakeRepository:
        def fetch_analysis(self, request, excluded_logins=None):
            return [{
                "platform": "mt5", "login": 1, "account_group": "real", "country": "Brazil",
                "leverage": 100, "registration": datetime(2026, 1, 1), "last_access": datetime(2026, 7, 1),
                "balance": Decimal("1000"), "equity_prev_day": Decimal("1000"), "agent": 0, "client_id": 1,
                "lead_source": "", "lead_campaign": "", "month_start": datetime(2026, 7, 1),
                "matched_trades": 1, "winning_trades": 1, "losing_trades": 0, "matched_volume": Decimal("1"),
                "matched_market_pnl": Decimal("10"), "deal_market_pnl": Decimal("10"), "gross_wins": Decimal("10"),
                "gross_losses": Decimal("-5"), "costs": Decimal("-1"), "client_net_pnl": Decimal("9"),
                "funding_pnl": Decimal("0"), "turnover": Decimal("100"), "avg_holding_seconds": Decimal("5"),
                "median_holding_seconds": Decimal("5"), "long_trades": 1, "short_trades": 0, "symbols_traded": 1,
                "active_trade_days": 1, "daily_profit_sum": Decimal("11"),
            }]

    app.dependency_overrides[get_repository] = lambda: FakeRepository()
    try:
        response = client.post("/api/abook/analysis", json={"lookback_months": 1})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["kpis"]["client_net_pnl"] == 9.0


def test_analysis_returns_two_stage_payload_for_new_request():
    class FakeRepository:
        def fetch_analysis(self, request, excluded_logins=None):
            rows = []
            for month, net, market in (("2026-05-01", 120, 130), ("2026-06-01", 100, 110), ("2026-07-01", 70, 80)):
                rows.append({
                    "platform": "mt5", "login": 7, "account_group": "real\\FPlive", "month_start": datetime.fromisoformat(month),
                    "matched_trades": 20, "winning_trades": 15, "losing_trades": 5, "matched_volume": Decimal("1"),
                    "matched_market_pnl": Decimal(str(market)), "deal_market_pnl": Decimal(str(market)),
                    "gross_wins": Decimal("180"), "gross_losses": Decimal("-60"), "costs": Decimal("-10"),
                    "client_net_pnl": Decimal(str(net)), "funding_pnl": Decimal("0"), "active_trade_days": 10,
                    "daily_profit_sum": Decimal(str(net)), "positive_profit_days": 8, "negative_profit_days": 2,
                    "daily_positive_sum": Decimal("100"), "daily_negative_sum": Decimal("-10"),
                    "max_positive_day": Decimal("10"), "min_negative_day": Decimal("-2"),
                    "flat_profit_days": 0, "turnover": Decimal("100"), "avg_holding_seconds": Decimal("5"),
                    "median_holding_seconds": Decimal("5"), "long_trades": 15, "short_trades": 5, "symbols_traded": 1,
                })
            return rows

    app.dependency_overrides[get_repository] = lambda: FakeRepository()
    try:
        response = client.post(
            "/api/abook/analysis",
            json={"rules": {"min_stability_score": 72, "max_top1_day_profit_contribution": 0.4}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["selection"]["counts"]["abook_candidates"] == 1
    assert body["coverage"]["validation_partial"] is True
    assert body["rules"]["min_stability_score"] == 72
    assert body["rules"]["max_top1_day_profit_contribution"] == 0.4
