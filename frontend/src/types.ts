export type Tab = 'overview' | 'users' | 'risk-routing' | 'direction' | 'newcomer'

export interface RequestModel {
  selection: { start: string; end: string }
  validation: { start: string; end: string }
  platforms: string[]
  filters: { groups: string[]; logins: number[] }
  rules: Record<string, number | string[] | boolean>
  personal_candidate_list: boolean
  news_candidate_list: boolean
}

export interface AccountRow {
  platform: string
  login: number
  account_group: string
  book: 'abook' | 'bbook'
  selection_source: string
  selection_client_net_pnl: number
  validation_client_net_pnl: number
  validation_status: string
  selection: Record<string, number | null>
  validation: Record<string, number | null>
  monthly?: Array<Record<string, any>>
  stability: { score: number; tier: string }
  selection_flags: string[]
  bbook_reason_tags?: string[]
  confidence_tier?: string
  risk_balance_prev_month?: number | null
  risk_average_open_degree?: number | null
  risk_peak_leverage_ratio?: number | null
  risk_leverage_p95_ratio?: number | null
  risk_turnover_leverage_p95_ratio?: number | null
  risk_concurrent_leverage_p95_ratio?: number | null
  risk_exposure_status?: string | null
  martingale_status?: string
  martingale_risk_level?: string | null
  martingale_detection_status?: 'none' | 'suspected' | 'confirmed'
  martingale_blocked?: boolean
  martingale_hard_block?: boolean
  confirmed_windows?: number
  confirmed_extreme_windows?: number
  expanded_windows?: number
  martingale_layer_hits?: Record<string, boolean>
  july_new_user?: boolean
}

export interface BookAnalyticsPayload {
  user_structure?: {
    daily_book_series?: Array<Record<string, any>>
    [key: string]: any
  }
  pnl_structure?: Record<'abook' | 'bbook', Record<string, any>>
  risk_exposure?: Record<string, any>
  routing_quality?: Record<string, any>
  [key: string]: any
}

export interface DirectionAnalyticsPayload {
  pnl_basis?: string
  selection?: { start: string; end: string }
  validation?: { start: string; end: string }
  counts?: Record<string, number>
  book_counts?: Record<'abook' | 'bbook', Record<string, number>>
  accounts?: Array<Record<string, any>>
  sets?: Record<string, Record<'long' | 'short', Record<string, any>>>
  book_sets?: Record<string, Record<'abook' | 'bbook', Record<'long' | 'short', Record<string, any>>>>
  comparison?: Record<string, number>
  rules?: Record<string, any>
}

export interface NewcomerSelectionMetrics {
  trade_count: number
  active_trade_days: number
  winning_trades: number
  losing_trades: number
  long_trades: number
  short_trades: number
  long_trades_ratio: number
  win_rate: number
  profit_factor: number | null
  payoff_ratio: number
  client_net_pnl: number
  top_positive_day_concentration: number
  gross_wins: number
  gross_losses: number
}

export type NewcomerPool = 'admitted' | 'observe' | 'rejected' | 'left_track' | 'blocked' | 'inactive'

export interface NewcomerAccount {
  platform: string
  login: number
  account_group: string
  martingale_hard_block: boolean
  martingale_risk_level?: string | null
  pool: NewcomerPool
  admitted: boolean
  admitted_on: string | null
  as_of: string | null
  active_trade_days: number
  window_trade_count: number
  selection: NewcomerSelectionMetrics
  selection_flags: string[]
  post_asof_pnl: number
  validation_period_pnl: number
  stats_end: string
  min_trades_used: number
  trades_to_mature: number
  days_to_cap: number
}

export interface NewcomerCounts {
  observe: number
  admitted: number
  rejected: number
  left_track: number
  martingale_blocked: number
  skipped_abook: number
  skipped_inactive: number
  active_candidates: number
  unqualified_total: number
}

export interface NewcomerTruncation {
  observe_cap: number
  observe_truncated: boolean
  rejected_cap: number
  rejected_truncated: boolean
}

