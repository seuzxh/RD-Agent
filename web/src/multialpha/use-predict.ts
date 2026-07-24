import { ref, type Ref } from 'vue'
import * as api from './api'
import type { PredictExperiment, Top20Item, PredictRecord } from './api'

export type PredictStatus = 'idle' | 'loading-list' | 'ready' | 'predicting' | 'done' | 'error'

export function usePredict() {
  const experiments = ref<PredictExperiment[]>([]) as Ref<PredictExperiment[]>
  const selectedExp = ref<PredictExperiment | null>(null)
  const selectedTraceId = ref<string | null>(null)
  const status = ref<PredictStatus>('idle')
  const top20 = ref<Top20Item[] | null>(null)
  const predictDate = ref<string>('')
  const error = ref<string>('')
  const history = ref<PredictRecord[]>([])
  const historyVisible = ref(false)

  async function fetchExperiments() {
    status.value = 'loading-list'
    error.value = ''
    try {
      const res = await api.fetchPredictExperiments()
      experiments.value = res.experiments
      status.value = 'ready'
    } catch (e) {
      error.value = (e as Error).message
      status.value = 'error'
    }
  }

  function selectExperiment(exp: PredictExperiment) {
    selectedExp.value = exp
    selectedTraceId.value = exp.trace_id
    top20.value = null
    predictDate.value = ''
  }

  async function runPrediction() {
    if (!selectedTraceId.value) return
    status.value = 'predicting'
    error.value = ''
    top20.value = null
    try {
      const res = await api.runPredict(selectedTraceId.value)
      // 轮询任务状态(复用 fetchTrace)
      await pollTask(res.task_id)
    } catch (e) {
      error.value = (e as Error).message
      status.value = 'error'
    }
  }

  async function pollTask(taskId: string) {
    let cursor = 0
    for (let i = 0; i < 120; i++) { // 最多等 10 分钟(5s * 120)
      try {
        const msgs = await api.fetchTrace({ id: taskId, all: false, reset: false, cursor })
        if (msgs && msgs.length > 0) {
          cursor += msgs.length
          // 找 prediction.top20 消息
          for (const msg of msgs) {
            if (msg.tag === 'prediction.top20' && msg.content) {
              const content = msg.content as { predict_date: string; top20: Top20Item[] }
              top20.value = content.top20
              predictDate.value = content.predict_date
              status.value = 'done'
              return
            }
            // END tag
            if (msg.tag === 'END') {
              const endContent = msg.content as { end_code?: number }
              if (endContent?.end_code !== 0) {
                error.value = `预测任务异常退出 (code=${endContent?.end_code})`
                status.value = 'error'
                return
              }
            }
          }
        }
      } catch {
        // 忽略轮询错误
      }
      await new Promise(r => setTimeout(r, 5000))
    }
    error.value = '预测超时'
    status.value = 'error'
  }

  async function fetchHistory() {
    try {
      const res = await api.fetchPredictHistory(selectedTraceId.value || undefined)
      history.value = res.records
    } catch {
      history.value = []
    }
  }

  return {
    experiments, selectedExp, selectedTraceId, status, top20, predictDate,
    error, history, historyVisible,
    fetchExperiments, selectExperiment, runPrediction, fetchHistory,
  }
}
