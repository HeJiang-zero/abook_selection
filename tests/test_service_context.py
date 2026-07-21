import json
from datetime import datetime
from decimal import Decimal

from app.martingale import load_martingale_snapshot
from app.models import AnalysisRules
from app.service import _daily_group_drawdown, build_misjudge_summary, build_two_stage_payload, classify_accounts, prepare_analysis_context


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
            "martingale_detection_status": "confirmed",
            "confirmed_windows": 2,
            "confirmed_extreme_windows": 0,
            "expanded_windows": 0,
            "layer_hits": {"layer1": True, "layer2": True, "layer3": True, "layer4": True, "layer5": False},
        }],
    }))
    return load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])


def test_rules_default_to_blocking_all_martingale_levels():
    rules = AnalysisRules()

    assert rules.excluded_martingale_levels == ["extreme", "high", "medium", "low"]


def test_martingale_block_wins_over_personal_candidate_override(tmp_path):
    context = prepare_analysis_context(
        [_row("2026-05-01", 120), _row("2026-06-01", 100), _row("2026-07-01", 80)],
        selection_start="2026-05-01",
        selection_end="2026-06-30",
        validation_start="2026-07-01",
        validation_end="2026-07-13",
    )

    account = classify_accounts(context, AnalysisRules(), {7}, _snapshot(tmp_path))[0]

    assert account["book"] == "bbook"
    assert account["selection_source"] == "martingale_blocked"


def test_phase_tagged_same_month_rows_are_not_counted_in_both_periods():
    selection_row = _row("2026-06-01", 120)
    selection_row["phase"] = "selection"
    validation_row = _row("2026-06-01", -80)
    validation_row["phase"] = "validation"

    payload = build_two_stage_payload(
        [selection_row, validation_row],
        selection_start="2026-06-01",
        selection_end="2026-06-15",
        validation_start="2026-06-16",
        validation_end="2026-06-30",
    )

    account = payload["accounts"][0]
    assert account["selection"]["client_net_pnl"] == 120.0
    assert account["validation"]["client_net_pnl"] == -80.0


def test_group_drawdown_uses_chronological_account_day_rows():
    accounts = [{"platform": "mt5", "login": 1}, {"platform": "mt5", "login": 2}, {"platform": "mt5", "login": 3}]
    daily_rows = [
        {"platform": "mt5", "login": 1, "trade_date": "2026-07-01", "client_net_pnl": -50},
        {"platform": "mt5", "login": 2, "trade_date": "2026-07-02", "client_net_pnl": 100},
        {"platform": "mt5", "login": 3, "trade_date": "2026-07-03", "client_net_pnl": -50},
    ]

    assert _daily_group_drawdown(accounts, daily_rows, "2026-07-01", "2026-07-13") == 50


def test_bbook_leakage_contains_selection_pnl_for_month_over_month_comparison():
    summary = build_misjudge_summary([
        {
            "platform": "mt5",
            "login": 7,
            "account_group": "real",
            "book": "bbook",
            "selection": {"client_net_pnl": 120.0},
            "validation": {"client_net_pnl": 80.0},
            "monthly": [
                {"month": "2026-05", "client_net_pnl": 20.0},
                {"month": "2026-06", "client_net_pnl": 45.0},
            ],
            "selection_source": "abook_rules_failed",
        }
    ])

    row = summary["bbook_profitable"][0]
    assert row["may_client_net_pnl"] == 20.0
    assert row["june_client_net_pnl"] == 45.0
    assert row["validation_client_net_pnl"] == 80.0


def test_bbook_leakage_exposes_readable_reason_tags():
    summary = build_misjudge_summary([
        {
            "platform": "mt5",
            "login": 8,
            "account_group": "real",
            "book": "bbook",
            "selection": {"client_net_pnl": 120.0},
            "validation": {"client_net_pnl": 180.0},
            "monthly": [],
            "selection_source": "martingale_blocked",
            "abook_rules_pass": False,
            "selection_flags": ["leverage_p95_ratio"],
            "martingale_blocked": True,
            "martingale_hard_block": True,
            "martingale_risk_level": "high",
        }
    ])

    tags = summary["bbook_profitable"][0]["bbook_reason_tags"]

    assert any("确认马丁" in tag for tag in tags)
    assert "Abook规则未通过" in tags
    assert "杠杆 P95 超限" in tags
