<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type {
  NewcomerAccount,
  NewcomerAccountSensitivity,
  NewcomerAnalyticsPayload,
  RequestModel,
} from '../types'
import { fetchNewcomerAccount } from '../api'
import { phaseDividerMarkLine } from '../phaseDivider'
import { money, number, pct, pf, pnlClass, profitableRate } from '../utils/format'

const props = defineProps<{
  analytics: NewcomerAnalyticsPayload | null
  loading: boolean
  request: RequestModel
  maxActiveDays: number
  analysisToken?: string
}>()
const emit = defineEmits<{
  (event: 'run', payload: RequestModel): void
  (event: 'update:maxActiveDays', value: number): void
}>()

type Pool = 'admitted' | 'observe' | 'rejected'
type ChartMode = 'post_asof' | 'full_window'
type TopMode = 'post_asof' | 'validation'
type SortKey = 'as_of' | 'pnl' | 'trade_count' | 'active_days' | 'trades_to_mature'

// Local editable copy of the request — props are read-only, so we never
// v-model directly on props.request. App.vue owns the source of truth and
// receives our edits via the run payload.
const localRequest = ref<RequestModel>(JSON.parse(JSON.stringify(props.request)) as RequestModel)
watch(() => props.request, (next) => {
  localRequest.value = JSON.parse(JSON.stringify(next)) as RequestModel
}, { deep: true })

const activePool = ref<Pool>('admitted')
const chartMode = ref<ChartMode>('post_asof')
const topMode = ref<TopMode>('post_asof')
const page = ref(1)
const pageSize = ref(12)
const searchQuery = ref('')
const sortKey = ref<SortKey>('pnl')
const sortDir = ref<'asc' | 'desc'>('desc')
const selected = ref<NewcomerAccount | null>(null)
const sensitivity = ref<NewcomerAccountSensitivity | null>(null)
const sensitivityLoading = ref(false)
const sensitivityError = ref('')
const customMinTrades = ref(75)
const statsEnd = ref('')
const cumulativeChart = ref<HTMLElement | null>(null)
const distributionChart = ref<HTMLElement | null>(null)
const asOfChart = ref<HTMLElement | null>(null)
let cumulativeInstance: echarts.ECharts | null = null
let distributionInstance: echarts.ECharts | null = null
let asOfInstance: echarts.ECharts | null = null

const martingaleLevels = ['extreme', 'high', 'medium', 'low']

function flagLabel(flag: string): string {
  const labels: Record<string, string> = {
    no_history: '窗口内无成交',
    inactive: '窗口内无成交',
    insufficient_sample: '样本不足/未成熟',
    profit_factor: 'PF 未达标',
    win_rate: '胜率未达标',
    payoff_ratio: '盈亏比未达标',
    long_trades_ratio: '多单比例未达标',
    profit_concentration: 'Top1 日集中度过高',
    leverage_p95_ratio: '杠杆未通过',
    martingale_hard_block: '马丁硬拦截',
    short_history_exhausted: '短历史轨已尽',
    active_days_exceeded: '活跃日超限',
    quality_failed: '质量未过线',
  }
  return labels[flag] || flag
}
function poolLabel(pool: string): string {
  const labels: Record<string, string> = {
    admitted: '入选',
    observe: '短历史观察',
    blocked: '马丁拦截',
    left_track: '已离轨',
    rejected: '未过线',
    inactive: '无成交',
  }
  return labels[pool] || pool
}

