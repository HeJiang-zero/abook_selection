# A-Book 用户筛选与 7 月验证面板

FastAPI 后端 + Vue 3/ECharts 前端，用于使用 5–6 月数据筛选用户，并用 7 月数据独立验证筛选效果。

## 运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export CLICKHOUSE_HOST=data-collect-alb-110459182.ap-southeast-2.elb.amazonaws.com
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_DATABASE=risk
export CLICKHOUSE_USER=default
export CLICKHOUSE_PASSWORD="$(sed -n 's/^ck\\.write\\.password=//p' clickhouse.md)"
export CLICKHOUSE_SECURE=0
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

打开 http://localhost:8000。生产环境请使用只读 ClickHouse 账号，并通过密钥管理注入 `CLICKHOUSE_PASSWORD`。

默认筛选规则为：Abook 候选满足交易笔数 `>= 20`、活跃交易天数 `>= 5`、胜率 `>= 50%`、`Profit Factor > 1`、盈亏比 `>= 1`、平均交易日净利润 `> 10 USD`、5–6 月月度持续性 `>= 50%`、单日利润/风险集中度 `<= 50%`；Bbook 候选使用对应的亏损方向条件。平均交易日利润定义为：阶段内用户净交易 P&L（`profit + storage + commission + fee`，仅 `action IN (0,1)`）除以有交易的自然日数量。账户没有亏损交易时，PF 在筛选上视为无穷大，API 中以 `null` 表示，避免 JSON 非法数值。

账户组中不区分大小写包含 `test` 或 `demo` 的账户是测试账号，所有查询、服务层聚合和账户详情都会硬性排除，即使请求传入 `exclude_test_accounts=false` 也不会放行。7 月验证阶段会保留没有交易的筛选账户，并标记为“无交易”。

## API

- `GET /api/health`
- `GET /api/abook/filters`
- `POST /api/abook/analysis`
- `GET /api/abook/accounts/{platform}/{login}`

分析请求使用显式阶段窗口：

```json
{
  "selection": {"start": "2026-05-01", "end": "2026-06-30"},
  "validation": {"start": "2026-07-01", "end": "2026-07-13"},
  "rules": {
    "min_trades": 20,
    "min_active_days": 5,
    "min_profit_factor": 1,
    "min_avg_daily_profit": 10,
    "neutral_band_usd": 10,
    "min_positive_month_rate": 1.0,
    "max_top_day_concentration": 0.5,
    "min_direction_day_rate_lower_bound": 0.55,
    "min_stability_score": 70
  },
  "exclude_test_accounts": true
}
```

所有分析查询均使用 `FINAL`，并过滤 `is_deleted = 0`。查询会为用户生成完整的月份网格，因此验证期没有交易的账户仍会返回。交易 P&L 只计算 `action IN (0,1)`；`action IN (2,3)` 的资金/信用流水单独返回。页面中的统一 `market_pnl`、毛盈亏和 PF 均以 Deals 聚合口径为准；撮合表的 `matched_market_pnl` 仅作为对账字段保留。理论镜像收益与客户净交易 P&L 分开返回。

当前 Abook 利润影响是理论估算：假设进入 Abook 后交易所的对手盘利润为 0，因此迁移增量为用户净交易 P&L；不包含真实外部成交、点差、对冲成本、滑点和流动性成本。

页面顶部的 Abook / Bbook 盈亏分析按 Core 候选组分别展示筛选期和验证期的账户数、盈利/亏损/中性账户、毛盈利、毛亏损、净 P&L、当前 Bbook 利润和假设 Abook 利润；理论增量只展示 7 月样本外验证期。Abook 理论增量定义为：`假设 Abook 利润 - 当前 Bbook 利润`；在当前没有外部 Abook 成交数据时，假设 Abook 利润为 0，因此它不是实际可实现利润。

这里的 `Profit Factor` 不是单笔交易的传统盈亏比：PF = 阶段总盈利 ÷ 阶段总亏损绝对值；页面的“盈亏比”是 `Payoff Ratio = 平均盈利交易 ÷ 平均亏损交易绝对值`。胜率、Payoff Ratio 和 PF 必须结合使用，单独提高胜率可能得到小赚大亏的策略。当前没有完整的保证金、止损距离或最大持仓风险字段，因此“单日利润/风险集中度”只是仓位管理的风险代理，不等同于账户真实风险率。

## 稳定性与反过拟合指标

筛选期候选会额外返回稳定性评分和风险标记。评分只使用筛选期，不读取 7 月：

- 月度持续性：盈利月份占比、最差月份 P&L、月度波动。
- 日度可信度：盈利/亏损天数、Wilson 95% 区间、日收益标准差。
- 收益质量：单笔期望、平均盈利、平均亏损、Payoff Ratio、收益/最大回撤。
- 集中度风险：Top 1 日正/负收益占阶段收益的比例。
- 样本等级：根据交易笔数、活跃交易天数和活跃月份分为高、中、低置信度。

`Core` 表示稳定性指标和样本门槛通过，`Watch` 表示方向成立但仍有样本、集中度或日度置信度风险；两者都必须使用 7 月样本外结果复核，不能把 Core 当作未来盈利保证。当前有效交易和撮合数据从 2026-05-15 开始，5 月会显示为部分月份；原始 Deals 表中更早记录如果标记为 `is_deleted=1`，只作为原始覆盖审计，不纳入 P&L。

## 测试

```bash
.venv/bin/python -m pytest -q
```
real\FPlive\TEST_USD_ZO_BA_NT_H 或 demo\HHdemo\forexhh-USD，像这种 group 里面含有 test/demo 的，我们要过滤掉，是测试账号。
