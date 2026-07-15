# Predictive Selection and Validation P&L Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the dashboard judge Abook candidates by 7月样本外验证理论增量, make every submitted rule visibly auditable, and add selection-only profitability/consistency filters that improve the chance of continued validation performance without using July to select.

**Architecture:** Extend the request model and service rules with minimum win rate, minimum Profit Factor, and minimum monthly consistency. Monthly consistency is computed from the two selection months as the weaker directional month divided by the stronger directional month. The backend echoes the exact applied rules; Vue compares current inputs with the returned rules and shows whether changes are pending or applied.

**Tech Stack:** FastAPI, Pydantic, Python service aggregation, Vue 3 template, pytest, ClickHouse verification, Git/GitHub SSH remote.

## Global Constraints

- `test` and `demo` accounts remain hard-excluded in query, service, and account detail paths.
- Deals remains the canonical market P&L source.
- July is validation-only and must not be used to calculate candidate eligibility.
- All dashboard theoretical-increment displays use validation-period values.
- No external Abook execution profit is assumed; assumed Abook profit remains zero.

### Task 1: Regression Tests

**Files:**
- Modify: `tests/test_models.py`
- Modify: `tests/test_two_stage_analysis.py`
- Modify: `tests/test_frontend_contract.py`

- [ ] Add failing tests for the new rule fields and selection-only monthly consistency behavior.
- [ ] Add a frontend contract requiring validation-only increment labels and pending/applied rule status.
- [ ] Run focused tests and confirm the failures are caused by missing behavior.

### Task 2: Backend Rules and Payload

**Files:**
- Modify: `app/models.py`
- Modify: `app/main.py`
- Modify: `app/service.py`
- Modify: `README.md`

- [ ] Add `min_win_rate`, `min_profit_factor`, and `min_selection_monthly_consistency` request rules.
- [ ] Compute monthly consistency from selection `best_month_pnl` and `worst_month_pnl`, symmetrically for positive and negative directions.
- [ ] Require directional candidates to meet the consistency and win-rate rules while retaining existing PF and sample gates.
- [ ] Echo every applied rule in the response and include the consistency ratio in account/stability output.
- [ ] Preserve July as validation-only.

### Task 3: Frontend Feedback and Validation-First Display

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`

- [ ] Show all applied rule values, including win rate, PF, consistency, neutral band, concentration, and confidence thresholds.
- [ ] Show a clear pending state when form values differ from the last response, and a confirmed applied state after reload.
- [ ] Remove selection-period theoretical increment from all visible dashboard surfaces.
- [ ] Keep selection P&L as context but label the decision metric as 7月验证理论增量.

### Task 4: Verification

**Files:**
- No new production files.

- [ ] Run full pytest and compile checks.
- [ ] Run a real ClickHouse analysis and confirm no demo/test rows, finite JSON, and candidate validation summaries.
- [ ] Compare default and stricter consistency settings to verify the parameter changes the candidate set and returned rules.

### Task 5: GitHub Publish

**Files:**
- All intended workspace changes.

- [ ] Initialize or connect the local repository to `git@github.com:JIANG-Web3Builder/abook_dashboard.git`.
- [ ] Confirm scope, create an agent branch, commit, push, and open a draft PR if GitHub tooling/authentication permits.

