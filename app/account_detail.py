from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import csv
import os
from pathlib import Path
from typing import Any, Iterable


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _positive_contribution(values: Iterable[float], top_n: int = 1) -> float | None:
    positive = sorted((value for value in values if value > 0), reverse=True)
    total = sum(positive)
    return round(sum(positive[:top_n]) / total, 6) if total else None


def _date_key(row: dict[str, Any]) -> str:
    value = row.get("exit_time") or row.get("entry_time")
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value or "")[:10]


def _hour_key(row: dict[str, Any]) -> str:
    value = row.get("exit_time") or row.get("entry_time")
    if isinstance(value, datetime):
        return f"{value.hour:02d}"
    text = str(value or " ")
    return text[11:13] if len(text) >= 13 else "unknown"


def _sum_rows(rows: Iterable[dict[str, Any]]) -> float:
    return round(sum(_number(row.get("profit")) for row in rows), 6)


def _remove_group_profit(rows: list[dict[str, Any]], group_key: Any, top_n: int = 1) -> float:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = group_key(row) if callable(group_key) else str(row.get(group_key) or "unknown")
        grouped[str(key)].append(row)
    ranked = sorted(
        ((key, sum(_number(row.get("profit")) for row in items if _number(row.get("profit")) > 0)) for key, items in grouped.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    removed = {key for key, profit in ranked[:top_n] if profit > 0}
    return round(_sum_rows(row for row in rows if str(group_key(row) if callable(group_key) else row.get(group_key) or "unknown") not in removed), 6)


def build_account_detail_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    if not materialized:
        return {"metrics": {}, "concentration": {}, "de_extreme": {}}
    raw_net_profit = _sum_rows(materialized)
    positive_rows = [row for row in materialized if _number(row.get("profit")) > 0]
    day_profits: dict[str, float] = defaultdict(float)
    order_profits = [_number(row.get("profit")) for row in materialized]
    symbol_profits: dict[str, float] = defaultdict(float)
    hour_profits: dict[str, float] = defaultdict(float)
    event_profits: dict[str, float] = defaultdict(float)
    for row in positive_rows:
        profit = _number(row.get("profit"))
        day_profits[_date_key(row)] += profit
        symbol_profits[str(row.get("symbol") or "unknown")] += profit
        hour_profits[_hour_key(row)] += profit
        if row.get("event_window"):
            event_profits[str(row["event_window"])] += profit

    positive_total = sum(value for value in order_profits if value > 0)
    best_event_values = list(event_profits.values())
    max_position_row = max(materialized, key=lambda row: abs(_number(row.get("entry_price")) * _number(row.get("volume"))), default=None)
    max_position_profit = _number(max_position_row.get("profit")) if max_position_row else 0.0
    metrics = {
        "raw_net_profit": raw_net_profit,
        "positive_profit_total": round(positive_total, 6),
        "negative_profit_total": round(sum(value for value in order_profits if value < 0), 6),
    }
    concentration = {}
    for key, values, top_n in (
        ("max_profit_day_contribution", day_profits.values(), 1),
        ("top3_profit_day_contribution", day_profits.values(), 3),
        ("max_profit_order_contribution", order_profits, 1),
        ("top3_profit_order_contribution", order_profits, 3),
        ("best_symbol_contribution", symbol_profits.values(), 1),
        ("best_time_bucket_contribution", hour_profits.values(), 1),
        ("best_event_contribution", best_event_values, 1),
    ):
        value = _positive_contribution(values, top_n)
        if value is not None:
            concentration[key] = value

    de_extreme = {}
    if day_profits:
        de_extreme["without_max_profit_day"] = _remove_group_profit(materialized, _date_key, 1)
        de_extreme["without_top3_profit_days"] = _remove_group_profit(materialized, _date_key, 3)
    positive_orders = sorted((value for value in order_profits if value > 0), reverse=True)
    if positive_orders:
        de_extreme["without_max_profit_order"] = round(raw_net_profit - positive_orders[0], 6)
        de_extreme["without_top3_profit_orders"] = round(raw_net_profit - sum(positive_orders[:3]), 6)
        de_extreme["without_top5_profit_orders"] = round(raw_net_profit - sum(positive_orders[:5]), 6)
    if symbol_profits:
        de_extreme["without_best_symbol"] = _remove_group_profit(materialized, "symbol", 1)
    if hour_profits:
        de_extreme["without_best_time_bucket"] = _remove_group_profit(materialized, _hour_key, 1)
    if event_profits:
        de_extreme["without_best_event"] = _remove_group_profit(materialized, "event_window", 1)
    if max_position_row:
        de_extreme["without_max_position_order"] = round(raw_net_profit - max_position_profit, 6)
    return {"metrics": metrics, "concentration": concentration, "de_extreme": de_extreme}


def summarize_markout_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    materialized = list(rows)
    for kind in ("entry", "exit"):
        fields = sorted({
            key for row in materialized for key in row
            if key.startswith(f"{kind}_mean_") and key.endswith("ms_bps")
        })
        if not fields:
            continue
        curve = []
        for field in fields:
            offset_text = field.removeprefix(f"{kind}_mean_").removesuffix("ms_bps")
            values = [(_number(row.get(field)), max(_number(row.get(f"{kind}_events")), 1.0)) for row in materialized if row.get(field) not in (None, "")]
            positive = [(value, weight) for value, weight in values if value > 0]
            negative = [(value, weight) for value, weight in values if value < 0]
            positive_mean = sum(value * weight for value, weight in positive) / sum(weight for _, weight in positive) if positive else None
            negative_mean = sum(value * weight for value, weight in negative) / sum(weight for _, weight in negative) if negative else None
            curve.append({
                "offset_ms": int(offset_text),
                "positive_bps": round(positive_mean, 6) if positive_mean is not None else None,
                "negative_bps": round(negative_mean, 6) if negative_mean is not None else None,
                "sample_count": len(values),
            })
        five_second = next((row for row in curve if row["offset_ms"] == 5000), None)
        values = [(_number(row.get(f"{kind}_mean_5000ms_bps")), max(_number(row.get(f"{kind}_events")), 1.0)) for row in materialized if row.get(f"{kind}_mean_5000ms_bps") not in (None, "")]
        positive = [(value, weight) for value, weight in values if value > 0]
        negative = [(value, weight) for value, weight in values if value < 0]
        positive_mean = sum(value * weight for value, weight in positive) / sum(weight for _, weight in positive) if positive else None
        negative_mean = sum(value * weight for value, weight in negative) / sum(weight for _, weight in negative) if negative else None
        result[kind] = {
            "positive_5s_bps": five_second["positive_bps"] if five_second else (round(positive_mean, 6) if positive_mean is not None else None),
            "negative_5s_bps": five_second["negative_bps"] if five_second else (round(negative_mean, 6) if negative_mean is not None else None),
            "curve": curve,
            "sample_count": len(values),
        }
    return result


def _month_keys(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start).replace(day=1)
    last = date.fromisoformat(end).replace(day=1)
    result = []
    while current <= last:
        result.append(current.strftime("%Y-%m"))
        current = current.replace(year=current.year + (current.month == 12), month=1 if current.month == 12 else current.month + 1)
    return result


def load_markout_rows(login: int, start: str, end: str) -> list[dict[str, Any]]:
    root = Path(os.getenv("ABOOK_MARKOUT_DATA_ROOT", "/Users/jianghe/gzkj_副本_notickdata/markout_yearly"))
    rows: dict[str, dict[str, Any]] = {}
    for month in _month_keys(start, end):
        for kind in ("entry", "exit"):
            path = root / month / f"{kind}_user_markout_stats.csv"
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8") as handle:
                for raw in csv.DictReader(handle):
                    if int(float(raw.get("login") or 0)) != int(login):
                        continue
                    row = rows.setdefault(month, {})
                    for key, value in raw.items():
                        if key.startswith("mean_") and key.endswith("ms_bps"):
                            row[f"{kind}_{key}"] = value
                    if raw.get("events") not in (None, ""):
                        row[f"{kind}_events"] = raw["events"]
    return list(rows.values())
