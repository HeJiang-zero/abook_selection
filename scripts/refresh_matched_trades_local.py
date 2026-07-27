from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import clickhouse_connect

from app.config import get_settings, load_env_file, Settings
from app.matched_trades_fifo import fifo_match, load_initial_entries
from app.matched_trades_local import (
    load_local_matched_month,
    merge_matched_rows,
    mt4_deals_query,
    mt5_deals_query,
    open_entries_query,
    partition_month,
    update_matched_manifest,
    write_matched_month,
    write_query_stream,
)
from app.warehouse import load_manifest, new_generation, publish_manifest


DEFAULT_START = date(2025, 7, 27)
DEFAULT_END = date(2026, 7, 27)
ALLOWED_PLATFORMS = ("hh_mt5", "mt4", "mt5")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh local matched trades from read-only ClickHouse inputs")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--platform", action="append", dest="platforms")
    parser.add_argument(
        "--warehouse-path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "warehouse",
    )
    parser.add_argument(
        "--input-path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "matched_trades_inputs",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.start >= args.end:
        parser.error("--start must be before the exclusive --end")
    args.platforms = sorted(set(args.platforms or ALLOWED_PLATFORMS))
    invalid = set(args.platforms) - set(ALLOWED_PLATFORMS)
    if invalid:
        parser.error(f"unsupported platform: {sorted(invalid)}")
    return args


def _as_datetime(value: date, *, end: bool = False) -> datetime:
    return datetime.combine(value, time.min)


def _month_starts(start: date, end: date) -> Iterable[Tuple[datetime, datetime, str]]:
    current = date(start.year, start.month, 1)
    while current < end:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        month_start = max(start, current)
        month_end = min(end, next_month)
        yield _as_datetime(month_start), _as_datetime(month_end), f"{current.year:04d}-{current.month:02d}"
        current = next_month


def _remote_client(settings: Settings) -> Any:
    if not settings.configured:
        raise RuntimeError("CLICKHOUSE_PASSWORD is not configured")
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        secure=settings.clickhouse_secure,
        compress=settings.clickhouse_compress,
        apply_server_timezone=settings.clickhouse_use_server_time_zone_for_dates,
    )


def _query_rows(client: Any, query: str, params: dict[str, Any]) -> List[dict[str, Any]]:
    result = client.query(query, parameters=params)
    columns = list(result.column_names)
    return [dict(zip(columns, row)) for row in result.result_rows]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _local_frontier(warehouse_path: Path) -> Optional[datetime]:
    root = warehouse_path / "dwd_matched_trades"
    if not root.exists() or not list(root.rglob("*.parquet")):
        return None
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    dataset = ds.dataset(str(root), format="parquet", partitioning="hive")
    values = dataset.to_table(columns=["exit_time"])["exit_time"]
    max_value = pc.max(pc.drop_null(values)).as_py()
    if max_value is None:
        return None
    return max_value.replace(tzinfo=None) if max_value.tzinfo else max_value


def _group_key(row: dict[str, Any]) -> Tuple[int, str, str]:
    return (
        int(row.get("Login", row.get("login", 0))),
        str(row.get("Platform", row.get("platform", ""))),
        str(row.get("Symbol", row.get("symbol", ""))),
    )


def _archive_inputs(args: argparse.Namespace, client: Any) -> dict[str, Any]:
    stats: dict[str, Any] = {"mt5_deals": {}, "mt4_trades_split": {}}
    for month_start, month_end, month in _month_starts(args.start, args.end):
        if "mt5" in args.platforms or "hh_mt5" in args.platforms:
            query, params = mt5_deals_query(month_start, month_end, [p for p in args.platforms if p != "mt4"])
            target = args.input_path / "mt5_deals" / f"month={month}" / "part.parquet"
            stats["mt5_deals"][month] = write_query_stream(client, query, params, target)
        if "mt4" in args.platforms:
            query, params = mt4_deals_query(month_start, month_end)
            target = args.input_path / "mt4_trades_split" / f"month={month}" / "part.parquet"
            stats["mt4_trades_split"][month] = write_query_stream(client, query, params, target)
    return stats


