import pytest
from pydantic import ValidationError

from app.models import AnalysisFilters, AnalysisRequest


def test_account_filters_are_limited_to_user_selection_fields():
    filters = AnalysisFilters(groups=["real\\FPlive"], logins=[123, 456])

    assert filters.model_dump() == {"groups": ["real\\FPlive"], "logins": [123, 456]}


@pytest.mark.parametrize("field", ["countries", "min_leverage", "min_balance"])
def test_account_filters_reject_non_selection_dimensions(field):
    with pytest.raises(ValidationError):
        AnalysisFilters(**{field: ["Brazil"] if field == "countries" else 1})


def test_default_strategy_filters_are_profit_factor_and_average_daily_profit():
    request = AnalysisRequest()

    assert request.rules.min_profit_factor == 1.0
    assert request.rules.min_avg_daily_profit == 0.0
    assert request.selection.start.isoformat() == "2026-05-01"
    assert request.validation.end.isoformat() == "2026-07-13"
    assert request.rules.min_positive_month_rate == 0.5
    assert request.rules.max_top1_day_profit_contribution == 0.2
    assert request.rules.max_peak_leverage_ratio == 200.0
    assert request.rules.max_high_leverage_holding_seconds == 300.0
    assert request.rules.min_direction_day_rate_lower_bound == 0.55
    assert request.rules.min_stability_score == 70
    assert request.rules.min_win_rate == 0.5
    assert request.rules.min_selection_monthly_consistency == 0.0


def test_analysis_request_accepts_separate_selection_and_validation_rules():
    request = AnalysisRequest(
        selection={"start": "2026-05-01", "end": "2026-06-30"},
        validation={"start": "2026-07-01", "end": "2026-07-31"},
        rules={"min_trades": 30, "min_active_days": 8, "neutral_band_usd": 15},
        exclude_test_accounts=False,
    )

    assert request.rules.min_trades == 30
    assert request.rules.min_active_days == 8
    assert request.rules.neutral_band_usd == 15
    assert request.exclude_test_accounts is False


def test_old_position_management_rule_is_rejected():
    with pytest.raises(ValidationError):
        AnalysisRequest(rules={"max_top_day_concentration": 0.5})
