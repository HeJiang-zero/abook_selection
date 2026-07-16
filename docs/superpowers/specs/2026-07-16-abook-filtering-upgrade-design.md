# Abook 筛选面板 Phase 0–6 升级设计

## 目标

在保持现有 FastAPI 分析接口主要输出兼容、现有 ClickHouse 数据口径不变的前提下，把马丁策略排除、参数寻优、误判成本、名单导出、Book 量化分析和前端工程化一次接入，形成可验证、可操作的 Abook/Bbook 分流面板。

## 背景与现状

当前仓库已有 FastAPI、ClickHouse 查询、两阶段账户分类、风险快照、个人候选名单和静态 Vue3 CDN 页面。`build_two_stage_payload` 已包含选择期/验证期分类、稳定性评分、Book 汇总和日度 P&L，但取数和内存计算耦合在同一个服务函数中。工作区新增的 `app/martingale.py` 与 `scripts/build_martingale_snapshot.py` 尚未接入主分析路径。当前 65 个 pytest 测试通过，前端没有 Vite 工程。

## 设计原则

1. 单次分析只取一次 ClickHouse 账户月事实和账户日事实；参数组合在内存中复用已取数据。
2. Abook 分类是唯一事实来源，主分析、寻优、导出和 Book 分析都调用同一分类函数，避免口径漂移。
3. 本地快照状态显式传播。快照 `missing`、`invalid`、`stale` 时不得静默解释为“没有马丁用户”。
4. 马丁拦截优先级高于规则候选和个人候选名单；Bbook 展示不因马丁被删除。
5. 验证期数据只用于验证和误判度量，寻优页面明确声明样本内择优和滚动验证要求。
6. 先写失败测试，再写最小实现；每个阶段均能独立运行和回归。

## 总体架构

```text
AnalysisRequest
  ├─ local snapshots: risk + martingale + personal candidates
  ├─ repository: monthly facts + daily pnl (one fetch per dataset)
  └─ service data context
       ├─ aggregate_accounts()
       ├─ classify_accounts(rules, snapshots)
       ├─ summarize_books()/misjudge()/funnel()
       └─ build payload / sweep result / export rows / book analytics

FastAPI endpoints
  /analysis          → full dashboard payload
  /sweep             → in-memory parameter grid evaluation
  /export            → CSV of final Abook list
  /book-analytics    → independent lazy-loaded Book analytics

Vite Vue3 frontend → static/ build output → FastAPI StaticFiles
```

服务层会在保留 `build_two_stage_payload()` 外部调用兼容性的同时，抽出可测试的 `prepare_analysis_context()`、`classify_accounts()` 和 `build_analysis_payload_from_context()`。ClickHouse Repository 增加一次性读取和 Book 分析所需的最小聚合接口；无法使用真实库时，所有新服务函数仍可用 pytest fixtures 验证。

## Phase 0：马丁表探查

新增可执行探查脚本，使用现有 `.env` 配置连接 ClickHouse，只输出 schema、`window_type` 取值、窗口覆盖范围和 `avg_volume_escalation` 分桶统计，不记录密码。探查结果写入 `docs/analysis/2026-07-16-martingale-schema.md`，明确当前字段是倍数还是增长率、实际窗口是否滚动 7 日，并让快照构建脚本使用同一结论。数据库不可用时，脚本返回清晰的配置/连接错误，应用仍以快照未就绪状态运行。

## Phase 1：马丁快照和硬拦截

`build_martingale_snapshot.py` 使用选择期覆盖范围内的所有滚动窗口，对五层规则逐窗打标，按用户取最严重风险等级并保留命中窗口计数及关键最大/最小指标。快照记录至少包含五层命中计数、风险等级、窗口元数据和可读的 `layer_hits` 明细。

`MartingaleSnapshot` 提供：

- `status`: `missing`、`invalid`、`stale` 或 `ready`；
- `blocked_logins(excluded_levels)`：只在 `ready` 时返回拦截集合；
- `enrich_rows(rows)`：给账户行添加 `martingale_risk_level`、`martingale_layer_hits` 和快照状态；
- `summary(excluded_levels)`：供规则区、侧边栏和审计输出使用。

`AnalysisRules` 新增 `excluded_martingale_levels`，默认 `['extreme', 'high', 'medium']`，允许显式加入 `low`。主分析先加载马丁快照，再将其作为 Abook 分类阶段的硬排除条件。个人名单仍可让账户进入分类输入，但不能让被拦截账户成为 `abook_candidate`；其 `selection_source` 记录 `martingale_blocked`。如果快照不是 `ready`，页面提示过滤未生效，且响应的 `rules` 和 `martingale` 区块同时暴露状态。

账户详情接口在现有交易明细外附带快照匹配记录和五层明细；没有匹配或快照未就绪时返回状态而非伪造命中。

## Phase 2：服务层拆分

把现有服务逻辑按责任拆成以下边界：

- `aggregate_account_rows(rows, periods)`：将月事实聚合为账户选择期/验证期指标；
- `classify_account(account, rules, personal_logins, martingale_index)`：只做规则判定、稳定性层级、来源和验证状态；
- `build_analysis_payload_from_context(context, rules)`：计算分组、迁移、利润影响、日度曲线和漏斗；
- `build_two_stage_payload(...)`：保留旧签名，负责组装 context 并转调新函数。

