# Abook/Bbook P&L Unification and Book Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the analysis safe for production data by enforcing demo/test exclusion, correcting population and cross-period statistics, using deals as the single business P&L source, and adding top-of-page Abook/Bbook profitability analysis.

**Architecture:** ClickHouse will filter the eligible `(platform, login)` population before every fact aggregation and will emit canonical deals P&L plus exact period behavior aggregates. Python will calculate finite cross-month statistics, cohort summaries, theoretical Bbook/Abook impact, and a new `book_performance` payload. The existing Vue page will render the new payload in a top summary section without changing account-table interactions.

**Tech Stack:** FastAPI, ClickHouse SQL, clickhouse-connect, Python `Decimal`, Vue 3 CDN, ECharts/Vue templates, pytest.

## Global Constraints

- Effective users must have `is_deleted = 0`, platform `mt5` or `hh_mt5`, and account groups without case-insensitive `test` or `demo`.
- User identity and counts use `(platform, login)`.
- Canonical trading P&L is `ods_mt5_deals FINAL` with `action IN (0, 1)` and `profit + storage + commission + fee`.
- `action IN (2, 3)` remains separate funding P&L and never enters trading profitability selection.
- `dwd_matched_trades FINAL` is behavior-only for trade count, volume, turnover, holding time, symbol, and direction metrics.
- Every emitted numeric value must be finite; no-loss Profit Factor remains `null`.
- Abook theoretical profit remains `0` until real external hedge data is available.
- Do not add the separately requested real ClickHouse/browser integration-test suite in this plan.

---

### Task 1: Add red regression tests for the corrected contracts

**Files:**
- Modify: `/Users/jianghe/abook_hedging/tests/test_queries.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_service.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_two_stage_analysis.py`
- Modify: `/Users/jianghe/abook_hedging/tests/test_api.py`

**Interfaces:**
- Consumes: current query builders and service payload functions.
- Produces: failing tests for forced exclusion, tuple population counts, canonical deals P&L, finite statistics, exact period behavior, and top book summaries.

- [ ] **Step 1: Add query contract tests.**

Add tests asserting that `build_analysis_query(...)` contains `uniqExact(tuple(platform, login))`, joins the eligible users CTE into matched and deal aggregations, exposes canonical deal gross wins/losses, and contains guarded daily sum/square/count fields. Add a test asserting `build_account_detail_query(...)` joins `risk.ods_mt5_users FINAL` and contains both case-insensitive `test` and `demo` predicates.

- [ ] **Step 2: Add service fixtures for exact statistics.**

Extend the existing row fixture with `market_pnl`, `daily_sum_squares`, `daily_stddev_count`, `selection_median_holding_seconds`, `validation_median_holding_seconds`, `selection_symbols_traded`, and `validation_symbols_traded`. Use two months with daily P&L values `[1, 3]` and `[5]`; assert the period population standard deviation is `sqrt(8/3)`, not an average of monthly standard deviations. Give the two months different medians and symbols; assert the phase value is the period value, not the last month or monthly maximum.

- [ ] **Step 3: Add service tests for book performance.**

Build one profitable Abook candidate and one losing Bbook candidate, then assert `book_performance.selection` and `.validation` expose profitable/loss/neutral counts, gross profit, gross loss, net P&L, current Bbook profit, assumed Abook profit, and theoretical increment. Assert a profitable user with net `100` has theoretical increment `100`, while a losing user with net `-100` has theoretical increment `-100`.

- [ ] **Step 4: Add a finite-payload regression test.**

Pass a row with zero active trading days and missing/zero daily variance inputs through `build_two_stage_payload(...)`; assert `json.dumps(payload, allow_nan=False)` succeeds and the resulting standard deviation is `0.0`.

- [ ] **Step 5: Run the focused tests and verify they fail for the intended reasons.**

Run:

```bash
/Users/jianghe/abook_hedging/.venv/bin/python -m pytest -q tests/test_queries.py tests/test_service.py tests/test_two_stage_analysis.py tests/test_api.py
```

Expected result: failures identify the missing query fields, missing `book_performance`, wrong tuple count contract, or non-finite statistic behavior; no unrelated collection error is acceptable.

### Task 2: Filter the eligible population and emit canonical query aggregates

**Files:**
- Modify: `/Users/jianghe/abook_hedging/app/queries.py`
- Modify: `/Users/jianghe/abook_hedging/app/repository.py`
- Test: `/Users/jianghe/abook_hedging/tests/test_queries.py`

**Interfaces:**
- Consumes: existing `build_analysis_query(...)`, `build_account_detail_query(...)`, and `ClickHouseRepository` calls.
- Produces: account-month rows with canonical deals P&L, exact variance inputs, phase behavior fields, tuple population counts, and detail-query exclusion.

- [ ] **Step 1: Make exclusion unconditional in the analysis query.**

Build the users CTE with the three fixed conditions below regardless of the legacy boolean argument:

```sql
WHERE is_deleted = 0
  AND has({platforms:Array(String)}, platform)
  AND positionCaseInsensitive(`group`, 'test') = 0
  AND positionCaseInsensitive(`group`, 'demo') = 0
```

