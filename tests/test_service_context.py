import json
from datetime import datetime
from decimal import Decimal

from app.martingale import load_martingale_snapshot
from app.models import AnalysisRules
from app.service import classify_accounts, prepare_analysis_context


def _row(month: str, pnl: int) -> dict:
    return {
        "platform": "mt5",
        "login": 7,
        "account_group": "real",
        "month_start": datetime.fromisoformat(month),
        "matched_trades": 20,
        "winning_trades": 15,
        "losing_trades": 5,
        "matched_volume": Decimal("10"),
        "matched_market_pnl": Decimal(str(pnl)),
        "market_pnl": Decimal(str(pnl)),
        "gross_wins": Decimal("200"),
        "gross_losses": Decimal("-50"),
        "costs": Decimal("-10"),
        "client_net_pnl": Decimal(str(pnl)),
        "funding_pnl": Decimal("0"),
        "active_trade_days": 10,
        "daily_active_days": 10,
        "daily_positive_days": 8,
        "daily_negative_days": 2,
        "daily_flat_days": 0,
        "daily_positive_sum": Decimal("100"),
        "daily_negative_sum": Decimal("-10"),
        "daily_abs_sum": Decimal("110"),
        "daily_profit_sum": Decimal(str(pnl)),
        "max_positive_day": Decimal("10"),
        "min_negative_day": Decimal("-2"),
        "turnover": Decimal("1000"),
        "avg_holding_seconds": Decimal("60"),
        "median_holding_seconds": Decimal("60"),
        "long_trades": 15,
        "short_trades": 5,
        "symbols_traded": 2,
        "positive_profit_days": 8,
        "negative_profit_days": 2,
        "flat_profit_days": 0,
    }


def _snapshot(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "window_type": "7D_SLIDING",
        "records": [{
            "platform": "mt5",
            "login": 7,
            "risk_level": "high",
            "layer_hits": {"layer1": True, "layer2": True, "layer3": True, "layer4": True, "layer5": False},
        }],
    }))
    return load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])


def test_rules_default_to_blocking_three_martingale_levels():
    rules = AnalysisRules()

    assert rules.excluded_martingale_levels == ["extreme", "high", "medium"]


def test_martingale_block_wins_over_personal_candidate_override(tmp_path):
    context = prepare_analysis_context(
        [_row("2026-05-01", 120), _row("2026-06-01", 100), _row("2026-07-01", 80)],
        selection_start="2026-05-01",
        selection_end="2026-06-30",
        validation_start="2026-07-01",
        validation_end="2026-07-13",
    )

    account = classify_accounts(context, AnalysisRules(), {7}, _snapshot(tmp_path))[0]

    assert account["cohort"] != "abook_candidate"
    assert account["selection_source"] == "martingale_blocked"
