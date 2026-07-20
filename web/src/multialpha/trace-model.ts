import type { CodeFile,FactorItem,FeedbackSummary,MetricItem,TraceMessage,TraceStatus,TraceViewModel } from './types'

function objectValue(value:unknown):Record<string,unknown>|null{if(value&&typeof value==='object'&&!Array.isArray(value))return value as Record<string,unknown>;if(typeof value!=='string')return null;try{return objectValue(JSON.parse(value))}catch{return null}}
function arrayValue(value:unknown):unknown[]{if(Array.isArray(value))return value;if(typeof value!=='string')return[];try{const parsed=JSON.parse(value);return Array.isArray(parsed)?parsed:[]}catch{return[]}}
function textValue(value:unknown):string{if(typeof value==='string')return value;if(value==null)return'';try{return JSON.stringify(value,null,2)}catch{return String(value)}}
function latest(messages:TraceMessage[],tag:string){return[...messages].reverse().find(message=>message.tag===tag)}

export function deriveTraceStatus(messages:TraceMessage[]):TraceStatus{
  const hasEnd=messages.some(message=>message.tag==='END')
  const hasFinalFeedback=messages.some(message=>message.tag==='feedback.hypothesis_feedback')
  const hasMetric=messages.some(message=>message.tag==='feedback.metric')
  if(hasEnd||(hasFinalFeedback&&hasMetric))return'done'
  if(messages.some(message=>/error/i.test(message.tag||'')))return'error'
  return'running'
}

function parseFactors(value:unknown):FactorItem[]{return arrayValue(value).map((item,index)=>{const data=objectValue(item)||{};const variables=objectValue(data.variables);return{name:String(data.name||data.factor_name||data.task_name||`Factor ${index+1}`),description:String(data.description||data.factor_description||''),formula:String(data.formulation||data.formula||data.expression||''),variables:variables?Object.fromEntries(Object.entries(variables).map(([key,val])=>[key,textValue(val)])):undefined,code:String(data.code||'')}})}

function parseCodes(value:unknown):CodeFile[]{const files:CodeFile[]=[];for(const raw of arrayValue(value)){const item=objectValue(raw);const workspace=objectValue(item?.workspace);if(!item||!workspace||!Object.keys(workspace).length)continue;for(const [name,content] of Object.entries(workspace)){if(typeof content==='string'&&content.trim())files.push({name,content,target:String(item.target_task_name||''),evoId:item.evo_id as string|number|undefined})}}if(files.length)return files;const data=objectValue(value);if(typeof data?.code==='string')return[{name:'factor.py',content:data.code}];if(typeof value==='string')return[{name:'factor.py',content:value}];return[]}

function parseMetricValues(value:unknown):Record<string,number|string>{const data=objectValue(value);if(!data)return{};const nested=objectValue(data.result);const source=nested||objectValue(data.metrics)||data;return Object.fromEntries(Object.entries(source).filter(([,item])=>['string','number'].includes(typeof item)).map(([key,item])=>[key,item as number|string]))}
const metricLabels:Record<string,string>={IC:'IC',ICIR:'ICIR','Rank IC':'Rank IC','Rank ICIR':'Rank ICIR','1day.excess_return_with_cost.annualized_return':'年化收益','1day.excess_return_with_cost.max_drawdown':'最大回撤','1day.excess_return_with_cost.information_ratio':'信息比率',annualized_return:'年化收益',max_drawdown:'最大回撤',information_ratio:'信息比率'}
function parseMetrics(value:unknown):{items:MetricItem[];values:Record<string,number|string>}{const values=parseMetricValues(value);const priority=['IC','ICIR','1day.excess_return_with_cost.annualized_return','1day.excess_return_with_cost.max_drawdown','1day.excess_return_with_cost.information_ratio','Rank IC','Rank ICIR'];const keys=[...priority.filter(key=>key in values),...Object.keys(values).filter(key=>!priority.includes(key))].slice(0,16);return{values,items:keys.map(key=>{const raw=values[key],number=Number(raw),percent=/annualized_return|max_drawdown/.test(key);return{label:metricLabels[key]||key,value:Number.isFinite(number)?number:raw,rawValue:Number.isFinite(number)?number:undefined,percent,tone:Number.isFinite(number)?number>0?'up':number<0?'down':'neutral':'neutral'}})}}

function parseFeedback(value:unknown):FeedbackSummary{const data=objectValue(value)||{};const decision=data.decision===true||data.decision==='True'||data.decision==='true'?true:data.decision===false||data.decision==='False'||data.decision==='false'?false:null;return{decision,reason:textValue(data.reason),observations:textValue(data.observations),evaluation:textValue(data.hypothesis_evaluation),newHypothesis:textValue(data.new_hypothesis),exception:textValue(data.exception)}}
function parseConfig(value:unknown){const data=objectValue(value);const raw=textValue(data?.config||value);const lines=raw.split('\n').map(line=>line.trim()).filter(line=>line.startsWith('|')&&line.endsWith('|'));if(lines.length>=3){const keys=lines[0].slice(1,-1).split('|').map(item=>item.trim()),values=lines[2].slice(1,-1).split('|').map(item=>item.trim());return keys.map((key,index)=>({key,value:values[index]||''})).filter(item=>item.value)}return data?Object.entries(data).filter(([,item])=>['string','number'].includes(typeof item)).map(([key,item])=>({key,value:String(item)})):[]}

export function buildTraceView(messages:TraceMessage[],loop:number|null):TraceViewModel{
  const scoped=loop==null?messages:messages.filter(message=>message.loop_id==null||Number(message.loop_id)===loop)
  const tokenMessages=scoped.filter(message=>message.tag==='token_cost').map(message=>objectValue(message.content)||{}),token=tokenMessages[tokenMessages.length-1]||{}
  const hypothesis=objectValue(latest(scoped,'research.hypothesis')?.content),tasks=parseFactors(latest(scoped,'research.tasks')?.content),codes=parseCodes(latest(scoped,'evolving.codes')?.content)
  const metricData=parseMetrics(latest(scoped,'feedback.metric')?.content),feedback=parseFeedback(latest(scoped,'feedback.hypothesis_feedback')?.content)
  const chartData=objectValue(latest(scoped,'feedback.return_chart')?.content)
  const loops=[...new Set(messages.map(message=>Number(message.loop_id)).filter(Number.isFinite))].sort((a,b)=>a-b)
  const loopMetrics:Record<number,string>={};for(const loopId of loops){const metric=parseMetricValues(latest(messages.filter(message=>Number(message.loop_id)===loopId),'feedback.metric')?.content);if(metric.IC!=null)loopMetrics[loopId]=`IC=${Number(metric.IC).toFixed(3)}`}
  return{hasEnd:messages.some(message=>message.tag==='END'),hasError:messages.some(message=>/error/i.test(message.tag)),loops,hypothesis,initialTasks:parseFactors(messages.find(message=>message.tag==='research.tasks'&&Number(message.loop_id)===0)?.content),config:parseConfig(messages.find(message=>message.tag==='feedback.config')?.content),factors:tasks,codes,chartHtml:textValue(chartData?.chart_html||chartData?.html||chartData?.chart),metrics:metricData.items,metricValues:metricData.values,feedback,promptTokens:Number(token.accumulated_prompt_tokens||token.prompt_tokens||0),completionTokens:Number(token.accumulated_completion_tokens||token.completion_tokens||0),totalTokens:Number(token.total_tokens||Number(token.accumulated_prompt_tokens||0)+Number(token.accumulated_completion_tokens||0)),callCount:Number(token.call_count||tokenMessages.length),loopMetrics}
}
