from __future__ import annotations

import csv
from io import StringIO


EXPORT_FIELDS = [
    "platform", "login", "account_group", "selection_source", "selection_client_net_pnl",
    "validation_client_net_pnl", "validation_status", "stability_score", "selection_flags",
    "martingale_status", "martingale_risk_level", "martingale_blocked", "martingale_block_reason",
]


def render_abook_csv(accounts: list[dict]) -> str:
    handle = StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for account in accounts:
        if account.get("cohort") != "abook_candidate":
            continue
        writer.writerow({
            "platform": account.get("platform", ""),
            "login": account.get("login", ""),
            "account_group": account.get("account_group", ""),
            "selection_source": account.get("selection_source", ""),
            "selection_client_net_pnl": account.get("selection_client_net_pnl", 0),
            "validation_client_net_pnl": account.get("validation_client_net_pnl", 0),
            "validation_status": account.get("validation_status", ""),
            "stability_score": account.get("stability", {}).get("score"),
            "selection_flags": ";".join(account.get("selection_flags", [])),
            "martingale_status": account.get("martingale_status", "not_loaded"),
            "martingale_risk_level": account.get("martingale_risk_level"),
            "martingale_blocked": account.get("martingale_blocked", False),
            "martingale_block_reason": "martingale_blocked" if account.get("martingale_blocked") else "",
        })
    return "\ufeff" + handle.getvalue()
