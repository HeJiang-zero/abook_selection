# Abook 筛选面板 Phase 0–6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 `modify.md` 的 Phase 0–6，让马丁排除、参数寻优、误判分析、CSV 导出、Book 分析和 Vite Vue3 面板在同一套可复用分析口径上运行。

**Architecture:** 保留现有 FastAPI/ClickHouse 入口与旧分析字段；将账户月事实、日度事实和快照整理成可复用的内存分析上下文，主分析、寻优、导出和 Book 分析全部调用同一分类函数。最后建立 Vite Vue3 + TypeScript + TailwindCSS + ECharts 前端并把构建结果输出到 `static/`。

**Tech Stack:** Python 3.9、FastAPI 0.115、Pydantic 2、ClickHouse Connect、pytest、Node/Vite、Vue 3、TypeScript、TailwindCSS、ECharts。

## Global Constraints

- 保持现有 65 个 pytest 测试通过，并保持旧 `lookback_months` 请求兼容。
- 马丁快照只有 `ready` 才能产生拦截集合；`missing`、`invalid`、`stale` 必须在 API 和 UI 显式显示。
- 默认排除马丁风险等级 `extreme`、`high`、`medium`，`low` 必须可配置。
- 个人候选名单不能绕过马丁硬拦截；Bbook 展示包含 Bbook Core 与 observation。
- 参数寻优最多 500 个组合，验证期 7 月 1–13 日必须在结果中标记为部分月份/样本内择优。
- 新 SQL 只做聚合或小名单下推，不向 ClickHouse 传入数万 login。
- 所有新行为先写一个最小失败测试，再写实现，再跑目标测试和全量回归。
- 不修改工作区已有的用户未跟踪文件：`modify.md`、`martingale.md`、`may_june_mean_bps_gt_0.05_logins.csv`、`app/martingale.py`、`scripts/build_martingale_snapshot.py` 以外的无关内容。

## File Map

- Create `scripts/probe_martingale_schema.py`: Phase 0 的 schema、窗口和倍数口径探查。
- Modify `scripts/build_martingale_snapshot.py`: 使用探查结论，输出五层命中明细和统一元数据。
- Modify `app/martingale.py`: 完成快照状态、索引、行 enrich 和摘要接口。
- Modify `app/models.py`: 增加马丁规则、寻优和 Book 分析请求模型。
- Modify `app/service.py`: 抽取可复用分析上下文，接入马丁分类，并计算误判、漏斗和名单影响。
- Create `app/sweep.py`: 参数网格展开、校验、排序目标和结果计算。
- Create `app/book_analytics.py`: 两个 Book 的差集聚合、分布、敞口和迁移指标。
- Modify `app/queries.py` and `app/repository.py`: 增加探查、品种/turnover 聚合和一次性数据读取接口。
- Modify `app/main.py`: 接入快照，新增 `/sweep`、`/export`、`/book-analytics`，扩展账户详情。
- Create `app/exports.py`: 最终 Abook CSV 序列化。
- Create `frontend/` with `package.json`, `vite.config.ts`, `index.html`, `src/main.ts`, `src/App.vue`, `src/style.css`, and focused components.
- Replace generated `static/index.html`, `static/app.js`, `static/styles.css` through the frontend build.
- Add tests under `tests/test_martingale.py`, `tests/test_sweep.py`, `tests/test_book_analytics.py`, `tests/test_exports.py`, and extend `tests/test_api.py`, `tests/test_frontend_contract.py`.

---

### Task 1: Phase 0 schema probe and robust martingale snapshot

**Files:**
- Create: `scripts/probe_martingale_schema.py`
- Modify: `scripts/build_martingale_snapshot.py`
- Modify: `app/martingale.py`
- Create: `tests/test_martingale.py`
- Create: `docs/analysis/2026-07-16-martingale-schema.md`

