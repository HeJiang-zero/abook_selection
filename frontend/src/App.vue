<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { exportAbook, fetchAccountDetail, fetchAnalysis, fetchBookAnalytics, fetchDirectionAnalytics, fetchNewcomerAnalytics, fetchWarehouseStatus, refreshLocalSnapshots as refreshLocalSnapshotsApi } from './api'
import type { AccountDetailPayload, AccountRow, AnalysisPayload, BookAnalyticsPayload, DirectionAnalyticsPayload, NewcomerAnalyticsPayload, RequestModel, Tab, WarehouseStatus } from './types'
import FilterSidebar from './components/FilterSidebar.vue'
import KpiCards from './components/KpiCards.vue'
import SelectionFunnel from './components/SelectionFunnel.vue'
import AbookAnalysis from './components/AbookAnalysis.vue'
import AccountsTable from './components/AccountsTable.vue'
import AccountDrawer from './components/AccountDrawer.vue'
import BookPerformance from './components/BookPerformance.vue'
import DirectionPanel from './components/DirectionPanel.vue'
import NewcomerPanel from './components/NewcomerPanel.vue'

const defaultRules: Record<string, number | string[] | boolean> = {
  min_trades: 75, min_win_rate: 0.5, min_profit_factor: 1.25,
  min_payoff_ratio: 0.6,
  min_long_trades_ratio: 0.3, max_long_trades_ratio: 0.7,
  max_top1_day_profit_contribution: 0.3,
  max_leverage_p95_ratio: 2000, max_high_leverage_holding_seconds: 60,
  high_confidence_trades: 100, high_confidence_days: 30,
  excluded_martingale_levels: ['extreme', 'high', 'medium', 'low'],
}
const request = ref<RequestModel>({
  selection: { start: '2026-05-01', end: '2026-06-30' }, validation: { start: '2026-07-01', end: '2026-07-22' },
  platforms: ['mt4', 'mt5', 'hh_mt5'], filters: { groups: [], logins: [] }, rules: { ...defaultRules }, personal_candidate_list: false, news_candidate_list: false,
})
const directionRequest = ref<RequestModel>(JSON.parse(JSON.stringify(request.value)) as RequestModel)
const newcomerRequest = ref<RequestModel>(JSON.parse(JSON.stringify(request.value)) as RequestModel)
const newcomerMaxActiveDays = ref(60)
const data = ref<AnalysisPayload>({ accounts: [] })
const activeTab = ref<Tab>('overview')
const loading = ref(false)
const bookLoading = ref(false)
const bookSymbolsLoaded = ref(false)
const warehouseStatus = ref<WarehouseStatus | null>(null)
const snapshotRefreshing = ref(false)
const error = ref('')
const rulesDirty = ref(false)
const bookData = ref<BookAnalyticsPayload | null>(null)
const directionData = ref<DirectionAnalyticsPayload | null>(null)
const directionLoading = ref(false)
const newcomerData = ref<NewcomerAnalyticsPayload | null>(null)
const newcomerLoading = ref(false)
const selectedAccount = ref<AccountRow | null>(null)
const selectedDirectionAccount = ref<Record<string, any> | null>(null)
const accountDetail = ref<AccountDetailPayload | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const bookRequestKey = ref('')
const directionRequestKey = ref('')
const newcomerRequestKey = ref('')
let detailRequestId = 0
let analysisVersion = 0
let bookLoadVersion = 0
let directionLoadVersion = 0
let newcomerLoadVersion = 0

function cloneRequest(source: RequestModel): RequestModel {
  return JSON.parse(JSON.stringify(source)) as RequestModel
}

function requestKey(source: RequestModel): string {
  return JSON.stringify(source)
}

function syncDependentRequests() {
  // The sidebar is the single source of truth for the main analysis. A new
  // apply must invalidate the independently editable direction/newcomer
  // requests as well, otherwise those tabs can keep using the previous run.
  directionRequest.value = cloneRequest(request.value)
  newcomerRequest.value = cloneRequest(request.value)
}

