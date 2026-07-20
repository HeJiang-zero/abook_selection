from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_PATH = BASE_DIR / "data" / "r4_snapshot.json"
R4_SELECTION_START = "2026-05-01"
R4_SELECTION_END = "2026-06-30"
# Operational thresholds use rounder, less brittle values than the research
# percentile cutoffs, while requiring a larger sample before routing.
R4_PRIMARY_TRADE_PCT = 0.35
R4_WIN_RATE = 0.55
R4_MIN_TRADES = 20
R4_MIN_PRIMARY_TRADES = 8


def snapshot_path() -> Path:
    return Path(os.getenv("ABOOK_R4_SNAPSHOT_PATH", str(DEFAULT_SNAPSHOT_PATH)))


def _parse_datetime(value: Any) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=None)


def _date_end_exclusive(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value) + timedelta(days=1), datetime.min.time())


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _window_features(platform: str, login: int, window_end: datetime, buckets: dict[str, dict[str, float]]) -> dict[str, Any]:
    total_trades = sum(int(item["trade_count"]) for item in buckets.values())
    total_wins = sum(int(item["winning_count"]) for item in buckets.values())
    for item in buckets.values():
        if item["trade_pct"] is None:
            item["trade_pct"] = item["trade_count"] / total_trades if total_trades else 0.0
    ordered = sorted(buckets.items(), key=lambda item: (item[1]["trade_pct"], item[1]["trade_count"]), reverse=True)
    primary_bucket, primary = ordered[0] if ordered else (None, {"trade_count": 0, "trade_pct": 0.0})
    top2 = {bucket for bucket, _ in ordered[:2]}
    profitable_buckets = [item for item in buckets.items() if item[1]["trade_count"] >= 3]
    best_bucket = max(
        profitable_buckets,
        key=lambda item: (item[1]["total_profit"], item[1]["trade_count"]),
        default=(None, {"trade_count": 0, "total_profit": 0.0}),
    )[0]
    soft_alignment = int(best_bucket is not None and best_bucket in top2)
    win_rate = total_wins / total_trades if total_trades else 0.0
    return {
        "platform": platform,
        "login": login,
        "window_end": window_end.date().isoformat(),
        "feat_week": window_end.date().isocalendar().week,
        "total_trades": total_trades,
        "total_wins": total_wins,
        "win_rate": round(win_rate, 8),
        "primary_bucket": primary_bucket,
        "primary_trade_pct": round(float(primary["trade_pct"]), 8),
        "primary_trades": int(primary["trade_count"]),
        "best_profit_bucket": best_bucket,
        "soft_alignment": soft_alignment,
        "avg_profit": round(sum(item["total_profit"] for item in buckets.values()) / total_trades, 8) if total_trades else None,
        "pass_r4": bool(
            soft_alignment == 1
            and primary["trade_pct"] >= R4_PRIMARY_TRADE_PCT
            and win_rate >= R4_WIN_RATE
            and total_trades >= R4_MIN_TRADES
            and primary["trade_count"] >= R4_MIN_PRIMARY_TRADES
        ),
    }