**Interfaces:**
- `probe_martingale_schema.py` exposes `probe(client) -> dict` and `main()`; its result has `columns`, `window_types`, `coverage`, `escalation_bins`, and `escalation_unit`.
- `MartingaleSnapshot.enrich_rows(rows)` adds `martingale_status`, `martingale_risk_level`, `martingale_layer_hits`, and `martingale_record` to each row.
- Snapshot records expose `layer_hits` as a five-key boolean mapping and preserve the existing aggregate counters.

- [ ] **Step 1: Write failing tests for snapshot state and five-layer output**

```python
def test_missing_snapshot_has_no_blocked_users_and_explicit_status(tmp_path):
    snapshot = load_martingale_snapshot(tmp_path / "missing.json", "2026-05-01", "2026-06-30", ["mt5"])
    assert snapshot.status == "missing"
    assert snapshot.blocked_logins(("extreme",)) == set()
    assert snapshot.summary()["status"] == "missing"

def test_ready_snapshot_enriches_rows_with_layer_details(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01", "selection_end": "2026-06-30",
        "platforms": ["mt5"], "window_type": "7D_SLIDING",
        "records": [{"platform": "mt5", "login": 7, "risk_level": "high",
                      "layer_hits": {"layer1": True, "layer2": True, "layer3": True,
                                      "layer4": True, "layer5": False}}]
    }))
    snapshot = load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])
    row = snapshot.enrich_rows([{"platform": "mt5", "login": 7}])[0]
    assert row["martingale_status"] == "ready"
    assert row["martingale_risk_level"] == "high"
    assert row["martingale_layer_hits"]["layer4"] is True
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run: `.venv/bin/python -m pytest -q tests/test_martingale.py`

Expected: FAIL because `enrich_rows` and the new fields do not exist.

- [ ] **Step 3: Implement probe and snapshot fields**

Use `client.query(...).column_names` for `DESCRIBE TABLE risk.dws_account_martingale_window`, group the table by `window_type`, compute `min(window_start)`, `max(window_end)`, and `quantileTDigest` bins for `avg_volume_escalation`. Keep the existing multiplier interpretation in the output, but make it a recorded probe result. Add `layer_hits` during record construction and add status-aware `enrich_rows`/`summary` methods.

- [ ] **Step 4: Run targeted and existing martingale tests**

Run: `.venv/bin/python -m pytest -q tests/test_martingale.py tests/test_risk.py`

Expected: all targeted tests pass.

- [ ] **Step 5: Commit the self-contained snapshot work**

```bash
git add scripts/probe_martingale_schema.py scripts/build_martingale_snapshot.py app/martingale.py tests/test_martingale.py docs/analysis/2026-07-16-martingale-schema.md
git commit -m "feat: add martingale schema probe and snapshot details"
```

### Task 2: Request models and reusable analysis context

**Files:**
- Modify: `app/models.py`
- Modify: `app/service.py`
- Create: `tests/test_service_context.py`

**Interfaces:**
- `AnalysisRules.excluded_martingale_levels: list[Literal["extreme", "high", "medium", "low"]]` defaults to `['extreme', 'high', 'medium']`.
- `SweepRequest` contains `analysis: AnalysisRequest`, `grid: dict[str, list[Any]]`, `objective`, and optional `max_misjudge_cost`.
- `BookAnalyticsRequest` contains `analysis: AnalysisRequest`, `abook_accounts: list[AccountKey]`, and `hedge_cost_bps` between 0 and 5.
- `prepare_analysis_context(rows, daily_rows, overview_rows, overview_daily_rows, selection_start, selection_end, validation_start, validation_end) -> AnalysisContext` returns immutable-ish materialized data used by all later endpoints.
- `classify_accounts(context, rules, personal_candidate_logins, martingale_snapshot) -> list[dict]` is pure with respect to its inputs.

- [ ] **Step 1: Add failing model and classification tests**

```python
def test_rules_default_to_blocking_three_martingale_levels():
    rules = AnalysisRules()
    assert rules.excluded_martingale_levels == ["extreme", "high", "medium"]

