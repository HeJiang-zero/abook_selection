# Top1 日贡献率与本地杠杆筛选设计

## 目标

在不读取 7 月验证期数据进行筛选的前提下，进一步剔除利润集中在单日或杠杆风险过高的用户，并把杠杆计算从每次页面查询迁移到本地风险快照。

## 口径

- Abook Top1 日利润贡献率：`最大单日正 P&L / 所有正 P&L 日之和`，候选必须严格小于 20%。
- Bbook 对称使用 Top1 日亏损贡献率：`最大单日负 P&L 绝对值 / 所有负 P&L 绝对值之和`，候选必须严格小于 20%。
- `balance_prev_month > 0` 时，平均开仓程度 = 筛选期日均交易名义金额 / `balance_prev_month`；峰值杠杆率 = 筛选期单日最大交易名义金额 / `balance_prev_month`。
- `balance_prev_month <= 0` 或为空时，杠杆相关比率为 `null`，标记 `unknown_nonpositive_balance`；不应用杠杆上限，但胜率、PF、盈亏比、月度持续性和 Top1 贡献率等其他规则继续应用。

交易名义金额使用 matched trades 的 `turnover` 聚合。该值是风险代理，不等同于交易平台保证金或真实净敞口。

## 架构

新增 `scripts/build_user_risk_snapshot.py`，从 `risk.ods_mt5_users` 和 matched trades 读取筛选期用户余额及日度交易名义金额，写入本地 `data/user_risk_snapshot.json`。快照包含覆盖日期、过滤后的平台/用户记录和每个用户的风险字段；该 JSON 被 `.gitignore` 排除，不上传 GitHub。

网页分析请求读取与筛选窗口匹配的快照：本地列表先保留余额非正用户和峰值杠杆未超过上限的用户，再把 Login 列表传入 ClickHouse。返回的月度行同时注入风险字段，服务层在候选分组时再次检查杠杆规则，确保本地过滤和业务候选判断一致。

如果快照缺失或日期不匹配，不静默声称已应用杠杆过滤；响应会标记风险快照状态，其他 P&L 筛选仍然继续。旧的 `max_top_day_concentration` 参数删除，替换为 `max_top1_day_profit_contribution`。

## 前端

应用规则区域展示 Top1 日贡献率上限、最大峰值杠杆率和风险快照状态。账户抽屉展示余额、平均开仓程度、峰值杠杆率和余额状态。参数修改后继续使用“待应用参数”提示，只有点击应用才重新请求。

## 测试与边界

- 测试 Top1 贡献率严格小于 20%，等于 20% 不通过。
- 测试余额为 0 的用户仍按其他筛选条件进入候选，不因杠杆率为空被拒绝。
- 测试正余额用户超过峰值杠杆上限被排除。
- 测试快照生成 SQL 继续排除 group 中大小写不敏感包含 `test` 或 `demo` 的用户，例如 `real\\FPlive\\TEST_USD_ZO_BA_NT_H` 和 `demo\\HHdemo\\forexhh-USD`。
- 测试快照缺失/过期时状态可见，且不会伪造杠杆过滤已生效。
