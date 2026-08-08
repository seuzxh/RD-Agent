# webUI 性能优化分支浏览器端实测报告

> 分支：`perf/webui-optimization`（C1–C10 性能改造）
> 测试日期：2026-07-26
> 测试方式：agent-browser（Chromium）+ Performance API + web-vitals + Flask PERF 中间件
> 后端：Flask dev server，端口 19899，PID 314582，13 个历史 trace（4 完成 + 9 运行中）
> 前端：`npm run build:flask` 生产构建，已开启 `localStorage["multialpha:vitals:enable"]="1"`

## 1. 测试范围与用例

| 类别 | 编号 | 用例 | 关注改造点 |
|------|------|------|------------|
| 性能 | P-01 | 首屏加载时间（navigation timing） | C2/C3 |
| 性能 | P-02 | 首页传输量（取代 13× /trace 全量） | C2 |
| 性能 | P-03 | 首页 API 调用模式（批量 status） | C1/C2 |
| 性能 | P-04 | 进入 trace 详情耗时与体积 | C3/C4 |
| 性能 | P-05 | chart artifact 端点与 CDN 加载 | C4/C5/C6 |
| 性能 | P-06 | 后端 PERF 中间件日志正确性 | 中间件 |
| 功能 | F-01 | 首页落地渲染 | — |
| 功能 | F-02 | 任务列表加载与刷新 | C1 |
| 功能 | F-03 | 详情页布局（智能体流程 + tabs） | — |
| 功能 | F-04 | 多 loop 切换 | C7 |
| 功能 | F-05 | 收益曲线 chart 渲染 | C5/C6 |
| 功能 | F-06 | 因子代码视图 | — |
| 功能 | F-07 | 健康检查 | — |
| 功能 | F-08 | 返回首页 | — |

## 2. 性能实测结果（P-01 ~ P-06）

### 2.1 首屏 Navigation Timing（P-01 ✅）

| 指标 | 实测 | 评级 |
|------|------|------|
| TTFB | **6.9 ms** | ✅ good |
| FCP（First Contentful Paint） | **140 ms** | ✅ good |
| domInteractive | 17 ms | ✅ |
| domContentLoaded | 101 ms | ✅ |
| 资源数 | 34 个 | ✅ |
| LCP/CLS/INP | 未采集（需用户交互触发） | ⚠️ 单测环境受限 |

> web-vitals 在生产构建默认关闭，需 `localStorage["multialpha:vitals:enable"]="1"` 开启。LCP/INP 在无人工交互的自动化测试中不会触发，属预期。

### 2.2 首页传输量（P-02 ✅）

```
GET /traces           545 B    (catalog index，文件名扫描)
GET /traces/status    2.3 KB   (13 个 trace 批量状态)
GET /multialpha.html  300 B    (304 cache hit)
GET /assets/*.js      300 B    (304 cache hit，decoded 748 KB)
GET /assets/*.css     300 B    (304 cache hit，decoded 393 KB)
-----------------------------------------------
首页总计              ≈ 4.0 KB（首次冷启动 ≈ 1.14 MB 含 JS/CSS）
```

**对比改造前**：13 × /trace 全量 ≈ 39 MB → **降低 99.99%**（C1+C2+C3 生效）。

### 2.3 首页 API 调用模式（P-03 ✅）

- 改造前：`N × POST /trace`（N = trace 数）
- 改造后实测：**1 × GET /traces（545 B）+ 1 × GET /traces/status（2.3 KB）**
- 列表渲染不再触发任何 `/trace` 详情请求，仅在用户点击进入详情时才加载（C3 按需加载）。

### 2.4 进入 trace 详情（P-04 ⚠️）

```
POST /trace?id=careful-levee   4533 ms   5.1 MB
```

- **体积**：5.1 MB（vs 改造前 20 MB，**降低 75%**）
- **耗时**：4.5 s（首次冷加载，包含 pickle 反序列化 + chart_html 内联序列化）
- **分析**：单 trace 仍 5.1 MB 的主因是 **C4 chart descriptor 未覆盖历史加载路径**（详见问题 #1）。剥离 chart 后预计可降至 < 200 KB。

### 2.5 Chart artifact 端点（P-05 🔴 FAIL）