Keep the Python parameter for request compatibility, but do not let it remove these predicates.

- [ ] **Step 2: Join the filtered users CTE before fact aggregation.**

Add `INNER JOIN users AS u ON m.platform = u.platform AND m.login = u.login` to `matched`, and `INNER JOIN users AS u ON d.platform = u.platform AND d.login = u.login` to `deal_daily`; use `u.account_group` only after the join. Apply the same eligible-user join to source coverage CTEs so their dates and deleted-row counts describe only the analysis population.

- [ ] **Step 3: Make deals the canonical P&L source.**

In `deal_daily`, add daily gross wins and gross losses from `profit` under `action IN (0, 1)`, plus daily squared net P&L. In `deal_costs`, sum those fields into `deal_market_pnl`, `gross_wins`, `gross_losses`, `client_net_pnl`, `costs`, and `funding_pnl`. Keep `matched_market_pnl` as an audit/reference field, but expose `market_pnl` from the deal aggregate for service-layer business calculations.

- [ ] **Step 4: Emit exact daily variance inputs.**

In `account_daily`, emit:

```sql
sumIf(toFloat64(daily_client_net_pnl), trade_rows > 0) AS daily_pnl_sum_for_variance,
sumIf(toFloat64(daily_client_net_pnl) * toFloat64(daily_client_net_pnl), trade_rows > 0) AS daily_pnl_square_sum,
countIf(trade_rows > 0) AS daily_variance_count
```

Use `coalesce(a.daily_pnl_sum_for_variance, 0)`, `coalesce(a.daily_pnl_square_sum, 0)`, and `coalesce(a.daily_variance_count, 0)` in the final projection. Do not use an unguarded `stddevPopIf` result as an API value.

- [ ] **Step 5: Add phase-level behavior aggregates.**

When selection and validation dates are supplied, add two matched CTEs grouped by `(platform, login)` that calculate `quantileTDigest(0.5)(holding_seconds)` and `uniqExact(symbol)` separately for each phase. Project `selection_median_holding_seconds`, `validation_median_holding_seconds`, `selection_symbols_traded`, and `validation_symbols_traded` onto every account-month row. Use zero when a phase has no matched rows.

- [ ] **Step 6: Fix population and detail-query filtering.**

Change population SQL to:

```sql
uniqExact(tuple(platform, login)) AS unique_account_count
```

Add the same fixed eligible-user join and group predicates to `build_account_detail_query(...)`. The repository must pass the phase dates to the analysis query and must not provide a bypass for detail access.

- [ ] **Step 7: Run query contract tests.**

Run:

```bash
/Users/jianghe/abook_hedging/.venv/bin/python -m pytest -q tests/test_queries.py
```

Expected result: all query contract tests pass.

### Task 3: Use canonical P&L and exact statistics in the service layer

**Files:**
- Modify: `/Users/jianghe/abook_hedging/app/service.py`
- Modify: `/Users/jianghe/abook_hedging/app/main.py`
- Modify: `/Users/jianghe/abook_hedging/app/models.py` only if phase-query arguments need explicit validation
- Test: `/Users/jianghe/abook_hedging/tests/test_service.py`
- Test: `/Users/jianghe/abook_hedging/tests/test_two_stage_analysis.py`

**Interfaces:**
- Consumes: canonical `market_pnl`, deals gross P&L, variance inputs, and phase behavior fields from Task 2.
- Produces: finite account/phase summaries, correct cross-month behavior metrics, and `book_performance` in `build_two_stage_payload(...)`.

- [ ] **Step 1: Add canonical-field helpers with fixture fallback.**

Use `market_pnl` when present and fall back to `matched_market_pnl` only for legacy unit-test fixtures. Use deal `gross_wins` and `gross_losses` for Profit Factor; do not recompute business P&L from matched values.

- [ ] **Step 2: Replace monthly standard-deviation averaging.**

Aggregate `daily_pnl_square_sum` and `daily_variance_count` across phase rows. Compute:

```python
mean = total_sum / count
variance = max(Decimal("0"), total_square_sum / count - mean * mean)
daily_stddev = Decimal(str(math.sqrt(float(variance)))) if count else ZERO
```

If the new fields are absent in a legacy fixture, use its finite `daily_stddev` only as a compatibility fallback; never propagate NaN or infinity.

- [ ] **Step 3: Use phase-level median and symbol fields.**

Change `_account_period_metrics(...)` to accept `phase="selection" | "validation"`. Read the phase-specific median and symbol count from the first phase row, falling back to existing fields for legacy fixtures. Do not use `rows[-1]` or `max(monthly symbols)` for phase summaries.

- [ ] **Step 4: Fix tuple-based monthly active-account counts.**

Replace the `active_logins` set in monthly overview with `active_accounts: set[tuple[str, int]]`, add `(account["platform"], account["login"])`, and report its length.

- [ ] **Step 5: Add group performance aggregation.**

