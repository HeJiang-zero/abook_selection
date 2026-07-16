from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Iterable

from .service import AnalysisContext


AccountKey = tuple[str, int]


def _key(account: dict[str, Any]) -> AccountKey:
    return str(account["platform"]), int(account["login"])


def _row_key(row: dict[str, Any]) -> AccountKey:
    return str(row.get("platform")), int(row.get("login", 0))


def split_books(accounts: list[dict[str, Any]], abook_keys: set[AccountKey]) -> tuple[list[dict], list[dict]]:
    population_keys = {_key(account) for account in accounts}
    abook = [account for account in accounts if _key(account) in abook_keys]
    bbook = [account for account in accounts if _key(account) not in abook_keys]
    if {_key(account) for account in abook} & {_key(account) for account in bbook}:
        raise ValueError("Abook and Bbook account sets overlap")
    if {_key(account) for account in abook} | {_key(account) for account in bbook} != population_keys:
        raise ValueError("Abook and Bbook do not partition the supplied population")
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


def _drawdown(values: Iterable[float]) -> float:
    running = 0.0
    peak = 0.0
    maximum = 0.0
    for value in values:
        running += float(value)
        peak = max(peak, running)
        maximum = max(maximum, peak - running)
    return round(maximum, 6)


def _concentration(values: list[float]) -> dict[str, dict[str, float]]:
    net_total = sum(values)
    absolute_total = sum(abs(value) for value in values)
    ordered = sorted(values, key=abs, reverse=True)
    result = {}
    for count in (5, 10, 20):
        result[f"top_{count}"] = {
            "net_share": round(sum(ordered[:count]) / net_total, 6) if net_total else 0.0,
            "absolute_share": round(sum(abs(value) for value in ordered[:count]) / absolute_total, 6) if absolute_total else 0.0,
        }
    return result


