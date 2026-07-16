# Abook/Bbook Routing Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every account end in exactly one of Abook or Bbook, route every detected Martingale account to Bbook, restore the daily-profit/monthly-profit-contribution rule, replace peak leverage with the 95th percentile leverage, remove the parameter-sweep window, and verify the live dashboard.

**Architecture:** Keep selection and validation rows in the service layer, but replace business cohorts with a final `book` field containing only `abook` or `bbook`. Preserve selection evidence, failure reasons, Martingale level, and source as audit metadata. Compute daily-profit concentration and leverage p95 from the existing in-memory account-period rows, while the Martingale snapshot remains a local ClickHouse-derived artifact.

**Tech Stack:** FastAPI, Pydantic, Python `Decimal`, ClickHouse, pytest, Vue 3, TypeScript, Vite, ECharts, shell smoke tests, in-app browser verification.

## Global Constraints

- Final business allocation is exactly `Abook` or `Bbook`; `observation`, `*_candidate`, and `Core + observation` are not business groups.
- Any detected Martingale level (`low`, `medium`, `high`, or `extreme`) is routed to Bbook; Martingale always overrides the personal list.
- The restored concentration rule is maximum single-day profit divided by that month’s total profit, evaluated per selection month and reduced to the worst month.
- The leverage rule uses the user leverage ratio 95th percentile, not the maximum/peak leverage ratio.
- Bbook company P&L is the negative of customer P&L; Abook customer P&L is not presented as company P&L.
- Bbook leakage totals use all qualifying accounts; the UI table displays only company-loss amounts greater than USD 100 and is collapsible.
- The parameter-sweep window and its frontend entry point are removed.
- `data/martingale_snapshot.json` and other local snapshots remain ignored and are never committed.

---

### Task 1: Lock calculation and routing contracts with failing tests

**Files:**
- Modify: `/Users/jianghe/abook_hedging/tests/test_two_stage_analysis.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_martingale.py`
- Create: `/Users/jianghe/abook_hedging/tests/test_routing_contract.py`

**Interfaces:**
- Tests establish `book in {"abook", "bbook"}` for every returned account.
- Tests establish daily monthly contribution as `max(daily_profit) / sum(month_profit)` for each month, with the maximum across months used by Abook eligibility.
- Tests establish personal-list precedence below Martingale precedence.
- Tests establish leverage p95 is the value used by the rule and the old peak value is not used.

- [ ] **Step 1: Write failing unit tests** for the new rule fields, two-book output, Martingale routing precedence, concentration edge cases, and p95 leverage.
- [ ] **Step 2: Run the focused tests** with `.venv/bin/python -m pytest tests/test_routing_contract.py tests/test_two_stage_analysis.py tests/test_martingale.py -q`; expected result is failure because the new fields and route contract do not exist yet.

### Task 2: Implement daily-profit/monthly-profit concentration and leverage p95

**Files:**
- Modify: `/Users/jianghe/abook_hedging/app/models.py`
- Modify: `/Users/jianghe/abook_hedging/app/service.py`
- Modify: `/Users/jianghe/abook_hedging/app/queries.py` only if the existing leverage rows do not contain enough observations for an in-memory percentile

**Interfaces:**
- Add `AnalysisRules.max_monthly_profit_contribution: float`, default `0.60`, range `(0, 1]`.
- Replace `max_peak_leverage_ratio` with `max_leverage_p95_ratio` while accepting no new peak-based business decision.
- Expose `max_daily_profit_month_contribution` in selection metrics and include `profit_concentration` in rule flags when the threshold fails.

- [ ] **Step 1: Implement failing-test-sized helpers** for per-month daily positive-profit concentration and a deterministic percentile-95 calculation.
- [ ] **Step 2: Run the focused tests** and confirm the new helpers fail only before implementation.
- [ ] **Step 3: Implement the helpers using `Decimal`**, treating a month with no positive profit as zero concentration and using the existing daily rows grouped by `YYYY-MM`.
- [ ] **Step 4: Wire the concentration threshold into both the direct Abook rule and stability assessment.** It must be applied to Abook eligibility; Bbook is the final fallback and does not require a separate negative-direction rule.
- [ ] **Step 5: Wire leverage p95 into `_leverage_filter_pass`, account metrics, and API serialization; remove peak leverage from the decision path while keeping legacy display aliases only when needed for old clients.
- [ ] **Step 6: Run focused tests** and confirm all calculation tests pass.

### Task 3: Make the Martingale snapshot inclusive and route all detected levels to Bbook

**Files:**
- Modify: `/Users/jianghe/abook_hedging/scripts/build_martingale_snapshot.py`
- Modify: `/Users/jianghe/abook_hedging/app/martingale.py`
- Modify: `/Users/jianghe/abook_hedging/app/models.py`
- Modify: `/Users/jianghe/abook_hedging/app/service.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_martingale.py`

**Interfaces:**
- Keep the five layer hit details and add `detection_mode` (`confirmed` or `expanded`) to snapshot records.
- Use `L1 AND (L2 OR L3 OR L4 OR L5)` as the expanded Martingale detection gate; retain the current stricter `L1 AND L3 AND L4` as the confirmed mode.
- Default `excluded_martingale_levels` is all four levels: `extreme`, `high`, `medium`, `low`.
- A ready snapshot match at any excluded level sets `book="bbook"` and `routing_reason="martingale"`, even when the account is in the personal list.
- Missing/stale snapshots set all accounts to Bbook for safety and expose the snapshot status.

