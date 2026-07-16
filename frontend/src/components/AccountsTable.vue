<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AccountRow } from '../types'
const props = defineProps<{ accounts: AccountRow[] }>()
const emit = defineEmits<{ (event: 'open', account: AccountRow): void }>()
const search = ref('')
const filtered = computed(() => props.accounts.filter(account => `${account.platform} ${account.login} ${account.account_group}`.toLowerCase().includes(search.value.toLowerCase())))
</script>
<template><section class="panel"><div class="panel-head"><div><span class="kicker">ACCOUNTS</span><h2>账户表现</h2></div><input v-model="search" class="search" placeholder="搜索平台、Login、账户组"></div><div class="table-scroll"><table><thead><tr><th>账户</th><th>分流</th><th>马丁</th><th>筛选期 P&amp;L</th><th>验证期 P&amp;L</th><th>稳定性</th></tr></thead><tbody><tr v-for="account in filtered" :key="`${account.platform}-${account.login}`" @click="emit('open', account)"><td>{{ account.platform }} / {{ account.login }}<small>{{ account.account_group }}</small></td><td><span class="tag">{{ account.cohort }}</span></td><td><span v-if="account.martingale_risk_level" class="tag danger">{{ account.martingale_risk_level }}</span><span v-else>—</span></td><td :class="account.selection_client_net_pnl >= 0 ? 'positive' : 'negative'">{{ account.selection_client_net_pnl.toFixed(2) }}</td><td :class="account.validation_client_net_pnl >= 0 ? 'positive' : 'negative'">{{ account.validation_client_net_pnl.toFixed(2) }}</td><td>{{ account.stability?.score ?? 0 }} · {{ account.stability?.tier ?? '—' }}</td></tr></tbody></table><div v-if="!filtered.length" class="empty">暂无账户</div></div></section></template>
