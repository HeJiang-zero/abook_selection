from datetime import datetime
from decimal import Decimal
import json
import math

from app.service import _account_period_metrics, build_two_stage_payload


def row(login, month, *, group="real\\FPlive", trades=0, wins=0, losses=0,
        market=0, net=0, costs=0, gross_wins=0, gross_losses=0,
        active_days=0, daily_sum=0, volume=0, turnover=0,
        daily_positive_days=None, daily_negative_days=None, daily_flat_days=None,
        daily_positive_sum=None, daily_negative_sum=None, max_positive_day=None,
        daily_stddev=0, daily_abs_sum=None, source_min=None, source_max=None):
    daily_positive_days = active_days if daily_positive_days is None else daily_positive_days
    daily_negative_days = 0 if daily_negative_days is None else daily_negative_days
    daily_flat_days = 0 if daily_flat_days is None else daily_flat_days
    daily_positive_sum = max(daily_sum, 0) if daily_positive_sum is None else daily_positive_sum
    daily_negative_sum = min(daily_sum, 0) if daily_negative_sum is None else daily_negative_sum
    max_positive_day = daily_positive_sum if max_positive_day is None else max_positive_day
    return {
        "platform": "mt5",
        "login": login,
        "account_group": group,
        "month_start": datetime.fromisoformat(f"2026-{month}-01"),
        "matched_trades": trades,
        "winning_trades": wins,
        "losing_trades": losses,
        "matched_volume": Decimal(str(volume)),
        "matched_market_pnl": Decimal(str(market)),
        "gross_wins": Decimal(str(gross_wins)),
        "gross_losses": Decimal(str(gross_losses)),
        "deal_market_pnl": Decimal(str(market)),
        "costs": Decimal(str(costs)),
        "client_net_pnl": Decimal(str(net)),
        "funding_pnl": Decimal("0"),
        "active_trade_days": active_days,
        "daily_profit_sum": Decimal(str(daily_sum)),
        "positive_profit_days": max(active_days, 0),
        "negative_profit_days": 0,
        "flat_profit_days": 0,
        "daily_active_days": active_days,
        "daily_positive_days": daily_positive_days,
        "daily_negative_days": daily_negative_days,
        "daily_flat_days": daily_flat_days,
        "daily_positive_sum": Decimal(str(daily_positive_sum)),
        "daily_negative_sum": Decimal(str(daily_negative_sum)),
        "max_positive_day": Decimal(str(max_positive_day)),
        "daily_stddev": Decimal(str(daily_stddev)),
        "daily_abs_sum": Decimal(str(abs(daily_abs_sum if daily_abs_sum is not None else daily_sum))),
        "source_matched_min": source_min,
        "source_matched_max": source_max,
        "source_deal_min": source_min,
        "source_deal_max": source_max,
        "turnover": Decimal(str(turnover)),
        "avg_holding_seconds": Decimal("60"),
        "median_holding_seconds": Decimal("60"),
        "long_trades": wins,
        "short_trades": losses,
        "symbols_traded": 1,
    }


def test_two_stage_analysis_separates_selection_and_validation_and_keeps_inactive_users():
    rows = [
        row(1, "05", trades=20, wins=15, losses=5, market=120, net=110,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=110),
        row(1, "06", trades=20, wins=14, losses=6, market=100, net=90,
            gross_wins=160, gross_losses=-60, active_days=8, daily_sum=90),
        # Login 1 has no July row in the source; service must materialize it as inactive.
        row(2, "05", trades=20, wins=4, losses=16, market=-120, net=-110,
            gross_wins=40, gross_losses=-160, active_days=10, daily_sum=-110),
        row(2, "06", trades=20, wins=5, losses=15, market=-100, net=-90,
            gross_wins=50, gross_losses=-150, active_days=8, daily_sum=-90),
        row(2, "07", trades=2, wins=1, losses=1, market=-20, net=-20,
            gross_wins=5, gross_losses=-25, active_days=1, daily_sum=-20),
        row(3, "05", trades=2, wins=1, losses=1, market=5, net=4,
            gross_wins=10, gross_losses=-5, active_days=1, daily_sum=4),
        row(3, "06", trades=2, wins=1, losses=1, market=5, net=4,
            gross_wins=10, gross_losses=-5, active_days=1, daily_sum=4),
        row(4, "05", group="real\\TEST_USD", trades=20, wins=15, losses=5,
            market=120, net=100, gross_wins=180, gross_losses=-60,
            active_days=10, daily_sum=100),
        row(4, "06", group="real\\TEST_USD", trades=20, wins=15, losses=5,
            market=120, net=100, gross_wins=180, gross_losses=-60,
            active_days=10, daily_sum=100),
    ]

    result = build_two_stage_payload(
        rows,
        selection_start="2026-05-01",
        selection_end="2026-06-30",
        validation_start="2026-07-01",
        validation_end="2026-07-13",
        min_trades=20,
        min_active_days=5,
        min_profit_factor=1,
        min_avg_daily_profit=10,
        neutral_band_usd=10,
        min_positive_month_rate=0,
        max_top1_day_profit_contribution=1,
        min_direction_day_rate_lower_bound=0,
        min_stability_score=0,
    )

    assert result["selection"]["counts"] == {
        "eligible_accounts": 3,
        "unique_accounts": 3,
        "account_rows": 3,
        "abook_candidates": 1,
        "bbook_candidates": 1,
        "directional_abook_candidates": 1,
        "directional_bbook_candidates": 1,
        "observation": 1,
    }
    accounts = {account["login"]: account for account in result["accounts"]}
    assert accounts[1]["cohort"] == "abook_candidate"
    assert accounts[1]["validation_status"] == "inactive"
    assert accounts[2]["cohort"] == "bbook_candidate"
    assert accounts[2]["transition_status"] == "continued_loss"
    assert 4 not in accounts
    assert result["validation"]["groups"]["abook_candidate"]["active_accounts"] == 0


