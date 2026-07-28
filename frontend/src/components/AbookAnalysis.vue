<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AccountRow, AnalysisPayload } from '../types'
import { money as fmtMoney, number } from '../utils/format'

const props = defineProps<{ data: AnalysisPayload }>()
const emit = defineEmits<{ (event: 'open', account: AccountRow): void }>()

type Phase = 'selection' | 'validation'

function amount(value: unknown): number { return number(value) }
function format(value: unknown): string { return fmtMoney(value) }
function ratio(value: unknown): string { return `${(number(value) * 100).toFixed(1)}%` }

function phasePnl(account: AccountRow, phase: Phase): number {
  return number(account[phase]?.client_net_pnl)
}

function phaseAmountValues(account: AccountRow, phase: Phase): number[] {
  const monthly = (account.monthly || [])
    .filter((item: any) => item.phase === phase)
    .map((item: any) => number(item.client_net_pnl))
  return monthly.length ? monthly : [phasePnl(account, phase)]
}

function monthPnl(account: AccountRow, month: string): number {
  const row = (account.monthly || []).find((item: any) => item.month === month)
  return number(row?.client_net_pnl)
}

// Derive the months actually present in the data — no hardcoded "2026-05" etc.
const availableMonths = computed<string[]>(() => {
  const months = new Set<string>()
  for (const account of (props.data.accounts || [])) {
    for (const item of (account.monthly || [])) {
      if (item && item.month) months.add(String(item.month))
    }
  }
  return [...months].sort()
})
const monthLabel = (month: string): string => {
  const [, m] = month.split('-')
  return `${Number(m)}月`
}
function phaseLabel(phase: Phase): string {
  if (phase !== 'selection') return '验证期'
  const selectionMonths = new Set<string>()
  for (const account of (props.data.accounts || [])) {
    for (const item of (account.monthly || [])) {
      if (item?.phase === 'selection' && item.month) selectionMonths.add(String(item.month))
    }
  }
  const labels = [...selectionMonths].sort().map(monthLabel)
  return labels.length ? `筛选期（${labels.join('、')}）` : '筛选期'
}

function phaseSummary(accounts: AccountRow[], phase: Phase) {
  const values = accounts.map(account => phasePnl(account, phase))
  const amountValues = accounts.flatMap(account => phaseAmountValues(account, phase))
  const totalProfit = amountValues.filter(value => value > 0).reduce((sum, value) => sum + value, 0)
  const totalLoss = amountValues.filter(value => value < 0).reduce((sum, value) => sum + Math.abs(value), 0)
  const trades = accounts.reduce((sum, account) => sum + number(account[phase]?.trade_count), 0)
  const wins = accounts.reduce((sum, account) => sum + number(account[phase]?.winning_trades), 0)
  return {
    totalProfit,
    totalLoss,
    netPnl: totalProfit - totalLoss,
    accounts: accounts.length,
    strictPositiveAccounts: values.filter(value => value > 0).length,
    profitableRate: values.length ? values.filter(value => value > 0).length / values.length : 0,
    activeAccounts: accounts.filter(account => number(account[phase]?.trade_count) > 0).length,
    trades,
    winRate: trades > 0 ? wins / trades : 0,
  }
}