def build_r4_records(
    rows: Iterable[dict[str, Any]],
    selection_start: str,
    selection_end: str,
    platforms: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build one latest weekly R4 feature row per account from 7D_SLIDING data."""
    allowed_platforms = set(platforms or [])
    start = datetime.combine(date.fromisoformat(selection_start), datetime.min.time())
    end = _date_end_exclusive(selection_end)
    windows: dict[tuple[str, int, datetime], dict[str, dict[str, float]]] = {}
    for row in rows:
        if str(row.get("window_type", "")) != "7D_SLIDING":
            continue
        platform = str(row.get("platform", ""))
        if allowed_platforms and platform not in allowed_platforms:
            continue
        try:
            login = int(row["login"])
            window_end = _parse_datetime(row["window_end"])
        except (KeyError, TypeError, ValueError):
            continue
        if not start <= window_end < end:
            continue
        bucket = str(row.get("bucket", ""))
        if not bucket:
            continue
        key = (platform, login, window_end)
        item = windows.setdefault(key, {}).setdefault(
            bucket, {"trade_count": 0, "winning_count": 0, "total_profit": 0.0, "trade_pct": None}
        )
        item["trade_count"] += _int(row.get("trade_count"))
        item["winning_count"] += _int(row.get("winning_count"))
        item["total_profit"] += _number(row.get("total_profit"))
        if row.get("trade_pct") not in (None, ""):
            item["trade_pct"] = _number(row.get("trade_pct"))

    features = [
        _window_features(platform, login, window_end, buckets)
        for (platform, login, window_end), buckets in windows.items()
    ]
    weekly: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    for feature in features:
        parsed = date.fromisoformat(feature["window_end"])
        key = (feature["platform"], feature["login"], parsed.isocalendar().year, parsed.isocalendar().week)
        previous = weekly.get(key)
        if previous is None or feature["window_end"] > previous["window_end"]:
            weekly[key] = feature

    by_account: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for feature in weekly.values():
        by_account.setdefault((feature["platform"], feature["login"]), []).append(feature)
    records = []
    for key, account_features in by_account.items():
        passing_weeks = sum(1 for feature in account_features if feature["pass_r4"])
        latest = max(account_features, key=lambda feature: feature["window_end"])
        records.append({**latest, "r4_passing_weeks": passing_weeks})
    return sorted(records, key=lambda item: (item["platform"], item["login"]))


@dataclass(frozen=True)
class R4Snapshot:
    path: Path
    selection_start: Optional[str]
    selection_end: Optional[str]
    platforms: tuple[str, ...]
    window_type: str
    records: tuple[dict[str, Any], ...]
    status: str
    missing_platforms: tuple[str, ...] = ()

    def indexed_records(self) -> dict[tuple[str, int], dict[str, Any]]:
        return {(str(row["platform"]), int(row["login"])): row for row in self.records}

    def enrich_rows(self, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        indexed = self.indexed_records() if self.status in {"ready", "partial"} else {}
        enriched = []
        for row in rows:
            item = dict(row)
            record = indexed.get((str(row["platform"]), int(row["login"])))
            item.update({
                "r4_status": self.status,
                "r4_pass": bool(record and record.get("pass_r4")),
                "r4_passing_weeks": int(record.get("r4_passing_weeks", 0)) if record else 0,
                "r4_record": dict(record) if record else None,
            })
            if record:
                for key in ("window_end", "feat_week", "win_rate", "primary_bucket", "primary_trade_pct", "primary_trades", "best_profit_bucket", "soft_alignment", "total_trades", "avg_profit"):
                    item[f"r4_{key}"] = record.get(key)
            enriched.append(item)
        return enriched

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path": str(self.path),
            "selection_start": self.selection_start,
            "selection_end": self.selection_end,
            "platforms": list(self.platforms),
            "missing_platforms": list(self.missing_platforms),
            "window_type": self.window_type,
            "records": len(self.records),
            "passed_users": sum(1 for row in self.records if row.get("pass_r4")),
        }


def load_r4_snapshot(path: Path, selection_start: str, selection_end: str, platforms: list[str]) -> R4Snapshot:
    if not path.exists():
        return R4Snapshot(path, None, None, tuple(), "", tuple(), "missing")
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return R4Snapshot(path, None, None, tuple(), "", tuple(), "invalid")
    snapshot_platforms = tuple(sorted(str(value) for value in payload.get("platforms", [])))
    requested = tuple(sorted(str(value) for value in platforms))
    dates_match = payload.get("selection_start") == selection_start and payload.get("selection_end") == selection_end
    missing_platforms = tuple(sorted(set(requested) - set(snapshot_platforms)))
    status = "stale" if not dates_match else "partial" if missing_platforms else "ready"
    records = payload.get("records", [])
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        return R4Snapshot(path, None, None, tuple(), "", tuple(), "invalid")
    return R4Snapshot(
        path, payload.get("selection_start"), payload.get("selection_end"), snapshot_platforms,
        str(payload.get("window_type", "")), tuple(records) if status in {"ready", "partial"} else tuple(), status,
        missing_platforms,
    )


def build_r4_filter(request: Any) -> R4Snapshot:
    return load_r4_snapshot(
        snapshot_path(), R4_SELECTION_START, R4_SELECTION_END, request.platforms
    )
