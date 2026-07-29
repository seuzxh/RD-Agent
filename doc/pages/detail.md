# 任务详情页（`#/tasks/:traceId`）

> 路由：`multialpha-task` · 组件：DetailHeader / PipelineStages / AgentFlow / ResultWorkspace / LogConsole 等
> 本页覆盖：迭代过程展示、结果工作区、运行日志、SOTA 对比、停止任务

---

## 1. 功能需求（PRD）

### 1.1 任务元信息
- 任务名、场景、状态、当前轮次选择器（Loop Switcher）

### 1.2 迭代过程展示
- **F2.2.1** Pipeline 阶段进度（PipelineStages）
- **F2.2.2** 任务摘要：假设、配置、初始因子任务（TaskBrief）
- **F2.2.3** 智能体流：因子、代码、指标值、反馈、假设（AgentFlow）
- **F2.2.4** Token 仪表盘：prompt/completion/total token + 调用次数

### 1.3 结果工作区（ResultWorkspace，4 个 Tab）
- **F2.3.1 最终结论**：核心指标（IC/年化/回撤/信息比率）、采纳/拒绝决策、反馈理由
- **F2.3.2 因子结果**：因子卡片（名称、描述、公式、变量）
- **F2.3.3 收益曲线**：iframe 嵌入 plotly 图表
- **F2.3.4 因子代码**：代码查看、多文件切换、复制、下载
- **F2.3.5** SOTA 产物弹窗：最优 loop 的假设/指标/反馈/因子代码
- **F2.3.6** 下载产物：导出 JSON（指标/因子/代码/反馈）

### 1.4 指标面板（MetricsPanel）
- 完整指标列表、因子、假设、反馈，支持下载

### 1.5 运行日志（LogConsole）
- **F2.5.1** 折叠/展开，展开后虚拟滚动显示日志（最多 5000 行）
- **F2.5.2** 实时轮询 stdout（任务运行中自动，已完成点击加载）
- **F2.5.3** 关键字搜索、隐藏 INFO、按级别着色（error/warn/success）
- **F2.5.4** 提供 stdout 完整下载链接

### 1.6 操作
- 停止任务（control）、自动轮询更新（5s 间隔，直到 done）

---

## 2. 技术方案

### 2.1 数据流

```
路由变化 → syncRoute() → selectTrace(id)
  │
  ├─ 命中 LRU 缓存(cache, 上限5)? → 直接渲染
  │
  └─ POST /trace {id, all:true, reset:true}  → messages[]
       │
       ├─ buildTraceView(messages, loop)  → view computed (单遍扫描)
       │    ├─ 按 tag 分类解析: hypothesis/tasks/codes/metric/feedback/chart/config/token
       │    ├─ deriveTraceStatus() → done/running/error
       │    └─ → 驱动 DetailHeader/AgentFlow/ResultWorkspace/...
       │
       ├─ status !== 'done'? → poll(id) 每 5s
       │    └─ POST /trace {id, cursor: messages.length}  → 增量消息
       │
       └─ LogConsole (独立)
            ├─ status === 'running' → 自动轮询 GET /stdout (Range, 2-8s 退避)
            └─ status !== 'running' → 点击展开才加载
```

### 2.2 消息解析（buildTraceView，单遍扫描 C7）

`trace-model.ts:23` 的 `buildTraceView` 一次遍历完成：loop 过滤后取各 tag 的 **latest** 消息，同时全量收集 loop/end/error/config。

| tag | 含义 | 解析产物 | 驱动组件 |
|---|---|---|---|
| `research.hypothesis` | 因子假设 | `hypothesis` | TaskBrief / AgentFlow |
| `research.tasks` (loop0) | 初始因子任务 | `initialTasks` | TaskBrief |
| `research.tasks` (当前loop) | 本轮因子任务 | `factors` | ResultWorkspace 因子Tab |
| `evolving.codes` | 因子代码 | `codes[]` | ResultWorkspace 代码Tab |
| `feedback.metric` | 回测指标 | `metrics` + `metricValues` + `loopMetrics` | ResultWorkspace 结论 / MetricsPanel / LoopSwitcher |
| `feedback.hypothesis_feedback` | 反馈决策 | `feedback` | ResultWorkspace 结论 |
| `feedback.return_chart` | 图表引用 | `chartRef` / `chartHtml` | ResultWorkspace 收益曲线Tab |
| `feedback.config` | 运行配置 | `config[]` | TaskBrief |
| `token_cost` | Token 消耗 | `totalTokens` 等 | TokenDashboard |
| `END` | 流程结束 | `hasEnd` | deriveTraceStatus → done |
| 含 `error` | 异常 | `hasError` | deriveTraceStatus → error |

---

## 3. 接口契约

### 3.1 `POST /trace` — 任务消息流

| 项 | 值 |
|---|---|
| 触发 | `selectTrace()` 首次进入（`use-multialpha.ts:121`）；运行中任务 5s 轮询（`:92`） |
| Content-Type | `application/json` |
| 后端 | `app.py:803` `update_trace()`，cursor 增量 |

**请求体**：
```jsonc
{
  "id": "Finance Data Building/generous-column",
  "all": true,      // 首次 true；轮询 false
  "reset": true,    // 首次 true；轮询 false
  "cursor": 0       // 轮询时传当前 messages.length；首次/legacy 不传
}
```

**响应体** `TraceMessage[]`：
```json
[{
  "tag": "research.hypothesis",
  "timestamp": "2026-07-26T...",
  "loop_id": 0,
  "content": { ... }
}]
```

