from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import clickhouse_connect

from app.config import get_settings, load_env_file
from app.queries import ALLOWED_PLATFORMS
from app.risk import snapshot_path


def _end_exclusive(value: str) -> str:
    return (date.fromisoformat(value) + timedelta(days=1)).isoformat()


def build_snapshot(selection_start: str, selection_end: str, platforms: list[str]) -> dict:
    settings = get_settings()
    if not settings.configured:
        raise RuntimeError("CLICKHOUSE_PASSWORD is not configured")
    selected = sorted(set(platforms) & ALLOWED_PLATFORMS)
    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        secure=settings.clickhouse_secure,
    )
    query = """
    WITH users AS (
        SELECT
            platform,
            login,
            any(`group`) AS account_group,
            any(balance_prev_month) AS balance_prev_month
        FROM risk.ods_mt5_users FINAL
        WHERE is_deleted = 0
          AND has({platforms:Array(String)}, platform)
          AND positionCaseInsensitive(`group`, 'test') = 0
          AND positionCaseInsensitive(`group`, 'demo') = 0
        GROUP BY platform, login
    ), daily AS (
        SELECT
            mt.platform,
            mt.login,
            toDate(mt.exit_time) AS trade_date,
            sum(abs(toFloat64(mt.turnover))) AS daily_turnover,
            if(any(toFloat64(u.balance_prev_month)) > 0,
               sum(abs(toFloat64(mt.turnover))) / any(toFloat64(u.balance_prev_month)),
               NULL) AS daily_leverage_ratio
        FROM risk.dwd_matched_trades AS mt FINAL
        INNER JOIN users AS u ON mt.platform = u.platform AND mt.login = u.login
        WHERE mt.exit_time >= {selection_start:Date}
          AND mt.exit_time < {selection_end_exclusive:Date}
        GROUP BY mt.platform, mt.login, trade_date
    ), holding AS (
        SELECT
            mt.platform,
            mt.login,
            quantileTDigest(0.5)(toFloat64(mt.holding_seconds)) AS median_holding_seconds
        FROM risk.dwd_matched_trades AS mt FINAL
        INNER JOIN users AS u ON mt.platform = u.platform AND mt.login = u.login
        WHERE mt.exit_time >= {selection_start:Date}
          AND mt.exit_time < {selection_end_exclusive:Date}
        GROUP BY mt.platform, mt.login
    ), aggregates AS (
        SELECT
            platform,
            login,
            sum(daily_turnover) AS total_turnover,
            count() AS active_days,
            max(daily_turnover) AS peak_daily_turnover,
            quantileTDigest(0.95)(daily_leverage_ratio) AS leverage_p95_ratio
        FROM daily
        GROUP BY platform, login
    )
    SELECT
        u.platform AS platform,
        u.login AS login,
        u.balance_prev_month AS balance_prev_month,
        coalesce(a.total_turnover, 0) AS total_turnover,
        coalesce(a.active_days, 0) AS active_days,
        coalesce(a.peak_daily_turnover, 0) AS peak_daily_turnover,
        coalesce(a.leverage_p95_ratio, 0) AS leverage_p95_ratio,
        coalesce(h.median_holding_seconds, 0) AS median_holding_seconds
    FROM users AS u
    LEFT JOIN aggregates AS a ON u.platform = a.platform AND u.login = a.login
    LEFT JOIN holding AS h ON u.platform = h.platform AND u.login = h.login
    ORDER BY u.platform, u.login
    """
    result = client.query(query, parameters={
        "platforms": selected,
        "selection_start": selection_start,
        "selection_end_exclusive": _end_exclusive(selection_end),
    })
    records = []
    for values in result.result_rows:
        row = dict(zip(result.column_names, values))
        balance = Decimal(str(row.get("balance_prev_month") or 0))
        total_turnover = Decimal(str(row.get("total_turnover") or 0))
        active_days = int(row.get("active_days") or 0)
        peak_daily_turnover = Decimal(str(row.get("peak_daily_turnover") or 0))
        leverage_p95_ratio = Decimal(str(row.get("leverage_p95_ratio") or 0))
        median_holding_seconds = Decimal(str(row.get("median_holding_seconds") or 0))
        if balance > 0:
            average_open_degree = float(total_turnover / Decimal(active_days) / balance) if active_days else 0.0
            peak_leverage_ratio = float(peak_daily_turnover / balance)
            leverage_p95 = float(leverage_p95_ratio)
            balance_status = "positive"
        else:
            average_open_degree = None
            peak_leverage_ratio = None
            leverage_p95 = None
            balance_status = "unknown_nonpositive_balance"
        records.append({
            "platform": str(row["platform"]),
            "login": int(row["login"]),
            "account_group": str(row.get("account_group") or ""),
            "balance_prev_month": float(balance),
            "average_open_degree": average_open_degree,
            "peak_leverage_ratio": peak_leverage_ratio,
            "leverage_p95_ratio": leverage_p95,
            "median_holding_seconds": float(median_holding_seconds),
            "balance_status": balance_status,
        })
    return {
        "selection_start": selection_start,
        "selection_end": selection_end,
        "platforms": selected,
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local Abook user risk snapshot")
    parser.add_argument("--selection-start", default="2026-05-01")
    parser.add_argument("--selection-end", default="2026-06-30")
    parser.add_argument("--platform", action="append", dest="platforms")
    args = parser.parse_args()
    load_env_file()
    platforms = args.platforms or sorted(ALLOWED_PLATFORMS)
    output = snapshot_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    payload = build_snapshot(args.selection_start, args.selection_end, platforms)
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    temporary.replace(output)
    print(json.dumps({"path": str(output), "records": len(payload["records"]), "test_demo_excluded_by_sql": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
