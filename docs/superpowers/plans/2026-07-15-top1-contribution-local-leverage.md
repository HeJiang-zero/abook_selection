# Top1 Contribution and Local Leverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a strict Top1 daily contribution filter and a local, reusable balance/turnover risk snapshot that applies peak leverage filtering while allowing non-positive-balance users to pass only the non-leverage rules.

**Architecture:** Generate `data/user_risk_snapshot.json` once for the selection window from ClickHouse, keep it local and ignored, and intersect its allowed Login list with request filters before the main analysis query. Enrich returned rows with snapshot metrics so the service applies the same risk rule and exposes auditable fields. Replace the old concentration parameter with a strict 20% Top1 contribution rule.

**Tech Stack:** Python 3.9, FastAPI, Pydantic, clickhouse-connect, pytest, Vue 3/ECharts static frontend.

## Global Constraints

- Selection rules use only the configured 5–6 month window; July remains validation-only.
- `risk.ods_mt5_users` rows whose group contains `test` or `demo`, case-insensitively, are always excluded.
- `balance_prev_month <= 0` or null skips only leverage filtering; all P&L-quality filters still apply.
- The local risk snapshot is generated data and must not be committed; database credentials must never enter Git.
- Top1 contribution uses strict `< 0.20`, not `<= 0.20`.

### Task 1: Lock metric and model contracts with failing tests

**Files:** `tests/test_models.py`, `tests/test_two_stage_analysis.py`, `tests/test_frontend_contract.py`, `tests/test_queries.py`.

- [ ] Add tests for `max_top1_day_profit_contribution=0.2`, `max_peak_leverage_ratio=5.0`, rejection of the old concentration rule, and the new frontend controls.
- [ ] Add a two-stage fixture where exactly 20% Top1 contribution fails, lower concentration passes, a positive-balance account above leverage 5 fails, and a non-positive-balance account still passes the other rules.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_models.py tests/test_two_stage_analysis.py tests/test_frontend_contract.py tests/test_queries.py` and verify failures are about the missing behavior.

### Task 2: Implement the local risk snapshot

**Files:** create `app/risk.py`, create `scripts/build_user_risk_snapshot.py`, create `tests/test_risk.py`, modify `app/repository.py`, `app/models.py`, `app/main.py`, `.gitignore`.

- [ ] Implement `load_risk_snapshot(path, selection_start, selection_end, platforms)` with explicit `missing`, `stale`, and `ready` states.
- [ ] Implement `RiskSnapshot.allowed_logins(max_peak_leverage_ratio)` so all non-positive-balance records remain allowed and positive-balance records must be at or below the threshold.
- [ ] Implement `RiskSnapshot.enrich_rows(rows)` with balance, average open degree, peak leverage ratio, and balance status fields.
- [ ] Generate the snapshot from `risk.ods_mt5_users FINAL` and daily matched `turnover`, with `is_deleted=0` and case-insensitive `test`/`demo` exclusions; write atomically to `ABOOK_RISK_SNAPSHOT_PATH` or `data/user_risk_snapshot.json`.
- [ ] Apply the local Login intersection before ClickHouse analysis and return risk snapshot status in the payload. Short-circuit to an empty result if the effective allowed Login set is empty.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_risk.py tests/test_api.py tests/test_queries.py`.

### Task 3: Implement candidate rules and risk audit fields

**Files:** modify `app/service.py`, `app/main.py`, `app/models.py`, `tests/test_two_stage_analysis.py`.

- [ ] Replace every `max_top_day_concentration` reference with strict directional Top1 checks: positive candidates use positive-day concentration, negative candidates use negative-day concentration.
- [ ] Require positive-balance accounts to have peak leverage `<= max_peak_leverage_ratio`; skip only this check for `unknown_nonpositive_balance`.
- [ ] Return new rules, risk snapshot status, risk metrics, and risk flags in account and payload output.
- [ ] Remove every old `max_top_day_concentration` reference.
- [ ] Run focused tests and `.venv/bin/python -m pytest -q`.

### Task 4: Update dashboard and documentation

**Files:** modify `static/app.js`, `static/index.html`, `static/styles.css`, `README.md`, `.gitignore`.

- [ ] Replace the old concentration input with Top1 contribution, add maximum peak leverage, show snapshot status, and show risk metrics in the account drawer.
- [ ] Include both new rule keys in `rulesDirty`, increment static cache version, and keep pending/applied text accurate.
- [ ] Document formulas, zero-balance treatment, refresh command, ignored local output, and examples of test/demo group exclusions.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_frontend_contract.py`.

### Task 5: Generate, verify, and commit

**Files:** local ignored `data/user_risk_snapshot.json`; all modified source, tests, docs, and plan files.

- [ ] Run `.venv/bin/python scripts/build_user_risk_snapshot.py --selection-start 2026-05-01 --selection-end 2026-06-30` with the configured read-only environment.
- [ ] Verify finite ratios or nulls, no case-insensitive `test`/`demo` groups, positive-balance ratios, and non-positive-balance status.
- [ ] Run `.venv/bin/python -m pytest -q` and `.venv/bin/python -m compileall -q app scripts`.
- [ ] Confirm `git check-ignore -v data/user_risk_snapshot.json clickhouse.md`, stage only safe files, and commit `feat: add top1 contribution and local leverage filters`.