def test_two_stage_analysis_reports_transition_precision_lift_and_abook_delta():
    rows = [
        row(1, "05", trades=20, wins=15, losses=5, market=120, net=110,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=110),
        row(1, "06", trades=20, wins=14, losses=6, market=100, net=90,
            gross_wins=160, gross_losses=-60, active_days=8, daily_sum=90),
        row(1, "07", trades=10, wins=8, losses=2, market=80, net=70,
            gross_wins=100, gross_losses=-20, active_days=5, daily_sum=70),
        row(2, "05", trades=20, wins=4, losses=16, market=-120, net=-110,
            gross_wins=40, gross_losses=-160, active_days=10, daily_sum=-110),
        row(2, "06", trades=20, wins=5, losses=15, market=-100, net=-90,
            gross_wins=50, gross_losses=-150, active_days=8, daily_sum=-90),
        row(2, "07", trades=10, wins=2, losses=8, market=-70, net=-60,
            gross_wins=20, gross_losses=-90, active_days=5, daily_sum=-60),
        row(3, "05", trades=20, wins=10, losses=10, market=20, net=5,
            gross_wins=50, gross_losses=-30, active_days=5, daily_sum=5),
        row(3, "06", trades=20, wins=10, losses=10, market=20, net=5,
            gross_wins=50, gross_losses=-30, active_days=5, daily_sum=5),
        row(3, "07", trades=10, wins=6, losses=4, market=40, net=30,
            gross_wins=60, gross_losses=-20, active_days=5, daily_sum=30),
    ]

    result = build_two_stage_payload(
        rows,
        selection_start="2026-05-01",
        selection_end="2026-06-30",
        validation_start="2026-07-01",
        validation_end="2026-07-13",
        min_trades=20,
        min_active_days=5,
        min_profit_factor=1,
        min_avg_daily_profit=10,
        min_positive_month_rate=0,
        max_top1_day_profit_contribution=1,
        min_direction_day_rate_lower_bound=0,
        min_stability_score=0,
    )

    assert result["transitions"]["abook_candidate"]["continued_profitable"] == 1
    assert result["transitions"]["bbook_candidate"]["continued_loss"] == 1
    assert result["validation"]["groups"]["abook_candidate"]["precision"] == 1.0
    assert result["validation"]["groups"]["bbook_candidate"]["precision"] == 1.0
    assert result["profit_impact"]["abook_candidate"]["selection_client_net_pnl"] == 200.0
    assert result["profit_impact"]["abook_candidate"]["incremental_change"] == 200.0
    assert result["profit_impact"]["bbook_candidate"]["incremental_change"] == -200.0
    json.dumps(result, allow_nan=False)


