# Markout 计算方法说明（给 AI / 复现用）

本文描述本仓库 **XAUUSD 撮合成交 markout** 的完整算法：用什么数据、怎么定价、怎么算、怎么按成交额加权、怎么画图。实现以 `markout_core/` 为准。

---

## 1. 目标与符号约定

**目标**：衡量客户成交后，市场价格相对其成交价是否朝有利于客户的方向移动。

| 约定 | 含义 |
|---|---|
| 单位 | **bps**（基点）：\(1\ \mathrm{bps} = 0.01\% = 10^{-4}\) |
| 正值 | **对客户有利**（toxicity / edge 视角下客户占优） |
| 负值 | **对客户不利**（对平台有利） |
| 事件单位 | 一条 **matched trade**（开仓 + 平仓配对），不是单边 fill |

**禁止**：按笔等权平均 markout。必须用 **`turnover`（成交额）加权**，否则 \$1,000 与 \$1,000,000 的单子权重相同。

---

## 2. 数据来源

### 2.1 表

- ClickHouse / 导出源表：`risk.dwd_matched_trades`
- 本地离线副本：`local_data/risk_dwd_matched_trades_mt5_XAUUSD/`（Parquet + manifest）
- 筛选：`platform = 'mt5'`，`symbol = 'XAUUSD'`，`entry_price > 0`，`exit_price > 0`，`volume > 0`

### 2.2 字段（计算必需）

| 字段 | 用途 |
|---|---|
| `login` | 客户账号，按用户聚合 |
| `direction` / `action` | 开仓方向：`Long/buy → action=0`，`Short/sell → action=1` |
| `entry_time` → `ts_ms` | 开仓时刻（Unix ms） |
| `exit_time` → `exit_ms` | 平仓时刻（Unix ms） |
| `entry_price`（别名 `price`） | 开仓成交价 |
| `exit_price` | 平仓成交价 |
| `volume` | 成交数量（盎司）；`1 lot = 100 oz`，仅用于 size 分桶 |
| **`turnover`** | **成交额（USD）**，markout 均值的权重 |
| `holding_seconds` → `holding_ms` | 持仓时长，用于 holding 分桶 / 延迟套利特征 |
| `profit` | 客户已实现盈亏（分类辅助，不进 markout 公式） |
| `entry_deal_id`, `exit_deal_id` | 事件身份，用于参考价 leave-one-out |

### 2.3 `turnover` 权重定义

- 优先直接用表字段 **`turnover`**（成交额）。
- 若缺失：回退 `(entry_price + exit_price) × volume`。
- 再缺失：单腿 `price × volume`。

同一 matched trade 的 entry / exit / combined markout **共用同一个 `turnover` 权重**。

---

## 3. 参考价带（Reference Tape）

本项目 **没有独立 bid/ask tick feed**。参考价来自全体 matched trades 的成交打印：

1. 对每条成交，取两个 print：`(ts_ms, entry_price)` 与 `(exit_ms, exit_price)`。
2. 按时间戳分组；同一毫秒多个 print 取 **median**，得到全局 tape：`times[]`, `prices[]`。
3. 查询时刻 \(t\) 的参考价：**as-of / 不晚于 \(t\) 的最近一个 tape 点**。
4. **Leave-one-out**：给某条 subject 事件定价时，排除该事件自己的 entry/exit print（用 `entry_deal_id`/`exit_deal_id` 识别），避免 offset=0 时用自己的成交价 mark 自己。
5. **最大陈旧度**：`DEFAULT_MAX_REFERENCE_AGE_MS = 60_000`。若最近可用 print 距查询时刻超过 60s，记为缺失（NaN），该观测不参与该 horizon 的加权均值。

伪代码：

```text
tape = median_by_timestamp(all entry/exit prints)
ref(event, t) =
  leave_one_out_as_of(tape, t, exclude=event)
  if t - print_time > 60_000ms → None
```

---

## 4. 单笔 Markout 公式

设 offset 为相对事件时刻的毫秒偏移 \(\Delta\)（可正可负）。

### 4.1 Entry markout（相对开仓）

锚定时刻：`ts_ms + Δ`  
锚定价格：`P_entry = entry_price`  
方向：`d_entry = +1`（buy/long）或 `-1`（sell/short）

\[
\mathrm{MO}_{\mathrm{entry}}(\Delta)
= d_{\mathrm{entry}} \cdot \frac{\mathrm{ref}(\mathrm{ts\_ms}+\Delta) - P_{\mathrm{entry}}}{P_{\mathrm{entry}}} \cdot 10000
\]

含义：开仓后价格往客户有利方向走 → 正。

### 4.2 Exit markout（相对平仓）

锚定时刻：`exit_ms + Δ`  
锚定价格：`P_exit = exit_price`  
方向：**与开仓相反**（平仓单方向）：`d_exit = -d_entry`

\[
\mathrm{MO}_{\mathrm{exit}}(\Delta)
= d_{\mathrm{exit}} \cdot \frac{\mathrm{ref}(\mathrm{exit\_ms}+\Delta) - P_{\mathrm{exit}}}{P_{\mathrm{exit}}} \cdot 10000
\]