async function loadAnalysis(options: { preserveAccount?: boolean } = { preserveAccount: true }) {
  const currentAnalysisVersion = ++analysisVersion
  bookLoadVersion += 1
  directionLoadVersion += 1
  newcomerLoadVersion += 1
  syncDependentRequests()
  const accountBeforeRefresh = selectedAccount.value
  loading.value = true; error.value = ''; bookData.value = null; directionData.value = null; newcomerData.value = null; selectedDirectionAccount.value = null; bookSymbolsLoaded.value = false
  bookRequestKey.value = ''
  directionRequestKey.value = ''
  newcomerRequestKey.value = ''
  bookLoading.value = false; directionLoading.value = false; newcomerLoading.value = false
  if (!options.preserveAccount) {
    closeAccount()
  }
  try {
    data.value = await fetchAnalysis(request.value)
    if (currentAnalysisVersion !== analysisVersion) return
    try { warehouseStatus.value = await fetchWarehouseStatus() } catch { /* analysis succeeded; retain the last Warehouse status */ }
    if (options.preserveAccount && accountBeforeRefresh) {
      const refreshed = (data.value.accounts || []).find(account => account.platform === accountBeforeRefresh.platform && account.login === accountBeforeRefresh.login)
      if (refreshed) selectedAccount.value = refreshed
    }
    rulesDirty.value = false
    await refreshActiveAnalytics(currentAnalysisVersion)
  } catch (err) {
    if (currentAnalysisVersion === analysisVersion) error.value = err instanceof Error ? err.message : String(err)
  } finally {
    if (currentAnalysisVersion === analysisVersion) loading.value = false
  }
}
async function refreshLocalSnapshots() {
  snapshotRefreshing.value = true
  error.value = ''
  try {
    await refreshLocalSnapshotsApi(request.value)
    warehouseStatus.value = await fetchWarehouseStatus()
    await loadAnalysis({ preserveAccount: false })
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { snapshotRefreshing.value = false }
}
async function openAccount(account: AccountRow) {
  const appliedDirectionAccount = directionData.value?.accounts?.find(item => item.platform === account.platform && item.login === account.login) || null
  const requestId = ++detailRequestId
  selectedAccount.value = account
  selectedDirectionAccount.value = appliedDirectionAccount
  accountDetail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    const detail = await fetchAccountDetail(account, appliedDirectionAccount ? directionRequest.value : request.value)
    if (requestId === detailRequestId) accountDetail.value = detail
  } catch (err) {
    if (requestId === detailRequestId) detailError.value = err instanceof Error ? err.message : String(err)
  } finally {
    if (requestId === detailRequestId) detailLoading.value = false
  }
}
function closeAccount() {
  detailRequestId += 1
  selectedAccount.value = null
  selectedDirectionAccount.value = null
  accountDetail.value = null
  detailError.value = ''
}
async function loadBook() {
  const includeSymbols = activeTab.value === 'users'
  const currentRequestKey = requestKey(request.value)
  const bookMatchesRequest = bookData.value && bookRequestKey.value === currentRequestKey
  if ((bookMatchesRequest && (!includeSymbols || bookSymbolsLoaded.value)) || bookLoading.value || activeTab.value === 'overview') return
  const requestVersion = analysisVersion
  const loadVersion = ++bookLoadVersion
  bookLoading.value = true
  const population = data.value.population_accounts || data.value.accounts || []
  try {
    const result = await fetchBookAnalytics(
      request.value,
      population.filter(a => a.book === 'abook').map(a => ({ platform: a.platform, login: a.login })),
      data.value.analysis_token,
      includeSymbols,
    )
    if (requestVersion === analysisVersion && loadVersion === bookLoadVersion) {
      bookData.value = result
      bookRequestKey.value = currentRequestKey
      bookSymbolsLoaded.value = includeSymbols
    }
  } catch (err) { if (requestVersion === analysisVersion && loadVersion === bookLoadVersion) error.value = err instanceof Error ? err.message : String(err) } finally { if (loadVersion === bookLoadVersion) bookLoading.value = false }
}
async function loadDirection() {
  const currentRequestKey = requestKey(directionRequest.value)
  if ((directionData.value && directionRequestKey.value === currentRequestKey) || directionLoading.value || activeTab.value !== 'direction') return
  const requestVersion = analysisVersion
  const loadVersion = ++directionLoadVersion
  directionLoading.value = true
  try {
    const result = await fetchDirectionAnalytics(directionRequest.value, data.value.analysis_token)
    if (requestVersion === analysisVersion && loadVersion === directionLoadVersion) {
      directionData.value = result
      directionRequestKey.value = currentRequestKey
    }
  } catch (err) { if (requestVersion === analysisVersion && loadVersion === directionLoadVersion) error.value = err instanceof Error ? err.message : String(err) } finally { if (loadVersion === directionLoadVersion) directionLoading.value = false }
}
async function runDirection(payload?: RequestModel) {
  if (payload) directionRequest.value = payload
  activeTab.value = 'direction'
  directionData.value = null
  selectedDirectionAccount.value = null
  await loadDirection()
}
async function loadNewcomer() {
  const currentRequestKey = `${requestKey(newcomerRequest.value)}:${newcomerMaxActiveDays.value}`
  if ((newcomerData.value && newcomerRequestKey.value === currentRequestKey) || newcomerLoading.value || activeTab.value !== 'newcomer') return
  if (!data.value.analysis_token) {
    error.value = '请先在总览点击「应用筛选与验证」，再运行新人筛选'
    return
  }
  const requestVersion = analysisVersion
  const loadVersion = ++newcomerLoadVersion
  newcomerLoading.value = true
  try {
    const result = await fetchNewcomerAnalytics(
      newcomerRequest.value,
      data.value.analysis_token,
      newcomerMaxActiveDays.value,
    )
    if (requestVersion === analysisVersion && loadVersion === newcomerLoadVersion) {
      newcomerData.value = result
      newcomerRequestKey.value = currentRequestKey
    }
  } catch (err) { if (requestVersion === analysisVersion && loadVersion === newcomerLoadVersion) error.value = err instanceof Error ? err.message : String(err) } finally { if (loadVersion === newcomerLoadVersion) newcomerLoading.value = false }
}

