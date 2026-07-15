# Dashboard calculation audit — 2026-07-15

## Scope

The audit covered the ClickHouse query, service aggregation, dashboard payload, and the personal candidate list at:

`/Users/jianghe/gzkj_副本_notickdata/markout_yearly/may_june_mean_bps_gt_0.05_logins.csv`

The analysis windows were 2026-05-01 through 2026-06-30 for selection and 2026-07-01 through 2026-07-13 for validation.

## Checks and fixes

- All query, service, and account-detail paths hard-exclude account groups containing `test` or `demo`, case-insensitively. A service-layer safety filter repeats this boundary.
- Dashboard company-profit monthly totals use the unfiltered population rows, so local leverage exclusions do not change the company baseline.
- `eligible_accounts` uses the same unfiltered post-test/demo population baseline; Abook/Bbook cohort rows still use the locally filtered selection rows.
- Net P&L uses Deals: `profit + storage + commission + fee` for `action IN (0, 1)`. Funding actions remain separate. Matched market P&L is retained as a fallback for old fixtures only.
- Abook validation theoretical increment is exactly the validation-period user net P&L of the deduplicated Abook cohort. With assumed Abook company profit of zero, this is `0 - current Bbook profit`.
- Book-performance “gross profit / gross loss” now sums trade gross wins/losses rather than account net P&L.
- Cross-period median holding time uses the account-level selection median from the exact period statistic, not the maximum of monthly medians.
- Personal candidate accounts are forced into Abook only after the normal platform/group/test-demo query boundary; `(platform, login)` is grouped once, so overlaps cannot double count P&L.

## Personal candidate file profile

- 31 CSV rows, 30 unique Login values, 1 repeated Login across May and June.
- No `platform` column; Login values are matched across the selected platforms.
- 30 mt5 accounts matched in the current data; no hh_mt5 duplicate was found.
- No matched account contained `test` or `demo` in its account group.

## Live comparison with the current default rules

The default monthly-continuity threshold is `0%` because it is an optional enhancement not included in the required rule list. The required defaults remain active days 10, win rate 50%, PF > 1, payoff ratio 0.8, positive-month rate 50%, daily-profit-rate lower bound 55%, stability 70, Top1 contribution < 20%, and peak leverage 200 with the 300-second short-hold exception.

| Mode | Abook accounts | Personal added | July validation theoretical increment | Active July positive rate |
|---|---:|---:|---:|---:|
| Personal list off | 35 | 0 | +$7,883.12 | 85.71% (28 active) |
| Personal list on | 65 | 30 | -$24,467.08 | 56.00% (50 active) |

Conclusion: this personal candidate list does not improve the current Abook hypothesis; it materially weakens both July incremental P&L and continuation rate. It is therefore implemented as an explicit opt-in switch, not enabled by default.
