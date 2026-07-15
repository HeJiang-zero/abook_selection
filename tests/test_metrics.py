from datetime import datetime, timezone
from decimal import Decimal

from app.metrics import calculate_drawdown, calculate_summary_metrics, month_bucket


def test_month_bucket_uses_utc_calendar_months():
    assert month_bucket(datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc)) == "2026-05"
    assert month_bucket(datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)) == "2026-06"


def test_summary_metrics_exclude_funding_and_keep_costs_separate():
    rows = [
        {"profit": Decimal("100"), "storage": Decimal("-5"), "commission": Decimal("-2"), "fee": Decimal("-1"), "action": 0},
        {"profit": Decimal("-40"), "storage": Decimal("-3"), "commission": Decimal("-2"), "fee": Decimal("0"), "action": 1},
        {"profit": Decimal("1000000"), "storage": Decimal("0"), "commission": Decimal("0"), "fee": Decimal("0"), "action": 2},
    ]

    result = calculate_summary_metrics(rows)

    assert result["market_pnl"] == Decimal("60")
    assert result["client_net_pnl"] == Decimal("47")
    assert result["costs"] == Decimal("-13")
    assert result["funding_pnl"] == Decimal("1000000")


def test_drawdown_tracks_peak_to_trough():
    assert calculate_drawdown([Decimal("10"), Decimal("5"), Decimal("12"), Decimal("2")]) == Decimal("10")