def test_two_stage_analysis_requires_win_rate_monthly_consistency_and_risk_concentration():
    strong = [
        row(21, "05", trades=20, wins=14, losses=6, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            volume=100),
        row(21, "06", trades=20, wins=13, losses=7, market=80, net=60,
            gross_wins=150, gross_losses=-50, active_days=10, daily_sum=60,
            volume=100),
    ]
    weak_month = [
        row(22, "05", trades=20, wins=14, losses=6, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            volume=100),
        row(22, "06", trades=20, wins=13, losses=7, market=20, net=20,
            gross_wins=150, gross_losses=-130, active_days=10, daily_sum=20,
            volume=100),
    ]
    oversized = [
        row(23, "05", trades=20, wins=14, losses=6, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            volume=100, max_positive_day=150),
        row(23, "06", trades=20, wins=13, losses=7, market=80, net=60,
            gross_wins=150, gross_losses=-50, active_days=10, daily_sum=60,
            volume=100, max_positive_day=150),
    ]
    result = build_two_stage_payload(
        strong + weak_month + oversized,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
        min_trades=20, min_active_days=5, min_profit_factor=1,
        min_avg_daily_profit=0, min_win_rate=0.6,
        min_selection_monthly_consistency=0.5,
        min_positive_month_rate=0, max_top1_day_profit_contribution=0.75,
        min_direction_day_rate_lower_bound=0, min_stability_score=0,
    )

    accounts = {account["login"]: account for account in result["accounts"]}
    assert accounts[21]["cohort"] == "abook_candidate"
    assert accounts[22]["base_cohort"] == "observation"
    assert accounts[23]["base_cohort"] == "observation"
    assert accounts[21]["selection"]["monthly_consistency_ratio"] == 0.6


def test_two_stage_analysis_requires_strict_top1_contribution_and_skips_leverage_for_zero_balance():
    diffuse = [
        row(31, "05", trades=20, wins=15, losses=5, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=19),
        row(31, "06", trades=20, wins=14, losses=6, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=19),
    ]
    exactly_twenty = [
        row(32, "05", trades=20, wins=15, losses=5, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=40),
        row(32, "06", trades=20, wins=14, losses=6, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=40),
    ]
    high_leverage = [
        row(33, "05", trades=20, wins=15, losses=5, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=19),
        row(33, "06", trades=20, wins=14, losses=6, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=19),
    ]
    zero_balance = [
        row(34, "05", trades=20, wins=15, losses=5, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=19),
        row(34, "06", trades=20, wins=14, losses=6, market=120, net=100,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=100,
            daily_positive_sum=100, max_positive_day=19),
    ]
    for item in high_leverage:
        item.update(risk_balance_prev_month=100, risk_balance_status="positive", risk_peak_leverage_ratio=8)
    for item in zero_balance:
        item.update(risk_balance_prev_month=0, risk_balance_status="unknown_nonpositive_balance", risk_peak_leverage_ratio=None)

    result = build_two_stage_payload(
        diffuse + exactly_twenty + high_leverage + zero_balance,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
        min_trades=20, min_active_days=5, min_profit_factor=1,
        min_avg_daily_profit=0, min_win_rate=0.5,
        min_selection_monthly_consistency=0.5,
        max_top1_day_profit_contribution=0.2, max_peak_leverage_ratio=5,
        min_positive_month_rate=0, min_direction_day_rate_lower_bound=0,
        min_stability_score=0,
    )

    accounts = {account["login"]: account for account in result["accounts"]}
    assert accounts[31]["cohort"] == "abook_candidate"
    assert accounts[32]["base_cohort"] == "observation"
    assert accounts[33]["base_cohort"] == "observation"
    assert accounts[34]["cohort"] == "abook_candidate"


def test_two_stage_analysis_keeps_test_accounts_excluded_even_when_override_is_false():
    rows = [row(99, "05", group="real\\TEST", trades=20, wins=15, losses=5, market=120, net=110,
                gross_wins=180, gross_losses=-60, active_days=10, daily_sum=110)]
    rows.append(row(99, "06", group="real\\TEST", trades=20, wins=15, losses=5, market=120, net=110,
                    gross_wins=180, gross_losses=-60, active_days=10, daily_sum=110))

    result = build_two_stage_payload(
        rows,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
        min_positive_month_rate=0,
        max_top1_day_profit_contribution=1,
        min_direction_day_rate_lower_bound=0,
        min_stability_score=0,
        exclude_test_accounts=False,
    )

    assert result["selection"]["counts"]["eligible_accounts"] == 0


def test_two_stage_analysis_excludes_demo_accounts_by_default():
    rows = [row(100, "05", group="demo\\HHdemo\\forexhh-USD", trades=20, wins=15, losses=5,
                market=120, net=110, gross_wins=180, gross_losses=-60, active_days=10, daily_sum=110)]

    result = build_two_stage_payload(
        rows,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
        min_positive_month_rate=0,
        max_top1_day_profit_contribution=1,
        min_direction_day_rate_lower_bound=0,
        min_stability_score=0,
    )

    assert result["selection"]["counts"]["eligible_accounts"] == 0


