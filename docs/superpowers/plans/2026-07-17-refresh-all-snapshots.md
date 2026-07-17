
# 一键刷新全部数据快照 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在左侧参数栏增加“一键刷新全部数据”操作，用当前筛选期和平台重建风险、平均盈利、马丁快照，并在成功后按当前验证期重新计算分析。

**Architecture:** 新增 SnapshotRefreshRequest 请求模型和 app/snapshot_refresh.py 协调器。协调器复用三个现有脚本的 build_snapshot() 生成 payload，先把三份 JSON 写入临时文件，全部成功后再替换正式文件；失败时恢复原文件。FastAPI 提供刷新接口，Vue 左侧按钮调用接口并在成功后触发既有分析请求。

**Tech Stack:** Python 3、FastAPI、Pydantic、ClickHouse Connect、pytest、Vue 3、TypeScript、Vite、pnpm。

## Global Constraints

- 刷新按钮使用当前筛选开始、筛选结束和平台，不使用验证期日期；验证期由随后自动触发的分析请求使用。
- 不在每次普通分析请求中自动重建快照。
- 风险、平均盈利和马丁快照均必须排除账户组中大小写不敏感包含 test 或 demo 的账户。
- 三个快照全部成功生成后才替换正式文件；任一构建或落盘失败时，已有正式快照内容必须保持不变。
- 普通分析请求的日期边界保持闭区间语义，结束日通过次日排他上界查询；验证结束日为 2026-07-16 时，排他上界必须为 2026-07-17。
- 不修改现有筛选规则、P&L 计算口径或 Abook/Bbook 路由规则。
- 只提交本功能新增或修改的文件，不覆盖工作区中已有的其他未提交改动。

## 文件结构

- Create: app/snapshot_refresh.py — 快照 payload 构建、临时文件写入、全部成功后的替换、失败恢复。
- Modify: app/models.py — 刷新接口请求模型。
- Modify: app/main.py — POST /api/abook/refresh-snapshots 接口。
- Modify: frontend/src/api.ts — 刷新接口客户端函数。
- Modify: frontend/src/components/FilterSidebar.vue — 刷新按钮和状态提示。
- Modify: frontend/src/App.vue — 刷新状态、成功后自动重算、清空旧 Book 分析。
- Modify: frontend/src/types.ts — 刷新响应类型。
- Modify: tests/test_snapshot_refresh.py — 协调器单元测试。
- Modify: tests/test_api.py — API 成功、失败和参数传递测试。
- Modify: tests/test_frontend_contract.py — 前端按钮和请求契约测试。
- Modify: tests/test_queries.py — 7 月 16 日排他边界回归测试。
- Modify: README.md — 使用说明和刷新按钮行为。
- Modify: static/ — 通过前端构建生成的生产静态资源；不手工编辑压缩文件。

---

### Task 1: 定义刷新请求模型和快照协调器接口

**Files:**
- Modify: app/models.py after AnalysisPeriod.
- Create: app/snapshot_refresh.py.
- Create: tests/test_snapshot_refresh.py.

**Interfaces:**
- SnapshotRefreshRequest has selection: AnalysisPeriod and platforms: list[str].
- refresh_snapshots(selection_start: str, selection_end: str, platforms: list[str]) -> dict[str, object].
- The result has status, selection_start, selection_end, and snapshots keyed by risk, avg_profit, and martingale.

- [ ] Step 1: Write failing tests.

Create tests that patch the three builder functions and snapshot_paths. The first test must assert all three builders receive 2026-05-01, 2026-06-30, and mt5, and all three target files are created. The second test must pre-populate all three target files with old, make the avg-profit builder raise RuntimeError("source unavailable"), then assert status is error, the error is returned, and all three old contents remain. The third test must assert SnapshotRefreshRequest rejects empty platforms, unsupported platforms, and reversed selection dates.

Use this concrete test shape:

