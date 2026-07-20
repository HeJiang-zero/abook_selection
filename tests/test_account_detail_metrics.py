from __future__ import annotations

from app.account_detail import build_account_detail_metrics, summarize_markout_rows
from app.exposure import build_unmatched_open_events, reconstruct_peak_exposure


def _row(day: str, profit: float, symbol: str, hour: int, volume: float, event: str | None = None) -> dict:
    return {
        "platform": "mt5",
        "login": 7,
        "symbol": symbol,
        "direction": "buy",
        "entry_time": f"2026-05-{day} {hour:02d}:00:00",
        "exit_time": f"2026-05-{day} {hour:02d}:00:05",
        "entry_price": 100.0,
        "exit_price": 101.0,
        "volume": volume,
        "profit": profit,
        "event_window": event,
        "entry_deal_id": int(day) * 100 + hour,
        "exit_deal_id": int(day) * 1000 + hour,
    }


def test_reconstruct_peak_exposure_includes_overlapping_readds_and_partial_closes():
    events = [
        {"platform": "mt5", "login": 7, "symbol": "EURUSD", "direction": "buy", "entry_time": "2026-05-01 09:00:00", "exit_time": "2026-05-02 09:00:00", "entry_price": 100, "volume": 10, "entry_deal_id": 1, "exit_deal_id": 11},
        {"platform": "mt5", "login": 7, "symbol": "EURUSD", "direction": "buy", "entry_time": "2026-05-01 12:00:00", "exit_time": "2026-05-03 09:00:00", "entry_price": 110, "volume": 5, "entry_deal_id": 2, "exit_deal_id": 12},
    ]
    balances = [
        {"platform": "mt5", "login": 7, "datetime": "2026-05-01 00:00:00", "balance": 1000},
        {"platform": "mt5", "login": 7, "datetime": "2026-05-02 00:00:00", "balance": 1000},
    ]

    result = reconstruct_peak_exposure(events, balances)

    account = result[("mt5", 7)]
    assert account["peak_position_value"] == 1550.0
    assert account["peak_leverage_ratio"] == 1.55
    assert account["exposure_status"] == "complete_for_matched_events"


def test_unmatched_raw_entry_deal_becomes_remaining_open_exposure():
    events = [{
        "platform": "mt5", "login": 7, "entry_deal_id": 100,
        "entry_time": "2026-05-01 09:00:00", "exit_time": "2026-05-02 09:00:00",
        "entry_price": 100, "volume": 4,
    }]
    raw_deals = [{
        "platform": "mt5", "login": 7, "deal_id": 100, "entry": 0,
        "time": "2026-05-01 09:00:00", "price": 100, "volume": 10,
    }]

    open_events = build_unmatched_open_events(raw_deals, events)

    assert len(open_events) == 1
    assert open_events[0]["volume"] == 6.0
    assert open_events[0]["exit_time"] is None


def test_account_detail_metrics_calculate_concentration_and_de_extreme_results():
    rows = [
        _row("01", 10, "EURUSD", 10, 1),
        _row("01", 5, "EURUSD", 10, 1),
        _row("02", 30, "XAUUSD", 11, 10, "news_a"),
        _row("03", 15, "XAUUSD", 11, 2, "news_a"),
        _row("03", -5, "EURUSD", 12, 1),
        _row("03", 20, "GBPUSD", 12, 20, "news_b"),
    ]

    result = build_account_detail_metrics(rows)

    assert result["metrics"]["raw_net_profit"] == 75.0
    assert result["concentration"]["max_profit_day_contribution"] == 0.4375
    assert result["concentration"]["top3_profit_day_contribution"] == 1.0
    assert result["concentration"]["max_profit_order_contribution"] == 0.375
    assert result["concentration"]["top3_profit_order_contribution"] == round(65 / 80, 6)
    assert result["concentration"]["best_symbol_contribution"] == 0.5625
    assert result["concentration"]["best_time_bucket_contribution"] == 0.5625
    assert result["concentration"]["best_event_contribution"] == round(45 / 65, 6)
    assert result["de_extreme"]["without_max_profit_day"] == 45.0
    assert result["de_extreme"]["without_top3_profit_days"] == 0.0
    assert result["de_extreme"]["without_max_profit_order"] == 45.0
    assert result["de_extreme"]["without_top3_profit_orders"] == 10.0
    assert result["de_extreme"]["without_top5_profit_orders"] == -5.0
    assert result["de_extreme"]["without_best_symbol"] == 30.0
    assert result["de_extreme"]["without_best_time_bucket"] == 30.0
    assert result["de_extreme"]["without_best_event"] == 30.0
    assert result["de_extreme"]["without_max_position_order"] == 55.0


def test_markout_summary_returns_positive_and_negative_entry_exit_curves():
    rows = [
        {"platform": "mt5", "login": 7, "entry_mean_5000ms_bps": 2.0, "exit_mean_5000ms_bps": -3.0},
        {"platform": "mt5", "login": 8, "entry_mean_5000ms_bps": -1.0, "exit_mean_5000ms_bps": 4.0},
        {"platform": "mt5", "login": 9, "entry_mean_5000ms_bps": 3.0, "exit_mean_5000ms_bps": -2.0},
    ]

    result = summarize_markout_rows(rows)

    assert result["entry"]["positive_5s_bps"] == 2.5
    assert result["entry"]["negative_5s_bps"] == -1.0
    assert result["exit"]["positive_5s_bps"] == 4.0
    assert result["exit"]["negative_5s_bps"] == -2.5


def test_account_detail_omits_dimensions_without_observations():
    result = build_account_detail_metrics([
        {"profit": 10, "symbol": "EURUSD", "exit_time": "2026-05-01 10:00:00"},
    ])

    assert "best_event_contribution" not in result["concentration"]
    assert "without_best_event" not in result["de_extreme"]