- [ ] **Step 1: Add failing tests** for all four levels, the expanded gate, missing/stale snapshot safety routing, and personal-list conflict.
- [ ] **Step 2: Run the Martingale tests** and confirm they fail against the current three-level default and observation fallback.
- [ ] **Step 3: Update the snapshot SQL** to emit both confirmed and expanded detection counts, retain layer definitions, and classify expanded-only matches as low severity unless a stricter tier is met.
- [ ] **Step 4: Update the model defaults and service precedence** so any detected level is Bbook and no detected account can be promoted by personal candidates.
- [ ] **Step 5: Rebuild the local snapshot for the current selection period** and record the new level counts without committing the JSON.
- [ ] **Step 6: Run Martingale and routing tests** and verify the account-level output contains only Abook/Bbook.

### Task 4: Replace cohort summaries with two-book summaries and correct company signs

**Files:**
- Modify: `/Users/jianghe/abook_hedging/app/service.py`
- Modify: `/Users/jianghe/abook_hedging/app/main.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_two_stage_analysis.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_book_analytics.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_export.py`

**Interfaces:**
- `accounts[*].book` is the only final allocation field and is either `abook` or `bbook`.
- Validation, book performance, monthly summaries, book analytics, export, and migration matrices use exactly `abook` and `bbook` keys.
- Preserve `selection_direction`, `selection_flags`, and `routing_reason` as evidence, not grouping.
- Bbook company profit/loss is `-customer_net_pnl`; Abook views show customer P&L and routing impact separately.
- Abook misjudge cost is the positive amount of Abook users who lose in validation; Bbook leakage is the negative company P&L from Bbook users who win in validation.

- [ ] **Step 1: Add failing assertions** that no response summary or account contains observation/candidate business groups and that Bbook signs are correct.
- [ ] **Step 2: Refactor `build_two_stage_payload`** to create `book` after rule evidence is computed, then derive `by_book={"abook":..., "bbook":...}`.
- [ ] **Step 3: Update selection counts, validation groups, profit impact, book performance, and book analytics** to use the two-book map only.
- [ ] **Step 4: Update the funnel** to show Abook eligibility stages and a final Abook/Bbook split, with Martingale as a Bbook reason.
- [ ] **Step 5: Keep all Bbook leakage totals in the payload**, but add a display-ready threshold field or a stable sorted list for frontend filtering.
- [ ] **Step 6: Run the full backend test suite** and fix all stale candidate/observation assertions.

### Task 5: Remove sweep UI and update filter/account/misjudge views

**Files:**
- Modify: `/Users/jianghe/abook_hedging/frontend/src/App.vue`
- Modify: `/Users/jianghe/abook_hedging/frontend/src/types.ts`
- Modify: `/Users/jianghe/abook_hedging/frontend/src/components/FilterSidebar.vue`
- Modify: `/Users/jianghe/abook_hedging/frontend/src/components/BookPerformance.vue`
- Modify: `/Users/jianghe/abook_hedging/frontend/src/components/MisjudgeAnalysis.vue`
- Modify: `/Users/jianghe/abook_hedging/frontend/src/components/SelectionFunnel.vue`
- Delete: `/Users/jianghe/abook_hedging/frontend/src/components/SweepPanel.vue`
- Modify: `/Users/jianghe/abook_hedging/frontend/src/types.ts`
- Modify: `/Users/jianghe/abook_hedging/tests/test_frontend_contract.py`

**Interfaces:**
- The filter sidebar exposes daily-profit/monthly-profit contribution and leverage p95 labels.
- The tab list contains no sweep tab or sweep import.
- Book labels are only Abook and Bbook.
- Bbook leakage is collapsible and displays rows with amount `> 100` by default, while totals remain all-account totals.

- [ ] **Step 1: Add/update frontend contract tests** for the new labels, no sweep tab, no candidate/observation labels, and the collapsible leakage markup.
- [ ] **Step 2: Run `npm run build`** from `/Users/jianghe/abook_hedging/frontend` and confirm the contract fails before the UI changes.
- [ ] **Step 3: Update the Vue state and components** to consume `book`, render the new rule inputs, and remove sweep loading/apply logic.
- [ ] **Step 4: Add the collapsible Bbook leakage table** with a `>100` display filter and clear customer/company sign labels.
- [ ] **Step 5: Build to `/Users/jianghe/abook_hedging/static`** and run frontend contract tests.

### Task 6: Documentation, live verification, and handoff

**Files:**
- Modify: `/Users/jianghe/abook_hedging/README.md`
- Modify: `/Users/jianghe/abook_hedging/docs/analysis/2026-07-16-abook-upgrade-validation.md`
- Modify: `/Users/jianghe/abook_hedging/modify.md` if restored into the root workspace; otherwise document the authoritative worktree path in the handoff

- [ ] **Step 1: Update documentation** for two-book routing, all-level Martingale Bbook routing, daily/monthly concentration, leverage p95, company sign conventions, and removed sweep UI.
- [ ] **Step 2: Run `.venv/bin/python -m pytest -q`** and require a green result.
- [ ] **Step 3: Run frontend build and static smoke checks** for `/`, `/assets/app.js`, `/assets/styles.css`, and `/api/health`.
- [ ] **Step 4: Run `./run_dashboard.sh`**, open the dashboard in the in-app browser, and verify the page renders, counts show Abook/Bbook only, and no console/runtime error blocks the page.
- [ ] **Step 5: Inspect `git diff`, stage only intended tracked files, commit, and push the verified branch.** Do not stage local snapshot JSON or `personal_candicate.csv`.