const rows = computed<NewcomerAccount[]>(() => {
  if (!props.analytics) return []
  if (activePool.value === 'admitted') return props.analytics.admitted || []
  if (activePool.value === 'observe') return props.analytics.observe || []
  return props.analytics.rejected || []
})
const pnlField = computed(() => activePool.value === 'observe' ? 'validation_period_pnl' : 'post_asof_pnl')
const filteredRows = computed<NewcomerAccount[]>(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return rows.value
  return rows.value.filter(row =>
    String(row.login).includes(query) || String(row.platform).toLowerCase().includes(query)
  )
})
function sortValue(row: NewcomerAccount, key: SortKey): number {
  if (key === 'pnl') return number(row[pnlField.value as keyof NewcomerAccount])
  if (key === 'trade_count') return number(row.selection?.trade_count)
  if (key === 'active_days') return number(row.active_trade_days)
  if (key === 'as_of') return row.as_of ? Date.parse(row.as_of) : 0
  if (key === 'trades_to_mature') return number(row.trades_to_mature)
  return 0
}
const sortedRows = computed<NewcomerAccount[]>(() => {
  const list = [...filteredRows.value]
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return list.sort((a, b) => (sortValue(a, key) - sortValue(b, key)) * dir)
})
const pageCount = computed(() => Math.max(1, Math.ceil(sortedRows.value.length / pageSize.value)))
const pagedRows = computed(() => sortedRows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const postSummary = computed(() => props.analytics?.summary?.post_asof || {})
const validationSummary = computed(() => props.analytics?.summary?.validation || {})
const topData = computed(() => {
  if (topMode.value === 'validation') return props.analytics?.top_accounts?.validation || { winners: [], losers: [] }
  return props.analytics?.top_accounts?.post_asof || { winners: [], losers: [] }
})
const truncation = computed(() => props.analytics?.truncation)
const unqualifiedTotal = computed(() => props.analytics?.counts?.unqualified_total
  ?? ((props.analytics?.counts?.rejected || 0) + (props.analytics?.counts?.left_track || 0) + (props.analytics?.counts?.martingale_blocked || 0)))

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'trades_to_mature' ? 'asc' : 'desc'
  }
}

function selectPool(pool: Pool) {
  activePool.value = pool
  page.value = 1
  searchQuery.value = ''
  selected.value = null
  sensitivity.value = null
  // Observe is most useful sorted by maturity progress; others by P&L.
  if (pool === 'observe') { sortKey.value = 'trades_to_mature'; sortDir.value = 'asc' }
  else { sortKey.value = 'pnl'; sortDir.value = 'desc' }
}
function runSearch() {
  page.value = 1
  selected.value = null
  sensitivity.value = null
  emit('run', JSON.parse(JSON.stringify(localRequest.value)) as RequestModel)
}

function downloadCsv() {
  if (!sortedRows.value.length) return
  const headers = ['platform', 'login', 'account_group', 'pool', 'as_of', 'window_trade_count', 'active_trade_days', 'trade_count', 'win_rate', 'profit_factor', 'post_asof_pnl', 'validation_period_pnl', 'trades_to_mature', 'days_to_cap', 'flags']
  const lines = sortedRows.value.map(row => [
    row.platform, row.login, row.account_group || '', row.pool, row.as_of || '',
    row.window_trade_count || 0, row.active_trade_days || 0,
    row.selection?.trade_count || 0, row.selection?.win_rate ?? '', row.selection?.profit_factor ?? '',
    row.post_asof_pnl ?? 0, row.validation_period_pnl ?? 0,
    row.trades_to_mature ?? 0, row.days_to_cap ?? 0,
    (row.selection_flags || []).join('|'),
  ].map(v => JSON.stringify(v ?? '')).join(','))
  const blob = new Blob([[headers.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob); link.download = `newcomer_${activePool.value}.csv`
  link.click(); URL.revokeObjectURL(link.href)
}

async function openAccount(account: NewcomerAccount) {
  selected.value = account
  customMinTrades.value = number(account.min_trades_used || localRequest.value.rules.min_trades || 75)
  statsEnd.value = account.stats_end || localRequest.value.validation.end
  sensitivity.value = null
  sensitivityError.value = ''
  await loadSensitivity()
}

// Sensitivity sweep grid: derive from the configured min_trades so the sweep
// stays meaningful when the user changes the bar, plus the user's custom value.
// Dedupe so we never send/ask for the same cutoff twice.
const sensitivityGrid = computed<number[]>(() => {
  const base = number(localRequest.value.rules.min_trades) || 75
  const candidates = [Math.round(base * 0.5), base, base * 2, base * 4, customMinTrades.value]
  return Array.from(new Set(candidates.filter(v => v >= 1))).sort((a, b) => a - b)
})

async function loadSensitivity() {
  if (!selected.value) return
  sensitivityLoading.value = true
  sensitivityError.value = ''
  try {
    sensitivity.value = await fetchNewcomerAccount({
      analysis: localRequest.value,
      analysis_token: props.analysisToken,
      platform: selected.value.platform,
      login: selected.value.login,
      min_trades: customMinTrades.value,
      min_trades_values: sensitivityGrid.value,
      stats_end: statsEnd.value || undefined,
      max_active_days: props.maxActiveDays,
    })
  } catch (err) {
    sensitivityError.value = err instanceof Error ? err.message : String(err)
  } finally {
    sensitivityLoading.value = false
  }
}

function ensureChart(el: HTMLElement): echarts.ECharts {
  return echarts.getInstanceByDom(el) ?? echarts.init(el)
}

function disposeCharts() {
  cumulativeInstance?.dispose()
  distributionInstance?.dispose()
  asOfInstance?.dispose()
  cumulativeInstance = null
  distributionInstance = null
  asOfInstance = null
}

function resizeCharts() {
  cumulativeInstance?.resize()
  distributionInstance?.resize()
  asOfInstance?.resize()
}

function renderCumulative() {
  if (!cumulativeChart.value) return
  const cumulativeRows = chartMode.value === 'post_asof'
    ? (props.analytics?.cumulative_pnl?.post_asof || [])
    : (props.analytics?.cumulative_pnl?.full_window || [])
  const dates = cumulativeRows.map(row => row.date)
  cumulativeInstance = ensureChart(cumulativeChart.value)
  cumulativeInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => money(value) },
    grid: { left: 72, right: 28, top: 36, bottom: 38, containLabel: true },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#8497ad' } },
    yAxis: {
      type: 'value',
      name: chartMode.value === 'post_asof' ? '入选后累积客户净 P&L' : '全窗累积客户净 P&L',
      nameTextStyle: { color: '#8497ad' },
      axisLabel: { color: '#8497ad' },
      splitLine: { lineStyle: { color: '#20364e' } },
    },
    series: [{
      name: '入选 cohort',
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: cumulativeRows.map(row => row.cumulative_pnl),
      lineStyle: { width: 3, color: '#54d6a6' },
      areaStyle: { color: 'rgba(84,214,166,.10)' },
      markLine: phaseDividerMarkLine(dates, localRequest.value),
    }],
  }, { notMerge: true })
}

