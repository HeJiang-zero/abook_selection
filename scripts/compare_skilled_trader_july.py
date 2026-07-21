#!/usr/bin/env python3
"""Compare legacy July-tuned rules vs skilled-trader defaults on the same window."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.avg_profit import build_avg_profit_filter
from app.config import load_env_file
from app.martingale import build_martingale_filter
from app.models import AnalysisRequest, AnalysisRules
from app.r4 import build_r4_filter
from app.repository import ClickHouseRepository
from app.risk import build_local_risk_filter
from app.service import build_two_stage_payload


LEGACY_RULES = AnalysisRules(
    min_trades=75,
    min_active_days=0,
    min_active_months=0,
    min_win_rate=0.5,
    min_profit_factor=1.25,
    min_payoff_ratio=0.4,
    payoff_link_factor=0.0,
    min_selection_monthly_consistency=0.0,
    min_positive_month_rate=0.0,
    max_top1_day_profit_contribution=0.3,
    max_daily_profit_month_contribution=1.0,
    max_leverage_p95_ratio=500.0,
    max_peak_leverage_ratio=500.0,
    max_high_leverage_holding_seconds=60.0,
    min_direction_day_rate_lower_bound=0.0,
    min_return_drawdown_ratio=0.0,
    high_confidence_trades=100,
    require_selection_monthly_positive=False,
    require_selection_net_positive=False,
    enable_r4=False,
)


def _summarize(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    abook = [a for a in payload["accounts"] if a["book"] == "abook"]
    validation = payload["validation"]["groups"]["abook"]
    traded = [a for a in abook if a["validation"]["trade_count"] > 0]
    profitable = [
        a for a in traded
        if float(a["validation"]["client_net_pnl"]) > 10
    ]
    losing = [
        a for a in traded
        if float(a["validation"]["client_net_pnl"]) < -10
    ]
    return {
        "label": label,
        "abook_accounts": len(abook),
        "validation_traded": len(traded),
        "validation_profitable": len(profitable),
        "validation_losing": len(losing),
        "continue_profit_rate": (
            round(len(profitable) / len(traded), 4) if traded else None
        ),
        "validation_client_net_pnl": round(float(validation["client_net_pnl"]), 2),
        "validation_profit_factor": validation.get("profit_factor"),
        "selection_client_net_pnl": round(
            float(payload["selection"]["groups"]["abook"]["client_net_pnl"]), 2
        ),
        "rules_profile": payload["rules"].get("profile"),
        "rules_snapshot": {
            "min_trades": payload["rules"].get("min_trades"),
            "min_active_days": payload["rules"].get("min_active_days"),
            "min_profit_factor": payload["rules"].get("min_profit_factor"),
            "min_payoff_ratio": payload["rules"].get("min_payoff_ratio"),
            "payoff_link_factor": payload["rules"].get("payoff_link_factor"),
            "min_positive_month_rate": payload["rules"].get("min_positive_month_rate"),
            "max_top1_day_profit_contribution": payload["rules"].get("max_top1_day_profit_contribution"),
            "max_leverage_p95_ratio": payload["rules"].get("max_leverage_p95_ratio"),
            "require_selection_monthly_positive": payload["rules"].get("selection_months_positive_required"),
            "require_selection_net_positive": payload["rules"].get("selection_net_positive_required"),
        },
    }


def _run(rows: list[dict[str, Any]], request: AnalysisRequest, martingale_snapshot: Any, rules: AnalysisRules) -> dict[str, Any]:
    return build_two_stage_payload(
        rows,
        overview_rows=rows,
        selection_start=request.selection.start.isoformat(),
        selection_end=request.selection.end.isoformat(),
        validation_start=request.validation.start.isoformat(),
        validation_end=request.validation.end.isoformat(),
        min_trades=rules.min_trades,
        min_active_days=rules.min_active_days,
        min_active_months=rules.min_active_months,
        min_win_rate=rules.min_win_rate,
        min_profit_factor=rules.min_profit_factor,
        min_payoff_ratio=rules.min_payoff_ratio,
        payoff_link_factor=rules.payoff_link_factor,
        min_avg_daily_profit=rules.min_avg_daily_profit,
        min_avg_profit=rules.min_avg_profit,
        min_selection_monthly_consistency=rules.min_selection_monthly_consistency,
        min_positive_month_rate=rules.min_positive_month_rate,
        max_top1_day_profit_contribution=rules.max_top1_day_profit_contribution,
        max_daily_profit_month_contribution=rules.max_daily_profit_month_contribution,
        max_leverage_p95_ratio=rules.max_leverage_p95_ratio,
        max_high_leverage_holding_seconds=rules.max_high_leverage_holding_seconds,
        min_direction_day_rate_lower_bound=rules.min_direction_day_rate_lower_bound,
        min_return_drawdown_ratio=rules.min_return_drawdown_ratio,
        min_stability_score=rules.min_stability_score,
        high_confidence_trades=rules.high_confidence_trades,
        high_confidence_days=rules.high_confidence_days,
        martingale_snapshot=martingale_snapshot,
        excluded_martingale_levels=rules.excluded_martingale_levels,
        require_selection_monthly_positive=rules.require_selection_monthly_positive,
        require_selection_net_positive=rules.require_selection_net_positive,
        enable_r4=rules.enable_r4,
        r4_min_passing_weeks=rules.r4_min_passing_weeks,
    )


def main() -> None:
    load_env_file()
    request = AnalysisRequest()
    risk_filter = build_local_risk_filter(request)
    r4_snapshot = build_r4_filter(request)
    martingale_snapshot = build_martingale_filter(request)
    avg_profit_snapshot = build_avg_profit_filter(request)
    repository = ClickHouseRepository()
    overview_rows = repository.fetch_analysis(request)
    rows = martingale_snapshot.enrich_rows(risk_filter.snapshot.enrich_rows(overview_rows))
    rows = r4_snapshot.enrich_rows(rows)
    rows = avg_profit_snapshot.enrich_rows(rows)

    skilled_rules = AnalysisRules()
    legacy_payload = _run(rows, request, martingale_snapshot, LEGACY_RULES)
    skilled_payload = _run(rows, request, martingale_snapshot, skilled_rules)

    report = {
        "window": {
            "selection": [request.selection.start.isoformat(), request.selection.end.isoformat()],
            "validation": [request.validation.start.isoformat(), request.validation.end.isoformat()],
        },
        "legacy": _summarize("legacy_july_tuned", legacy_payload),
        "skilled": _summarize("skilled_trader", skilled_payload),
        "skilled_defaults": skilled_rules.model_dump(),
    }
    out = ROOT / "docs" / "analysis" / "2026-07-21-skilled-trader-july-compare.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["legacy"], indent=2, ensure_ascii=False))
    print(json.dumps(report["skilled"], indent=2, ensure_ascii=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