def test_two_stage_analysis_reports_raw_and_active_deal_coverage_separately():
    item = row(101, "05", source_min="2026-05-15", source_max="2026-07-14")
    item["source_deal_raw_min"] = "2023-08-08"
    item["source_deal_raw_max"] = "2026-07-14"
    item["source_deal_deleted_rows"] = 123

    result = build_two_stage_payload(
        [item],
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
    )

    assert result["coverage"]["source_min"] == "2026-05-15"
    assert result["coverage"]["source_deal_raw_min"] == "2023-08-08"
    assert result["coverage"]["source_deal_deleted_rows"] == 123
    assert result["coverage"]["historical_deals_before_active"] is True


def test_two_stage_analysis_exposes_monthly_company_profit_and_july_book_split():
    rows = [
        row(1, "05", trades=20, wins=15, losses=5, market=120, net=110,
            gross_wins=180, gross_losses=-60, active_days=10, daily_sum=110),
        row(1, "06", trades=20, wins=14, losses=6, market=100, net=90,
            gross_wins=160, gross_losses=-60, active_days=8, daily_sum=90),
        row(1, "07", trades=10, wins=8, losses=2, market=80, net=70,
            gross_wins=100, gross_losses=-20, active_days=5, daily_sum=70),
        row(2, "05", trades=20, wins=4, losses=16, market=-120, net=-110,
            gross_wins=40, gross_losses=-160, active_days=10, daily_sum=-110),
        row(2, "06", trades=20, wins=5, losses=15, market=-100, net=-90,
            gross_wins=50, gross_losses=-150, active_days=8, daily_sum=-90),
        row(2, "07", trades=10, wins=2, losses=8, market=-70, net=-60,
            gross_wins=20, gross_losses=-90, active_days=5, daily_sum=-60),
    ]
    result = build_two_stage_payload(
        rows,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
        min_positive_month_rate=0,
        max_top1_day_profit_contribution=1,
        min_direction_day_rate_lower_bound=0,
        min_stability_score=0,
    )

    monthly = {item["month"]: item for item in result["profit_overview"]["monthly"]}
    assert monthly["2026-05"]["company_bbook_profit"] == 0.0
    assert monthly["2026-06"]["company_bbook_profit"] == 0.0
    assert result["profit_overview"]["july_book_split"]["abook"]["user_net_pnl"] == 70.0
    assert result["profit_overview"]["july_book_split"]["book"]["company_profit"] == 60.0


def test_two_stage_analysis_uses_source_unique_account_count_and_hides_zero_pnl_accounts():
    zero = row(9, "05")
    zero["population_unique_accounts"] = 1
    zero["population_account_rows"] = 1
    active = row(9, "06", trades=1, wins=1, losses=0, market=5, net=5,
                 gross_wins=5, gross_losses=0, active_days=1, daily_sum=5)
    active["population_unique_accounts"] = 1
    active["population_account_rows"] = 1
    result = build_two_stage_payload(
        [zero, active],
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
    )

    assert result["selection"]["counts"]["unique_accounts"] == 1
    assert [account["login"] for account in result["accounts"]] == [9]