function renderDistribution() {
  if (!distributionChart.value) return
  const dist = props.analytics?.pnl_distribution?.post_asof || []
  const colors = ['#d95f66', '#ed7b82', '#f3a4a9', '#7d8da3', '#8bd8bb', '#54d6a6', '#2eaf82']
  distributionInstance = ensureChart(distributionChart.value)
  distributionInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 52, right: 20, top: 28, bottom: 70, containLabel: true },
    xAxis: {
      type: 'category',
      data: dist.map(row => row.label),
      axisLabel: { color: '#8497ad', rotate: 25, interval: 0 },
    },
    yAxis: {
      type: 'value',
      name: '用户数',
      nameTextStyle: { color: '#8497ad' },
      axisLabel: { color: '#8497ad' },
      splitLine: { lineStyle: { color: '#20364e' } },
    },
    series: [{
      type: 'bar',
      barMaxWidth: 34,
      data: dist.map((row, index) => ({
        value: row.accounts || 0,
        itemStyle: { color: colors[index] || '#7d8da3' },
      })),
    }],
  }, { notMerge: true })
}

function renderAsOf() {
  if (!asOfChart.value) return
  const buckets = props.analytics?.as_of_distribution || []
  asOfInstance = ensureChart(asOfChart.value)
  asOfInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 52, right: 20, top: 28, bottom: 70, containLabel: true },
    xAxis: {
      type: 'category',
      data: buckets.map(row => row.date),
      axisLabel: { color: '#8497ad', rotate: 30, interval: 0 },
    },
    yAxis: {
      type: 'value',
      name: '入选人数',
      nameTextStyle: { color: '#8497ad' },
      axisLabel: { color: '#8497ad' },
      splitLine: { lineStyle: { color: '#20364e' } },
    },
    series: [{
      type: 'bar',
      barMaxWidth: 28,
      data: buckets.map(row => ({ value: row.accounts || 0, itemStyle: { color: '#f0bd72' } })),
    }],
  }, { notMerge: true })
}

