# Abook 筛选面板 Phase 0–6 验证记录

验证时间：2026-07-16

## 自动化验证

- `.venv/bin/python -m pytest -q`：82 passed，0 failed；仅有现有 urllib3/LibreSSL warning。
- `frontend` 使用桌面 Bundled Node 24.14.0 + pnpm 11.7.0 构建：Vite 6.4.3 exit 0。
- FastAPI `/api/health`：200，返回 `{"status":"ok","service":"abook-dashboard"}`。
- `/`、`/assets/app.js`、`/assets/styles.css`：均返回 200。

## Phase 0 真实数据

- `risk.dws_account_martingale_window` schema 探查成功，28 个字段。
- `window_type`：`7D_SLIDING`、`CUSTOM`；默认快照使用 `7D_SLIDING`。
- `avg_volume_escalation` 确认为倍数口径。
- 选择期快照构建成功：801 个用户；极高 381、高 258、中 68、低 94。

## 默认真实分析

请求：`POST /api/abook/analysis`，平台 `mt5`，默认 2026-05-01 至 2026-06-30 筛选、2026-07-01 至 2026-07-13 验证。

- HTTP：200。
- 全量处理耗时约 2 分 3 秒；单账户过滤请求耗时约 12.6 秒。页面有 loading 状态，ClickHouse 全量人口查询是主要耗时来源。
- `martingale.status`：`ready`。
- 马丁拦截人数：707。
- Abook Core：21。
- 误判成本：446.66。
- 返回账户：6,345。
- `coverage.validation_partial`：`true`，符合 7 月 1–13 日部分月份护栏。

## 结论

页面静态资源、健康检查、默认分析和新增分析字段均已实际验证。参数寻优、CSV 导出和 Book 分析通过 pytest/FakeRepository 契约验证；它们不会在前端静态加载时触发，分别在用户操作或切换 Tab 时请求。