分类结果包含 `base_cohort`、最终 `cohort`、`selection_source`、`deployable`、稳定性、马丁字段和验证期指标。Abook 只包含最终 `abook_candidate`；展示 Bbook 仍为 `bbook_candidate + observation`。

## Phase 3：参数寻优

新增模型：

```python
class SweepRequest(BaseModel):
    analysis: AnalysisRequest
    grid: dict[str, list[Any]]
    objective: Literal["validation_increment", "increment_with_cost_cap", "validation_precision"]
    max_misjudge_cost: float | None = Field(default=None, ge=0)
```

只允许 `AnalysisRules` 中的数值规则进入网格，拒绝未知字段、空列表、非法范围和超过 500 个笛卡尔积组合。`increment_with_cost_cap` 必须提供成本上限。`POST /api/abook/sweep` 先取一次基础数据，再逐组调用纯内存分类/汇总，返回每组规则、Abook Core 数、验证活跃样本、继续盈利率、验证理论增量、误判成本、净收益、precision、lift 和马丁拦截人数。结果按目标排序，并带 `sample_warning`、`validation_partial` 和“样本内择优”的护栏文案。

## Phase 4：误判、漏斗和导出

主分析响应增加：

- `misjudge.abook_losses`：Abook 且验证期亏损的账户及亏损额；
- `misjudge.abook_loss_total`：误判成本；
- `misjudge.bbook_profitable`：Bbook 展示组中验证期盈利账户及 `selection_flags`/拦截原因；
- `funnel`：全量人口、样本达标、方向盈利、稳定 Core、杠杆通过、非马丁、Abook Core 各层人数和流失原因；
- `personal_candidate_impact`：个人名单开关前后 Abook 人数和验证增量差异。

`GET /api/abook/export` 接受与分析相同的 query/body 语义，返回 `text/csv`，列出 platform、login、group、选择期关键指标、验证期关键指标、来源和马丁拦截原因。导出只允许最终 Abook 名单，不把 Bbook 或 observation 账户混入。

## Phase 5：Book 量化分析

新增 `POST /api/abook/book-analytics`，请求包含 `AnalysisRequest`、当前确定的 Abook 名单和可选 `hedge_cost_bps`（0–5）。后端复用主分析分类结果；全量人口和 Abook 聚合来自同一窗口，Bbook 使用全量减 Abook 的差集。

响应包含四块：

1. 盈亏结构：选择期/验证期日度和累计曲线、账户 P&L 分布、最大回撤、Top 5/10/20 集中度、胜率和 PF 分布。
2. 用户结构：刷单/高频/波段/马丁风格人数、P&L、持仓/交易量分桶和品种热力图。
3. 风险敞口：日度多空 turnover、峰值杠杆、最大敞口日期、Abook 对冲成本、扣成本后的验证增量和盈亏平衡 bps。
4. 分流质量：筛选期 cohort 到验证状态迁移矩阵、逐日命中率/累计命中差、分流前后公司利润对比。

新增 SQL 只返回账户日/品种聚合，不在 SQL 中塞数万 login；Abook 名单作为小集合下推，Bbook 由差集完成。不存在交易明细时，接口返回空分布和可解释的样本状态，不报 500。

## Phase 6：Vite 前端

新增 `frontend/` 工程，使用 Vite、Vue 3、TypeScript、TailwindCSS 和 ECharts。开发服务器将 `/api` 代理到 8000，生产构建以 `vite build --outDir ../static` 覆盖静态产物。组件边界为 `FilterSidebar`、`KpiCards`、`BookPerformance`、`MisjudgeAnalysis`、`SelectionFunnel`、`SweepPanel`、`AccountsTable` 和 `AccountDrawer`。

页面使用总览、盈亏结构、用户结构、风险敞口、分流质量、参数寻优六个 Tab。Book 分析只在首次进入对应 Tab 时请求；所有 Tab 都读取相同的当前请求和 Abook 名单。侧边栏显示风险/马丁快照状态、排除人数和规则；账户表支持搜索、排序、分页/虚拟滚动、马丁/来源标记和 CSV 导出；抽屉显示交易明细及马丁五层命中。

## 错误处理与兼容性

- 未配置 ClickHouse：分析接口返回 503；静态首页和 `/api/health` 仍可用。
- ClickHouse 查询错误：返回 502，隐藏连接凭据，保留服务端日志上下文。
- 快照缺失/损坏/过期：分析返回 200 但 `martingale.status` 明确非 ready，页面显示警告；不静默称为无命中。
- 寻优输入错误：返回 422，并指出具体 grid 字段或组合数。
- CSV 始终 UTF-8 with BOM，便于中文表头在 Excel 中打开；无名单时返回表头和 200。
- 旧 `lookback_months` 请求、旧分析字段和旧账户详情接口保持现有测试契约。

## 测试与验收标准

新增 pytest 覆盖：快照状态和窗口边界、五层规则/风险等级、个人名单与马丁冲突、拆分后的分类纯函数、寻优 500 组合上限与指标、误判/漏斗、CSV 字段、Book 差集与 bps 敏感性、账户详情马丁明细、前端构建产物契约。验收命令为：

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run build
cd .. && .venv/bin/python -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); assert c.get('/api/health').json()['status']=='ok'; assert c.get('/').status_code == 200"
```

真实数据验收在 ClickHouse 可用时运行 schema 探查和快照构建，记录默认参数接入前后 Abook 人数、验证增量、误判成本和马丁排除人数；寻优结果标记为样本内择优，并写入 `docs/analysis`。