async function refreshActiveAnalytics(expectedVersion: number) {
  if (expectedVersion !== analysisVersion) return
  if (activeTab.value === 'users' || activeTab.value === 'risk-routing') await loadBook()
  else if (activeTab.value === 'direction') await loadDirection()
  else if (activeTab.value === 'newcomer') await loadNewcomer()
}

async function runNewcomer(payload?: RequestModel) {
  if (payload) newcomerRequest.value = payload
  activeTab.value = 'newcomer'
  newcomerData.value = null
  await loadNewcomer()
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
function downloadDirectionExport() {
  const accounts = directionData.value?.accounts || []
  const headers = ['platform', 'login', 'quadrant', 'long_trade_count', 'long_win_rate', 'long_profit_factor', 'long_side_pnl', 'short_trade_count', 'short_win_rate', 'short_profit_factor', 'short_side_pnl', 'in_total_abook']
  const lines = accounts.map(account => {
    const long = account.long?.selection || {}
    const short = account.short?.selection || {}
    return [account.platform, account.login, account.quadrant, long.trade_count, long.win_rate, long.profit_factor ?? '', long.side_pnl, short.trade_count, short.win_rate, short.profit_factor ?? '', short.side_pnl, account.in_total_abook].map(value => JSON.stringify(value ?? '')).join(',')
  })
  const blob = new Blob([[headers.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob); link.download = 'abook_direction_accounts.csv'; link.click(); URL.revokeObjectURL(link.href)
}
function openDirectionAccount(account: Record<string, any>) {
  const match = (data.value.accounts || []).find(item => item.platform === account.platform && item.login === account.login)
  if (match) {
    openAccount(match)
    return
  }
  openAccount({
    platform: account.platform,
    login: account.login,
    account_group: account.account_group || '',
    book: account.book || 'bbook',
    selection_source: 'direction',
    selection_client_net_pnl: 0,
    validation_client_net_pnl: 0,
    validation_status: 'unknown',
    selection: {},
    validation: {},
    stability: { score: 0, tier: '—' },
    selection_flags: [],
  } as AccountRow)
}
function selectTab(tab: Tab) {
  activeTab.value = tab
  error.value = ''
  if (tab === 'users' || tab === 'risk-routing') loadBook()
  else if (tab === 'direction') loadDirection()
  else if (tab === 'newcomer') loadNewcomer()
}
function reset() {
  request.value = {
    selection: { start: '2026-05-01', end: '2026-06-30' },
    validation: { start: '2026-07-01', end: '2026-07-22' },
    platforms: ['mt4', 'mt5', 'hh_mt5'],
    filters: { groups: [], logins: [] },
    rules: { ...defaultRules },
    personal_candidate_list: false,
    news_candidate_list: false,
  }
  directionRequest.value = JSON.parse(JSON.stringify(request.value)) as RequestModel
  newcomerRequest.value = JSON.parse(JSON.stringify(request.value)) as RequestModel
  newcomerMaxActiveDays.value = 60
  error.value = ''
  loadAnalysis()
}
watch(() => request.value.rules, () => { rulesDirty.value = true }, { deep: true })
const snapshotNeedsRefresh = computed(() => {
  const status = warehouseStatus.value
  if (!status || status.source !== 'local' || !status.snapshots) return false
  return Object.values(status.snapshots).some(snapshot => (
    snapshot.status !== 'ready'
    || snapshot.selection_start !== request.value.selection.start
    || snapshot.selection_end !== request.value.selection.end
  ))
})
onMounted(async () => {
  try { warehouseStatus.value = await fetchWarehouseStatus() } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  await loadAnalysis()
})
const tabs: Array<{ id: Tab; label: string }> = [
  { id: 'overview', label: '总览' }, { id: 'users', label: '用户结构' },
  { id: 'risk-routing', label: '风险与分流' }, { id: 'direction', label: '多空分向' },
  { id: 'newcomer', label: '新人滚动筛' },
]
</script>

<template>
  <div class="app-shell">
    <header class="topbar"><div><span class="kicker">RISK / A-BOOK ANALYTICS</span><h1>Abook 筛选与 Book 分析</h1><p>筛选期 → 样本外验证 · 用户表现与交易详情</p></div><div class="top-actions"><button class="ghost" @click="downloadExport">导出 Abook CSV</button><span class="status-pill" :class="loading ? 'busy' : 'ready'">{{ loading ? '查询中' : '就绪' }}</span></div></header>
    <div class="layout">
      <FilterSidebar :request="request" :data="data" :loading="loading" :rules-dirty="rulesDirty" :warehouse-status="warehouseStatus" :snapshot-needs-refresh="snapshotNeedsRefresh" :snapshot-refreshing="snapshotRefreshing" @apply="loadAnalysis" @refresh-snapshots="refreshLocalSnapshots" @reset="reset" />
      <main class="content" :class="{ 'direction-content': activeTab === 'direction' || activeTab === 'newcomer' }"><div v-if="error" class="alert error">{{ error }}</div><nav class="tabs"><button v-for="tab in tabs" :key="tab.id" :class="{ active: activeTab === tab.id }" @click="selectTab(tab.id)">{{ tab.label }}</button></nav>
        <template v-if="loading"><section class="panel query-state" aria-live="polite"><span class="kicker">LOCAL QUERY</span><h2>正在读取本地交易数据…</h2><p>首次查询会扫描本地 Warehouse，完成后本次结果会被缓存；请稍候，不要重复点击。</p></section></template>
        <template v-else-if="activeTab === 'overview'"><AbookAnalysis :data="data" @open="openAccount" /><KpiCards :data="data" /><SelectionFunnel :data="data" :rules-dirty="rulesDirty" /><AccountsTable :accounts="data.accounts || []" @open="openAccount" /></template>
        <template v-else-if="activeTab === 'direction'"><DirectionPanel :analytics="directionData" :loading="directionLoading" :request="directionRequest" @open="openDirectionAccount" @export="downloadDirectionExport" @run="runDirection" /></template>
        <template v-else-if="activeTab === 'newcomer'"><NewcomerPanel :analytics="newcomerData" :loading="newcomerLoading" :request="newcomerRequest" :max-active-days="newcomerMaxActiveDays" :analysis-token="data.analysis_token" @update:max-active-days="newcomerMaxActiveDays = $event" @run="runNewcomer" /></template>
        <template v-else><BookPerformance :analytics="bookData" :loading="bookLoading" :active-tab="activeTab" :request="request" :accounts="data.population_accounts || data.accounts || []" @open="openAccount" /></template>
      </main>
    </div>
    <AccountDrawer :account="selectedAccount" :detail="accountDetail" :direction-account="selectedDirectionAccount" :loading="detailLoading" :error="detailError" @close="closeAccount" />
  </div>
</template>
