<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{ analytics: any | null; loading: boolean; activeTab: string }>()
const chart = ref<HTMLElement | null>(null)
const cumulativeChart = ref<HTMLElement | null>(null)
const dailyChart = ref<HTMLElement | null>(null)
let instance: echarts.ECharts | null = null
let cumulativeInstance: echarts.ECharts | null = null
let dailyInstance: echarts.ECharts | null = null

function disposePnlCharts() {
  cumulativeInstance?.dispose()
  dailyInstance?.dispose()
  cumulativeInstance = null
  dailyInstance = null
}

function renderPnlCharts(analytics: any) {
  if (!cumulativeChart.value || !dailyChart.value) return
  instance?.dispose()
  instance = null
  disposePnlCharts()
  const abook = analytics.pnl_structure?.abook?.daily_series || []
  const bbook = analytics.pnl_structure?.bbook?.daily_series || []
  const dates = [...new Set([...abook, ...bbook].map((row: any) => row.date))].sort()
  const valuesByDate = (rows: any[], field: string) => Object.fromEntries(rows.map(row => [row.date, row[field] ?? 0]))
  const aCumulative = valuesByDate(abook, 'cumulative_pnl')
  const bCumulative = valuesByDate(bbook, 'cumulative_pnl')
  const aDaily = valuesByDate(abook, 'pnl')
  const bDaily = valuesByDate(bbook, 'pnl')

  cumulativeInstance = echarts.init(cumulativeChart.value)
  cumulativeInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9fb3c9' } },
    grid: { left: 58, right: 58, top: 42, bottom: 28 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#8497ad' } },
    yAxis: [
      { type: 'value', name: 'Abook', nameTextStyle: { color: '#54d6a6' }, axisLabel: { color: '#8497ad' }, splitLine: { lineStyle: { color: '#20364e' } } },
      { type: 'value', name: 'Bbook', nameTextStyle: { color: '#ff8d91' }, axisLabel: { color: '#8497ad' }, splitLine: { show: false } },
    ],
    series: [
      { name: 'Abook 累计客户 P&L', type: 'line', yAxisIndex: 0, smooth: true, data: dates.map(date => aCumulative[date]), lineStyle: { color: '#54d6a6' }, areaStyle: { color: 'rgba(84,214,166,.10)' } },
      { name: 'Bbook 累计客户 P&L', type: 'line', yAxisIndex: 1, smooth: true, data: dates.map(date => bCumulative[date]), lineStyle: { color: '#ff8d91' }, areaStyle: { color: 'rgba(255,141,145,.08)' } },
    ],
  })

  dailyInstance = echarts.init(dailyChart.value)
  dailyInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9fb3c9' } },
    grid: { left: 58, right: 18, top: 42, bottom: 28 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#8497ad' } },
    yAxis: { type: 'value', name: '每日客户 P&L', nameTextStyle: { color: '#8497ad' }, axisLabel: { color: '#8497ad' }, splitLine: { lineStyle: { color: '#20364e' } } },
    series: [
      { name: 'Abook 每日客户 P&L', type: 'line', smooth: true, data: dates.map(date => aDaily[date]), lineStyle: { color: '#54d6a6' } },
      { name: 'Bbook 每日客户 P&L', type: 'line', smooth: true, data: dates.map(date => bDaily[date]), lineStyle: { color: '#ff8d91' } },
    ],
  })
}

async function renderChart() {
  await nextTick()
  if (!props.analytics) return
  if (props.activeTab === 'users') {
    instance?.dispose()
    instance = null
    renderPnlCharts(props.analytics)
    return
  }
  disposePnlCharts()
  if (!chart.value) return
  instance?.dispose()
  instance = echarts.init(chart.value)
  const analytics = props.analytics
  let x: string[] = []
  let series: any[] = []
  if (props.activeTab === 'risk') {
    const rows = analytics.risk_exposure?.abook?.daily_turnover || []
    x = rows.map((row: any) => row.date)
    series = [{ name: 'Abook turnover', type: 'line', smooth: true, data: rows.map((row: any) => row.turnover), lineStyle: { color: '#f4c46a' } }]
  } else if (props.activeTab === 'routing') {
    const rows = analytics.routing_quality?.daily_hit_curves || []
    x = rows.map((row: any) => row.date)
    series = [
      { name: 'Abook 命中率', type: 'line', data: rows.map((row: any) => row.abook_hit_rate), lineStyle: { color: '#54d6a6' } },
      { name: 'Bbook 命中率', type: 'line', data: rows.map((row: any) => row.bbook_hit_rate), lineStyle: { color: '#ff8d91' } },
    ]
  } else {
    return
  }
  instance.setOption({ backgroundColor: 'transparent', tooltip: { trigger: 'axis' }, legend: { textStyle: { color: '#9fb3c9' } }, grid: { left: 44, right: 18, top: 42, bottom: 28 }, xAxis: { type: 'category', data: x, axisLabel: { color: '#8497ad' } }, yAxis: { type: 'value', axisLabel: { color: '#8497ad' }, splitLine: { lineStyle: { color: '#20364e' } } }, series })
}

