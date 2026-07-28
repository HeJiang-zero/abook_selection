from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
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
    matched_trades_query,
    mt5_deals_query,
    open_entries_query,
    partition_month,
    update_matched_manifest,
    write_matched_month,
    write_query_stream,
    write_query_stream_with_retry,
)
from app.warehouse import load_manifest, new_generation, publish_manifest


DEFAULT_START = date(2025, 7, 27)
DEFAULT_END = date(2026, 7, 27)
ALLOWED_PLATFORMS = ("hh_mt5", "mt4", "mt5")
MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh local matched trades from read-only ClickHouse inputs")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--recompute-from", type=datetime.fromisoformat)
    parser.add_argument("--remote-reconcile", action="store_true")
    parser.add_argument("--reconcile-start", type=datetime.fromisoformat)
    parser.add_argument(
        "--reconcile-month",
        help="Replace one historical MT4 matched-trades month from remote FINAL, e.g. 2026-05",
    )
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
    if args.recompute_from is not None:
        args.recompute_from = args.recompute_from.replace(tzinfo=None)
        if args.recompute_from >= _as_datetime(args.end):
            parser.error("--recompute-from must be before the exclusive --end")
    if args.reconcile_start is not None:
        args.reconcile_start = args.reconcile_start.replace(tzinfo=None)
        if args.reconcile_start >= _as_datetime(args.end):
            parser.error("--reconcile-start must be before the exclusive --end")
    if args.reconcile_start is not None and not args.remote_reconcile:
        parser.error("--reconcile-start requires --remote-reconcile")
    if args.reconcile_month is not None:
        match = MONTH_RE.fullmatch(args.reconcile_month)
        if match is None or not 1 <= int(match.group(2)) <= 12:
            parser.error("--reconcile-month must use YYYY-MM")
        args.remote_reconcile = True
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


def _month_bounds(month: str) -> Tuple[datetime, datetime]:
    match = MONTH_RE.fullmatch(month)
    if match is None or not 1 <= int(match.group(2)) <= 12:
        raise ValueError("month must use YYYY-MM")
    current = date(int(match.group(1)), int(match.group(2)), 1)
    if current.month == 12:
        next_month = date(current.year + 1, 1, 1)
    else:
        next_month = date(current.year, current.month + 1, 1)
    return _as_datetime(current), _as_datetime(next_month)


def _naive_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"matched-trade timestamp is not datetime: {value!r}")
    return value.replace(tzinfo=None)


def _day_ranges(start: datetime, end: datetime) -> Iterable[Tuple[datetime, datetime, str]]:
    current = start.date()
    end_date = end.date()
    while current < end_date:
        next_day = current + timedelta(days=1)
        day_end = min(end_date, next_day)
        yield _as_datetime(current), _as_datetime(day_end), current.isoformat()
        current = next_day


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


def _load_archived_deals(root: Path, start: datetime, end: datetime) -> List[dict[str, Any]]:
    files = list(root.rglob("*.parquet")) if root.exists() else []
    if not files:
        return []
    import pyarrow.dataset as ds

    dataset = ds.dataset(str(root), format="parquet", partitioning="hive")
    time_type = dataset.schema.field("Time").type
    has_timezone = getattr(time_type, "tz", None) is not None
    start_utc = start.replace(tzinfo=timezone.utc) if has_timezone else start
    end_utc = end.replace(tzinfo=timezone.utc) if has_timezone else end
    table = dataset.to_table(
        filter=(ds.field("Time") >= start_utc) & (ds.field("Time") < end_utc)
    )
    return table.to_pylist()


def _historical_consumed_by_entry(
    warehouse_path: Path, cutoff: datetime
) -> dict[Tuple[str, int, str, int], float]:
    root = warehouse_path / "dwd_matched_trades"
    if not root.exists() or not list(root.rglob("*.parquet")):
        return {}
    import pyarrow.dataset as ds

    dataset = ds.dataset(str(root), format="parquet", partitioning="hive")
    time_type = dataset.schema.field("exit_time").type
    has_timezone = getattr(time_type, "tz", None) is not None
    cutoff_value = cutoff.replace(tzinfo=timezone.utc) if has_timezone else cutoff
    table = dataset.to_table(
        columns=["platform", "login", "symbol", "entry_deal_id", "exit_time", "volume"],
        filter=ds.field("exit_time") < cutoff_value,
    )
    grouped = table.group_by(["platform", "login", "symbol", "entry_deal_id"]).aggregate(
        [("volume", "sum")]
    )
    return {
        (str(row["platform"]), int(row["login"]), str(row["symbol"]), int(row["entry_deal_id"])):
            float(row["volume_sum"])
        for row in grouped.to_pylist()
    }


