<script setup lang="ts">
import type { AnalysisPayload, RequestModel } from '../types'
defineProps<{ request: RequestModel; data: AnalysisPayload; loading: boolean; rulesDirty: boolean }>()
const emit = defineEmits<{ (event: 'apply'): void; (event: 'reset'): void }>()
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
    <label class="wide">最大峰值杠杆率<input v-model.number="request.rules.max_peak_leverage_ratio" type="number" min="0"></label>
    <label class="check"><input v-model="request.personal_candidate_list" type="checkbox"> 个人候选名单（加入 Abook）</label>
    <div class="platforms"><label v-for="platform in ['mt5', 'hh_mt5']" :key="platform" class="check"><input v-model="request.platforms" :value="platform" type="checkbox"> {{ platform }}</label></div>
    <button class="primary" :disabled="loading || !request.platforms.length" @click="emit('apply')">{{ loading ? '正在计算…' : '应用筛选与验证' }}</button>
    <div v-if="data.martingale" class="status-box" :class="data.martingale.status === 'ready' ? 'ok' : 'warn'"><strong>马丁过滤：{{ data.martingale.status }}</strong><span>排除 {{ data.martingale.blocked_users ?? 0 }} 人</span></div>
    <p v-if="rulesDirty" class="hint warning">参数已修改，点击应用后重新计算。</p>
  </aside>
</template>
