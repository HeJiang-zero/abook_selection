# Account Drawer Stability and Bbook Phase P&L Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the account-detail drawer render crash and expose Bbook selection/validation profit, loss, and net P&L in overview and user-structure views.

**Architecture:** Reuse the existing account-level P&L summaries in the overview and the existing book-analytics `phase_summary` payload in user structure. Keep the change frontend-only for display and template stability; preserve backend data semantics.

**Tech Stack:** Vue 3 + TypeScript + Vite, FastAPI/Python analytics, pytest, pnpm.

## Global Constraints

- Keep Bbook `盈利金额` and `亏损金额` as signed customer-net-P&L components; do not replace them with company profit.
- Keep the fix compatible with the existing static Vite build served by FastAPI.
- Do not change filter defaults or martingale routing behavior.
- Follow test-first order: add and run failing tests before production edits.

### Task 1: Add regression tests for drawer and Bbook metrics

**Files:**
- Modify: `tests/test_frontend_contract.py`
- Modify: `tests/test_book_analytics.py`

**Interfaces:**
- Tests assert the source-level Vue contract and the existing analytics payload fields.

- [ ] **Step 1: Add a failing drawer-template contract test**

  Assert that `AccountDrawer.vue` contains a `<template v-for="item in deExtremeItems"` wrapper and no `<tr v-for="item in deExtremeItems" ... v-if` combination.

- [ ] **Step 2: Add failing Bbook display-contract assertions**

  Assert that `AbookAnalysis.vue` exposes a Bbook summary and that
  `BookPerformance.vue` contains the explicit `盈利金额`, `亏损金额`, and
  `净 P&L` labels.

- [ ] **Step 3: Strengthen the analytics regression case**

  In `test_book_analytics_reports_period_profitability_and_distribution`,
  assert Bbook validation `positive_pnl`, `negative_pnl`, and `net_pnl` values
  alongside the existing Bbook selection loss assertion.

- [ ] **Step 4: Run the focused tests and confirm RED**

  Run:

  ```bash
  .venv/bin/pytest tests/test_frontend_contract.py tests/test_book_analytics.py -q
  ```

  Expected: failures from the missing overview/display contracts; the backend
  field assertions should continue to pass because the API already supplies
  the fields.

### Task 2: Fix the AccountDrawer render crash

**Files:**
- Modify: `frontend/src/components/AccountDrawer.vue:126-129`

**Interfaces:**
- Consumes: `detail.de_extreme` and the existing `deExtremeItems` list.
- Produces: a stable table render with conditional rows.

- [ ] **Step 1: Move the loop to a template wrapper**

  Use:

  ```vue
  <tbody>
    <template v-for="item in deExtremeItems" :key="item[0]">
      <tr v-if="detail.de_extreme?.[item[0]] !== undefined">
        <td>{{ item[1] }}</td>
        <td :class="number(detail.de_extreme?.[item[0]]) >= 0 ? 'positive' : 'negative'">
          {{ format(detail.de_extreme?.[item[0]]) }}
        </td>
      </tr>
    </template>
  </tbody>
  ```

- [ ] **Step 2: Run the focused frontend contract test**

  Run:

  ```bash
  .venv/bin/pytest tests/test_frontend_contract.py -q
  ```

  Expected: the drawer contract passes.

### Task 3: Add Bbook phase summaries to overview

**Files:**
- Modify: `frontend/src/components/AbookAnalysis.vue`

**Interfaces:**
- Consumes: `props.data.accounts` account-level selection/validation client-net-P&L.
- Produces: overview cards for both Abook and Bbook with phase profit, loss, and net values.

- [ ] **Step 1: Add a reusable book summary computed value**

  Filter accounts by `book`, call the existing `phaseSummary` for both phases,
  and expose `bookSummaries` keyed by `abook` and `bbook`.

- [ ] **Step 2: Render the Bbook summary using explicit labels**

  Keep the existing Abook cards and add a Bbook section with the same two phase
  cards and the labels `盈利金额`, `亏损金额`, and `净 P&L`.

- [ ] **Step 3: Run focused source and analytics tests**

  Run the focused pytest command from Task 1 and expect it to pass.

### Task 4: Make user-structure phase amounts explicit

**Files:**
- Modify: `frontend/src/components/BookPerformance.vue`

**Interfaces:**
- Consumes: `analytics.pnl_structure[book].phase_summary[phase]`.
- Produces: clear phase cards for both books with positive, negative, and net P&L.

- [ ] **Step 1: Replace the compact phase summary line**

  In each book/phase card, render explicit rows for `positive_pnl`,
  `negative_pnl`, and `net_pnl`, preserving account counts, PF, and win rate.

- [ ] **Step 2: Run the frontend contract tests**

  Run:

  ```bash
  .venv/bin/pytest tests/test_frontend_contract.py -q
  ```

  Expected: all frontend contract tests pass.

### Task 5: Build and verify the complete change

**Files:**
- Generated: `static/app.js`
- Generated: `static/styles.css` if Vite updates it.

- [ ] **Step 1: Run all Python tests**

  Run:

  ```bash
  .venv/bin/pytest -q
  ```

- [ ] **Step 2: Build the frontend**

  Run:

  ```bash
  cd frontend && pnpm build
  ```

- [ ] **Step 3: Re-run the test suite after build output generation**

  Run `.venv/bin/pytest -q` and expect PASS.

- [ ] **Step 4: Verify in the user Chrome tab**

  Reload the local app, confirm the overview contains Bbook selection and
  validation profit/loss/net rows, open 用户结构 and confirm both book phase
  cards contain the same three values, then click an Abook user and wait at
  least three seconds to confirm the drawer remains visible and no console
  error is emitted.
