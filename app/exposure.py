from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime
from typing import Any


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip().replace("/", "-").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * 0.95 + 0.999999999) - 1)))
    return round(ordered[index], 6)


def reconstruct_peak_exposure(
    events: list[dict[str, Any]],
    balance_rows: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    """Reconstruct concurrent matched-position exposure from open/close events.

    A matched-trade row is treated as one position slice. This captures overlap
    and re-adds in the matched event stream; genuinely unreported open volume
    must be supplied as an event with no ``exit_time`` by the caller.
    """
    balances: dict[tuple[str, int], list[tuple[date, float]]] = {}
    for row in balance_rows:
        try:
            key = (str(row["platform"]), int(row["login"]))
            timestamp = _parse_datetime(row["datetime"])
            balance = float(row.get("balance") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        balances.setdefault(key, []).append((timestamp.date(), balance))
    for values in balances.values():
        values.sort(key=lambda item: item[0])

    scheduled: dict[tuple[str, int], list[tuple[datetime, int, float, bool]]] = {}
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for row in events:
        try:
            key = (str(row["platform"]), int(row["login"]))
            opened = _parse_datetime(row["entry_time"])
            position_value = abs(float(row["entry_price"]) * float(row["volume"]))
        except (KeyError, TypeError, ValueError):
            continue
        record = result.setdefault(key, {
            "peak_position_value": 0.0,
            "peak_leverage_ratio": None,
            "leverage_values": [],
            "peak_leverage_values": [],
            "exposure_status": "complete_for_matched_events",
        })
        scheduled.setdefault(key, []).append((opened, 1, position_value, True))
        exit_value = row.get("exit_time")
        if exit_value in (None, ""):
            record["exposure_status"] = "includes_open_event_estimate"
        else:
            try:
                closed = _parse_datetime(exit_value)
            except (TypeError, ValueError):
                record["exposure_status"] = "invalid_close_time"
            else:
                scheduled[key].append((closed, 0, position_value, False))

    for key, timeline in scheduled.items():
        active_value = 0.0
        values = balances.get(key, [])
        balance_dates = [item[0] for item in values]
        daily_peaks: dict[date, float] = {}
        daily_leverage: dict[date, float] = {}
        for timestamp, priority, position_value, is_open in sorted(timeline, key=lambda item: (item[0], item[1])):
            if is_open:
                active_value += position_value
            else:
                active_value = max(0.0, active_value - position_value)
            day = timestamp.date()
            daily_peaks[day] = max(daily_peaks.get(day, 0.0), active_value)
            position = bisect_right(balance_dates, day) - 1
            if position >= 0 and values[position][1] > 0:
                daily_leverage[day] = max(daily_leverage.get(day, 0.0), active_value / values[position][1])

        record = result[key]
        record["peak_position_value"] = round(max(daily_peaks.values(), default=0.0), 6)
        record["peak_leverage_values"] = [round(value, 6) for value in daily_leverage.values()]
        record["leverage_values"] = list(record["peak_leverage_values"])
        record["peak_leverage_ratio"] = max(record["peak_leverage_values"], default=None)
        record["leverage_p95_ratio"] = _p95(record["peak_leverage_values"])
        if not values:
            record["exposure_status"] = "missing_daily_balance"

    return result


def build_unmatched_open_events(
    raw_deal_rows: list[dict[str, Any]],
    matched_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn raw entry deals not fully represented by matched rows into open events."""
    matched_volume: dict[tuple[str, int, int], float] = {}
    for row in matched_events:
        try:
            key = (str(row["platform"]), int(row["login"]), int(row["entry_deal_id"]))
            matched_volume[key] = matched_volume.get(key, 0.0) + abs(float(row["volume"]))
        except (KeyError, TypeError, ValueError):
            continue

    open_events = []
    for row in raw_deal_rows:
        try:
            if int(row.get("entry", -1)) != 0:
                continue
            key = (str(row["platform"]), int(row["login"]), int(row["deal_id"]))
            raw_volume = abs(float(row["volume"]))
            remaining = raw_volume - matched_volume.get(key, 0.0)
            if remaining <= 1e-12:
                continue
            open_events.append({
                "platform": key[0],
                "login": key[1],
                "entry_time": row["time"],
                "entry_price": float(row["price"]),
                "volume": remaining,
                "exit_time": None,
                "entry_deal_id": key[2],
                "exit_deal_id": None,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return open_events
