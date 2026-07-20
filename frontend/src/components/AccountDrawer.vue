<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { AccountDetailPayload, AccountRow } from '../types'
const props = defineProps<{ account: AccountRow | null; detail: AccountDetailPayload | null; loading: boolean; error: string }>()
const emit = defineEmits<{ (event: 'close'): void }>()
const entryMarkoutChart = ref<HTMLDivElement | null>(null)
const exitMarkoutChart = ref<HTMLDivElement | null>(null)
let entryChart: echarts.ECharts | null = null
let exitChart: echarts.ECharts | null = null

function number(value: unknown): number {
  const parsed = Number(value ?? 0)
  return Number.isFinite(parsed) ? parsed : 0
}

function format(value: unknown): string { return number(value).toFixed(2) }
function percent(value: unknown): string { return `${(number(value) * 100).toFixed(1)}%` }
function text(value: unknown): string { return value === null || value === undefined || value === '' ? '—' : String(value) }

const concentrationItems = [
  ['max_profit_day_contribution', '最大盈利日贡献率'],
  ['top3_profit_day_contribution', '前三盈利日贡献率'],
  ['max_profit_order_contribution', '最大盈利订单贡献率'],
  ['top3_profit_order_contribution', '前三盈利订单贡献率'],
  ['best_symbol_contribution', '最佳品种贡献率'],
  ['best_time_bucket_contribution', '最佳时段贡献率'],
  ['best_event_contribution', '最佳事件贡献率'],
]
const deExtremeItems = [
  ['without_max_profit_day', '去掉最大盈利日'],
  ['without_top3_profit_days', '去掉前三盈利日'],
  ['without_max_profit_order', '去掉最大盈利订单'],
  ['without_top3_profit_orders', '去掉前三盈利订单'],
  ['without_top5_profit_orders', '去掉前五盈利订单'],
  ['without_best_symbol', '去掉最佳品种'],
  ['without_best_time_bucket', '去掉最佳时段'],
  ['without_best_event', '去掉最佳新闻事件'],
  ['without_max_position_order', '去掉最大仓位订单'],
]

function renderMarkoutChart(target: HTMLDivElement | null, kind: 'entry' | 'exit', chart: echarts.ECharts | null): echarts.ECharts | null {
  const curve = props.detail?.markout?.[kind]?.curve || []
  if (!target || !curve.length) {
    chart?.dispose()
    return null
  }
  const instance = chart || echarts.init(target)
  instance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['正向平均 bps', '负向平均 bps'] },
    grid: { left: 42, right: 16, top: 30, bottom: 28 },
    xAxis: { type: 'category', data: curve.map((point: any) => `${point.offset_ms}ms`) },
    yAxis: { type: 'value', name: 'bps' },
    series: [
      { name: '正向平均 bps', type: 'line', connectNulls: true, data: curve.map((point: any) => point.positive_bps) },
      { name: '负向平均 bps', type: 'line', connectNulls: true, data: curve.map((point: any) => point.negative_bps) },
    ],
  })
  return instance
}

async function renderMarkoutCharts() {
  await nextTick()
  entryChart = renderMarkoutChart(entryMarkoutChart.value, 'entry', entryChart)
  exitChart = renderMarkoutChart(exitMarkoutChart.value, 'exit', exitChart)
}