### 4.3 Combined markout

对同一 matched trade、同一 \(\Delta\)：

\[
\mathrm{MO}_{\mathrm{combined}}(\Delta)
= \frac{\mathrm{MO}_{\mathrm{entry}}(\Delta) + \mathrm{MO}_{\mathrm{exit}}(\Delta)}{2}
\]

任一侧缺失（NaN）→ combined 缺失。这是 **pair 内 entry/exit 等权**；跨交易聚合仍用 turnover 加权。

### 4.4 数值例子

- 买入 `entry_price=100`，`Δ=+100ms` 时 `ref=101` → entry markout = `+100 bps`
- 卖出 `entry_price=100`，`ref=99` → entry markout = `+100 bps`
- 多头平仓 `exit_price=100`，`ref=99` → exit markout = `+100 bps`（平仓后价格继续下跌，对空平有利）

---

## 5. 聚合：成交额加权（必须）

对一组观测 \(\{(m_i, w_i)\}\)，其中 \(m_i\) 为某 horizon 的 markout（bps），\(w_i=\mathrm{turnover}_i\)：

\[
\bar{m}_w = \frac{\sum_{i:\, m_i\text{ finite},\, w_i>0} m_i w_i}{\sum_{i:\, m_i\text{ finite},\, w_i>0} w_i}
\]

**不要**用 \(\frac{1}{n}\sum m_i\)。

加权 t-stat（检验 \(H_0:\bar{m}_w=0\)）：

- 加权方差：\(\sigma_w^2 = \sum w_i (m_i-\bar{m}_w)^2 / \sum w_i\)
- 有效样本量：\(n_{\mathrm{eff}} = (\sum w_i)^2 / \sum w_i^2\)
- \(t = \bar{m}_w / \sqrt{\sigma_w^2 / n_{\mathrm{eff}}}\)

分位数（p05/p20/…）、胜率（win rate）仍按 **笔** 计算（描述分布），但报告的 **mean markout 曲线必须是 turnover 加权**。

---

## 6. 时间轴（Horizons）

### 6.1 统计网格（CSV / 用户表）

```text
DEFAULT_OFFSETS_MS =
  -10000, -5000, -1000, -500, -100, -50, -10,
  0,
  10, 50, 100, 250, 500, 1000, 2000, 5000, 10000
```

单位：毫秒。负值 = 事件发生前，正值 = 事件发生后。

### 6.2 画图网格（更密）

- 窗口：`± DEFAULT_PLOT_WINDOW_MS = ±5000 ms`
- 约 `DEFAULT_PLOT_SAMPLES = 400` 个点：对称、近对数间距（`generate_plot_offsets`）
- 用于 SVG 曲线；统计表仍用上面的粗网格

### 6.3 分类常用 horizon

- Primary：`+1000 ms`
- Consistency：`+500, +1000, +2000 ms`

---

## 7. 分组曲线怎么算

对每个 group（side / size / holding / login / candidate vs control）：

1. 筛出该组事件集合 \(G\)
2. 对每个 offset \(\Delta\)，取 \(\{m_i(\Delta), w_i\}_{i\in G}\)
3. 曲线点 \(y(\Delta) = \) turnover 加权均值
4. `counts[group] = |G|`（事件笔数，仅作覆盖率注释）

### 7.1 分桶定义

**Side**

- `buy (long)`：`action == 0`
- `sell (short)`：`action == 1`

**Size**（`lots = volume / 100`）

- `size < 0.1 lot`
- `0.1 <= size < 1 lot`
- `size >= 1 lot`

**Holding**（`holding_ms`）

- `hold <= 1s`
- `1s < hold <= 5s`
- `5s < hold <= 1m`
- `hold > 1m`

Size 图额外输出 **未加权** 分位数曲线 p05/p20/p80/p95（诊断用）；**mean 线仍是 turnover 加权**。

---

## 8. 按用户聚合

对每个 `login`（通常要求 `events >= 50`）：

1. 取其全部 matched trades
2. 对每个统计 offset，算 turnover 加权 mean → `mean_{offset}ms_bps`
3. Primary horizon（+1000ms）：加权 mean / 加权 std / 加权 t-stat，以及按笔的 median、p05、p20、win rate
4. 用这些特征做 toxic / latency-arb 分类（见 `classify_abusive_users`；细节可随阈值变，但 **输入的 mean 必须是加权的**）

排序 / Top-Bottom 用户图：按 `mean_1000ms_bps`（turnover 加权）排序。

---

## 9. 怎么画图（给 AI 复现）

### 9.1 曲线数据结构

```text
curves[group_name][offset_ms] = weighted_mean_bps | None
counts[group_name] = n_events
```

例：

```json
{
  "buy (long)": {"-1000": -0.12, "0": 0.01, "1000": 0.45},
  "sell (short)": {"-1000": 0.05, "0": 0.00, "1000": -0.20}
}
```

