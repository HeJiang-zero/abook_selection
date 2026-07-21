from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.r4 import R4_SELECTION_END, R4_SELECTION_START, build_r4_records


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = Path("/Users/jianghe/holding_buckets/account_holding_buckets.csv")
DEFAULT_OUTPUT_PATH = BASE_DIR / "data" / "r4_snapshot.json"


def source_path() -> Path:
    return Path(os.getenv("ABOOK_R4_SOURCE_PATH", str(DEFAULT_SOURCE_PATH)))


def output_path() -> Path:
    return Path(os.getenv("ABOOK_R4_SNAPSHOT_PATH", str(DEFAULT_OUTPUT_PATH)))


def build_snapshot(selection_start: str, selection_end: str, platforms: list[str]) -> dict:
    path = source_path()
    if not path.exists():
        raise FileNotFoundError(f"R4 source CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        records = build_r4_records(csv.DictReader(handle), R4_SELECTION_START, R4_SELECTION_END, platforms)
    return {
        "selection_start": R4_SELECTION_START,
        "selection_end": R4_SELECTION_END,
        "platforms": sorted(set(platforms)),
        "window_type": "7D_SLIDING",
        "source_path": str(path),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local R4 Abook snapshot from 7D_SLIDING holding buckets")
    parser.add_argument("--selection-start", default="2026-05-01")
    parser.add_argument("--selection-end", default="2026-06-30")
    parser.add_argument("--platform", action="append", dest="platforms")
    args = parser.parse_args()
    platforms = args.platforms or ["mt4", "mt5", "hh_mt5"]
    payload = build_snapshot(args.selection_start, args.selection_end, platforms)
    output = output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"path": str(output), "records": len(payload["records"]), "source_path": payload["source_path"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