const abookAccounts = computed(() => (props.data.accounts || []).filter(account => account.book === 'abook'))
const bbookAccounts = computed(() => (props.data.accounts || []).filter(account => account.book === 'bbook'))
const populationAccounts = computed(() => props.data.population_accounts || props.data.accounts || [])
function apiPhaseSummary(book: 'abook' | 'bbook', phase: Phase) {
  const group = phase === 'selection'
    ? props.data.selection?.groups?.[book] as Record<string, any> | undefined
    : props.data.validation?.groups?.[book] as Record<string, any> | undefined
  const performance = props.data.book_performance?.[phase]?.[book] as Record<string, any> | undefined
  const accounts = number(group?.accounts ?? performance?.accounts)
  const strictPositiveAccounts = phase === 'validation' ? number(group?.strict_positive_accounts) : 0
  return {
    totalProfit: number(performance?.positive_pnl),
    totalLoss: Math.abs(number(performance?.negative_pnl)),
    netPnl: number(performance?.net_pnl ?? group?.client_net_pnl),
    accounts,
    strictPositiveAccounts,
    profitableRate: accounts ? strictPositiveAccounts / accounts : 0,
    activeAccounts: number(group?.active_accounts),
    trades: number(group?.matched_trades),
  }
}
const summaries = computed(() => ({
  selection: apiPhaseSummary('abook', 'selection'),
  validation: apiPhaseSummary('abook', 'validation'),
}))
const bbookSummaries = computed(() => ({
  selection: apiPhaseSummary('bbook', 'selection'),
  validation: apiPhaseSummary('bbook', 'validation'),
}))
const leakage = computed(() => (props.data.misjudge?.bbook_profitable || []).filter((row: any) => number(row.profit_amount) > 100))

type AbookSortField = string
const sortBy = ref<AbookSortField>('validation')
const sortDirection = ref<'asc' | 'desc'>('desc')
const search = ref('')
const page = ref(1)
const pageSize = ref(50)

function toggleSort(field: AbookSortField) {
  if (sortBy.value === field) sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  else { sortBy.value = field; sortDirection.value = 'desc' }
}
function sortMark(field: AbookSortField): string {
  return sortBy.value === field ? (sortDirection.value === 'asc' ? '↑' : '↓') : '↕'
}

function accountSortValue(account: AccountRow, field: AbookSortField): number {
  if (availableMonths.value.includes(field)) return monthPnl(account, field)
  if (field === 'selectionWinRate') return number(account.selection?.win_rate)
  if (field === 'validationWinRate') return number(account.validation?.win_rate)
  if (field === 'selectionTrades') return number(account.selection?.trade_count)
  if (field === 'validation') return phasePnl(account, 'validation')
  return number(account.stability?.score)
}

const filteredAbookAccounts = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return abookAccounts.value
  return abookAccounts.value.filter(account =>
    `${account.platform} ${account.login} ${account.account_group}`.toLowerCase().includes(query)
  )
})
const sortedAbookAccounts = computed(() => [...filteredAbookAccounts.value].sort((left, right) => {
  const delta = accountSortValue(left, sortBy.value) - accountSortValue(right, sortBy.value)
  return (sortDirection.value === 'asc' ? 1 : -1) * (delta || (left.login - right.login))
}))
const abookPageCount = computed(() => Math.max(1, Math.ceil(sortedAbookAccounts.value.length / pageSize.value)))
const pagedAbookAccounts = computed(() => sortedAbookAccounts.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))

function toggleLeakageSort(field: string) {
  if (leakageSortBy.value === field) leakageSortDirection.value = leakageSortDirection.value === 'asc' ? 'desc' : 'asc'
  else { leakageSortBy.value = field; leakageSortDirection.value = 'desc' }
}

function leakageSortMark(field: string): string {
  return leakageSortBy.value === field ? (leakageSortDirection.value === 'asc' ? '↑' : '↓') : '↕'
}

const leakageSortBy = ref<string>('validation')
const leakageSortDirection = ref<'asc' | 'desc'>('desc')
const leakageMonths = computed(() => availableMonths.value.slice(0, 3))
function leakageMonthValue(row: any, month: string): number {
  const monthly = row.monthly_pnls || {}
  if (monthly[month] != null) return number(monthly[month])
  // Legacy aliases for older payloads.
  if (month.endsWith('-05') && row.may_client_net_pnl != null) return number(row.may_client_net_pnl)
  if (month.endsWith('-06') && row.june_client_net_pnl != null) return number(row.june_client_net_pnl)
  return 0
}
const sortedLeakage = computed(() => [...leakage.value].sort((left: any, right: any) => {
  let delta = 0
  if (leakageSortBy.value === 'validation') {
    delta = number(left.validation_client_net_pnl) - number(right.validation_client_net_pnl)
  } else {
    delta = leakageMonthValue(left, leakageSortBy.value) - leakageMonthValue(right, leakageSortBy.value)
  }
  return (leakageSortDirection.value === 'asc' ? 1 : -1) * (delta || (Number(left.login) - Number(right.login)))
}))

