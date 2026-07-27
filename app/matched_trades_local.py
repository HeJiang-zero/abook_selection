from __future__ import annotations

from datetime import date, datetime
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import os
from pathlib import Path
import re
from datetime import timezone
from typing import Any, Callable, Iterable, List, Optional, Tuple
from uuid import uuid4

from .matched_trades_fifo import matched_trade_key


_MUTATION = re.compile(r"\b(INSERT|ALTER|DELETE|OPTIMIZE|DROP|TRUNCATE|ATTACH|DETACH|RENAME|SYSTEM)\b", re.I)


def _format_datetime(value: datetime) -> str:
    return value.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _assert_read_only(query: str) -> None:
    match = _MUTATION.search(query)
    if match:
        raise ValueError(f"mutating ClickHouse query is forbidden: {match.group(1)}")


def mt5_deals_query(
    start: datetime, end: datetime, platforms: list[str]
) -> Tuple[str, dict[str, Any]]:
    query = """
    SELECT
        toUInt64(login) AS Login,
        toString(platform) AS Platform,
        toString(symbol) AS Symbol,
        toInt32(action) AS Action,
        toInt32(entry) AS Entry,
        time_msc AS Time,
        toUInt64(deal) AS Deal,
        toUInt64(position_id) AS PositionID,
        volume_ext / 1e8 AS Volume,
        price AS Price,
        rate_profit AS RateProfit,
        contract_size AS ContractSize,
        toUInt8(is_deleted) AS IsDeleted
    FROM risk.ods_mt5_deals FINAL
    WHERE platform IN {platforms:Array(String)}
      AND action IN (0, 1)
      AND entry <> 3
      AND is_deleted = 0
      AND time_msc >= {start:DateTime64(6)}
      AND time_msc < {end:DateTime64(6)}
    ORDER BY login, platform, symbol, time_msc, deal
    """
    _assert_read_only(query)
    return query, {
        "platforms": list(platforms),
        "start": _format_datetime(start),
        "end": _format_datetime(end),
    }


def mt4_deals_query(start: datetime, end: datetime) -> Tuple[str, dict[str, Any]]:
    query = """
    SELECT
        toUInt64(login) AS Login,
        'mt4' AS Platform,
        toString(symbol) AS Symbol,
        toInt32(action) AS Action,
        0 AS Entry,
        toDateTime64(deal_time, 3) AS Time,
        toUInt64(split_id) AS Deal,
        toUInt64(ticket) AS PositionID,
        volume AS Volume,
        price AS Price,
        conv_rate AS RateProfit,
        contract_size AS ContractSize
    FROM risk.ods_mt4_trades_split
    WHERE action IN (0, 1)
      AND deal_time >= {start_dt:DateTime}
      AND deal_time < {end_dt:DateTime}
    ORDER BY login, symbol, deal_time, split_id
    """
    _assert_read_only(query)
    return query, {
        "start_dt": _format_datetime(start),
        "end_dt": _format_datetime(end),
    }


def open_entries_query(cutoff: datetime) -> Tuple[str, dict[str, Any]]:
    query = """
    SELECT
        platform,
        login,
        symbol,
        argMax(direction, snapshot_at) AS direction,
        argMax(position_id, snapshot_at) AS position_id,
        entry_deal_id,
        argMax(open_time, snapshot_at) AS open_time,
        argMax(open_price, snapshot_at) AS open_price,
        argMax(original_volume, snapshot_at) AS original_volume,
        argMax(remaining_volume, snapshot_at) AS remaining_volume
    FROM risk.dwd_match_trades_open FINAL
    WHERE snapshot_at <= {cutoff:DateTime}
    GROUP BY platform, login, symbol, entry_deal_id
    HAVING remaining_volume > 0.0001
    """
    _assert_read_only(query)
    return query, {"cutoff": _format_datetime(cutoff)}


def matched_trades_query(
    start: datetime, end: datetime
) -> Tuple[str, dict[str, Any]]:
    query = """
    SELECT
        toUInt64(login) AS login,
        toString(platform) AS platform,
        toString(symbol) AS symbol,
        toString(direction) AS direction,
        entry_time,
        exit_time,
        entry_price,
        exit_price,
        volume,
        profit,
        holding_seconds,
        turnover,
        toUInt64(entry_deal_id) AS entry_deal_id,
        toUInt64(exit_deal_id) AS exit_deal_id
    FROM risk.dwd_matched_trades FINAL
    WHERE exit_time >= {start:DateTime}
      AND exit_time < {end:DateTime}
    ORDER BY exit_time, platform, login, symbol, entry_deal_id, exit_deal_id
    """
    _assert_read_only(query)
    return query, {"start": _format_datetime(start), "end": _format_datetime(end)}


def write_query_stream(client: Any, query: str, params: dict[str, Any], target: Path) -> int:
    _assert_read_only(query)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required for matched-trade local data") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    writer = None
    row_count = 0
    try:
        with client.query_arrow_stream(query, parameters=params) as stream:
            for batch in stream:
                table = pa.Table.from_batches([batch], schema=batch.schema)
                if writer is None:
                    writer = pq.ParquetWriter(temporary, table.schema)
                writer.write_table(table)
                row_count += table.num_rows
        if writer is None:
            table = client.query_arrow(query, parameters=params)
            pq.write_table(table, temporary)
            row_count = table.num_rows
        else:
            writer.close()
            writer = None
        os.replace(temporary, target)
        return row_count
    finally:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)


