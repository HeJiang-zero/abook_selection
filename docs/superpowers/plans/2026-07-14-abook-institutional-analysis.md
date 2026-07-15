# Abook Institutional Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add institution-grade user stability metrics and out-of-sample validation to the Abook dashboard, then improve chart interaction and account-table usability.

**Architecture:** Keep ClickHouse responsible for account-month and account-level daily aggregates; keep Python responsible for scoring, confidence intervals, cohort assignment, and JSON shaping. Keep July completely out of selection scoring. Extend the existing Vue 3/ECharts page with derived cards, tooltips, filters, pagination, and an account drawer that consumes the same payload.

**Tech Stack:** FastAPI, Pydantic, clickhouse-connect, ClickHouse SQL, Vue 3 CDN, ECharts 5, pytest/httpx.

## Global Constraints

- Use `risk.ods_mt5_users FINAL` as the account population and exclude `is_deleted = 1`.
- Exclude account groups containing `test` case-insensitively when the switch is enabled.
- Use `action IN (0, 1)` for trading P&L and keep `action IN (2, 3)` funding separate.
- Do not use validation-period data to calculate selection scores or cohorts.
- Do not call theoretical Abook profit real external hedging profit.
- All JSON must serialize finite numbers; use `null` only for no-loss PF.

---

### Task 1: Add failing backend tests for stability metrics and source coverage

**Files:**
- Modify: `tests/test_two_stage_analysis.py`
- Modify: `tests/test_queries.py`

**Interfaces:**
- Consumes: existing `build_two_stage_payload` and `build_analysis_query` interfaces.
- Produces: executable expectations for `stability`, `confidence_tier`, `selection_flags`, source coverage, and daily quality fields.

- [x] Add a fixture with two selection months, one validation month, daily quality aggregates, and a concentrated-profit account.
- [x] Assert the account with a single dominant positive day is not `Abook Core` even when total P&L and PF pass.
- [x] Assert a consistent account gets a nonzero stability score and `confidence_tier` based on sample thresholds.
- [x] Assert the payload contains source minimum/maximum dates and marks May as partial when the source starts on May 15.
- [x] Assert the query contains the account daily aggregation and source coverage CTEs.
- [x] Run `pytest tests/test_two_stage_analysis.py tests/test_queries.py -q` and confirm the new expectations fail before implementation.

### Task 2: Extend ClickHouse query with daily quality and source coverage

**Files:**
- Modify: `app/queries.py`
- Test: `tests/test_queries.py`

**Interfaces:**
- Consumes: existing platform, date, group, Login, and test-account filters.
- Produces: monthly rows with repeated account-level fields `daily_*` and `source_*`.

- [x] Add `account_daily` from `deal_daily` with active days, positive/negative days, positive/negative sums, max positive day, daily standard deviation, and absolute-day sum.
- [x] Add `trade_source_coverage` and `deal_source_coverage` CTEs filtered by selected platforms and valid deals.
- [x] Cross join the aggregates into the existing account-month result without changing account-month grain.
- [x] Preserve `uniqExact(login)` population count and platform/login de-duplication.
- [x] Run query contract tests and keep SQL parameter placeholders valid for clickhouse-connect.

### Task 3: Implement stable cohort scoring and validation diagnostics

**Files:**
- Modify: `app/service.py`
- Modify: `app/models.py` if new thresholds are configurable.
- Test: `tests/test_two_stage_analysis.py`

**Interfaces:**
- Consumes: account-month rows from Task 2 and `AnalysisRules`.
- Produces: per-account `stability`, `confidence_tier`, `selection_flags`, `cohort`, `selection_quality`; aggregate `stability_overview`, source coverage, and validation diagnostics.

- [x] Add Decimal-safe helpers for standard deviation, Wilson intervals, bounded ratios, and finite JSON values.
- [x] Calculate monthly consistency, worst month, profit concentration, daily rate confidence, expectancy, payoff ratio, drawdown ratio, and behavior metrics from selection rows.
- [x] Calculate an explainable 0–100 selection score using selection-only features; never read validation metrics in scoring.
- [x] Assign Core, Watch, or Observation cohorts using hard eligibility gates plus the score and confidence tier.
- [x] Add validation direction agreement and selection-vs-validation P&L correlation without changing cohorts.
- [x] Keep all account rows for aggregate reconciliation, but return only nonzero three-month P&L accounts in the detail table.
- [x] Run the targeted tests and then all service tests.

### Task 4: Add interaction-ready API fields and front-end controls

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: Task 3 payload fields.
- Produces: summary cards, stability breakdown, source warnings, tooltips, account search/filter/sort/pagination, and drawer metrics.

- [x] Add top cards for Core count, validation success rate, theoretical risk protection, and confidence/sample warning.
- [x] Add ECharts `tooltip.trigger = 'axis'`, `axisPointer.type = 'cross'`, series values, and explicit phase labels to all charts.
- [x] Add client-side account search, cohort filter, confidence filter, sort selector, and pagination with a bounded page size.
- [x] Add account-row stability score, confidence tier, concentration, drawdown, and sample columns while keeping the default table compact.
- [x] Add drawer sections for month-by-month P&L and stability/behavior metrics.
- [x] Preserve loading, error, empty, partial-month, and theoretical-profit notices.
- [x] Update contract tests for every required control and tooltip configuration.

### Task 5: Verify with unit tests, live ClickHouse, and browser inspection

**Files:**
- Modify: `README.md` with metric definitions and run instructions.
- Test: all `tests/*.py`.

- [x] Run `.venv/bin/python -m pytest -q`.
- [x] Run `.venv/bin/python -m compileall -q app tests`.
- [x] Start the API with the password read from `clickhouse.md`, then check `/api/health`, `/api/abook/filters`, and `/api/abook/analysis`.
- [x] Reconcile unique population count, cohort totals, transition totals, monthly totals, and company-profit sign conventions on live data.
- [x] Open the dashboard in the browser and verify charts have nonzero dimensions, tooltips are configured, filters apply, table pagination changes rows, and the account drawer opens.
- [x] Stop the local server and report any source-coverage or external-Abook limitations.
