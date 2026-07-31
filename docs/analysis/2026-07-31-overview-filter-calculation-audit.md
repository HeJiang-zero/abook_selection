# 总览 Tab 筛选参数与计算口径

本文档记录总览 tab 中筛选参数使用的数据源和计算逻辑，用于和其他项目对账。

## 总体结论

总览 Abook 路由是混合口径：

- 交易质量类指标主要使用 `risk.dwd_matched_trades`。
- 客户净 P&L、日度利润集中度主要使用 `risk.ods_mt5_deals`。
- MT4 没有 raw deals 口径时，P&L 相关字段 fallback 到 `risk.dwd_matched_trades.profit`。
- 杠杆不是页面请求中实时从 deals 或 matched trades 直接计算，而是读取本地风险快照 `data/user_risk_snapshot.json`。
- 马丁阻断读取本地马丁快照 `data/martingale_snapshot.json`。

核心代码位置：

- 前端参数：`frontend/src/components/FilterSidebar.vue`
- 默认参数：`frontend/src/App.vue`
- 查询口径：`app/queries.py`
- 路由判断：`app/service.py`
- 风险快照：`app/risk.py`、`scripts/build_user_risk_snapshot.py`
- 马丁快照：`app/martingale.py`

## 最终 Abook 路由规则

普通规则通过条件：

```text
selection.trade_count >= min_trades
AND (selection.profit_factor IS NULL OR selection.profit_factor > min_profit_factor)
AND selection.win_rate >= min_win_rate
AND selection.payoff_ratio >= min_payoff_ratio
AND min_long_trades_ratio <= selection.long_trades_ratio <= max_long_trades_ratio
AND selection.top_positive_day_concentration < max_top1_day_profit_contribution
AND leverage_pass
```

最终 book 分配：

```text
如果马丁阻断 => Bbook
否则如果个人候选名单或新闻候选名单命中 => Abook
否则如果普通规则通过 => Abook
否则 => Bbook
```

注意：个人候选名单和新闻候选名单是 Abook override，但仍会被确认马丁硬阻断。

## 默认参数

| 参数 | 默认值 |
|---|---:|
| 筛选期 | 2026-05-01 至 2026-06-30 |
| 验证期 | 2026-07-01 至 2026-07-22 |
| 平台 | mt4, mt5, hh_mt5 |
| `min_trades` | 75 |
| `min_win_rate` | 0.5 |
| `min_profit_factor` | 1.25 |
| `min_payoff_ratio` | 0.6 |
| `min_long_trades_ratio` | 0.3 |
| `max_long_trades_ratio` | 0.7 |
| `max_top1_day_profit_contribution` | 0.3 |
| `max_leverage_p95_ratio` | 2000 |
| `max_high_leverage_holding_seconds` | 60 |
| `excluded_martingale_levels` | extreme, high, medium, low |

## 参数数据源与计算逻辑

| 参数/指标 | 使用数据 | 计算逻辑 | 是否参与 Abook 路由 |
|---|---|---|---|
| 筛选开始/结束 | `dwd_matched_trades.exit_time` 和 `ods_mt5_deals.time` | 页面传入闭区间日期；后端转为结束日次日的排他上界。matched 指标按 `exit_time`，deals 指标按 `time`。 | 是，限定 selection 指标窗口 |
| 验证开始/结束 | `dwd_matched_trades.exit_time` 和 `ods_mt5_deals.time` | 同筛选期，但只生成 validation 指标。 | 否，只做样本外展示 |
| 平台 | 用户表、matched、deals | 平台限定在 `mt4`、`mt5`、`hh_mt5`。 | 是，限定人口和交易范围 |
| 账户组过滤 | `ods_mt5_users`、`ods_mt4_users` | 用户人口来自 `ods_mt5_users UNION ods_mt4_users`；固定排除 `is_deleted = 1`、group 包含 `test` 或 `demo` 的账户。 | 是 |
| Login 过滤 | 用户表 | 如果指定 Login，只保留对应 Login。 | 是 |
| 最低交易笔数 `min_trades` | `dwd_matched_trades` | 筛选期 `count()`，即 matched round-trip 平仓订单数。要求 `>= min_trades`。 | 是 |
| 最低胜率 `min_win_rate` | `dwd_matched_trades` | `countIf(profit > 0) / count()`。要求 `>= min_win_rate`。 | 是 |
| 最低 Profit Factor `min_profit_factor` | `dwd_matched_trades` | `sumIf(profit, profit > 0) / abs(sumIf(profit, profit < 0))`。要求严格 `> min_profit_factor`。如果没有亏损且有盈利，API 返回 `null`，但路由上视为通过任意有限阈值。 | 是 |
| 最低盈亏比 `min_payoff_ratio` | `dwd_matched_trades` | `平均盈利单 / abs(平均亏损单)`，即 `(gross_wins / winning_trades) / abs(gross_losses / losing_trades)`。要求 `>= min_payoff_ratio`。 | 是 |
| Long 比例下限/上限 | `dwd_matched_trades` | `long_trades / (long_trades + short_trades)`，其中 `long_trades = countIf(direction = 'Long')`，`short_trades = countIf(direction = 'Short')`。上下限都是包含比较。 | 是 |
| Top1 日利润贡献率上限 | `ods_mt5_deals`；MT4 fallback 到 `dwd_matched_trades` | 筛选期内：最大正的单日 `client_net_pnl` / 所有正日 `client_net_pnl` 之和。要求严格 `< max_top1_day_profit_contribution`。 | 是 |
| 最大杠杆率 P95 | 风险快照 | 使用快照字段 `leverage_p95_ratio`。如果余额状态不是 `positive`，或字段缺失，则跳过杠杆上限。 | 是 |
| 高杠杆持仓秒数例外 | 风险快照 + matched 持仓 | 当 `leverage_p95_ratio > max_leverage_p95_ratio` 时，如果 `median_holding_seconds <= max_high_leverage_holding_seconds`，仍通过。 | 是 |
| 确认马丁排除等级 | 马丁快照 | `martingale_detection_status == confirmed` 且 `risk_level` 在勾选的 excluded levels 内时，硬阻断到 Bbook。`suspected` 不会被该列表硬阻断。 | 是，优先级高于普通规则和候选名单 |
| 个人候选名单 | 本地候选名单 | Login 命中时加入 Abook。 | 是，但低于马丁硬阻断 |
| 新闻候选名单 | 本地候选名单 | Login 命中时加入 Abook。 | 是，但低于马丁硬阻断 |

