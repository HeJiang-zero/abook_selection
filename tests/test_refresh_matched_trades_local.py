from datetime import date, datetime

from app.matched_trades_local import write_matched_month
from scripts.refresh_matched_trades_local import parse_args, run_refresh


def matched_row(exit_deal_id=12):
    return {
        "platform": "mt5",
        "login": 7,
        "symbol": "EURUSD",
        "direction": "Long",
        "entry_time": datetime(2026, 7, 23, 23, 0),
        "exit_time": datetime(2026, 7, 24, 0, 0),
        "entry_price": 1.1,
        "exit_price": 1.15,
        "volume": 0.5,
        "profit": 0.025,
        "holding_seconds": 3600,
        "turnover": 1.125,
        "entry_deal_id": 11,
        "exit_deal_id": exit_deal_id,
    }


class _QueryResult:
    def __init__(self, columns, rows):
        self.column_names = columns
        self.result_rows = rows


class _Stream:
    def __init__(self, batches):
        self.batches = batches

    def __enter__(self):
        return iter(self.batches)

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeClient:
    def __init__(self):
        self.queries = []
        self.mutations = []
        self.last_table = None

    def query_arrow_stream(self, query, parameters):
        import pyarrow as pa

        self.queries.append(query)
        if "ods_mt4_trades_split" in query:
            table = pa.table({
                "Login": pa.array([], type=pa.uint64()),
                "Platform": pa.array([], type=pa.string()),
                "Symbol": pa.array([], type=pa.string()),
                "Action": pa.array([], type=pa.int32()),
                "Entry": pa.array([], type=pa.int32()),
                "Time": pa.array([], type=pa.timestamp("ms")),
                "Deal": pa.array([], type=pa.uint64()),
                "PositionID": pa.array([], type=pa.uint64()),
                "Volume": pa.array([], type=pa.float64()),
                "Price": pa.array([], type=pa.float64()),
                "RateProfit": pa.array([], type=pa.float64()),
                "ContractSize": pa.array([], type=pa.float64()),
            })
        else:
            table = pa.table({
                "Login": pa.array([], type=pa.uint64()),
                "Platform": pa.array([], type=pa.string()),
                "Symbol": pa.array([], type=pa.string()),
                "Action": pa.array([], type=pa.int32()),
                "Entry": pa.array([], type=pa.int32()),
                "Time": pa.array([], type=pa.timestamp("us")),
                "Deal": pa.array([], type=pa.uint64()),
                "PositionID": pa.array([], type=pa.uint64()),
                "Volume": pa.array([], type=pa.float64()),
                "Price": pa.array([], type=pa.float64()),
                "RateProfit": pa.array([], type=pa.float64()),
                "ContractSize": pa.array([], type=pa.float64()),
                "IsDeleted": pa.array([], type=pa.uint8()),
            })
        self.last_table = table
        return _Stream(table.to_batches())

    def query_arrow(self, query, parameters):
        return self.last_table

    def query(self, query, parameters):
        self.queries.append(query)
        if "dwd_match_trades_open" in query:
            return _QueryResult(
                [
                    "platform", "login", "symbol", "direction", "position_id",
                    "entry_deal_id", "open_time", "open_price", "original_volume", "remaining_volume",
                ],
                [["mt5", 7, "EURUSD", "Long", 101, 11, datetime(2026, 7, 23, 23), 1.1, 1.0, 1.0]],
            )
        if "ods_mt4_trades_split" in query:
            return _QueryResult([], [])
        if "ods_mt5_deals" in query:
            return _QueryResult(
                [
                    "Login", "Platform", "Symbol", "Action", "Entry", "Time", "Deal",
                    "PositionID", "Volume", "Price", "RateProfit", "ContractSize", "IsDeleted",
                ],
                [[7, "mt5", "EURUSD", 1, 0, datetime(2026, 7, 25, 0), 13, 101, 1.0, 1.2, 1.0, 100000, 0]],
            )
        raise AssertionError(f"unexpected query: {query}")

    def insert_df(self, *args, **kwargs):
        self.mutations.append((args, kwargs))
        raise AssertionError("ClickHouse writes are forbidden")


def test_parse_args_uses_confirmed_exclusive_window_and_platforms():
    args = parse_args([])

    assert args.start == date(2025, 7, 27)
    assert args.end == date(2026, 7, 27)
    assert args.platforms == ["hh_mt5", "mt4", "mt5"]


def test_dry_run_never_touches_remote_or_local(tmp_path):
    client = _FakeClient()
    args = parse_args([
        "--dry-run", "--warehouse-path", str(tmp_path / "warehouse"),
        "--input-path", str(tmp_path / "inputs"),
    ])

    result = run_refresh(args, client=client)

    assert result["status"] == "dry_run"
    assert result["remote_write_attempts"] == 0
    assert client.queries == []
    assert not (tmp_path / "warehouse").exists()
    assert not (tmp_path / "inputs").exists()


def test_refresh_is_idempotent_and_never_writes_remote(tmp_path):
    warehouse = tmp_path / "warehouse"
    output = warehouse / "dwd_matched_trades" / "month=2026-07" / "part.parquet"
    write_matched_month(output, [matched_row()])
    client = _FakeClient()
    args = parse_args([
        "--start", "2026-07-25", "--end", "2026-07-27",
        "--warehouse-path", str(warehouse), "--input-path", str(tmp_path / "inputs"),
    ])

    first = run_refresh(args, client=client)
    second = run_refresh(args, client=client)

    assert first["added_rows"] == 1
    assert second["added_rows"] == 0
    assert first["remote_write_attempts"] == 0
    assert client.mutations == []
    assert (tmp_path / "inputs" / "manifest.json").exists()
