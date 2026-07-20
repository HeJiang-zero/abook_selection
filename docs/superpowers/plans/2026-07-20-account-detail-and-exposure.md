# Account Detail And Exposure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add collapsible/sortable Abook and Bbook tables, reconstruct peak concurrent leverage from order events, and replace history-order detail with concentration, de-extreme, and Markout metrics.

**Architecture:** Keep the existing FastAPI and Vue/ECharts architecture. Add pure Python metric helpers for event reconstruction and detail aggregation, expose one enriched account-detail payload, and keep unavailable event/Markout sources as explicit nulls. Add client-side numeric table sorting and collapsible sections without changing routing rules.

**Tech Stack:** Python 3.9, FastAPI, ClickHouse SQL, pytest, Vue 3, TypeScript, ECharts, Vite.

## Global Constraints

- Do not use a nonexistent open-position table; reconstruct exposure from `risk.dwd_matched_trades` events.
- Use `abs(entry_price * current_remaining_volume)` for position value and latest positive daily balance for leverage.
- Do not show historical order rows in the account drawer.
- Do not route users using the new concentration or de-extreme metrics.
- Missing Markout/event inputs must be `null`/“暂无数据”, never fabricated zeroes.
- Run Python tests, frontend build, and `git diff --check` before handoff.

### Task 1: Pure exposure and detail metric contracts

**Files:**
- Modify: `tests/test_risk_calculation.py`
- Modify: `tests/test_service_context.py`
- Create: `tests/test_account_detail_metrics.py`

**Interfaces:**
- `reconstruct_peak_exposure(events, balances) -> dict` returns per-account `peak_exposure_values`, `peak_leverage_values`, `exposure_status`.
- `build_account_detail_payload(rows, markout_rows=None, event_rows=None) -> dict` returns `metrics`, `concentration`, `de_extreme`, `markout`, and `symbols` without a `trades` display contract.

- [ ] Write failing tests for an order opened, partially closed, and re-added; assert peak concurrent value is based on remaining quantity rather than daily closed turnover.
- [ ] Write failing tests for all seven contribution ratios and all ten de-extreme net P&Ls using a small fixture with two days, three orders, two symbols, and two hours.
- [ ] Write failing tests that separate positive-P&L and negative-P&L users for entry/exit 5-second Markout means and return null when source rows are absent.
- [ ] Run `PYTHONPATH=. .venv/bin/pytest -q tests/test_risk_calculation.py tests/test_account_detail_metrics.py` and verify the new assertions fail because the interfaces are absent.

### Task 2: Backend exposure reconstruction and detail payload

**Files:**
- Modify: `scripts/build_user_risk_snapshot.py`
- Modify: `app/risk.py`
- Modify: `app/service.py`
- Modify: `app/queries.py`
- Modify: `app/repository.py`
- Modify: `app/main.py`

**Interfaces:**
- Keep the existing snapshot output fields for compatibility, add `peak_concurrent_position_value`, `peak_concurrent_leverage_ratio`, and `concurrent_leverage_p95_ratio`.
- Account detail endpoint returns metric blocks and symbols; it no longer needs to expose a rendered history-order table.

- [ ] Implement event normalization from `entry_time`, `exit_time`, `entry_price`, `exit_price`, `volume`, `entry_deal_id`, and `exit_deal_id`, preserving platform/login identity.
- [ ] Implement event sweep that adds entry volume and subtracts exit volume per position identity, aggregates open value across positions, and matches each event timestamp to the latest positive balance.
- [ ] Add a regression version to invalidate snapshots built with the daily closed-turnover formula.
- [ ] Extend detail aggregation with daily/hourly/symbol/order positive-profit groups, concentration ratios, de-extreme net P&Ls, and optional Markout CSV loading through `ABOOK_MARKOUT_DATA_ROOT`.
- [ ] Add explicit null/status fields for missing event windows or Markout files.
- [ ] Run the Task 1 tests and then `PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py tests/test_queries.py tests/test_account_detail_metrics.py`.

### Task 3: Frontend collapse, sorting, and detail presentation

**Files:**
- Modify: `frontend/src/components/AbookAnalysis.vue`
- Modify: `frontend/src/components/AccountDrawer.vue`
- Modify: `frontend/src/types.ts`
- Modify: `tests/test_frontend_contract.py`
- Regenerate: `static/app.js`, `static/styles.css`

**Interfaces:**
- Abook and Bbook list headers expose a `details` open/closed state.
- Table headers call one numeric sort handler and show ascending/descending state.
- Drawer renders metric blocks, concentration ratios, de-extreme results, and two Markout curves; it renders no history-trade table.

- [ ] Write failing source-contract tests for Abook `<details>`, sortable headers, de-extreme labels, and absence of `历史交易明细`.
- [ ] Implement stable numeric sort by `(field, direction)` for P&L, win rate, trade count, and stability.
- [ ] Add the same sorting behavior to the Bbook leakage table where numeric columns exist.
- [ ] Replace the drawer trade table with the new metric sections and clear unavailable-data copy.
- [ ] Run `PATH=/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH pnpm run build` from `frontend/`.

### Task 4: Verification and audit notes

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-20-account-detail-and-exposure-design.md` if implementation details require clarification.

- [ ] Run `PYTHONPATH=. .venv/bin/pytest -q` and confirm zero failures.
- [ ] Run `PYTHONPATH=. .venv/bin/python -m compileall -q app scripts tests`.
- [ ] Run `git diff --check`.
- [ ] Verify the generated frontend contains sortable Abook/Bbook headers, no history-order table, and the new exposure/detail labels.
- [ ] Report that real leverage distributions require rebuilding the snapshot with a configured ClickHouse connection; do not claim live user counts from stale local data.
