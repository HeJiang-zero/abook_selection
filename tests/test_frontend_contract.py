from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_exposes_two_stage_controls_and_validation_sections():
    html = (ROOT / "static" / "index.html").read_text()
    assert "筛选开始日期" in html
    assert "验证开始日期" in html
    assert "最低交易笔数" in html
    assert "状态迁移" in html
    assert "理论反向利润" in html
    assert "profit_overview" in html
    assert "visibleAccounts" in html
    assert "Abook / Bbook 盈亏分析" in html
    assert "book_performance" in html
    assert "Abook 7月验证理论增量" in html
    assert "筛选期理论增量" not in html
    assert "monthly_consistency_ratio" in html or "最低月度持续性" in html
    assert "待应用参数" in html
    assert "Top1 日利润贡献率" in html
    assert "最大峰值杠杆率" in html
    assert "高杠杆短持仓例外" in html
    for rule in [
        "min_active_days", "min_win_rate", "min_profit_factor", "min_payoff_ratio",
        "min_positive_month_rate", "min_direction_day_rate_lower_bound",
        "min_stability_score", "max_top1_day_profit_contribution",
        "max_peak_leverage_ratio", "max_high_leverage_holding_seconds",
    ]:
        assert f'v-model.number="request.rules.{rule}"' in html
    assert "max_top_day_concentration" not in html


def test_frontend_uses_two_stage_payload_fields():
    javascript = (ROOT / "static" / "app.js").read_text()
    assert "request.selection.start" in javascript
    assert "request.validation.end" in javascript
    assert "data.validation" in javascript
    assert "transitions" in javascript
    assert "active_positive_account_rate" in javascript
    assert "active_negative_account_rate" in javascript
    assert "theoretical_increment" in (ROOT / "static" / "index.html").read_text()
    assert "validation_incremental_change" in (ROOT / "static" / "index.html").read_text()
    assert "rulesDirty" in javascript
    assert "max_peak_leverage_ratio" in javascript
    assert "max_high_leverage_holding_seconds" in javascript


def test_frontend_exposes_stability_controls_and_interactive_account_table():
    html = (ROOT / "static" / "index.html").read_text()
    javascript = (ROOT / "static" / "app.js").read_text()
    assert "稳定 Abook" in html
    assert "置信等级" in html
    assert "accountSearch" in html
    assert "pageSize" in html
    assert "stability" in html
    assert "confidence_tier" in html
    assert "min_stability_score" in javascript
    assert "axisPointer: { type: 'cross' }" in javascript
    assert "filteredAccounts" in javascript


def test_filter_panel_keeps_apply_button_reachable_when_advanced_rules_are_open():
    css = (ROOT / "static" / "styles.css").read_text()
    assert "max-height: calc(100vh - 36px)" in css
    assert "overflow-y: auto" in css


def test_frontend_shows_applied_rule_confirmation():
    html = (ROOT / "static" / "index.html").read_text()
    javascript = (ROOT / "static" / "app.js").read_text()
    assert "已应用规则" in html
    assert "data.rules" in html
    assert "data.selection && data.profit_impact" in html
    assert "/assets/app.js?v=" in html
    assert "账户表现" in html
    assert "test / demo" in html
    assert "个人候选名单（加入 Abook）" in html
    assert "request.personal_candidate_list" in html
    assert "personal_candidate_list" in javascript
    assert "app.js?v=20260715-6" in html
