<script setup lang="ts">
import { computed } from 'vue'
import type { AccountRow, AnalysisPayload } from '../types'

const props = defineProps<{ data: AnalysisPayload }>()
const emit = defineEmits<{ (event: 'open', account: AccountRow): void }>()

type Phase = 'selection' | 'validation'

function amount(value: unknown): number {
  const parsed = Number(value ?? 0)
  return Number.isFinite(parsed) ? parsed : 0
}

function format(value: unknown): string {
  return amount(value).toFixed(2)
}

function ratio(value: unknown): string {
  return `${(amount(value) * 100).toFixed(1)}%`
}

function phasePnl(account: AccountRow, phase: Phase): number {
  return amount(account[phase]?.client_net_pnl)
}

function monthPnl(account: AccountRow, month: string): number {
  const row = (account.monthly || []).find((item: any) => item.month === month)
  return amount(row?.client_net_pnl)
}

function phaseSummary(accounts: AccountRow[], phase: Phase) {
  const values = accounts.map(account => phasePnl(account, phase))
  const totalProfit = values.filter(value => value > 0).reduce((sum, value) => sum + value, 0)
  const totalLoss = values.filter(value => value < 0).reduce((sum, value) => sum + Math.abs(value), 0)
  const trades = accounts.reduce((sum, account) => sum + amount(account[phase]?.trade_count), 0)
  const wins = accounts.reduce((sum, account) => sum + amount(account[phase]?.winning_trades), 0)
  return {
    totalProfit,
    totalLoss,
    netPnl: totalProfit - totalLoss,
    accounts: accounts.length,
    activeAccounts: accounts.filter(account => amount(account[phase]?.trade_count) > 0).length,
    trades,
    winRate: trades > 0 ? wins / trades : 0,
  }
}

const abookAccounts = computed(() => (props.data.accounts || []).filter(account => account.book === 'abook'))
const summaries = computed(() => ({
  selection: phaseSummary(abookAccounts.value, 'selection'),
  validation: phaseSummary(abookAccounts.value, 'validation'),
}))
const leakage = computed(() => (props.data.misjudge?.bbook_profitable || []).filter((row: any) => amount(row.profit_amount) > 100))
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div><span class="kicker">ABOOK ANALYSIS</span><h2>Abook 分析</h2></div>
      <span class="hint">客户 P&amp;L 口径，不直接代表公司利润</span>
    </div>

    <div class="phase-cards">
      <article v-for="phase in (['selection', 'validation'] as Phase[])" :key="phase" class="metric-card">
        <span class="kicker">{{ phase === 'selection' ? '筛选期（5–6 月）' : '验证期（7 月）' }}</span>
        <div class="list-row"><span>总盈利</span><b class="positive">{{ format(summaries[phase].totalProfit) }}</b></div>
        <div class="list-row"><span>总亏损</span><b class="negative">{{ format(summaries[phase].totalLoss) }}</b></div>
        <div class="list-row"><span>净 P&amp;L</span><b :class="summaries[phase].netPnl >= 0 ? 'positive' : 'negative'">{{ format(summaries[phase].netPnl) }}</b></div>
        <small>总盈利 - 总亏损 = 净 P&amp;L · {{ summaries[phase].activeAccounts }}/{{ summaries[phase].accounts }} 个活跃账户 · {{ summaries[phase].trades }} 笔交易</small>
      </article>
    </div>

    <div class="panel-head"><div><h3>Abook 用户</h3><span class="hint">点击用户查看当前分析窗口内的历史交易</span></div><span class="tag">{{ abookAccounts.length }} 人</span></div>
    <div v-if="!abookAccounts.length" class="empty">暂无筛选到 Abook 用户</div>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>账户</th><th>来源</th><th>5月 P&amp;L</th><th>6月 P&amp;L</th><th>7月 P&amp;L</th><th>5–6 月胜率</th><th>7 月胜率</th><th>交易数</th><th>稳定性</th></tr></thead>
        <tbody>
          <tr v-for="account in abookAccounts" :key="`${account.platform}-${account.login}`" @click="emit('open', account)">
            <td>{{ account.platform }} / {{ account.login }}<small>{{ account.account_group }}</small></td>
            <td><small>{{ account.selection_source }}</small></td>
            <td :class="monthPnl(account, '2026-05') >= 0 ? 'positive' : 'negative'">{{ format(monthPnl(account, '2026-05')) }}</td>
            <td :class="monthPnl(account, '2026-06') >= 0 ? 'positive' : 'negative'">{{ format(monthPnl(account, '2026-06')) }}</td>
            <td :class="phasePnl(account, 'validation') >= 0 ? 'positive' : 'negative'">{{ format(phasePnl(account, 'validation')) }}</td>
            <td>{{ ratio(account.selection?.win_rate) }}</td>
            <td>{{ ratio(account.validation?.win_rate) }}</td>
            <td>{{ amount(account.selection?.trade_count) }} / {{ amount(account.validation?.trade_count) }}</td>
            <td>{{ amount(account.stability?.score).toFixed(0) }} · {{ account.stability?.tier || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="inset">
      <div class="panel-head"><div><h3>Bbook 漏网</h3><span class="hint">验证期盈利且最终留在 Bbook 的用户</span></div><span class="negative">公司损失 {{ format(props.data.misjudge?.bbook_company_loss_total) }}</span></div>
      <details open>
        <summary>显示公司损失大于 100 的 {{ leakage.length }} 人</summary>
        <div v-if="!leakage.length" class="empty">暂无金额大于 100 的漏网用户</div>
        <div v-else class="table-scroll"><table><thead><tr><th>用户</th><th>6月 P&amp;L</th><th>7月 P&amp;L</th><th>Bbook 公司影响</th></tr></thead><tbody><tr v-for="row in leakage" :key="`${row.platform}-${row.login}`"><td>{{ row.platform }} / {{ row.login }}<small>筛选期合计 {{ format(row.selection_client_net_pnl) }}</small></td><td :class="row.june_client_net_pnl >= 0 ? 'positive' : 'negative'">{{ format(row.june_client_net_pnl) }}</td><td class="positive">{{ format(row.validation_client_net_pnl) }}</td><td class="negative">{{ format(row.company_loss_if_left_bbook) }}</td></tr></tbody></table></div>
      </details>
    </div>

    <details class="inset">
      <summary>盈亏口径与数据来源</summary>
      <div class="basis-list">
        <div>客户净 P&amp;L：{{ props.data.profit_overview?.pnl_basis?.client_net_pnl || '—' }}</div>
        <div>市场 P&amp;L：{{ props.data.profit_overview?.pnl_basis?.market_pnl || '—' }}</div>
        <div>公司 P&amp;L：{{ props.data.profit_overview?.pnl_basis?.company_pnl || '—' }}</div>
        <div>数据覆盖：Deals {{ props.data.coverage?.source_deal_min || '—' }} 至 {{ props.data.coverage?.source_deal_max || '—' }}</div>
      </div>
    </details>
  </section>
</template>
