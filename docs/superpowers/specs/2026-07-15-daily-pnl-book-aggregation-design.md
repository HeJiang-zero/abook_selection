# 日度 P&L 曲线与 BBook 观察组合并设计

## 背景

当前仪表盘在“筛选期与验证期月度 P&L”区域使用按月结果绘图，鼠标悬浮时只能读取月度聚合值。页面还展示了入选组 vs 对照组、用户状态迁移和 Abook 理论利润影响三个不再需要的区块。

本次改动将 P&L 图改为日度增量曲线，并将页面展示从三组收敛为 Abook / BBook 两组：内部筛选仍保留 `observation` 原始标记，但展示层把 `bbook_candidate + observation` 作为 BBook。

## 目标与非目标

### 目标

- 在筛选期和验证期的完整日期范围内展示当天 P&L 增量。
- 提供两张日线图：Abook 图和 BBook 图。
- 每张图展示公司净 P&L、对应 Book 净 P&L、对应 Book 盈利 P&L、对应 Book 亏损 P&L。
- Tooltip 在同一天内同时展示日期、阶段和所有曲线的精确金额。
- BBook 展示组包含 `bbook_candidate` 与 `observation`。
- 删除 `入选组 vs 对照组`、`TRANSITIONS：用户状态迁移`、`PROFIT IMPACT：Abook 理论利润影响` 页面区块。
- 保持现有分析 API 中迁移和利润影响字段的向后兼容。

### 非目标

- 不改变 Abook/Bbook 候选筛选规则、稳定性评分或验证状态计算。
- 不新增用户可配置的“是否合并观察组”开关；本次固定按 BBook 展示。
- 不实现真实外部 Abook 成交、点差、滑点、对冲或流动性成本。
- 不删除后端 `transitions` 或 `profit_impact` 字段。

## 口径与数据流

### P&L 口径

日度查询使用 `risk.ods_mt5_deals FINAL`：

```text
client_net_pnl = profit + storage + commission + fee
```

仅计入 `action IN (0, 1)`，并过滤 `is_deleted = 0`。用户、平台、账户组、Login、test/demo 过滤边界与现有分析查询一致。日期以 UTC 的 `toDate(time)` 聚合。

公司净 P&L 沿用当前公司 BBook 利润定义：总体人口用户净交易 P&L 的相反数。Abook/BBook 净 P&L 为相应展示组的用户净交易 P&L。盈利和亏损曲线按账户当天净 P&L 拆分：正值合计为盈利 P&L，负值合计为亏损 P&L；两者相加等于对应 Book 净 P&L。

### 查询与服务层

保留现有按月分析查询，用于账户筛选、稳定性和阶段汇总；新增独立日度查询返回至少以下字段：

- `platform`
- `login`
- `trade_date`
- `client_net_pnl`
- `market_pnl`（保留统一口径的对账字段）
- `matched_trades`（用于识别活动日，可选但建议保留）

日度查询由 Repository 暴露独立方法。两阶段分析请求需要同时支持：

- 总体人口日度行：用于公司净 P&L；
- 有效分析账户日度行：用于根据筛选结果分配 Abook/BBook。

服务层在现有账户分组完成后，以 `(platform, login)` 将日度行分配到 `abook_candidate`、`bbook_candidate`、`observation`，再把后两者合并为展示用 BBook。所有日期生成完整网格，缺失值为 0；日期按升序返回，并附带 `phase`（筛选期/验证期）。

建议返回新字段 `daily_book_series`，结构为：

```json
{
  "date": "2026-05-15",
  "phase": "selection",
  "company_net_pnl": 100.0,
  "abook": {
    "net_pnl": 20.0,
    "profitable_pnl": 30.0,
    "loss_pnl": -10.0
  },
  "bbook": {
    "net_pnl": -80.0,
    "profitable_pnl": 5.0,
    "loss_pnl": -85.0
  }
}
```

其中每组满足 `net_pnl = profitable_pnl + loss_pnl`，避免前端自行计算造成口径差异。

## 前端设计

- 将原月度 P&L 卡片改为日度 P&L 区域，包含两个相同高度的图表：Abook 日度 P&L、BBook 日度 P&L。
- 两张图均使用折线图，四条曲线分别对应公司净 P&L、Book 净 P&L、Book 盈利 P&L、Book 亏损 P&L。
- 使用类目日期轴，日期显示保持紧凑；筛选期与验证期通过背景分段或阶段标记区分。
- 使用 ECharts `tooltip.trigger = 'axis'` 和 crosshair axis pointer。formatter 显示完整日期、阶段和每条曲线的美元金额，不要求用户读取坐标轴。
- 新增独立的图表实例和 resize 处理；重新加载分析时用新数据整体替换旧 option，避免旧月份或旧曲线残留。
- 删除验证图、迁移表和理论利润影响表对应的 HTML；删除不再使用的 `renderValidationChart`、迁移 formatter/helper 和相关前端状态引用。保留后端字段，不影响接口兼容。
- 账户表的展示筛选将 `observation` 归入 BBook；内部原始 cohort 字段可以继续保留，账户详情不改变筛选依据。

## 测试策略

### 后端

- 查询构造测试：确认日度查询使用 `FINAL`、`is_deleted = 0`、test/demo 排除、平台/组/Login 过滤、UTC 日聚合和交易 P&L 公式。
- Repository/API 测试：Fake Repository 提供日度行时，响应包含 `daily_book_series`；没有日度行的旧兼容 fixture 不应破坏既有月度/API 测试。
- 服务层测试：
  - 日期按日排序且覆盖筛选期与验证期；缺失日期为 0；
  - Abook 与 BBook 日净 P&L 聚合正确；
  - `bbook_candidate + observation` 合并正确；
  - 每组净值等于盈利值加亏损值；
  - 公司净 P&L 使用总体人口，不受候选筛选组变化影响。

### 前端

- 契约测试确认页面存在两张日线图和日度数据字段，tooltip 使用 axis trigger/crosshair。
- 契约测试确认页面不再包含“入选组 vs 对照组”、`TRANSITIONS`、`PROFIT IMPACT` 及对应旧渲染入口。
- 契约测试确认 BBook 展示包含观察组，Abook/BBook 图表数据字段均被使用。

## 验收标准

1. 页面加载分析后显示上下两张日线图，不再显示月度 P&L、入选组 vs 对照组、TRANSITIONS 和 PROFIT IMPACT 区块。
2. 移动鼠标到任意日期，tooltip 直接列出当天四条曲线的金额和筛选/验证阶段。
3. Abook 曲线只使用 Abook Core；BBook 曲线使用 Bbook Core 加观察组。
4. 同一天每组 `net = profitable + loss`，公司线使用总体人口口径。
5. test/demo 账户和删除 Deals 不进入任何日度值。
6. 现有筛选、账户详情和既有 API 兼容测试保持通过。

