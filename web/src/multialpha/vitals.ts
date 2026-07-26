/**
 * web-vitals 采集：开发期在控制台输出 + 写 localStorage，便于性能优化前后对比。
 *
 * 采集指标（Google Web Vitals）：
 *   - TTFB: Time to First Byte，首字节时间（反映后端响应 + 网络往返）
 *   - FCP:  First Contentful Paint，首次内容绘制（反映页面加载到可见内容）
 *   - LCP:  Largest Contentful Paint，最大内容绘制（反映主要内容加载完成）
 *   - CLS:  Cumulative Layout Shift，累计布局偏移（反映视觉稳定性）
 *   - INP:  Interaction to Next Paint，交互到下次绘制（反映交互响应性）
 *
 * 优化 P0/P1/P2 各阶段跑一次标准操作，对比这些指标的变化。
 */
import { onCLS, onFCP, onINP, onLCP, onTTFB, type Metric } from 'web-vitals'

const STORAGE_KEY = 'multialpha:vitals'
const SAMPLE_SIZE = 50

function isDevMode(): boolean {
  // 开发期采集；生产可关
  return import.meta.env.DEV || localStorage.getItem('multialpha:vitals:enable') === '1'
}

function persist(metric: Metric): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const all = raw ? JSON.parse(raw) as Record<string, Array<{ name: string; value: number; ts: string }>> : {}
    const arr = all[metric.name] ?? []
    arr.push({ name: metric.name, value: metric.value, ts: new Date().toISOString() })
    all[metric.name] = arr.slice(-SAMPLE_SIZE)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    // localStorage 满或禁用，静默跳过
  }
}

function log(metric: Metric): void {
  const rating = metric.rating === 'good' ? '✅' : metric.rating === 'needs-improvement' ? '⚠️' : '🔴'
  const unit = metric.name === 'CLS' || metric.name === 'INP' ? '' : 'ms'
  // 控制台用颜色区分评级
  const color = metric.rating === 'good' ? '#4caf50' : metric.rating === 'needs-improvement' ? '#ff9800' : '#f44336'
  // eslint-disable-next-line no-console
  console.log(
    `%c[WebVitals] ${rating} ${metric.name}: ${metric.value.toFixed(2)}${unit} (rating: ${metric.rating})`,
    `color: ${color}; font-weight: bold`,
  )
}

export function setupVitals(): void {
  if (!isDevMode()) return

  const handler = (metric: Metric): void => {
    log(metric)
    persist(metric)
  }

  onTTFB(handler)
  onFCP(handler)
  onLCP(handler)
  onCLS(handler)
  onINP(handler)

  // eslint-disable-next-line no-console
  console.log(
    '%c[WebVitals] 采集已启用（TTFB/FCP/LCP/CLS/INP）。数据存 localStorage["multialpha:vitals"]。',
    'color: #2196f3',
  )
}
