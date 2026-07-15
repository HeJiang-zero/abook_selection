# Daily P&L Book Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Replace the monthly P&L panel with two accurate daily P&L charts, merge the observation cohort into displayed BBook, and remove the three obsolete dashboard sections.

**Architecture:** Keep the existing monthly analysis query as the source for account selection and stage metrics. Add a separate account-day Deals query, pass filtered and population day rows into the service, and return a pre-aggregated daily_book_series payload so the browser never derives daily values from monthly totals. Render two ECharts line charts from that payload while retaining the backend’s internal observation cohort and legacy response fields for compatibility.

**Tech Stack:** Python 3, FastAPI, ClickHouse SQL, pytest, Vue 3 CDN, ECharts 5.

## Global Constraints

- Use Deals 'profit + storage + commission + fee' for action IN (0, 1) only.
- Continue filtering is_deleted = 0, and exclude account groups containing test or demo case-insensitively.
- Aggregate dates in UTC using ClickHouse toDate(time).
- Company net P&L is overall user net trading P&L multiplied by -1.
- BBook display data is bbook_candidate + observation; do not change candidate qualification rules.
- Do not remove backend transitions or profit_impact fields.
- Follow TDD: each behavior starts with a failing test, then the minimum implementation, then a focused passing test run.

---

### Task 1: Add the account-day P&L query

**Files:**
- Modify: /Users/jianghe/abook_hedging/app/queries.py
- Test: /Users/jianghe/abook_hedging/tests/test_queries.py

**Interfaces:**
- Produces build_daily_pnl_query(*, platforms: list[str], start: str, end: str, filters: dict[str, Any] | None = None, excluded_logins: set[tuple[str, int]] | None = None) -> tuple[str, dict[str, Any]].
- Returns one row per (platform, login, trade_date) with client_net_pnl, market_pnl, and matched_trades.

- [ ] **Step 1: Write the failing query contract test**

Append to tests/test_queries.py:

~~~python
from app.queries import build_analysis_query, build_daily_pnl_query


def test_daily_pnl_query_aggregates_utc_deals_and_reuses_account_boundaries():
    query, params = build_daily_pnl_query(
        platforms=["mt5"],
        start="2026-05-01",
        end="2026-07-13",
        filters={"groups": ["real\\FPlive"], "logins": [123]},
    )

    assert "risk.ods_mt5_users FINAL" in query
    assert "risk.ods_mt5_deals FINAL" in query
    assert "toDate(d.time) AS trade_date" in query
    assert "action IN (0, 1)" in query
    assert "sumIf(profit + storage + commission + fee, action IN (0, 1)) AS client_net_pnl" in query
    assert "is_deleted = 0" in query
    assert "positionCaseInsensitive(group, 'test') = 0" in query
    assert "positionCaseInsensitive(group, 'demo') = 0" in query
    assert "has({login_0:Array(UInt64)}, login)" in query
    assert params["start"] == "2026-05-01"
    assert params["end_exclusive"] == "2026-07-14"


def test_daily_pnl_query_embeds_large_excluded_login_sets_without_http_array_params():
    query, params = build_daily_pnl_query(
        platforms=["mt5"],
        start="2026-05-01",
        end="2026-07-13",
        filters={},
        excluded_logins={("mt5", login) for login in range(3000)},
    )

    assert "NOT ((platform = 'mt5' AND login IN (0,1,2" in query
    assert "excluded_logins" not in params
~~~

- [ ] **Step 2: Run the focused tests to verify the expected failure**

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_queries.py::test_daily_pnl_query_aggregates_utc_deals_and_reuses_account_boundaries tests/test_queries.py::test_daily_pnl_query_embeds_large_excluded_login_sets_without_http_array_params
~~~

Expected: FAIL with ImportError because build_daily_pnl_query does not exist.

- [ ] **Step 3: Implement the minimal query builder**

In app/queries.py, add build_daily_pnl_query after build_analysis_query. Reuse the existing platform validation and safe group/Login/excluded-login predicate construction. The query must use risk.ods_mt5_users FINAL, risk.ods_mt5_deals FINAL, toDate(d.time) AS trade_date, is_deleted = 0, action IN (0, 1), and the canonical client_net_pnl expression. Use _date_end_exclusive(end) and never interpolate unvalidated request values.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run the same focused pytest command. Expected: 2 passed.

