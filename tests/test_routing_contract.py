from decimal import Decimal

from app.service import (
    _account_period_metrics,
    _final_book,
    _percentile,
)


def _month_row(month: str, pnl: float, max_positive_day: float) -> dict:
    return {
        "platform": "mt5",
        "login": 1,
        "account_group": "real\\FPlive",
        "month_start": f"2026-{month}-01",
        "matched_trades": 20,
        "winning_trades": 12,
        "losing_trades": 8,
        "matched_volume": Decimal("1"),
        "matched_market_pnl": Decimal(str(pnl)),
        "market_pnl": Decimal(str(pnl)),
        "gross_wins": Decimal("100"),
        "gross_losses": Decimal("-20"),
        "deal_market_pnl": Decimal(str(pnl)),
        "costs": Decimal("0"),
        "client_net_pnl": Decimal(str(pnl)),
        "funding_pnl": Decimal("0"),
        "active_trade_days": 10,
        "daily_profit_sum": Decimal(str(pnl)),
        "positive_profit_days": 5,
        "negative_profit_days": 5,
        "flat_profit_days": 0,
        "daily_active_days": 10,
        "daily_positive_days": 5,
        "daily_negative_days": 5,
        "daily_flat_days": 0,
        "daily_positive_sum": Decimal(str(max_positive_day + 10)),
        "daily_negative_sum": Decimal("-10"),
        "max_positive_day": Decimal(str(max_positive_day)),
        "min_negative_day": Decimal("-10"),
        "daily_stddev": Decimal("1"),
        "daily_abs_sum": Decimal("100"),
        "avg_holding_seconds": Decimal("60"),
        "median_holding_seconds": Decimal("60"),
        "long_trades": 10,
        "short_trades": 10,
        "symbols_traded": 1,
        "risk_balance_status": "positive",
        "risk_leverage_p95_ratio": 3,
    }


def test_concentration_uses_the_worst_month_not_selection_positive_sum():
    metrics = _account_period_metrics(
        [_month_row("05", 100, 80), _month_row("06", 200, 100)],
        {"platform": "mt5", "login": 1, "account_group": "real"},
        phase="selection",
    )

    assert metrics["max_daily_profit_month_contribution"] == 0.8


def test_percentile_95_is_used_for_leverage_rule():
    assert _percentile([Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("100")], 0.95) == Decimal("80.8")


def test_martingale_always_routes_to_bbook_before_personal_override():
    assert _final_book(martingale_detected=True, personal_candidate=True, abook_rules_pass=True) == "bbook"
    assert _final_book(martingale_detected=False, personal_candidate=True, abook_rules_pass=False) == "abook"
    assert _final_book(martingale_detected=False, personal_candidate=False, abook_rules_pass=False) == "bbook"
