import json

from app.r4 import (
    R4_MIN_PRIMARY_TRADES,
    R4_MIN_TRADES,
    R4_PRIMARY_TRADE_PCT,
    R4_WIN_RATE,
    build_r4_records,
    load_r4_snapshot,
)
from scripts import build_r4_snapshot


def _bucket(window_end, bucket, trade_count, trade_pct, winning_count, total_profit, window_type="7D_SLIDING"):
    return {
        "platform": "mt5",
        "login": 9001,
        "window_type": window_type,
        "window_end": window_end,
        "bucket": bucket,
        "trade_count": trade_count,
        "trade_pct": trade_pct,
        "winning_count": winning_count,
        "total_profit": total_profit,
    }


def test_r4_uses_only_selection_7d_windows_and_weekly_latest_snapshot():
    rows = [
        _bucket("2026-06-20 00:00:00", "0_10s", 12, 0.60, 10, 40),
        _bucket("2026-06-20 00:00:00", "10_30s", 8, 0.40, 6, 30),
        _bucket("2026-06-25 00:00:00", "0_10s", 12, 0.60, 10, 40),
        _bucket("2026-06-25 00:00:00", "10_30s", 8, 0.40, 6, 30),
        _bucket("2026-06-25 00:00:00", "30_60s", 10, 0.50, 10, 100, "CUSTOM"),
        _bucket("2026-07-05 00:00:00", "0_10s", 20, 0.60, 20, 200),
    ]

    records = build_r4_records(rows, "2026-05-01", "2026-06-30", ["mt5"])

    assert len(records) == 1
    record = records[0]
    assert record["window_end"] == "2026-06-25"
    assert record["total_trades"] == 20
    assert record["win_rate"] == 0.8
    assert record["primary_trade_pct"] == 0.6
    assert record["primary_trades"] == 12
    assert record["soft_alignment"] == 1
    assert record["pass_r4"] is True


def test_r4_defaults_use_robust_thresholds_not_research_percentile_cutoffs():
    assert R4_PRIMARY_TRADE_PCT == 0.35
    assert R4_WIN_RATE == 0.55
    assert R4_MIN_TRADES == 20
    assert R4_MIN_PRIMARY_TRADES == 8


def test_r4_snapshot_loads_only_matching_selection_and_platforms(tmp_path):
    path = tmp_path / "r4.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "window_type": "7D_SLIDING",
        "records": [{"platform": "mt5", "login": 9001, "pass_r4": True}],
    }))

    snapshot = load_r4_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])

    assert snapshot.status == "ready"
    assert snapshot.indexed_records()[("mt5", 9001)]["pass_r4"] is True


def test_r4_builder_reads_configured_csv_and_writes_selection_only(tmp_path, monkeypatch):
    source = tmp_path / "holding.csv"
    source.write_text(
        "platform,login,window_type,window_end,bucket,trade_count,trade_pct,winning_count,total_profit\n"
        "mt5,9001,7D_SLIDING,2026-06-25,0_10s,12,0.6,10,40\n"
        "mt5,9001,7D_SLIDING,2026-06-25,10_30s,8,0.4,6,30\n"
        "mt5,9001,7D_SLIDING,2026-07-05,0_10s,20,0.6,20,200\n",
    )
    monkeypatch.setenv("ABOOK_R4_SOURCE_PATH", str(source))

    payload = build_r4_snapshot.build_snapshot("2026-07-01", "2026-07-16", ["mt5"])

    assert payload["selection_start"] == "2026-05-01"
    assert payload["selection_end"] == "2026-06-30"
    assert len(payload["records"]) == 1
    assert payload["records"][0]["pass_r4"] is True
