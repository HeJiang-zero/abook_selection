from __future__ import annotations

from collections import Counter, defaultdict
from math import log10
from typing import Any, Iterable

from .service import AnalysisContext


def _key(account: dict[str, Any]) -> tuple[str, int]:
    return str(account["platform"]), int(account["login"])


def split_books(accounts: list[dict[str, Any]], abook_keys: set[tuple[str, int]]) -> tuple[list[dict], list[dict]]:
    abook = [account for account in accounts if _key(account) in abook_keys]
    bbook = [account for account in accounts if _key(account) not in abook_keys]
    return abook, bbook


def calculate_hedge_sensitivity(
    abook_accounts: list[dict[str, Any]],
    validation_turnover: float,
    base_increment: float,
    hedge_cost_bps: float,
) -> dict[str, float | None]:
    turnover = float(validation_turnover or sum(float(account.get("validation", {}).get("turnover", 0.0)) for account in abook_accounts))
    cost = turnover * float(hedge_cost_bps) / 10000.0
    break_even = (float(base_increment) / turnover * 10000.0) if turnover else None
    return {
        "hedge_cost_bps": float(hedge_cost_bps),
        "validation_turnover": turnover,
        "hedge_cost": round(cost, 6),
        "base_increment": float(base_increment),
        "after_cost_increment": round(float(base_increment) - cost, 6),
        "break_even_bps": round(break_even, 6) if break_even is not None else None,
    }


def _phase_metrics(accounts: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    values = [float(account.get(phase, {}).get("client_net_pnl", 0.0)) for account in accounts]
    positive = [value for value in values if value > 0]
    negative = [value for value in values if value < 0]
    return {
        "accounts": len(accounts),
        "active_accounts": sum(1 for account in accounts if account.get(phase, {}).get("trade_count", 0) > 0),
        "total_client_net_pnl": round(sum(values), 6),
        "profitable_accounts": len(positive),
        "loss_accounts": len(negative),
        "pnl_distribution": values,
        "top_5_share": round(sum(sorted(values, reverse=True)[:5]) / sum(values), 6) if sum(values) else 0.0,
    }


def _style(account: dict[str, Any]) -> str:
    if account.get("martingale_blocked") or account.get("martingale_risk_level"):
        return "martingale"
    holding = float(account.get("selection", {}).get("median_holding_seconds", 0) or 0)
    trades = int(account.get("selection", {}).get("trade_count", 0) or 0)
    if holding < 60:
        return "scalping"
    if trades >= 100:
        return "high_frequency"
    if holding > 86400:
        return "swing"
    return "normal"


def _daily_series(context: AnalysisContext, accounts: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    keys = {_key(account) for account in accounts}
    grouped: dict[str, float] = defaultdict(float)
    for row in context.daily_rows:
        if (str(row.get("platform")), int(row.get("login", 0))) not in keys:
            continue
        grouped[str(row.get("trade_date", ""))[:10]] += float(row.get("client_net_pnl", 0) or 0)
    running = 0.0
    result = []
    for day in sorted(grouped):
        running += grouped[day]
        result.append({"date": day, "pnl": round(grouped[day], 6), "cumulative_pnl": round(running, 6), "book": label})
    return result


def build_book_analytics(
    context: AnalysisContext,
    accounts: list[dict[str, Any]],
    abook_keys: set[tuple[str, int]],
    hedge_cost_bps: float,
    symbol_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    abook, bbook = split_books(accounts, abook_keys)
    books = {"abook": abook, "bbook": bbook}
    pnl_structure = {
        book: {
            "selection": _phase_metrics(items, "selection"),
            "validation": _phase_metrics(items, "validation"),
            "daily_series": _daily_series(context, items, book),
        }
        for book, items in books.items()
    }
    user_structure = {}
    for book, items in books.items():
        style_counts = Counter(_style(account) for account in items)
        style_pnl = defaultdict(float)
        for account in items:
            style_pnl[_style(account)] += float(account.get("validation", {}).get("client_net_pnl", 0.0))
        user_structure[book] = {
            "styles": [{"style": style, "accounts": count, "validation_client_net_pnl": round(style_pnl[style], 6)} for style, count in sorted(style_counts.items())],
            "holding_seconds": [float(account.get("selection", {}).get("median_holding_seconds", 0) or 0) for account in items],
            "trade_counts": [int(account.get("selection", {}).get("trade_count", 0) or 0) for account in items],
            "symbols": list(symbol_rows or []),
        }
    abook_validation_turnover = sum(float(account.get("validation", {}).get("turnover", 0.0)) for account in abook)
    base_increment = sum(float(account.get("validation", {}).get("client_net_pnl", 0.0)) for account in abook)
    risk_exposure = {
        book: {"selection_turnover": sum(float(account.get("selection", {}).get("turnover", 0.0)) for account in items),
               "validation_turnover": sum(float(account.get("validation", {}).get("turnover", 0.0)) for account in items)}
        for book, items in books.items()
    }
    risk_exposure["abook"].update(calculate_hedge_sensitivity(abook, abook_validation_turnover, base_increment, hedge_cost_bps))
    risk_exposure["bbook"]["hedge_cost_bps"] = 0.0
    transitions = Counter((account.get("cohort", "observation"), account.get("validation_status", "no_trade")) for account in accounts)
    return {
        "pnl_structure": pnl_structure,
        "user_structure": user_structure,
        "risk_exposure": risk_exposure,
        "routing_quality": {
            "transitions": [{"cohort": cohort, "validation_status": status, "accounts": count} for (cohort, status), count in sorted(transitions.items())],
            "validation_partial": context.validation_end.endswith("13"),
            "sample_warning": sum(1 for account in abook if account.get("validation", {}).get("trade_count", 0) > 0) < 30,
        },
    }