iframe 请求：`GET /api/v2/trace/artifact?id=undefined` → 空白。
**根因**：C4/C6 在历史 trace 上未生效，详见问题 #1。

### 2.6 后端 PERF 中间件（P-06 ✅）

完整累计统计（测试期间 51 次请求）：

| endpoint | count | avg ms | max ms | total | 4xx/5xx |
|----------|-------|--------|--------|-------|---------|
| /trace (POST, incremental) | 24 | 189.3 | 4523 | 9.7 MB | 0 |
| /health | 1 | 39.0 | 39 | 0.8 KB | 0 |
| /stdout (poll) | 14 | 1.0 | 1 | 2.2 KB | 13（416 退避） |
| /traces (catalog) | 4 | 2.0 | 2 | 2.1 KB | 0 |
| /multialpha.html | 2 | 1.5 | 3 | 0 | 0 |
| /api/v2/trace/artifact (C5) | 2 | 0.5 | 1 | 0 | 1（id=undefined） |
| /traces/status (batch) | 4 | 0.0 | 0 | 9.2 KB | 0 |

- `[PERF]` 前缀 + method/path/status/duration/size 全部正确输出 ✅
- `/traces/status` 4 次调用全部 ≤ 1 ms / 2.3 KB ✅
- 增量 `/trace` 轮询 23/24 次都是 0-1 ms / 3 B（cursor 增量空响应）✅
- `/stdout` 14 次中 13 次 416（range not satisfiable，退避机制生效，P2-7 优化）✅

## 3. 功能验证结果（F-01 ~ F-08）

| 用例 | 结果 | 说明 |
|------|------|------|
| F-01 落地渲染 | ✅ PASS | 顶部栏/侧边栏/主区域布局正常，13 任务显示 |
| F-02 列表+刷新 | ✅ PASS | 状态筛选（全部/完成/运行中）+ 场景下拉 + 刷新按钮全部可用，刷新触发 /traces/status |
| F-03 详情布局 | ✅ PASS | 任务起点 + 多智能体流程（5 阶段全显示 IC=0.024）+ Loop 选择 + 4 个 Tab + SOTA + 下载 |
| F-04 多 loop 切换 | ⚠️ 无法验证 | 当前已完成任务均只有 1 个 loop；运行中任务尚未产出 loop |
| F-05 chart 渲染 | 🔴 **FAIL** | iframe 空白，详见问题 #1 |
| F-06 因子代码 | ✅ PASS | 文件选择器（momentum_20d 等）+ 复制/下载按钮 + 代码内容 |
| F-07 健康检查 | ✅ PASS | GET /health 200 39ms，结构化 JSON 返回 |
| F-08 返回首页 | ✅ PASS | 点击 logo 回到 #/，落地页正常 |

**通过率：6/8（75%），其中 1 个无法验证、1 个失败。**

> **2026-07-26 R2 修复后复测**：F-05 已修复通过（见 §4 问题 #1）。当前通过率 7/8，剩 F-04 待多 loop 任务出现后补测。

## 4. 发现的问题

### 🔴 问题 #1（P0，严重）：历史 trace 的 chart 无法显示 + C4 在历史路径失效

**现象**：
- 点击「收益曲线」Tab → iframe 加载 `/api/v2/trace/artifact?id=undefined` → 空白。
- 详情接口 `POST /trace` 仍返回 5.1 MB（包含 4.97 MB 的内联 chart_html）。

**根因**：
C4（chart_html → descriptor 替换）只覆盖了实时路径 `_process_incoming_message`（`/receive` 收到的消息），**未覆盖历史加载路径** `_read_trace_into`。历史 trace 仍走 `WebStorage._obj_to_json`（`ui/storage.py:212-225`），生成 5 MB 内联 chart_html。

前端 `trace-model.ts:62` 的 `chartRef` 提取逻辑：
```js
chartRef:(objectValue(chartData?.chart_ref)||objectValue(chartData as object)) as ChartRef|null
```
当 `chartData = {chart_html: "..."}` 时，`chart_ref` 不存在，但 `objectValue(chartData)` 返回 truthy 对象 → 被误判为有效 ChartRef，导致 `trace_id=undefined`。`chartHtml` fallback 分支永远走不到。