def _rebuild_initial_entries(
    open_rows: Iterable[dict[str, Any]],
    consumed_by_entry: dict[Tuple[str, int, str, int], float],
) -> List[dict[str, Any]]:
    rebuilt: List[dict[str, Any]] = []
    for row in open_rows:
        key = (
            str(row.get("platform", "")),
            int(row.get("login", 0)),
            str(row.get("symbol", "")),
            int(row.get("entry_deal_id", 0)),
        )
        original = float(row.get("original_volume") or 0.0)
        remaining = original - consumed_by_entry.get(key, 0.0)
        if remaining <= 0.0001:
            continue
        rebuilt_row = dict(row)
        rebuilt_row["remaining_volume"] = remaining
        rebuilt.append(rebuilt_row)
    return load_initial_entries(rebuilt)


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


def _archive_inputs(
    args: argparse.Namespace,
    client: Any,
    client_factory: Any = None,
) -> dict[str, Any]:
    stats: dict[str, Any] = {"mt5_deals": {}, "mt4_trades_split": {}}

    def existing_rows(path: Path) -> int:
        if not path.exists():
            return -1
        import pyarrow.parquet as pq

        return pq.read_metadata(path).num_rows

    def archive_table_month(
        table_name: str,
        month_start: datetime,
        month_end: datetime,
        month: str,
        query_builder: Any,
        query_args: tuple[Any, ...],
    ) -> int:
        month_target = args.input_path / table_name / f"month={month}" / "part.parquet"
        prior_month = existing_rows(month_target)
        if prior_month >= 0:
            return prior_month
        total = 0
        for day_start, day_end, day in _day_ranges(month_start, month_end):
            query, params = query_builder(day_start, day_end, *query_args)
            target = args.input_path / table_name / f"month={month}" / f"day={day}" / "part.parquet"
            prior_day = existing_rows(target)
            total += prior_day if prior_day >= 0 else write_query_stream_with_retry(
                client, query, params, target, retries=3, client_factory=client_factory
            )
        return total

    for month_start, month_end, month in _month_starts(args.start, args.end):
        if "mt5" in args.platforms or "hh_mt5" in args.platforms:
            stats["mt5_deals"][month] = archive_table_month(
                "mt5_deals", month_start, month_end, month, mt5_deals_query,
                ([p for p in args.platforms if p != "mt4"],),
            )
        if "mt4" in args.platforms:
            stats["mt4_trades_split"][month] = archive_table_month(
                "mt4_trades_split", month_start, month_end, month, mt4_deals_query, (),
            )
    return stats


