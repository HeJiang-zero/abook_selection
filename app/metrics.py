from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable


ZERO = Decimal("0")


def month_bucket(value: datetime) -> str:
    """Return the UTC calendar month used by the analysis layer."""
    return f"{value.year:04d}-{value.month:02d}"


def calculate_drawdown(values: Iterable[Decimal]) -> Decimal:
    """Return the maximum peak-to-trough loss for a cumulative series."""
    peak = ZERO
    drawdown = ZERO
    for value in values:
        cumulative = Decimal(value)
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def calculate_summary_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Decimal]:
    """Separate trading P&L, execution costs, and funding movements."""
    market_pnl = ZERO
    costs = ZERO
    funding_pnl = ZERO
    for row in rows:
        action = int(row.get("action", 0))
        profit = Decimal(row.get("profit", ZERO))
        storage = Decimal(row.get("storage", ZERO))
        commission = Decimal(row.get("commission", ZERO))
        fee = Decimal(row.get("fee", ZERO))
        if action in (0, 1):
            market_pnl += profit
            costs += storage + commission + fee
        elif action in (2, 3):
            funding_pnl += profit
    return {
        "market_pnl": market_pnl,
        "client_net_pnl": market_pnl + costs,
        "costs": costs,
        "funding_pnl": funding_pnl,
    }