def _phase_metrics(accounts: list[dict[str, Any]], phase: str, book: str) -> dict[str, Any]:
    values = [float(account.get(phase, {}).get("client_net_pnl", 0.0)) for account in accounts]
    positive = [value for value in values if value > 0]
    negative = [value for value in values if value < 0]
    win_rates = [float(account.get(phase, {}).get("win_rate", 0.0)) for account in accounts]
    profit_factors = [
        float(account[phase]["profit_factor"])
        for account in accounts
        if account.get(phase, {}).get("profit_factor") is not None
    ]
    customer_net_pnl = round(sum(values), 6)
    return {
        "accounts": len(accounts),
        "active_accounts": sum(1 for account in accounts if account.get(phase, {}).get("trade_count", 0) > 0),
        "total_client_net_pnl": customer_net_pnl,
        "customer_net_pnl": customer_net_pnl,
        "bbook_company_profit": round(-customer_net_pnl, 6),
        "company_profit_if_current_book": 0.0 if book == "abook" else round(-customer_net_pnl, 6),
        "theoretical_company_increment_if_routed_abook": customer_net_pnl if book == "abook" else 0.0,
        "profitable_accounts": len(positive),
        "loss_accounts": len(negative),
        "pnl_distribution": values,
        "win_rate_distribution": win_rates,
        "profit_factor_distribution": profit_factors,
        "profit_concentration": _concentration(values),
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


def _row_date(row: dict[str, Any]) -> date:
    value = row.get("trade_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _daily_series(context: AnalysisContext, accounts: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    keys = {_key(account) for account in accounts}
    grouped: dict[date, float] = defaultdict(float)
    for row in context.daily_rows:
        if _row_key(row) not in keys:
            continue
        grouped[_row_date(row)] += float(row.get("client_net_pnl", 0) or 0)
    running = 0.0
    company_running = 0.0
    result = []
    for day in sorted(grouped):
        running += grouped[day]
        selection_start = date.fromisoformat(context.selection_start)
        selection_end = date.fromisoformat(context.selection_end)
        validation_start = date.fromisoformat(context.validation_start)
        validation_end = date.fromisoformat(context.validation_end)
        phase = "selection" if selection_start <= day <= selection_end else "validation" if validation_start <= day <= validation_end else "other"
        company_pnl = 0.0 if label == "abook" else -grouped[day]
        company_running += company_pnl
        result.append({
            "date": day.isoformat(),
            "phase": phase,
            "pnl": round(grouped[day], 6),
            "customer_pnl": round(grouped[day], 6),
            "cumulative_pnl": round(running, 6),
            "company_pnl": round(company_pnl, 6),
            "company_cumulative_pnl": round(company_running, 6),
            "book": label,
        })
    return result


def _bucket(values: Iterable[float], edges: list[float]) -> list[dict[str, Any]]:
    result = []
    values = list(values)
    for index, lower in enumerate(edges):
        upper = edges[index + 1] if index + 1 < len(edges) else None
        count = sum(1 for value in values if value >= lower and (upper is None or value < upper))
        result.append({"lower": lower, "upper": upper, "accounts": count})
    return result


def _aggregate_symbol_rows(rows: Iterable[dict[str, Any]], keys: set[AccountKey] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"trade_count": 0.0, "volume": 0.0, "market_pnl": 0.0, "turnover": 0.0})
    for row in rows:
        if keys is not None and _row_key(row) not in keys:
            continue
        item = grouped[str(row.get("symbol", "unknown"))]
        for field in item:
            item[field] += float(row.get(field, 0) or 0)
    return [
        {"symbol": symbol, **{field: round(value, 6) for field, value in metrics.items()}}
        for symbol, metrics in sorted(grouped.items(), key=lambda pair: abs(pair[1]["market_pnl"]), reverse=True)
    ]


def _symbol_heatmap(symbol_rows: Any, book: str, keys: set[AccountKey]) -> list[dict[str, Any]]:
    if isinstance(symbol_rows, dict):
        population = _aggregate_symbol_rows(symbol_rows.get("population", []))
        selected = _aggregate_symbol_rows(symbol_rows.get("abook", []))
        if book == "abook":
            return selected
        selected_by_symbol = {row["symbol"]: row for row in selected}
        result = []
        for row in population:
            subtract = selected_by_symbol.get(row["symbol"], {})
            result.append({
                field: round(float(row.get(field, 0)) - float(subtract.get(field, 0)), 6)
                for field in ("trade_count", "volume", "market_pnl", "turnover")
            } | {"symbol": row["symbol"]})
        return result
    return _aggregate_symbol_rows(symbol_rows or [], keys)


def _turnover_series(turnover_rows: Any, book: str, keys: set[AccountKey]) -> list[dict[str, Any]]:
    if isinstance(turnover_rows, dict):
        if book == "abook":
            rows = turnover_rows.get("abook", [])
        else:
            population = turnover_rows.get("population", [])
            abook = turnover_rows.get("abook", [])
            rows = population
            # Difference is applied after aggregation below to retain all dates.
            population_series = _turnover_series(population, "population", keys)
            abook_series = _turnover_series(abook, "abook", keys)
            abook_by_date = {row["date"]: row for row in abook_series}
            return [{
                "date": row["date"],
                "turnover": round(row["turnover"] - abook_by_date.get(row["date"], {}).get("turnover", 0), 6),
                "long_turnover": round(row["long_turnover"] - abook_by_date.get(row["date"], {}).get("long_turnover", 0), 6),
                "short_turnover": round(row["short_turnover"] - abook_by_date.get(row["date"], {}).get("short_turnover", 0), 6),
                "trade_count": row["trade_count"] - abook_by_date.get(row["date"], {}).get("trade_count", 0),
            } for row in population_series]
    else:
        rows = turnover_rows or []
    grouped: dict[date, dict[str, float]] = defaultdict(lambda: {"turnover": 0.0, "long_turnover": 0.0, "short_turnover": 0.0, "trade_count": 0})
    for row in rows:
        if keys and _row_key(row) not in keys:
            continue
        item = grouped[_row_date(row)]
        for field in item:
            item[field] += float(row.get(field, 0) or 0)
    return [{"date": day.isoformat(), **{field: round(value, 6) for field, value in item.items()}} for day, item in sorted(grouped.items())]


def _daily_hit_curves(context: AnalysisContext, accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    books = {_key(account): "abook" if account.get("cohort") == "abook_candidate" else "bbook" for account in accounts}
    grouped: dict[date, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"active": 0, "hits": 0, "net_pnl": 0.0}))
    for row in context.daily_rows:
        book = books.get(_row_key(row))
        if not book:
            continue
        value = float(row.get("client_net_pnl", 0) or 0)
        item = grouped[_row_date(row)][book]
        if int(row.get("matched_trades", 0) or 0) > 0:
            item["active"] += 1
            item["hits"] += 1 if (value > 0 if book == "abook" else value < 0) else 0
        item["net_pnl"] += value
    cumulative = 0
    result = []
    for day in sorted(grouped):
        abook = grouped[day].get("abook", {"active": 0, "hits": 0, "net_pnl": 0.0})
        bbook = grouped[day].get("bbook", {"active": 0, "hits": 0, "net_pnl": 0.0})
        difference = abook["hits"] - bbook["hits"]
        cumulative += difference
        result.append({
            "date": day.isoformat(),
            "abook_hit_rate": round(abook["hits"] / abook["active"], 6) if abook["active"] else 0.0,
            "bbook_hit_rate": round(bbook["hits"] / bbook["active"], 6) if bbook["active"] else 0.0,
            "abook_net_pnl": round(abook["net_pnl"], 6),
            "bbook_net_pnl": round(bbook["net_pnl"], 6),
            "hit_difference": difference,
            "cumulative_hit_difference": cumulative,
        })
    return result


