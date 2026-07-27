# Local matched_trades Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Download the rolling-year MT5/MT4 matching inputs locally and append any missing FIFO-matched trades to the local Warehouse without issuing writes to ClickHouse.

**Architecture:** Keep the FIFO algorithm in a pure Python module that accepts normalized deal dictionaries and bootstrap open entries. Keep ClickHouse extraction, local Parquet archival, local merge, and manifest updates in a separate CLI script. The CLI computes only after the local Warehouse’s current matched-trade frontier, bootstraps from read-only `dwd_match_trades_open`, and merges by the stable five-column trade key.

**Tech Stack:** Python 3.9, `clickhouse-connect`, PyArrow Parquet, standard library `datetime`/`deque`, pytest.

## Global Constraints

- ClickHouse access is read-only: only `SELECT`, `DESCRIBE`, and metadata reads are allowed; never call `insert_df` or execute `INSERT`, `ALTER`, `DELETE`, or `OPTIMIZE`.
- The requested window is `[2025-07-27, 2026-07-27)` and platforms are `mt4`, `mt5`, and `hh_mt5`.
- MT5 inputs must use `FINAL`, `action IN (0, 1)`, `entry <> 3`, `is_deleted = 0`, and `volume_ext / 1e8`; MT4 inputs must use `action IN (0, 1)` and raw decimal volume.
- FIFO grouping is `(login, platform, symbol)`; sorting is by event time and deal/split ID; volume tolerance is `0.0001`.
- Existing user changes remain untouched. Local writes use temporary files followed by `os.replace`, and the manifest publishes last.
- Input downloads use day-sized Parquet chunks with up to three retries; completed month/day files are resumed rather than downloaded again.
- The local matched-trades Parquet schema remains the existing 14-column Warehouse projection; `exchange_rate` is used in calculations but not added to existing output partitions.

---

## Task 1: Add pure FIFO matching and bootstrap helpers

**Files:**
- Create: `app/matched_trades_fifo.py`
- Test: `tests/test_matched_trades_fifo.py`

**Interfaces:**
- `fifo_match(deals: list[dict], initial_entries: list[dict] | None = None) -> tuple[list[dict], list[dict], list[dict]]` returns `(matched, unmatched_entries, unmatched_exits)` with normalized output fields.
- `matched_trade_key(row: dict) -> tuple[str, int, str, int, int]` returns `(platform, login, symbol, entry_deal_id, exit_deal_id)`.
- `load_initial_entries(rows: Iterable[dict]) -> list[dict]` normalizes open-table rows into queue entries with `remaining` above the tolerance.

- [ ] **Step 1: Write failing unit tests**

Add tests for:

```python
def test_fifo_matches_partial_long_close_in_time_then_deal_order():
    deals = [
        deal(1, "2026-07-25T00:00:00.001", 0, 1.0, 1.10),
        deal(2, "2026-07-25T00:00:00.001", 1, 0.4, 1.20),
    ]
    matched, entries, exits = fifo_match(deals)
    assert [(row["entry_deal_id"], row["exit_deal_id"], row["volume"]) for row in matched] == [(1, 2, 0.4)]
    assert entries == [] and exits == []

def test_fifo_splits_reverse_trade_into_close_and_new_open():
    matched, entries, exits = fifo_match([
        deal(1, "2026-07-25T00:00:00", 0, 1.0, 100.0),
        deal(2, "2026-07-25T00:00:01", 1, 1.5, 90.0),
    ])
    assert matched[0]["direction"] == "Long"
    assert matched[0]["volume"] == 1.0
    assert entries[0]["remaining"] == 0.5
    assert entries[0]["direction"] == "Short"

def test_bootstrap_entries_preserve_entry_deal_id_and_ignore_zero_remaining():
    entries = load_initial_entries([open_row(11, 0.5), open_row(12, 0.0)])
    assert [item["deal_id"] for item in entries] == [11]

def test_matched_trade_key_is_idempotent():
    assert matched_trade_key(row("mt4", 7, "EURUSD", 11, 12)) == ("mt4", 7, "EURUSD", 11, 12)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest tests/test_matched_trades_fifo.py -q`

Expected: collection or assertion failures because `app.matched_trades_fifo` does not yet exist.

- [ ] **Step 3: Implement the smallest pure FIFO module**

