<script setup lang="ts">
import type { AnalysisPayload } from '../types'
defineProps<{ data: AnalysisPayload }>()
</script>
<template>
  <section class="two-col"><article class="panel"><div class="panel-head"><h2>误判分析</h2><span class="negative">送掉 {{ (data.misjudge?.abook_loss_total ?? 0).toFixed(2) }}</span></div><div v-if="!data.misjudge?.abook_losses?.length" class="empty">暂无 Abook 亏损用户</div><div v-for="row in data.misjudge?.abook_losses || []" :key="row.login" class="list-row"><span>{{ row.platform }} / {{ row.login }}</span><b class="negative">{{ row.loss_amount.toFixed(2) }}</b></div></article><article class="panel"><div class="panel-head"><h2>Bbook 漏网</h2><span class="positive">{{ data.misjudge?.bbook_profitable_total?.toFixed(2) ?? '0.00' }}</span></div><div v-for="row in data.misjudge?.bbook_profitable || []" :key="row.login" class="list-row"><span>{{ row.platform }} / {{ row.login }}</span><b class="positive">{{ row.profit_amount.toFixed(2) }}</b></div><div v-if="!data.misjudge?.bbook_profitable?.length" class="empty">暂无漏网用户</div></article></section>
</template>
