<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{ analytics: any | null; loading: boolean }>()
const chart = ref<HTMLElement | null>(null)
let instance: echarts.ECharts | null = null

async function renderChart() {
  await nextTick()
  if (!chart.value || !props.analytics) return
  instance?.dispose()
  instance = echarts.init(chart.value)
  const rows = props.analytics.pnl_structure?.abook?.daily_series || []
  instance.setOption({
    backgroundColor: 'transparent', tooltip: { trigger: 'axis' },
    grid: { left: 38, right: 18, top: 18, bottom: 28 },
    xAxis: { type: 'category', data: rows.map((row: any) => row.date), axisLabel: { color: '#8497ad' } },
    yAxis: { type: 'value', axisLabel: { color: '#8497ad' }, splitLine: { lineStyle: { color: '#20364e' } } },
    series: [{ type: 'line', smooth: true, data: rows.map((row: any) => row.cumulative_pnl), lineStyle: { color: '#54d6a6' }, areaStyle: { color: 'rgba(84,214,166,.12)' } }],
  })
}
watch(() => props.analytics, renderChart)
onBeforeUnmount(() => instance?.dispose())
</script>
<template><section class="panel"><div class="panel-head"><div><span class="kicker">BOOK ANALYTICS</span><h2>Abook / Bbook 量化分析</h2></div><span class="hint">切换 Tab 时懒加载</span></div><div v-if="loading" class="empty">加载 Book 分析…</div><template v-else-if="analytics"><div class="book-grid"><article v-for="book in ['abook', 'bbook']" :key="book" class="book-card"><h3>{{ book === 'abook' ? 'Abook' : 'Bbook' }}</h3><p>筛选期 P&amp;L <b>{{ (analytics.pnl_structure?.[book]?.selection?.total_client_net_pnl ?? 0).toFixed(2) }}</b></p><p>验证期 P&amp;L <b>{{ (analytics.pnl_structure?.[book]?.validation?.total_client_net_pnl ?? 0).toFixed(2) }}</b></p><p>验证交易账户 <b>{{ analytics.pnl_structure?.[book]?.validation?.active_accounts ?? 0 }}</b></p><p>Turnover <b>{{ (analytics.risk_exposure?.[book]?.validation_turnover ?? 0).toFixed(2) }}</b></p></article></div><div ref="chart" class="book-chart"></div></template><div v-else class="empty">切换到分析 Tab 以加载数据</div></section></template>