Normalize timestamps to `datetime`, use `deque` for long/short queues, calculate long profit as `(exit - entry) * matched * rate`, short profit as `(entry - exit) * matched * rate`, calculate turnover as `(entry + exit) * matched * rate`, and report residual queue entries and unmatched closing volume. Keep login/platform/symbol on every emitted row.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `pytest tests/test_matched_trades_fifo.py -q`

Expected: all FIFO tests pass with no warnings or errors.

- [ ] **Step 5: Commit the isolated FIFO change**

Run: `git add app/matched_trades_fifo.py tests/test_matched_trades_fifo.py && git commit -m "feat: add local matched trade fifo matcher"`

## Task 2: Add read-only input extraction and local archive helpers

**Files:**
- Create: `app/matched_trades_local.py`
- Test: `tests/test_matched_trades_local.py`

**Interfaces:**
- `mt5_deals_query(start: datetime, end: datetime, platforms: list[str]) -> tuple[str, dict]` returns the parameterized read-only query and parameters.
- `mt4_deals_query(start: datetime, end: datetime) -> tuple[str, dict]` returns the parameterized read-only query and parameters.
- `open_entries_query(cutoff: datetime) -> tuple[str, dict]` returns an as-of query using `argMax(..., snapshot_at)` from `risk.dwd_match_trades_open FINAL`.
- `write_query_stream(client, query, params, target: Path) -> int` writes one Arrow stream atomically.
- `partition_month(value: datetime | date | str) -> str` returns `YYYY-MM`.

- [ ] **Step 1: Write failing tests for query safety and atomic archive writes**

Assert the generated queries contain `FINAL`, the required filters, no mutation keywords, and the correct volume conversions. Use a fake Arrow stream to verify a Parquet target is published and temporary files are removed after success; use a failing stream to verify the target is not published.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest tests/test_matched_trades_local.py -q`

Expected: failures because the new module and helpers are absent.

- [ ] **Step 3: Implement read-only queries and atomic Arrow writing**

Use explicit column aliases matching the FIFO module. Fetch MT5 `time_msc`, `deal`, `position_id`, `rate_profit`, and `contract_size`; fetch MT4 `deal_time`, `split_id`, `ticket`, `conv_rate`, and `contract_size`. Keep all query parameters explicit and reject any query string containing mutation keywords before execution.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `pytest tests/test_matched_trades_local.py -q`

Expected: all archive/query tests pass.

- [ ] **Step 5: Commit the extraction helpers**

Run: `git add app/matched_trades_local.py tests/test_matched_trades_local.py && git commit -m "feat: add matched trade input archive helpers"`

## Task 3: Add local merge, deduplication, and manifest helpers

**Files:**
- Modify: `app/matched_trades_local.py`
- Test: `tests/test_matched_trades_local.py`

**Interfaces:**
- `load_local_matched_month(path: Path) -> list[dict]` reads an existing output month.
- `merge_matched_rows(existing: Iterable[dict], additions: Iterable[dict]) -> list[dict]` keeps one row per `matched_trade_key`, preferring additions only when the key was not already present.
- `write_matched_month(path: Path, rows: Iterable[dict]) -> int` writes the canonical 14-column schema atomically and sorts by exit time and key.
- `update_matched_manifest(manifest: dict, month_rows: dict[str, int], updated_at: str) -> dict` updates only matched-trade row totals/month counts and generation metadata.

- [ ] **Step 1: Write failing tests for merge idempotency and preservation**

Cover duplicate additions, existing rows winning on duplicate keys, preserving unrelated months, exact canonical column order, and rollback behavior when an atomic write fails.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest tests/test_matched_trades_local.py -q -k 'merge or month or manifest'`

Expected: failures for the missing merge/write functions.

- [ ] **Step 3: Implement schema-safe local merge**

Use PyArrow to read/write Parquet. Convert Decimal values to the existing numeric types, ensure UInt64 IDs stay unsigned, partition by `exit_time` (falling back to `entry_time` only for open rows), and use `os.replace` for publication. Do not remove or rewrite unaffected month directories.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `pytest tests/test_matched_trades_local.py -q`

Expected: all local archive and merge tests pass.

- [ ] **Step 5: Commit the merge layer**

Run: `git add app/matched_trades_local.py tests/test_matched_trades_local.py && git commit -m "feat: merge local matched trade partitions idempotently"`

## Task 4: Build the refresh CLI with a dry-run mode and read-only guard

