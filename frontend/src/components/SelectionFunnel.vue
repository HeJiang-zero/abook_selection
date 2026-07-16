<script setup lang="ts">
import type { AnalysisPayload } from '../types'
defineProps<{ data: AnalysisPayload }>()
</script>
<template>
  <section class="panel"><div class="panel-head"><div><span class="kicker">FUNNEL</span><h2>筛选漏斗</h2></div></div><div class="funnel"><div v-for="stage in data.funnel?.stages || []" :key="stage.name" class="funnel-row"><span>{{ stage.name }}</span><b>{{ stage.count }}</b><small>{{ Object.entries(stage.drop_reasons || {}).map(([key, value]) => `${key}: ${value}`).join(' · ') || '—' }}</small></div></div></section>
</template>