**影响**：
- **所有历史 trace 的 chart 都显示不出来**（10 个已完成/运行中 trace 全部受影响）。
- C4+C5+C6 的体积优化（5 MB → 132 KB）在历史路径上完全失效。

**复现**：
```bash
curl -X POST http://localhost:19899/trace \
  -H "Content-Type: application/json" \
  -d '{"id":"Finance Data Building/careful-levee","cursor":0}' \
  | python3 -c "import json,sys;d=json.load(sys.stdin);[print(m['content'].keys()) for m in d if m.get('tag')=='feedback.return_chart']"
# 输出：dict_keys(['chart_html'])  ← 没有 chart_ref
```

**建议修复**（C4 历史路径补齐）：
1. 在 `_read_trace_into`（`app.py:404-432`）append 消息前，对 `tag == 'feedback.return_chart'` 的消息做 descriptor 替换。
2. 或在 `WebStorage._obj_to_json`（`ui/storage.py:212-225`）的 chart 分支直接生成 descriptor（不再 `plotly.io.to_html`）。
3. 前端 `trace-model.ts:62` 同时加固：仅当 `chart_ref.trace_id` 是字符串且非空时才认为有效，否则走 `chartHtml` fallback。

**影响改造点**：C4（核心修复）、C5（间接受益）、C6（前端防御）。

**✅ 已修复**（commit `d4fa1f9a`，分支 `fix/webui-perf-bugs`）：
- `_read_trace_into` 检测 chart tag 时直接生成 descriptor（不再走 `_obj_to_json` 内联）
- `trace-model.ts` chartRef 校验 trace_id 非空字符串，否则走 chartHtml fallback
- 附带修复：CDN 版本 6.7.0 → 2.35.3（bootcdn 上 6.x 是 404，2.35.3 是稳定可用最高 2.x）
- 复测：POST /trace 5.1MB → 21.7KB（99.6% 降幅），iframe URL `id=undefined` → `id=careful-levee`
- artifact 端点 134.7KB / 3.7ms，plotly 2.35.3 在 bootcdn HTTP 200 可下载

---

### 🟡 问题 #2（P2，中等）：运行中但无 message 的任务在详情页显示「待启动」

**现象**：
任务 `bipartite-module-20260724` 在 `/traces/status` 标为 `running`，但进入详情页后：
- 5 个智能体阶段全部显示「○ 待启动」（disabled）
- 4 个 Tab（最终结论/因子结果/收益曲线/因子代码）全部 disabled
- 仅有「运行日志」（81 行）可展开

**根因（推测）**：
任务 subprocess 在运行但还没产出任何关键 tag 消息（hypothesis/tasks/codes/metric/feedback），导致 `buildTraceView` 提取到的所有 latest-by-tag 都是 undefined。详情页正确反映了"无产物"状态，但视觉上和"未启动"无法区分，与 status="running" 不一致。

**建议**：
- 详情页头部加 status chip（running/done/error），与侧边栏状态对齐。
- 或在「待启动」状态下加副标题「等待首个 loop 产出…」。

**非阻塞**，可作为 UX 优化。

**✅ 已修复**（commit `d7bd5e7b`）：
- AgentFlow.vue 接收 `status` prop，当 `status='running'` 且 `agent.done=false` 时显示「⏳ 等待产出」
- Multiα1phaApp.vue 向 AgentFlow 传 `:status="currentTask?.status||'idle'"`
- 复测 bipartite-module：5 阶段全部从「○ 待启动」→「⏳ 等待产出」

---

### 🟡 问题 #3（P3，轻微）：Tab 标签 count 显示为名字一部分

**现象**：
- 「因子结果4」「因子代码4」（4 = 因子/文件数）
- 数字被拼到标签名后，视觉上像名字的一部分。

**建议**：
- count 改用独立 badge 样式（如圆角小标签、弱对比色）。
- 或单独放在标签右侧并加视觉分隔。

**非阻塞**，纯 UX。

**✅ 已修复**（commit `c317aada`）：
- ResultWorkspace.vue：count span 加 `class="count-badge"`
- 新增 scoped CSS：圆角 9px + 弱对比蓝色背景（rgba(38,103,255,0.12)）+ 11px 字号 + 6px 左边距
- active 状态切金色，disabled 状态半透明
- 复测 DOM：「因子结果」label + 独立 badge "4"，视觉分离 ✅

