import { onBeforeUnmount, type Ref } from 'vue'
import * as echarts from 'echarts'

/**
 * Reuse an existing ECharts instance on a DOM node, or create one.
 * Prefer this over dispose+init to avoid flicker and memory churn.
 */
export function ensureChart(el: HTMLElement): echarts.ECharts {
  return echarts.getInstanceByDom(el) ?? echarts.init(el)
}

/**
 * Reusable ECharts lifecycle helper for a single container ref.
 *
 * Usage:
 *   const chart = useChart(containerRef)
 *   chart.render(option)
 */
export function useChart(containerRef: Ref<HTMLElement | null>) {
  let instance: echarts.ECharts | null = null

  function ensure(): echarts.ECharts | null {
    if (!containerRef.value) return null
    instance = ensureChart(containerRef.value)
    return instance
  }

  function render(option: echarts.EChartsOption): void {
    const chart = ensure()
    if (!chart) return
    chart.setOption(option, { notMerge: true })
  }

  function resize(): void {
    instance?.resize()
  }

  function dispose(): void {
    instance?.dispose()
    instance = null
  }

  function handleResize() {
    instance?.resize()
  }

  window.addEventListener('resize', handleResize)
  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize)
    dispose()
  })

  return { render, resize, dispose, ensure }
}

/**
 * Lifecycle helper for a list of chart containers (ref="charts" array pattern).
 * Tracks instances by DOM element; never dispose+init on re-render.
 */
export function useChartList() {
  const instances = new Set<echarts.ECharts>()

  function render(el: HTMLElement | undefined, option: echarts.EChartsOption): echarts.ECharts | null {
    if (!el) return null
    const chart = ensureChart(el)
    instances.add(chart)
    chart.setOption(option, { notMerge: true })
    return chart
  }

  function resize(): void {
    instances.forEach(chart => chart.resize())
  }

  function dispose(): void {
    instances.forEach(chart => chart.dispose())
    instances.clear()
  }

  function handleResize() {
    resize()
  }

  window.addEventListener('resize', handleResize)
  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize)
    dispose()
  })

  return { render, resize, dispose }
}