const accountLookup = computed(() => new Map(
  (props.data.accounts || []).map(account => [`${account.platform}-${account.login}`, account]),
))

function leakageAccount(row: any): AccountRow {
  return accountLookup.value.get(`${row.platform}-${row.login}`) || row as AccountRow
}

watch(search, () => { page.value = 1 })
watch(abookPageCount, () => { if (page.value > abookPageCount.value) page.value = abookPageCount.value })
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div><span class="kicker">ABOOK ANALYSIS</span><h2>Abook 分析</h2></div>
      <span class="hint">客户 P&amp;L 口径，不直接代表公司利润</span>
    </div>

    <div class="phase-cards">
      <article v-for="phase in (['selection', 'validation'] as Phase[])" :key="phase" class="metric-card">
        <span class="kicker">{{ phaseLabel(phase) }}</span>
        <div class="list-row"><span>盈利金额</span><b class="positive">{{ format(summaries[phase].totalProfit) }}</b></div>
        <div class="list-row"><span>亏损金额</span><b class="negative">{{ format(-summaries[phase].totalLoss) }}</b></div>
        <div class="list-row"><span>净 P&amp;L</span><b :class="summaries[phase].netPnl >= 0 ? 'positive' : 'negative'">{{ format(summaries[phase].netPnl) }}</b></div>
        <div v-if="phase === 'validation'" class="list-row"><span>盈利人数占比（P&amp;L &gt; 0 / Abook 总人数）</span><b class="positive">{{ ratio(summaries[phase].profitableRate) }}（{{ summaries[phase].strictPositiveAccounts }}/{{ summaries[phase].accounts }}）</b></div>
        <small>盈利金额 + 亏损金额 = 净 P&amp;L · {{ summaries[phase].activeAccounts }}/{{ summaries[phase].accounts }} 个活跃账户 · {{ summaries[phase].trades }} 笔交易</small>
      </article>
    </div>

    <div class="panel-head"><div><span class="kicker">BBOOK ANALYSIS</span><h3>Bbook 分析</h3></div><span class="hint">客户 P&amp;L 口径；公司利润单独计算</span></div>
    <div class="phase-cards">
      <article v-for="phase in (['selection', 'validation'] as Phase[])" :key="phase" class="metric-card">
        <span class="kicker">{{ phaseLabel(phase) }}</span>
        <div class="list-row"><span>盈利金额</span><b class="positive">{{ format(bbookSummaries[phase].totalProfit) }}</b></div>
        <div class="list-row"><span>亏损金额</span><b class="negative">{{ format(-bbookSummaries[phase].totalLoss) }}</b></div>
        <div class="list-row"><span>净 P&amp;L</span><b :class="bbookSummaries[phase].netPnl >= 0 ? 'positive' : 'negative'">{{ format(bbookSummaries[phase].netPnl) }}</b></div>
        <small>盈利金额 + 亏损金额 = 净 P&amp;L · {{ bbookSummaries[phase].activeAccounts }}/{{ bbookSummaries[phase].accounts }} 个活跃账户 · {{ bbookSummaries[phase].trades }} 笔交易</small>
      </article>
    </div>

    <details class="user-list" open>
      <summary><div class="panel-head"><div><h3>Abook 用户</h3><span class="hint">点击用户查看指标；点击列名切换升序/降序</span></div><span class="tag">{{ abookAccounts.length }} 人</span></div></summary>
      <div v-if="!abookAccounts.length" class="empty">暂无筛选到 Abook 用户</div>
      <div v-else class="table-scroll">
        <input v-model="search" class="search" placeholder="搜索平台、Login、账户组" style="margin-bottom:8px">
        <table>
          <thead><tr>
            <th>账户</th><th>来源</th>
            <th v-for="month in availableMonths" :key="month"><button class="table-sort" @click="toggleSort(month)">{{ monthLabel(month) }} P&amp;L {{ sortMark(month) }}</button></th>
            <th><button class="table-sort" @click="toggleSort('validation')">验证期 P&amp;L {{ sortMark('validation') }}</button></th>
            <th><button class="table-sort" @click="toggleSort('selectionWinRate')">筛选期胜率 {{ sortMark('selectionWinRate') }}</button></th>
            <th><button class="table-sort" @click="toggleSort('validationWinRate')">验证期胜率 {{ sortMark('validationWinRate') }}</button></th>
            <th><button class="table-sort" @click="toggleSort('selectionTrades')">交易数 {{ sortMark('selectionTrades') }}</button></th>
            <th><button class="table-sort" @click="toggleSort('score')">稳定性 {{ sortMark('score') }}</button></th>
          </tr></thead>
          <tbody>
            <tr v-for="account in pagedAbookAccounts" :key="`${account.platform}-${account.login}`" @click="emit('open', account)">
              <td>{{ account.platform }} / {{ account.login }}<small>{{ account.account_group }}</small></td>
              <td><small>{{ account.selection_source }}</small></td>
              <td v-for="month in availableMonths" :key="month" :class="monthPnl(account, month) >= 0 ? 'positive' : 'negative'">{{ format(monthPnl(account, month)) }}</td>
              <td :class="phasePnl(account, 'validation') >= 0 ? 'positive' : 'negative'">{{ format(phasePnl(account, 'validation')) }}</td>
              <td>{{ ratio(account.selection?.win_rate) }}</td>
              <td>{{ ratio(account.validation?.win_rate) }}</td>
              <td>{{ amount(account.selection?.trade_count) }} / {{ amount(account.validation?.trade_count) }}</td>
              <td>{{ amount(account.stability?.score).toFixed(0) }} · {{ account.stability?.tier || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="pagination">
          <button class="ghost compact" :disabled="page <= 1" @click="page--">上一页</button>
          <span>第 {{ page }} / {{ abookPageCount }} 页 · {{ sortedAbookAccounts.length }} 个账户</span>
          <button class="ghost compact" :disabled="page >= abookPageCount" @click="page++">下一页</button>
          <label style="margin-left:auto">每页<select v-model.number="pageSize" @change="page = 1"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label>
        </div>
      </div>
    </details>

    <div class="inset">
      <div class="panel-head"><div><h3>Bbook 漏网</h3><span class="hint">验证期盈利且最终留在 Bbook 的用户</span></div><span class="negative">公司损失 {{ format(props.data.misjudge?.bbook_company_loss_total) }}</span></div>
      <details open>
        <summary>显示公司损失大于 100 的 {{ leakage.length }} 人</summary>
        <div v-if="!leakage.length" class="empty">暂无金额大于 100 的漏网用户</div>
        <div v-else class="table-scroll"><table><thead><tr>
          <th>用户</th>
          <th v-for="month in leakageMonths" :key="month"><button class="table-sort" @click="toggleLeakageSort(month)">{{ monthLabel(month) }} P&amp;L {{ leakageSortMark(month) }}</button></th>
          <th><button class="table-sort" @click="toggleLeakageSort('validation')">验证期 P&amp;L {{ leakageSortMark('validation') }}</button></th>
          <th>Bbook 原因</th>
        </tr></thead><tbody><tr v-for="row in sortedLeakage" :key="`${row.platform}-${row.login}`" @click="emit('open', leakageAccount(row))">
          <td>{{ row.platform }} / {{ row.login }}<small>筛选期合计 {{ format(row.selection_client_net_pnl) }}</small></td>
          <td v-for="month in leakageMonths" :key="month" :class="leakageMonthValue(row, month) >= 0 ? 'positive' : 'negative'">{{ format(leakageMonthValue(row, month)) }}</td>
          <td class="positive">{{ format(row.validation_client_net_pnl) }}</td>
          <td><span v-for="tag in (row.bbook_reason_tags || ['Bbook'])" :key="tag" class="tag danger">{{ tag }}</span></td>
        </tr></tbody></table></div>
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
