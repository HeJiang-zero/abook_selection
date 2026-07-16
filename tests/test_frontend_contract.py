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
    assert (ROOT / "static" / "assets" / "app.js").exists()
    assert (ROOT / "static" / "assets" / "styles.css").exists()


def test_frontend_contains_filter_controls_and_all_phase_six_tabs():
    app = _source("App.vue")
    sidebar = (FRONTEND / "src" / "components" / "FilterSidebar.vue").read_text()
    assert "总览" in app
    assert "盈亏结构" in app
    assert "用户结构" in app
    assert "风险敞口" in app
    assert "分流质量" in app
    assert "参数寻优" in app
    assert "个人候选名单" in sidebar
    assert "马丁" in sidebar
    for rule in ["min_trades", "min_stability_score", "max_peak_leverage_ratio", "excluded_martingale_levels"]:
        assert rule in app or rule in sidebar


def test_frontend_uses_new_analysis_actions_and_book_lazy_load():
    api = _source("api.ts")
    app = _source("App.vue")
    assert "/api/abook/analysis" in api
    assert "/api/abook/sweep" in api
    assert "/api/abook/export" in api
    assert "/api/abook/book-analytics" in api
    assert "loadBook" in app
    assert "MisjudgeAnalysis" in app
    assert "SelectionFunnel" in app
    assert "AccountsTable" in app
    assert "AccountDrawer" in app


def test_frontend_has_martingale_drawer_and_responsive_sidebar_contract():
    drawer = (FRONTEND / "src" / "components" / "AccountDrawer.vue").read_text()
    css = (FRONTEND / "src" / "style.css").read_text()
    assert "layer1" in drawer and "layer5" in drawer
    assert "martingale_risk_level" in drawer
    assert "max-height: calc(100vh - 36px)" in css
    assert "overflow-y: auto" in css
