# Bbook Leakage Reasons Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show readable Bbook routing reasons for validation-profitable leakage users and let each row open the existing account analysis drawer without adding page-load detail queries.

**Architecture:** Build `bbook_reason_tags` on the existing account routing payload, pass it through `build_misjudge_summary`, and join leakage rows to the full `accounts` array in `AbookAnalysis.vue`. Reuse the existing `openAccount` callback and `AccountDrawer`; no new API endpoint or bulk detail query is introduced.

**Tech Stack:** Python/FastAPI service functions, pytest contract tests, Vue 3 + TypeScript, Vite.

## Global Constraints

- Keep the leakage population as validation-period customer net P&L greater than 100.
- Preserve existing account-detail request, request-id race protection, and backdrop-only drawer close behavior.
- Do not add a user-detail request during initial analysis or Book tab loading.
- Always return at least one readable Bbook reason tag when an account is routed to Bbook.

---

### Task 1: Add backend reason tags

**Files:**
- Modify: `app/service.py` near `build_misjudge_summary` and account construction.
- Test: `tests/test_service_context.py`.

**Interfaces:**
- Produces account field `bbook_reason_tags: list[str]` and leakage field with the same name.

- [ ] **Step 1: Write the failing test**

Add a test that passes a Bbook account with confirmed high-risk martingale, failed Abook rules, and a leverage flag to `build_misjudge_summary`, then asserts the returned leakage row contains readable tags including `确认马丁`, `Abook规则未通过`, and `杠杆 P95 超限`.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_service_context.py -k bbook_reason_tags`

Expected: FAIL because `bbook_reason_tags` is absent.

- [ ] **Step 3: Implement the minimal backend mapping**

Add a focused helper that maps `martingale_blocked`, `martingale_hard_blocked`, `martingale_risk_level`, `martingale_status`, `selection_source`, `abook_rules_pass`, and `selection_flags` to Chinese labels. Add the resulting list to every account in `build_two_stage_payload`, and copy it into `build_misjudge_summary` items. Use `Bbook（未通过 Abook 路由）` only when no more specific tag exists.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_service_context.py -k bbook_reason_tags`

Expected: PASS.

- [ ] **Step 5: Commit the backend change**

Run: `git add app/service.py tests/test_service_context.py && git commit -m "feat: expose bbook routing reason tags"`

### Task 2: Add leakage table labels and drawer reuse

**Files:**
- Modify: `frontend/src/components/AbookAnalysis.vue`.
- Modify: `frontend/src/types.ts`.
- Test: `tests/test_frontend_contract.py`.

**Interfaces:**
- Consumes `misjudge.bbook_profitable[].bbook_reason_tags` and `accounts` keyed by `(platform, login)`.
- Produces clickable leakage rows that emit the existing `open` event with a full `AccountRow` when available.

- [ ] **Step 1: Write the failing frontend contract test**

Assert that `AbookAnalysis.vue` contains a Bbook reason column, renders `bbook_reason_tags`, and emits `open` from the leakage table row.

- [ ] **Step 2: Run the focused contract test and verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_contract.py -k bbook_leakage`

Expected: FAIL because the leakage table has no reason tags or click handler.

- [ ] **Step 3: Implement the minimal UI behavior**

Create a computed account lookup by platform/login and map sorted leakage rows to the full account object. Add a reason-tag cell and `@click="emit('open', leakageAccount(row))"` to each row. Keep the existing P&L columns, sorting, and >100 filter unchanged. Add `bbook_reason_tags?: string[]` to `AccountRow`.

- [ ] **Step 4: Run the focused contract test and verify it passes**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_contract.py -k bbook_leakage`

Expected: PASS.

- [ ] **Step 5: Commit the frontend change**

Run: `git add frontend/src/components/AbookAnalysis.vue frontend/src/types.ts tests/test_frontend_contract.py && git commit -m "feat: make bbook leakage users actionable"`

### Task 3: Regression verification

**Files:**
- Modify: `static/app.js` via the existing Vite build output.

- [ ] **Step 1: Run all Python tests**

Run: `PYTHONPATH=. .venv/bin/pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Build the frontend**

Run from `frontend/`: `PATH=/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH /Users/jianghe/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm build`

Expected: Vite production build succeeds and regenerates `static/app.js`.

- [ ] **Step 3: Verify no extra bulk detail request was added**

Run: `rg -n "fetchAccountDetail|loadAnalysis|loadBook" frontend/src/components/AbookAnalysis.vue frontend/src/App.vue`

Expected: only the existing `open` event path in `App.vue` calls `fetchAccountDetail`; `AbookAnalysis.vue` does not call the API.
