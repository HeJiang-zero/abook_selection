from __future__ import annotations

from typing import Any

import clickhouse_connect

from .config import Settings, get_settings
from .models import AnalysisRequest
from .queries import (
    build_account_detail_query,
    build_analysis_query,
    build_book_symbol_query,
    build_daily_pnl_query,
)


class RepositoryConfigurationError(RuntimeError):
    pass


class ClickHouseRepository:
    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        if client is not None:
            self.client = client
            return
        if not self.settings.configured:
            self.client = None
            return
        self.client = clickhouse_connect.get_client(
            host=self.settings.clickhouse_host,
            port=self.settings.clickhouse_port,
            username=self.settings.clickhouse_user,
            password=self.settings.clickhouse_password,
            database=self.settings.clickhouse_database,
            secure=self.settings.clickhouse_secure,
            compress=self.settings.clickhouse_compress,
            apply_server_timezone=self.settings.clickhouse_use_server_time_zone_for_dates,
        )

    def _rows(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if self.client is None:
            raise RepositoryConfigurationError("CLICKHOUSE_PASSWORD is not configured")
        result = self.client.query(query, parameters=params)
        return [dict(zip(result.column_names, row)) for row in result.result_rows]

    def fetch_analysis(
        self,
        request: AnalysisRequest,
        excluded_logins: set[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        if request.lookback_months is not None:
            start = request.start or request.selection.start
            end = request.end or request.validation.end
            lookback_months = request.lookback_months
        else:
            start = min(request.selection.start, request.validation.start)
            end = max(request.selection.end, request.validation.end)
            lookback_months = 3
        query, params = build_analysis_query(
            platforms=request.platforms,
            start=start.isoformat(),
            end=end.isoformat(),
            lookback_months=lookback_months,
            filters=request.filters.model_dump(),
            excluded_logins=excluded_logins,
            selection_start=request.selection.start.isoformat(),
            selection_end=request.selection.end.isoformat(),
            validation_start=request.validation.start.isoformat(),
            validation_end=request.validation.end.isoformat(),
        )
        return self._rows(query, params)

    def fetch_daily_pnl(
        self,
        request: AnalysisRequest,
        excluded_logins: set[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        start = min(request.selection.start, request.validation.start)
        end = max(request.selection.end, request.validation.end)
        query, params = build_daily_pnl_query(
            platforms=request.platforms,
            start=start.isoformat(),
            end=end.isoformat(),
            filters=request.filters.model_dump(),
            excluded_logins=excluded_logins,
        )
        return self._rows(query, params)

    def fetch_account_detail(self, platform: str, login: int, start: str, end: str) -> list[dict[str, Any]]:
        query, params = build_account_detail_query(platform, login, start, end)
        return self._rows(query, params)

    def fetch_book_symbol_rows(self, request: AnalysisRequest, account_keys: set[tuple[str, int]] | None = None) -> list[dict[str, Any]]:
        start = min(request.selection.start, request.validation.start)
        end = max(request.selection.end, request.validation.end)
        query, params = build_book_symbol_query(
            platforms=request.platforms, start=start.isoformat(), end=end.isoformat(), account_keys=account_keys
        )
        return self._rows(query, params)

    def fetch_filter_options(self) -> dict[str, list[str]]:
        if self.client is None:
            raise RepositoryConfigurationError("CLICKHOUSE_PASSWORD is not configured")
        result = self.client.query(
            """
            SELECT platform, `group`
            FROM risk.ods_mt5_users FINAL
            WHERE is_deleted = 0
              AND positionCaseInsensitive(`group`, 'test') = 0
              AND positionCaseInsensitive(`group`, 'demo') = 0
              AND platform IN ('mt4', 'mt5', 'hh_mt5')
            GROUP BY platform, `group`
            ORDER BY platform, `group`
            """
        )
        rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
        return {
            "platforms": sorted({row["platform"] for row in rows}),
            "groups": sorted({row["group"] for row in rows if row["group"]}),
        }
