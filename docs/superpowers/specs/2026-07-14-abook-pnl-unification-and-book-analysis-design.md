# Abook/Bbook P&L 统一与顶部盈亏分析设计

## 目标

修复真实 ClickHouse 数据核查中发现的统计问题，并在页面顶部增加 Abook 候选与 Bbook 候选的盈利、亏损和理论利润影响分析。

本次范围包括：

- 所有分析和账户明细路径强制排除账户组中不区分大小写包含 `test` 或 `demo` 的账户。
- 修复跨平台 login 去重少算、无交易账户产生 NaN、跨月统计不正确等问题。
- 统一 matched/deals 的交易 P&L 口径。
- 在页面顶部展示 Abook/Bbook 候选组在筛选期和验证期的盈利、亏损与理论利润影响。

明确不在本次范围：新增真实 ClickHouse 集成测试、浏览器自动化测试和其他第 5 类测试工作。

## 口径设计

### 用户范围

有效用户来源为 `risk.ods_mt5_users FINAL`，要求：

- `is_deleted = 0`。
- 平台为 `mt5` 或 `hh_mt5`。
- 账户组不包含 `test` 或 `demo`。

用户唯一键统一为 `(platform, login)`。排除条件在用户 CTE、交易聚合、源覆盖统计和账户明细查询中均生效；外部请求不能通过 `exclude_test_accounts=false` 绕过强制排除。

### 统一 P&L

采用 `risk.ods_mt5_deals FINAL` 中 `action IN (0, 1)` 的交易流水作为唯一客户交易 P&L 来源：

- `market_pnl = sum(profit)`。
- `costs = sum(storage + commission + fee)`。
- `client_net_pnl = market_pnl + costs`。
- `gross_wins`、`gross_losses` 和 Profit Factor 均从该 P&L 来源计算。
- `action IN (2, 3)` 保持为独立 funding P&L，不参与交易盈利筛选。

`risk.dwd_matched_trades FINAL` 只用于交易数、成交量、成交额、持仓时间、品种和方向等行为指标。为便于审计，可以保留 matched 的参考 P&L 字段，但不得再用于业务 P&L、Profit Factor、理论公司利润或候选筛选。

### 跨月指标

- 日收益标准差使用所有有效交易日的总和、平方和与样本数计算总体标准差，不再对月度标准差做加权平均；无有效交易日时返回 0。
- 持仓时间中位数按筛选期和验证期分别从 matched 明细聚合，不能取最后一个月的中位数。
- 品种数按筛选期和验证期分别做期间去重。
- 月度活跃账户按 `(platform, login)` 去重。

## API 数据流

查询层继续输出账户月度粒度，但增加或调整以下字段：

- canonical deals P&L 字段：`market_pnl`、`gross_wins`、`gross_losses`、`deal_market_pnl`、`costs`、`client_net_pnl`。
- matched 行为字段：交易数、成交量、持仓时间、方向、品种等。
- 日收益统计所需的总和、平方和、有效交易日数。
- 筛选期和验证期的持仓时间中位数、品种数。
- 采用 `uniqExact(tuple(platform, login))` 的人口统计字段。

服务层按统一 canonical P&L 计算：

- 账户、月度、分组、验证和利润影响的 `market_pnl`。
- gross profit/loss、Profit Factor、平均日利润和候选分组。
- 理论 Bbook 利润与 Abook 理论增量。

### Abook 理论增量

定义为：

`Abook 理论增量 = 假设 Abook 后公司利润 - 当前 Bbook 公司利润`

在当前假设 Abook 公司利润为 0、Bbook 公司利润为 `-用户净交易 P&L` 时：

`Abook 理论增量 = 用户净交易 P&L`

该指标表示相对继续留在 Bbook 的理论变化，不是真实 Abook 收益；不包含外部成交、点差、滑点、流动性和对冲成本。

## 顶部页面展示

在现有 KPI 区域下方增加 Abook/Bbook 盈亏分析区，分别展示筛选期（2026-05 至 2026-06）和验证期（2026-07-01 至 2026-07-13）：

- 候选账户数。
- 盈利、亏损、中性账户数及占比；中性区间沿用 ±10 USD。
- 总盈利、总亏损、净 P&L。
- 当前 Bbook 理论利润。
- 假设 Abook 利润。
- Abook 理论增量。

页面名称使用“Abook 候选”和“Bbook 候选”，并明确标注“理论”与“样本外验证”，避免把候选组误解为已经实际迁移的账簿。

## 错误处理与兼容性

- 所有输出数值必须有限；无亏损交易的 Profit Factor 继续以 `null` 表示。
- 无交易账户保留在阶段汇总中，但所有比例使用非零分母保护。
- 账户明细接口对 demo/test 账户返回空结果或拒绝访问，不返回交易明细。
- 保留前端已有字段名称和结构；canonical P&L 字段优先使用新字段，测试 fixture 缺失新字段时允许向后兼容回退，真实查询不依赖回退。

## 验证标准

- 现有单元测试在更新口径后全部通过。
- 真实查询结果中 demo/test 账户为 0。
- 有效账户数按 `(platform, login)` 统计，不再少算跨平台 login。
- 真实数据 payload 可通过 `json.dumps(..., allow_nan=False)`。
- matched/deals 的业务 P&L 字段在服务层使用同一 canonical deals 口径。
- 顶部 Abook/Bbook 汇总可与账户明细、筛选期和验证期汇总相加核对。
