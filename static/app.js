const { createApp, nextTick } = Vue;

const DEFAULT_REQUEST = () => ({
  selection: { start: '2026-05-01', end: '2026-06-30' },
  validation: { start: '2026-07-01', end: '2026-07-13' },
  rules: {
    min_trades: 20, min_active_days: 10, min_win_rate: 0.5, min_profit_factor: 1, min_payoff_ratio: 0.8, min_avg_daily_profit: 0,
    min_selection_monthly_consistency: 0,
    min_positive_month_rate: 0.5, max_top1_day_profit_contribution: 0.2, max_peak_leverage_ratio: 200,
    max_high_leverage_holding_seconds: 300,
    min_direction_day_rate_lower_bound: 0.55, min_stability_score: 70,
    high_confidence_trades: 100, high_confidence_days: 30,
  },
  personal_candidate_list: false,
  platforms: ['mt5', 'hh_mt5'],
  filters: { groups: [], logins: [] },
});

createApp({
  data() {
    return {
      loading: false,
      detailLoading: false,
      error: '',
      groupInput: '',
      loginInput: '',
      accountSearch: '',
      cohortFilter: '',
      confidenceFilter: '',
      sortKey: 'selection_client_net_pnl',
      page: 1,
      pageSize: 50,
      chart: null,
      validationChart: null,
      stabilityChart: null,
      selectedAccount: null,
      detail: { symbols: [], trades: [] },
      request: DEFAULT_REQUEST(),
      data: { coverage: null, selection: null, validation: { groups: {} }, transitions: {}, profit_impact: {}, personal_candidate_list: { enabled: false }, accounts: [], monthly_series: [] },
    };
  },
  computed: {
    selectionMonthlyProfit() {
      return (this.data.profit_overview && this.data.profit_overview.monthly || []).filter(item => item.phase === 'selection');
    },
    visibleAccounts() {
      return (this.data.accounts || []).filter(account => account.has_nonzero_pnl);
    },
    filteredAccounts() {
      const query = this.accountSearch.trim().toLowerCase();
      const rows = this.visibleAccounts.filter(account => {
        const text = `${account.platform} ${account.login} ${account.account_group || ''}`.toLowerCase();
        return (!query || text.includes(query))
          && (!this.cohortFilter || account.cohort === this.cohortFilter)
          && (!this.confidenceFilter || account.confidence_tier === this.confidenceFilter);
      });
      const numeric = (account) => Number(account[this.sortKey] ?? account.stability?.score ?? 0);
      return rows.sort((left, right) => numeric(right) - numeric(left));
    },
    pagedAccounts() {
      const start = (this.page - 1) * this.pageSize;
      return this.filteredAccounts.slice(start, start + this.pageSize);
    },
    pageCount() { return Math.max(1, Math.ceil(this.filteredAccounts.length / this.pageSize)); },
    selectionStability() { return this.data.selection?.stability_overview || {}; },
    rulesDirty() {
      if (!this.data.rules) return false;
      const keys = [
        'min_trades', 'min_active_days', 'min_win_rate', 'min_profit_factor', 'min_payoff_ratio',
        'min_avg_daily_profit', 'min_selection_monthly_consistency',
        'min_positive_month_rate',
        'max_top1_day_profit_contribution', 'max_peak_leverage_ratio', 'max_high_leverage_holding_seconds', 'min_direction_day_rate_lower_bound',
        'min_stability_score', 'high_confidence_trades', 'high_confidence_days',
      ];
      return keys.some(key => Number(this.request.rules[key]) !== Number(this.data.rules[key]))
        || Boolean(this.request.personal_candidate_list) !== Boolean(this.data.personal_candidate_list?.enabled);
    },
  },
  mounted() {
    this.loadAnalysis();
    window.addEventListener('resize', () => {
      if (this.chart) this.chart.resize();
      if (this.validationChart) this.validationChart.resize();
      if (this.stabilityChart) this.stabilityChart.resize();
    });
  },
  methods: {
    parseList(value) { return value.split(',').map(item => item.trim()).filter(Boolean); },
    parseLoginList(value) { return this.parseList(value).map(item => Number(item)).filter(item => Number.isInteger(item) && item > 0); },
    displayRule(key) { return this.rulesDirty ? this.request.rules[key] : this.data.rules?.[key]; },
    riskModeLabel(value) { return ({ local_login_exclusion: '本地 Login 排除高杠杆账户（含短持仓例外）', local_login_intersection: '本地 Login 交集过滤', service_post_filter: '服务层本地快照过滤' }[value]) || value || '未应用'; },
    resetFilters() { this.groupInput = ''; this.loginInput = ''; this.request = DEFAULT_REQUEST(); this.loadAnalysis(); },
    async loadAnalysis() {
      this.loading = true;
      this.error = '';
      this.request.filters.groups = this.parseList(this.groupInput);
      this.request.filters.logins = this.parseLoginList(this.loginInput);
      this.page = 1;
      try {
        const response = await fetch('/api/abook/analysis', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.request),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(this.formatApiError(body.detail));
        this.data = body;
      } catch (error) {
        this.error = error.message || '查询失败';
      } finally {
        this.loading = false;
        await nextTick();
        if (!this.error && this.data.selection) this.renderCharts();
      }
    },
    formatApiError(detail) {
      if (Array.isArray(detail)) {
        return detail.map(item => {
          if (typeof item === 'string') return item;
          const location = Array.isArray(item?.loc) ? item.loc.join('.') : '';
          return [location, item?.msg].filter(Boolean).join(': ');
        }).filter(Boolean).join('；') || '查询失败';
      }
      if (detail && typeof detail === 'object') return detail.msg || JSON.stringify(detail);
      return detail || '查询失败';
    },
    renderCharts() {
      this.renderPnlChart();
      this.renderValidationChart();
      this.renderStabilityChart();
    },
    renderPnlChart() {
      const node = document.getElementById('pnl-chart');
      if (!node || !window.echarts) return;
      if (!this.chart) this.chart = echarts.init(node);
      const records = this.data.monthly_series || [];
      const months = [...new Set(records.map(item => item.month))];
      const totalByMonth = months.map(month => records.filter(item => item.month === month).reduce((sum, item) => sum + (item.client_net_pnl || 0), 0));
      const mirrorByMonth = months.map(month => records.filter(item => item.month === month).reduce((sum, item) => sum + (item.theoretical_mirror_pnl || 0), 0));
      const phases = months.map(month => (records.find(item => item.month === month) || {}).phase === 'validation' ? '验证期' : '筛选期');
      this.chart.setOption({
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'cross' },
          formatter: params => params.map(item => `${item.marker}${item.seriesName}: ${this.money(item.value)}`).join('<br/>'),
        },
        legend: { data: ['用户净 P&L', '公司理论反向 P&L'], textStyle: { color: '#94a3b8' } },
        grid: { left: 18, right: 20, top: 42, bottom: 32, containLabel: true },
        xAxis: { type: 'category', data: months.map((month, index) => `${month} · ${phases[index]}`), axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#94a3b8' } },
        yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: value => this.money(value) }, splitLine: { lineStyle: { color: '#1e293b' } } },
        series: [
          { name: '用户净 P&L', type: 'bar', barMaxWidth: 28, data: totalByMonth, itemStyle: { color: '#38bdf8', borderRadius: [5, 5, 0, 0] } },
          { name: '公司理论反向 P&L', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7, data: mirrorByMonth, lineStyle: { width: 3, color: '#a78bfa' }, itemStyle: { color: '#a78bfa' } },
        ],
      }, true);
    },
    renderValidationChart() {
      const node = document.getElementById('validation-chart');
      if (!node || !window.echarts) return;
      if (!this.validationChart) this.validationChart = echarts.init(node);
      const cohorts = ['abook_candidate', 'bbook_candidate', 'observation'];
      const groups = this.data.validation.groups || {};
      this.validationChart.setOption({
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'cross' },
          formatter: params => params.map(item => `${item.marker}${item.seriesName}: ${this.percent(item.value)}`).join('<br/>'),
        },
        legend: { data: ['7月盈利率', '7月亏损率'], textStyle: { color: '#94a3b8' } },
        grid: { left: 12, right: 12, top: 42, bottom: 20, containLabel: true },
        xAxis: { type: 'category', data: cohorts.map(cohort => this.cohortLabel(cohort)), axisLabel: { color: '#94a3b8' } },
        yAxis: { type: 'value', max: 1, axisLabel: { color: '#94a3b8', formatter: value => `${(value * 100).toFixed(0)}%` }, splitLine: { lineStyle: { color: '#1e293b' } } },
        series: [
          { name: '有交易账户 7月盈利率', type: 'bar', data: cohorts.map(cohort => (groups[cohort] || {}).active_positive_account_rate || 0), itemStyle: { color: '#86efac' } },
          { name: '有交易账户 7月亏损率', type: 'bar', data: cohorts.map(cohort => (groups[cohort] || {}).active_negative_account_rate || 0), itemStyle: { color: '#fda4af' } },
        ],
      }, true);
    },
    renderStabilityChart() {
      const node = document.getElementById('stability-chart');
      if (!node || !window.echarts) return;
      if (!this.stabilityChart) this.stabilityChart = echarts.init(node);
      const overview = this.selectionStability;
      this.stabilityChart.setOption({
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'cross' },
          formatter: params => params.map(item => `${item.marker}${item.seriesName}: ${this.number(item.value)}`).join('<br/>'),
        },
        grid: { left: 12, right: 12, top: 28, bottom: 16, containLabel: true },
        xAxis: { type: 'category', data: ['Abook Core', 'Abook Watch', 'Bbook Core', 'Bbook Watch'], axisLabel: { color: '#94a3b8' } },
        yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } } },
        series: [{ name: '账户数', type: 'bar', barMaxWidth: 32, data: [overview.abook_core || 0, overview.abook_watch || 0, overview.bbook_core || 0, overview.bbook_watch || 0], itemStyle: { color: '#38bdf8', borderRadius: [5, 5, 0, 0] } }],
      }, true);
    },
    async openAccount(account) {
      this.selectedAccount = account;
      this.detailLoading = true;
      this.detail = { symbols: [], trades: [] };
      try {
        const start = this.request.selection.start;
        const end = this.request.validation.end;
        const response = await fetch(`/api/abook/accounts/${account.platform}/${account.login}?start=${start}&end=${end}`);
        const body = await response.json();
        if (!response.ok) throw new Error(this.formatApiError(body.detail) || '详情加载失败');
        this.detail = body;
      } catch (error) {
        this.error = error.message || '详情加载失败';
      } finally {
        this.detailLoading = false;
      }
    },
    cohortLabel(value) {
      return ({ abook_candidate: 'Abook Core', bbook_candidate: 'Bbook Core', observation: '观察组' }[value]) || value || '—';
    },
    statusLabel(value) {
      return ({ profitable: '盈利', loss: '亏损', neutral: '中性', inactive: '无交易', continued_profitable: '继续盈利', started_loss: '开始亏损', continued_loss: '继续亏损', turned_profit: '转为盈利' }[value]) || value || '—';
    },
    successTransition(transition, cohort) {
      return transition[cohort === 'abook_candidate' ? 'continued_profitable' : cohort === 'bbook_candidate' ? 'continued_loss' : 'profitable'] || 0;
    },
    reversalTransition(transition, cohort) {
      return transition[cohort === 'abook_candidate' ? 'started_loss' : cohort === 'bbook_candidate' ? 'turned_profit' : 'loss'] || 0;
    },
    tierLabel(value) { return ({ core: 'Core', watch: 'Watch', observation: '观察' }[value]) || value || '—'; },
    confidenceLabel(value) { return ({ high: '高', medium: '中', low: '低' }[value]) || value || '—'; },
    previousPage() { if (this.page > 1) this.page -= 1; },
    nextPage() { if (this.page < this.pageCount) this.page += 1; },
    pf(value) { return value === null || value === undefined ? '∞' : Number(value).toFixed(2); },
    number(value) { return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value || 0); },
    money(value) { return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0); },
    percent(value) { return `${((value || 0) * 100).toFixed(1)}%`; },
    tone(value) { return value > 0 ? 'positive' : value < 0 ? 'negative' : ''; },
  },
}).mount('#app');