def _compute_additions(
    args: argparse.Namespace,
    client: Any,
    frontier: Optional[datetime],
) -> Tuple[List[dict[str, Any]], List[dict[str, Any]], datetime, int]:
    start_dt = _as_datetime(args.start)
    end_dt = _as_datetime(args.end)
    cutoff = args.recompute_from or frontier or start_dt
    if cutoff >= end_dt:
        return [], [], cutoff, 0

    open_query, open_params = open_entries_query(cutoff)
    open_rows = _query_rows(client, open_query, open_params)
    consumed_by_entry = _historical_consumed_by_entry(args.warehouse_path, cutoff)
    initial = _rebuild_initial_entries(open_rows, consumed_by_entry)
    initial_by_group: dict[Tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in initial:
        initial_by_group[(entry["login"], entry["platform"], entry["symbol"])].append(entry)

    deals_by_group: dict[Tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    if "mt5" in args.platforms or "hh_mt5" in args.platforms:
        rows = _load_archived_deals(args.input_path / "mt5_deals", cutoff, end_dt)
        if not rows:
            query, params = mt5_deals_query(cutoff, end_dt, [p for p in args.platforms if p != "mt4"])
            rows = _query_rows(client, query, params)
        for row in rows:
            deals_by_group[_group_key(row)].append(row)
    if "mt4" in args.platforms:
        rows = _load_archived_deals(args.input_path / "mt4_trades_split", cutoff, end_dt)
        if not rows:
            query, params = mt4_deals_query(cutoff, end_dt)
            rows = _query_rows(client, query, params)
        for row in rows:
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


def _remote_reconcile(
    warehouse_path: Path,
    client: Any,
    start: datetime,
    end: datetime,
    platforms: Optional[Iterable[str]] = None,
) -> Tuple[int, int, str]:
    platform_list = list(platforms) if platforms is not None else None
    target_platforms = set(platform_list or ())
    query, params = matched_trades_query(start, end, platforms=platform_list)
    remote_rows = _query_rows(client, query, params)
    if not target_platforms:
        target_platforms = {str(row.get("platform", "")) for row in remote_rows}
    month = partition_month(start)
    path = warehouse_path / "dwd_matched_trades" / f"month={month}" / "part.parquet"
    existing = load_local_matched_month(path)
    keep = [
        row for row in existing
        if (
            str(row.get("platform", "")) not in target_platforms
            or not (start <= _naive_datetime(row.get("exit_time") or row.get("entry_time")) < end)
        )
    ]
    merged = merge_matched_rows(keep, remote_rows)
    write_matched_month(path, merged)
    return len(remote_rows), len(merged), month


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
        "recompute_from": args.recompute_from.isoformat(sep=" ") if args.recompute_from else None,
        "remote_write_attempts": 0,
        "remote_queries": 0,
    }
    if args.dry_run:
        result["planned_input_path"] = str(args.input_path)
        result["planned_warehouse_path"] = str(args.warehouse_path)
        return result
    client_factory = None
    if client is None:
        client_factory = lambda: _remote_client(get_settings())
        client = client_factory()

    if args.reconcile_month is not None:
        month_start, month_end = _month_bounds(args.reconcile_month)
        remote_rows, merged_rows, reconcile_month = _remote_reconcile(
            args.warehouse_path,
            client,
            month_start,
            month_end,
            platforms=("mt4",),
        )
        manifest_path = args.warehouse_path / "manifest.json"
        manifest = load_manifest(manifest_path)
        updated = update_matched_manifest(
            manifest,
            {reconcile_month: merged_rows},
            datetime.now().astimezone().isoformat(),
            coverage_start=month_start.date(),
            coverage_end=(month_end - timedelta(days=1)).date(),
            platforms=("mt4",),
        )
        publish_manifest(manifest_path, updated)
        result.update({
            "mode": "reconcile_month",
            "reconcile_month": reconcile_month,
            "remote_reconcile_rows": remote_rows,
            "merged_rows": merged_rows,
            "affected_months": [reconcile_month],
        })
        return result

    archive_stats = _archive_inputs(args, client, client_factory=client_factory)
    if client_factory is not None:
        client = client_factory()
    additions, unmatched_exits, cutoff, bootstrap_rows = _compute_additions(args, client, frontier)
    added_count, month_rows = _merge_output(args.warehouse_path, additions)
    reconcile_info: dict[str, Any] = {}
    if args.remote_reconcile:
        reconcile_start = args.reconcile_start or args.recompute_from or frontier or _as_datetime(args.start)
        remote_rows, merged_rows, reconcile_month = _remote_reconcile(
            args.warehouse_path, client, reconcile_start, _as_datetime(args.end)
        )
        month_rows[reconcile_month] = merged_rows
        reconcile_info = {
            "remote_reconcile_rows": remote_rows,
            "remote_reconcile_month": reconcile_month,
            "remote_reconcile_start": reconcile_start.isoformat(sep=" "),
        }
    if month_rows:
        manifest_path = args.warehouse_path / "manifest.json"
        manifest = load_manifest(manifest_path)
        updated = update_matched_manifest(
            manifest,
            month_rows,
            datetime.now().astimezone().isoformat(),
            coverage_start=args.start,
            coverage_end=args.end - timedelta(days=1),
            platforms=args.platforms,
        )
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
    result.update(reconcile_info)
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
