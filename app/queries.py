from __future__ import annotations

from datetime import date, timedelta
from typing import Any


ALLOWED_PLATFORMS = {"mt5", "hh_mt5"}


def _date_end_exclusive(end: str) -> str:
    return (date.fromisoformat(end) + timedelta(days=1)).isoformat()


def build_analysis_query(
    *,
    platforms: list[str],
    start: str,
    end: str,
    lookback_months: int,
    filters: dict[str, Any] | None = None,
    selection_start: str | None = None,
    selection_end: str | None = None,
    validation_start: str | None = None,
    validation_end: str | None = None,
    excluded_logins: set[tuple[str, int]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build one monthly fact query covering both selection and validation windows."""
    clean_platforms = [platform for platform in platforms if platform in ALLOWED_PLATFORMS]
    if not clean_platforms:
        clean_platforms = sorted(ALLOWED_PLATFORMS)
    if lookback_months not in (1, 2, 3):
        raise ValueError("lookback_months must be 1, 2, or 3")

    filters = filters or {}
    params: dict[str, Any] = {
        "platforms": clean_platforms,
        "start": start,
        "end_exclusive": _date_end_exclusive(end),
        "lookback_months": lookback_months,
        "selection_start": selection_start or start,
        "selection_end_exclusive": _date_end_exclusive(selection_end or end),
        "validation_start": validation_start or start,
        "validation_end_exclusive": _date_end_exclusive(validation_end or end),
    }
    user_conditions = ["is_deleted = 0", "has({platforms:Array(String)}, platform)"]
    user_conditions.append("positionCaseInsensitive(`group`, 'test') = 0")
    user_conditions.append("positionCaseInsensitive(`group`, 'demo') = 0")
    values = filters.get("groups") or []
    if values:
        params["group_0"] = values
        user_conditions.append("has({group_0:Array(String)}, `group`)")
    if filters.get("logins"):
        login_values = sorted({int(login) for login in filters["logins"]})
        if len(login_values) <= 2000:
            params["login_0"] = login_values
            user_conditions.append("has({login_0:Array(UInt64)}, login)")
        else:
            # clickhouse_connect puts query parameters in the HTTP URL. A large
            # allowed-login array causes HTTP 414, so embed only validated ints
            # in the query text; the list originates from the local snapshot.
            user_conditions.append(f"login IN ({','.join(str(login) for login in login_values)})")
    if excluded_logins:
        by_platform: dict[str, list[int]] = {}
        for platform, login in sorted(excluded_logins):
            by_platform.setdefault(str(platform), []).append(int(login))
        excluded_predicates = [
            f"(platform = '{platform}' AND login IN ({','.join(str(login) for login in sorted(logins))}))"
            for platform, logins in sorted(by_platform.items())
        ]
        user_conditions.append("NOT (" + " OR ".join(excluded_predicates) + ")")

    user_where = " AND ".join(user_conditions)
    query = f"""
WITH users AS (
    SELECT
        platform,
        login,
        any(`group`) AS account_group
    FROM risk.ods_mt5_users FINAL
    WHERE {user_where}
    GROUP BY platform, login
), months AS (
    SELECT addMonths(toStartOfMonth(toDate({{start:Date}})), number) AS month_start
    FROM numbers(36)
    WHERE number <= dateDiff(
        'month',
        toStartOfMonth(toDate({{start:Date}})),
        toStartOfMonth(toDate({{end_exclusive:Date}}) - toIntervalDay(1))
    )
), matched AS (
    SELECT
        platform,
        login,
        toStartOfMonth(exit_time) AS month_start,
        count() AS matched_trades,
        countIf(profit > 0) AS winning_trades,
        countIf(profit < 0) AS losing_trades,
        sum(volume) AS matched_volume,
        sum(profit) AS market_pnl,
        sumIf(profit, profit > 0) AS gross_wins,
        sumIf(profit, profit < 0) AS gross_losses,
        sum(turnover) AS turnover,
        avg(holding_seconds) AS avg_holding_seconds,
        quantileTDigest(0.5)(toFloat64(holding_seconds)) AS median_holding_seconds,
        countIf(direction = 'Long') AS long_trades,
        countIf(direction = 'Short') AS short_trades,
        uniqExact(symbol) AS symbols_traded
    FROM risk.dwd_matched_trades AS mt FINAL
    INNER JOIN users AS u
        ON mt.platform = u.platform AND mt.login = u.login
    WHERE mt.platform IN {{platforms:Array(String)}}
      AND mt.exit_time >= {{start:Date}}
      AND mt.exit_time < {{end_exclusive:Date}}
    GROUP BY platform, login, month_start
), deal_daily AS (
    SELECT
        platform,
        login,
        toDate(time) AS trade_date,
        toStartOfMonth(time) AS month_start,
        countIf(action IN (0, 1)) AS trade_rows,
        sumIf(profit, action IN (0, 1)) AS daily_deal_market_pnl,
        sumIf(profit, action IN (0, 1) AND profit > 0) AS daily_gross_wins,
        sumIf(profit, action IN (0, 1) AND profit < 0) AS daily_gross_losses,
        sumIf(storage + commission + fee, action IN (0, 1)) AS daily_costs,
        sumIf(profit + storage + commission + fee, action IN (0, 1)) AS daily_client_net_pnl,
        sumIf(profit, action IN (2, 3)) AS daily_funding_pnl
    FROM risk.ods_mt5_deals AS d FINAL
    INNER JOIN users AS u
        ON d.platform = u.platform AND d.login = u.login
    WHERE d.is_deleted = 0
      AND d.platform IN {{platforms:Array(String)}}
      AND d.time >= {{start:Date}}
      AND d.time < {{end_exclusive:Date}}
    GROUP BY platform, login, trade_date, month_start
), deal_costs AS (
    SELECT
        platform,
        login,
        month_start,
        sum(daily_deal_market_pnl) AS deal_market_pnl,
        sum(daily_gross_wins) AS gross_wins,
        sum(daily_gross_losses) AS gross_losses,
        sum(daily_costs) AS costs,
        sum(daily_client_net_pnl) AS client_net_pnl,
        sum(daily_funding_pnl) AS funding_pnl,
        countIf(trade_rows > 0) AS active_trade_days,
        sum(daily_client_net_pnl) AS daily_profit_sum,
        countIf(trade_rows > 0 AND daily_client_net_pnl > 0) AS positive_profit_days,
        countIf(trade_rows > 0 AND daily_client_net_pnl < 0) AS negative_profit_days,
        countIf(trade_rows > 0 AND daily_client_net_pnl = 0) AS flat_profit_days
    FROM deal_daily
    GROUP BY platform, login, month_start
), account_daily AS (
    SELECT
        platform,
        login,
        month_start,
        countIf(trade_rows > 0) AS daily_active_days,
        countIf(trade_rows > 0 AND daily_client_net_pnl > 0) AS daily_positive_days,
        countIf(trade_rows > 0 AND daily_client_net_pnl < 0) AS daily_negative_days,
        countIf(trade_rows > 0 AND daily_client_net_pnl = 0) AS daily_flat_days,
        sumIf(daily_client_net_pnl, trade_rows > 0 AND daily_client_net_pnl > 0) AS daily_positive_sum,
        sumIf(daily_client_net_pnl, trade_rows > 0 AND daily_client_net_pnl < 0) AS daily_negative_sum,
        maxIf(daily_client_net_pnl, trade_rows > 0 AND daily_client_net_pnl > 0) AS max_positive_day,
        minIf(daily_client_net_pnl, trade_rows > 0 AND daily_client_net_pnl < 0) AS min_negative_day,
        sumIf(toFloat64(daily_client_net_pnl), trade_rows > 0) AS daily_pnl_sum_for_variance,
        sumIf(toFloat64(daily_client_net_pnl) * toFloat64(daily_client_net_pnl), trade_rows > 0) AS daily_pnl_square_sum,
        countIf(trade_rows > 0) AS daily_variance_count,
        sumIf(abs(daily_client_net_pnl), trade_rows > 0) AS daily_abs_sum
    FROM deal_daily
    GROUP BY platform, login, month_start
), account_months AS (
    SELECT
        u.platform,
        u.login,
        u.account_group,
        m.month_start
    FROM users AS u
    CROSS JOIN months AS m
), population AS (
    SELECT
        uniqExact(tuple(platform, login)) AS unique_account_count,
        count() AS account_row_count
    FROM users
), period_matched_stats AS (
    SELECT
        mt.platform,
        mt.login,
        quantileTDigestIf(0.5)(toFloat64(mt.holding_seconds), mt.exit_time >= {{selection_start:Date}} AND mt.exit_time < {{selection_end_exclusive:Date}}) AS selection_median_holding_seconds,
        quantileTDigestIf(0.5)(toFloat64(mt.holding_seconds), mt.exit_time >= {{validation_start:Date}} AND mt.exit_time < {{validation_end_exclusive:Date}}) AS validation_median_holding_seconds,
        uniqExactIf(mt.symbol, mt.exit_time >= {{selection_start:Date}} AND mt.exit_time < {{selection_end_exclusive:Date}}) AS selection_symbols_traded,
        uniqExactIf(mt.symbol, mt.exit_time >= {{validation_start:Date}} AND mt.exit_time < {{validation_end_exclusive:Date}}) AS validation_symbols_traded
    FROM risk.dwd_matched_trades AS mt FINAL
    INNER JOIN users AS u
        ON mt.platform = u.platform AND mt.login = u.login
    WHERE mt.platform IN {{platforms:Array(String)}}
      AND mt.exit_time >= {{start:Date}}
      AND mt.exit_time < {{end_exclusive:Date}}
    GROUP BY mt.platform, mt.login
), trade_source_coverage AS (
    SELECT
        min(exit_time) AS source_matched_min,
        max(exit_time) AS source_matched_max
    FROM risk.dwd_matched_trades AS mt FINAL
    INNER JOIN users AS u
        ON mt.platform = u.platform AND mt.login = u.login
    WHERE mt.platform IN {{platforms:Array(String)}}
), deal_source_coverage AS (
    SELECT
        min(d.time) AS source_deal_raw_min,
        max(d.time) AS source_deal_raw_max,
        minIf(d.time, d.is_deleted = 0) AS source_deal_min,
        maxIf(d.time, d.is_deleted = 0) AS source_deal_max,
        countIf(d.is_deleted = 1) AS source_deal_deleted_rows
    FROM risk.ods_mt5_deals AS d FINAL
    INNER JOIN users AS u
        ON d.platform = u.platform AND d.login = u.login
    WHERE d.platform IN {{platforms:Array(String)}}
)
SELECT
    k.platform AS platform,
    k.login AS login,
    k.account_group AS account_group,
    k.month_start AS month_start,
    p.unique_account_count AS population_unique_accounts,
    p.account_row_count AS population_account_rows,
    ts.source_matched_min AS source_matched_min,
    ts.source_matched_max AS source_matched_max,
    ds.source_deal_raw_min AS source_deal_raw_min,
    ds.source_deal_raw_max AS source_deal_raw_max,
    ds.source_deal_min AS source_deal_min,
    ds.source_deal_max AS source_deal_max,
    ds.source_deal_deleted_rows AS source_deal_deleted_rows,
    coalesce(m.matched_trades, 0) AS matched_trades,
    coalesce(m.winning_trades, 0) AS winning_trades,
    coalesce(m.losing_trades, 0) AS losing_trades,
    coalesce(m.matched_volume, 0) AS matched_volume,
    coalesce(m.market_pnl, 0) AS matched_market_pnl,
    coalesce(d.deal_market_pnl, 0) AS market_pnl,
    coalesce(d.gross_wins, 0) AS gross_wins,
    coalesce(d.gross_losses, 0) AS gross_losses,
    coalesce(d.deal_market_pnl, 0) AS deal_market_pnl,
    coalesce(d.costs, 0) AS costs,
    coalesce(d.client_net_pnl, 0) AS client_net_pnl,
    coalesce(d.funding_pnl, 0) AS funding_pnl,
    coalesce(d.active_trade_days, 0) AS active_trade_days,
    coalesce(d.daily_profit_sum, 0) AS daily_profit_sum,
    coalesce(d.positive_profit_days, 0) AS positive_profit_days,
    coalesce(d.negative_profit_days, 0) AS negative_profit_days,
    coalesce(d.flat_profit_days, 0) AS flat_profit_days,
    coalesce(a.daily_active_days, 0) AS daily_active_days,
    coalesce(a.daily_positive_days, 0) AS daily_positive_days,
    coalesce(a.daily_negative_days, 0) AS daily_negative_days,
    coalesce(a.daily_flat_days, 0) AS daily_flat_days,
    coalesce(a.daily_positive_sum, 0) AS daily_positive_sum,
    coalesce(a.daily_negative_sum, 0) AS daily_negative_sum,
    coalesce(a.max_positive_day, 0) AS max_positive_day,
    coalesce(a.min_negative_day, 0) AS min_negative_day,
    coalesce(a.daily_pnl_sum_for_variance, 0) AS daily_pnl_sum_for_variance,
    coalesce(a.daily_pnl_square_sum, 0) AS daily_pnl_square_sum,
    coalesce(a.daily_variance_count, 0) AS daily_variance_count,
    coalesce(a.daily_abs_sum, 0) AS daily_abs_sum,
    coalesce(m.turnover, 0) AS turnover,
    coalesce(m.avg_holding_seconds, 0) AS avg_holding_seconds,
    coalesce(m.median_holding_seconds, 0) AS median_holding_seconds,
    coalesce(m.long_trades, 0) AS long_trades,
    coalesce(m.short_trades, 0) AS short_trades,
    coalesce(m.symbols_traded, 0) AS symbols_traded,
    if(isNaN(period_stats.selection_median_holding_seconds), 0, coalesce(period_stats.selection_median_holding_seconds, 0)) AS selection_median_holding_seconds,
    if(isNaN(period_stats.validation_median_holding_seconds), 0, coalesce(period_stats.validation_median_holding_seconds, 0)) AS validation_median_holding_seconds,
    coalesce(period_stats.selection_symbols_traded, 0) AS selection_symbols_traded,
    coalesce(period_stats.validation_symbols_traded, 0) AS validation_symbols_traded
FROM account_months AS k
CROSS JOIN population AS p
CROSS JOIN trade_source_coverage AS ts
CROSS JOIN deal_source_coverage AS ds
LEFT JOIN matched AS m
    ON k.platform = m.platform AND k.login = m.login AND k.month_start = m.month_start
LEFT JOIN deal_costs AS d
    ON k.platform = d.platform AND k.login = d.login AND k.month_start = d.month_start
LEFT JOIN account_daily AS a
    ON k.platform = a.platform AND k.login = a.login AND k.month_start = a.month_start
LEFT JOIN period_matched_stats AS period_stats
    ON k.platform = period_stats.platform AND k.login = period_stats.login
ORDER BY k.platform, k.login, k.month_start
"""
    return query, params


def build_account_detail_query(platform: str, login: int, start: str, end: str) -> tuple[str, dict[str, Any]]:
    """Return trade-level detail for one account."""
    if platform not in ALLOWED_PLATFORMS:
        raise ValueError("unsupported platform")
    query = """
    SELECT
        platform, login, symbol, direction, entry_time, exit_time,
        entry_price, exit_price, volume, profit, holding_seconds,
        turnover, entry_deal_id, exit_deal_id
    FROM risk.dwd_matched_trades AS m FINAL
    INNER JOIN risk.ods_mt5_users AS u FINAL
      ON m.platform = u.platform AND m.login = u.login
    WHERE u.is_deleted = 0
      AND positionCaseInsensitive(u.`group`, 'test') = 0
      AND positionCaseInsensitive(u.`group`, 'demo') = 0
      AND m.platform = {platform:String}
      AND m.login = {login:UInt64}
      AND m.exit_time >= {start:Date}
      AND m.exit_time < {end_exclusive:Date}
    ORDER BY exit_time DESC
    LIMIT 5000
    """
    return query, {
        "platform": platform,
        "login": login,
        "start": start,
        "end_exclusive": _date_end_exclusive(end),
    }