def test_two_stage_analysis_scores_stability_and_penalizes_one_day_concentration():
    rows = [
        row(10, "05", trades=40, wins=26, losses=14, market=150, net=130,
            gross_wins=240, gross_losses=-90, active_days=12, daily_sum=130,
            daily_positive_days=8, daily_negative_days=4, daily_positive_sum=120,
            daily_negative_sum=-30, max_positive_day=150, daily_stddev=32,
            daily_abs_sum=150, source_min="2026-05-15", source_max="2026-07-14"),
        row(10, "06", trades=40, wins=26, losses=14, market=150, net=130,
            gross_wins=240, gross_losses=-90, active_days=12, daily_sum=130,
            daily_positive_days=8, daily_negative_days=4, daily_positive_sum=120,
            daily_negative_sum=-30, max_positive_day=150, daily_stddev=32,
            daily_abs_sum=150, source_min="2026-05-15", source_max="2026-07-14"),
        row(11, "05", trades=40, wins=26, losses=14, market=150, net=130,
            gross_wins=240, gross_losses=-90, active_days=12, daily_sum=130,
            daily_positive_days=8, daily_negative_days=4, daily_positive_sum=120,
            daily_negative_sum=-30, max_positive_day=30, daily_stddev=12,
            daily_abs_sum=150, source_min="2026-05-15", source_max="2026-07-14"),
        row(11, "06", trades=40, wins=26, losses=14, market=150, net=130,
            gross_wins=240, gross_losses=-90, active_days=12, daily_sum=130,
            daily_positive_days=8, daily_negative_days=4, daily_positive_sum=120,
            daily_negative_sum=-30, max_positive_day=30, daily_stddev=12,
            daily_abs_sum=150, source_min="2026-05-15", source_max="2026-07-14"),
    ]

    result = build_two_stage_payload(
        rows,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
        min_trades=20, min_active_days=5,
    )

    accounts = {account["login"]: account for account in result["accounts"]}
    concentrated = accounts[10]
    stable = accounts[11]
    assert concentrated["stability"]["top_positive_day_concentration"] > 0.5
    assert "profit_concentration" in concentrated["selection_flags"]
    assert stable["stability"]["score"] > concentrated["stability"]["score"]
    assert stable["confidence_tier"] in {"medium", "high"}
    assert result["selection"]["stability_overview"]["abook_core_or_watch"] >= 1
    assert result["coverage"]["source_min"] == "2026-05-15"
    assert "2026-05" in result["coverage"]["partial_months"]


def test_two_stage_analysis_only_deploys_stable_candidates_and_uses_active_precision():
    rows = [
        row(21, "05", trades=60, wins=42, losses=18, market=560, net=500,
            gross_wins=900, gross_losses=-250, active_days=40, daily_sum=500,
            daily_positive_days=34, daily_negative_days=6, daily_positive_sum=550,
            daily_negative_sum=-50, max_positive_day=80, daily_stddev=18,
            daily_abs_sum=600),
        row(21, "06", trades=60, wins=42, losses=18, market=560, net=500,
            gross_wins=900, gross_losses=-250, active_days=40, daily_sum=500,
            daily_positive_days=34, daily_negative_days=6, daily_positive_sum=550,
            daily_negative_sum=-50, max_positive_day=80, daily_stddev=18,
            daily_abs_sum=600),
        row(21, "07", trades=30, wins=22, losses=8, market=250, net=150,
            gross_wins=400, gross_losses=-120, active_days=20, daily_sum=150,
            daily_positive_days=12, daily_negative_days=8, daily_positive_sum=190,
            daily_negative_sum=-40, max_positive_day=30, daily_stddev=15,
            daily_abs_sum=230),
        row(22, "05", trades=60, wins=42, losses=18, market=560, net=500,
            gross_wins=900, gross_losses=-250, active_days=40, daily_sum=600,
            daily_positive_days=25, daily_negative_days=15, daily_positive_sum=560,
            daily_negative_sum=-60, max_positive_day=200, daily_stddev=40,
            daily_abs_sum=620),
        row(22, "06", trades=60, wins=42, losses=18, market=560, net=-100,
            gross_wins=900, gross_losses=-250, active_days=40, daily_sum=300,
            daily_positive_days=15, daily_negative_days=25, daily_positive_sum=100,
            daily_negative_sum=-200, max_positive_day=80, daily_stddev=40,
            daily_abs_sum=300),
        row(22, "07", trades=30, wins=8, losses=22, market=-200, net=-150,
            gross_wins=120, gross_losses=-400, active_days=20, daily_sum=-150,
            daily_positive_days=6, daily_negative_days=14, daily_positive_sum=40,
            daily_negative_sum=-190, max_positive_day=20, daily_stddev=20,
            daily_abs_sum=230),
        row(23, "05", trades=60, wins=18, losses=42, market=-560, net=-500,
            gross_wins=250, gross_losses=-900, active_days=40, daily_sum=-500,
            daily_positive_days=6, daily_negative_days=34, daily_positive_sum=50,
            daily_negative_sum=-550, max_positive_day=20, daily_stddev=18,
            daily_abs_sum=600),
        row(23, "06", trades=60, wins=18, losses=42, market=-560, net=-500,
            gross_wins=250, gross_losses=-900, active_days=40, daily_sum=-500,
            daily_positive_days=6, daily_negative_days=34, daily_positive_sum=50,
            daily_negative_sum=-550, max_positive_day=20, daily_stddev=18,
            daily_abs_sum=600),
        row(23, "07", trades=30, wins=8, losses=22, market=-200, net=-150,
            gross_wins=120, gross_losses=-400, active_days=20, daily_sum=-150,
            daily_positive_days=6, daily_negative_days=14, daily_positive_sum=40,
            daily_negative_sum=-190, max_positive_day=20, daily_stddev=20,
            daily_abs_sum=230),
    ]

    result = build_two_stage_payload(
        rows,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
    )

    assert result["selection"]["counts"]["abook_candidates"] == 1
    assert result["selection"]["counts"]["bbook_candidates"] == 1
    accounts = {account["login"]: account for account in result["accounts"]}
    assert "monthly_consistency" in accounts[22]["selection_flags"]
    assert result["validation"]["groups"]["abook_candidate"]["precision"] == 1.0
    assert result["validation"]["groups"]["abook_candidate"]["active_positive_account_rate"] == 1.0
    assert result["validation"]["groups"]["bbook_candidate"]["active_negative_account_rate"] == 1.0