def _company_profit_comparison(
    context: AnalysisContext,
    accounts: list[dict[str, Any]],
    turnover_by_book: dict[str, list[dict[str, Any]]],
    hedge_cost_bps: float,
) -> list[dict[str, Any]]:
    account_books = {_key(account): "abook" if account.get("cohort") == "abook_candidate" else "bbook" for account in accounts}
    grouped: dict[date, dict[str, float]] = defaultdict(lambda: {"baseline_user_net_pnl": 0.0, "bbook_user_net_pnl": 0.0})
    rows = context.overview_daily_rows or context.daily_rows
    for row in rows:
        day = _row_date(row)
        value = float(row.get("client_net_pnl", 0) or 0)
        grouped[day]["baseline_user_net_pnl"] += value
        if account_books.get(_row_key(row)) == "bbook":
            grouped[day]["bbook_user_net_pnl"] += value
    abook_turnover = {row["date"]: row["turnover"] for row in turnover_by_book.get("abook", [])}
    result = []
    for day in sorted(grouped):
        item = grouped[day]
        hedge_cost = abook_turnover.get(day.isoformat(), 0.0) * float(hedge_cost_bps) / 10000.0
        baseline = -item["baseline_user_net_pnl"]
        after = -item["bbook_user_net_pnl"] - hedge_cost
        result.append({
            "date": day.isoformat(),
            "baseline_company_profit": round(baseline, 6),
            "after_routing_company_profit": round(after, 6),
            "incremental_change": round(after - baseline, 6),
            "hedge_cost": round(hedge_cost, 6),
        })
    return result


def build_book_analytics(
    context: AnalysisContext,
    accounts: list[dict[str, Any]],
    abook_keys: set[AccountKey],
    hedge_cost_bps: float,
    symbol_rows: Iterable[dict[str, Any]] | dict[str, list[dict[str, Any]]] | None = None,
    turnover_rows: Iterable[dict[str, Any]] | dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    abook, bbook = split_books(accounts, abook_keys)
    books = {"abook": abook, "bbook": bbook}
    daily_series = {book: _daily_series(context, items, book) for book, items in books.items()}
    pnl_structure = {}
    for book, items in books.items():
        validation_series = [row["pnl"] for row in daily_series[book] if row["date"] >= context.validation_start and row["date"] <= context.validation_end]
        pnl_structure[book] = {
            "selection": _phase_metrics(items, "selection", book),
            "validation": _phase_metrics(items, "validation", book),
            "daily_series": daily_series[book],
            "max_drawdown": _drawdown(validation_series),
            "profit_concentration": _concentration([float(account.get("validation", {}).get("client_net_pnl", 0.0)) for account in items]),
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
            "holding_duration_bins": _bucket((float(account.get("selection", {}).get("median_holding_seconds", 0) or 0) for account in items), [0, 60, 300, 3600, 86400]),
            "trade_counts": [int(account.get("selection", {}).get("trade_count", 0) or 0) for account in items],
            "trade_volume_bins": _bucket((float(account.get("selection", {}).get("total_volume", 0) or 0) for account in items), [0, 1, 10, 100, 1000]),
            "symbol_heatmap": _symbol_heatmap(symbol_rows, book, {_key(account) for account in items}),
        }

    turnover_by_book = {book: _turnover_series(turnover_rows, book, {_key(account) for account in items}) for book, items in books.items()}
    risk_exposure = {}
    for book, items in books.items():
        exposure = {
            "selection_turnover": sum(float(account.get("selection", {}).get("turnover", 0.0)) for account in items),
            "validation_turnover": sum(float(account.get("validation", {}).get("turnover", 0.0)) for account in items),
            "daily_turnover": turnover_by_book[book],
            "peak_leverage_distribution": [float(account.get("risk_peak_leverage_ratio", account.get("selection", {}).get("risk_peak_leverage_ratio", 0.0)) or 0) for account in items],
            "max_exposure_dates": sorted(turnover_by_book[book], key=lambda row: row["turnover"], reverse=True)[:10],
        }
        risk_exposure[book] = exposure
    abook_validation_turnover = sum(float(account.get("validation", {}).get("turnover", 0.0)) for account in abook)
    base_increment = sum(float(account.get("validation", {}).get("client_net_pnl", 0.0)) for account in abook)
    risk_exposure["abook"].update(calculate_hedge_sensitivity(abook, abook_validation_turnover, base_increment, hedge_cost_bps))
    risk_exposure["bbook"]["hedge_cost_bps"] = 0.0

    transitions = Counter((account.get("cohort", "observation"), account.get("validation_status", "no_trade")) for account in accounts)
    transition_matrix: dict[str, dict[str, int]] = defaultdict(dict)
    for (cohort, status), count in transitions.items():
        transition_matrix[cohort][status] = count
    return {
        "pnl_structure": pnl_structure,
        "user_structure": user_structure,
        "risk_exposure": risk_exposure,
        "routing_quality": {
            "transitions": [{"cohort": cohort, "validation_status": status, "accounts": count} for (cohort, status), count in sorted(transitions.items())],
            "transition_matrix": dict(transition_matrix),
            "daily_hit_curves": _daily_hit_curves(context, accounts),
            "company_profit_comparison": _company_profit_comparison(context, accounts, turnover_by_book, hedge_cost_bps),
            "validation_partial": context.validation_end.endswith("13"),
            "sample_warning": sum(1 for account in abook if account.get("validation", {}).get("trade_count", 0) > 0) < 30,
        },
    }
