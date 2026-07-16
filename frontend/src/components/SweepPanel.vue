<script setup lang="ts">
import { ref } from 'vue'
import type { RequestModel } from '../types'
import { fetchSweep } from '../api'

const props = defineProps<{ request: RequestModel }>()
const emit = defineEmits<{ (event: 'applyRules', rules: Record<string, number | string[]>): void }>()
const minWinRateText = ref('0.5,0.55,0.6')
const minStabilityText = ref('60,70,80')
const objective = ref('validation_increment')
const maxMisjudgeCost = ref(500)
const results = ref<any[]>([])
const combinations = ref(0)
const loading = ref(false)
const error = ref('')

function parseNumbers(text: string) {
  return text.split(',').map(value => Number(value.trim())).filter(value => Number.isFinite(value))
}

async function run() {
  error.value = ''
  loading.value = true
  try {
    const grid = {
      min_win_rate: parseNumbers(minWinRateText.value),
      min_stability_score: parseNumbers(minStabilityText.value),
    }
    if (!grid.min_win_rate.length || !grid.min_stability_score.length) throw new Error('请输入有效的逗号分隔数字')
    const response = await fetchSweep(props.request, grid, objective.value, maxMisjudgeCost.value)
    results.value = response.results || []
    combinations.value = response.combinations || 0
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head"><div><span class="kicker">SWEEP</span><h2>参数寻优</h2></div><button class="primary compact" :disabled="loading" @click="run">{{ loading ? '扫描中…' : '开始扫描' }}</button></div>
    <p class="hint warning">7 月 1–13 日为部分月份；结果是样本内择优，需要滚动验证。最多 500 组组合。</p>
    <div class="sweep-controls">
      <label>最低胜率网格<input v-model="minWinRateText" placeholder="0.5,0.55,0.6"></label>
      <label>最低稳定性网格<input v-model="minStabilityText" placeholder="60,70,80"></label>
      <label>排序目标<select v-model="objective"><option value="validation_increment">最大验证增量</option><option value="increment_with_cost_cap">增量且误判成本不超过上限</option><option value="validation_precision">最大继续盈利率</option></select></label>
      <label v-if="objective === 'increment_with_cost_cap'">误判成本上限<input v-model.number="maxMisjudgeCost" type="number" min="0"></label>
    </div>
    <div v-if="error" class="alert error">{{ error }}</div>
    <p v-if="combinations" class="hint">已评估 {{ combinations }} 组。点击任意行将规则回填到主筛选并重算。</p>
    <div class="table-scroll"><table><thead><tr><th>Abook Core</th><th>继续盈利率</th><th>验证增量</th><th>误判成本</th><th>净收益</th><th>Lift</th><th>样本</th></tr></thead><tbody><tr v-for="row in results" :key="JSON.stringify(row.rules)" class="clickable" @click="emit('applyRules', row.rules)"><td>{{ row.abook_core }}</td><td>{{ (row.continue_profit_rate * 100).toFixed(1) }}%</td><td>{{ row.validation_increment.toFixed(2) }}</td><td>{{ row.misjudge_cost.toFixed(2) }}</td><td>{{ row.net_gain.toFixed(2) }}</td><td>{{ row.lift.toFixed(2) }}</td><td :class="row.sample_warning ? 'warning' : ''">{{ row.validation_active_accounts }}{{ row.sample_warning ? ' ⚠' : '' }}</td></tr></tbody></table><div v-if="!results.length" class="empty">定义网格后开始扫描</div></div>
  </section>
</template>
