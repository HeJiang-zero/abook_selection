<script setup lang="ts">
import type { AnalysisPayload } from '../types'
defineProps<{ data: AnalysisPayload }>()
</script>

<template>
  <section class="kpi-grid">
    <article class="kpi"><span>有效账户</span><strong>{{ data.selection?.counts?.eligible_accounts ?? 0 }}</strong><small>测试/演示账户已排除</small></article>
    <article class="kpi accent"><span>Abook Core</span><strong>{{ data.selection?.counts?.abook_candidates ?? 0 }}</strong><small>可部署账户</small></article>
    <article class="kpi"><span>验证期公司增量（理论）</span><strong>{{ (data.profit_impact?.abook_candidate?.validation_company_increment_if_routed_abook ?? 0).toFixed(2) }}</strong><small>Abook 候选迁移后的公司变化</small></article>
    <article class="kpi danger"><span>Abook 误判成本（公司少赚）</span><strong>{{ (data.misjudge?.abook_loss_total ?? 0).toFixed(2) }}</strong><small>验证期客户亏损额对应的 Bbook 利润</small></article>
  </section>
</template>
