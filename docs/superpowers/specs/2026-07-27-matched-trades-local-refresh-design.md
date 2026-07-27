# 本地 matched_trades 补数设计

## 目标

在不修改 ClickHouse 的前提下，补齐本地 `data/warehouse/dwd_matched_trades` 在滚动窗口 `[2025-07-27, 2026-07-27)` 内的缺失结果，并把用于复算的 MT5/MT4 原始成交数据保存到本地 `data/matched_trades_inputs/`，供后续项目和审计复用。

## 已确认的远端边界

- 平台范围：`mt4`、`mt5`、`hh_mt5`。
- 当前本地 matched trades 最晚到 2026-07-24；远端当前结果到 2026-07-27。
- 远端有效 MT5 deals、positions snapshot、MT4 positions snapshot 和 matched trades 的有效覆盖均从 2026-05-15 左右开始，因此不对远端没有有效输入的数据日期伪造匹配结果。
- ClickHouse 只执行 `SELECT` / `DESCRIBE` 查询；禁止执行 `INSERT`、`ALTER`、`DELETE`、`OPTIMIZE` 等写操作。

## 方案选择

### 方案 A：直接复制远端 `dwd_matched_trades`

实现最快，但没有使用指南中的本地 FIFO 逻辑，也不能留下完整原始输入作为复算依据，因此不采用。

### 方案 B：从一年前开始全量本地重算

理论上最直接，但窗口起点前的历史未平仓状态无法从当前快照完整还原，且会重复计算和重写数百万条既有结果，风险和资源开销都较高。

### 方案 C：下载完整近一年输入，按本地缺口增量 FIFO 复算（采用）

近一年 MT5 deals、MT4 split deals 保存为月分区 Parquet。实际补算从本地已有结果的最后时间点开始，使用远端 `dwd_match_trades_open` 在该时间点前的最新 entry 状态初始化 FIFO 队列，再处理之后的原始 deals。新结果按 `(login, platform, symbol, entry_deal_id, exit_deal_id)` 去重合并到本地现有 Parquet；ClickHouse 仍只读。

## 数据流与模块

### `app/matched_trades_fifo.py`

纯本地、无数据库依赖的撮合模块，提供：

- `fifo_match(deals, initial_entries)`：按 `(login, platform, symbol)` 的已排序成交执行指南中的净头寸拆分、FIFO 撮合、profit、turnover 和 holding seconds 计算。
- `matched_trade_key(row)`：返回稳定的五元唯一键，用于本地幂等合并。
- `load_initial_entries(rows)`：将 `dwd_match_trades_open` 的 entry 状态转换成 FIFO 队列，并按剩余量过滤。

计算输出保留本地 Warehouse 现有的 14 列投影（不改变现有查询契约）；`exchange_rate` 参与计算但不新增到已有 Parquet schema，避免同一月分区出现不兼容 schema。

### `scripts/refresh_matched_trades_local.py`

命令行入口负责：

1. 读取 `.env` 中的 ClickHouse 配置并建立只读客户端。
2. 拉取滚动窗口内的 MT5 deals 和 MT4 split deals，按月份原子写入 `data/matched_trades_inputs/`。
3. 找到本地 matched trades 的最后 exit 时间；拉取该时间点前最新的 `dwd_match_trades_open` 状态。
4. 拉取从冷启动状态时间到窗口结束的有效 MT5/MT4 deals，在每个 `(login, platform, symbol)` 组内按时间和 deal ID 排序后执行 FIFO。
5. 读取已有本地 matched trades，按唯一键合并新结果，只原子替换受影响月份的 Parquet 文件。
6. 更新输入数据 manifest 和 Warehouse manifest 的 affected-month 行数、generation 与更新时间。

### 本地文件边界

- 原始输入：`data/matched_trades_inputs/mt5_deals/month=YYYY-MM/part.parquet`、`mt4_trades_split/month=YYYY-MM/part.parquet`，以及 `manifest.json`。
- 业务输出：只写 `data/warehouse/dwd_matched_trades/month=YYYY-MM/part.parquet` 的受影响月份。
- 所有替换使用临时文件 + `os.replace`；失败时不发布半成品 manifest。

## 正确性与异常处理

- MT5 过滤 `action IN (0,1)`, `entry <> 3`, `is_deleted = 0`，volume 使用 `volume_ext / 1e8`；MT4 过滤 `action IN (0,1)`，volume 使用原始手数。
- FIFO 分组键严格包含 `login`、`platform`、`symbol`；排序键为毫秒时间和 deal/split ID。
- volume 比较使用 `0.0001` 容差；rate 为 0 或 NULL 时使用 1.0 并记录异常计数，不能静默产生 NaN。
- 若冷启动缺少可用的 open 状态且本地已有结果无法覆盖起算点，命令失败并说明缺失范围，不写入本地输出。
- 输出前检查 unmatched exits、负 holding seconds、非正 volume 和重复唯一键；异常记录到命令行 JSON 摘要。

## 验证

- 单元测试覆盖：多空 FIFO、部分平仓、反向开仓、同一时间 deal ID 排序、冷启动 entry、幂等去重和原子文件写入。
- 使用临时 Warehouse 做端到端测试，验证既有月份不变、受影响月份可重复运行且行数不增长。
- 实际运行后只读查询远端 `dwd_matched_trades FINAL`，以行数、唯一键集合、profit/turnover 合计和最大 exit 时间对账；对账差异只报告，不向远端写回。
