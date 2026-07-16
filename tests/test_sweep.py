from datetime import datetime
from decimal import Decimal

import pytest

from app.models import AnalysisRules
from app.service import prepare_analysis_context
from app.sweep import evaluate_sweep, expand_rule_grid


def _row(login: int, month: str, pnl: int, wins: int = 1) -> dict:
    losses = 2 - wins
    return {
        "platform": "mt5", "login": login, "account_group": "real",
        "month_start": datetime.fromisoformat(month), "matched_trades": 2,
        "winning_trades": wins, "losing_trades": losses, "matched_volume": Decimal("2"),
        "matched_market_pnl": Decimal(str(pnl)), "market_pnl": Decimal(str(pnl)),
        "gross_wins": Decimal("20"), "gross_losses": Decimal("-10"),
        "costs": Decimal("0"), "client_net_pnl": Decimal(str(pnl)), "funding_pnl": Decimal("0"),
        "active_trade_days": 2, "daily_active_days": 2, "daily_positive_days": 1,
        "daily_negative_days": 1, "daily_flat_days": 0, "daily_positive_sum": Decimal("10"),
        "daily_negative_sum": Decimal("-5"), "daily_abs_sum": Decimal("15"),
        "daily_profit_sum": Decimal(str(pnl)), "max_positive_day": Decimal("10"),
        "min_negative_day": Decimal("-5"), "turnover": Decimal("1000"),
        "avg_holding_seconds": Decimal("60"), "median_holding_seconds": Decimal("60"),
        "long_trades": 1, "short_trades": 1, "symbols_traded": 1,
        "positive_profit_days": 1, "negative_profit_days": 1, "flat_profit_days": 0,
    }


def _rules() -> AnalysisRules:
    return AnalysisRules(
        min_trades=0, min_active_days=0, min_win_rate=0.5,
        min_profit_factor=0, min_payoff_ratio=0, min_avg_daily_profit=0,
        min_selection_monthly_consistency=0, min_positive_month_rate=0,
        max_top1_day_profit_contribution=1, max_peak_leverage_ratio=200,
        min_direction_day_rate_lower_bound=0, min_stability_score=0,
        high_confidence_trades=0, high_confidence_days=0,
    )


def _context():
    rows = [
        _row(1, "2026-05-01", 20), _row(1, "2026-06-01", 20), _row(1, "2026-07-01", 30),
        _row(2, "2026-05-01", 20), _row(2, "2026-06-01", 20), _row(2, "2026-07-01", -25, wins=0),
    ]
    return prepare_analysis_context(
        rows, selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
    )


def test_sweep_rejects_more_than_500_combinations():
    with pytest.raises(ValueError, match="500"):
        expand_rule_grid({"min_win_rate": [0.5] * 501}, AnalysisRules())


def test_sweep_reports_validation_increment_and_misjudge_cost():
    result = evaluate_sweep(_context(), _rules(), {"min_win_rate": [0.5]}, "validation_increment", None)

    row = result["results"][0]
    assert row["abook_core"] == 2
    assert row["misjudge_cost"] == 25.0
    assert row["validation_increment"] == 5.0
