/** Shared formatting helpers used across all analytics panels. */

export function number(value: unknown): number {
  const parsed = Number(value ?? 0)
  return Number.isFinite(parsed) ? parsed : 0
}

export function money(value: unknown): string {
  return number(value).toFixed(2)
}

export function pct(value: unknown): string {
  return `${(number(value) * 100).toFixed(1)}%`
}

/** Share of profitable accounts — the metric historically (mis)named "precision". */
export function profitableRate(profitable: unknown, total: unknown): string {
  return pct(number(profitable) / Math.max(1, number(total)))
}

export function pf(value: unknown): string {
  return value === null || value === undefined ? '∞' : money(value)
}

export function pnlClass(value: unknown): string {
  return number(value) >= 0 ? 'positive' : 'negative'
}
