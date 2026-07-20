import type { AccountDetailPayload, AccountRow, AnalysisPayload, BookAnalyticsPayload, RequestModel, SnapshotRefreshResponse } from './types'

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export function fetchAnalysis(request: RequestModel) {
  return postJson<AnalysisPayload>('/api/abook/analysis', request)
}

export function refreshSnapshots(request: RequestModel) {
  return postJson<SnapshotRefreshResponse>('/api/abook/refresh-snapshots', {
    selection: request.selection,
    platforms: request.platforms,
  })
}

export function fetchBookAnalytics(request: RequestModel, accounts: Array<{ platform: string; login: number }>) {
  return postJson<BookAnalyticsPayload>('/api/abook/book-analytics', { analysis: request, abook_accounts: accounts })
}

export async function fetchAccountDetail(account: AccountRow, request: RequestModel): Promise<AccountDetailPayload> {
  const start = [request.selection.start, request.validation.start].sort()[0]
  const end = [request.selection.end, request.validation.end].sort()[1]
  const params = new URLSearchParams({
    start,
    end,
    selection_start: request.selection.start,
    selection_end: request.selection.end,
  })
  const response = await fetch(`/api/abook/accounts/${encodeURIComponent(account.platform)}/${account.login}?${params.toString()}`)
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`)
  return response.json() as Promise<AccountDetailPayload>
}

export function exportAbook(request: RequestModel) {
  return fetch('/api/abook/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })
}
