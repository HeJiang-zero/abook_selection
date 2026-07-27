from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Deque, Iterable, List, Optional, Tuple


VOLUME_TOLERANCE = 0.0001


def _first(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        return _as_datetime(to_pydatetime())
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def matched_trade_key(row: dict[str, Any]) -> Tuple[str, int, str, int, int]:
    return (
        str(_first(row, "platform", "Platform", default="")),
        int(_first(row, "login", "Login", default=0)),
        str(_first(row, "symbol", "Symbol", default="")),
        int(_first(row, "entry_deal_id", "EntryDealID", default=0)),
        int(_first(row, "exit_deal_id", "ExitDealID", default=0)),
    )


def load_initial_entries(rows: Iterable[dict[str, Any]]) -> List[dict[str, Any]]:
    entries: List[dict[str, Any]] = []
    for row in rows:
        remaining = _float(_first(row, "remaining", "remaining_volume", "RemainingVolume"))
        if remaining <= VOLUME_TOLERANCE:
            continue
        direction = str(_first(row, "direction", "Direction", default="Long")).lower()
        entries.append({
            "deal_id": int(_first(row, "deal_id", "entry_deal_id", "EntryDealID", default=0)),
            "position_id": int(_first(row, "position_id", "PositionID", default=0)),
            "time": _as_datetime(_first(row, "time", "open_time", "EntryTime")),
            "price": _float(_first(row, "price", "open_price", "EntryPrice")),
            "remaining": remaining,
            "direction": "Long" if direction in {"long", "buy", "0"} else "Short",
            "login": int(_first(row, "login", "Login", default=0)),
            "platform": str(_first(row, "platform", "Platform", default="")),
            "symbol": str(_first(row, "symbol", "Symbol", default="")),
        })
    entries.sort(key=lambda item: (item["time"], item["deal_id"]))
    return entries


def _new_entry(deal: dict[str, Any], volume: float, direction: str) -> dict[str, Any]:
    return {
        "deal_id": int(_first(deal, "Deal", "deal", "split_id", default=0)),
        "position_id": int(_first(deal, "PositionID", "position_id", "ticket", default=0)),
        "time": _as_datetime(_first(deal, "Time", "time", "deal_time")),
        "price": _float(_first(deal, "Price", "price")),
        "remaining": float(volume),
        "direction": direction,
        "login": int(_first(deal, "Login", "login", default=0)),
        "platform": str(_first(deal, "Platform", "platform", default="")),
        "symbol": str(_first(deal, "Symbol", "symbol", default="")),
    }


def _unmatched_exit(deal: dict[str, Any], volume: float, closes_long: bool) -> dict[str, Any]:
    return {
        "login": int(_first(deal, "Login", "login", default=0)),
        "platform": str(_first(deal, "Platform", "platform", default="")),
        "symbol": str(_first(deal, "Symbol", "symbol", default="")),
        "exit_deal_id": int(_first(deal, "Deal", "deal", "split_id", default=0)),
        "exit_time": _as_datetime(_first(deal, "Time", "time", "deal_time")),
        "volume": float(volume),
        "direction": "Long" if closes_long else "Short",
    }


def _emit_match(
    entry: dict[str, Any], deal: dict[str, Any], matched: float, closes_long: bool
) -> dict[str, Any]:
    entry_price = float(entry["price"])
    exit_price = _float(_first(deal, "Price", "price"))
    entry_time = entry["time"]
    exit_time = _as_datetime(_first(deal, "Time", "time", "deal_time"))
    raw_rate = _first(deal, "RateProfit", "rate_profit", "conv_rate", default=1.0)
    exchange_rate = _float(raw_rate, default=1.0)
    if exchange_rate == 0.0:
        exchange_rate = 1.0
    price_diff = exit_price - entry_price if closes_long else entry_price - exit_price
    holding_seconds = max(0.0, (exit_time - entry_time).total_seconds())
    return {
        "login": int(_first(deal, "Login", "login", default=0)),
        "platform": str(_first(deal, "Platform", "platform", default="")),
        "symbol": str(_first(deal, "Symbol", "symbol", default="")),
        "direction": "Long" if closes_long else "Short",
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "volume": float(matched),
        "profit": float(price_diff * matched * exchange_rate),
        "holding_seconds": float(holding_seconds),
        "turnover": float((entry_price + exit_price) * matched * exchange_rate),
        "entry_deal_id": int(entry["deal_id"]),
        "exit_deal_id": int(_first(deal, "Deal", "deal", "split_id", default=0)),
    }


def fifo_match(
    deals: Iterable[dict[str, Any]],
    initial_entries: Optional[Iterable[dict[str, Any]]] = None,
) -> Tuple[List[dict[str, Any]], List[dict[str, Any]], List[dict[str, Any]]]:
    long_queue: Deque[dict[str, Any]] = deque()
    short_queue: Deque[dict[str, Any]] = deque()
    initial = load_initial_entries(initial_entries or [])
    net = 0.0
    for entry in initial:
        (long_queue if entry["direction"] == "Long" else short_queue).append(entry)
        net += entry["remaining"] if entry["direction"] == "Long" else -entry["remaining"]

    normalized_deals = list(deals)
    normalized_deals.sort(key=lambda item: (
        _as_datetime(_first(item, "Time", "time", "deal_time")),
        int(_first(item, "Deal", "deal", "split_id", default=0)),
    ))
    matched_trades: List[dict[str, Any]] = []
    unmatched_exits: List[dict[str, Any]] = []

    for deal in normalized_deals:
        volume = _float(_first(deal, "Volume", "volume"))
        if volume <= VOLUME_TOLERANCE:
            continue
        action = int(_first(deal, "Action", "action", default=0))
        if action not in (0, 1):
            continue
        is_buy = action == 0
        new_net = net + volume if is_buy else net - volume
        closing = 0.0
        opening = 0.0
        closes_long = False
        opens_long = False

        if net > VOLUME_TOLERANCE and new_net < -VOLUME_TOLERANCE:
            closing, opening, closes_long = abs(net), abs(new_net), True
        elif net < -VOLUME_TOLERANCE and new_net > VOLUME_TOLERANCE:
            closing, opening, opens_long = abs(net), abs(new_net), True
        elif net > VOLUME_TOLERANCE and new_net >= -VOLUME_TOLERANCE:
            if new_net > net + VOLUME_TOLERANCE:
                opening, opens_long = new_net - net, True
            else:
                closing, closes_long = max(0.0, net - new_net), True
        elif net < -VOLUME_TOLERANCE and new_net <= VOLUME_TOLERANCE:
            if abs(new_net) > abs(net) + VOLUME_TOLERANCE:
                opening, opens_long = abs(new_net) - abs(net), False
            else:
                closing, closes_long = max(0.0, abs(net) - abs(new_net)), False
        else:
            opening, opens_long = volume, is_buy

        net = new_net if abs(new_net) > VOLUME_TOLERANCE else 0.0
        queue = long_queue if closes_long else short_queue
        remaining = closing
        while remaining > VOLUME_TOLERANCE:
            if not queue:
                unmatched_exits.append(_unmatched_exit(deal, remaining, closes_long))
                break
            entry = queue[0]
            matched = min(float(entry["remaining"]), remaining)
            matched_trades.append(_emit_match(entry, deal, matched, closes_long))
            entry["remaining"] -= matched
            remaining -= matched
            if entry["remaining"] <= VOLUME_TOLERANCE:
                queue.popleft()

        if opening > VOLUME_TOLERANCE:
            entry = _new_entry(deal, opening, "Long" if opens_long else "Short")
            (long_queue if opens_long else short_queue).append(entry)

    unmatched_entries = [
        entry for queue in (long_queue, short_queue) for entry in queue
        if entry["remaining"] > VOLUME_TOLERANCE
    ]
    return matched_trades, unmatched_entries, unmatched_exits
