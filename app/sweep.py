from __future__ import annotations

from itertools import product
from typing import Any

from .models import AnalysisRules
from .service import AnalysisContext, classify_accounts


MAX_SWEEP_COMBINATIONS = 500
NUMERIC_RULE_FIELDS = {
    "min_trades", "min_active_days", "min_win_rate", "min_profit_factor",
    "min_payoff_ratio", "min_avg_daily_profit", "min_selection_monthly_consistency",
    "min_positive_month_rate", "max_top1_day_profit_contribution", "max_peak_leverage_ratio",
    "max_high_leverage_holding_seconds", "min_direction_day_rate_lower_bound",
    "min_stability_score", "high_confidence_trades", "high_confidence_days",
}


def expand_rule_grid(grid: dict[str, list[Any]], rules: AnalysisRules) -> list[AnalysisRules]:
    if not grid:
        return [rules]
    unknown = sorted(set(grid) - NUMERIC_RULE_FIELDS)
    if unknown:
        raise ValueError(f"unsupported sweep rule fields: {unknown}")
    fields = list(grid)
    if any(not isinstance(values, list) or not values for values in grid.values()):
        raise ValueError("each sweep grid field must contain a non-empty list")
    combinations = 1
    for values in grid.values():
        combinations *= len(values)
    if combinations > MAX_SWEEP_COMBINATIONS:
        raise ValueError(f"sweep grid has {combinations} combinations; maximum is {MAX_SWEEP_COMBINATIONS}")
    base = rules.model_dump()
    expanded = []
    for values in product(*(grid[field] for field in fields)):
        candidate = dict(base)
        candidate.update(dict(zip(fields, values)))
        try:
            expanded.append(AnalysisRules.model_validate(candidate))
        except Exception as exc:
            raise ValueError(f"invalid sweep value for {fields}") from exc
    return expanded


def _sum_validation(accounts: list[dict[str, Any]]) -> float:
    return round(sum(float(account["validation"].get("client_net_pnl", 0.0)) for account in accounts), 6)


def _result_row(accounts: list[dict[str, Any]], rules: AnalysisRules) -> dict[str, Any]:
    abook = [account for account in accounts if account["cohort"] == "abook_candidate"]
    active = [account for account in abook if account["validation"]["trade_count"] > 0]
    profitable = [account for account in active if account["validation_status"] == "profitable"]
    validation_increment = _sum_validation(abook)
    misjudge_cost = round(
        sum(max(0.0, -float(account["validation"].get("client_net_pnl", 0.0))) for account in abook),
        6,
    )
    observation = [account for account in accounts if account["cohort"] == "observation"]
    observation_active = [account for account in observation if account["validation"]["trade_count"] > 0]
    precision = len(profitable) / len(active) if active else 0.0
    observation_rate = (
        sum(1 for account in observation_active if account["validation_status"] == "profitable") / len(observation_active)
        if observation_active else 0.0
    )
    return {
        "rules": rules.model_dump(),
        "abook_core": len(abook),
        "validation_active_accounts": len(active),
        "continue_profit_rate": round(precision, 6),
        "validation_increment": validation_increment,
        "misjudge_cost": misjudge_cost,
        "net_gain": validation_increment,
        "precision": round(precision, 6),
        "lift": round(precision / observation_rate, 6) if observation_rate else 0.0,
        "martingale_excluded": sum(1 for account in accounts if account.get("martingale_blocked")),
        "sample_warning": len(active) < 30,
    }


def evaluate_sweep(
    context: AnalysisContext,
    base_rules: AnalysisRules,
    grid: dict[str, list[Any]],
    objective: str,
    max_misjudge_cost: float | None,
    *,
    personal_candidate_logins: set[int] | None = None,
    martingale_snapshot: Any | None = None,
) -> dict[str, Any]:
    if objective == "increment_with_cost_cap" and max_misjudge_cost is None:
        raise ValueError("max_misjudge_cost is required for increment_with_cost_cap")
    rule_sets = expand_rule_grid(grid, base_rules)
    results = [
        _result_row(
            classify_accounts(
                context,
                rules,
                personal_candidate_logins=personal_candidate_logins,
                martingale_snapshot=martingale_snapshot,
            ),
            rules,
        )
        for rules in rule_sets
    ]
    if objective == "increment_with_cost_cap":
        results = [row for row in results if row["misjudge_cost"] <= float(max_misjudge_cost)]
    sort_key = {
        "validation_increment": lambda row: row["validation_increment"],
        "increment_with_cost_cap": lambda row: row["validation_increment"],
        "validation_precision": lambda row: row["precision"],
    }.get(objective)
    if sort_key is None:
        raise ValueError(f"unsupported sweep objective: {objective}")
    results.sort(key=sort_key, reverse=True)
    return {
        "results": results,
        "combinations": len(rule_sets),
        "objective": objective,
        "guardrails": {
            "validation_partial": context.validation_end.endswith("13"),
            "sample_in_selection": "validation period is used for in-sample ranking; use rolling validation",
            "max_combinations": MAX_SWEEP_COMBINATIONS,
            "max_misjudge_cost": max_misjudge_cost,
        },
    }
