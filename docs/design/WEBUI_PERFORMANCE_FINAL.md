# webUI 性能优化最终设计

> 状态：**最终实施依据**（2026-07-26 对抗审查收敛后，合并原始设计 + 三轮审查 + 性能审计的有用信息）
> 适用：`/home/zxh/projects/1.multialphaV/RD-Agent` 的 `web/` 前端 + `rdagent/log/server/` Flask 后端
>
> 本文档是 webUI 性能优化的**唯一设计文档**，已合并以下来源的有用信息：
> - 第一性原理分析（三个分离）
> - 对原始架构设计的对抗式审查（4 处过度设计裁决）
> - 三轮多 Agent 审查（framework/reliability/compatibility，结论已吸收到 §1）
> - 2026-07-21 性能审计（已优化进度 + 后续优化项，已吸收到 §4.1 和 §9）
>
> 维护约定：任一改造点（C1-C10）的实施方案、文件落点、CDN 决策变化，必须同步本文档。

---

## 目录

- [0. 一句话结论](#0-一句话结论)
- [1. 对抗审查裁决（与原始设计的分歧）](#1-对抗审查裁决与原始设计的分歧)
- [2. 关键名词与动作释义](#2-关键名词与动作释义)
- [3. 核心原理：三个分离](#3-核心原理三个分离)
- [4. 量化基线（实测）](#4-量化基线实测)
- [5. 改造点清单（C1-C10）](#5-改造点清单c1-c10)
- [6. CDN 决策（chart 加载方式）](#6-cdn-决策chart-加载方式)
- [7. 阶段编排与预期收益](#7-阶段编排与预期收益)
- [8. 涉及文件清单](#8-涉及文件清单)
- [9. 明确不做](#9-明确不做)
- [10. 验证策略](#10-验证策略)

---

## 0. 一句话结论

**卡顿根因不是某个组件慢，而是展示链路把"完整 trace"当作任务目录、状态源、详情数据、重型产物的共同载体**——每次读都付出全量重放成本。优化方向是**三个分离**（事件流 vs 读模型、元数据 vs 产物、索引 vs 对象）+ 前端增量物化，共 10 个改造点（C1-C10），分 P0/P1/P2 三阶段落地。

---

## 1. 对抗审查裁决

> 背景：本项目曾有一份 873 行的原始架构设计（已合并到本文档并删除），经三轮多 Agent 审查（framework/reliability/compatibility，全 APPROVE）。本节是对该原始设计的对抗式复审裁决——架构方向一致，但存在 4 处过度设计，已砍掉或后置。

原始设计经对抗式审查 + 代码实证核查，结论：

### 1.1 架构方向：一致 ✅

原始设计的"数据边界是根因，非传输通道"与第一性原理分析**本质同源**。三个分离被全覆盖，且原始设计补充了第一性原理遗漏的真实增量：

| 第一性原理遗漏点 | 原始设计的补充 | 价值 |
|---|---|---|
| v1/v2 兼容矩阵 + capability 探测 | §7.4 + §10.1 | 迁移期新旧前后端兼容，必要 |
| 幽灵 task 隔离 | §6.4 第2点 | `_get_or_create_task` 隐式创建是真实 bug，必要 |
| catalog 历史状态来源（interrupted 语义） | §6.1 状态来源优先级 | 不伪造 END，必要 |
| LRU 按字节而非条数 | §6.2 + §8.3 | 含 chart 的旧 trace 按条数会爆内存，必要 |

### 1.2 四处过度设计：砍掉或后置 ⚠️

原始设计存在 4 处系统性过度设计，把它们放进"性能优化"会拖垮交付。经代码实证确认：

| 编号 | 过度设计 | 裁决 | 代码证据 |
|---|---|---|---|
| **OD-1** | Logger fan-out source identity 两阶段提交（改 `log_object`/`truncate_storages` 协议，FileStorage 先返回 Path 再传 source_ref 给 WebStorage） | **砍掉，改读侧 projection** | [`logger.py:132-136`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/logger.py) 当前 `log_object` 是无协调的循环调用；chart 按需加载在 `/receive` 入口 + artifact 端点（C4/C5）即可完成，不碰 Logger 核心抽象 |
| **OD-2** | stream epoch sidecar 子系统（隐藏 sidecar + UUID epoch + reset 自愈 + legacy 文件指纹） | **后置**为独立正确性任务 | truncate 在本系统低频（只 RDLoop 循环重置触发），与性能零相关；保留 cursor 越界 `reset_required` 即可 |
| **OD-3** | task state machine 健壮性集（6 状态 + bounded kill 链 + spawn + env 隔离） | **拆分**：最小状态机保留（C10），健壮性集独立排期 | [`app.py:81`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) spawn 与"消除 import 税"矛盾（spawn 不继承父进程内存，每子进程重新 import）；且 `self.process` 不可 pickle，bound-method target 在 spawn 下不可用 |
| **OD-4** | Gunicorn 生产编排（单 worker gthread + worker hook + SIGTERM drain + PID 检测） | **后置** | 完成定义只有 4 条性能目标，进程编排不应阻塞交付；当前 `app.run` 单机开发场景够用 |

### 1.3 "CLOSED" 语义提醒

三份审查报告（framework/reliability/compatibility，全 APPROVE）的"CLOSED"**全部指设计文档已修订**，零行 v2 代码被验证过。审查报告自陈"不代表尚未编写的实现已经通过代码或生产验收"。本最终方案的改造点清单（§5）才是可执行依据。

---

## 2. 关键名词与动作释义

| 名词 | 释义 | 当前实现位置 |
|---|---|---|
| **事件流** | rdagent 子进程产生的 append-only 消息序列，是系统真相 | `task.messages`（[`app.py:176`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py)）+ pkl 文件 |
| **读模型** | 为查询优化的物化视图（状态/摘要），由事件流投影而来 | 当前无（性能问题根因） |
| **catalog** | 轻量任务目录索引，含 id/status/loops/created_at/updated_at/has_chart，不含消息正文；`created_at` 用于列表排序 | 本方案 C1 新增 |
| **artifact** | 重产物（chart HTML），独立端点按需加载，不进消息流 | 本方案 C4/C5 新增 |
| **descriptor** | artifact 的轻量指针（`{loop_id, available, artifact_id}`，<200 字节），替代 5MB chart_html | 本方案 C4 新增 |
| **幽灵 task** | `_get_or_create_task` 在 id 不存在时隐式创建的无 process 壳 task，污染 registry | [`app.py:218-232`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) 当前 bug，C10 修复 |
| **stream epoch** | 序列版本号，truncate/replace 时变化（用于检测 cursor 错位） | 本方案 P3 后置 |
| **chart_html** | `plotly.io.to_html()` 生成的完整 HTML，含内联 plotly.js（~2.7MB），单条约 5MB | [`ui/storage.py:223`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/storage.py) |
| **chart_ref / chartRef** | chart 的轻量引用字段，替代前端 `chartHtml` 字段 | 本方案 C6 新增 |
| **LRU 驱逐** | 内存超限时淘汰最久未访问的 trace（`is_alive` 的运行任务不驱逐） | 本方案 C3 新增 |
| **三个分离** | 事件流 vs 读模型 / 元数据 vs 产物 / 索引 vs 对象，本方案的核心原理 | §3 |
| **CDN 加载** | chart HTML 通过 `<script src=cdn>` 加载 plotly.js，而非内联 2.7MB | 本方案 §6（bootcdn） |

---

## 3. 核心原理：三个分离

### 分离 1：事件流 vs 读模型

**原理**：列表/状态查询不该走事件流。事件流是 append-only 事实记录，读模型是为查询优化的物化视图，必须分离。

**当前违背**：前端为算"每个 trace 是什么状态"，拉取整个事件流（`all:true`）只为读最后几条消息的 tag → 13 trace × 全量 = ~39MB 传输。

**改造**：C1（后端 catalog 状态投影）+ C2（前端批量状态查询）。

### 分离 2：元数据 vs 产物

**原理**：异构载荷（元数据 vs 大产物）应走不同通道。元数据高频小体积，产物低频大体积，混在一起会导致取元数据时拖上全部产物。

**当前违背**：5MB chart_html 与 200 字节 token_cost 消息混在同一 `task.messages` 数组、同一 `/trace` 响应 → chart 占载荷 99%。

**改造**：C4（chart 读侧分离）+ C5（artifact 端点）+ C6（前端 iframe src 懒加载）+ §6 CDN 决策。

### 分离 3：索引 vs 对象

**原理**：系统真相应存成可索引、可选择性读取的格式。存成需整体反序列化的格式（pickle 整对象图）会丧失"只读 tag"或"只读最新"的能力。

**当前违背**：启动时 `_load_existing_traces` 必须把全部 pkl 反序列化进内存才能服务任何请求 → 0.66s 启动 + 39MB 常驻，随 trace 数线性增长。

**改造**：C3（按需加载 + LRU 驱逐）+ C10（拒绝幽灵 task，配合 C3）。

### 前端增量物化

**原理**：前端应维护物化视图，poll 时增量更新而非全量重放。

**当前违背**：`buildTraceView` 每次 `messages.push` 都全量重解析（3 遍扫描 + 6 次反向 latest）+ 8 子组件全重渲染。

**改造**：C7（合并扫描）+ C8（shallowRef + v-memo）+ C9（消除组件内 reverse 扫描）。

---

## 4. 量化基线（实测）

> 数据来源：2026-07-25 本地 13 个 trace 实测。

| 指标 | 实测值 |
|---|---|
| 首页后台状态回填潜在总 JSON | **39.01 MB**（13 trace × 全量） |
| `plain-transformation` 完整 trace | **20.47 MB（HTTP）**，93 条消息 |
| 单张 chart_html | **约 4.75 MB**（含 2.7MB 内联 plotly.js） |
| `plain-transformation` 图表份数 | 4（4-20MB/trace） |
| 13 trace 历史反序列化 + JSON 构造 | **约 4.9 s**（冷启动实测） |
| chart pkl 占磁盘 | ~165 KB（plotly.io.to_html 膨胀 118 倍） |
| 715 pkl 总磁盘 | 13 MB |
| pkl 文件名格式 | `{tag}.{pid_chain}.{ts}.pkl`（tag 在文件名可读） |

### 4.1 已完成的基线优化（2026-07-21 审计轮，纳入本文档为前置基线）

> 以下 7 项在本轮架构优化之前已修复，是本文档量化基线测得时的代码状态。C1-C10 在此基础上继续优化。

| 编号 | 问题 | 状态 | commit |
|---|---|---|---|
| P0-1 | `/trace` 的 `random.randint(1,10)` 随机返回 + pointer 按 `user_ip` 划分游标（NAT 用户丢消息的正确性 bug） | ✅ 已修（改全量返回增量 + 前端传 cursor） | `bdd45209` |
| P1-3 | `buildTraceView` 的 `latest()` 每次 `[...messages].reverse().find()` + `loopMetrics` 嵌套循环（200msg×10loop=2000 次比较） | ✅ 已修（latest 改线性扫描） | `117081a1` |
| P1-4 | `messages.value = [...messages.value, ...updates]` 全数组重建（触发所有 computed 失效） | ✅ 已修（改 `push`） | `bdd45209` |
| P1-5 | `AgentFlow.vue` 5 个 `latest(tag)` 重复扫描（5 × 数组复制+反转） | ✅ 间接优化 | `117081a1` |
| P1-6 | iframe plotly chart 无 hash 约束，每次 poll 可能重建（50-150ms 重绘） | ✅ 已修（加 `stableChartHtml` 长度比较） | `117081a1` |
| P2-7 | LogConsole + use-multiα1pha 双轮询无合并（42 req/min） | ✅ 已修（LogConsole 退避 2s→8s） | `117081a1` |
| P2-12 | LRU 缓存上限 2 太小 | ✅ 已修（提到 5） | `bdd45209` |

**结论**：消息条数不大，主要放大项是多轮图表 HTML。优化数组循环只能降次要 CPU 开销，不能解决首页和详情的数据体积问题。

---

## 5. 改造点清单（C1-C10）

每个改造点含：**当前实现（文件:行号）→ 目标实现 → 影响范围**。

### 5.1 P0 阻断级

#### C1 — 后端 catalog 状态投影 + `/traces/status` 端点

- **分离维度**：分离 1（事件流 vs 读模型）
- **当前**：[`app.py:477-483`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) `/traces` 只返回 id 列表无状态；[`app.py:176`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) `rdagent_processes` 是唯一 task 注册表无独立投影；`/receive`（L597-614）只 append 不维护状态摘要
- **目标**：
  1. 新增模块级 `trace_states: dict[str, TraceStateSnapshot]`，结构 `{id, status, loops:set, created_at, updated_at, has_chart:bool}`
     - `created_at`：trace 创建时间，用于前端列表排序（默认 `created_at DESC, id ASC`）
     - `updated_at`：最后消息时间，用于展示"最近更新"
  2. 新增 `_update_trace_state(trace_id, msg)` 投影函数（复用 `deriveTraceStatus` 的 tag 判定：END/feedback.metric+feedback.hypothesis_feedback=done，error tag=error，否则 running）。每次调用同步更新 `updated_at`；`created_at` 在首次初始化时设置后不再变
  3. **`created_at` 推导方式**（两种来源）：
     - **运行态 trace**（`/upload` 创建）：初始化 `trace_states[id] = {status:running, created_at: <当前时间>}`（L174），精确到秒
     - **历史 trace**（启动 catalog 索引时）：从 trace 目录下的 pkl 文件名时间戳推导——pkl 文件名格式 `{tag}.{pid_chain}.{YYYY-MM-DD_HH-MM-SS-FFFFFF}.pkl`，取该 trace 目录下**最早的 pkl 时间戳**作为 `created_at`（实测样例：`plain-transformation` 最早 pkl `2026-07-20_15-07-56-045827.pkl` → `created_at = 2026-07-20T15:07:56Z`）。此推导在 C3 的 catalog 索引阶段完成（扫文件名，不反序列化对象，与 C3 共用索引逻辑）
  4. `/receive` append 后调用 `_update_trace_state`
  5. `/upload` 创建任务时初始化 `trace_states[id] = {status:running, created_at:<now>}`
  6. 新增 `GET /traces/status` 返回所有状态快照（~120 字节/trace），响应按 `created_at DESC, id ASC` 排序
- **影响范围**：`server/app.py`（新增 ~40 行）；不动 FileStorage/Logger/WebStorage；v1 `/traces` 保持不变
- **验证**：`curl localhost:19899/traces/status` 返回 < 2KB JSON，含所有 trace 状态

#### C2 — 前端消除 N+1 全量拉取

- **分离维度**：分离 1
- **当前**：[`use-multialpha.ts:56-63`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/use-multialpha.ts) `loadStatusesSequentially` 对每个未缓存 trace 串行发 `fetchTrace({id, all:true, reset:true})`（L59），单次拉全量含 5MB chart，仅为算状态
- **目标**：
  1. [`rdagent-api.ts`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/services/rdagent-api.ts) 新增 `fetchTraceStatuses(signal?)` → `GET /traces/status`
  2. `use-multialpha.ts:56-63` 重写为 `loadStatusesBatch`：单次调 `fetchTraceStatuses`，循环写 `statuses.value[id]`
  3. 加 AbortSignal + generation token（参考 L113-115 `selectTrace` 已有的 generation 守卫模式）
- **影响范围**：`rdagent-api.ts`（+5 行）、`use-multialpha.ts`（重写 8 行函数）
- **验证**：浏览器 Network，首页加载从"13 个 `/trace` 串行 ~39MB"变为"1 个 `/traces/status` <2KB"
- **依赖**：C1

#### C3 — 后端按需加载 + LRU 驱逐

- **分离维度**：分离 3（索引 vs 对象）
- **当前**：[`app.py:997`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) `main()` 调 `_load_existing_traces` 同步阻塞；[`app.py:389-398`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) 全量 `pickle.load` + `_obj_to_json`，结果永久驻留；[`app.py:218-232`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) `_get_or_create_task` 只增不减
- **目标**：
  1. `_load_existing_traces`（L389-398）改为只建 catalog 索引：扫目录名 + pkl 文件名 tag（文件名含 tag，不反序列化对象），写入 `trace_states`（复用 C1 投影层），**不调 `read_trace`、不 `pickle.load`**。同时从 pkl 文件名时间戳推导 `created_at`（取该 trace 目录下最早 pkl 的时间戳，见 C1 第 3 点）和 `updated_at`（取最晚 pkl 时间戳）
  2. `_get_or_create_task`（L218-232）改为按需加载：首次访问某 trace 才 `read_trace`，加 `last_access` 时间戳
  3. 新增 `_evict_if_needed()`：`rdagent_processes` 超 `UI_MAX_INMEMORY_TRACES`（默认 20，加到 `ui/conf.py`）时驱逐最久未访问且 `process is None or not is_alive()` 的 trace
  4. `main()`（L995-998）启动只做 catalog 索引，不阻塞
- **影响范围**：`server/app.py`（~50 行改动）、`rdagent/log/ui/conf.py`（+1 字段 `max_inmemory_traces`）
- **关键约束**：`is_alive()` 为真的运行任务**永不驱逐**
- **验证**：冷启动 0.66s → <0.1s；RSS 39MB → 按需（~3MB/活动 trace）；历史 trace 首次 ~0.1s，二次即时
- **依赖**：与 C10 强耦合，必须同批改

#### C10 — 后端拒绝幽灵 task（修真实 bug）

- **分离维度**：正确性（配合 C3）
- **当前**：[`app.py:218-232`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) `_get_or_create_task` 在 id 不存在时**隐式创建** `RDAgentTask(create_process=False)` 壳，塞进 `rdagent_processes`。`/receive`、`/trace`、`/sota` 共用此入口——历史 trace id 变成永久驻留的幽灵 task，破坏 C3 的 LRU 驱逐
- **目标**：
  1. 拆分 `_get_or_create_task` 为两个函数：
     - `_get_running_task(trace_id)` —— 只读，返回运行中 task 或 None
     - `_get_or_load_task(trace_id)` —— 显式加载（首次访问历史 trace 时调，走 C3 按需 read_trace）
  2. `/receive`（L608/611）、`/trace`（L413）改用 `_get_running_task`；历史消息走 v2 catalog 不进 `rdagent_processes`
  3. `/sota`（L776-824）历史分支改为消费临时 snapshot，不写回 registry
- **影响范围**：`server/app.py`（拆分 1 函数为 2，改 4 个调用点，~30 行）
- **验证**：访问历史 trace 后 `len(rdagent_processes)` 不增长；运行任务仍能正常 `/receive`

### 5.2 P1 核心收益（chart 产物分离）

#### C4 — 后端 chart 读侧分离（不改 Logger）

- **分离维度**：分离 2（元数据 vs 产物）
- **当前**：[`ui/storage.py:212-225`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/storage.py) `Quantitative Backtesting Chart` 分支调 `plotly.io.to_html(report_figure(obj))`（L223）生成 ~5MB HTML 塞进 `content.chart_html`；这条 5MB 消息经 `/receive` 进入 `task.messages`，每次 `/trace` 全量响应重传
- **目标**（**读侧 projection，不动 Logger**）：
  1. `server/app.py` 新增 `/receive` 预处理：收到 `tag == "feedback.return_chart"` 消息时，**不 append 原 5MB content**，而是从消息体取 `loop_id`/`timestamp`，append 轻量 descriptor `{loop_id, available:true, artifact_id}`（<200 字节）
  2. v1 `/trace` 响应保留原 `chart_html` 字段（兼容旧前端）—— 由 adapter 在出口处按需填充：检测到 descriptor 就调 C5 的 artifact 生成函数恢复 HTML，响应结束后释放
  3. `ui/storage.py:223` 的 `to_html` 调用**不在实时链路触发**（实时只发 descriptor；函数保留供 artifact 端点调用）
- **影响范围**：`server/app.py`（`/receive` 预处理 + v1 adapter，~40 行）、`ui/storage.py:212-225`（chart 分支标注"实时链路跳过 to_html"）；**不动 `logger.py`、不动 `storage.py`（FileStorage）、不动 `truncate_storages`**
- **对抗审查裁决**：OD-1 的替代方案。原始设计要求改 Logger 做两阶段提交，裁决为过度设计；读侧 projection 完成同样目标
- **验证**：实时跑 1 loop，`task.messages` 里 return_chart 消息 <200 字节，无 5MB chart_html
- **依赖**：C1 的 `trace_states` 可复用

#### C5 — 后端 artifact 端点（bootcdn CDN 版本）

- **分离维度**：分离 2
- **当前**：无独立 chart 端点，chart 只能从 `/trace` 响应的 `chart_html` 字段取
- **目标**：
  1. `server/app.py` 新增 `GET /api/v2/trace/artifact?id=<trace_id>&loop=<loop_id>`
  2. 实现：按 trace_id + loop_id 在 FileStorage 目录 glob `Loop_N/running/Quantitative Backtesting Chart/*.pkl`，取时间戳最新一份（tie-breaker：规范化相对路径字典序），`pickle.load` → `report_figure(df)` → `plotly.io.to_html(fig, include_plotlyjs=False)` + 注入 `<script src="https://cdn.bootcdn.net/ajax/libs/plotly.js/<版本>/plotly.min.js">`（版本对齐 multialphav env 的 Python plotly，实施第一步 `pip show plotly` 确认）
  3. HTML 落盘到 `UI_TRACE_ARTIFACT_CACHE_PATH`（新配置，加 `ui/conf.py`），后续请求 `send_file`，带 `ETag`（SHA-256 of HTML bytes）+ `Cache-Control: private, max-age=0, must-revalidate`
  4. 支持 `If-None-Match → 304`
  5. 路径越界校验（复用 [`app.py:235`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) `_resolve_stdout_path` 的 `commonpath` 模式）
- **影响范围**：`server/app.py`（新增路由 + 生成函数，~50 行）、`rdagent/log/ui/conf.py`（+2 字段：`trace_artifact_cache_path`、`trace_artifact_cache_max_mb`）
- **CDN 细节**：见 §6
- **验证**：`curl /api/v2/trace/artifact?id=...&loop=0` 返回 HTML（~230KB，非 5MB），二次请求带 ETag 返回 304；磁盘 `__charts__/` 生成文件
- **依赖**：C4

#### C6 — 前端 iframe src 懒加载

- **分离维度**：分离 2
- **当前**：[`ResultWorkspace.vue:10`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/components/ResultWorkspace.vue) `<iframe :srcdoc="stableChartHtml" sandbox="allow-scripts"/>` 把 5MB HTML 字符串塞进 srcdoc；L26 `stableChartHtml` watch 比较长度存 5MB ref；[`trace-model.ts:47`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/trace-model.ts) `chartHtml` 从消息提取完整 HTML；[`MultiAlphaApp.vue:11`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/MultiAlphaApp.vue) 传 `:chart-html`
- **目标**：
  1. `trace-model.ts:47` `chartHtml` 字段改 `chartRef`：从 descriptor 取 `{loop_id, available, artifact_id}`，不取 `chart_html`
  2. `ResultWorkspace.vue:10` 改 `<iframe :src="chartUrl" sandbox="allow-scripts"/>`，`chartUrl` 由 `trace_id + chartRef.loop_id` 拼成 `/api/v2/trace/artifact?id=...&loop=...`
  3. `ResultWorkspace.vue:26` 删除 `stableChartHtml` 的 5MB ref 与 length watch，改为 `chartUrl` computed
  4. `MultiAlphaApp.vue:11` 改 `:chart-ref="view.chartRef"`
  5. `types.ts` `TraceViewModel` 加 `chartRef` 字段
- **影响范围**：`ResultWorkspace.vue`（~15 行）、`trace-model.ts:47`（1 行）、`MultiAlphaApp.vue:11`（1 行）、`types.ts`（+1 字段）
- **sandbox 约束**：`sandbox="allow-scripts"`（**不加 allow-same-origin**）；artifact HTML 继续内联数据，plotly.js 走 bootcdn CDN 跨域加载（无 CORS 矛盾，见 §6）
- **验证**：浏览器 Network，切换到"收益曲线"tab 才发 artifact 请求；不切 tab 时 0 请求；iframe 正常渲染图表
- **依赖**：C5

### 5.3 P2 增量优化（前端重算）

#### C7 — buildTraceView 合并扫描

- **分离维度**：前端增量物化
- **当前**（[`trace-model.ts:24-47`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/trace-model.ts)）：L25 `messages.filter` 第 1 遍；L26 `scoped.filter` 第 2 遍；L27-29 连续 6 次 `latest(scoped, tag)`，`latest`（L6）是反向线性扫描，最坏 6 遍；L33-41 显式单遍（遍历 `messages` 非 `scoped`，selectedLoop 收窄时仍扫全量）；`parseFactors`（L16）等每次重算都重复 `JSON.parse`
- **目标**：
  1. L27-29 的 6 次 `latest` 合并到 L33-41 主循环：单遍正向扫描时记录各 tag 最后一条消息到 `Map<tag, msg>`
  2. `deriveTraceStatus`（L8-14）的 hasEnd/hasError 判定并入同一遍
  3. `parseFactors`/`parseCodes`/`parseMetrics` 内部对 `objectValue`（含 `JSON.parse`）结果按字符串引用 memoize（WeakMap）
- **影响范围**：`trace-model.ts` 单文件重构（~30 行，纯函数易测）
- **验证**：单测——同样输入消息，新旧 buildTraceView 输出深相等；100 条消息执行时间 ~3ms → <1ms

#### C8 — shallowRef + v-memo

- **分离维度**：前端增量物化
- **当前**：[`use-multialpha.ts:32`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/use-multialpha.ts) `view = computed(() => buildTraceView(messages.value, ...))`，`messages.value` 是深响应式 ref，每次 push 触发 computed；[`MultiAlphaApp.vue:11`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/MultiAlphaApp.vue) 8 子组件全部依赖 `view.*`，view 引用每次轮询都变 → 全部重渲染
- **目标**：
  1. `use-multialpha.ts:18` `messages` 改 `shallowRef<TraceMessage[]>`（DTO 不需深代理）
  2. `use-multialpha.ts:32` view 用 `shallowRef` + 手动触发（poll 有新增时调 `view.value = buildTraceView(...)`，selectedLoop 切换时才全量重算）
  3. `MultiAlphaApp.vue:11` 对 `AgentFlow`/`ResultWorkspace`/`TokenDashboard` 加 `v-memo="[view.factors, view.codes, view.chartRef, view.metricValues, view.feedback]"`
- **影响范围**：`use-multialpha.ts`（~10 行）、`MultiAlphaApp.vue:11`（3 个 v-memo）
- **验证**：Vue DevTools Performance，轮询周期内重渲染组件数 8 → 1-2 个

#### C9 — 消除组件内 reverse 扫描

- **分离维度**：前端增量物化
- **当前**：`AgentFlow.vue` computed 内 5 次 `[...props.messages].reverse().find(...)`（每次复制整个数组并反转）；`UserInteractionDialog.vue:166-182` `deep:true` watch 整个 messages 树
- **目标**：
  1. `AgentFlow.vue` 改为接收 `view.factors`/`view.codes`/`view.metricValues` 等已派生字段（不再接收 `messages` 自行扫描）
  2. `UserInteractionDialog.vue` 改为接收 `pendingInteraction` 单条 + `hasEnd` 布尔（从 view 取），移除 `deep:true` watch
- **影响范围**：`AgentFlow.vue`、`UserInteractionDialog.vue`（各改 props 契约，~20 行）
- **验证**：组件 props 不再含 `messages[]`；deep watcher 数 = 0

### 5.4 P3 后置项（独立排期）

| 项 | 说明 | 为什么后置 |
|---|---|---|
| stream epoch sidecar 子系统 | OD-2 | truncate 低频，与性能零相关；保留 cursor 越界 `reset_required` 即可 |
| task state machine 健壮性集 | OD-3 健壮性部分 | 性能只需最小状态机（C10 已含）；spawn 与消除 import 税矛盾 |
| Gunicorn 生产编排 | OD-4 | 单机开发场景 `app.run` 够用；生产部署是独立运维决策 |
| BroadcastChannel 多标签页 | 原始设计 §8.5 Phase 4 | 当前单用户开发，后置 |
| 新建任务 8s import 税 | Python 生态固有成本 | preloader 方案复杂度高，投入产出比低 |

---

## 6. CDN 决策（chart 加载方式）

### 6.1 选型

经对比，选定 **bootcdn 国内 CDN + 对齐 Python plotly 版本**：

| 方案 | 单 chart 体积 | 离线可用 | sandbox 约束 | 国内延迟 | 决策 |
|---|---|---|---|---|---|
| 现状（内联 plotly.js） | ~5MB（2.7MB JS 内联） | ✅ | 无 | 首次快 | 否决（体积过大） |
| 官方 CDN（cdn.plot.ly） | ~230KB | ❌ 需外网 | 需 CORS | 国内不稳定 | 否决 |
| **bootcdn 国内 CDN** | **~230KB** | ❌ 需外网 | 需 CORS | **国内 ~50ms** | **采用** |
| 自托管（Flask static） | ~230KB | ✅ | 无（同源） | 首次 ~200ms | 备选（离线场景） |

### 6.2 实现要点

- chart HTML 生成：`plotly.io.to_html(fig, include_plotlyjs=False)` + 注入 `<script src="https://cdn.bootcdn.net/ajax/libs/plotly.js/<版本>/plotly.min.js">`
- 版本对齐：实施第一步 `/home/zxh/miniconda3/envs/multialphav/bin/pip show plotly` 取精确版本号，拼 bootcdn URL
- 单 chart 响应：5MB → ~230KB（仅数据 + div + script 标签）
- N 个 chart 共享一份 plotly.js（浏览器缓存，仅首次拉取）

### 6.3 sandbox 与 CDN 兼容性

- iframe `sandbox="allow-scripts"`（**不加 allow-same-origin**）下，iframe 处于 opaque origin（null origin）
- `<script src="https://cdn...">` 加载外部脚本**不需要 same-origin**——浏览器对 `<script src>` 跨域资源默认允许，只有 cookie/CORS 预检请求才受限
- bootcdn 返回 `Access-Control-Allow-Origin: *`，满足跨域加载
- **矛盾不存在**的前提：chart 数据内联在 HTML（不跨域 fetch），只有 plotly.js 库走 CDN

### 6.4 离线 trade-off

bootcdn 不可达时 chart 渲染失败（显示空白）。可接受——内网机器首次需外网加载 plotly.js，之后浏览器缓存。若未来需完全离线，切"自托管"备选方案（放 plotly.min.js 到 Flask static，改 script src 为 `/static/plotly.min.js`）。

---

## 7. 阶段编排与预期收益

### 7.1 依赖关系

```
P0（C1→C2，C3+C10 并行）→  P1（C4→C5→C6 串行）→  P2（C7/C8/C9 可并行）
```

### 7.2 各阶段收益（累积）

| 阶段 | 改造点 | 可见收益 |
|---|---|---|
| **P0a/b** | C1 + C2 | **首页 39MB → <2KB** |
| **P0c** | C3 + C10 | **冷启动 0.66s → <0.1s，内存 39MB → 按需（~3MB/trace）** |
| **P1** | C4 + C5 + C6 | **单 trace 恢复 5-20MB → <2MB（chart 走 bootcdn，单图 230KB）** |
| **P2** | C7 + C8 + C9 | **轮询重算 8 组件 → 1-2 个，buildTraceView 3遍+6反扫 → 1遍** |

每个 P0/P1 子阶段**独立可验证、独立可合入**，不需要全部完成才见效。

### 7.3 总预期收益

| 指标 | 现状 | P0 后 | P1 后 | P2 后 |
|---|---|---|---|---|
| 首页初始传输 | ~39MB | **<2KB** | <2KB | <2KB |
| 单 trace 恢复传输 | 5-20MB | 5-20MB | **<2MB** | <2MB |
| 服务端冷启动 | 0.66s+线性 | **<0.1s** | <0.1s | <0.1s |
| 服务端常驻内存 | 39MB | **按需** | 按需 | 按需 |
| 每轮轮询主线程开销 | 全量重算+8组件 | 同 | 同 | **增量+1-2组件** |

---

## 8. 涉及文件清单（共 9 文件）

### 后端（3 文件）

| 文件 | 涉及改造点 | 改动 |
|---|---|---|
| [`rdagent/log/server/app.py`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) | C1/C3/C4/C5/C10 | catalog 投影 + `/traces/status` + 按需加载 + LRU + 幽灵 task 修复 + chart 分离 + artifact 端点 |
| [`rdagent/log/ui/storage.py`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/storage.py) | C4 | chart 分支实时链路跳过 `to_html` |
| [`rdagent/log/ui/conf.py`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/conf.py) | C3/C5 | `max_inmemory_traces` + `trace_artifact_cache_path` 配置项 |

### 前端（6 文件）

| 文件 | 涉及改造点 | 改动 |
|---|---|---|
| [`web/src/services/rdagent-api.ts`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/services/rdagent-api.ts) | C2 | `fetchTraceStatuses` |
| [`web/src/multialpha/use-multialpha.ts`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/use-multialpha.ts) | C2/C8 | `loadStatusesBatch` + shallowRef |
| [`web/src/multialpha/trace-model.ts`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/trace-model.ts) | C6/C7 | `chartRef` + 合并扫描 |
| [`web/src/multialpha/MultiAlphaApp.vue`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/MultiAlphaApp.vue) | C6/C8 | prop 改名 + v-memo |
| [`web/src/multialpha/components/ResultWorkspace.vue`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/components/ResultWorkspace.vue) | C6 | iframe src 懒加载 |
| [`web/src/multialpha/components/AgentFlow.vue`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/components/AgentFlow.vue) + [`UserInteractionDialog.vue`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/components/UserInteractionDialog.vue) | C9 | props 契约改 |

---

## 9. 明确不做

| 项 | 理由 |
|---|---|
| 改 Logger `log_object`/`truncate_storages` 协议（OD-1） | 读侧 projection（C4/C5）可完成同样目标，不碰核心抽象 |
| stream epoch sidecar（OD-2） | truncate 低频，cursor 越界 `reset_required` 即可 |
| task state machine 健壮性集（OD-3） | 性能只需最小状态机（C10），健壮性集独立排期 |
| Gunicorn 生产编排（OD-4） | 单机开发场景够用，生产部署独立决策 |
| 新建任务 8s import 税 | Python 生态固有成本，preloader 复杂度高 |
| pkl 存储格式重构（pickle → JSON/parquet） | 改动面太大，pkl 绑定 rdagent 对象是上游设计；本方案让 pkl 不在热路径即可 |
| polling 改 SSE/WebSocket | 当前 5s polling 对增量场景够用，改造收益不抵风险 |
| 74% 不可见 pkl 的写盘过滤 | FileStorage 写一切是上游设计，改动影响调试能力 |
| 用 Pinia 替换 Composition API | 状态规模不需要新框架 |
| 用 Web Worker 掩盖 20MB JSON | 应先从数据契约消除无效载荷 |
| chart 切 CDN 后又改 Plotly JSON + 前端共享 runtime | 本轮保持 Plotly HTML 格式，减体积靠 CDN 加载 |
| LogConsole filtered 预计算 lowercase 缓存（AUDIT P2-9） | 当前每次过滤 5000 行 + toLowerCase，属增量优化，非架构瓶颈 |
| katex/element-plus 懒加载 + vite manualChunks（AUDIT P3-15） | 首屏资源优化，与 trace 读路径无关，独立排期 |
| Docker 并发信号量 + auto_remove（AUDIT P4-17） | 多租户资源治理，与单机性能优化无关，独立排期 |

---

## 10. 验证策略

### 10.1 每阶段验证清单

| 阶段 | 验证方式 | 通过标准 |
|---|---|---|
| P0a（C1） | `curl /traces/status` | 返回 < 2KB JSON，含所有 trace 状态 |
| P0b（C2） | 浏览器 Network 面板 | 首页加载只有 1 个 `/traces/status` 请求，无 13 个 `/trace` 串行 |
| P0c（C3+C10） | 服务端冷启动计时 + RSS 监控 + 访问历史 trace 后 `len(rdagent_processes)` | 冷启动 <0.1s；RSS 按需；幽灵 task 不创建 |
| P1（C4/C5/C6） | 浏览器 Network + 实时跑 1 loop | `/trace` 响应无 chart_html；切换 chart tab 才发 artifact 请求（~230KB） |
| P2（C7/C8/C9） | Vue DevTools Performance + 单测 | buildTraceView 输出深相等；重渲染组件 8→1-2；deep watcher=0 |

### 10.2 契约测试前置（P0 之前）

实施前先固化 v1 兼容基线（原始设计 §12 Phase 0）：
- 13 trace 基线：响应字节、反序列化时间、消息数、图表大小
- v1 `/traces`、`/trace` 兼容回归测试（确保新改造不破坏旧接口）
- 测量剖面固化（Python/Node/Chromium 版本、冷/暖缓存）

### 10.3 性能观测工具（已集成，用于优化前后对比）

> 以下两个工具已集成到代码中，在 P0/P1/P2 各阶段实施前后跑标准操作，对比指标变化。

#### 前端 web-vitals（页面加载/交互延迟）

- **库**：`web-vitals` v6.0.0（已装）
- **采集模块**：[`web/src/multialpha/vitals.ts`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/vitals.ts)，在 [`main.ts`](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/main.ts) 挂载
- **采集指标**：
  - **TTFB**（Time to First Byte）：首字节时间，反映后端响应 + 网络往返
  - **FCP**（First Contentful Paint）：首次内容绘制，反映页面加载到可见内容
  - **LCP**（Largest Contentful Paint）：最大内容绘制，反映主要内容加载完成
  - **CLS**（Cumulative Layout Shift）：累计布局偏移，反映视觉稳定性
  - **INP**（Interaction to Next Paint）：交互到下次绘制，反映交互响应性
- **输出方式**：
  - 开发期浏览器控制台彩色输出（绿=good / 黄=needs-improvement / 红=poor）
  - 写入 `localStorage["multialpha:vitals"]`（每个指标保留最近 50 次采样），便于跨阶段对比
- **启用/关闭**：开发模式（`import.meta.env.DEV`）自动开启；生产可设 `localStorage["multialpha:vitals:enable"] = "1"` 强制开启
- **使用方式**：打开浏览器 DevTools Console，执行标准操作（首页加载→切换任务→打开 chart），观察 `[WebVitals]` 输出

#### 后端 API 性能中间件（请求耗时 + 响应大小）

- **位置**：[`rdagent/log/server/app.py`](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py) 的 `@app.before_request` + `@app.after_request` 中间件（在 `app = Flask(...)` 之后）
- **记录内容**：每个 API 请求的 `方法 路径 → 状态码 耗时ms 响应大小`
- **输出方式**：server 控制台 stderr 彩色输出（绿<200ms / 黄200ms-1s / 红>1s），示例：
  ```
  [PERF] GET /traces → 200 2ms 545B
  [PERF] POST /trace → 200 1523ms 19.9MB    ← 优化前（含 chart）
  [PERF] POST /trace → 200 45ms 1.8MB       ← P1 后（chart 已分离）
  ```
- **过滤**：不记录静态资源（CSS/JS/字体/图片），只关注 API 路径
- **启用/关闭**：默认开启；设环境变量 `PERF_LOG=0` 关闭
- **使用方式**：启动 `rdagent server_ui`，观察控制台 `[PERF]` 行；或 `grep PERF server.log`

#### 标准对比操作（每阶段执行）

每个 P0/P1/P2 阶段实施前后，执行以下操作并记录指标：

| 操作 | 观察指标 | 预期变化（P0→P1→P2） |
|---|---|---|
| 首页加载 | 前端 TTFB/LCP/FCP + 后端 `/traces` 请求 | TTFB 降（首页不再全量拉 trace）；后端 `[PERF] GET /traces` + `/traces/status` 响应 <2KB |
| 切换到一个历史 trace | 后端 `/trace` 耗时 + 响应大小 | `/trace` 响应从 5-20MB → <2MB（P1 后 chart 分离） |
| 打开 chart 页签 | 后端 `/api/v2/trace/artifact` 首次耗时 | 首次 ~200-500ms（生成 HTML），二次 304 即时 |
| 等待 1 轮 poll | 前端 INP + 后端 `/trace` 增量耗时 | INP 从 >50ms → <50ms（P2 后 reducer 增量）；后端增量响应 <256KB |

---

**版本**：v1.1（2026-07-26 合并原始设计 + 三轮审查 + 性能审计为唯一文档）
**适用目录**：`/home/zxh/projects/1.multialphaV/RD-Agent`

---

## 更新来源

- 2026-07-21：性能审计（18 个问题 P0-P4 分级，7 项已优化含 commit hash，已吸收到 §4.1 和 §9）
- 2026-07-25：原始架构设计（873 行，含 catalog/lazy repository/artifact/reducer 四要素）+ 三轮多 Agent 审查（framework/reliability/compatibility，全 APPROVE，结论已吸收到 §1）
- 2026-07-26：对抗审查收敛。原始设计经对抗式审查 + 代码实证核查，架构方向一致但存在 4 处过度设计（OD-1 Logger 两阶段提交 / OD-2 epoch sidecar / OD-3 state machine 健壮性集 / OD-4 Gunicorn 编排）。本最终方案砍掉 OD-1（改读侧 projection）、后置 OD-2/OD-3/OD-4，保留 10 个改造点（C1-C10）分 P0/P1/P2 三阶段。CDN 选型 bootcdn 国内 + 对齐 Python plotly 版本。原始设计 + 三轮审查报告 + 审计报告共 5 份过程文档的有用信息已合并到本文档，原件删除。