~~~python
def test_refresh_snapshots_keeps_existing_files_when_a_builder_fails(monkeypatch, tmp_path):
    paths = {
        "risk": tmp_path / "risk.json",
        "avg_profit": tmp_path / "avg_profit.json",
        "martingale": tmp_path / "martingale.json",
    }
    for path in paths.values():
        path.write_text("old")
    monkeypatch.setattr(snapshot_refresh, "snapshot_paths", lambda: paths)
    monkeypatch.setattr(snapshot_refresh, "risk_build_snapshot", lambda *args: {"records": []})
    monkeypatch.setattr(
        snapshot_refresh,
        "avg_profit_build_snapshot",
        lambda *args: (_ for _ in ()).throw(RuntimeError("source unavailable")),
    )
    monkeypatch.setattr(snapshot_refresh, "martingale_build_snapshot", lambda *args: {"records": []})

    result = snapshot_refresh.refresh_snapshots("2026-05-01", "2026-06-30", ["mt5"])

    assert result["status"] == "error"
    assert "source unavailable" in result["error"]
    assert all(path.read_text() == "old" for path in paths.values())
~~~

- [ ] Step 2: Run the focused tests and verify the expected failure.

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_snapshot_refresh.py
~~~

Expected: FAIL because SnapshotRefreshRequest, app.snapshot_refresh, and refresh_snapshots do not exist.

- [ ] Step 3: Implement the request model and coordinator.

Add this model to app/models.py:

~~~python
class SnapshotRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection: AnalysisPeriod
    platforms: List[str]

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: List[str]) -> List[str]:
        allowed = {"mt5", "hh_mt5"}
        if not value or set(value) - allowed:
            raise ValueError("platforms must contain only mt5 or hh_mt5")
        return sorted(set(value))
~~~

Create app/snapshot_refresh.py with module-level names that tests can patch:

~~~python
from scripts.build_avg_profit_snapshot import build_snapshot as avg_profit_build_snapshot
from scripts.build_martingale_snapshot import build_snapshot as martingale_build_snapshot
from scripts.build_user_risk_snapshot import build_snapshot as risk_build_snapshot

def snapshot_paths() -> dict[str, Path]:
    return {
        "risk": risk_snapshot_path(),
        "avg_profit": avg_profit_snapshot_path(),
        "martingale": martingale_snapshot_path(),
    }

def refresh_snapshots(selection_start: str, selection_end: str, platforms: list[str]) -> dict[str, object]:
    """Build three payloads and replace local snapshots as one operation."""
~~~

Use a module-level threading.Lock to serialize concurrent refresh requests. Build all three payloads before creating any target file. Serialize with json.dumps(..., ensure_ascii=False, allow_nan=False, indent=2) plus a trailing newline. Stage each payload in a unique same-directory temporary file, then replace the three targets with os.replace. Before replacing, read existing bytes or None; on any replacement error restore every target from the saved bytes through a temporary restore file. Always unlink stage and restore temporary files in finally. Return status ready with each snapshot path, record count, and selection dates. On builder or filesystem failure return status error, error text, and an empty snapshots object after rollback; do not expose raw exceptions through the API.

- [ ] Step 4: Run focused tests and verify they pass.

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_snapshot_refresh.py
~~~

Expected: all snapshot refresh tests pass.

- [ ] Step 5: Commit the coordinator unit.

~~~bash
git add app/models.py app/snapshot_refresh.py tests/test_snapshot_refresh.py
git commit -m "feat: coordinate atomic snapshot refresh"
~~~

---

### Task 2: Expose the backend refresh endpoint

**Files:**
- Modify: app/main.py imports and API routes.
- Modify: tests/test_api.py.

**Interfaces:**
- Consumes SnapshotRefreshRequest and refresh_snapshots from Task 1.
- Produces POST /api/abook/refresh-snapshots, returning HTTP 200 for success and HTTP 502 for refresh failure.

- [ ] Step 1: Write failing endpoint tests.

Add one test that patches app.main.refresh_snapshots, posts selection 2026-05-01 through 2026-06-30 with platforms mt5 and hh_mt5, and asserts status 200 plus the exact normalized arguments. Add a second test that patches the coordinator to return status error and source unavailable, then asserts status 502 and that detail includes source unavailable.

~~~python
def test_refresh_snapshots_endpoint_reports_refresh_failure(monkeypatch):
    monkeypatch.setattr(
        "app.main.refresh_snapshots",
        lambda *args: {"status": "error", "error": "source unavailable", "snapshots": {}},
    )
    response = client.post("/api/abook/refresh-snapshots", json={
        "selection": {"start": "2026-05-01", "end": "2026-06-30"},
        "platforms": ["mt5"],
    })
    assert response.status_code == 502
    assert "source unavailable" in response.json()["detail"]
