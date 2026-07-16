<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { exportAbook, fetchAnalysis, fetchBookAnalytics } from './api'
import type { AccountRow, AnalysisPayload, RequestModel, Tab } from './types'
import FilterSidebar from './components/FilterSidebar.vue'
import KpiCards from './components/KpiCards.vue'
import SelectionFunnel from './components/SelectionFunnel.vue'
import MisjudgeAnalysis from './components/MisjudgeAnalysis.vue'
import AccountsTable from './components/AccountsTable.vue'
import AccountDrawer from './components/AccountDrawer.vue'
import BookPerformance from './components/BookPerformance.vue'

const defaultRules: Record<string, number | string[]> = {
  min_trades: 20, min_active_days: 10, min_win_rate: 0.5, min_profit_factor: 1,
  min_payoff_ratio: 0.8, min_avg_daily_profit: 0, min_selection_monthly_consistency: 0,
  min_positive_month_rate: 0.5, max_top1_day_profit_contribution: 0.2,
  max_daily_profit_month_contribution: 0.6, max_leverage_p95_ratio: 200, max_high_leverage_holding_seconds: 300,
  min_direction_day_rate_lower_bound: 0.55, min_stability_score: 70,
  high_confidence_trades: 100, high_confidence_days: 30,
  excluded_martingale_levels: ['extreme', 'high', 'medium', 'low'],
}
const request = ref<RequestModel>({
  selection: { start: '2026-05-01', end: '2026-06-30' }, validation: { start: '2026-07-01', end: '2026-07-13' },
  platforms: ['mt5', 'hh_mt5'], filters: { groups: [], logins: [] }, rules: { ...defaultRules }, personal_candidate_list: false,
})
const data = ref<AnalysisPayload>({ accounts: [] })
const activeTab = ref<Tab>('overview')
const loading = ref(false)
const bookLoading = ref(false)
const error = ref('')
const rulesDirty = ref(false)
const bookData = ref<any | null>(null)
const selectedAccount = ref<AccountRow | null>(null)

async function loadAnalysis() {
  loading.value = true; error.value = ''; bookData.value = null
  try { data.value = await fetchAnalysis(request.value); rulesDirty.value = false } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { loading.value = false }
}
async function loadBook() {
  if (bookData.value || bookLoading.value || activeTab.value === 'overview') return
  bookLoading.value = true
  try { bookData.value = await fetchBookAnalytics(request.value, (data.value.accounts || []).filter(a => a.book === 'abook').map(a => ({ platform: a.platform, login: a.login }))) } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { bookLoading.value = false }
}
async function downloadExport() {
  const response = await exportAbook(request.value)
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`)
  const link = document.createElement('a')
  link.href = URL.createObjectURL(await response.blob())
  link.download = 'abook_accounts.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}
function selectTab(tab: Tab) { activeTab.value = tab; if (tab !== 'overview') loadBook() }
function reset() { request.value.rules = { ...defaultRules }; request.value.personal_candidate_list = false; loadAnalysis() }
watch(() => request.value.rules, () => { rulesDirty.value = true }, { deep: true })
onMounted(loadAnalysis)
const tabs: Array<{ id: Tab; label: string }> = [
  { id: 'overview', label: '总览' }, { id: 'pnl', label: '盈亏结构' }, { id: 'users', label: '用户结构' },
  { id: 'risk', label: '风险敞口' }, { id: 'routing', label: '分流质量' },
]
</script>

<template>
  <div class="app-shell">
    <header class="topbar"><div><span class="kicker">RISK / A-BOOK ANALYTICS</span><h1>Abook 筛选与 Book 分析</h1><p>筛选期 → 样本外验证 · 马丁排除 · 误判成本量化</p></div><div class="top-actions"><button class="ghost" @click="downloadExport">导出 Abook CSV</button><span class="status-pill" :class="loading ? 'busy' : 'ready'">{{ loading ? '查询中' : '就绪' }}</span></div></header>
    <div class="layout">
      <FilterSidebar :request="request" :data="data" :loading="loading" :rules-dirty="rulesDirty" @apply="loadAnalysis" @reset="reset" />
      <main class="content"><div v-if="error" class="alert error">{{ error }}</div><nav class="tabs"><button v-for="tab in tabs" :key="tab.id" :class="{ active: activeTab === tab.id }" @click="selectTab(tab.id)">{{ tab.label }}</button></nav>
        <template v-if="activeTab === 'overview'"><KpiCards :data="data" /><MisjudgeAnalysis :data="data" /><SelectionFunnel :data="data" /><AccountsTable :accounts="data.accounts || []" @open="selectedAccount = $event" /></template>
        <template v-else><BookPerformance :analytics="bookData" :loading="bookLoading" :active-tab="activeTab" /></template>
      </main>
    </div>
    <AccountDrawer :account="selectedAccount" @close="selectedAccount = null" />
  </div>
</template>
