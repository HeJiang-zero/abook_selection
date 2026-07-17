# Abook 分析总览与用户详情设计

## 背景

总览当前展示“ Abook 误判”和“Bbook 漏网”。用户希望总览主体改为 Abook 分析：先分别查看筛选期（5–6 月）和验证期（7 月）的 Abook 盈利汇总，再查看每个最终分流到 Abook 的用户，并能打开用户交易详情。

现有后端已经返回账户的 selection、validation、stability、martingale 和 risk 字段，也已有账户交易明细接口；缺口主要在总览组件的展示口径和前端详情 API 接入。

## 目标

1. 将总览中的“ Abook 误判”改为“ Abook 分析”。
2. 分别展示筛选期和验证期的总盈利、总亏损、净 P&L。
3. 只列出最终 book 为 abook 的筛选用户。
4. 用户列表显示 5–6 月 P&L、7 月 P&L、两阶段胜率、交易数、稳定性等信息。
5. 点击用户后展示当前分析窗口内的交易明细和关键账户信息。
6. 保留 Bbook 漏网信息，作为 Abook 分析下方的独立区域，避免现有监控信息丢失。

## 口径

- 筛选期使用 account.selection；验证期使用 account.validation。
- 总盈利是阶段内各 Abook 用户 P&L 大于 0 的金额之和。
- 总亏损是阶段内各 Abook 用户 P&L 小于 0 的绝对值之和。
- 净 P&L = 总盈利 - 总亏损。
- 用户胜率使用阶段内 winning_trades / trade_count。
- 交易详情范围为当前分析窗口的最早日期到最晚日期，即筛选开始日至验证结束日；明细接口继续执行现有 5000 条上限。
- 不把 Abook 客户 P&L 直接解释为公司利润；Abook 区域明确标注客户 P&L 口径。

## 组件与数据流

新增 AbookAnalysis.vue 替换 MisjudgeAnalysis 在总览中的位置。组件接收完整 AnalysisPayload，内部筛选 account.book === 'abook'，计算两个阶段的汇总，并渲染用户表。用户点击事件传回 App.vue。

App.vue 保存 selectedAccount 和 accountDetail 状态；点击用户时调用 GET /api/abook/accounts/{platform}/{login}，传入当前分析窗口 start/end 以及 selection_start/selection_end。AccountDrawer 接收账户摘要和交易详情，展示阶段指标、风险/稳定性/马丁信息、交易明细和品种汇总。

详情加载失败时保留用户摘要并显示错误，不影响总览；关闭抽屉时清理详情状态。重复点击同一用户时允许重新请求，以保证日期窗口变化后明细不会过期。

## 错误处理

- 账户详情请求中，抽屉显示加载状态。
- 请求失败时显示错误信息和“暂无交易详情”，不伪造交易数据。
- 没有 Abook 用户或某阶段没有交易时显示空状态，金额和胜率使用安全的 0 值。
- 交易明细中的 Decimal 已由现有 API 转为 JSON 数字，前端统一格式化显示。

## 测试

- Python API 测试验证账户详情接口继续使用传入日期范围。
- 前端契约测试验证 Abook 分析标题、阶段总盈利/总亏损/净 P&L、Abook 用户筛选、交易详情调用和交易表字段。
- 前端构建验证 Vue 模板、TypeScript 类型和生产静态资源。
- 完整 Python 测试套件回归验证已有分析逻辑不变。

## 验收标准

- 总览显示“Abook 分析”，而不是只显示“Abook 误判”。
- 筛选期和验证期各自显示总盈利、总亏损、净 P&L，净值满足总盈利减总亏损。
- 用户列表只包含 Abook 账户，并显示两个阶段 P&L、胜率和交易数。
- 点击用户可看到当前分析窗口内的历史交易、品种汇总和关键风险信息。
- Bbook 漏网信息仍可查看。