---

### 🟡 问题 #4（P3，轻微）：Hero 标题拼写 `Multiα1pha`

**现象**：首页大标题显示 `Multiα1pha`（数字 1 而非字母 l）。

**建议**：检查 landing 模板字符串是否误用 `1` 替代 `l`。

**非阻塞**，纯文案。

**✅ 已修复**（commit `049a2aa9`）：
- LandingTerminal.vue：`Multi<span>α</span>1pha` → `Multi<span>α</span>lpha`
- 保留 α 字符（设计标识，span 包裹可独立着色），仅把 1pha 改回 lpha
- 复测：`document.querySelector('h1').textContent === 'Multiαlpha'` ✅

## 5. 性能改造有效性总评

| 改造点 | 测试结论 | 证据 |
|--------|----------|------|
| C1 catalog + /traces/status | ✅ 生效 | 首页 545 B + 2.3 KB，无 N×/trace |
| C2 前端批量拉取 | ✅ 生效 | loadStatusesBatch 单次调用 |
| C3 按需加载 + 冷启动扫描 | ✅ 生效 | /traces 2 ms，列表不触发详情 |
| C4 chart descriptor | 🔴 **历史路径失效** | 5 MB chart_html 仍在响应中 |
| C5 artifact 端点 | ✅ 端点本身工作 | /api/v2/trace/artifact 200 1ms（实时 trace）/ id=undefined（历史） |
| C6 iframe src 懒加载 | 🔴 被前端误判拖累 | chartRef 永远 truthy，trace_id=undefined |
| C7 单遍扫描 | ⚠️ 未独立验证 | 单 loop 任务无法对比 |
| C8 shallowRef | ⚠️ 未独立验证 | 无明显渲染卡顿 |
| C9 消除 reverse | ⚠️ 未独立验证 | done 状态显示正确 |
| C10 幽灵 task | ✅ 生效 | 列表无幽灵项 |
| PERF 中间件 | ✅ 生效 | 全部请求正确记录 method/path/status/dur/size |
| web-vitals | ✅ 采集正常 | TTFB/FCP 写入 localStorage |

**总体结论**：性能优化在**首页加载、任务列表、增量轮询**层面达成预期（39 MB → 4 KB）；但 **C4 的历史路径覆盖遗漏导致 chart 显示回归**，是必须在合并前修复的 P0 问题。

## 6. 建议的下一步

**2026-07-26 R2 修复后状态**（分支 `fix/webui-perf-bugs`）：

1. ~~**P0 修复问题 #1**~~：✅ 已修复（commit `d4fa1f9a`）—— C4 历史路径补齐 + 前端 chartRef 防御 + CDN 版本修正。
2. **chart 体积验证**：✅ 已验证 —— POST /trace 5.1MB → 21.7KB，artifact 端点 134.7KB（C4+C5 收益达成）。
3. **多 loop 验证**：⏳ 待有 ≥ 2 loop 的任务出现后补测 F-04。
4. ~~**UX 优化**~~：✅ 问题 #2/#3/#4 已全部修复（commit `d7bd5e7b`/`c317aada`/`049a2aa9`）。
5. **合并建议**：所有发现的问题已修复且通过复测，`fix/webui-perf-bugs` 分支可以合入 `perf/webui-optimization`（或直接合入 main，取决于发布节奏）。

## 7. 修复分支提交记录（fix/webui-perf-bugs）

| commit | 类型 | 问题 | 说明 |
|--------|------|------|------|
| `d4fa1f9a` | P0 | #1 chart 不可显示 | C4 历史路径补齐 + 前端 chartRef 防御 + CDN 6.7.0→2.35.3 |
| `d7bd5e7b` | P2 | #2 待启动 vs 等待产出 | AgentFlow 区分 running/idle 状态文案 |
| `c317aada` | P3 | #3 Tab count 拼字 | count-badge 样式（圆角+弱对比色） |
| `049a2aa9` | P3 | #4 Multiα1pha typo | 1pha → lpha（保留 α 标识） |