def _compute_additions(
    args: argparse.Namespace,
    client: Any,
    frontier: Optional[datetime],
) -> Tuple[List[dict[str, Any]], List[dict[str, Any]], datetime, int]:
    start_dt = _as_datetime(args.start)
    end_dt = _as_datetime(args.end)
    cutoff = frontier or start_dt
    if cutoff >= end_dt:
        return [], [], cutoff, 0

    open_query, open_params = open_entries_query(cutoff)
    open_rows = _query_rows(client, open_query, open_params)
    initial = load_initial_entries(open_rows)
    initial_by_group: dict[Tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in initial:
        initial_by_group[(entry["login"], entry["platform"], entry["symbol"])].append(entry)

    deals_by_group: dict[Tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    if "mt5" in args.platforms or "hh_mt5" in args.platforms:
        query, params = mt5_deals_query(cutoff, end_dt, [p for p in args.platforms if p != "mt4"])
        for row in _query_rows(client, query, params):
            deals_by_group[_group_key(row)].append(row)
    if "mt4" in args.platforms:
        query, params = mt4_deals_query(cutoff, end_dt)
        for row in _query_rows(client, query, params):
            deals_by_group[_group_key(row)].append(row)

    additions: List[dict[str, Any]] = []
    unmatched_exits: List[dict[str, Any]] = []
    for key in sorted(set(initial_by_group) | set(deals_by_group)):
        matched, _, unmatched = fifo_match(
            deals_by_group.get(key, []), initial_by_group.get(key, [])
        )
        additions.extend(
            row for row in matched
            if start_dt <= row["exit_time"] < end_dt
        )
        unmatched_exits.extend(unmatched)
    return additions, unmatched_exits, cutoff, len(initial)


def _merge_output(
    warehouse_path: Path, additions: Iterable[dict[str, Any]]
) -> Tuple[int, dict[str, int]]:
    additions_by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in additions:
        additions_by_month[partition_month(row["exit_time"])].append(row)
    added_count = 0
    month_rows: dict[str, int] = {}
    for month, month_additions in sorted(additions_by_month.items()):
        path = warehouse_path / "dwd_matched_trades" / f"month={month}" / "part.parquet"
        existing = load_local_matched_month(path)
        merged = merge_matched_rows(existing, month_additions)
        new_count = len(merged) - len(existing)
        if new_count > 0:
            write_matched_month(path, merged)
            added_count += new_count
            month_rows[month] = len(merged)
    return added_count, month_rows


def _publish_input_manifest(
    args: argparse.Namespace,
    archive_stats: dict[str, Any],
    cutoff: datetime,
    bootstrap_rows: int,
) -> None:
    _write_json_atomic(args.input_path / "manifest.json", {
        "schema_version": 1,
        "window": {"start": args.start.isoformat(), "end_exclusive": args.end.isoformat()},
        "platforms": args.platforms,
        "bootstrap": {"cutoff": cutoff.isoformat(sep=" "), "rows": bootstrap_rows},
        "tables": archive_stats,
        "remote_write_attempts": 0,
    })


def run_refresh(args: argparse.Namespace, client: Any = None) -> dict[str, Any]:
    frontier = _local_frontier(args.warehouse_path)
    result: dict[str, Any] = {
        "status": "dry_run" if args.dry_run else "ok",
        "window": {"start": args.start.isoformat(), "end_exclusive": args.end.isoformat()},
        "platforms": args.platforms,
        "local_frontier": frontier.isoformat(sep=" ") if frontier else None,
        "remote_write_attempts": 0,
        "remote_queries": 0,
    }
    if args.dry_run:
        result["planned_input_path"] = str(args.input_path)
        result["planned_warehouse_path"] = str(args.warehouse_path)
        return result
    if client is None:
        client = _remote_client(get_settings())

    archive_stats = _archive_inputs(args, client)
    additions, unmatched_exits, cutoff, bootstrap_rows = _compute_additions(args, client, frontier)
    added_count, month_rows = _merge_output(args.warehouse_path, additions)
    if month_rows:
        manifest_path = args.warehouse_path / "manifest.json"
        manifest = load_manifest(manifest_path)
        updated = update_matched_manifest(manifest, month_rows, datetime.now().astimezone().isoformat())
        publish_manifest(manifest_path, updated)
    _publish_input_manifest(args, archive_stats, cutoff, bootstrap_rows)
    result.update({
        "archive_rows": archive_stats,
        "bootstrap_cutoff": cutoff.isoformat(sep=" "),
        "bootstrap_rows": bootstrap_rows,
        "computed_rows": len(additions),
        "added_rows": added_count,
        "unmatched_exits": len(unmatched_exits),
        "affected_months": sorted(month_rows),
    })
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    load_env_file()
    try:
        result = run_refresh(parse_args(argv))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
