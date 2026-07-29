# 首页（`#/`）

> 路由：`multialpha-home` · 组件：`LandingTerminal` + `TaskSidebar` + `TopBar`
> 本页覆盖：任务列表、首屏仪表盘、任务入口、顶栏操作

---

## 1. 功能需求（PRD）

### 1.1 任务总览
- **F1.1.1** 左侧任务列表展示所有历史与进行中任务，按场景分类（因子挖掘 / 研报因子提取 / 量化全流程 / 模型实现）
- **F1.1.2** 每条任务显示：任务名、场景标签、**实时状态**（运行中 / 已完成 / 异常 / 待查看）
- **F1.1.3** 支持按场景下拉筛选、按状态（全部 / 完成 / 运行中）chip 筛选
- **F1.1.4** 列表超过 10 条时分页，点击"加载更多"每次 +10
- **F1.1.5** 点击任务跳转详情页

### 1.2 首屏仪表盘
- **F1.2.1** Hero 统计卡：TASKS 总数、已完成数、运行中数
- **F1.2.2** Ticker 滚动条：前 8 条任务名 + 状态图标（✓/▶/○）
- **F1.2.3** 实时时钟（每秒刷新）

### 1.3 任务入口
- **F1.3.1** 文字描述建任务（可用）→ 见 [新建任务文档](create-task.md)
- **F1.3.2** 研报 PDF 因子提取（可用）
- **F1.3.3** 因子迭代优化（可用）
- **F1.3.4** K 线图形分析（即将上线，禁用）
- **F1.3.5** 交割单分析（即将上线，禁用）
- **F1.3.6** 查看历史任务（聚焦左侧列表）

### 1.4 顶栏操作
- **F1.4.1** "刷新任务"按钮：重新拉取列表
- **F1.4.2** "健康检查"按钮：弹窗显示环境检查项
- **F1.4.3** 列表加载失败时显示错误 + "重新加载"

---

## 2. 技术方案

### 2.1 数据流

```
onMounted(MultiAlphaApp)
  │
  ▼
loadTraceIds()                          [串行]
  ├─ GET /traces          → traceIds[]
  │    失败 → listError = msg → TaskSidebar 显示错误 + 重试
  │    成功 ↓
  └─ loadStatusesBatch()
       ├─ GET /traces/status → statuses{} (C1 批量端点)
       │    失败 → 静默，状态保持 idle，列表仍展示（无降级）
       └─ 合并 → tasks computed → 下发 TaskSidebar + LandingTerminal
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

### 2.2 首页请求
首页加载固定发起 **2 个 API 请求**（`/traces` + `/traces/status`），无轮询、无 SSE，首屏渲染完成后页面静止。

> 降级路径（`/traces/status` 失败时逐个 `/trace` 推导状态）已在 commit `45f6bbd0` 删除。

---

## 3. 接口契约

### 3.1 `GET /traces` — 任务 ID 清单

| 项 | 值 |
|---|---|
| 触发 | `use-multialpha.ts:45` `loadTraceIds()` |
| 请求 | 无参数 |
| 后端 | `app.py:879` `list_traces()` 扫描日志目录 |

**响应体** `string[]`：
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

### 3.2 `GET /traces/status` — 批量状态快照（C1）

| 项 | 值 |
|---|---|
| 触发 | `use-multialpha.ts:53` `loadStatusesBatch()` ← `/traces` 成功后 |
| 请求 | 无参数 |
| 后端 | `app.py:887` `list_trace_statuses()` 读内存 `trace_states`，出口经 `_resolve_trace_status` 校正 |

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

**字段 → 渲染映射**：

| 字段 | 组件 | 渲染位置 | UI 表现 |
|---|---|---|---|
| `status` | TaskSidebar:17 | `.status-dot` | 状态点颜色（running蓝/done绿/error红/idle无） |
| `status` | TaskSidebar:18 | `.task-meta` | 转中文（运行中/已完成/异常/待查看） |
| `status` | TaskSidebar:9,34 | 筛选 chips | 全部/完成/运行中 |
| `status` | LandingTerminal:14 | ticker 图标 | done✓/running▶/其他○ |
| `status` 聚合 | LandingTerminal:35 | hero 卡副标题 | doneCount + runningCount |

**失败处理**：静默，状态保持 idle，列表仍展示。

> 状态判断逻辑见 [TRACE_STATUS_FIX](../design/TRACE_STATUS_FIX.md)：catalog 判 running 时检查进程存活，已死/不存在则判 error。

---

### 3.3 `GET /health` — 环境健康检查

| 项 | 值 |
|---|---|
| 触发 | TopBar"🩺 健康检查"按钮点击（`TopBar.vue:35`） |
| 后端 | `app.py:1065` |

**响应体** `HealthCheck`：
```json
{
  "overall": "pass",
  "checks": [{ "name": "...", "icon": "🟢", "status": "pass", "detail": "..." }]
}
```

---

## 4. 实现索引

### 首页组件
| 文件 | 消费数据 | 渲染职责 |
|---|---|---|
| `components/TopBar.vue` | listLoading | 顶栏：刷新/健康检查/新建 |
| `components/TaskSidebar.vue` | tasks | **左侧任务列表**（筛选/状态点/场景） |
| `components/LandingTerminal.vue` | tasks | **首屏**（hero 卡 + ticker + 入口 + 架构展示） |

### 数据层关键位置
| 文件:行 | 作用 |
|---|---|
| `use-multialpha.ts:28-31` | tasks computed（合并两接口数据） |
| `use-multialpha.ts:41-57` | `loadTraceIds()`：GET /traces + 触发 loadStatusesBatch |
| `use-multialpha.ts:59-69` | `loadStatusesBatch()`：GET /traces/status（失败静默） |

### 后端路由
| 路由 | 方法 | 文件:行 | 实现函数 |
|---|---|---|---|
| `/traces` | GET | `app.py:879` | `list_traces()` 扫目录 |
| `/traces/status` | GET | `app.py:887` | `list_trace_statuses()`（经 `_resolve_trace_status` 校正） |
| `/health` | GET | `app.py:1065` | 环境检查 |
