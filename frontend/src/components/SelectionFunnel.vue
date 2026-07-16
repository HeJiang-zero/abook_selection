<script setup lang="ts">
import type { AnalysisPayload } from '../types'
defineProps<{ data: AnalysisPayload }>()
const labels: Record<string, string> = { eligible: '全量账户', sample_qualified: '样本达标', positive_direction: '盈利方向成立', stability_core: '稳定性通过', leverage_passed: '杠杆 P95 通过', non_martingale: '非马丁', abook: 'Abook' }
</script>
<template>
  <section class="panel"><div class="panel-head"><div><span class="kicker">FUNNEL</span><h2>Abook 资格漏斗</h2></div></div><div class="funnel"><div v-for="stage in data.funnel?.stages || []" :key="stage.name" class="funnel-row"><span>{{ labels[stage.name] || stage.name }}</span><b>{{ stage.count }}</b><small>{{ Object.entries(stage.drop_reasons || {}).map(([key, value]) => `${key}: ${value}`).join(' · ') || '—' }}</small></div></div></section>
</template>
