from datetime import date, datetime
import re

import pytest

from app.matched_trades_local import (
    load_local_matched_month,
    merge_matched_rows,
    mt4_deals_query,
    matched_trades_query,
    mt5_deals_query,
    open_entries_query,
    partition_month,
    update_matched_manifest,
    write_matched_month,
    write_query_stream,
    write_query_stream_with_retry,
)


def test_mt5_query_is_read_only_and_normalizes_fifo_fields():
    query, params = mt5_deals_query(
        datetime(2025, 7, 27), datetime(2026, 7, 27), ["mt5", "hh_mt5"]
    )

    assert "FROM risk.ods_mt5_deals FINAL" in query
    assert "action IN (0, 1)" in query
    assert "entry <> 3" in query
    assert "is_deleted = 0" in query
    assert "volume_ext / 1e8" in query
    assert "position_id" in query and "rate_profit" in query and "time_msc" in query
    assert not any(re.search(rf"\b{keyword}\b", query.upper()) for keyword in ("INSERT", "ALTER", "DELETE", "OPTIMIZE"))
    assert params["platforms"] == ["mt5", "hh_mt5"]


def test_mt4_query_is_read_only_and_uses_split_id_and_raw_volume():
    query, params = mt4_deals_query(datetime(2025, 7, 27), datetime(2026, 7, 27))

    assert "FROM risk.ods_mt4_trades_split" in query
    assert "split_id" in query and "ticket" in query and "conv_rate" in query
    assert "volume AS Volume" in query
    assert "action IN (0, 1)" in query
    assert not any(re.search(rf"\b{keyword}\b", query.upper()) for keyword in ("INSERT", "ALTER", "DELETE", "OPTIMIZE"))
    assert params["start_dt"] == "2025-07-27 00:00:00"


def test_open_entries_query_is_as_of_and_read_only():
    query, params = open_entries_query(datetime(2026, 7, 25))

    assert "FROM risk.dwd_match_trades_open FINAL" in query
    assert "argMax" in query
    assert "remaining_volume" in query
    assert "snapshot_at <=" in query
    assert not any(re.search(rf"\b{keyword}\b", query.upper()) for keyword in ("INSERT", "ALTER", "DELETE", "OPTIMIZE"))
    assert params["cutoff"] == "2026-07-25 00:00:00"


def test_matched_trades_query_is_read_only_and_has_local_projection_fields():
    query, params = matched_trades_query(datetime(2026, 7, 24), datetime(2026, 7, 27))

    assert "FROM risk.dwd_matched_trades FINAL" in query
    assert "entry_deal_id" in query and "exit_deal_id" in query and "turnover" in query
    assert not any(re.search(rf"\b{keyword}\b", query.upper()) for keyword in ("INSERT", "ALTER", "DELETE", "OPTIMIZE"))
    assert params["start"] == "2026-07-24 00:00:00"


def test_partition_month_accepts_datetime_and_iso_strings():
    assert partition_month(datetime(2026, 7, 25, 1, 2, 3)) == "2026-07"
    assert partition_month("2025-08-01 00:00:00") == "2025-08"


class _Stream:
    def __init__(self, batches):
        self.batches = batches

    def __enter__(self):
        return iter(self.batches)

    def __exit__(self, exc_type, exc, tb):
        return False


class _Client:
    def __init__(self, batches):
        self.batches = batches

    def query_arrow_stream(self, query, parameters):
        return _Stream(self.batches)


def test_write_query_stream_publishes_arrow_batches_atomically(tmp_path):
    import pyarrow as pa

    target = tmp_path / "month=2026-07" / "part.parquet"
    batch = pa.RecordBatch.from_arrays([pa.array([1, 2])], ["login"])

    assert write_query_stream(_Client([batch]), "SELECT 1", {}, target) == 2
    assert target.exists()
    assert not list(target.parent.glob("*.tmp"))


class _FailingStream:
    def __enter__(self):
        class Broken:
            def __iter__(self):
                raise RuntimeError("stream failed")

        return Broken()

    def __exit__(self, exc_type, exc, tb):
        return False


class _FailingClient:
    def query_arrow_stream(self, query, parameters):
        return _FailingStream()