**失败**：`ElMessage.error`；轮询失败静默重试（保留已渲染数据）。

---

### 3.2 `GET /stdout` — 运行日志（HTTP Range）

| 项 | 值 |
|---|---|
| 触发 | LogConsole 展开时（`LogConsole.vue:120`）；运行中自动轮询，已完成点击加载 |
| 请求头 | `Range: bytes={offset}-`（offset>0 时） |
| 后端 | `app.py:861` `download_stdout_file()`，Flask `send_file` 原生 Range |

**URL**：`/stdout?id={traceId}`

**响应（3 种状态）**：
| 状态 | 含义 | 前端处理 |
|---|---|---|
| `206` + `Content-Range: bytes start-end/total` | 正常增量切片 | `nextOffset = end + 1` |
| `416` + `Content-Range: bytes */total` | offset 超出 EOF | total<offset → 文件被截断，重置 offset=0；否则等待 |
| `200`（无 Range） | 全量回退 | `nextOffset = Content-Length` |

**渲染**：虚拟滚动列表（`MAX_LINES=5000`，`LINE_HEIGHT=20`），支持关键字过滤、隐藏 INFO、级别着色。

**轮询策略**：基础 2s，连续 3 次无数据后退避至最大 8s。

---

### 3.3 `GET /api/v2/trace/artifact` — 收益曲线 HTML（C5）

| 项 | 值 |
|---|---|
| 触发 | 切到"收益曲线"Tab 时（`ResultWorkspace.vue:29` 拼 URL，iframe `src`） |
| 参数 | `id`（必填）、`loop`（可选） |
| 后端 | `app.py:758` `get_chart_artifact()`，HTML 走 bootcdn 加载 plotly.js |

**响应**：`200` text/html（iframe 直接渲染）；`304`（If-None-Match 命中）；`404`（无图表）。

---

### 3.4 `GET /traces/:id/sota` — SOTA 产物

| 项 | 值 |
|---|---|
| 触发 | 点击"🏆 SOTA 产物"按钮（`ResultWorkspace.vue:40`） |
| 参数 | 路径 `trace_name`；可选 `log_path` |
| 后端 | `app.py:1249` `get_sota()`，依次查 `__session__` → message stream |

**响应体**：
```json
{
  "sota_loop_id": 3,
  "sota_hypothesis": { "hypothesis": "...", "concise_reason": "..." },
  "sota_metrics": { "IC": 0.05, "1day.excess_return_with_cost.annualized_return": 0.2 },
  "sota_feedback": { "decision": true, "reason": "..." },
  "sota_factors": [{ "name": "...", "description": "...", "code": "..." }]
}
```

---

### 3.5 `POST /control` — 任务控制

| 项 | 值 |
|---|---|
| 触发 | 详情页"停止"按钮（`use-multialpha.ts:171` `stopCurrentTask`） |
| 请求体 | `{ "id": "...", "action": "stop" }` |

**响应**：`200`。后端追加 END 消息 + 投影到 catalog（见 [TRACE_STATUS_FIX](../design/TRACE_STATUS_FIX.md)）。前端立即置 `status='done'` + 停止轮询 + `ElMessage.success`。

---

## 4. 实现索引

### 详情页组件
| 文件 | 消费数据 | 渲染职责 |
|---|---|---|
| `components/DetailHeader.vue` | currentTask | 任务元信息 + 停止按钮 |
| `components/PipelineStages.vue` | scopedMessages | 流程阶段进度 |
| `components/TaskBrief.vue` | view.hypothesis/config/initialTasks | 任务摘要 |
| `components/AgentFlow.vue` | scopedMessages + view.* | 智能体协作流 |
| `components/LoopSwitcher.vue` | selectedLoop + view.loops/loopMetrics | 轮次切换 |
| `components/TokenDashboard.vue` | view.totalTokens 等 | Token 统计 |
| `components/ResultWorkspace.vue` | view.* | **4 Tab 结果区** + SOTA 弹窗 + 图表 iframe |
| `components/MetricsPanel.vue` | view.metrics/factors/feedback | 完整指标面板 |
| `components/LogConsole.vue` | traceId + status | **运行日志**（虚拟滚动 + Range 轮询） |
| `components/TraceLoading.vue` | loading | 加载态 |

### 数据层关键位置
| 文件:行 | 作用 |
|---|---|
| `use-multialpha.ts:87-108` | `poll()`：5s 轮询 POST /trace（增量） |
| `use-multialpha.ts:110-125` | `requestInitial()`：首次拉 trace + LRU 缓存 |
| `use-multialpha.ts:127-150` | `selectTrace()`：进入详情主流程 |
| `trace-model.ts:7-13` | `deriveTraceStatus()`：消息推导状态 |
| `trace-model.ts:23-68` | `buildTraceView()`：单遍扫描消息→ViewModel |

### 后端路由
| 路由 | 方法 | 文件:行 | 实现函数 |
|---|---|---|---|
| `/trace` | POST | `app.py:803` | `update_trace()` cursor 增量 |
| `/stdout` | GET | `app.py:861` | `download_stdout_file()` Range |
| `/api/v2/trace/artifact` | GET | `app.py:758` | `get_chart_artifact()` C5 |
| `/traces/<path>/sota` | GET | `app.py:1249` | `get_sota()` |
| `/control` | POST | `app.py:1201` | 任务控制 |