watch(() => [props.analytics, props.activeTab], renderChart, { deep: true })
onBeforeUnmount(() => {
  instance?.dispose()
  disposePnlCharts()
})
</script>

<template>
  <section class="panel">
    <div class="panel-head"><div><span class="kicker">BOOK ANALYTICS</span><h2>Abook / Bbook 量化分析</h2></div><span class="hint">当前页签懒加载</span></div>
    <div v-if="loading" class="empty">加载 Book 分析…</div>
    <template v-else-if="analytics">
      <div class="book-grid"><article v-for="book in ['abook', 'bbook']" :key="book" class="book-card"><h3>{{ book === 'abook' ? 'Abook' : 'Bbook' }}</h3><p>筛选期客户净 P&amp;L <b>{{ (analytics.pnl_structure?.[book]?.selection?.customer_net_pnl ?? 0).toFixed(2) }}</b></p><p>验证期客户净 P&amp;L <b>{{ (analytics.pnl_structure?.[book]?.validation?.customer_net_pnl ?? 0).toFixed(2) }}</b></p><p v-if="book === 'bbook'">Bbook 公司盈亏（客户 P&amp;L 取负） <b>{{ (analytics.pnl_structure?.[book]?.validation?.company_profit_if_current_book ?? 0).toFixed(2) }}</b></p><p v-else>Abook 公司盈亏 <b>不由客户 P&amp;L 推断</b></p><p v-if="book === 'abook'">扣对冲成本理论公司增量 <b>{{ (analytics.risk_exposure?.abook?.after_cost_increment ?? 0).toFixed(2) }}</b></p><p>最大回撤（客户口径） <b>{{ (analytics.pnl_structure?.[book]?.max_drawdown ?? 0).toFixed(2) }}</b></p><p>Top 5 客户 P&amp;L 集中度 <b>{{ ((analytics.pnl_structure?.[book]?.profit_concentration?.top_5?.absolute_share ?? 0) * 100).toFixed(1) }}%</b></p><p>验证 Turnover <b>{{ (analytics.risk_exposure?.[book]?.validation_turnover ?? 0).toFixed(2) }}</b></p></article></div>
      <template v-if="activeTab === 'users'"><div ref="cumulativeChart" class="book-chart"></div><div ref="dailyChart" class="book-chart"></div></template>
      <div v-else ref="chart" class="book-chart"></div>
      <div v-if="activeTab === 'users'" class="two-col metric-columns"><article v-for="book in ['abook', 'bbook']" :key="book" class="book-card"><h3>{{ book }} 用户结构</h3><div v-for="style in analytics.user_structure?.[book]?.styles || []" :key="style.style" class="list-row"><span>{{ style.style }}</span><b>{{ style.accounts }} 人 / 客户 {{ style.validation_client_net_pnl.toFixed(2) }}</b></div><h4>品种客户盈亏热力图</h4><div v-for="row in analytics.user_structure?.[book]?.symbol_heatmap || []" :key="row.symbol" class="list-row"><span>{{ row.symbol }}</span><b>{{ row.market_pnl.toFixed(2) }} · {{ row.trade_count }}</b></div></article></div>
      <div v-else-if="activeTab === 'risk'" class="two-col metric-columns"><article v-for="book in ['abook', 'bbook']" :key="book" class="book-card"><h3>{{ book }} 风险敞口</h3><div v-for="row in analytics.risk_exposure?.[book]?.max_exposure_dates || []" :key="row.date" class="list-row"><span>{{ row.date }}</span><b>{{ row.turnover.toFixed(2) }}</b></div></article></div>
      <div v-else-if="activeTab === 'routing'" class="panel inset"><h3>公司利润对比</h3><div v-for="row in analytics.routing_quality?.company_profit_comparison || []" :key="row.date" class="list-row"><span>{{ row.date }}</span><b :class="row.incremental_change >= 0 ? 'positive' : 'negative'">{{ row.incremental_change.toFixed(2) }}</b></div></div>
    </template>
    <div v-else class="empty">切换到分析 Tab 以加载数据</div>
  </section>
</template>