def test_write_query_stream_does_not_publish_after_stream_failure(tmp_path):
    target = tmp_path / "month=2026-07" / "part.parquet"

    with pytest.raises(RuntimeError, match="stream failed"):
        write_query_stream(_FailingClient(), "SELECT 1", {}, target)

    assert not target.exists()
    assert not list(target.parent.glob("*.tmp"))


class _FlakyClient(_Client):
    def __init__(self, batches):
        super().__init__(batches)
        self.calls = 0

    def query_arrow_stream(self, query, parameters):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("incomplete read")
        return super().query_arrow_stream(query, parameters)


def test_write_query_stream_with_retry_retries_a_broken_connection(tmp_path):
    import pyarrow as pa

    target = tmp_path / "month=2026-07" / "part.parquet"
    batch = pa.RecordBatch.from_arrays([pa.array([1])], ["login"])
    client = _FlakyClient([batch])

    assert write_query_stream_with_retry(client, "SELECT 1", {}, target, retries=2) == 1
    assert client.calls == 2
    assert target.exists()


def matched_row(exit_deal_id, *, exit_time="2026-07-25T00:00:00"):
    return {
        "platform": "mt5",
        "login": 7,
        "symbol": "EURUSD",
        "direction": "Long",
        "entry_time": datetime.fromisoformat("2026-07-24T23:00:00"),
        "exit_time": datetime.fromisoformat(exit_time),
        "entry_price": 1.1,
        "exit_price": 1.2,
        "volume": 1.0,
        "profit": 0.1,
        "holding_seconds": 3600.0,
        "turnover": 2.3,
        "entry_deal_id": 11,
        "exit_deal_id": exit_deal_id,
    }


def test_merge_matched_rows_is_idempotent_and_preserves_existing_duplicate():
    existing = [matched_row(12)]
    additions = [matched_row(12), matched_row(13)]

    merged = merge_matched_rows(existing, additions)

    assert [row["exit_deal_id"] for row in merged] == [12, 13]
    assert merged[0]["profit"] == 0.1


def test_write_and_load_matched_month_use_canonical_schema(tmp_path):
    import pyarrow.parquet as pq

    target = tmp_path / "month=2026-07" / "part.parquet"
    assert write_matched_month(target, [matched_row(13), matched_row(12)]) == 2

    loaded = load_local_matched_month(target)
    assert [row["exit_deal_id"] for row in loaded] == [12, 13]
    assert pq.read_schema(target).names == [
        "platform", "login", "symbol", "direction", "entry_time", "exit_time",
        "entry_price", "exit_price", "volume", "profit", "holding_seconds",
        "turnover", "entry_deal_id", "exit_deal_id",
    ]


def test_update_matched_manifest_changes_only_matched_trade_counts():
    original = {
        "generation": "old",
        "tables": {
            "dwd_matched_trades": {
                "rows": 10,
                "monthly_rows": {"2026-06": 10},
            },
            "ods_mt5_deals": {"rows": 99},
        },
    }

    updated = update_matched_manifest(original, {"2026-06": 11, "2026-07": 2}, "now")

    assert updated["tables"]["dwd_matched_trades"]["rows"] == 13
    assert updated["tables"]["dwd_matched_trades"]["monthly_rows"] == {"2026-06": 11, "2026-07": 2}
    assert updated["tables"]["ods_mt5_deals"] == {"rows": 99}
    assert updated["generation"] != "old"


def test_update_matched_manifest_extends_coverage():
    manifest = {
        "schema_version": 1,
        "tables": {
            "dwd_matched_trades": {
                "monthly_rows": {"2026-05": 11},
                "rows": 11,
                "coverage": {
                    "mt4": [{"start": "2026-02-01", "end": "2026-07-31"}],
                },
            },
        },
    }

    updated = update_matched_manifest(
        manifest,
        {"2025-08": 4},
        "now",
        coverage_start=date(2025, 7, 27),
        coverage_end=date(2026, 5, 31),
        platforms=["mt4"],
    )

    assert updated["tables"]["dwd_matched_trades"]["coverage"]["mt4"] == [
        {"start": "2025-07-27", "end": "2026-07-31"}
    ]
