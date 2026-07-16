# A-Book 用户筛选与 7 月验证面板

FastAPI 后端 + Vue 3/ECharts 前端，用于使用 5–6 月数据筛选用户，并用 7 月数据独立验证筛选效果。

## 运行

### Phase 0–6 升级功能

马丁快照探查和构建：

```bash
.venv/bin/python scripts/probe_martingale_schema.py
.venv/bin/python scripts/build_martingale_snapshot.py --selection-start 2026-05-01 --selection-end 2026-06-30
```

前端构建：

```bash
cd frontend
pnpm install --ignore-scripts
pnpm run build
cd ..
./run_dashboard.sh
```

构建产物输出到 `static/`，FastAPI 通过 `/assets` 托管。页面包含马丁状态与五层明细、误判成本、筛选漏斗、Book 分析、参数寻优和 Abook CSV 导出。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd /Users/jianghe/abook_hedging && ./run_dashboard.sh
```

首次运行前，把本地 ClickHouse 配置写入被 Git 忽略的 `.env`（可参考 `.env.example`）。脚本会自动加载 `.env` 并启动服务。
打开 http://localhost:8000。生产环境请使用只读 ClickHouse 账号，并通过密钥管理注入 `CLICKHOUSE_PASSWORD`。

默认筛选规则为：Abook 候选满足交易笔数 `>= 20`、活跃交易天数 `>= 10`、胜率 `>= 50%`、`Profit Factor > 1`、盈亏比 `>= 0.8`、平均交易日净利润 `> 0 USD`、盈利月份占比 `>= 50%`、日盈利率 95% 下限 `>= 55%`、稳定性评分 `>= 70`、Top1 日利润贡献率 `< 20%`、峰值杠杆率 `<= 200`。月度持续性参数保留为可选增强条件，默认不额外收紧筛选。峰值杠杆超过 200 时，仅筛选期中位持仓不超过 300 秒的用户保留为短持仓例外；Bbook 候选使用对应的亏损方向条件。平均交易日利润定义为：阶段内用户净交易 P&L（`profit + storage + commission + fee`，仅 `action IN (0,1)`）除以有交易的自然日数量。账户没有亏损交易时，PF 在筛选上视为无穷大，API 中以 `null` 表示，避免 JSON 非法数值。

账户组中不区分大小写包含 `test` 或 `demo` 的账户是测试账号，所有查询、服务层聚合和账户详情都会硬性排除。7 月验证阶段会保留没有交易的筛选账户，并标记为“无交易”。

左侧“个人候选名单（加入 Abook）”默认关闭；开启后读取 `ABOOK_PERSONAL_CANDIDATE_LIST_PATH` 指定的 CSV，未设置时使用本机的个人候选名单路径。名单只作为 Abook 强制加入名单，仍受平台、账户组和 test/demo 边界约束，并按 `(platform, login)` 去重。

## API

- `GET /api/health`
- `GET /api/abook/filters`
- `POST /api/abook/analysis`
- `POST /api/abook/sweep`
- `GET /api/abook/export` / `POST /api/abook/export`
- `POST /api/abook/book-analytics`
- `GET /api/abook/accounts/{platform}/{login}`

分析请求使用显式阶段窗口：

```json
{
  "selection": {"start": "2026-05-01", "end": "2026-06-30"},
  "validation": {"start": "2026-07-01", "end": "2026-07-13"},
  "rules": {
    "min_trades": 20,
    "min_active_days": 10,
    "min_win_rate": 0.5,
    "min_profit_factor": 1,
    "min_payoff_ratio": 0.8,
    "min_avg_daily_profit": 0,
    "min_positive_month_rate": 0.5,
    "max_top1_day_profit_contribution": 0.2,
    "max_peak_leverage_ratio": 200,
    "max_high_leverage_holding_seconds": 300,
    "min_direction_day_rate_lower_bound": 0.55,
    "min_stability_score": 70
  }
}
```

所有分析查询均使用 `FINAL`，并过滤 `is_deleted = 0`。查询会为用户生成完整的月份网格，因此验证期没有交易的账户仍会返回。交易 P&L 只计算 `action IN (0,1)`；`action IN (2,3)` 的资金/信用流水单独返回。页面中的统一 `market_pnl`、毛盈亏和 PF 均以 Deals 聚合口径为准；撮合表的 `matched_market_pnl` 仅作为对账字段保留。理论镜像收益与客户净交易 P&L 分开返回。

当前 Abook 利润影响是理论估算：假设进入 Abook 后交易所的对手盘利润为 0，因此迁移增量为用户净交易 P&L；不包含真实外部成交、点差、对冲成本、滑点和流动性成本。

页面的符号口径固定为：customer_net_pnl 是客户净交易 P&L，不代表公司利润；留在 Bbook 时公司利润为客户净交易 P&L 取负；Abook 用户的正负只用于命中、误判和样本外验证，Abook 实际公司利润在没有外部成交数据时显示为理论 0。Abook 候选的“公司增量”是把该用户从 Bbook 移到 Abook 的理论变化，验证期还可以再扣除对冲成本。Bbook “漏网”只统计被判为 bbook_candidate 但验证期转正的用户，不把 observation 控制组混入误判金额。

volume 沿用 dwd_matched_trades.volume 原始单位；不同品种可能有不同交易量精度（例如外汇数据可出现 1000），不能直接当作统一“手数”。turnover 是交易名义金额风险代理，也不是公司利润，页面单独标注。

## 本地风险快照

杠杆筛选不在每次页面请求中重新聚合。使用以下命令按筛选期生成本地快照：

```bash
.venv/bin/python scripts/build_user_risk_snapshot.py --selection-start 2026-05-01 --selection-end 2026-06-30
```

快照默认写入 `data/user_risk_snapshot.json`，也可用 `ABOOK_RISK_SNAPSHOT_PATH` 覆盖路径。快照使用 matched trades 的 `turnover` 计算平均开仓程度和峰值杠杆率，并记录筛选期中位持仓秒数。峰值杠杆率定义为：单日交易名义金额峰值 / `balance_prev_month`；`balance_prev_month <= 0` 的用户不计算杠杆率。SQL 会排除 group 中大小写不敏感包含 `test` 或 `demo` 的账户，例如 `real\\FPlive\\TEST_USD_ZO_BA_NT_H`、`demo\\HHdemo\\forexhh-USD`。该本地文件不会提交到 GitHub。

全量风险名单会在用户 SQL 中按平台生成安全的 Login 排除条件，避免把数万 Login 放进 HTTP 参数导致 414；只有指定少量 Login 时才使用交集过滤。

`balance_prev_month` 为空或小于等于 0 时不会把杠杆率伪造为 0：该用户标记为 `unknown_nonpositive_balance`，跳过杠杆上限，但继续执行胜率、PF、盈亏比、月度持续性和 Top1 日贡献率筛选。快照缺失或日期不匹配时，页面会显示风险快照状态，不会声称杠杆过滤已生效。

高杠杆例外不是无条件放行：只有峰值杠杆超过上限且筛选期中位持仓不超过例外秒数时才放行；短持仓时间来自本地快照，因此仍可在页面请求中使用本地 Login 过滤。

页面顶部的 Abook / Bbook 盈亏分析按 Abook Core 与展示 Bbook（Bbook Core + observation）分别展示筛选期和验证期的账户数、盈利/亏损/中性账户、毛盈利、毛亏损、净 P&L、当前 Bbook 利润和假设 Abook 利润；理论增量只展示 7 月样本外验证期。Abook 理论增量定义为：`假设 Abook 利润 - 当前 Bbook 利润`；在当前没有外部 Abook 成交数据时，假设 Abook 利润为 0，因此它不是实际可实现利润。

阶段公司利润概览是总体人口基线：它使用相同日期、平台、账户组和 test/demo 排除条件，但不使用 Abook 的胜率、PF、稳定性或杠杆筛选。这样修改筛选参数不会改变每个月的总体公司利润；只有日期、平台、账户组或 Login 范围变化时，基线才会变化。

页面的 P&L 区域使用筛选期与验证期的日度增量曲线，悬浮到日期时显示公司净 P&L、对应 Book 净 P&L、盈利 P&L 和亏损 P&L 的当天值。展示层的 BBook 固定包含 Bbook Core 与 observation 候选组；内部筛选仍保留 observation 原始标记用于审计。

这里的 `Profit Factor` 不是单笔交易的传统盈亏比：PF = 阶段总盈利 ÷ 阶段总亏损绝对值；页面的“盈亏比”是 `Payoff Ratio = 平均盈利交易 ÷ 平均亏损交易绝对值`。胜率、Payoff Ratio 和 PF 必须结合使用，单独提高胜率可能得到小赚大亏的策略。当前杠杆率使用交易名义金额 / 上月余额，是仓位管理的可审计代理，不等同于平台真实保证金风险率或净敞口。

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
