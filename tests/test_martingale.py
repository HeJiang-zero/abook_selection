import json

from app.martingale import load_martingale_snapshot
from scripts.build_martingale_snapshot import _risk_level_for_row


def _record(
    login: int,
    *,
    level: str = "extreme",
    detection_status: str = "suspected",
    confirmed_windows: int = 1,
    confirmed_extreme_windows: int = 0,
    expanded_windows: int = 1,
):
    return {
        "platform": "mt5",
        "login": login,
        "risk_level": level,
        "detection_mode": "confirmed" if confirmed_windows else "expanded",
        "martingale_detection_status": detection_status,
        "confirmed_windows": confirmed_windows,
        "confirmed_extreme_windows": confirmed_extreme_windows,
        "expanded_windows": expanded_windows,
        "layer_hits": {"layer1": True, "layer3": True, "layer4": True},
    }


def _ready_snapshot(path, records):
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "window_type": "7D_SLIDING",
        "records": records,
    }))
    return load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])


def test_missing_snapshot_has_no_blocked_users_and_explicit_status(tmp_path):
    snapshot = load_martingale_snapshot(tmp_path / "missing.json", "2026-05-01", "2026-06-30", ["mt5"])

    assert snapshot.status == "missing"
    assert snapshot.blocked_logins(("extreme",)) == set()
    assert snapshot.summary()["status"] == "missing"


def test_ready_snapshot_enriches_rows_with_layer_details(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "window_type": "7D_SLIDING",
        "records": [{
            "platform": "mt5",
            "login": 7,
            "risk_level": "high",
            "martingale_detection_status": "confirmed",
            "confirmed_windows": 2,
            "confirmed_extreme_windows": 0,
            "expanded_windows": 0,
            "layer_hits": {
                "layer1": True,
                "layer2": True,
                "layer3": True,
                "layer4": True,
                "layer5": False,
            },
        }],
    }))

    snapshot = load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])
    row = snapshot.enrich_rows([{"platform": "mt5", "login": 7}])[0]

    assert row["martingale_status"] == "ready"
    assert row["martingale_risk_level"] == "high"
    assert row["martingale_layer_hits"]["layer4"] is True


def test_snapshot_with_malformed_record_is_invalid(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "window_type": "7D_SLIDING",
        "records": [{"platform": "mt5", "login": 7}],
    }))

    snapshot = load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])

    assert snapshot.status == "invalid"
    assert snapshot.summary()["status"] == "invalid"


def test_default_martingale_summary_blocks_all_detected_levels(tmp_path):
    path = tmp_path / "snapshot.json"
    records = []
    for login, level in enumerate(("extreme", "high", "medium", "low"), start=1):
        records.append({
            "platform": "mt5", "login": login, "risk_level": level,
            "martingale_detection_status": "confirmed",
            "confirmed_windows": 2,
            "confirmed_extreme_windows": 2 if level == "extreme" else 0,
            "expanded_windows": 0,
            "layer_hits": {"layer1": True},
        })
    path.write_text(json.dumps({
        "selection_start": "2026-05-01", "selection_end": "2026-06-30",
        "platforms": ["mt5"], "window_type": "7D_SLIDING", "records": records,
    }))

    snapshot = load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])

    assert snapshot.summary()["blocked_users"] == 4
    assert snapshot.summary()["confirmed_level_counts"] == {
        "extreme": 1, "high": 1, "medium": 1, "low": 1,
    }


def test_single_extreme_candidate_is_suspected_and_not_blocked(tmp_path):
    snapshot = _ready_snapshot(tmp_path / "snapshot.json", [_record(7)])

    assert snapshot.blocked_logins(("extreme",)) == set()
    row = snapshot.enrich_rows([{"platform": "mt5", "login": 7}])[0]
    assert row["martingale_status"] == "ready"
    assert row["martingale_detection_status"] == "suspected"


def test_repeated_confirmed_extreme_is_hard_blocked(tmp_path):
    snapshot = _ready_snapshot(
        tmp_path / "snapshot.json",
        [_record(7, detection_status="confirmed", confirmed_windows=2, confirmed_extreme_windows=2)],
    )

    assert snapshot.blocked_logins(("extreme",)) == {("mt5", 7)}
    assert snapshot.summary()["confirmed_users"] == 1
    assert snapshot.summary()["suspected_users"] == 0


def test_snapshot_with_missing_requested_platform_is_partial_not_globally_stale(tmp_path):
    path = tmp_path / "snapshot.json"
    snapshot = _ready_snapshot(
        path,
        [_record(7, detection_status="confirmed", confirmed_windows=2, confirmed_extreme_windows=2)],
    )

    mixed = load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5", "mt4"])

    assert mixed.status == "partial"
    assert mixed.missing_platforms == ("mt4",)
    assert mixed.indexed_records()[("mt5", 7)]["risk_level"] == "extreme"
    assert mixed.blocked_logins(("extreme",)) == {("mt5", 7)}


def test_old_snapshot_without_detection_fields_is_not_ready(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "window_type": "7D_SLIDING",
        "records": [{
            "platform": "mt5",
            "login": 7,
            "risk_level": "extreme",
            "layer_hits": {"layer1": True},
        }],
    }))

    snapshot = load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])

    assert snapshot.status == "invalid"


def test_confirmed_user_does_not_inherit_broad_extreme_level_without_strict_extreme():
    row = {
        "confirmed_windows": 3,
        "confirmed_extreme_tier_windows": 0,
        "confirmed_high_tier_windows": 0,
        "confirmed_medium_tier_windows": 0,
        "confirmed_low_tier_windows": 3,
        "extreme_windows": 1,
        "high_windows": 0,
        "medium_windows": 0,
        "low_windows": 0,
    }

    assert _risk_level_for_row(row, "confirmed") == "low"