### 9.2 图类型（本仓库产出）

| 图 | 含义 |
|---|---|
| `{kind}_markout_by_side.svg` | 买/卖分组曲线 |
| `{kind}_markout_by_size.svg` | 手数分组；mean 实线 + 分位数虚线 |
| `{kind}_markout_by_holding.svg` | 持仓时长分组 |
| `{kind}_top_users.svg` / `_bottom_users.svg` | 按 +1s 加权 mean 排序的用户 |
| `{kind}_candidate_vs_control.svg` | 标记用户 vs 其余用户 |
| `shape_*.svg` | 用户曲线形态诊断 |

`kind ∈ {entry, exit, combined}`。兼容旧文件名：`markout_by_*.svg` = entry。

### 9.3 坐标与样式要求

- **X 轴**：offset（ms），使用 **symlog**（零附近线性，远处对数），便于同时看 ±几 ms 与 ±几秒
- **Y 轴**：markout（bps），线性；画 `y=0` 参考虚线
- **每条曲线**：一个 group；图例写 `group (n=counts)`
- **标题**：含 symbol、kind、分组维度
- **不要**把 \$1k 与 \$1M 的单子等权进 mean

### 9.4 最小可运行伪代码

```python
# 1) load matched trades with turnover
# 2) build leave-one-out reference tape from all entry/exit prints
# 3) for each event i, each offset d:
#      entry_mo[i,d] = dir_entry * (ref(ts+d) - entry_px) / entry_px * 1e4
#      exit_mo[i,d]  = dir_exit  * (ref(exit+d) - exit_px) / exit_px * 1e4
#      comb_mo[i,d]  = 0.5 * (entry_mo + exit_mo) if both finite
# 4) for each group G and offset d:
#      y[G,d] = sum(mo[i,d]*turnover[i]) / sum(turnover[i])  # finite only
# 5) plot y vs d (symlog x), one line per group
```

---

## 10. 端到端流水线（本仓库）

```text
risk.dwd_matched_trades
        │ export_local_data.py
        ▼
local_data/.../Parquet + manifest
        │ markout_yearly/run.py
        │   └─ markout_output/run.py (单窗口)
        │        └─ markout_core (engine + reports + plots)
        ▼
markout_yearly/{YYYY-MM,full_year}/
  ├── user_markout_stats.csv          # 全用户加权统计
  ├── abusive_users.csv / abusive_summary.md
  ├── {entry,exit,combined}_*.csv/svg # 三类 markout 完整矩阵
  ├── reference_price_tape.csv
  └── markout_by_*.svg                # entry 兼容别名
```

跑批：

```bash
.venv/bin/python markout_yearly/run.py
```

单窗口：

```bash
.venv/bin/python markout_output/run.py \
  --start "2026-06-01 00:00:00" --end "2026-07-01 00:00:00" \
  --out-dir /tmp/markout_demo
```

---

## 11. 实现入口（代码地图）

| 模块 | 职责 |
|---|---|
| `markout_core/core.py` | 公式、tape、`MarkoutEngine`、turnover 权重、加权统计 |
| `markout_core/curves.py` | 分组曲线（加权） |
| `markout_core/users.py` | 用户统计、分类、matrix 聚合 |
| `markout_core/shapes.py` | 用户曲线形态 |
| `markout_core/plots.py` | SVG / symlog 坐标 |
| `markout_core/reports.py` | Markdown + 完整输出矩阵 |
| `markout_core/data.py` | 本地 Parquet / manifest |
| `markout_yearly/run.py` | 按月 + full_year 批处理 |

---

## 12. 常见错误（AI 实现时务必避开）

1. **按笔简单平均** markout → 错误；必须用 `turnover` 加权。
2. 用独立 tick mid，却声称与本项目一致 → 本项目参考价是 **成交 print tape + leave-one-out**。
3. Exit 仍用开仓方向 → 错误；exit 方向取反。
4. Combined 对 entry/exit **跨交易**再平均一次导致双重计数 → pair 内先平均，再跨交易用 turnover 加权。
5. Offset=0 不排除自身 print → 人为把 markout 拉向 0。
6. 忽略 60s 参考价陈旧截断 → 稀疏时段会用过时价。
7. 把 `volume`（盎司）当成 USD 权重 → 权重必须是 **`turnover`**。

---

## 13. 验收检查清单

- [ ] 单笔公式与第 4 节一致（entry / exit / combined）
- [ ] 参考价为 leave-one-out as-of print，最大年龄 60s
- [ ] 所有报告的 mean 曲线 / `mean_*ms_bps` / `mo_mean_primary_bps` 为 turnover 加权
- [ ] \$1k 与 \$1M 单子权重约为 1 : 1000（若 turnover 差 1000 倍）
- [ ] 图：X=symlog(offset)，Y=bps，含 y=0，分组图例带 n
- [ ] 同时产出 entry / exit / combined 三套结果

---

*文档对应实现版本：turnover 加权 markout（`markout_core.event_notional_usd` 优先读 `turnover`）。*
