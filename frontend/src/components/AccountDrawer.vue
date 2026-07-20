<script setup lang="ts">
import type { AccountDetailPayload, AccountRow } from '../types'
defineProps<{ account: AccountRow | null; detail: AccountDetailPayload | null; loading: boolean; error: string }>()
const emit = defineEmits<{ (event: 'close'): void }>()

function number(value: unknown): number {
  const parsed = Number(value ?? 0)
  return Number.isFinite(parsed) ? parsed : 0
}

function format(value: unknown): string { return number(value).toFixed(2) }
function percent(value: unknown): string { return `${(number(value) * 100).toFixed(1)}%` }
function text(value: unknown): string { return value === null || value === undefined || value === '' ? '—' : String(value) }
</script>
<template>
  <div v-if="account" class="drawer-backdrop" @click.self="emit('close')">
    <aside class="drawer">
      <button class="close" @click="emit('close')">×</button>
      <span class="kicker">ACCOUNT DETAIL</span>
      <h2>{{ account.platform }} / {{ account.login }}</h2>
      <p>{{ account.account_group }} · {{ account.book === 'abook' ? 'Abook' : 'Bbook' }} · {{ account.selection_source }}</p>

      <div class="detail-grid">
        <span>筛选期客户净 P&amp;L</span><b>{{ format(account.selection?.client_net_pnl) }}</b>
        <span>验证期客户净 P&amp;L</span><b>{{ format(account.validation?.client_net_pnl) }}</b>
        <span>筛选期胜率 / 交易</span><b>{{ percent(account.selection?.win_rate) }} / {{ number(account.selection?.trade_count) }}</b>
        <span>验证期胜率 / 交易</span><b>{{ percent(account.validation?.win_rate) }} / {{ number(account.validation?.trade_count) }}</b>
        <span>筛选期 PF / 盈亏比</span><b>{{ text(account.selection?.profit_factor) }} / {{ format(account.selection?.payoff_ratio) }}</b>
        <span>验证期 PF / 盈亏比</span><b>{{ text(account.validation?.profit_factor) }} / {{ format(account.validation?.payoff_ratio) }}</b>
        <span>稳定性 / 置信度</span><b>{{ number(account.stability?.score).toFixed(0) }} / {{ text(account.confidence_tier) }}</b>
        <span>马丁风险等级</span><b>{{ text(account.martingale_risk_level) }}</b>
        <span>杠杆率 P95</span><b>{{ text(account.risk_leverage_p95_ratio) }}</b>
      </div>

      <h3>马丁五层命中</h3>
      <div class="layer-grid"><span v-for="layer in ['layer1', 'layer2', 'layer3', 'layer4', 'layer5']" :key="layer" :class="account.martingale_layer_hits?.[layer] ? 'hit' : ''">{{ layer }} {{ account.martingale_layer_hits?.[layer] ? '命中' : '未命中' }}</span></div>

      <div v-if="loading" class="empty">正在加载历史交易详情…</div>
      <div v-else-if="error" class="alert error">交易详情加载失败：{{ error }}</div>
      <template v-else-if="detail">
        <h3>品种汇总</h3>
        <div v-if="!detail.symbols.length" class="empty">暂无品种汇总</div>
        <div v-else class="table-scroll"><table><thead><tr><th>品种</th><th>交易数</th><th>交易量</th><th>P&amp;L</th><th>胜率</th></tr></thead><tbody><tr v-for="row in detail.symbols" :key="row.symbol"><td>{{ row.symbol }}</td><td>{{ row.trade_count }}</td><td>{{ format(row.volume) }}</td><td :class="row.profit >= 0 ? 'positive' : 'negative'">{{ format(row.profit) }}</td><td>{{ percent(row.win_rate) }}</td></tr></tbody></table></div>

        <h3>历史交易明细</h3>
        <div v-if="!detail.trades.length" class="empty">当前分析窗口内暂无交易</div>
        <div v-else class="table-scroll"><table><thead><tr><th>平仓时间</th><th>品种</th><th>方向</th><th>交易量</th><th>Profit</th><th>持仓秒数</th></tr></thead><tbody><tr v-for="(trade, index) in detail.trades" :key="String(trade.exit_deal_id || trade.entry_deal_id || index)"><td>{{ text(trade.exit_time) }}</td><td>{{ text(trade.symbol) }}</td><td>{{ text(trade.direction) }}</td><td>{{ format(trade.volume) }}</td><td :class="number(trade.profit) >= 0 ? 'positive' : 'negative'">{{ format(trade.profit) }}</td><td>{{ format(trade.holding_seconds) }}</td></tr></tbody></table></div>
      </template>
      <div v-else class="empty">暂无交易详情</div>
    </aside>
  </div>
</template>