- [ ] **Step 5: Commit the query unit**

~~~bash
git add app/queries.py tests/test_queries.py
git commit -m "feat: add daily pnl query"
~~~

### Task 2: Expose daily rows through the repository and API request flow

**Files:**
- Modify: /Users/jianghe/abook_hedging/app/repository.py
- Modify: /Users/jianghe/abook_hedging/app/main.py
- Test: /Users/jianghe/abook_hedging/tests/test_api.py

**Interfaces:**
- Adds ClickHouseRepository.fetch_daily_pnl(request: AnalysisRequest, excluded_logins: set[tuple[str, int]] | None = None) -> list[dict[str, Any]].
- analysis() passes daily_rows and overview_daily_rows only for the two-stage request; legacy lookback_months responses remain unchanged.

- [ ] **Step 1: Write the failing repository/API test**

Add fetch_daily_pnl to the Fake Repository in the two-stage API test:

~~~python
def fetch_daily_pnl(self, request, excluded_logins=None):
    return [{
        "platform": "mt5", "login": 7,
        "trade_date": datetime(2026, 5, 15),
        "client_net_pnl": Decimal("12"),
        "market_pnl": Decimal("13"),
        "matched_trades": 2,
    }]
~~~

After the response, assert:

~~~python
assert "daily_book_series" in response.json()
~~~

- [ ] **Step 2: Run the focused API test to verify the expected failure**

~~~bash
.venv/bin/python -m pytest -q tests/test_api.py::test_analysis_returns_two_stage_payload_for_new_request
~~~

Expected: FAIL because the payload does not yet contain daily_book_series.

- [ ] **Step 3: Implement repository and main wiring**

In app/repository.py, calculate the two-stage request window with the same min(selection.start, validation.start) and max(selection.end, validation.end) logic used by fetch_analysis, call build_daily_pnl_query, and return _rows(query, params).

In app/main.py, use a compatibility helper:

~~~python
def fetch_daily(repository, request, excluded_logins=None):
    method = getattr(repository, "fetch_daily_pnl", None)
    if not callable(method):
        return []
    return method(request, excluded_logins=excluded_logins)
~~~

Use the same effective/overview boundary as the existing monthly fetch: overview_daily_rows comes from the unfiltered request when overview_rows is fetched; personal-candidate mode reuses those rows; an intentionally empty effective risk result uses an empty daily list; otherwise fetch with effective_request and the same excluded Login set. Pass both lists to build_two_stage_payload.

- [ ] **Step 4: Run focused API and existing API tests**

~~~bash
.venv/bin/python -m pytest -q tests/test_api.py::test_analysis_returns_two_stage_payload_for_new_request tests/test_api.py
~~~

Expected: all selected API tests pass.

- [ ] **Step 5: Commit the repository/API unit**

~~~bash
git add app/repository.py app/main.py tests/test_api.py
git commit -m "feat: wire daily pnl rows into analysis"
~~~

### Task 3: Aggregate daily Abook/Bbook series and merge observation into BBook

**Files:**
- Modify: /Users/jianghe/abook_hedging/app/service.py
- Test: /Users/jianghe/abook_hedging/tests/test_two_stage_analysis.py

**Interfaces:**
- Adds optional daily_rows and overview_daily_rows keyword parameters to build_two_stage_payload.
- Produces daily_book_series with date, phase, company_net_pnl, and nested abook/bbook net_pnl, profitable_pnl, and loss_pnl.
- Keeps existing monthly_series, transitions, and profit_impact response fields.

- [ ] **Step 1: Write the failing service test**

Add a daily_row helper and a test to tests/test_two_stage_analysis.py:

~~~python
def daily_row(login, day, net, market=None, trades=1):
    return {
        "platform": "mt5", "login": login,
        "trade_date": datetime.fromisoformat(day),
        "client_net_pnl": Decimal(str(net)),
        "market_pnl": Decimal(str(market if market is not None else net)),
        "matched_trades": trades,
    }


