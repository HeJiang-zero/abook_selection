<script setup lang="ts">
import type { AnalysisPayload } from '../types'
defineProps<{ data: AnalysisPayload }>()
</script>

<template>
  <section class="kpi-grid">
    <article class="kpi"><span>有效账户</span><strong>{{ data.selection?.counts?.eligible_accounts ?? 0 }}</strong><small>测试/演示账户已排除</small></article>
    <article class="kpi accent"><span>Abook</span><strong>{{ data.selection?.counts?.abook ?? 0 }}</strong><small>最终对冲账户</small></article>
    <article class="kpi"><span>Bbook</span><strong>{{ data.selection?.counts?.bbook ?? 0 }}</strong><small>马丁及其他不对冲账户</small></article>
    <article class="kpi danger"><span>Abook 验证期净 P&amp;L</span><strong>{{ (data.profit_overview?.july_book_split?.abook?.user_net_pnl ?? 0).toFixed(2) }}</strong><small>客户 P&amp;L 口径</small></article>
  </section>
</template>