watch(() => props.detail, renderMarkoutCharts, { deep: true })
onBeforeUnmount(() => { entryChart?.dispose(); exitChart?.dispose() })
</script>
<template>
  <div v-if="account" class="drawer-backdrop">
    <aside class="drawer" @click.stop>
      <button type="button" class="close" @click="emit('close')">×</button>
      <span class="kicker">ACCOUNT DETAIL</span>
      <h2>{{ account.platform }} / {{ account.login }}</h2>
      <p>{{ account.account_group }} · {{ account.book === 'abook' ? 'Abook' : 'Bbook' }} · {{ account.selection_source }}<span v-if="account.july_new_user"> · 7月新用户</span><span v-if="account.r4_pass"> · R4</span></p>

      <div class="detail-grid">
        <span>筛选期客户净 P&amp;L</span><b>{{ format(account.selection?.client_net_pnl) }}</b>
        <span>验证期客户净 P&amp;L</span><b>{{ format(account.validation?.client_net_pnl) }}</b>
        <span>筛选期胜率 / 交易</span><b>{{ percent(account.selection?.win_rate) }} / {{ number(account.selection?.trade_count) }}</b>
        <span>验证期胜率 / 交易</span><b>{{ percent(account.validation?.win_rate) }} / {{ number(account.validation?.trade_count) }}</b>
        <span>筛选期 PF / 盈亏比</span><b>{{ text(account.selection?.profit_factor) }} / {{ format(account.selection?.payoff_ratio) }}</b>
        <span>验证期 PF / 盈亏比</span><b>{{ text(account.validation?.profit_factor) }} / {{ format(account.validation?.payoff_ratio) }}</b>
        <span>稳定性 / 置信度</span><b>{{ number(account.stability?.score).toFixed(0) }} / {{ text(account.confidence_tier) }}</b>
        <span>马丁风险等级</span><b>{{ text(account.martingale_risk_level) }}</b>
        <span>马丁检测状态</span><b>{{ account.martingale_detection_status === 'confirmed' ? '确认马丁' : account.martingale_detection_status === 'suspected' ? '疑似马丁' : '未命中' }}</b>
        <span>确认窗口 / Extreme 窗口</span><b>{{ account.confirmed_windows ?? 0 }} / {{ account.confirmed_extreme_windows ?? 0 }}</b>
        <span>扩展候选窗口</span><b>{{ account.expanded_windows ?? 0 }}</b>
        <span>杠杆率 P95</span><b>{{ text(account.risk_leverage_p95_ratio) }}</b>
        <template v-if="account.risk_turnover_leverage_p95_ratio !== null && account.risk_turnover_leverage_p95_ratio !== undefined">
          <span>成交额杠杆 P95</span><b>{{ text(account.risk_turnover_leverage_p95_ratio) }}</b>
        </template>
        <template v-if="account.risk_concurrent_leverage_p95_ratio !== null && account.risk_concurrent_leverage_p95_ratio !== undefined">
          <span>并发敞口杠杆 P95</span><b>{{ text(account.risk_concurrent_leverage_p95_ratio) }}</b>
        </template>
      </div>

      <h3>马丁五层命中</h3>
      <div class="layer-grid"><span v-for="layer in ['layer1', 'layer2', 'layer3', 'layer4', 'layer5']" :key="layer" :class="account.martingale_layer_hits?.[layer] ? 'hit' : ''">{{ layer }} {{ account.martingale_layer_hits?.[layer] ? '命中' : '未命中' }}</span></div>

      <div v-if="loading" class="empty">正在加载用户指标…</div>
      <div v-else-if="error" class="alert error">用户指标加载失败：{{ error }}</div>
      <template v-else-if="detail">
        <h3>品种汇总</h3>
        <div v-if="!detail.symbols.length" class="empty">暂无品种汇总</div>
        <div v-else class="table-scroll"><table><thead><tr><th>品种</th><th>交易数</th><th>交易量</th><th>P&amp;L</th><th>胜率</th></tr></thead><tbody><tr v-for="row in detail.symbols" :key="row.symbol"><td>{{ row.symbol }}</td><td>{{ row.trade_count }}</td><td>{{ format(row.volume) }}</td><td :class="row.profit >= 0 ? 'positive' : 'negative'">{{ format(row.profit) }}</td><td>{{ percent(row.win_rate) }}</td></tr></tbody></table></div>

        <template v-if="Object.keys(detail.metrics || {}).length">
          <h3>利润与集中度</h3>
          <div class="detail-grid">
            <template v-for="item in [['raw_net_profit', '原始净利润'], ['positive_profit_total', '所有盈利订单利润'], ['negative_profit_total', '所有亏损订单利润']]" :key="item[0]">
              <span>{{ item[1] }}</span><b>{{ format(detail.metrics?.[item[0]]) }}</b>
            </template>
            <template v-for="item in concentrationItems" :key="item[0]">
              <template v-if="detail.concentration?.[item[0]] !== undefined">
                <span>{{ item[1] }}</span><b>{{ percent(detail.concentration?.[item[0]]) }}</b>
              </template>
            </template>
          </div>
          <p class="hint">贡献率低于20%较分散；20–40%有一定集中；40–60%高度依赖少数场景；高于60%非常集中。</p>
        </template>

        <template v-if="Object.keys(detail.de_extreme || {}).length">
          <h3>去极值测试（保留原始结果）</h3>
          <div class="table-scroll"><table><thead><tr><th>测试</th><th>净利润</th></tr></thead><tbody><tr v-for="item in deExtremeItems" v-if="detail.de_extreme?.[item[0]] !== undefined" :key="item[0]"><td>{{ item[1] }}</td><td :class="number(detail.de_extreme?.[item[0]]) >= 0 ? 'positive' : 'negative'">{{ format(detail.de_extreme?.[item[0]]) }}</td></tr></tbody></table></div>
        </template>

        <template v-if="detail.markout && Object.keys(detail.markout).length">
          <h3>±5s Markout</h3>
          <div v-if="detail.markout.entry" class="markout-block"><div class="list-row"><span>Entry 5s Markout</span><b>{{ text(detail.markout.entry.positive_5s_bps) }} / {{ text(detail.markout.entry.negative_5s_bps) }} bps</b></div><div ref="entryMarkoutChart" class="markout-chart"></div></div>
          <div v-if="detail.markout.exit" class="markout-block"><div class="list-row"><span>Exit 5s Markout</span><b>{{ text(detail.markout.exit.positive_5s_bps) }} / {{ text(detail.markout.exit.negative_5s_bps) }} bps</b></div><div ref="exitMarkoutChart" class="markout-chart"></div></div>
        </template>
      </template>
      <div v-else class="empty">暂无用户指标</div>
    </aside>
  </div>
</template>
