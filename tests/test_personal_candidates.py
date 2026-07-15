from app.personal_candidates import load_personal_candidates


def test_personal_candidate_loader_deduplicates_logins_and_skips_invalid_rows(tmp_path):
    path = tmp_path / "candidates.csv"
    path.write_text(
        "month,login,trades,winrate,mean_bps\n"
        "2026-05,101,20,0.6,1.2\n"
        "2026-06,101,22,0.7,1.3\n"
        "2026-05,102,20,0.5,0.2\n"
        "2026-05,not-a-login,20,0.5,0.2\n"
        "2026-05,,20,0.5,0.2\n"
    )

    result = load_personal_candidates(path)

    assert result.status == "ready"
    assert result.login_ids == frozenset({101, 102})
    assert result.raw_rows == 5
    assert result.unique_logins == 2
    assert result.invalid_rows == 2
    assert result.duplicate_rows == 1


def test_personal_candidate_loader_handles_missing_file(tmp_path):
    result = load_personal_candidates(tmp_path / "missing.csv")

    assert result.status == "missing"
    assert result.login_ids == frozenset()
