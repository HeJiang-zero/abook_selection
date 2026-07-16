<script setup lang="ts">
import type { AnalysisPayload } from '../types'
defineProps<{ data: AnalysisPayload }>()
</script>

<template>
  <section class="kpi-grid">
    <article class="kpi"><span>有效账户</span><strong>{{ data.selection?.counts?.eligible_accounts ?? 0 }}</strong><small>测试/演示账户已排除</small></article>
    <article class="kpi accent"><span>Abook Core</span><strong>{{ data.selection?.counts?.abook_candidates ?? 0 }}</strong><small>可部署账户</small></article>
    <article class="kpi"><span>验证理论增量</span><strong>{{ (data.profit_impact?.abook_candidate?.validation_incremental_change ?? 0).toFixed(2) }}</strong><small>样本外验证期</small></article>
    <article class="kpi danger"><span>Abook 误判成本</span><strong>{{ (data.misjudge?.abook_loss_total ?? 0).toFixed(2) }}</strong><small>验证期亏损用户合计</small></article>
  </section>
</template>
