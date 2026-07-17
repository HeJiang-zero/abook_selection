import type { AnalysisPayload, BookAnalyticsPayload, RequestModel, SnapshotRefreshResponse } from './types'

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

export function exportAbook(request: RequestModel) {
  return fetch('/api/abook/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })
}