def test_two_stage_payload_builds_daily_book_series_and_merges_observation_into_bbook():
    rows = [
        row(1, "05", trades=20, wins=15, losses=5, market=100, net=80, active_days=10, daily_sum=80),
        row(2, "05", trades=20, wins=4, losses=16, market=-100, net=-80, active_days=10, daily_sum=-80),
        row(3, "05", trades=1, wins=1, losses=0, market=5, net=5, active_days=1, daily_sum=5),
    ]
    daily = [
        daily_row(1, "2026-05-15", 30), daily_row(1, "2026-05-16", -10),
        daily_row(2, "2026-05-15", -25), daily_row(2, "2026-05-16", -5),
        daily_row(3, "2026-05-15", 7),
    ]
    result = build_two_stage_payload(
        rows, daily_rows=daily, overview_daily_rows=daily,
        selection_start="2026-05-01", selection_end="2026-05-31",
        validation_start="2026-07-01", validation_end="2026-07-02",
        min_trades=0, min_active_days=0, min_profit_factor=0,
        min_avg_daily_profit=-100, min_positive_month_rate=0,
        max_top1_day_profit_contribution=1,
        min_direction_day_rate_lower_bound=0, min_stability_score=0,
    )

    series = {item["date"]: item for item in result["daily_book_series"]}
    assert series["2026-05-15"]["company_net_pnl"] == -12.0
    assert series["2026-05-15"]["abook"] == {"net_pnl": 30.0, "profitable_pnl": 30.0, "loss_pnl": 0.0}
    assert series["2026-05-15"]["bbook"] == {"net_pnl": -18.0, "profitable_pnl": 7.0, "loss_pnl": -25.0}
    assert series["2026-05-16"]["bbook"]["net_pnl"] == -5.0
    assert series["2026-05-16"]["abook"]["loss_pnl"] == -10.0
    assert series["2026-06-01"]["company_net_pnl"] == 0.0
~~~

Also add a test where overview_daily_rows contains an account omitted from daily_rows, proving the company line uses the population rows and not filtered candidate rows.

- [ ] **Step 2: Run the focused service test to verify the expected failure**

~~~bash
.venv/bin/python -m pytest -q tests/test_two_stage_analysis.py::test_two_stage_payload_builds_daily_book_series_and_merges_observation_into_bbook
~~~

Expected: FAIL because build_two_stage_payload does not accept daily row arguments or return daily_book_series.

- [ ] **Step 3: Implement the minimal service aggregation**

Add _daily_book_series before build_two_stage_payload. It accepts daily_rows, overview_daily_rows, accounts, selection_start, selection_end, validation_start, and validation_end. Use date.fromisoformat, timedelta(days=1), and the existing _decimal and _float helpers. Iterate over every date in the union of the two inclusive windows. Map abook_candidate to abook and every other account to bbook. Aggregate overview_daily_rows or daily_rows for company_net_pnl with a negative sign, and daily_rows only for accounts present in the account map. For each book, add positive account-day values to profitable_pnl and negative values to loss_pnl; net_pnl must equal their sum. Emit phase as selection or validation and fill missing dates with zero.

Update build_two_stage_payload to accept the optional iterables, call the helper after by_cohort is built, and add daily_book_series to the payload. Use the same merged BBook list for book_performance:

~~~python
display_bbook_accounts = by_cohort["bbook_candidate"] + by_cohort["observation"]
~~~

Keep validation_groups, internal counts, transitions, and profit impact keyed by their original cohorts.

- [ ] **Step 4: Run focused service tests and all two-stage tests**

~~~bash
.venv/bin/python -m pytest -q tests/test_two_stage_analysis.py::test_two_stage_payload_builds_daily_book_series_and_merges_observation_into_bbook tests/test_two_stage_analysis.py
~~~

Expected: all selected tests pass.

- [ ] **Step 5: Commit the service unit**

~~~bash
git add app/service.py tests/test_two_stage_analysis.py
git commit -m "feat: aggregate daily pnl into display books"
~~~

### Task 4: Render two daily charts and remove obsolete dashboard sections

**Files:**
- Modify: /Users/jianghe/abook_hedging/static/app.js
- Modify: /Users/jianghe/abook_hedging/static/index.html
- Modify: /Users/jianghe/abook_hedging/tests/test_frontend_contract.py

**Interfaces:**
- Consumes data.daily_book_series from Task 3.
- Produces chart nodes abook-daily-pnl-chart and bbook-daily-pnl-chart.
- Uses renderDailyPnlChart(book, nodeId) and no longer creates validationChart.

