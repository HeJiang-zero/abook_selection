<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AccountRow } from '../types'
import { money, number, pnlClass } from '../utils/format'

const props = defineProps<{ accounts: AccountRow[] }>()
const emit = defineEmits<{ (event: 'open', account: AccountRow): void }>()

type SortField = 'selection_client_net_pnl' | 'validation_client_net_pnl' | 'stability'

const search = ref('')
const debouncedSearch = ref('')
const sortBy = ref<SortField>('validation_client_net_pnl')
const sortDirection = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = ref(50)
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(search, (value) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    debouncedSearch.value = value
    page.value = 1
  }, 200)
})

const filtered = computed(() => {
  const query = debouncedSearch.value.toLowerCase()
  if (!query) return props.accounts
  return props.accounts.filter(account =>
    `${account.platform} ${account.login} ${account.account_group}`.toLowerCase().includes(query)
  )
})
function sortValue(account: AccountRow, field: SortField): number {
  if (field === 'stability') return number(account.stability?.score)
  return number(account[field])
}
const sorted = computed(() => [...filtered.value].sort((left, right) => {
  const delta = sortValue(left, sortBy.value) - sortValue(right, sortBy.value)
  if (delta === 0) return left.login - right.login
  return (sortDirection.value === 'asc' ? 1 : -1) * delta
}))
const pageCount = computed(() => Math.max(1, Math.ceil(sorted.value.length / pageSize.value)))
const paged = computed(() => sorted.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))

function toggleSort(field: SortField) {
  if (sortBy.value === field) sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  else { sortBy.value = field; sortDirection.value = 'desc' }
}
function sortMark(field: SortField): string {
  return sortBy.value === field ? (sortDirection.value === 'asc' ? '↑' : '↓') : '↕'
}
watch(pageCount, () => { if (page.value > pageCount.value) page.value = pageCount.value })
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div><span class="kicker">ACCOUNTS</span><h2>账户表现</h2></div>
      <input v-model="search" class="search" placeholder="搜索平台、Login、账户组" aria-label="搜索账户">
    </div>
    <div class="table-scroll">
      <table aria-label="账户表现表">
        <thead>
          <tr>
            <th>账户</th>
            <th>最终分流</th>
            <th>来源</th>
            <th>马丁</th>
            <th><button class="table-sort" @click="toggleSort('selection_client_net_pnl')">筛选期客户 P&amp;L {{ sortMark('selection_client_net_pnl') }}</button></th>
            <th><button class="table-sort" @click="toggleSort('validation_client_net_pnl')">验证期客户 P&amp;L {{ sortMark('validation_client_net_pnl') }}</button></th>
            <th><button class="table-sort" @click="toggleSort('stability')">稳定性 {{ sortMark('stability') }}</button></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="account in paged" :key="`${account.platform}-${account.login}`" @click="emit('open', account)">
            <td>
              {{ account.platform }} / {{ account.login }}
              <small>{{ account.account_group }}</small>
              <span v-if="account.july_new_user" class="tag">窗口新用户</span>
            </td>
            <td><span class="tag">{{ account.book === 'abook' ? 'Abook' : 'Bbook' }}</span></td>
            <td><small>{{ account.selection_source }}</small></td>
            <td>
              <span v-if="account.martingale_risk_level" class="tag danger">{{ account.martingale_risk_level }} · {{ account.martingale_detection_status === 'confirmed' ? '确认' : '疑似' }}</span>
              <span v-else>—</span>
            </td>
            <td :class="pnlClass(account.selection_client_net_pnl)">{{ money(account.selection_client_net_pnl) }}</td>
            <td :class="pnlClass(account.validation_client_net_pnl)">{{ money(account.validation_client_net_pnl) }}</td>
            <td>{{ number(account.stability?.score) }} · {{ account.stability?.tier ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!paged.length" class="empty">暂无账户</div>
    </div>
    <div class="pagination">
      <button class="ghost compact" :disabled="page <= 1" @click="page--">上一页</button>
      <span>第 {{ page }} / {{ pageCount }} 页 · {{ sorted.length }} 个账户</span>
      <button class="ghost compact" :disabled="page >= pageCount" @click="page++">下一页</button>
      <label style="margin-left:auto">每页
        <select v-model.number="pageSize" @change="page = 1">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
      </label>
    </div>
  </section>
</template>
