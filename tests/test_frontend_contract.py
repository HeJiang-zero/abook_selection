from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def _source(name: str) -> str:
    return (FRONTEND / "src" / name).read_text()


def test_vite_project_and_build_output_are_present():
    package = (FRONTEND / "package.json").read_text()
    index = (ROOT / "static" / "index.html").read_text()
    assert '"build": "vite build --outDir ../static"' in package
    assert '"vue"' in package
    assert '"echarts"' in package
    assert 'src="/assets/app.js"' in index
    assert 'href="/assets/styles.css"' in index
    assert (ROOT / "static" / "app.js").exists()
    assert (ROOT / "static" / "styles.css").exists()


def test_frontend_contains_filter_controls_and_all_phase_six_tabs():
    app = _source("App.vue")
    sidebar = (FRONTEND / "src" / "components" / "FilterSidebar.vue").read_text()
    assert "总览" in app
    assert "盈亏结构" not in app
    assert "用户结构" in app
    assert "风险敞口" in app
    assert "分流质量" in app
    assert "参数寻优" not in app
    assert "个人候选名单" in sidebar
    assert "马丁" in sidebar
    for rule in ["min_trades", "min_stability_score", "max_leverage_p95_ratio", "max_daily_profit_month_contribution", "min_avg_profit", "excluded_martingale_levels"]:
        assert rule in app or rule in sidebar


def test_frontend_uses_new_analysis_actions_and_book_lazy_load():
    api = _source("api.ts")
    app = _source("App.vue")
    assert "/api/abook/analysis" in api
    assert "/api/abook/sweep" not in api
    assert "/api/abook/export" in api
    assert "/api/abook/book-analytics" in api
    assert "loadBook" in app
    assert "MisjudgeAnalysis" in app
    assert "SelectionFunnel" in app
    assert "AccountsTable" in app
    assert "AccountDrawer" in app


def test_frontend_exposes_book_metrics_and_account_paging():
    books = (FRONTEND / "src" / "components" / "BookPerformance.vue").read_text()
    accounts = (FRONTEND / "src" / "components" / "AccountsTable.vue").read_text()
    assert "Core + observation" not in books
    for metric in ["max_drawdown", "symbol_heatmap", "company_profit_comparison", "monthly", "distribution", "style_breakdown", "top_accounts"]:
        assert metric in books
    assert "daily_turnover" not in books
    assert "Turnover" not in books
    for control in ["sortBy", "pageSize", "page"]:
        assert control in accounts


def test_user_structure_has_independent_cumulative_and_daily_pnl_charts():
    books = _source("components/BookPerformance.vue")
    assert "cumulativeChart" in books
    assert "dailyChart" in books
    assert "Abook 累计客户 P&L" in books
    assert "Bbook 累计客户 P&L" in books
    assert "Abook 每日客户 P&L" in books
    assert "Bbook 每日客户 P&L" in books
    assert "yAxis: [" in books
    assert "yAxisIndex: 1" in books
    assert books.count("yAxis: [") >= 2
    assert "Abook 每日客户 P&L" in books and "Bbook 每日客户 P&L" in books
    assert "daily_series" in books


def test_frontend_has_martingale_drawer_and_responsive_sidebar_contract():
    drawer = (FRONTEND / "src" / "components" / "AccountDrawer.vue").read_text()
    css = (FRONTEND / "src" / "style.css").read_text()
    assert "layer1" in drawer and "layer5" in drawer
    assert "martingale_risk_level" in drawer
    assert "max-height: calc(100vh - 36px)" in css
    assert "overflow-y: auto" in css


def test_frontend_exposes_refresh_all_data_button_and_request_contract():
    sidebar = (ROOT / "frontend/src/components/FilterSidebar.vue").read_text()
    api = (ROOT / "frontend/src/api.ts").read_text()
    app = (ROOT / "frontend/src/App.vue").read_text()

    assert "刷新全部数据" in sidebar
    assert "refreshSnapshots" in api
    assert "refresh-snapshots" in api
    assert "refreshing" in app
    assert "bookData.value = null" in app