**Files:**
- Create: `scripts/refresh_matched_trades_local.py`
- Modify: `data/README.md`
- Test: `tests/test_refresh_matched_trades_local.py`

**Interfaces:**
- `parse_args(argv) -> argparse.Namespace` accepts `--start`, `--end`, `--platform`, `--warehouse-path`, `--input-path`, and `--dry-run`.
- `run_refresh(args, client=None) -> dict` returns JSON-serializable counts for downloaded rows, bootstrap rows, computed rows, additions, unmatched exits, affected months, and remote write attempts (always zero).
- `main(argv=None) -> int` loads `.env`, runs the command, and prints a JSON summary.

- [ ] **Step 1: Write failing CLI tests**

Test that the default dates are `2025-07-27` and `2026-07-27`, platform validation accepts exactly the three supported platforms, dry-run performs no client query and no local write, and a fake client receives only `SELECT`/`DESCRIBE` SQL. Test a temporary Warehouse with an existing July partition: the refresh adds a missing key once and the second run adds zero rows.

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `pytest tests/test_refresh_matched_trades_local.py -q`

Expected: failures because the CLI does not yet exist.

- [ ] **Step 3: Implement the CLI workflow**

Use the rolling-year window for archival. Determine the local frontier from existing matched output, use the latest open-entry state at or before the frontier as bootstrap, download process deals from that bootstrap timestamp through `end`, group by `(login, platform, symbol)`, call `fifo_match`, filter additions to the requested exit window, merge by key, rewrite only affected output months, and publish input/output manifests last. If no valid bootstrap exists for a non-empty existing Warehouse, fail before writing.

- [ ] **Step 4: Add operator documentation**

Document the read-only command and the exact output paths in `data/README.md`, including a dry-run example and the JSON fields that prove remote writes are zero.

- [ ] **Step 5: Run CLI tests and verify GREEN**

Run: `pytest tests/test_refresh_matched_trades_local.py -q`

Expected: all CLI tests pass and the second refresh is idempotent.

- [ ] **Step 6: Commit the CLI**

Run: `git add scripts/refresh_matched_trades_local.py data/README.md tests/test_refresh_matched_trades_local.py && git commit -m "feat: refresh local matched trades from readonly inputs"`

## Task 5: Execute the real local refresh and reconcile read-only

**Files:**
- Modify: `data/matched_trades_inputs/` (generated local Parquet and manifest)
- Modify: `data/warehouse/dwd_matched_trades/month=2026-07/part.parquet` (generated local output)
- Modify: `data/warehouse/manifest.json` (generated metadata)

- [ ] **Step 1: Run dry-run and inspect the plan**

Run: `.venv/bin/python scripts/refresh_matched_trades_local.py --start 2025-07-27 --end 2026-07-27 --dry-run`

Expected: JSON identifies the rolling-year archive, local frontier, bootstrap cutoff, affected month, and `remote_write_attempts: 0` without changing files.

- [ ] **Step 2: Run the real read-only refresh**

Run: `.venv/bin/python scripts/refresh_matched_trades_local.py --start 2025-07-27 --end 2026-07-27`

Expected: raw MT5/MT4 inputs are written under `data/matched_trades_inputs/`, only the missing local matched rows are added, and the command reports zero remote write attempts.

- [ ] **Step 3: Verify local idempotency and schema**

Run the same command a second time, then inspect Parquet schemas, duplicate keys, per-platform counts, min/max exit times, and `git status --short`. Expected: `added_rows: 0` on the second run, no duplicate keys, and no changes outside generated data plus the intended code/docs files.

- [ ] **Step 4: Reconcile against ClickHouse read-only**

Run a separate `SELECT` query against `risk.dwd_matched_trades FINAL` for `[2026-07-25, 2026-07-27)`, comparing counts, unique keys, sum(profit), sum(turnover), and max(exit_time) to the local output. Any difference is reported with platform and key samples; no remote mutation is attempted.

If the read-only comparison shows an irrecoverable historical bootstrap mismatch, rerun with `--remote-reconcile --reconcile-start YYYY-MM-DDTHH:MM:SS`; this reads the authoritative remote rows for only that interval and replaces the local interval without issuing a remote write.

- [ ] **Step 5: Run the full verification suite**

Run: `pytest -q`

Expected: exit code 0 with all repository tests passing; report the exact count and any pre-existing warnings.