## P&L 口径

### MT5 / HH MT5

客户净 P&L：

```text
client_net_pnl = sum(profit + storage + commission + fee)
where ods_mt5_deals.is_deleted = 0
  and action IN (0, 1)
```

Market P&L：

```text
market_pnl = sum(profit)
where ods_mt5_deals.is_deleted = 0
  and action IN (0, 1)
```

Funding P&L：

```text
funding_pnl = sum(profit)
where action IN (2, 3)
```

`funding_pnl` 单独保留，不计入 `client_net_pnl`。

### MT4

MT4 P&L fallback：

```text
client_net_pnl = sum(dwd_matched_trades.profit)
market_pnl = sum(dwd_matched_trades.profit)
costs = 0
funding_pnl = 0
```

## 质量指标口径

以下指标使用 matched round-trip，即 `dwd_matched_trades.profit`：

- `trade_count`
- `winning_trades`
- `losing_trades`
- `win_rate`
- `gross_wins`
- `gross_losses`
- `profit_factor`
- `average_win`
- `average_loss`
- `payoff_ratio`
- `expectancy_per_trade`
- `long_trades`
- `short_trades`
- `long_trades_ratio`
- `avg_holding_seconds`
- `median_holding_seconds`
- `symbols_traded`

## 风险快照口径

风险快照生成时：

1. 从 `dwd_matched_trades` 按平仓日聚合每日成交额：

```text
daily_turnover = sum(abs(dwd_matched_trades.turnover))
```

2. 从 `risk.ods_mt4_daily_balance` 和 `risk.ods_mt5_daily_balance` 读取每日余额。
3. 每个交易日匹配该日及之前最近的正余额。
4. 计算每日成交额杠杆：

```text
turnover_leverage = daily_turnover / latest_daily_balance_asof_trade_day
```

5. 同时用 `dwd_matched_trades` 的 entry/exit 时间线重建并发未平仓敞口；MT5 还会尝试从 `ods_mt5_deals` 补未被 matched 覆盖的开仓事件。
6. 最终 `leverage_p95_ratio` 取成交额杠杆 P95 与并发敞口杠杆 P95 中更保守的较高值。

余额为空、小于等于 0、或交易日找不到余额时，不会把杠杆伪造成 0；该账户会标记为 `missing_daily_balance` 或 `unknown_nonpositive_balance`，路由时跳过杠杆上限。

## 可能导致和另一个项目不一致的点

- PF、胜率、盈亏比、交易数用 `dwd_matched_trades`，不是 raw deals。
- 客户净 P&L 和 Top1 日利润贡献率用 deals client net；MT4 例外，用 matched fallback。
- Profit Factor 是严格 `>` 阈值，不是 `>=`。
- Top1 日利润贡献率是严格 `<` 阈值，不是 `<=`。
- 没有亏损交易且有盈利时，PF 在 JSON 里是 `null`，但筛选通过有限 PF 阈值。
- `client_net_pnl` 包含 `storage + commission + fee`，但不包含 `action IN (2, 3)` 的 funding。
- 日期结束日是闭区间输入、排他上界查询，例如 `2026-06-30` 会查到 `< 2026-07-01`。
- group 中包含 `test` 或 `demo` 的账户被硬排除。
- 杠杆来自快照，不一定随着页面日期修改实时重算；快照 stale 时页面会提示重建。
- 马丁快照缺失或 invalid 会安全阻断；stale 会提示但不会把总览全部强制 Bbook。