def test_martingale_block_wins_over_personal_candidate_override():
    context = make_context_for_account(platform="mt5", login=7, profitable_selection=True)
    snapshot = ready_snapshot_for("mt5", 7, "high")
    account = classify_accounts(context, AnalysisRules(), {7}, snapshot)[0]
    assert account["cohort"] != "abook_candidate"
    assert account["selection_source"] == "martingale_blocked"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_service_context.py`

Expected: FAIL on missing model field and missing context/classification interfaces.

- [ ] **Step 3: Implement models and extract context/classification**

Move the existing account aggregation and classification calculations behind the two explicit interfaces without changing the old payload shape. Keep `build_two_stage_payload` as a compatibility wrapper. Add a helper that returns `martingale_blocked` only when the snapshot is `ready` and the record risk level is in the selected levels; preserve `bbook_candidate`/`observation` population for display.

- [ ] **Step 4: Run focused service tests and full regression**

Run: `.venv/bin/python -m pytest -q tests/test_service_context.py tests/test_service.py tests/test_two_stage_analysis.py`

Expected: all pass and old payload assertions remain unchanged.

- [ ] **Step 5: Commit the context boundary**

```bash
git add app/models.py app/service.py tests/test_service_context.py
git commit -m "refactor: extract reusable abook analysis context"
```

### Task 3: Wire martingale into the analysis API and account details

**Files:**
- Modify: `app/main.py`
- Modify: `app/service.py`
- Modify: `app/models.py`
- Create: `tests/test_api_martingale.py`

**Interfaces:**
- `POST /api/abook/analysis` adds `martingale` summary and includes martingale fields on account rows.
- `GET /api/abook/accounts/{platform}/{login}` adds `martingale` with snapshot status and optional record.
- `build_martingale_filter(request) -> MartingaleSnapshot` remains the single snapshot loader.

- [ ] **Step 1: Write failing API tests**

```python
def test_analysis_reports_martingale_status_and_blocks_personal_candidate(monkeypatch):
    monkeypatch.setenv("ABOOK_MARTINGALE_SNAPSHOT_PATH", str(make_ready_snapshot(login=7, level="high")))
    response = client.post("/api/abook/analysis", json={"personal_candidate_list": True})
    assert response.status_code == 200
    body = response.json()
    account = next(item for item in body["accounts"] if item["login"] == 7)
    assert account["selection_source"] == "martingale_blocked"
    assert body["martingale"]["status"] == "ready"
```

- [ ] **Step 2: Run the test and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_api_martingale.py`

Expected: FAIL because the API has no martingale summary or block integration.

- [ ] **Step 3: Implement API wiring**

Load the snapshot beside the risk snapshot, enrich the overview and filtered rows, pass the snapshot and selected levels into classification, and add account detail lookup. Do not filter the population rows used for company baseline; only final Abook classification is hard-blocked.

- [ ] **Step 4: Run API regression**

Run: `.venv/bin/python -m pytest -q tests/test_api.py tests/test_api_martingale.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/service.py app/models.py tests/test_api_martingale.py
git commit -m "feat: enforce martingale exclusion in abook analysis"
```

### Task 4: Parameter sweep endpoint

**Files:**
- Create: `app/sweep.py`
- Modify: `app/main.py`
- Modify: `app/service.py`
- Create: `tests/test_sweep.py`

**Interfaces:**
- `expand_rule_grid(grid: dict[str, list[Any]], rules: AnalysisRules) -> list[AnalysisRules]` validates fields and returns at most 500 rule objects.
- `evaluate_sweep(context, base_rules, grid, objective, max_misjudge_cost) -> dict` returns `results`, `combinations`, `objective`, and `guardrails`.
- `POST /api/abook/sweep` takes `SweepRequest` and uses one repository fetch for monthly rows and one for daily rows.

