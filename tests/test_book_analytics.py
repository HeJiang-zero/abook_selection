from app.book_analytics import build_book_analytics, calculate_hedge_sensitivity, split_books
from app.service import prepare_analysis_context


def _account(login: int, book: str, validation_pnl: float, turnover: float):
    return {
        "platform": "mt5", "login": login, "account_group": "real", "book": book,
        "selection": {"client_net_pnl": 100, "trade_count": 10, "active_trade_days": 2, "turnover": turnover,
                       "avg_holding_seconds": 60, "median_holding_seconds": 60, "profit_factor": 1.5,
                       "winning_trades": 7, "losing_trades": 3},
        "validation": {"client_net_pnl": validation_pnl, "trade_count": 5, "active_trade_days": 1, "turnover": turnover / 2,
                        "avg_holding_seconds": 60, "median_holding_seconds": 60, "profit_factor": 1.5,
                        "winning_trades": 3, "losing_trades": 2},
        "validation_status": "profitable" if validation_pnl > 0 else "loss",
        "martingale_blocked": False, "martingale_risk_level": None,
        "stability": {"score": 80, "tier": "core"},
    }


def test_bbook_is_population_minus_abook():
    accounts = [_account(1, "abook", 20, 100000), _account(2, "bbook", -20, 50000), _account(3, "bbook", 0, 20000)]
    abook, bbook = split_books(accounts, {("mt5", 1)})

    assert {(row["platform"], row["login"]) for row in abook} == {("mt5", 1)}
    assert {(row["platform"], row["login"]) for row in bbook} == {("mt5", 2), ("mt5", 3)}


def test_hedge_cost_reduces_increment_and_reports_break_even_bps():
    result = calculate_hedge_sensitivity([{"validation": {"turnover": 100000}}], 100000, 1000, 2.0)

    assert result["hedge_cost"] == 20.0
    assert result["after_cost_increment"] == 980.0
    assert result["break_even_bps"] == 100.0


def test_book_analytics_returns_four_analysis_blocks():
    accounts = [_account(1, "abook", 20, 100000), _account(2, "bbook", -20, 50000)]
    context = prepare_analysis_context(
        [], selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
    )

    result = build_book_analytics(context, accounts, {("mt5", 1)}, 1.0, [])

    assert set(result) >= {"pnl_structure", "user_structure", "risk_exposure", "routing_quality"}
    assert result["risk_exposure"]["abook"]["hedge_cost_bps"] == 1.0


def test_book_analytics_includes_routing_risk_and_distribution_metrics():
    accounts = [
        _account(1, "abook", 20, 100000),
        _account(2, "bbook", -20, 50000),
    ]
    daily_rows = [
        {"platform": "mt5", "login": 1, "trade_date": "2026-07-01", "client_net_pnl": 10, "matched_trades": 2},
        {"platform": "mt5", "login": 1, "trade_date": "2026-07-02", "client_net_pnl": -30, "matched_trades": 2},
        {"platform": "mt5", "login": 2, "trade_date": "2026-07-01", "client_net_pnl": -5, "matched_trades": 1},
        {"platform": "mt5", "login": 2, "trade_date": "2026-07-02", "client_net_pnl": 2, "matched_trades": 1},
    ]
    turnover_rows = [
        {"platform": "mt5", "login": 1, "trade_date": "2026-07-01", "turnover": 100, "long_turnover": 60, "short_turnover": 40},
        {"platform": "mt5", "login": 2, "trade_date": "2026-07-01", "turnover": 80, "long_turnover": 30, "short_turnover": 50},
    ]
    symbol_rows = {
        "population": [{"platform": "mt5", "login": 1, "symbol": "EURUSD", "trade_count": 2, "volume": 3, "market_pnl": 5, "turnover": 100}],
        "abook": [{"platform": "mt5", "login": 1, "symbol": "EURUSD", "trade_count": 2, "volume": 3, "market_pnl": 5, "turnover": 100}],
    }
    context = prepare_analysis_context(
        [], daily_rows=daily_rows, overview_daily_rows=daily_rows,
        selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
    )

    result = build_book_analytics(
        context, accounts, {("mt5", 1)}, 1.0, symbol_rows, turnover_rows,
    )

    assert result["pnl_structure"]["abook"]["max_drawdown"] == 30.0
    assert "top_5" in result["pnl_structure"]["abook"]["profit_concentration"]
    assert result["user_structure"]["abook"]["symbol_heatmap"][0]["symbol"] == "EURUSD"
    assert result["risk_exposure"]["abook"]["daily_turnover"][0]["turnover"] == 100.0
    assert result["routing_quality"]["daily_hit_curves"]
    assert result["routing_quality"]["company_profit_comparison"]


def test_book_analytics_separates_customer_pnl_from_company_profit_sign():
    accounts = [
        _account(1, "abook", 20, 100000),
        _account(2, "bbook", -20, 50000),
    ]
    context = prepare_analysis_context(
        [], selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-13",
    )

    result = build_book_analytics(context, accounts, {("mt5", 1)}, 0.0, [])
    abook_validation = result["pnl_structure"]["abook"]["validation"]
    bbook_validation = result["pnl_structure"]["bbook"]["validation"]

    assert abook_validation["customer_net_pnl"] == 20.0
    assert abook_validation["company_profit_if_current_book"] == 0.0
    assert bbook_validation["customer_net_pnl"] == -20.0
    assert bbook_validation["company_profit_if_current_book"] == 20.0
