import pytest
from pydantic import ValidationError
import importlib


def _load_snapshot_refresh():
    try:
        return importlib.import_module("app.snapshot_refresh")
    except ImportError as exc:
        pytest.fail(f"snapshot refresh module is not implemented: {exc}")


def _load_request_model():
    models = importlib.import_module("app.models")
    model = getattr(models, "SnapshotRefreshRequest", None)
    if model is None:
        pytest.fail("SnapshotRefreshRequest is not implemented")
    return model


def test_refresh_snapshots_builds_all_three_payloads_with_current_selection(monkeypatch, tmp_path):
    snapshot_refresh = _load_snapshot_refresh()
    calls = []
    monkeypatch.setattr(
        snapshot_refresh,
        "risk_build_snapshot",
        lambda start, end, platforms: calls.append(("risk", start, end, platforms)) or {"records": [{"login": 1}]},
    )
    monkeypatch.setattr(
        snapshot_refresh,
        "avg_profit_build_snapshot",
        lambda start, end, platforms: calls.append(("avg_profit", start, end, platforms)) or {"records": [{"login": 1}]},
    )
    monkeypatch.setattr(
        snapshot_refresh,
        "martingale_build_snapshot",
        lambda start, end, platforms: calls.append(("martingale", start, end, platforms)) or {"records": [{"login": 1}]},
    )
    paths = {
        "risk": tmp_path / "risk.json",
        "avg_profit": tmp_path / "avg_profit.json",
        "martingale": tmp_path / "martingale.json",
    }
    monkeypatch.setattr(snapshot_refresh, "snapshot_paths", lambda: paths)

    result = snapshot_refresh.refresh_snapshots("2026-05-01", "2026-06-30", ["mt4", "mt5", "hh_mt5"])

    assert result["status"] == "ready"
    assert {(name, start, end) for name, start, end, _ in calls} == {
        ("risk", "2026-05-01", "2026-06-30"),
        ("avg_profit", "2026-05-01", "2026-06-30"),
        ("martingale", "2026-05-01", "2026-06-30"),
    }
    assert all(path.exists() for path in paths.values())
    assert all(platforms == ["mt4", "mt5", "hh_mt5"] for _, _, _, platforms in calls)


def test_refresh_snapshots_keeps_existing_files_when_a_builder_fails(monkeypatch, tmp_path):
    snapshot_refresh = _load_snapshot_refresh()
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


def test_snapshot_refresh_request_rejects_empty_or_unsupported_platforms():
    SnapshotRefreshRequest = _load_request_model()
    with pytest.raises(ValidationError):
        SnapshotRefreshRequest(
            selection={"start": "2026-05-01", "end": "2026-06-30"},
            platforms=[],
        )
    with pytest.raises(ValidationError):
        SnapshotRefreshRequest(
            selection={"start": "2026-05-01", "end": "2026-06-30"},
            platforms=["other"],
        )


def test_snapshot_refresh_request_rejects_reversed_selection_dates():
    SnapshotRefreshRequest = _load_request_model()
    with pytest.raises(ValidationError):
        SnapshotRefreshRequest(
            selection={"start": "2026-06-30", "end": "2026-05-01"},
            platforms=["mt5"],
        )
