from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from scripts.build_avg_profit_snapshot import build_snapshot as avg_profit_build_snapshot
from scripts.build_martingale_snapshot import build_snapshot as martingale_build_snapshot
from scripts.build_user_risk_snapshot import build_snapshot as risk_build_snapshot

from .avg_profit import snapshot_path as avg_profit_snapshot_path
from .martingale import snapshot_path as martingale_snapshot_path
from .risk import snapshot_path as risk_snapshot_path


_REFRESH_LOCK = threading.Lock()


def snapshot_paths() -> dict[str, Path]:
    return {
        "risk": risk_snapshot_path(),
        "avg_profit": avg_profit_snapshot_path(),
        "martingale": martingale_snapshot_path(),
    }


def _serialise(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def _temporary_path(path: Path, token: str, kind: str) -> Path:
    return path.with_name(f".{path.name}.{token}.{kind}")


def _restore_originals(originals: dict[Path, bytes | None], token: str) -> None:
    for path, content in originals.items():
        if content is None:
            path.unlink(missing_ok=True)
            continue
        restore_path = _temporary_path(path, token, "restore")
        restore_path.write_bytes(content)
        os.replace(restore_path, path)


def refresh_snapshots(
    selection_start: str,
    selection_end: str,
    platforms: list[str],
) -> dict[str, object]:
    """Build and atomically publish all local analysis snapshots."""
    builders: dict[str, Callable[[str, str, list[str]], dict[str, Any]]] = {
        "risk": risk_build_snapshot,
        "avg_profit": avg_profit_build_snapshot,
        "martingale": martingale_build_snapshot,
    }
    with _REFRESH_LOCK:
        paths = snapshot_paths()
        if len(set(paths.values())) != len(paths):
            return {
                "status": "error",
                "error": "snapshot paths must be unique",
                "snapshots": {},
            }

        token = uuid.uuid4().hex
        staged: dict[str, Path] = {}
        originals: dict[Path, bytes | None] = {}
        try:
            payloads = {
                name: builder(selection_start, selection_end, list(platforms))
                for name, builder in builders.items()
            }
            for name, path in paths.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                originals[path] = path.read_bytes() if path.exists() else None
                staged_path = _temporary_path(path, token, "tmp")
                staged_path.write_text(_serialise(payloads[name]), encoding="utf-8")
                staged[name] = staged_path

            for name, path in paths.items():
                os.replace(staged[name], path)

            return {
                "status": "ready",
                "selection_start": selection_start,
                "selection_end": selection_end,
                "snapshots": {
                    name: {
                        "status": "ready",
                        "path": str(paths[name]),
                        "records": len(payloads[name].get("records", [])),
                        "selection_start": selection_start,
                        "selection_end": selection_end,
                    }
                    for name in paths
                },
            }
        except Exception as exc:
            if originals:
                try:
                    _restore_originals(originals, token)
                except Exception as restore_exc:
                    return {
                        "status": "error",
                        "error": f"{exc}; snapshot rollback failed: {restore_exc}",
                        "snapshots": {},
                    }
            return {"status": "error", "error": str(exc), "snapshots": {}}
        finally:
            for temporary in staged.values():
                temporary.unlink(missing_ok=True)
            for path in paths.values():
                _temporary_path(path, token, "restore").unlink(missing_ok=True)