def write_query_stream_with_retry(
    client: Any,
    query: str,
    params: dict[str, Any],
    target: Path,
    *,
    retries: int = 3,
    client_factory: Optional[Callable[[], Any]] = None,
) -> int:
    if retries < 1:
        raise ValueError("retries must be at least 1")
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        current_client = client if attempt == 0 or client_factory is None else client_factory()
        try:
            return write_query_stream(current_client, query, params, target)
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def partition_month(value: datetime | date | str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text.replace(" ", "T"))
    return f"{parsed.year:04d}-{parsed.month:02d}"


CANONICAL_MATCHED_COLUMNS = [
    "platform", "login", "symbol", "direction", "entry_time", "exit_time",
    "entry_price", "exit_price", "volume", "profit", "holding_seconds",
    "turnover", "entry_deal_id", "exit_deal_id",
]


def _matched_schema() -> Any:
    import pyarrow as pa

    return pa.schema([
        ("platform", pa.string()),
        ("login", pa.uint64()),
        ("symbol", pa.string()),
        ("direction", pa.string()),
        ("entry_time", pa.timestamp("ms", tz="UTC")),
        ("exit_time", pa.timestamp("ms", tz="UTC")),
        ("entry_price", pa.decimal128(24, 8)),
        ("exit_price", pa.decimal128(24, 8)),
        ("volume", pa.decimal128(20, 8)),
        ("profit", pa.decimal128(24, 8)),
        ("holding_seconds", pa.decimal128(20, 4)),
        ("turnover", pa.decimal128(24, 8)),
        ("entry_deal_id", pa.uint64()),
        ("exit_deal_id", pa.uint64()),
    ])


def _as_utc(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _decimal(value: Any, scale: int) -> Decimal:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    quantum = Decimal(1).scaleb(-scale)
    return decimal_value.quantize(quantum, rounding=ROUND_HALF_UP)


def _normalise_loaded_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for name in ("entry_price", "exit_price", "volume", "profit", "holding_seconds", "turnover"):
        if result.get(name) is not None:
            result[name] = float(result[name])
    return result


def load_local_matched_month(path: Path) -> List[dict[str, Any]]:
    if not path.exists():
        return []
    import pyarrow.parquet as pq

    return [_normalise_loaded_row(row) for row in pq.read_table(path).to_pylist()]


def merge_matched_rows(
    existing: Iterable[dict[str, Any]], additions: Iterable[dict[str, Any]]
) -> List[dict[str, Any]]:
    merged: dict[Tuple[str, int, str, int, int], dict[str, Any]] = {}
    for row in existing:
        merged[matched_trade_key(row)] = dict(row)
    for row in additions:
        merged.setdefault(matched_trade_key(row), dict(row))
    return sorted(
        merged.values(),
        key=lambda row: (
            _as_utc(row.get("exit_time") or row.get("entry_time")),
            matched_trade_key(row),
        ),
    )


def write_matched_month(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    canonical = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            _as_utc(row.get("exit_time") or row.get("entry_time")),
            matched_trade_key(row),
        ),
    )
    schema = _matched_schema()
    values = {
        "platform": [str(row.get("platform", "")) for row in canonical],
        "login": [int(row.get("login", 0)) for row in canonical],
        "symbol": [str(row.get("symbol", "")) for row in canonical],
        "direction": [str(row.get("direction", "")) for row in canonical],
        "entry_time": [_as_utc(row.get("entry_time")) for row in canonical],
        "exit_time": [_as_utc(row.get("exit_time")) for row in canonical],
        "entry_price": [_decimal(row.get("entry_price", 0), 8) for row in canonical],
        "exit_price": [_decimal(row.get("exit_price", 0), 8) for row in canonical],
        "volume": [_decimal(row.get("volume", 0), 8) for row in canonical],
        "profit": [_decimal(row.get("profit", 0), 8) for row in canonical],
        "holding_seconds": [_decimal(row.get("holding_seconds", 0), 4) for row in canonical],
        "turnover": [_decimal(row.get("turnover", 0), 8) for row in canonical],
        "entry_deal_id": [int(row.get("entry_deal_id", 0)) for row in canonical],
        "exit_deal_id": [int(row.get("exit_deal_id", 0)) for row in canonical],
    }
    table = pa.table(values, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        pq.write_table(table, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return table.num_rows


def update_matched_manifest(
    manifest: dict[str, Any],
    month_rows: dict[str, int],
    updated_at: str,
    *,
    coverage_start: Optional[date] = None,
    coverage_end: Optional[date] = None,
    platforms: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    updated = deepcopy(manifest)
    payload = updated.setdefault("tables", {}).setdefault(
        "dwd_matched_trades", {"monthly_rows": {}, "rows": 0}
    )
    monthly_rows = dict(payload.get("monthly_rows", {}))
    monthly_rows.update({month: int(rows) for month, rows in month_rows.items()})
    payload["monthly_rows"] = dict(sorted(monthly_rows.items()))
    payload["months"] = sorted(monthly_rows)
    payload["rows"] = sum(monthly_rows.values())
    if coverage_start is not None and coverage_end is not None:
        if coverage_end < coverage_start:
            raise ValueError("coverage_end must not be before coverage_start")
        coverage = payload.setdefault("coverage", {})
        for platform in platforms or ("mt4", "mt5", "hh_mt5"):
            intervals = list(coverage.get(platform, []))
            intervals.append({
                "start": coverage_start.isoformat(),
                "end": coverage_end.isoformat(),
            })
            bounds = [
                (date.fromisoformat(item["start"]), date.fromisoformat(item["end"]))
                for item in intervals
            ]
            coverage[platform] = [{
                "start": min(start for start, _ in bounds).isoformat(),
                "end": max(end for _, end in bounds).isoformat(),
            }]
    updated["updated_at"] = updated_at
    updated["generation"] = f"local-matched-{uuid4().hex[:8]}"
    return updated