- [ ] **Step 1: Write failing tests for grid validation and metrics**

```python
def test_sweep_rejects_more_than_500_combinations():
    with pytest.raises(ValueError, match="500"):
        expand_rule_grid({"min_win_rate": [0.4] * 501}, AnalysisRules())

def test_sweep_reports_validation_increment_and_misjudge_cost():
    result = evaluate_sweep(context_with_one_profitable_and_one_losing_account(), AnalysisRules(),
                            {"min_win_rate": [0.5]}, "validation_increment", None)
    row = result["results"][0]
    assert row["abook_core"] == 1
    assert row["misjudge_cost"] == 25.0
```

- [ ] **Step 2: Run targeted tests and observe failure**

Run: `.venv/bin/python -m pytest -q tests/test_sweep.py`

Expected: FAIL because sweep helpers and endpoint do not exist.

- [ ] **Step 3: Implement grid expansion and endpoint**

Use `itertools.product`, copy `AnalysisRules` for each combination, compute metrics from the same context, sort by the requested objective, reject a missing cost cap for `increment_with_cost_cap`, and mark `sample_warning` for fewer than 30 active validation accounts.

- [ ] **Step 4: Run sweep and full service tests**

Run: `.venv/bin/python -m pytest -q tests/test_sweep.py tests/test_service.py tests/test_two_stage_analysis.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/sweep.py app/main.py app/service.py tests/test_sweep.py
git commit -m "feat: add in-memory abook parameter sweep"
```

### Task 5: Misjudge analysis, selection funnel, personal comparison, and CSV export

**Files:**
- Modify: `app/service.py`
- Create: `app/exports.py`
- Modify: `app/main.py`
- Create: `tests/test_exports.py`
- Extend: `tests/test_two_stage_analysis.py`, `tests/test_api.py`

**Interfaces:**
- `build_misjudge_summary(accounts) -> dict` returns Abook loss list/total and Bbook profitable list with flags.
- `build_selection_funnel(accounts, eligible_accounts) -> dict` returns ordered stages and drop reasons.
- `render_abook_csv(accounts) -> str` returns UTF-8 BOM CSV with stable headers.
- `GET /api/abook/export` returns `StreamingResponse` with `text/csv; charset=utf-8`.

- [ ] **Step 1: Write failing tests**

```python
def test_misjudge_cost_is_sum_of_validation_losses_only():
    summary = build_misjudge_summary([abook_validation_loss(-40), abook_validation_profit(30)])
    assert summary["abook_loss_total"] == 40.0
    assert [row["login"] for row in summary["abook_losses"]] == [1]

def test_export_contains_only_final_abook_and_utf8_bom():
    csv_text = render_abook_csv([final_abook_account(login=7)])
    assert csv_text.startswith("\\ufeff")
    assert "platform,login" in csv_text
    assert "7" in csv_text
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_exports.py`

Expected: FAIL because the helpers and endpoint are absent.

- [ ] **Step 3: Implement summaries and export**

Build funnel counts from explicit stages (`eligible`, `sample_qualified`, `directional`, `stability_core`, `leverage_passed`, `non_martingale`, `abook_core`), keep each stage’s dropped account keys and reason codes, and add personal-list on/off comparison using the same context. Serialize only `cohort == 'abook_candidate'` rows with the account group and source fields.

- [ ] **Step 4: Run targeted and full API tests**

Run: `.venv/bin/python -m pytest -q tests/test_exports.py tests/test_api.py tests/test_two_stage_analysis.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/service.py app/exports.py app/main.py tests/test_exports.py tests/test_api.py tests/test_two_stage_analysis.py
git commit -m "feat: add misjudge funnel and abook export"
```

### Task 6: Book analytics and repository aggregations

**Files:**
- Create: `app/book_analytics.py`
- Modify: `app/queries.py`
- Modify: `app/repository.py`
- Modify: `app/main.py`
- Create: `tests/test_book_analytics.py`

