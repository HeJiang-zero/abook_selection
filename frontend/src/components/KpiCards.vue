<script setup lang="ts">
import type { AnalysisPayload } from '../types'
defineProps<{ data: AnalysisPayload }>()
</script>

<template>
  <section class="kpi-grid">
    <article class="kpi"><span>有效账户</span><strong>{{ data.selection?.counts?.eligible_accounts ?? 0 }}</strong><small>测试/演示账户已排除</small></article>
    <article class="kpi accent"><span>Abook</span><strong>{{ data.selection?.counts?.abook ?? 0 }}</strong><small>最终对冲账户</small></article>
    <article class="kpi"><span>Bbook</span><strong>{{ data.selection?.counts?.bbook ?? 0 }}</strong><small>马丁及其他不对冲账户</small></article>
    <article class="kpi danger"><span>Abook 误判成本（公司少赚）</span><strong>{{ (data.misjudge?.abook_loss_total ?? 0).toFixed(2) }}</strong><small>验证期客户亏损额对应的 Bbook 利润</small></article>
  </section>
</template>