def test_two_stage_analysis_uses_exact_cross_period_statistics():
    first = row(500, "05", trades=2, wins=2, losses=0, market=4, net=4, active_days=2, daily_sum=4)
    second = row(500, "06", trades=1, wins=1, losses=0, market=5, net=5, active_days=1, daily_sum=5)
    for item in (first, second):
        item["market_pnl"] = item["deal_market_pnl"]
        item["selection_median_holding_seconds"] = Decimal("42")
        item["selection_symbols_traded"] = 3
    first["daily_pnl_sum_for_variance"] = Decimal("4")
    first["daily_pnl_square_sum"] = Decimal("10")
    first["daily_variance_count"] = 2
    second["daily_pnl_sum_for_variance"] = Decimal("5")
    second["daily_pnl_square_sum"] = Decimal("25")
    second["daily_variance_count"] = 1
    first["median_holding_seconds"] = Decimal("10")
    second["median_holding_seconds"] = Decimal("99")
    first["symbols_traded"] = 1
    second["symbols_traded"] = 2

    metrics = _account_period_metrics(
        [first, second],
        {"platform": "mt5", "login": 500, "account_group": "real"},
        phase="selection",
    )

    assert math.isclose(metrics["daily_stddev"], math.sqrt(8 / 3), rel_tol=1e-9)
    assert metrics["median_holding_seconds"] == 42.0
    assert metrics["symbols_traded"] == 3


def test_two_stage_analysis_exposes_book_performance_and_finite_payload():
    profitable = row(501, "05", trades=20, wins=15, losses=5, market=120, net=100,
                     gross_wins=150, gross_losses=-50, active_days=10, daily_sum=100)
    profitable["market_pnl"] = profitable["deal_market_pnl"]
    profitable["daily_stddev"] = 10
    profitable["daily_pnl_sum_for_variance"] = Decimal("100")
    profitable["daily_pnl_square_sum"] = Decimal("1000")
    profitable["daily_variance_count"] = 10
    profitable_2 = dict(profitable, month_start=datetime(2026, 6, 1))
    losing = row(502, "05", trades=20, wins=5, losses=15, market=-120, net=-100,
                 gross_wins=50, gross_losses=-150, active_days=10, daily_sum=-100)
    losing["market_pnl"] = losing["deal_market_pnl"]
    losing["daily_pnl_sum_for_variance"] = Decimal("-100")
    losing["daily_pnl_square_sum"] = Decimal("1000")
    losing["daily_variance_count"] = 10
    losing_2 = dict(losing, month_start=datetime(2026, 6, 1))
    zero_variance = row(503, "05")
    zero_variance["daily_stddev"] = float("nan")
    zero_variance["daily_active_days"] = 0
    zero_variance["active_trade_days"] = 0
    zero_variance_2 = dict(zero_variance, month_start=datetime(2026, 6, 1))

    result = build_two_stage_payload(
        [profitable, profitable_2, losing, losing_2, zero_variance, zero_variance_2],
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
        min_trades=20, min_active_days=5, min_profit_factor=1,
        min_avg_daily_profit=9, min_positive_month_rate=0,
        max_top1_day_profit_contribution=1, min_direction_day_rate_lower_bound=0,
        min_stability_score=0,
    )

    assert result["book_performance"]["selection"]["abook"]["net_pnl"] == 200.0
    assert result["book_performance"]["selection"]["bbook"]["net_pnl"] == -200.0
    assert result["book_performance"]["selection"]["abook"]["theoretical_increment"] == 200.0
    assert result["book_performance"]["selection"]["bbook"]["theoretical_increment"] == -200.0
    json.dumps(result, allow_nan=False)
