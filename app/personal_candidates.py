from __future__ import annotations

from dataclasses import dataclass
import csv
import os
from pathlib import Path


DEFAULT_PERSONAL_CANDIDATE_PATH = Path(
    os.getenv(
        "ABOOK_PERSONAL_CANDIDATE_LIST_PATH",
        "/Users/jianghe/gzkj_副本_notickdata/markout_yearly/may_june_mean_bps_gt_0.05_logins.csv",
    )
)


@dataclass(frozen=True)
class PersonalCandidateList:
    path: Path
    status: str
    login_ids: frozenset[int]
    raw_rows: int = 0
    unique_logins: int = 0
    duplicate_rows: int = 0
    invalid_rows: int = 0

    def summary(self, *, enabled: bool) -> dict[str, object]:
        return {
            "enabled": enabled,
            "status": self.status,
            "path": str(self.path),
            "raw_rows": self.raw_rows,
            "unique_logins": self.unique_logins,
            "duplicate_rows": self.duplicate_rows,
            "invalid_rows": self.invalid_rows,
            "matched_accounts": 0,
            "added_accounts": 0,
            "overlap_accounts": 0,
        }


def load_personal_candidates(path: Path | None = None) -> PersonalCandidateList:
    candidate_path = Path(path or DEFAULT_PERSONAL_CANDIDATE_PATH)
    if not candidate_path.exists():
        return PersonalCandidateList(candidate_path, "missing", frozenset())
    try:
        with candidate_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = {str(header).strip().lower() for header in (reader.fieldnames or [])}
            login_header = next((header for header in headers if header in {"login", "account", "account_id"}), None)
            if login_header is None:
                return PersonalCandidateList(candidate_path, "invalid", frozenset())
            actual_header = next(header for header in (reader.fieldnames or []) if str(header).strip().lower() == login_header)
            logins: set[int] = set()
            raw_rows = duplicate_rows = invalid_rows = 0
            for row in reader:
                raw_rows += 1
                raw_login = str(row.get(actual_header, "") or "").strip()
                try:
                    login = int(raw_login)
                    if login <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    invalid_rows += 1
                    continue
                if login in logins:
                    duplicate_rows += 1
                logins.add(login)
    except (OSError, UnicodeError, csv.Error):
        return PersonalCandidateList(candidate_path, "invalid", frozenset())
    status = "ready" if logins else "empty"
    return PersonalCandidateList(
        path=candidate_path,
        status=status,
        login_ids=frozenset(logins),
        raw_rows=raw_rows,
        unique_logins=len(logins),
        duplicate_rows=duplicate_rows,
        invalid_rows=invalid_rows,
    )
