import json

from app.risk import load_risk_snapshot
from app.models import AnalysisRequest


def test_risk_snapshot_filters_positive_balance_but_keeps_nonpositive_balance(tmp_path):
    path = tmp_path / "risk.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "records": [
            {"platform": "mt5", "login": 1, "balance_prev_month": 1000,
             "average_open_degree": 1, "peak_leverage_ratio": 3,
             "balance_status": "positive"},
            {"platform": "mt5", "login": 2, "balance_prev_month": 1000,
             "average_open_degree": 1, "peak_leverage_ratio": 8,
             "balance_status": "positive"},
            {"platform": "mt5", "login": 3, "balance_prev_month": 0,
             "average_open_degree": None, "peak_leverage_ratio": None,
             "balance_status": "unknown_nonpositive_balance"},
        ],
    }))

    snapshot = load_risk_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])

    assert snapshot.status == "ready"
    assert snapshot.allowed_logins(5) == {("mt5", 1), ("mt5", 3)}
    enriched = snapshot.enrich_rows([{"platform": "mt5", "login": 3}])[0]
    assert enriched["risk_balance_status"] == "unknown_nonpositive_balance"
    assert enriched["risk_peak_leverage_ratio"] is None


def test_risk_filter_detects_explicit_login_removed_by_leverage(tmp_path):
    path = tmp_path / "risk.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "records": [{"platform": "mt5", "login": 2, "balance_prev_month": 1000,
                     "peak_leverage_ratio": 8, "balance_status": "positive"}],
    }))
    snapshot = load_risk_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])
    from app.risk import LocalRiskFilter
    risk_filter = LocalRiskFilter(snapshot, snapshot.allowed_logins(5))
    request = AnalysisRequest(platforms=["mt5"], filters={"logins": [2]})
    assert risk_filter.is_empty_for(request)


def test_risk_snapshot_reports_missing_and_stale(tmp_path):
    missing = load_risk_snapshot(tmp_path / "missing.json", "2026-05-01", "2026-06-30", ["mt5"])
    assert missing.status == "missing"

    path = tmp_path / "stale.json"
    path.write_text(json.dumps({"selection_start": "2026-04-01", "selection_end": "2026-05-31", "platforms": ["mt5"], "records": []}))
    stale = load_risk_snapshot(path, "2026-05-01", "2026-06-30", ["mt5"])
    assert stale.status == "stale"


def test_large_ready_snapshot_remains_a_local_login_filter(tmp_path, monkeypatch):
    path = tmp_path / "large.json"
    path.write_text(json.dumps({
        "selection_start": "2026-05-01",
        "selection_end": "2026-06-30",
        "platforms": ["mt5"],
        "records": [
            {"platform": "mt5", "login": login, "balance_prev_month": 1000,
             "peak_leverage_ratio": 8, "balance_status": "positive"}
            for login in range(2500)
        ],
    }))
    monkeypatch.setenv("ABOOK_RISK_SNAPSHOT_PATH", str(path))
    from app.risk import build_local_risk_filter
    risk_filter = build_local_risk_filter(AnalysisRequest(platforms=["mt5"]))
    assert risk_filter.allowed_logins is None
    assert len(risk_filter.excluded_logins) == 2500
    assert risk_filter.sql_login_filter_applied is True
    assert risk_filter.summary()["filter_mode"] == "local_login_exclusion"