~~~

- [ ] Step 2: Run the endpoint tests and verify they fail.

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_api.py -k refresh_snapshots
~~~

Expected: FAIL because the route and app.main.refresh_snapshots import do not exist.

- [ ] Step 3: Implement the endpoint.

Import SnapshotRefreshRequest and refresh_snapshots in app/main.py, then add:

~~~python
@app.post("/api/abook/refresh-snapshots")
def refresh_snapshot_files(request: SnapshotRefreshRequest) -> dict:
    result = refresh_snapshots(
        request.selection.start.isoformat(),
        request.selection.end.isoformat(),
        request.platforms,
    )
    if result.get("status") != "ready":
        raise HTTPException(
            status_code=502,
            detail=str(result.get("error", "snapshot refresh failed")),
        )
    return result
~~~

Leave Pydantic validation as HTTP 422 for reversed dates and unsupported or empty platforms.

- [ ] Step 4: Run endpoint and existing API tests.

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_api.py
~~~

Expected: all API tests pass.

- [ ] Step 5: Commit the endpoint.

~~~bash
git add app/main.py tests/test_api.py
git commit -m "feat: expose snapshot refresh endpoint"
~~~

---

### Task 3: Add the left-panel refresh button and automatic analysis reload

**Files:**
- Modify: frontend/src/api.ts.
- Modify: frontend/src/types.ts.
- Modify: frontend/src/components/FilterSidebar.vue.
- Modify: frontend/src/App.vue.
- Modify: tests/test_frontend_contract.py.

**Interfaces:**
- refreshSnapshots(request: RequestModel): Promise<SnapshotRefreshResponse> posts only request.selection and request.platforms.
- FilterSidebar emits refresh in addition to apply and reset, and receives refreshing: boolean and refreshMessage: string.
- App.vue owns refresh state; successful refresh calls loadAnalysis() and leaves bookData cleared.

- [ ] Step 1: Write failing frontend contract tests.

Read frontend/src/components/FilterSidebar.vue, frontend/src/api.ts, and frontend/src/App.vue. Assert the source contains the text 刷新全部数据, identifier refreshSnapshots, path refresh-snapshots, identifier refreshing, and bookData.value = null.

~~~python
def test_frontend_exposes_refresh_all_data_button_and_request_contract():
    sidebar = (ROOT / "frontend/src/components/FilterSidebar.vue").read_text()
    api = (ROOT / "frontend/src/api.ts").read_text()
    app = (ROOT / "frontend/src/App.vue").read_text()
    assert "刷新全部数据" in sidebar
    assert "refreshSnapshots" in api
    assert "refresh-snapshots" in api
    assert "refreshing" in app
    assert "bookData.value = null" in app
~~~

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_frontend_contract.py -k refresh
~~~

Expected: FAIL before implementation.

- [ ] Step 2: Implement the frontend flow.

In frontend/src/types.ts add SnapshotRefreshResponse with status ready, selection_start, selection_end, and a snapshots record containing status, path, records, selection_start, and selection_end.

In frontend/src/api.ts add:

~~~typescript
export function refreshSnapshots(request: RequestModel) {
  return postJson<SnapshotRefreshResponse>("/api/abook/refresh-snapshots", {
    selection: request.selection,
    platforms: request.platforms,
  })
}
~~~

In FilterSidebar.vue add refreshing and refreshMessage props, add refresh to emits, and add a button next to the apply button:

~~~vue
<button class="ghost" :disabled="loading || refreshing || !request.platforms.length" @click="emit('refresh')">
  {{ refreshing ? "正在刷新…" : "刷新全部数据" }}
</button>
<p v-if="refreshMessage" class="hint" :class="{ warning: refreshMessage.includes('失败') }">
  {{ refreshMessage }}
</p>
~~~

In App.vue add refreshing and refreshMessage refs, import refreshSnapshots, and implement:

~~~typescript
async function refreshAllSnapshots() {
  refreshing.value = true
  refreshMessage.value = ""
  error.value = ""
  try {
    const result = await refreshSnapshots(request.value)
    bookData.value = null
    refreshMessage.value = "刷新成功：3 个快照已更新，正在重新计算"
    await loadAnalysis()
  } catch (err) {
    refreshMessage.value = "刷新失败：" + (err instanceof Error ? err.message : String(err))
  } finally {
    refreshing.value = false
  }
}
~~~

Pass refreshing, refresh-message, and the refresh event to FilterSidebar. Do not add a watcher that refreshes snapshots merely because dates were edited.

- [ ] Step 3: Run the focused frontend contract test and build.

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_frontend_contract.py -k refresh
cd frontend && pnpm run build
~~~

Expected: focused contract test passes and Vite exits with status 0, updating static/.

- [ ] Step 4: Commit the frontend flow.

~~~bash
git add frontend/src/api.ts frontend/src/types.ts frontend/src/components/FilterSidebar.vue frontend/src/App.vue tests/test_frontend_contract.py static/
git commit -m "feat: add dashboard snapshot refresh control"
~~~

---

### Task 4: Verify date coverage and document the operation

**Files:**
- Modify: tests/test_queries.py.
- Modify: README.md.

**Interfaces:**
- Consumes existing build_analysis_query() and build_daily_pnl_query() date parameter behavior.
- Produces regression evidence that validation end 2026-07-16 results in 2026-07-17 as the exclusive query boundary.

- [ ] Step 1: Add the boundary regression test.

Add:

~~~python
def test_analysis_and_daily_queries_include_validation_end_2026_07_16():
    analysis_query, analysis_params = build_analysis_query(
        platforms=["mt5"], start="2026-05-01", end="2026-07-16", lookback_months=3,
        filters={}, selection_start="2026-05-01", selection_end="2026-06-30",
        validation_start="2026-07-01", validation_end="2026-07-16",
    )
    daily_query, daily_params = build_daily_pnl_query(
        platforms=["mt5"], start="2026-05-01", end="2026-07-16", filters={},
    )
    assert analysis_params["end_exclusive"] == "2026-07-17"
    assert analysis_params["validation_end_exclusive"] == "2026-07-17"
    assert daily_params["end_exclusive"] == "2026-07-17"
    assert "{validation_end_exclusive:Date}" in analysis_query
    assert "{end_exclusive:Date}" in daily_query
~~~

Run:

~~~bash
.venv/bin/python -m pytest -q tests/test_queries.py -k 2026_07_16
~~~

Expected: PASS with current query implementation; this locks the required behavior before the final full-suite check.

- [ ] Step 2: Update README.md.

Add after the local snapshot commands:

~~~text
页面左侧“刷新全部数据”会按当前筛选期和平台重建风险、平均盈利、马丁三个本地快照。三个快照全部成功后页面会自动重新计算；验证期结束日仍由页面日期控制。例如验证结束日设为 2026-07-16，主查询会读取至 7 月 16 日（排他上界为 2026-07-17）。如果 ClickHouse 尚未落库 7 月 16 日数据，覆盖信息会反映实际可用范围。
~~~

- [ ] Step 3: Run the full verification suite.

Run:

~~~bash
.venv/bin/python -m pytest -q
cd frontend && pnpm run build
git diff --check
git status --short
~~~

Expected: pytest exits 0 with 0 failures, frontend build exits 0, git diff --check emits no output, and git status contains only intended feature changes plus pre-existing user modifications.

- [ ] Step 4: Commit documentation and regression coverage.

~~~bash
git add tests/test_queries.py README.md
git commit -m "docs: describe snapshot refresh and date coverage"
~~~

---

## Plan Self-Review

- Spec goal 1 is covered by Task 3's left-panel button.
- Spec goal 2 is covered by Task 1's current-selection arguments and Task 3's request body.
- Spec goal 3 is covered by Task 3's loadAnalysis() call after successful refresh.
- Spec goal 4 is covered by Task 2's response and Task 3's loading/message state.
- Spec goal 5 is covered by Task 1's stage/rollback tests and implementation.
- The non-goals are preserved by the explicit selection-only request body and by leaving the existing analysis flow unchanged.
- All named functions, properties, and file paths are consistent across tasks.
- No placeholder or unspecified error-handling step remains in the plan.
