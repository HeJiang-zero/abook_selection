from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import clickhouse_connect

from app.config import get_settings, load_env_file


def _rows(result) -> list[dict]:
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def probe(client) -> dict:
    columns = _rows(client.query("DESCRIBE TABLE risk.dws_account_martingale_window"))
    window_types = _rows(client.query("""
        SELECT window_type, count() AS rows, min(window_start) AS min_window_start,
               max(window_end) AS max_window_end
        FROM risk.dws_account_martingale_window
        GROUP BY window_type
        ORDER BY window_type
    """))
    coverage = _rows(client.query("""
        SELECT min(window_start) AS min_window_start, max(window_end) AS max_window_end,
               count() AS rows
        FROM risk.dws_account_martingale_window
    """))
    escalation_bins = _rows(client.query("""
        SELECT
            multiIf(avg_volume_escalation < 1, '<1.0',
                    avg_volume_escalation < 1.1, '1.0-1.1',
                    avg_volume_escalation < 1.2, '1.1-1.2',
                    avg_volume_escalation < 1.3, '1.2-1.3',
                    avg_volume_escalation < 1.5, '1.3-1.5',
                    avg_volume_escalation < 1.8, '1.5-1.8', '>=1.8') AS bucket,
            count() AS rows
        FROM risk.dws_account_martingale_window
        GROUP BY bucket
        ORDER BY bucket
    """))
    return {
        "columns": columns,
        "window_types": window_types,
        "coverage": coverage[0] if coverage else {},
        "escalation_bins": escalation_bins,
        "escalation_unit": "multiplier",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the martingale window schema and value distributions")
    parser.add_argument("--output", type=Path, default=Path("docs/analysis/2026-07-16-martingale-schema.json"))
    args = parser.parse_args()
    load_env_file()
    settings = get_settings()
    if not settings.configured:
        raise RuntimeError("CLICKHOUSE_PASSWORD is not configured")
    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        secure=settings.clickhouse_secure,
    )
    result = probe(client)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "columns": len(result["columns"]), "window_types": result["window_types"]}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