**Interfaces:**
- `split_books(accounts, abook_keys) -> tuple[list[dict], list[dict]]` returns Abook and display Bbook, and asserts the key sets partition the supplied population.
- `calculate_hedge_sensitivity(abook_accounts, validation_turnover, base_increment, hedge_cost_bps) -> dict` returns cost, after-cost increment, and break-even bps.
- `build_book_analytics(context, accounts, abook_keys, hedge_cost_bps, symbol_rows) -> dict` returns `pnl_structure`, `user_structure`, `risk_exposure`, and `routing_quality`.
- `POST /api/abook/book-analytics` returns the above and carries `coverage`/`sample_warning`.

- [ ] **Step 1: Write failing unit tests for set difference and cost math**

```python
def test_bbook_is_population_minus_abook():
    abook, bbook = split_books(population_accounts(3), {("mt5", 1)})
    assert {account_key(row) for row in abook} == {("mt5", 1)}
    assert {account_key(row) for row in bbook} == {("mt5", 2), ("mt5", 3)}

def test_hedge_cost_reduces_increment_and_reports_break_even_bps():
    result = calculate_hedge_sensitivity([{"validation": {"turnover": 100000}}], 100000, 1000, 2.0)
    assert result["hedge_cost"] == 20.0
    assert result["after_cost_increment"] == 980.0
    assert result["break_even_bps"] == 100.0
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_book_analytics.py`

Expected: FAIL because the Book analytics module is absent.

- [ ] **Step 3: Implement pure Book analytics**

Use existing account validation/selection metrics for P&L distributions, drawdowns, concentration, styles and transitions. Use account-day rows for turnover and daily hit curves. Add ClickHouse queries for symbol aggregation and daily turnover with a small Abook key predicate; when the repository fixture lacks those methods, use empty aggregates while preserving response shape.

- [ ] **Step 4: Add endpoint and verify API behavior**

Run: `.venv/bin/python -m pytest -q tests/test_book_analytics.py tests/test_api.py`

Expected: all pass, including `hedge_cost_bps=5` validation and population/Abook/Bbook partition assertions.

- [ ] **Step 5: Commit**

```bash
git add app/book_analytics.py app/queries.py app/repository.py app/main.py tests/test_book_analytics.py
git commit -m "feat: add book analytics and hedge sensitivity"
```

### Task 7: Vite Vue3 dashboard rebuild

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/style.css`
- Create: `frontend/src/components/FilterSidebar.vue`
- Create: `frontend/src/components/KpiCards.vue`
- Create: `frontend/src/components/BookPerformance.vue`
- Create: `frontend/src/components/MisjudgeAnalysis.vue`
- Create: `frontend/src/components/SelectionFunnel.vue`
- Create: `frontend/src/components/SweepPanel.vue`
- Create: `frontend/src/components/AccountsTable.vue`
- Create: `frontend/src/components/AccountDrawer.vue`
- Modify: `tests/test_frontend_contract.py`
- Replace generated: `static/index.html`, `static/app.js`, `static/styles.css`

**Interfaces:**
- `App.vue` owns `AnalysisRequest`, current payload, active tab, selected Abook keys, and lazy Book analytics state.
- Components receive typed props and emit `apply-rules`, `open-account`, `run-sweep`, `export-list`, and `select-tab` events.
- Build command is `cd frontend && npm run build`, output directory is `../static`.

- [ ] **Step 1: Add frontend contract tests before implementation**

Extend the contract tests to require `Vite`, `martingale`, `sweep`, `misjudge`, `funnel`, `book-analytics`, six tab labels, and the build output markers. Keep the existing assertions for legacy payload fields.

- [ ] **Step 2: Run contract tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_frontend_contract.py`

Expected: FAIL because `frontend/` and the new generated markers do not exist.

