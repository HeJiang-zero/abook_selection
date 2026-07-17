<script setup lang="ts">
import type { AnalysisPayload, RequestModel } from '../types'
defineProps<{
  request: RequestModel
  data: AnalysisPayload
  loading: boolean
  rulesDirty: boolean
  refreshing: boolean
  refreshMessage: string
}>()
const emit = defineEmits<{ (event: 'apply'): void; (event: 'reset'): void; (event: 'refresh'): void }>()
</script>

<template>
  <aside class="sidebar panel">
    <div class="panel-head"><div><span class="kicker">FILTERS</span><h2>分析窗口</h2></div><button class="ghost" @click="emit('reset')">重置</button></div>
    <div class="date-grid">
      <label>筛选开始<input v-model="request.selection.start" type="date"></label>
      <label>筛选结束<input v-model="request.selection.end" type="date"></label>
      <label>验证开始<input v-model="request.validation.start" type="date"></label>
      <label>验证结束<input v-model="request.validation.end" type="date"></label>
    </div>
    <label class="wide">最低交易笔数<input v-model.number="request.rules.min_trades" type="number" min="0"></label>
    <label class="wide">最低稳定性评分<input v-model.number="request.rules.min_stability_score" type="number" min="0" max="100"></label>
    <label class="wide">avg_profit 最低值（活跃日均盈利）<input v-model.number="request.rules.min_avg_profit" type="number" step="0.01"></label>
    <label class="wide">最大杠杆率 P95<input v-model.number="request.rules.max_leverage_p95_ratio" type="number" min="0"></label>
    <label class="wide">单日最大盈利占当月利润<input v-model.number="request.rules.max_daily_profit_month_contribution" type="number" min="0" max="1" step="0.01"></label>
    <div class="filter-group"><strong>核心规则</strong><label>最低胜率<input v-model.number="request.rules.min_win_rate" type="number" min="0" max="1" step="0.01"></label><label>最低 Profit Factor<input v-model.number="request.rules.min_profit_factor" type="number" min="0" step="0.01"></label><label>最低平均日利润<input v-model.number="request.rules.min_avg_daily_profit" type="number" step="0.01"></label></div>
    <div class="filter-group"><strong>马丁路由到 Bbook</strong><label v-for="level in ['extreme', 'high', 'medium', 'low']" :key="level" class="check"><input v-model="request.rules.excluded_martingale_levels" type="checkbox" :value="level"> {{ level }}</label></div>
    <label class="check"><input v-model="request.personal_candidate_list" type="checkbox"> 个人候选名单（加入 Abook）</label>
    <div class="platforms"><label v-for="platform in ['mt5', 'hh_mt5']" :key="platform" class="check"><input v-model="request.platforms" :value="platform" type="checkbox"> {{ platform }}</label></div>
    <div class="action-row">
      <button class="primary" :disabled="loading || refreshing || !request.platforms.length" @click="emit('apply')">{{ loading ? '正在计算…' : '应用筛选与验证' }}</button>
      <button class="ghost" :disabled="loading || refreshing || !request.platforms.length" @click="emit('refresh')">{{ refreshing ? '正在刷新…' : '刷新全部数据' }}</button>
    </div>
    <div v-if="data.martingale" class="status-box" :class="data.martingale.status === 'ready' ? 'ok' : 'warn'"><strong>{{ data.martingale.message || `马丁过滤：${data.martingale.status}` }}</strong><span>排除 {{ data.martingale.blocked_users ?? 0 }} 人</span></div>
    <div v-if="data.avg_profit" class="status-box" :class="data.avg_profit.status === 'ready' ? 'ok' : 'warn'"><strong>avg_profit 本地快照：{{ data.avg_profit.status }}</strong><span>{{ data.avg_profit.records ?? 0 }} 条用户记录 · CUSTOM 活跃日均值<span v-if="data.avg_profit.source_min"> · {{ data.avg_profit.source_min }}～{{ data.avg_profit.source_max }}</span></span></div>
    <p v-if="refreshMessage" class="hint" :class="{ warning: refreshMessage.includes('失败') }">{{ refreshMessage }}</p>
    <p v-if="rulesDirty" class="hint warning">参数已修改，点击应用后重新计算。</p>
  </aside>
</template>