- [ ] **Step 1: Write the failing frontend contract assertions**

Update tests/test_frontend_contract.py with:

~~~python
assert "daily_book_series" in javascript or "daily_book_series" in html
assert "abook-daily-pnl-chart" in html
assert "bbook-daily-pnl-chart" in html
assert "trigger: 'axis'" in javascript
assert "axisPointer: { type: 'cross' }" in javascript
assert "入选组 vs 对照组" not in html
assert "TRANSITIONS" not in html
assert "PROFIT IMPACT" not in html
assert "renderValidationChart" not in javascript
assert "validation-chart" not in html
~~~

Also assert that the account filter has only Abook and BBook options and that observation is mapped to BBook in JavaScript.

- [ ] **Step 2: Run frontend contract tests to verify the expected failure**

~~~bash
.venv/bin/python -m pytest -q tests/test_frontend_contract.py
~~~

Expected: FAIL because the current HTML and JavaScript still contain the monthly chart, validation chart, transitions, and profit impact panel.

- [ ] **Step 3: Implement the minimal frontend change**

In static/index.html, replace the single pnl-chart card with two cards containing abook-daily-pnl-chart and bbook-daily-pnl-chart. Remove the validation chart card, transitions table, and profit impact card. Use data.book_performance.selection.bbook.accounts for the merged BBook KPI and remove the observation account-filter option.

In static/app.js, replace chart/validationChart state with abookPnlChart, bbookPnlChart, and stabilityChart. Implement renderDailyPnlCharts and renderDailyPnlChart using data.daily_book_series. The chart must use four line series named 公司净 P&L, Abook/Bbook 净 P&L, Abook/Bbook 盈利 P&L, and Abook/Bbook 亏损 P&L; use tooltip trigger axis, axisPointer crosshair, a date header with phase, and money formatting for every value. Keep stability rendering and resize all three live chart instances. Remove renderValidationChart, successTransition, reversalTransition, and unused validation chart state.

Map observation to the BBook display in cohortLabel and filteredAccounts:

~~~javascript
const displayCohort = account.cohort === 'abook_candidate' ? 'abook_candidate' : 'bbook_candidate';
~~~

- [ ] **Step 4: Run frontend contract tests and verify they pass**

~~~bash
.venv/bin/python -m pytest -q tests/test_frontend_contract.py
~~~

Expected: all frontend contract tests pass.

- [ ] **Step 5: Commit the frontend unit**

~~~bash
git add static/app.js static/index.html tests/test_frontend_contract.py
git commit -m "feat: replace monthly pnl panel with daily book charts"
~~~

### Task 5: Full verification and final cleanup

**Files:**
- Modify: /Users/jianghe/abook_hedging/README.md if the dashboard description still says monthly-only.
- Test: all existing tests under /Users/jianghe/abook_hedging/tests/.

- [ ] **Step 1: Update stale user-facing documentation**

Change the README dashboard description from a monthly P&L chart to daily incremental P&L curves, and state that displayed BBook includes the observation cohort. Do not remove the backend compatibility explanation for transitions or profit impact.

- [ ] **Step 2: Run the complete test suite**

~~~bash
.venv/bin/python -m pytest -q
~~~

Expected: exit code 0 with zero failures.

- [ ] **Step 3: Run syntax and diff checks**

~~~bash
.venv/bin/python -m compileall -q app tests
git diff --check HEAD~4..HEAD
git status --short
~~~

Expected: compileall succeeds, the diff check is clean, and only intended source/test/documentation files plus pre-existing untracked user files remain.

- [ ] **Step 4: Review the requirement checklist against the rendered source**

~~~bash
rg -n "daily_book_series|abook-daily-pnl-chart|bbook-daily-pnl-chart|trigger: 'axis'|axisPointer: \\{ type: 'cross' \\}" static/app.js static/index.html app/service.py
rg -n "入选组 vs 对照组|TRANSITIONS|PROFIT IMPACT|validation-chart|renderValidationChart" static/app.js static/index.html
~~~

Expected: the first command finds the new daily chart contract; the second command returns no obsolete UI/rendering matches.

- [ ] **Step 5: Commit final documentation/cleanup**

~~~bash
git add README.md
git commit -m "docs: describe daily book pnl charts"
~~~