- [ ] **Step 3: Scaffold the Vite application and typed API client**

Create `package.json` scripts with `"build": "vite build --outDir ../static"` and dependencies for Vue, ECharts, Tailwind and Vite. Define request/response types, use `fetch` for `/api/abook/analysis`, `/api/abook/sweep`, `/api/abook/export`, `/api/abook/book-analytics`, and render the status/error states.

- [ ] **Step 4: Implement the dashboard components**

Build the dark financial layout, responsive two-column sidebar/content shell, KPI cards, funnel, misjudge lists, six tabs, ECharts charts, virtualized/paginated account table, CSV action and account drawer. The sidebar must keep the Apply button reachable with advanced rules open and show the martingale warning when status is not `ready`.

- [ ] **Step 5: Build and run contract tests**

Run: `cd frontend && npm run build && cd .. && .venv/bin/python -m pytest -q tests/test_frontend_contract.py`

Expected: Vite exits 0, `static/` contains the generated assets, and all frontend contract tests pass.

- [ ] **Step 6: Commit frontend**

```bash
git add frontend static tests/test_frontend_contract.py
git commit -m "feat: rebuild abook dashboard with vite vue3"
```

### Task 8: End-to-end verification and real-data evidence

**Files:**
- Modify: `README.md` with build/run instructions and snapshot status behavior.
- Create: `docs/analysis/2026-07-16-abook-upgrade-validation.md`.

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest -q`

Expected: zero failures; capture the exact passed count and any existing dependency warning.

- [ ] **Step 2: Build the frontend from a clean command**

Run: `cd frontend && npm run build`

Expected: exit code 0 and generated `static/index.html` referencing compiled assets.

- [ ] **Step 3: Start the dashboard and check HTTP boundaries**

Run: `./run_dashboard.sh` in a PTY, then request `/api/health`, `/`, `/assets/app.js`, and `/assets/styles.css` with a local HTTP client. Stop the server after checks.

Expected: health JSON has `status: ok`, homepage is HTML, and generated assets return 200.

- [ ] **Step 4: Run Phase 0 probe and snapshot when ClickHouse is configured**

Run: `.venv/bin/python scripts/probe_martingale_schema.py` and `.venv/bin/python scripts/build_martingale_snapshot.py --selection-start 2026-05-01 --selection-end 2026-06-30`.

Expected: either a valid schema/snapshot summary is written, or a clear configuration/connection error is recorded without corrupting an existing snapshot.

- [ ] **Step 5: Validate the default analysis contract**

Use a TestClient fixture for no-ClickHouse and a connected repository when available; verify `martingale.status`, `selection.counts`, `misjudge`, `funnel`, `book_performance`, `daily_book_series`, and six frontend tabs. Record before/after Abook count and validation increment when real rows are available.

- [ ] **Step 6: Commit documentation and report evidence**

```bash
git add README.md docs/analysis/2026-07-16-abook-upgrade-validation.md
git commit -m "docs: record abook upgrade validation"
```

## Plan Self-Review

- Spec coverage: Phase 0 is Task 1; Phase 1 is Tasks 1–3; Phase 2 is Task 2; Phase 3 is Task 4; Phase 4 is Task 5; Phase 5 is Task 6; Phase 6 is Task 7; verification and real-data evidence are Task 8.
- Placeholder scan: no `TBD`, `TODO`, or unnamed future work is used; every task names files, interfaces, tests, commands, and expected outcomes.
- Type consistency: `AnalysisRules`, `SweepRequest`, `BookAnalyticsRequest`, `AnalysisContext`, `classify_accounts`, `expand_rule_grid`, `evaluate_sweep`, `split_books`, `calculate_hedge_sensitivity`, `build_book_analytics`, and `render_abook_csv` are the shared names used by later tasks.
- Scope check: all phases are intentionally in one release because the requested success criterion is a functioning final website; the implementation remains gated by independently testable tasks.