export interface NewcomerKpi {
  admitted_accounts: number
  post_asof_net_pnl: number
  admitted_positive: number
  admitted_negative: number
  observe_accounts: number
  skipped_inactive: number
  average_post_asof_pnl: number
  median_post_asof_pnl: number
}

export interface NewcomerTopRow {
  platform: string
  login: number
  account_group: string
  as_of: string | null
  active_trade_days: number
  trade_count: number
  pnl: number
}

export interface NewcomerTopAccounts {
  winners: NewcomerTopRow[]
  losers: NewcomerTopRow[]
}

export interface NewcomerAsOfBucket {
  date: string
  accounts: number
}

export interface NewcomerAnalyticsPayload {
  pnl_basis?: string
  selection?: { start: string; end: string }
  validation?: { start: string; end: string }
  counts?: Partial<NewcomerCounts>
  truncation?: NewcomerTruncation
  kpi?: Partial<NewcomerKpi>
  summary?: Record<string, any>
  pnl_distribution?: Record<string, Array<Record<string, any>>>
  cumulative_pnl?: Record<string, Array<Record<string, any>>>
  as_of_distribution?: NewcomerAsOfBucket[]
  top_accounts?: Record<string, Partial<NewcomerTopAccounts>>
  admitted?: NewcomerAccount[]
  observe?: NewcomerAccount[]
  rejected?: NewcomerAccount[]
  rules?: Record<string, any>
}

export interface NewcomerAccountSensitivity {
  platform?: string
  login?: number
  stats_end?: string
  points: NewcomerAccount[]
}

export interface WarehouseStatus {
  source: string
  status: string
  warehouse_path?: string
  generation?: string | null
  updated_at?: string | null
  data_start?: string | null
  data_end?: string | null
  platforms?: string[]
  snapshots?: Record<string, {
    status: string
    warehouse_generation?: string | null
    platforms?: string[]
    selection_start?: string | null
    selection_end?: string | null
    validation_start?: string | null
    validation_end?: string | null
  }>
}

export interface AccountDetailPayload {
  symbols: Array<{
    symbol: string
    trade_count: number
    volume: number
    profit: number
    win_rate: number
    avg_holding_seconds: number
  }>
  metrics?: Record<string, number>
  concentration?: Record<string, number>
  de_extreme?: Record<string, number>
  markout?: Record<string, {
    primary_horizon_ms?: number
    primary_bps?: number | null
    mean_5s_bps?: number | null
    sample_count?: number
    curve: Array<{
      offset_ms: number
      mean_bps: number | null
      sample_count?: number
    }>
  }>
  martingale?: Record<string, any>
  direction_summary?: DirectionSummary
}

export interface DirectionMetric {
  trade_count: number
  winning_trades?: number
  losing_trades?: number
  win_rate: number | null
  profit_factor: number | null
  payoff_ratio: number | null
  side_pnl: number
  sample_status: string
}

export interface DirectionSummaryPhase {
  long: DirectionMetric
  short: DirectionMetric
  long_trades_ratio: number | null
  short_trades_ratio: number | null
}

export interface DirectionSummary {
  basis: 'matched.profit'
  selection: DirectionSummaryPhase
  validation: DirectionSummaryPhase
}

export interface AnalysisPayload {
  analysis_token?: string
  selection?: { counts: Record<string, number>; groups: Record<string, unknown> }
  validation?: { groups: Record<string, any>; diagnostics: Record<string, any> }
  coverage?: Record<string, any>
  profit_impact?: Record<string, any>
  book_performance?: Record<string, any>
  misjudge?: Record<string, any>
  rules?: Record<string, any>
  funnel?: { stages: Array<{ name: string; count: number; drop_reasons: Record<string, number> }> }
  martingale?: Record<string, any>
  accounts?: AccountRow[]
  population_accounts?: AccountRow[]
  daily_book_series?: any[]
  avg_profit?: Record<string, any>
  [key: string]: any
}
