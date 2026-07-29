// prediction 专用 API re-export
// prediction 专属 API + 类型(定义在 services/rdagent-api.ts)，外加轮询复用的 fetchTrace
export { fetchPredictExperiments, runPredict, fetchPredictHistory, fetchTrace } from '../services/rdagent-api'
export type { PredictExperiment, Top20Result, PredictRecord, Top20Item, TraceMessage, TraceRequest } from '../services/rdagent-api'
