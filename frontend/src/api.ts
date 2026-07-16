import type { AnalysisPayload, RequestModel } from './types'

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

export function fetchSweep(request: RequestModel, grid: Record<string, unknown[]>) {
  return postJson<any>('/api/abook/sweep', { analysis: request, grid, objective: 'validation_increment' })
}

export function fetchBookAnalytics(request: RequestModel, accounts: Array<{ platform: string; login: number }>, hedge_cost_bps = 0) {
  return postJson<any>('/api/abook/book-analytics', { analysis: request, abook_accounts: accounts, hedge_cost_bps })
}

export function exportAbook(request: RequestModel) {
  return fetch('/api/abook/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })
}
