<script setup lang="ts">
import { ref } from 'vue'
import type { RequestModel } from '../types'
import { fetchSweep } from '../api'
const props = defineProps<{ request: RequestModel }>()
const results = ref<any[]>([])
const loading = ref(false)
async function run() { loading.value = true; try { results.value = (await fetchSweep(props.request, { min_win_rate: [0.5, 0.55, 0.6], min_stability_score: [60, 70, 80] })).results } finally { loading.value = false } }
</script>
<template><section class="panel"><div class="panel-head"><div><span class="kicker">SWEEP</span><h2>参数寻优</h2></div><button class="primary compact" :disabled="loading" @click="run">{{ loading ? '扫描中…' : '扫描默认网格' }}</button></div><p class="hint warning">7 月 1–13 日为部分月份；结果是样本内择优，需要滚动验证。</p><div class="table-scroll"><table><thead><tr><th>Abook Core</th><th>继续盈利率</th><th>验证增量</th><th>误判成本</th><th>Lift</th></tr></thead><tbody><tr v-for="row in results" :key="JSON.stringify(row.rules)"><td>{{ row.abook_core }}</td><td>{{ (row.continue_profit_rate * 100).toFixed(1) }}%</td><td>{{ row.validation_increment.toFixed(2) }}</td><td>{{ row.misjudge_cost.toFixed(2) }}</td><td>{{ row.lift.toFixed(2) }}</td></tr></tbody></table></div></section></template>