Add a helper with signature `def _book_performance(accounts: list[dict[str, Any]], phase: str, neutral_band_usd: float) -> dict[str, Any]`. For each phase, calculate account counts by `client_net_pnl > neutral_band`, `< -neutral_band`, or neutral; gross positive account P&L; gross negative account P&L; net P&L; current Bbook profit `-net`; assumed Abook profit `0`; and theoretical increment `assumed_abook_profit - current_bbook_profit`.

Return:

```python
"book_performance": {
    "selection": {"abook": selection_abook_summary, "bbook": selection_bbook_summary},
    "validation": {"abook": validation_abook_summary, "bbook": validation_bbook_summary},
    "definition": "Abook theoretical increment equals assumed Abook profit minus current Bbook profit",
}
```

- [ ] **Step 6: Keep all derived profit fields on canonical P&L.**

Update monthly series, KPIs, phase summaries, validation groups, `profit_impact`, `profit_overview`, and drawdown curves to use the canonical `market_pnl` field and canonical deals gross P&L. Preserve `is_theoretical=true` and preserve the existing API labels unchanged unless a label would contradict the canonical deals definition.

- [ ] **Step 7: Run service tests.**

Run:

```bash
/Users/jianghe/abook_hedging/.venv/bin/python -m pytest -q tests/test_service.py tests/test_two_stage_analysis.py tests/test_api.py
```

Expected result: all service/API tests pass and the JSON finite regression test passes.

### Task 4: Render the Abook/Bbook analysis at the top of the page

**Files:**
- Modify: `/Users/jianghe/abook_hedging/static/index.html`
- Modify: `/Users/jianghe/abook_hedging/static/app.js`
- Modify: `/Users/jianghe/abook_hedging/static/styles.css`
- Test: `/Users/jianghe/abook_hedging/tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: `data.book_performance.selection` and `data.book_performance.validation` from Task 3.
- Produces: top-of-page Abook/Bbook profitability cards with period labels, theory warnings, and no changes to account-table filters.

- [ ] **Step 1: Add the top analysis markup.**

Add a visible `BOOK PERFORMANCE` section immediately after the existing KPI cards. Render two group cards, “Abook 候选” and “Bbook 候选”, each with selection and validation rows showing accounts, profitable/loss/neutral counts, gross profit, gross loss, net P&L, current Bbook profit, assumed Abook profit, and theoretical increment.

- [ ] **Step 2: Add stable formatting helpers.**

Use existing `money`, `number`, `percent`, and `tone` helpers. Add a label for the period and a small note: “理论值，不含真实外部对冲收益与成本”. Positive/negative colors apply only to movement/profit values, not neutral account counts.

- [ ] **Step 3: Add empty/error-safe rendering.**

Render the section only when `book_performance` exists; otherwise show the same loading/error path used by existing dashboard panels. Do not create NaN text in the browser; use `0` or `—` for absent finite fields.

- [ ] **Step 4: Update the frontend contract test.**

Assert that the page contains the visible section title, Abook/Bbook labels, selection/validation labels, theoretical increment label, and the finite-value fallback branch.

- [ ] **Step 5: Run frontend/API tests.**

Run:

```bash
/Users/jianghe/abook_hedging/.venv/bin/python -m pytest -q tests/test_frontend_contract.py tests/test_api.py
```

Expected result: all frontend contract and API tests pass.

### Task 5: Verify the full implementation against local and live evidence

**Files:**
- Modify: `/Users/jianghe/abook_hedging/README.md` with the canonical P&L and top-summary definitions.

**Interfaces:**
- Consumes: completed query, service, API, and frontend changes.
- Produces: verified full test output and a live ClickHouse reconciliation record in the final handoff.

- [ ] **Step 1: Run the complete local verification suite.**

Run:

```bash
/Users/jianghe/abook_hedging/.venv/bin/python -m pytest -q
/Users/jianghe/abook_hedging/.venv/bin/python -m compileall -q app tests
```

Expected result: pytest exits 0 with zero failures, and compileall exits 0.

- [ ] **Step 2: Run the actual analysis query with live ClickHouse credentials.**

Execute the default 2026-05-01 through 2026-07-13 analysis and verify: no returned account group contains `test` or `demo`; `population_unique_accounts` equals the tuple distinct count; `market_pnl`, `gross_wins`, `gross_losses`, and `client_net_pnl` equal the eligible deals aggregates; and `json.dumps(payload, allow_nan=False)` succeeds.

- [ ] **Step 3: Verify detail-query exclusion.**

Request a known demo/test account through the repository detail path and confirm it returns no trades or a controlled rejection, while a valid account still returns its matched rows.

- [ ] **Step 4: Verify top-summary reconciliation.**

For both selection and validation, independently sum the Abook and Bbook account net P&L and compare with `book_performance`, `profit_impact`, and `profit_overview`. Confirm theoretical increment equals `assumed_abook_profit - current_bbook_profit` for both groups.

- [ ] **Step 5: Update README definitions.**

Document the forced exclusion behavior, canonical deals P&L, matched behavior-only role, exact theoretical increment formula, and the fact that the top summary separates selection from sample-out validation.

- [ ] **Step 6: Record final evidence.**

Because this workspace has no `.git` directory, do not run `git commit`; report the changed files and exact verification commands/results instead.
