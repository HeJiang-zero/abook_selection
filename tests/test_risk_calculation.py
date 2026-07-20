from scripts.build_user_risk_snapshot import apply_concurrent_exposure, calculate_daily_risk
from pathlib import Path


def test_daily_risk_matches_mt4_and_mt5_balance_datetime_formats():
    trades = [
        {"platform": "mt4", "login": 1, "trade_date": "2026-05-01", "daily_position_value": 100},
        {"platform": "mt5", "login": 2, "trade_date": "2026-05-01", "daily_position_value": 400},
    ]
    balances = [
        {"platform": "mt4", "login": 1, "datetime": "2026/05/01 23:59:59", "balance": 100},
        {"platform": "mt5", "login": 2, "datetime": "2026-05-01T23:59:59", "balance": 200},
    ]

    result = calculate_daily_risk(trades, balances)

    assert result[("mt4", 1)]["leverage_values"] == [1.0]
    assert result[("mt5", 2)]["leverage_values"] == [2.0]
    assert result[("mt4", 1)]["leverage_p95_ratio"] == 1.0
    assert result[("mt5", 2)]["leverage_p95_ratio"] == 2.0


def test_daily_risk_uses_latest_balance_as_of_trade_day_and_marks_missing_balance():
    trades = [
        {"platform": "mt5", "login": 3, "trade_date": "2026-05-02", "daily_position_value": 300},
        {"platform": "mt5", "login": 4, "trade_date": "2026-05-02", "daily_position_value": 300},
    ]
    balances = [
        {"platform": "mt5", "login": 3, "datetime": "2026-05-01 00:00:00", "balance": 100},
        {"platform": "mt5", "login": 3, "datetime": "2026-05-02 12:00:00", "balance": 150},
        {"platform": "mt5", "login": 4, "datetime": "2026-05-02 12:00:00", "balance": 0},
    ]

    result = calculate_daily_risk(trades, balances)

    assert result[("mt5", 3)]["leverage_values"] == [2.0]
    assert result[("mt5", 4)]["leverage_values"] == []
    assert result[("mt5", 4)]["balance_status"] == "unknown_nonpositive_balance"


def test_daily_risk_uses_open_price_times_open_quantity_as_position_value():
    result = calculate_daily_risk(
        [{"platform": "mt5", "login": 5, "trade_date": "2026-05-01", "daily_position_value": 100000}],
        [{"platform": "mt5", "login": 5, "datetime": "2026-05-01", "balance": 10000}],
    )

    assert result[("mt5", 5)]["leverage_values"] == [10.0]


def test_daily_risk_prefers_turnover_when_the_snapshot_provides_it():
    result = calculate_daily_risk(
        [{"platform": "mt5", "login": 6, "trade_date": "2026-05-01", "daily_turnover": 5000}],
        [{"platform": "mt5", "login": 6, "datetime": "2026-05-01", "balance": 1000}],
    )

    assert result[("mt5", 6)]["leverage_values"] == [5.0]
    assert result[("mt5", 6)]["total_turnover"] == 5000.0


def test_risk_snapshot_query_uses_opening_day_for_opening_leverage():
    source = Path("scripts/build_user_risk_snapshot.py").read_text()

    assert "toDate(mt.exit_time) AS trade_date" in source
    assert "sum(abs(toFloat64(mt.turnover))) AS daily_turnover" in source
    assert "mt.exit_time >= {selection_start:Date}" in source
    assert "mt.exit_time < {selection_end_exclusive:Date}" in source
    assert "FROM {table} AS b FINAL" not in source
    assert "FROM {table} AS b\n" in source


def test_concurrent_exposure_replaces_closed_turnover_leverage_for_filtering():
    daily = {
        ("mt5", 7): {
            "leverage_p95_ratio": 0.8,
            "peak_leverage_ratio": 0.8,
            "balance_status": "positive",
        }
    }
    exposure = {
        ("mt5", 7): {
            "peak_position_value": 200000.0,
            "peak_leverage_ratio": 250.0,
            "leverage_p95_ratio": 180.0,
            "exposure_status": "includes_open_event_estimate",
        }
    }

    result = apply_concurrent_exposure(daily, exposure)

    assert result[("mt5", 7)]["leverage_p95_ratio"] == 180.0
    assert result[("mt5", 7)]["peak_leverage_ratio"] == 250.0
    assert result[("mt5", 7)]["peak_concurrent_position_value"] == 200000.0
