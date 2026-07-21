# 找高手版（中等严格）vs 旧默认：7 月验证对比

窗口：筛选 2026-05-01～06-30，验证 2026-07-01～07-16。  
脚本：`scripts/compare_skilled_trader_july.py`  
原始 JSON：`docs/analysis/2026-07-21-skilled-trader-july-compare.json`

## 设计原则

中等严格不是把所有门槛一起放宽，而是：

- **放宽策略形状**：胜率可到 35%、不要求筛选期每个月都赚、活跃日 15、交易数 100  
- **保持 edge / 防运气**：PF>1.4、Top1<0.22、Wilson 日盈利率≥0.52、收益/回撤≥1、筛选期总净盈利>0

不同策略（高胜率刮头皮 / 低胜率趋势）都能过；靠几天暴利或回撤效率差的会被挡。

## 结果

| 指标 | 旧默认 | 严格版（此前） | **中等严格（当前）** |
|------|--------|----------------|----------------------|
| Abook 人数 | 46 | 4 | **9** |
| 验证期有交易 | 45 | 4 | 8 |
| 继续盈利 / 亏损 | 25 / 13 | 3 / 0 | **6 / 1** |
| 继续盈利率 | 55.6% | 75% | **75%** |
| 验证期客户净 P&L | +17,424 | +1,572 | **+2,482** |
| 验证期组合 PF | 1.28 | 1.97 | **1.57** |

## 解读

- 相对旧默认：人数少很多，但继续盈利率从 55.6% 提到 75%，组合质量更稳。  
- 相对严格版：多收了约一倍账户，7 月净 P&L 反而更高（+2482 vs +1572），说明放宽的是「策略形状」而不是「运气过滤」。  
- 试过更松的中等（放宽 Top1 / 回撤 / PF）会把 7 月质量稀释到接近打平甚至转负，因此没有采用。

## 当前默认参数

```text
min_trades=100, min_active_days=15, min_active_months=2
min_win_rate=0.35, min_profit_factor=1.4
min_payoff_ratio=0.6, payoff_link_factor=1.0
min_positive_month_rate=0.8, require_selection_monthly_positive=false
require_selection_net_positive=true
max_top1_day_profit_contribution=0.22
min_direction_day_rate_lower_bound=0.52
min_return_drawdown_ratio=1.0
max_leverage_p95_ratio=1500
```
