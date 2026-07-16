import json

from app.martingale import load_martingale_snapshot


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
            "layer_hits": {"layer1": True},
        })
    path.write_text(json.dumps({
        "selection_start": "2026-05-01", "selection_end": "2026-06-30",
        "platforms": ["mt5"], "window_type": "7D_SLIDING", "records": records,
    }))

    snapshot = load_martingale_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])

    assert snapshot.summary()["blocked_users"] == 4
