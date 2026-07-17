# Abook 分析总览与用户详情 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将总览改为 Abook 分析，分阶段展示盈利汇总和 Abook 用户指标，并接入当前分析窗口内的交易详情抽屉。

**Architecture:** 新增 AbookAnalysis.vue 负责 Abook 汇总、用户列表和 Bbook 漏网保留区；App.vue 负责账户详情请求状态；AccountDrawer.vue 负责阶段指标、风险信息、品种汇总和交易明细。后端复用已有账户详情接口，只补充 API 客户端和契约测试。

**Tech Stack:** Vue 3、TypeScript、FastAPI、pytest、Vite、现有 ClickHouse 账户详情查询。

## Global Constraints

- 顶部同时展示筛选期（5–6 月）和验证期（7 月）两组汇总。
- 总盈利 = 阶段内正 P&L 用户金额之和；总亏损 = 阶段内负 P&L 绝对值之和；净 P&L = 总盈利 - 总亏损。
- 用户列表只展示最终 book 为 abook 的账户。
- 用户胜率使用阶段内 winning_trades / trade_count，0 交易时显示 0.0%。
- 交易详情使用当前分析窗口的最早日期到最晚日期，并保留后端 5000 条限制。
- Abook 客户 P&L 不解释为公司利润；Bbook 漏网区继续保留。
- 不修改既有筛选和路由逻辑。

## Files

- Create: frontend/src/components/AbookAnalysis.vue
- Modify: frontend/src/components/KpiCards.vue
- Modify: frontend/src/components/AccountDrawer.vue
- Modify: frontend/src/App.vue
- Modify: frontend/src/api.ts
- Modify: frontend/src/types.ts
- Modify: tests/test_frontend_contract.py
- Modify: tests/test_api.py
- Modify: README.md

---

### Task 1: Add failing contract and API tests

**Files:**
- Modify: tests/test_frontend_contract.py
- Modify: tests/test_api.py

- [ ] Step 1: Add frontend contract assertions.

Assert AbookAnalysis.vue exists and contains Abook 分析, 筛选期, 验证期, 总盈利, 总亏损, 净 P&L, selection_client_net_pnl, validation_client_net_pnl, refresh/detail identifiers, and that App.vue no longer imports MisjudgeAnalysis.

- [ ] Step 2: Add account detail date-range API test.

Patch a FakeRepository.fetch_account_detail that records arguments, call GET /api/abook/accounts/mt5/7 with start=2026-05-01, end=2026-07-16, selection_start=2026-05-01, selection_end=2026-06-30, and assert those exact values reach the repository.

- [ ] Step 3: Run the focused tests and verify RED.

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_frontend_contract.py -k abook_analysis tests/test_api.py -k account_detail_range
~~~

Expected: FAIL because AbookAnalysis.vue, fetchAccountDetail, and the new contract are absent.

---

### Task 2: Implement the Abook analysis overview

**Files:**
- Create: frontend/src/components/AbookAnalysis.vue
- Modify: frontend/src/components/KpiCards.vue
- Modify: frontend/src/App.vue

**Interfaces:**
- AbookAnalysis props: data: AnalysisPayload.
- AbookAnalysis emits: open(account: AccountRow).
- App receives open and passes selected account to AccountDrawer.

- [ ] Step 1: Implement phase aggregation.

Use a local function that maps Abook accounts to each phase and returns positive_pnl, negative_pnl, net_pnl, account count, active account count, trade count, and win_rate. Render two phase cards with labels 筛选期（5–6 月） and 验证期（7 月）. Render the formula text 总盈利 - 总亏损 = 净 P&L.

- [ ] Step 2: Implement the Abook user table.

Filter accounts with account.book === 'abook'. Render platform/Login, account group, selection/validation P&L, selection/validation win rate, trade counts, and stability. Emit open on row click. Render empty state when no Abook accounts exist.

- [ ] Step 3: Preserve Bbook leakage below the Abook table.

Reuse data.misjudge.bbook_profitable and the existing >100 display filter. Label it Bbook 漏网 and show company loss if left in Bbook. Do not show the old Abook 误判 label.

- [ ] Step 4: Replace the old total KPI and component wiring.

Change KpiCards fourth KPI from Abook 误判成本 to Abook 验证期净 P&L. Replace MisjudgeAnalysis import/use in App.vue with AbookAnalysis. Update header subtitle to mention用户表现与交易详情. Keep SelectionFunnel and AccountsTable only if they remain useful; the new Abook table is the primary Abook list.

- [ ] Step 5: Run the focused frontend contract test.

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_frontend_contract.py -k abook_analysis
~~~

Expected: PASS.

---

### Task 3: Connect account detail API and enrich the drawer

**Files:**
- Modify: frontend/src/api.ts
- Modify: frontend/src/types.ts
- Modify: frontend/src/App.vue
- Modify: frontend/src/components/AccountDrawer.vue

**Interfaces:**
- fetchAccountDetail(account: AccountRow, request: RequestModel): Promise<AccountDetailPayload>.
- AccountDetailPayload has trades: Array<Record<string, unknown>> and symbols: Array<{symbol: string; trade_count: number; volume: number; profit: number; win_rate: number; avg_holding_seconds: number}>.
- AccountDrawer props: account, detail, loading, error.

- [ ] Step 1: Implement typed detail API client.

Build URLSearchParams with start=min(selection.start, validation.start), end=max(selection.end, validation.end), selection_start, selection_end. Request GET /api/abook/accounts/{platform}/{login}.

- [ ] Step 2: Implement App detail state.

Add detail, detailLoading, detailError refs and openAccount(account), closeAccount() functions. On open, set account immediately, clear old detail/error, request the current analysis window, and keep the summary visible if the request fails. On close, clear all detail state. Clear selected account when a new analysis loads.

- [ ] Step 3: Implement the drawer detail sections.

Show phase P&L, win rate, trade count, PF, payoff ratio, stability, confidence, risk leverage P95, martingale level, symbols table, and trades table. Show loading and error states. Format timestamps, numbers, and missing values safely.

- [ ] Step 4: Run frontend build.

Run with the bundled Node runtime:

~~~bash
PATH="/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH" NODE_PATH="/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules" pnpm run build
~~~

Expected: Vite exits 0 and updates static/.

---

### Task 4: Documentation and complete verification

**Files:**
- Modify: README.md
- Modify: tests/test_frontend_contract.py

- [ ] Step 1: Document Abook 分析 and current-window detail behavior in README.

- [ ] Step 2: Run full Python tests, frontend contract tests, build, and diff check.

~~~bash
.venv/bin/python -m pytest -q
PATH="/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH" NODE_PATH="/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules" pnpm run build
git diff --check
~~~

Expected: all tests pass, build exits 0, and diff check is clean.

- [ ] Step 3: Commit feature changes.

~~~bash
git add frontend/src/components/AbookAnalysis.vue frontend/src/components/KpiCards.vue frontend/src/components/AccountDrawer.vue frontend/src/App.vue frontend/src/api.ts frontend/src/types.ts tests/test_frontend_contract.py tests/test_api.py README.md
git commit -m "feat: add abook analysis overview and trade details"
~~~

## Plan Self-Review

- Stage totals, formula, and Abook-only users are covered by Task 2.
- Bbook leakage preservation is covered by Task 2 Step 3.
- Current-window transaction details and error states are covered by Task 3.
- Date forwarding is covered by Task 1 Step 2.
- Existing filtering/routing remains untouched.
- No unresolved placeholders or unspecified error-handling steps remain.

