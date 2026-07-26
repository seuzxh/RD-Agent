# MultiAlpha 前端规格文档（PRD / 技术方案 / 接口清单 / 实现索引）

> 版本：v1.0 · 更新：2026-07-26
> 范围：MultiAlpha 单页应用 —— **首页**（`#/`）与**任务详情页**（`#/tasks/:traceId`）
> 受众：产品 / 前后端开发 / 测试 / 技术评审

---

## 目录

- [第一部分 · 产品需求文档（PRD）](#第一部分产品需求文档prd)
- [第二部分 · 技术方案设计](#第二部分技术方案设计)
- [第三部分 · 接口清单及契约](#第三部分接口清单及契约)
- [第四部分 · 实现索引（代码地图）](#第四部分实现索引代码地图)

---

# 第一部分·产品需求文档（PRD）

## 1.1 产品定位

MultiAlpha 是面向量化研究员的 **AI 因子挖掘终端**。将一句自然语言策略构想，通过 5 个智能体协作、最多 10 轮自动迭代，转化为可回测、可执行的 α 因子（含因子代码、回测指标、收益曲线）。

- **目标用户**：量化研究员、策略分析师
- **核心价值**：把"投研假设 → 因子代码 → 回测验证 → 反馈优化"的人工闭环，自动化为端到端 R&D 流程
- **部署形态**：内网私有部署（国新证券），Flask 单服务 + 前端 SPA

## 1.2 功能范围（本文档覆盖）

| 页面 | 路由 | 核心功能 |
|---|---|---|
| **首页** | `#/` | 任务总览（列表 + 统计）、新建任务入口、多智能体架构展示 |
| **任务详情页** | `#/tasks/:traceId` | 单任务的迭代过程、因子结果、回测图表、运行日志、SOTA 对比 |

> 预测页 `#/predict` 不在本文档范围。

## 1.3 首页功能需求

### F1.1 任务总览
- **F1.1.1** 左侧任务列表展示所有历史与进行中任务，按场景分类（因子挖掘 / 研报因子提取 / 量化全流程 / 模型实现）
- **F1.1.2** 每条任务显示：任务名、场景标签、**实时状态**（运行中 / 已完成 / 异常 / 待查看）
- **F1.1.3** 支持按场景下拉筛选、按状态（全部 / 完成 / 运行中）chip 筛选
- **F1.1.4** 列表超过 10 条时分页，点击"加载更多"每次 +10
- **F1.1.5** 点击任务跳转详情页

### F1.2 首屏仪表盘
- **F1.2.1** Hero 统计卡：TASKS 总数、已完成数、运行中数
- **F1.2.2** Ticker 滚动条：前 8 条任务名 + 状态图标（✓/▶/○）
- **F1.2.3** 实时时钟（每秒刷新）

### F1.3 任务入口
- **F1.3.1** 文字描述建任务（可用）
- **F1.3.2** 研报 PDF 因子提取（可用）
- **F1.3.3** 因子迭代优化（可用）
- **F1.3.4** K 线图形分析（即将上线，禁用）
- **F1.3.5** 交割单分析（即将上线，禁用）
- **F1.3.6** 查看历史任务（聚焦左侧列表）

### F1.4 操作
- **F1.4.1** 顶栏"刷新任务"按钮：重新拉取列表
- **F1.4.2** 顶栏"健康检查"按钮：弹窗显示环境检查项
- **F1.4.3** 列表加载失败时显示错误 + "重新加载"

## 1.4 任务详情页功能需求

### F2.1 任务元信息
- 任务名、场景、状态、当前轮次选择器（Loop Switcher）

### F2.2 迭代过程展示
- **F2.2.1** Pipeline 阶段进度（PipelineStages）
- **F2.2.2** 任务摘要：假设、配置、初始因子任务（TaskBrief）
- **F2.2.3** 智能体流：因子、代码、指标值、反馈、假设（AgentFlow）
- **F2.2.4** Token 仪表盘：prompt/completion/total token + 调用次数

### F2.3 结果工作区（ResultWorkspace，4 个 Tab）
- **F2.3.1 最终结论**：核心指标（IC/年化/回撤/信息比率）、采纳/拒绝决策、反馈理由
- **F2.3.2 因子结果**：因子卡片（名称、描述、公式、变量）
- **F2.3.3 收益曲线**：iframe 嵌入 plotly 图表
- **F2.3.4 因子代码**：代码查看、多文件切换、复制、下载
- **F2.3.5** SOTA 产物弹窗：最优 loop 的假设/指标/反馈/因子代码
- **F2.3.6** 下载产物：导出 JSON（指标/因子/代码/反馈）

### F2.4 指标面板（MetricsPanel）
- 完整指标列表、因子、假设、反馈，支持下载

### F2.5 运行日志（LogConsole）
- **F2.5.1** 折叠/展开，展开后虚拟滚动显示日志（最多 5000 行）
- **F2.5.2** 实时轮询 stdout（任务运行中自动，已完成点击加载）
- **F2.5.3** 关键字搜索、隐藏 INFO、按级别着色（error/warn/success）
- **F2.5.4** 提供 stdout 完整下载链接

### F2.6 操作
- 停止任务（control）、自动轮询更新（5s 间隔，直到 done）

## 1.5 非功能需求

| 项 | 要求 |
|---|---|
| 首屏渲染 | 后端 API 响应 < 100ms（实测 < 3ms） |
| 字体 | ⚠️ 当前依赖 Google Fonts CDN，国内首屏阻塞 ~769ms，**需本地化** |
| 轮询 | 运行中任务日志轮询退避（2s→8s），详情消息 5s 固定 |
| 容错 | `/traces/status` 不可用时降级为 N+1 全量拉取 |
| 缓存 | trace 详情 LRU 缓存 5 条；静态资源当前 `no-cache`（建议 hash 资源 immutable） |

---

# 第二部分·技术方案设计

## 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                   浏览器（SPA）                           │
│  Vue 3 + Vue Router (hash) + Element Plus + ECharts      │
│                                                          │
│  MultiAlphaApp.vue                                       │
│   ├─ useMultiAlpha() composable  ← 唯一数据层            │
│   │    ├─ loadTraceIds()      → GET /traces              │
│   │    ├─ loadStatusesBatch() → GET /traces/status       │
│   │    ├─ selectTrace()       → POST /trace (+轮询)      │
│   │    └─ createTask()        → POST /upload             │
│   ├─ ① TopBar                                            │
│   ├─ ② TaskSidebar                                       │
│   └─ ③ LandingTerminal / DetailWorkspace / PredictDash  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP (同源，开发期 vite proxy)
┌────────────────────────▼────────────────────────────────┐
│            Flask 后端 (rdagent/log/server/app.py)         │
│  /traces  /traces/status  /trace  /stdout  /upload       │
│  /control  /health  /traces/:id/sota  /api/v2/...        │
│  静态服务 send_from_directory(git_ignore_folder/static)   │
└────────────────────────┬────────────────────────────────┘
                         │ 文件系统 / 子进程
┌────────────────────────▼────────────────────────────────┐
│  trace 日志目录 + RD-Agent 子进程（因子挖掘执行环境）       │
└─────────────────────────────────────────────────────────┘
```

## 2.2 前端分层设计

```
视图层 (components/*.vue)        ← 纯展示，props in / emit out，自身不发请求
   ▲ props 下发 / emit 上抛
组合层 (use-multialpha.ts)       ← 唯一状态中枢：tasks/messages/statuses/cache
   ▲ 调用
服务层 (services/rdagent-api.ts) ← fetch 封装，ApiError，类型定义
   ▲ HTTP
后端 (Flask routes)
```

**设计原则**：
1. **单一数据源**：所有组件不直接 fetch，统一由 `useMultiAlpha()` 管理，避免 N+1 与状态不一致
2. **props down / events up**：组件无副作用，便于测试与复用
3. **类型驱动**：`types.ts` 定义所有契约，API 层泛型约束响应

## 2.3 首页数据流

```
onMounted(MultiAlphaApp)
  │
  ▼
loadTraceIds()                          [串行]
  ├─ GET /traces          → traceIds[]
  │    失败 → listError = msg → TaskSidebar 显示错误 + 重试
  │    成功 ↓
  └─ loadStatusesBatch()
       ├─ GET /traces/status → statuses{} (推荐路径, C1 优化)
       │    失败 → 降级: 对未缓存 trace 逐个 POST /trace {all:true}
       └─ 合并 → tasks computed → 下发 ①②③ 组件
                                ↓
                         首屏渲染完成（无后续请求）
```

**tasks computed（数据合并枢纽，`use-multialpha.ts:28`）**：
```ts
traceIds.map(id => {
  const [scenario, ...name] = id.split('/')
  return { id, scenario, name: name.join('/'), status: statuses[id] || 'idle' }
})
```

## 2.4 任务详情页数据流

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

## 2.5 关键技术决策

| 决策 | 方案 | 理由 |
|---|---|---|
| 路由模式 | hash history (`createWebHashHistory`) | Flask 统一兜底 `/<path:fn>` 服务静态，hash 避免后端路由配置 |
| 状态管理 | composable（非 Pinia） | 单页应用状态简单，组合式函数足够，减少依赖 |
| 状态批量获取 | C1 端点 `/traces/status` | 替代首页 N+1 全量拉 trace，1 次请求获取所有状态 |
| 日志获取 | HTTP Range 增量轮询（非 SSE） | Flask `send_file` 原生支持 Range；SSE 在 Werkzeug 下需额外处理 |
| 图表加载 | C5 artifact 端点 + iframe | plotly.js 走 CDN 不内联（省 2.7MB）；HTML 按 trace+loop 缓存 |
| 消息解析 | 单遍扫描 `buildTraceView` (C7) | 一次遍历完成 latest-by-tag + loop/end/error 收集，O(n) |
| 缓存 | LRU 5 条 + 状态缓存 | 避免来回切换 trace 重复请求 |

## 2.6 性能与优化项

| 优先级 | 问题 | 影响 | 建议 |
|---|---|---|---|
| 🔴 P0 | Google Fonts 阻塞首屏 ~769ms | FCP/LCP 严重劣化，国内可能不可达 | 字体本地化或 `media="print" onload` |
| 🟡 P1 | 首页 `/traces` 与 `/traces/status` 串行 | 多 1 个 RTT | 二者无依赖，`Promise.all` 并行 |
| 🟡 P1 | 主 bundle 731KB 无代码分割 | 首屏加载全量（含详情/预测组件） | 路由懒加载 `import()` |
| 🟢 P2 | 静态资源 `Cache-Control: no-cache` | 每次回源验证 | hash 资源 `max-age=31536000, immutable` |
| 🟢 P2 | API 无 Cache-Control | 列表每次回源 | `/traces/status` 可短缓存 5s |

---

# 第三部分·接口清单及契约

## 3.0 接口总览

| # | 接口 | 方法 | 页面 | 触发时机 | 渲染区域 |
|---|---|---|---|---|---|
| 1 | `/traces` | GET | 首页 | onMounted | TaskSidebar 列表 + Landing 统计/ticker |
| 2 | `/traces/status` | GET | 首页 | /traces 成功后 | TaskSidebar 状态点 + Landing 计数/ticker |
| 3 | `/trace` | POST | 详情 | 进入详情 + 5s 轮询 | 详情全部区域（经 buildTraceView） |
| 4 | `/stdout` | GET (Range) | 详情 | LogConsole 展开时 | LogConsole 日志 |
| 5 | `/api/v2/trace/artifact` | GET | 详情 | 切到"收益曲线"Tab | ResultWorkspace iframe |
| 6 | `/traces/:id/sota` | GET | 详情 | 点击"SOTA 产物"按钮 | ResultWorkspace SOTA 弹窗 |
| 7 | `/upload` | POST | 首页 | 新建任务提交 | 创建后跳详情 |
| 8 | `/control` | POST | 详情 | 点击"停止" | 状态更新 |
| 9 | `/health` | GET | 首页 | 点击"健康检查"按钮 | TopBar 弹窗 |

> 通用响应头：`Access-Control-Allow-Origin: *`。错误体统一 `{ "error": "..." }`，前端 `ApiError` 抛出。

---

## 3.1 `GET /traces` — 任务 ID 清单

**作用**：返回所有可浏览的 trace id，首页任务列表的**唯一数据源**。

| 项 | 值 |
|---|---|
| 触发 | `use-multialpha.ts:45` `loadTraceIds()` ← `MultiAlphaApp.vue:24` onMounted |
| 请求 | 无参数，无自定义头 |
| 响应 | `200` `application/json`，无 Cache-Control |
| 后端 | `app.py:879` `list_traces()` 扫描日志目录 |

**响应体** `string[]`（目录顺序）：
```json
["Finance Data Building/generous-column", "Finance Prediction/bipartite-module-20260724", ...]
```

**字段 → 渲染映射**（id 按 `/` 拆解为 scenario + name）：

| 字段 | 组件 | 渲染位置 | UI 表现 |
|---|---|---|---|
| `id` | TaskSidebar:16 | 列表项 | key + 点击跳转 `#/tasks/:id` |
| `name`（`/`后） | TaskSidebar:17 | `.task-name` | 任务名 |
| `scenario`（`/`前） | TaskSidebar:5,18,33 | 下拉选项 + `.task-meta` | 转中文（因子挖掘/研报因子提取...） |
| `length` | LandingTerminal:15 | hero 卡 TASKS | `padStart(2,'0')` |
| `name`(前8) | LandingTerminal:14 | ticker 滚动条 | 任务名 |

**失败**：`listError` 置位 → TaskSidebar 红色"任务加载失败" + 重试按钮 + `ElMessage.error`。

---

## 3.2 `GET /traces/status` — 批量状态快照（C1）

**作用**：为 `/traces` 的每个任务补充实时状态，替代 N+1 全量拉取。

| 项 | 值 |
|---|---|
| 触发 | `use-multialpha.ts:53` `loadStatusesBatch()` ← `/traces` 成功后 |
| 请求 | 无参数 |
| 响应 | `200` `application/json`，无 Cache-Control |
| 后端 | `app.py:887` `list_trace_statuses()` 读内存 `trace_states`，按 `created_at DESC` 排序 |

**响应体** `TraceStatusItem[]`：
```json
[{
  "id": "Finance Data Building/generous-column",
  "status": "done",                 // running|done|error|idle
  "loops": [],
  "created_at": "2026-07-26T07:47:34:234099Z",
  "updated_at": "2026-07-26T08:01:41:405264Z",
  "has_chart": true
}]
```

**字段 → 渲染映射**（写入 `statuses[id]`，经 tasks computed 合并）：

| 字段 | 组件 | 渲染位置 | UI 表现 |
|---|---|---|---|
| `status` | TaskSidebar:17 | `.status-dot` | 状态点颜色（running蓝/done绿/error红/idle无） |
| `status` | TaskSidebar:18 | `.task-meta` | 转中文（运行中/已完成/异常/待查看） |
| `status` | TaskSidebar:9,34 | 筛选 chips | 全部/完成/运行中 |
| `status` | LandingTerminal:14 | ticker 图标 | done✓/running▶/其他○ |
| `status` 聚合 | LandingTerminal:35 | hero 卡副标题 | doneCount + runningCount |
| `created_at`/`updated_at`/`loops`/`has_chart` | — | **首页不用** | 仅详情页 |

**失败降级**（`use-multialpha.ts:67-77`）：404 时对未缓存 trace 逐个 `POST /trace {all:true}` → `deriveTraceStatus()` 推导状态。

---

## 3.3 `POST /trace` — 任务消息流

**作用**：详情页核心接口，返回任务全部/增量消息，前端解析为各 UI 区域。

| 项 | 值 |
|---|---|
| 触发 | `selectTrace()` 首次进入（`use-multialpha.ts:121`）；运行中任务 5s 轮询（`:92`）；`/traces/status` 降级时 |
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
  "tag": "research.hypothesis",   // 见下表 tag 分类
  "timestamp": "2026-07-26T...",
  "loop_id": 0,
  "content": { ... }              // 结构因 tag 而异
}]
```

**消息 tag 分类与消费**（`trace-model.ts` `buildTraceView` 单遍扫描）：

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

**关键解析逻辑**：
- `deriveTraceStatus()`：倒序扫描，`END` 或（最终反馈 + 指标）→ done；含 error → error；否则 running
- `buildTraceView(messages, loop)`：loop 过滤后取各 tag 的 **latest** 消息；loop/end/error/config 全量收集

**失败**：`ElMessage.error`；轮询失败静默重试（保留已渲染数据）。

---

## 3.4 `GET /stdout` — 运行日志（HTTP Range）

**作用**：LogConsole 实时日志内容，增量获取。

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
| `416` + `Content-Range: bytes */total` | offset 超出 EOF | total<offset → 文件被截断，重置 offset=0；否则等待，无数据 |
| `200`（无 Range） | 全量回退 | `nextOffset = Content-Length` |

**渲染**：虚拟滚动列表（`MAX_LINES=5000`，`LINE_HEIGHT=20`），支持关键字过滤、隐藏 INFO、级别着色。

**轮询策略**：基础 2s，连续 3 次无数据后退避至最大 8s。

---

## 3.5 `GET /api/v2/trace/artifact` — 收益曲线 HTML（C5）

**作用**：按 trace + loop 返回 plotly 图表 HTML，供 iframe 加载。

| 项 | 值 |
|---|---|
| 触发 | 切到"收益曲线"Tab 时（`ResultWorkspace.vue:29` 拼 URL，iframe `src`） |
| 参数 | `id`（必填）、`loop`（可选） |
| 后端 | `app.py:758` `get_chart_artifact()`，HTML 走 bootcdn 加载 plotly.js |

**响应**：`200` text/html（iframe 直接渲染）；`304`（If-None-Match 命中）；`404`（无图表）。

> 路径越界校验：trace_dir 必须在 log_folder_path 下，否则 422。

---

## 3.6 `GET /traces/:id/sota` — SOTA 产物

**作用**：查询该 trace 的最优实验产物（假设/指标/反馈/因子代码），SOTA 弹窗展示。

| 项 | 值 |
|---|---|
| 触发 | 点击"🏆 SOTA 产物"按钮（`ResultWorkspace.vue:40`） |
| 参数 | 路径 `trace_name`；可选 `log_path` |
| 后端 | `app.py:1249` `get_sota()`，依次查 `__session__` → message stream |

**响应体**（`sota_query.query_sota` 结果）：
```json
{
  "sota_loop_id": 3,
  "sota_hypothesis": { "hypothesis": "...", "concise_reason": "..." },
  "sota_metrics": { "IC": 0.05, "1day.excess_return_with_cost.annualized_return": 0.2 },
  "sota_feedback": { "decision": true, "reason": "..." },
  "sota_factors": [{ "name": "...", "description": "...", "code": "..." }]
}
```
失败：`404 { "error": "Trace not found", "hint": "..." }`。

---

## 3.7 `POST /upload` — 新建任务

**作用**：提交任务参数与文件，启动 RD-Agent 子进程。

| 项 | 值 |
|---|---|
| 触发 | NewTaskDialog 提交（`use-multialpha.ts:157` `createTask`） |
| Content-Type | `multipart/form-data` |

**表单字段**：`scenario`、`loops`、`description`、`model_selector`（非 lgbm 时）、`auto_mode`、`files[]`。

**响应**：`200 { "id": "Finance Data Building/xxx" }`；失败 `{ "error": "..." }`。
**后续**：`cache.delete(id)` → `loadTraceIds()` 刷新列表 → `selectTrace(id)` 跳详情。

---

## 3.8 `POST /control` — 任务控制

**作用**：停止任务。

| 项 | 值 |
|---|---|
| 触发 | 详情页"停止"按钮（`use-multialpha.ts:171` `stopCurrentTask`） |
| 请求体 | `{ "id": "...", "action": "stop" }` |

**响应**：`200`。前端立即置 `status='done'` + 停止轮询 + `ElMessage.success`。

---

## 3.9 `GET /health` — 环境健康检查

**作用**：弹窗展示后端环境配置检查项。

| 项 | 值 |
|---|---|
| 触发 | TopBar"🩺 健康检查"按钮点击（`TopBar.vue:35`） |
| 后端 | `app.py:1065` |

**响应体** `HealthCheck`：
```json
{
  "overall": "pass",              // pass | issues
  "checks": [{ "name": "...", "icon": "🟢", "status": "pass", "detail": "..." }]
}
```

---

# 第四部分·实现索引（代码地图）

## 4.1 前端关键文件

### 入口与装配
| 文件 | 行 | 作用 |
|---|---|---|
| `web/multialpha.html` | 14 | HTML 入口，`<script src="/src/multialpha/main.ts">` |
| `src/multialpha/main.ts` | 16 | `createApp(MultiAlphaApp).use(router).mount()` |
| `src/multialpha/router.ts` | 3 | hash 路由：`/`、`/predict`、`/tasks/:traceId` |
| `src/multialpha/MultiAlphaApp.vue` | 24 | `onMounted → loadTraceIds() → syncRoute()`；装配所有组件 |

### 数据层（核心）
| 文件 | 行 | 作用 |
|---|---|---|
| `src/multialpha/use-multialpha.ts` | 28-31 | **tasks computed**：合并两接口数据 |
| ↑ | 41-57 | `loadTraceIds()`：GET /traces + 触发 loadStatusesBatch |
| ↑ | 59-78 | `loadStatusesBatch()`：GET /traces/status + 降级逻辑 |
| ↑ | 87-108 | `poll()`：5s 轮询 POST /trace（增量） |
| ↑ | 110-125 | `requestInitial()`：首次拉 trace + LRU 缓存 |
| ↑ | 127-150 | `selectTrace()`：进入详情主流程 |
| `src/multialpha/trace-model.ts` | 7-13 | `deriveTraceStatus()`：消息推导状态 |
| ↑ | 23-68 | `buildTraceView()`：**单遍扫描**消息→ViewModel（C7） |
| `src/multialpha/types.ts` | — | 所有类型定义（TraceTask/TraceViewModel/...） |

### 服务层
| 文件 | 行 | 作用 |
|---|---|---|
| `src/services/rdagent-api.ts` | 17-25 | `parseResponse` + `ApiError` |
| ↑ | 27 | `fetchTraceIds()` → GET /traces |
| ↑ | 39-40 | `fetchTraceStatuses()` → GET /traces/status |
| ↑ | 41 | `fetchTrace()` → POST /trace |
| ↑ | 42 | `uploadTask()` → POST /upload |
| ↑ | 43 | `controlTask()` → POST /control |
| ↑ | 45 | `fetchSota()` → GET /traces/:id/sota |
| ↑ | 47 | `fetchHealth()` → GET /health |
| ↑ | 66-98 | `fetchStdoutRange()` → GET /stdout (Range) |
| `src/multialpha/api.ts` | — | re-export 服务层（多组件统一入口） |

### 首页组件
| 文件 | 消费数据 | 渲染职责 |
|---|---|---|
| `components/TopBar.vue` | listLoading | 顶栏：刷新/健康检查/新建 |
| `components/TaskSidebar.vue` | tasks | **左侧任务列表**（筛选/状态点/场景） |
| `components/LandingTerminal.vue` | tasks | **首屏**（hero 卡 + ticker + 入口 + 架构展示） |

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

## 4.2 后端关键路由

| 路由 | 方法 | 文件:行 | 实现函数 |
|---|---|---|---|
| `/traces` | GET | `app.py:879` | `list_traces()` 扫目录 |
| `/traces/status` | GET | `app.py:887` | `list_trace_statuses()` 读内存 |
| `/trace` | POST | `app.py:803` | `update_trace()` cursor 增量 |
| `/stdout` | GET | `app.py:861` | `download_stdout_file()` Range |
| `/api/v2/trace/artifact` | GET | `app.py:758` | `get_chart_artifact()` C5 |
| `/traces/<path>/sota` | GET | `app.py:1249` | `get_sota()` |
| `/upload` | POST | `app.py:902` | `upload_file()` 启动子进程 |
| `/control` | POST | `app.py:1201` | 任务控制 |
| `/health` | GET | `app.py:1065` | 环境检查 |
| `/` | GET | `app.py:1456` | `index()` serve index.html |
| `/<path:fn>` | GET | `app.py:1463` | `server_static_files()` 静态兜底 |

## 4.3 构建

| 命令 | 作用 |
|---|---|
| `npm run dev` | vite 开发（:8080，proxy 到 :19899） |
| `npm run build` | 产出到 `web/dist` |
| `npm run build:flask` | 产出到 `git_ignore_folder/static`（Flask 服务目录） |

> ⚠️ Flask 实际服务 `git_ignore_folder/static`（`build:flask` 产物），非 `web/dist`。hash 文件名随构建变化。
