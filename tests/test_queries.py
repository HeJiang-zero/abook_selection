from app.queries import build_analysis_query


def test_analysis_query_has_final_and_delete_filter():
    query, params = build_analysis_query(
        platforms=["mt5", "hh_mt5"],
        start="2026-05-15",
        end="2026-07-13",
        lookback_months=3,
        filters={"groups": ["real\\FPlive"]},
    )

    assert "risk.ods_mt5_users FINAL" in query
    assert "FROM risk.dwd_matched_trades AS mt FINAL" in query
    assert "is_deleted = 0" in query
    assert params["group_0"] == ["real\\FPlive"]
    assert params["lookback_months"] == 3


def test_analysis_query_only_adds_group_and_login_filters():
    query, params = build_analysis_query(
        platforms=["mt5"],
        start="2026-05-15",
        end="2026-07-13",
        lookback_months=3,
        filters={"groups": ["real\\FPlive"], "logins": [123]},
    )

    assert "`group`" in query
    assert "has({login_0:Array(UInt64)}, login)" in query
    assert "country" not in query
    assert "leverage >=" not in query
    assert "balance >=" not in query
    assert params["group_0"] == ["real\\FPlive"]


def test_analysis_query_builds_full_months_and_excludes_test_accounts():
    query, params = build_analysis_query(
        platforms=["mt5"],
        start="2026-05-01",
        end="2026-07-13",
        lookback_months=3,
        filters={},
    )

    assert "positionCaseInsensitive(`group`, 'test') = 0" in query
    assert "positionCaseInsensitive(`group`, 'demo') = 0" in query
    assert "CROSS JOIN months" in query
    assert "positive_profit_days" in query
    assert "uniqExact(tuple(platform, login)) AS unique_account_count" in query
    assert "population_unique_accounts" in query
    assert "account_daily" in query
    assert "daily_positive_sum" in query
    assert "trade_source_coverage" in query
    assert "source_matched_min" in query
    assert params["start"] == "2026-05-01"


def test_analysis_query_always_excludes_test_accounts_even_when_override_is_false():
    query, _ = build_analysis_query(
        platforms=["mt5"], start="2026-05-01", end="2026-07-13", lookback_months=3,
        filters={}, exclude_test_accounts=False,
    )

    assert "positionCaseInsensitive(`group`, 'test') = 0" in query
    assert "positionCaseInsensitive(`group`, 'demo') = 0" in query


def test_analysis_query_exposes_raw_and_active_deal_coverage():
    query, _ = build_analysis_query(
        platforms=["mt5"], start="2026-05-01", end="2026-07-13", lookback_months=3,
        filters={},
    )

    assert "source_deal_raw_min" in query
    assert "source_deal_raw_max" in query
    assert "source_deal_deleted_rows" in query


def test_analysis_query_uses_tuple_population_and_canonical_deals_pnl():
    query, _ = build_analysis_query(
        platforms=["mt5", "hh_mt5"], start="2026-05-01", end="2026-07-13", lookback_months=3,
        filters={}, exclude_test_accounts=False,
    )

    assert "uniqExact(tuple(platform, login)) AS unique_account_count" in query
    assert "daily_pnl_square_sum" in query
    assert "daily_variance_count" in query
    assert "daily_gross_wins" in query
    assert "daily_gross_losses" in query
    assert query.count("INNER JOIN users") >= 2
    assert "coalesce(d.deal_market_pnl, 0) AS market_pnl" in query
    assert "positionCaseInsensitive(`group`, 'test') = 0" in query
    assert "positionCaseInsensitive(`group`, 'demo') = 0" in query


def test_account_detail_query_always_filters_demo_and_test_accounts():
    from app.queries import build_account_detail_query

    query, _ = build_account_detail_query("mt5", 123, "2026-05-01", "2026-07-13")

    assert "risk.ods_mt5_users AS u FINAL" in query
    assert "positionCaseInsensitive(u.`group`, 'test') = 0" in query
    assert "positionCaseInsensitive(u.`group`, 'demo') = 0" in query