// Split watches: chartMode only re-renders the cumulative curve, not the
// distribution / as-of charts. Analytics (a reference swap) re-renders all.
watch(chartMode, () => nextTick(renderCumulative))
watch(() => props.analytics, () => nextTick(() => {
  page.value = Math.min(page.value, pageCount.value)
  renderCumulative()
  renderDistribution()
  renderAsOf()
}))
watch(pageCount, () => { if (page.value > pageCount.value) page.value = pageCount.value })

function handleResize() { resizeCharts() }
window.addEventListener('resize', handleResize)
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  disposeCharts()
})
</script>

<template>
  <section class="panel direction-panel newcomer-panel">
    <div class="panel-head">
      <div>
        <span class="kicker">NEWCOMER ROLLING SCREEN</span>
        <h2>新人滚动筛</h2>
        <p class="hint">仅纳入窗口内 trades &gt; 0 · 个人 as-of · 活跃日 ≤ N · 不含总览 Abook / 僵尸账号</p>
      </div>
      <div class="direction-actions">
        <button class="primary" :disabled="loading || !localRequest.platforms.length" @click="runSearch">
          {{ analytics ? '重新运行新人筛选' : '运行新人筛选' }}
        </button>
      </div>
    </div>

    <div class="direction-parameters">
      <div class="parameter-heading">
        <div>
          <h3>新人筛选参数</h3>
          <p class="hint">独立于总览侧栏；修改后不会自动查询。窗口内 0 成交账号直接跳过。须先完成总览「应用筛选与验证」。</p>
        </div>
        <span class="tag">独立参数</span>
      </div>
      <div class="date-grid">
        <label>筛选开始<input v-model="localRequest.selection.start" type="date"></label>
        <label>筛选结束<input v-model="localRequest.selection.end" type="date"></label>
        <label>验证开始<input v-model="localRequest.validation.start" type="date"></label>
        <label>验证结束<input v-model="localRequest.validation.end" type="date"></label>
      </div>
      <div class="direction-parameter-grid">
        <label>短历史活跃日上限 N<input :value="maxActiveDays" type="number" min="1" max="365" @input="emit('update:maxActiveDays', Number(($event.target as HTMLInputElement).value) || 60)"></label>
        <label>最低交易笔数<input v-model.number="localRequest.rules.min_trades" type="number" min="0"></label>
        <label>最低胜率<input v-model.number="localRequest.rules.min_win_rate" type="number" min="0" max="1" step="0.01"></label>
        <label>最低 Profit Factor<input v-model.number="localRequest.rules.min_profit_factor" type="number" min="0" step="0.01"></label>
        <label>最低盈亏比<input v-model.number="localRequest.rules.min_payoff_ratio" type="number" min="0" step="0.01"></label>
        <label>Long 比例下限<input v-model.number="localRequest.rules.min_long_trades_ratio" type="number" min="0" max="1" step="0.01"></label>
        <label>Long 比例上限<input v-model.number="localRequest.rules.max_long_trades_ratio" type="number" min="0" max="1" step="0.01"></label>
        <label>Top1 日利润贡献率上限<input v-model.number="localRequest.rules.max_top1_day_profit_contribution" type="number" min="0" max="1" step="0.01"></label>
        <label>最大杠杆率 P95<input v-model.number="localRequest.rules.max_leverage_p95_ratio" type="number" min="0"></label>
        <label>高杠杆持仓例外秒数<input v-model.number="localRequest.rules.max_high_leverage_holding_seconds" type="number" min="0"></label>
      </div>
      <div class="direction-parameter-footer">
        <div class="platforms">
          <label v-for="platform in ['mt4', 'mt5', 'hh_mt5']" :key="platform" class="check">
            <input v-model="localRequest.platforms" :value="platform" type="checkbox"> {{ platform }}
          </label>
        </div>
        <div class="direction-martingale">
          <span>确认马丁阻断等级</span>
          <label v-for="level in martingaleLevels" :key="level" class="check">
            <input v-model="localRequest.rules.excluded_martingale_levels" type="checkbox" :value="level"> {{ level }}
          </label>
          <small>与总览一致：命中硬拦截者不进可过线/入选。</small>
        </div>
      </div>
    </div>

    <div v-if="loading" class="newcomer-skeleton" aria-busy="true" aria-label="加载新人滚动筛">
      <div class="skeleton-line"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-line"></div>
      <p class="empty">加载新人滚动筛…</p>
    </div>
    <template v-else-if="analytics">
      <div class="kpi-grid direction-kpis">
        <article class="kpi accent"><span>入选人数</span><strong>{{ analytics.kpi?.admitted_accounts || 0 }}</strong><small>个人 as-of 过线</small></article>
        <article class="kpi"><span>入选后净 P&amp;L</span><strong :class="pnlClass(analytics.kpi?.post_asof_net_pnl)">{{ money(analytics.kpi?.post_asof_net_pnl) }}</strong><small>as-of 次日 → {{ analytics.validation?.end }}</small></article>
        <article class="kpi"><span>盈 / 亏人数</span><strong>{{ analytics.kpi?.admitted_positive || 0 }} / {{ analytics.kpi?.admitted_negative || 0 }}</strong><small>均值 {{ money(analytics.kpi?.average_post_asof_pnl) }} · 中位 {{ money(analytics.kpi?.median_post_asof_pnl) }}</small></article>
        <article class="kpi"><span>短历史观察</span><strong>{{ analytics.kpi?.observe_accounts || 0 }}</strong><small>有成交、尚未成熟</small></article>
        <article class="kpi"><span>跳过无成交</span><strong>{{ analytics.kpi?.skipped_inactive || 0 }}</strong><small>窗口 trades = 0</small></article>
      </div>

      <div class="phase-cards">
        <article class="metric-card">
          <span class="kicker">入选 · 个人 as-of 后</span>
          <strong :class="pnlClass(postSummary.net_pnl)">{{ money(postSummary.net_pnl) }}</strong>
          <small>{{ postSummary.accounts || 0 }} 用户 · 赚 {{ postSummary.profitable_accounts || 0 }} · 亏 {{ postSummary.loss_accounts || 0 }} · 中性 {{ postSummary.neutral_accounts || 0 }} · 盈利占比 {{ profitableRate(postSummary.profitable_accounts, postSummary.accounts) }}</small>
          <small>盈利 {{ money(postSummary.positive_pnl) }} · 亏损 {{ money(postSummary.negative_pnl) }}</small>
          <small>平均 {{ money(postSummary.average_pnl) }} · 中位 {{ money(postSummary.median_pnl) }} · Top5 集中度 {{ pct(postSummary.profit_concentration?.top_5?.absolute_share) }}</small>
        </article>
        <article class="metric-card">
          <span class="kicker">入选 · 统一验证窗诊断</span>
          <strong :class="pnlClass(validationSummary.net_pnl)">{{ money(validationSummary.net_pnl) }}</strong>
          <small>{{ validationSummary.accounts || 0 }} 用户 · 赚 {{ validationSummary.profitable_accounts || 0 }} · 亏 {{ validationSummary.loss_accounts || 0 }}</small>
          <small>仅作对照；主 KPI 仍以个人 as-of 后为准</small>
          <small>平均 {{ money(validationSummary.average_pnl) }} · 中位 {{ money(validationSummary.median_pnl) }}</small>
        </article>
      </div>

      <div class="book-section-title">
        <div>
          <h3>入选 cohort 表现</h3>
          <p class="hint">累积曲线按每人 as-of 次日起计；全窗曲线含筛选期仅作对照</p>
        </div>
        <label>曲线口径
          <select v-model="chartMode">
            <option value="post_asof">入选后（主口径）</option>
            <option value="full_window">全窗对照</option>
          </select>
        </label>
      </div>
      <div class="two-col direction-chart-pair">
        <article class="inset">
          <h5>累积客户净 P&amp;L</h5>
          <div ref="cumulativeChart" class="book-chart direction-cumulative-chart"></div>
        </article>
        <article class="inset">
          <h5>入选后 P&amp;L 分布</h5>
          <div ref="distributionChart" class="book-chart direction-distribution-chart"></div>
        </article>
      </div>

      <div class="inset" v-if="(analytics.as_of_distribution || []).length">
        <h5>按 as-of 日期的入选人数</h5>
        <div ref="asOfChart" class="book-chart direction-distribution-chart"></div>
      </div>

      <div class="two-col">
        <article class="inset">
          <div class="book-section-title">
            <h4>Top 盈利</h4>
            <label class="compact-select">口径
              <select v-model="topMode">
                <option value="post_asof">入选后</option>
                <option value="validation">验证窗</option>
              </select>
            </label>
          </div>
          <div v-for="row in (topData.winners || []).slice(0, 5)" :key="`w-${row.platform}-${row.login}`" class="list-row">
            <span>{{ row.platform }} / {{ row.login }}<small>as-of {{ row.as_of || '—' }} · {{ row.active_trade_days || 0 }} 日</small></span>
            <b class="positive">{{ money(row.pnl) }}</b>
          </div>
          <div v-if="!(topData.winners || []).length" class="empty">暂无</div>
        </article>
        <article class="inset">
          <h4>Top 亏损</h4>
          <div v-for="row in (topData.losers || []).slice(0, 5)" :key="`l-${row.platform}-${row.login}`" class="list-row">
            <span>{{ row.platform }} / {{ row.login }}<small>as-of {{ row.as_of || '—' }} · {{ row.active_trade_days || 0 }} 日</small></span>
            <b class="negative">{{ money(row.pnl) }}</b>
          </div>
          <div v-if="!(topData.losers || []).length" class="empty">暂无</div>
        </article>
      </div>

      <div class="direction-toolbar">
        <button class="ghost compact" :class="{ active: activePool === 'admitted' }" @click="selectPool('admitted')">入选 {{ analytics.counts?.admitted || 0 }}</button>
        <button class="ghost compact" :class="{ active: activePool === 'observe' }" @click="selectPool('observe')">短历史观察 {{ analytics.counts?.observe || 0 }}</button>
        <button class="ghost compact" :class="{ active: activePool === 'rejected' }" @click="selectPool('rejected')">未过线/离轨 {{ unqualifiedTotal }}</button>
        <span class="hint">跳过 Abook {{ analytics.counts?.skipped_abook || 0 }} · 跳过无成交 {{ analytics.counts?.skipped_inactive || 0 }} · 活跃候选 {{ analytics.counts?.active_candidates || 0 }} · {{ analytics.pnl_basis }}</span>
      </div>

      <div class="newcomer-table-tools">
        <input v-model="searchQuery" type="search" placeholder="按 login / platform 过滤…" aria-label="过滤账户" @input="page = 1">
        <label>每页
          <select v-model.number="pageSize" @change="page = 1">
            <option :value="12">12</option>
            <option :value="24">24</option>
            <option :value="50">50</option>
          </select>
        </label>
        <button class="ghost compact" :disabled="!sortedRows.length" @click="downloadCsv">导出 CSV</button>
        <span class="hint" v-if="truncation?.observe_truncated && activePool === 'observe'">仅显示前 {{ truncation?.observe_cap }} 条（共 {{ analytics.counts?.observe || 0 }}），如需完整请导出 CSV</span>
        <span class="hint" v-if="truncation?.rejected_truncated && activePool === 'rejected'">仅显示前 {{ truncation?.rejected_cap }} 条（共 {{ unqualifiedTotal }}），如需完整请导出 CSV</span>
      </div>

      <div class="table-scroll direction-account-table">
        <table aria-label="新人筛选账户表">
          <thead>
            <tr>
              <th>账户</th>
              <th class="sortable" @click="toggleSort('trade_count')">窗口笔数</th>
              <th class="sortable" @click="toggleSort('active_days')">活跃日</th>
              <th class="sortable" @click="toggleSort('as_of')">as-of</th>
              <th>筛选笔数</th>
              <th>胜率</th>
              <th>PF</th>
              <th v-if="activePool === 'observe'">距成熟 / 距上限</th>
              <th>状态</th>
              <th class="sortable" @click="toggleSort('pnl')">{{ activePool === 'observe' ? '验证期诊断 P&L' : '入选后 P&L' }}</th>
              <th>未过原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in pagedRows" :key="`${account.platform}-${account.login}`" class="clickable-row" @click="openAccount(account)">
              <td>{{ account.platform }} / {{ account.login }}<small>{{ account.account_group }}</small></td>
              <td>{{ account.window_trade_count || 0 }}</td>
              <td>{{ account.active_trade_days || 0 }}</td>
              <td>{{ account.as_of || '—' }}</td>
              <td>{{ account.selection?.trade_count || 0 }}</td>
              <td>{{ pct(account.selection?.win_rate) }}</td>
              <td>{{ pf(account.selection?.profit_factor) }}</td>
              <td v-if="activePool === 'observe'">
                <span v-if="account.trades_to_mature > 0">差 {{ account.trades_to_mature }} 笔</span>
                <span v-else>已达标</span>
                <small>/ 剩 {{ account.days_to_cap }} 天</small>
              </td>
              <td><span class="tag" :class="account.admitted ? '' : 'danger'">{{ poolLabel(account.pool) }}</span></td>
              <td :class="pnlClass(activePool === 'observe' ? account.validation_period_pnl : account.post_asof_pnl)">
                {{ money(activePool === 'observe' ? account.validation_period_pnl : account.post_asof_pnl) }}
              </td>
              <td>
                <span v-for="flag in (account.selection_flags || []).slice(0, 3)" :key="flag" class="tag danger">{{ flagLabel(flag) }}</span>
                <small v-if="(account.selection_flags || []).length > 3">+{{ account.selection_flags.length - 3 }}</small>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!sortedRows.length" class="empty">当前池没有账户</div>
      </div>
      <div v-if="sortedRows.length" class="pagination direction-pagination">
        <button class="ghost compact" :disabled="page <= 1" @click="page--">上一页</button>
        <span>第 {{ page }} / {{ pageCount }} 页 · {{ sortedRows.length }} 个账户 · {{ poolLabel(activePool) }}</span>
        <button class="ghost compact" :disabled="page >= pageCount" @click="page++">下一页</button>
      </div>

      <div v-if="selected" class="inset newcomer-sensitivity">
        <div class="book-section-title">
          <div>
            <h3>{{ selected.platform }} / {{ selected.login }} · 单用户敏感性</h3>
            <p class="hint">单独改 min_trades / 统计结束日，仅重算该用户；后端有短缓存，重复请求秒回。</p>
          </div>
          <button class="ghost compact" @click="selected = null; sensitivity = null">关闭</button>
        </div>
        <div class="direction-parameter-grid">
          <label>该用户 min_trades<input v-model.number="customMinTrades" type="number" min="1" :disabled="sensitivityLoading"></label>
          <label>统计结束日<input v-model="statsEnd" type="date" :disabled="sensitivityLoading"></label>
        </div>
        <div class="direction-actions" style="justify-content:flex-start;margin:12px 0">
          <button class="primary" :disabled="sensitivityLoading" @click="loadSensitivity">重算该用户</button>
          <button v-if="sensitivityError" class="ghost compact" @click="loadSensitivity">重试</button>
        </div>
        <div v-if="sensitivityLoading" class="empty" aria-busy="true">重算中…</div>
        <div v-else-if="sensitivityError" class="alert error">{{ sensitivityError }}</div>
        <div v-else-if="sensitivity" class="table-scroll">
          <table aria-label="单用户敏感性扫描">
            <thead>
              <tr>
                <th>min_trades</th>
                <th>as-of</th>
                <th>活跃日</th>
                <th>是否过线</th>
                <th>距成熟</th>
                <th>入选后 P&amp;L</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="point in sensitivity.points" :key="point.min_trades_used">
                <td>{{ point.min_trades_used }}</td>
                <td>{{ point.as_of || '—' }}</td>
                <td>{{ point.active_trade_days }}</td>
                <td>{{ point.admitted ? '是' : '否' }}</td>
                <td>{{ point.trades_to_mature > 0 ? `差 ${point.trades_to_mature} 笔` : '已达标' }}</td>
                <td :class="pnlClass(point.post_asof_pnl)">{{ money(point.post_asof_pnl) }}</td>
                <td><span v-for="flag in (point.selection_flags || []).slice(0, 3)" :key="flag" class="tag danger">{{ flagLabel(flag) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
    <div v-else class="empty">请先在总览完成筛选，再点击「运行新人筛选」。只看窗口内真正有成交的短历史用户；结果不写回总览 Abook。</div>
  </section>
</template>
