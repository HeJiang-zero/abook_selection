<script setup lang="ts">
import type { AnalysisPayload } from '../types'
import { computed } from 'vue'
const props = defineProps<{ data: AnalysisPayload }>()
const visibleLeakage = computed(() => (props.data.misjudge?.bbook_profitable || []).filter((row: any) => row.profit_amount > 100))
</script>
<template>
  <section class="two-col"><article class="panel"><div class="panel-head"><h2>Abook 误判</h2><span class="negative">公司少赚 {{ (data.misjudge?.abook_loss_total ?? 0).toFixed(2) }}</span></div><div v-if="!data.misjudge?.abook_losses?.length" class="empty">暂无 Abook 亏损用户</div><div v-for="row in data.misjudge?.abook_losses || []" :key="row.login" class="list-row"><span>{{ row.platform }} / {{ row.login }}<small>客户净 P&amp;L {{ row.validation_client_net_pnl.toFixed(2) }} · Abook 路由影响 {{ row.company_increment_if_routed.toFixed(2) }}</small></span><b class="negative">{{ row.company_increment_if_routed.toFixed(2) }}</b></div></article><article class="panel"><div class="panel-head"><h2>Bbook 漏网</h2><span class="negative">公司损失 {{ (data.misjudge?.bbook_company_loss_total ?? 0).toFixed(2) }}</span></div><details open><summary>显示公司损失大于 100 的 {{ visibleLeakage.length }} 人（总额按全部漏网账户计算）</summary><div v-for="row in visibleLeakage" :key="row.login" class="list-row"><span>{{ row.platform }} / {{ row.login }}<small>客户盈利 {{ row.validation_client_net_pnl.toFixed(2) }} · Bbook 公司影响 {{ row.company_loss_if_left_bbook.toFixed(2) }}</small></span><b class="negative">{{ row.company_loss_if_left_bbook.toFixed(2) }}</b></div><div v-if="!visibleLeakage.length" class="empty">暂无金额大于 100 的漏网用户</div></details></article></section>
</template>
