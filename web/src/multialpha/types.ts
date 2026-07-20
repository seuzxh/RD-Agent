export type TraceStatus = 'idle' | 'running' | 'done' | 'error'
export type ResultTab = 'conclusion' | 'factors' | 'chart' | 'code'
export type TaskMethod = 'text' | 'pdf' | 'optimize' | 'image' | 'trade'
export type { TraceMessage } from '../services/rdagent-api'

export interface TraceTask { id:string; scenario:string; name:string; status:TraceStatus }
export interface CodeFile { name:string; content:string; target?:string; evoId?:string|number }
export interface MetricItem { label:string; value:string|number; rawValue?:number; tone?:'up'|'down'|'neutral'; percent?:boolean }
export interface FactorItem { name:string; description?:string; formula?:string; variables?:Record<string,string>; code?:string }
export interface FeedbackSummary { decision:boolean|null; reason:string; observations:string; evaluation:string; newHypothesis:string; exception:string }
export interface TraceViewModel {
  hasEnd:boolean; hasError:boolean; loops:number[]; hypothesis:Record<string,unknown>|null
  initialTasks:FactorItem[]; config:Array<{key:string;value:string}>; factors:FactorItem[]; codes:CodeFile[]
  chartHtml:string; metrics:MetricItem[]; metricValues:Record<string,number|string>; feedback:FeedbackSummary
  promptTokens:number; completionTokens:number; totalTokens:number; callCount:number; loopMetrics:Record<number,string>
}
