from datetime import datetime

from app.matched_trades_fifo import fifo_match, load_initial_entries, matched_trade_key


def deal(deal_id, timestamp, action, volume, price, *, platform="mt5", login=7, symbol="EURUSD"):
    return {
        "Login": login,
        "Platform": platform,
        "Symbol": symbol,
        "Action": action,
        "Entry": 0,
        "Time": datetime.fromisoformat(timestamp),
        "Deal": deal_id,
        "PositionID": deal_id + 1000,
        "Volume": volume,
        "Price": price,
        "RateProfit": 1.0,
    }


def open_row(entry_deal_id, remaining, *, direction="LONG"):
    return {
        "platform": "mt5",
        "login": 7,
        "symbol": "EURUSD",
        "direction": direction,
        "position_id": entry_deal_id + 1000,
        "entry_deal_id": entry_deal_id,
        "open_time": datetime(2026, 7, 24, 23, 0, 0),
        "open_price": 1.10,
        "original_volume": remaining,
        "remaining_volume": remaining,
    }


def row(platform, login, symbol, entry_deal_id, exit_deal_id):
    return {
        "platform": platform,
        "login": login,
        "symbol": symbol,
        "entry_deal_id": entry_deal_id,
        "exit_deal_id": exit_deal_id,
    }


def test_fifo_matches_partial_long_close_in_time_then_deal_order():
    matched, entries, exits = fifo_match([
        deal(1, "2026-07-25T00:00:00.001", 0, 1.0, 1.10),
        deal(2, "2026-07-25T00:00:00.001", 1, 0.4, 1.20),
    ])

    assert [
        (item["entry_deal_id"], item["exit_deal_id"], item["volume"])
        for item in matched
    ] == [(1, 2, 0.4)]
    assert len(entries) == 1
    assert entries[0]["remaining"] == 0.6
    assert exits == []


def test_fifo_splits_reverse_trade_into_close_and_new_open():
    matched, entries, exits = fifo_match([
        deal(1, "2026-07-25T00:00:00", 0, 1.0, 100.0),
        deal(2, "2026-07-25T00:00:01", 1, 1.5, 90.0),
    ])

    assert matched[0]["direction"] == "Long"
    assert matched[0]["volume"] == 1.0
    assert entries[0]["remaining"] == 0.5
    assert entries[0]["direction"] == "Short"
    assert exits == []


def test_bootstrap_entries_preserve_entry_deal_id_and_ignore_zero_remaining():
    entries = load_initial_entries([open_row(11, 0.5), open_row(12, 0.0)])

    assert [item["deal_id"] for item in entries] == [11]


def test_matched_trade_key_is_idempotent():
    assert matched_trade_key(row("mt4", 7, "EURUSD", 11, 12)) == (
        "mt4",
        7,
        "EURUSD",
        11,
        12,
    )
