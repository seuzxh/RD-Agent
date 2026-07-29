# webUI 任务详情看板：各环节展示内容来源

> 本文档梳理 webUI「任务详情看板」中每个展示环节的数据来源链路：从前端组件字段 → `buildTraceView` 解析 → 消息 tag → 后端 `_obj_to_json` 转换 → 原始 Python 对象 / pickle 文件。

---

## 0. 数据流总览

```
子进程 pickle 文件（FileStorage）         原始 Python 对象（Hypothesis / FBWorkspace / Experiment / ...）
        │                                            │
        │  WebStorage.log(obj, tag)                  │
        ▼                                            ▼
┌───────────────────────────────────────────────────────────┐
│ WebStorage._obj_to_json(obj, tag)  ← rdagent/log/ui/storage.py
│   按 tag 字符串匹配，把对象字段抽取成 {tag, loop_id, content} 消息
└───────────────────────────────────────────────────────────┘
        │ HTTP POST /receive  →  server.app.task.messages
        ▼
┌───────────────────────────────────────────────────────────┐
│ POST /trace  →  返回 [{tag, timestamp, loop_id, content}, ...]
└───────────────────────────────────────────────────────────┘
        │ fetchTrace()  ← web/src/services/rdagent-api.ts
        ▼
┌───────────────────────────────────────────────────────────┐
│ buildTraceView(messages, loop)  ← web/src/multialpha/trace-model.ts
│   按 tag 提取最新一条 / 全量聚合，组装成 TraceViewModel
└───────────────────────────────────────────────────────────┘
        │ computed(() => buildTraceView(...))
        ▼
┌───────────────────────────────────────────────────────────┐
│ 各 Vue 组件按 props 消费 TraceViewModel 字段              │
│  PipelineStages / DetailHeader / AgentFlow / MetricsPanel │
│  / ResultWorkspace / ResultPage                           │
└───────────────────────────────────────────────────────────┘
```

关键事实：

- 前端**不直接读 pickle**，只消费 `/trace` 返回的消息流
- `tag` 是匹配核心：`_obj_to_json` 按 tag 字符串匹配决定输出 schema；`buildTraceView` 按 tag 取最新一条
- `loop_id` 决定作用域：选了某轮 loop 后，前端会过滤 `message.loop_id === loop`

---

## 1. 任务详情看板的整体结构

任务详情看板由以下组件构成（[web/src/multialpha/components/](../../RD-Agent/web/src/multialpha/components/)）：

| 组件 | 文件 | 展示内容 |
|---|---|---|
| `DetailHeader` | [DetailHeader.vue](../../RD-Agent/web/src/multialpha/components/DetailHeader.vue) | 任务名、scenario、状态、当前轮次 |
| `PipelineStages` | [PipelineStages.vue](../../RD-Agent/web/src/multialpha/components/PipelineStages.vue) | 4 步流水线进度条（研究→编码→回测→反馈） |
| `AgentFlow` | [AgentFlow.vue](../../RD-Agent/web/src/multialpha/components/AgentFlow.vue) | 5 个智能体卡片，点击查看产物 |
| `MetricsPanel` | [MetricsPanel.vue](../../RD-Agent/web/src/multialpha/components/MetricsPanel.vue) | 顶部 8 个核心指标 + 假设/反馈摘要 |
| `ResultWorkspace` | [ResultWorkspace.vue](../../RD-Agent/web/src/multialpha/components/ResultWorkspace.vue) | 4 个 Tab：最终结论 / 因子结果 / 收益曲线 / 因子代码 + SOTA 弹窗 |
| `ResultPage` | [ResultPage.vue](../../RD-Agent/web/src/views/ResultPage.vue) | 跨轮次摘要表 + 指标趋势图（"成功假设"开关 / 日志 / 全部循环文件下载） |

数据统一来自 `use-multialpha.ts` 的 `view = computed(() => buildTraceView(messages.value, selectedLoop.value))`（[use-multialpha.ts:32](../../RD-Agent/web/src/multialpha/use-multialpha.ts#L32)）。

---

## 2. PipelineStages：4 步流水线进度条

[PipelineStages.vue](../../RD-Agent/web/src/multialpha/components/PipelineStages.vue) 定义的 4 个环节及判定 tag：

| 环节（前端显示） | 判定为"done"所需 tag | 后端产出位置 |
|---|---|---|
| 研究 | `research.hypothesis` 或 `research.tasks` | [`storage.py:62-110`](../../RD-Agent/rdagent/log/ui/storage.py#L62-L110) |
| 编码 | `evolving.codes` | [`storage.py:114-135`](../../RD-Agent/rdagent/log/ui/storage.py#L114-L135) |
| 回测 | `feedback.metric` 或 `feedback.return_chart` | [`storage.py:198-220`](../../RD-Agent/rdagent/log/ui/storage.py#L198-L220)、[`storage.py:183-196`](../../RD-Agent/rdagent/log/ui/storage.py#L183-L196) |
| 反馈 | `evolving.feedbacks` 或 `feedback.hypothesis_feedback` | [`storage.py:139-160`](../../RD-Agent/rdagent/log/ui/storage.py#L139-L160)、[`storage.py:222-253`](../../RD-Agent/rdagent/log/ui/storage.py#L222-L253) |

判定逻辑：扫描当前作用域 messages 的 tag 集合，按顺序首个未命中的环节标记为 `active`（高亮），其后的标记为 `idle`。

---

## 3. DetailHeader：任务头部信息

[DetailHeader.vue](../../RD-Agent/web/src/multialpha/components/DetailHeader.vue)：

| 字段 | 来源 |
|---|---|
| `name`（任务名） | 上传时由 `randomname.get_name()` 生成，前端从 `traceIds` 列表选中 |
| `scenario` | 表单提交的字面值（如 `Finance Data Building`） |
| `status`（idle/running/done/error） | [`deriveTraceStatus(messages)`](../../RD-Agent/web/src/multialpha/trace-model.ts#L11-L17)：见 `END` 或（`feedback.hypothesis_feedback` + `feedback.metric` 同时存在）→ `done`；含 `error` → `error`；否则 `running` |
| `loop`（第几轮） | `TraceViewModel.loops`（从所有消息的 `loop_id` 字段聚合去重排序） |

---

## 4. AgentFlow：5 个智能体协作卡片

[AgentFlow.vue](../../RD-Agent/web/src/multialpha/components/AgentFlow.vue)，每个 agent 的 `done` 判定和点击展开后的产物：

| Agent | 图标 | done 判定 | 点击展开产物字段 | 数据来源 |
|---|---|---|---|---|
| 假设生成（研究员） | 🧠 | `latest('research.hypothesis')` 存在 | `hypothesis.hypothesis`、`hypothesis.reason` | [`storage.py:62-87`](../../RD-Agent/rdagent/log/ui/storage.py#L62-L87) → `Hypothesis` 对象 |
| 实验设计（设计师） | ✏️ | `latest('research.tasks')` 存在 | `factors[].{name, description, formula}` | [`storage.py:91-110`](../../RD-Agent/rdagent/log/ui/storage.py#L91-L110) → `FactorTask` / `ModelTask` 列表 |
| 代码实现（编码员） | ▰ | `codes.length > 0` | `codes[].{name, target, content}` | [`storage.py:114-135`](../../RD-Agent/rdagent/log/ui/storage.py#L114-L135) → `FBWorkspace.file_dict` |
| 回测执行（执行员） | 📊 | `latest('feedback.metric')` 存在 | `metricValues{IC, ICIR, ...}` | [`storage.py:198-220`](../../RD-Agent/rdagent/log/ui/storage.py#L198-L220) → `Experiment.result.to_json()` |
| 反馈评审（评审员） | 🔍 | `latest('feedback.hypothesis_feedback')` 存在 | `feedback.{decision, reason, observations, evaluation, newHypothesis, exception}` | [`storage.py:222-253`](../../RD-Agent/rdagent/log/ui/storage.py#L222-L253) → `HypothesisFeedback` 对象 |

> `latest(tag)` = 从后往前找第一条匹配 tag 的消息（[trace-model.ts:8](../../RD-Agent/web/src/multialpha/trace-model.ts#L8)）。

---

## 5. MetricsPanel：顶部核心指标摘要

[MetricsPanel.vue](../../RD-Agent/web/src/multialpha/components/MetricsPanel.vue)：

| 展示字段 | 来源 |
|---|---|
| 因子结果数量 `factors.length` | `latest('research.tasks')` → `parseFactors()` 解析数组的长度 |
| 8 个核心指标（IC / ICIR / 年化收益 / 最大回撤 / 信息比率 / Rank IC / Rank ICIR / ...） | `latest('feedback.metric')` → `parseMetrics()`，按 priority 排序取前 8 个 |
| 指标数值显示格式 | `percent=true` 的字段（如年化收益、最大回撤）显示为百分比；其余保留 4 位小数 |
| 研究假设文本 | `hypothesis.hypothesis` 或 `hypothesis.concise_observation`（前者优先） |
| 反馈摘要文本 | `feedback.reason` 或 `feedback.observations` 或 `feedback.evaluation`（按优先级取首个非空） |
| 导出按钮 | 触发 `$emit('download')`，由父组件打包下载 |

---

## 6. ResultWorkspace：4 Tab 工作区（本轮详情核心）

[ResultWorkspace.vue](../../RD-Agent/web/src/multialpha/components/ResultWorkspace.vue)，4 个 Tab 的内容来源：

### 6.1 Tab "最终结论"（conclusion）

| 展示区块 | 字段 | 来源 tag | 后端字段映射 |
|---|---|---|---|
| 4 个核心指标卡（IC / 年化收益 / 最大回撤 / 信息比率） | `coreMetrics` | `feedback.metric` | [`parseMetrics`](../../RD-Agent/web/src/multialpha/trace-model.ts#L21) priority 前 4 |
| 采纳/拒绝 chip | `feedback.decision` | `feedback.hypothesis_feedback` | `HypothesisFeedback.decision` |
| 决定理由 | `feedback.reason` | 同上 | `HypothesisFeedback.reason` |
| 实验观察 | `feedback.observations` | 同上 | `HypothesisFeedback.observations` |
| 假设评估 | `feedback.hypothesis_evaluation` | 同上 | `HypothesisFeedback.hypothesis_evaluation` |
| 异常信息 | `feedback.exception` | 同上 | `HypothesisFeedback.exception` |
| 下一轮新假设 | `feedback.newHypothesis` | 同上 | `HypothesisFeedback.new_hypothesis` |

### 6.2 Tab "因子结果"（factors）

| 字段 | 来源 tag → 后端字段 |
|---|---|
| `name` | `research.tasks` → `FactorTask.factor_name` 或 `ModelTask.name` |
| `description` | `research.tasks` → `FactorTask.factor_description` 或 `ModelTask.description` |
| `formula`（FormulaBlock 渲染） | `research.tasks` → `FactorTask.factor_formulation` |
| `variables`（键值对表） | `research.tasks` → `FactorTask.variables` |

### 6.3 Tab "收益曲线"（chart）

| 字段 | 来源 tag → 后端字段 |
|---|---|
| `chartHtml`（iframe srcdoc） | `feedback.return_chart` → `chart_html` |

后端转换（[`storage.py:183-196`](../../RD-Agent/rdagent/log/ui/storage.py#L183-L196)）：

```python
# tag 含 "Quantitative Backtesting Chart" 时
data = {"chart_html": plotly.io.to_html(report_figure(obj))}
```

`report_figure()` 来自 [`qlib_report_figure.py`](../../RD-Agent/rdagent/log/ui/qlib_report_figure.py)，把 qlib 回测结果对象转成 plotly HTML。

### 6.4 Tab "因子代码"（code）

| 字段 | 来源 tag → 后端字段 |
|---|---|
| `name`（文件名，如 `task.py`） | `evolving.codes` → `FBWorkspace.file_dict` 的 key |
| `content`（代码文本） | 同上 → `FBWorkspace.file_dict` 的 value |
| `target`（目标任务名） | `evolving.codes` → `FBWorkspace.target_task.name` |
| `evoId`（演化代 ID） | `evolving.codes` → `evo_id`（从 tag 字符串 `evo_loop_<ei>.evolving code` 提取） |

代码下拉框按 `evoId` 分组，前端 `getLastEvoEntries()` 会取**最新一代 evo** 的所有 entries（[ResultPage.vue 中的 `getLastEvoEntries`](../../RD-Agent/web/src/views/ResultPage.vue)）。

### 6.5 SOTA 弹窗（独立数据源）

点 "🏆 SOTA 产物" 触发 `loadSota()`，调 `fetchSota(traceId)`，走**完全不同的 API**：

| 展示字段 | 来源 |
|---|---|
| `sota_loop_id` / `sota_hypothesis` / `sota_feedback` / `sota_metrics` / `sota_factors` | `GET /sota?trace_name=...` 返回的 JSON |
| 数据源（二选一） | 1. `<trace_root>/<scenario>/<name>/__session__/` 存在 → 加载 session pickle（CLI 任务路径）<br>2. 不存在 → 从消息流提取（webUI 任务路径，`source: "message_stream"`） |
| 详见 | [trace-storage-paths.md §5](./trace-storage-paths.md#5-已知路径不一致webui-任务的-__session__-错位) 与 [API.md §2.8](../reference/API.md) |

---

## 7. ResultPage：跨轮次摘要表（高层视图）

[ResultPage.vue](../../RD-Agent/web/src/views/ResultPage.vue) 是另一个独立视图，把所有轮次聚合到一张表 + 一个趋势图：

### 7.1 摘要表每行 = 一个 loop

| 列 | 字段 | 来源 |
|---|---|---|
| `#` | `index` | loop 序号 |
| 组件（仅 Data Science） | `researchHypothesis.component` | `feedback.hypothesis_feedback` → `Hypothesis.component` |
| 状态 | `feedbackHypothesis.decision` | `feedback.hypothesis_feedback` → `HypothesisFeedback.decision`（true=成功 / false=失败） |
| 假设 | `researchHypothesis.hypothesis` | `research.hypothesis` → `Hypothesis.hypothesis` |
| 反馈 | `feedbackHypothesis.reason` | `feedback.hypothesis_feedback` → `HypothesisFeedback.reason` |
| 文件（按钮组） | `getLoopLastEvoFiles(loopItem)` | 取该 loop 最新 evo 的 `evolving.codes` workspace + `base_factors.json` + `descriptions.md`（task descriptions 拼成的 markdown） |

展开行额外显示：`observations`、`decision`（状态）。

### 7.2 指标趋势图

`chartBox` 组件渲染 `metricData`，每条线是一个指标，每个数据点 = `Round N`。指标同样来自 `feedback.metric`，按 loop 聚合。

### 7.3 顶部按钮

| 按钮 | 行为 | 数据源 |
|---|---|---|
| "成功的假设" 开关 | `switchValue=true` 时仅展示 `decision=true` 的 loop | `feedback.hypothesis_feedback.decision` 过滤 |
| 日志下载 | `downloadLogs()` | `GET /stdout?id=<trace_id>` → `<trace_root>/<scenario>/<trace_name>.log`（见 [trace-storage-paths.md §6.2](./trace-storage-paths.md#62-gets-stdoutidtrace_id)） |
| 全部循环文件下载 | `downloadAllLoops()` | 前端内存中按 loop 打包，每个 loop 取 `getLoopLastEvoFiles()` 的 zip |

---

## 8. 消息 tag → 后端对象字段映射总表

下表是 [`WebStorage._obj_to_json`](../../RD-Agent/rdagent/log/ui/storage.py#L55-L295) 的完整 tag 映射，是前端所有展示的**最终数据来源**：

| 消息 tag | 触发条件（tag 字符串包含） | 原始 Python 对象 | content 关键字段 |
|---|---|---|---|
| `research.hypothesis` | `"hypothesis generation"` | `Hypothesis` | `hypothesis`、`reason`、`concise_reason`、`concise_justification`、`concise_observation`、`concise_knowledge` |
| `research.tasks` | `"experiment generation"` 或 `"load_experiment"` | `list[FactorTask]` 或 `list[ModelTask]` | `name`、`description`、`formulation`、`variables`（factor）；额外 `model_type`（model） |
| `research.pdf_image` | `"pdf_image"` 或 `"load_pdf_screenshot"` | 图像对象 | `image`（jpg 相对路径，存到 `static/pdf_images/`） |
| `evolving.codes` | `f"evo_loop_{ei}.evolving code"` 且不含 `"running"` | `list[FBWorkspace]` | `evo_id`、`target_task_name`、`workspace`（file_dict） |
| `evolving.feedbacks` | `f"evo_loop_{ei}.evolving feedback"` 且不含 `"running"` | `list[CoSTEERSingleFeedback]` | `evo_id`、`final_decision`、`execution`、`code`、`return_checking` |
| `feedback.config` | `"scenario"` | `Scenario` | `config`（= `Scenario.experiment_setting`） |
| `feedback.return_chart` | `"Quantitative Backtesting Chart"` | qlib 回测结果 | `chart_html`（plotly HTML） |
| `feedback.metric` | `"running"` 且对象是 `Experiment` 且 `result` 非空 | `Experiment.result` | `result`（`result.to_json()` 字符串） |
| `feedback.hypothesis_feedback` | `"feedback"` 且对象是 `ExperimentFeedback` | `HypothesisFeedback` 或 `ExperimentFeedback` | `observations`、`hypothesis_evaluation`、`new_hypothesis`、`decision`、`reason`、`exception`（HypothesisFeedback 全集） |
| `token_cost` | `"token_cost"` | litellm 字典 | `model`、`prompt_tokens`、`completion_tokens`、`cost`、`accumulated_cost`（NaN/Inf 归 0） |
| `END` | 子进程退出时 server 追加 | 无 | `error_msg`、`end_code` |

**未被 `_obj_to_json` 处理的 tag**：直接返回空 dict，`WebStorage.log()` 输出 `"Normal log, skipped"`，前端不会收到该消息。

---

## 9. loop_id 和 evo_id 的提取规则

这两个 ID 是看板按轮次/按演化代筛选的关键：

### 9.1 `loop_id`

由 [`extract_loopid_func_name(tag)`](../../RD-Agent/rdagent/log/utils/__init__.py) 从 tag 字符串提取。tag 形如 `Loop_0.direct_exp_gen.token_cost.3851031-3853142`，提取 `Loop_` 后的数字部分。

前端使用：

- `TraceViewModel.loops` = 所有消息 `loop_id` 去重排序
- 选了某轮 loop 后，`buildTraceView` 过滤 `message.loop_id === loop` 重新构建 view
- `loopMetrics[loopId]` = 每轮的 IC 值，用于 LoopSwitcher 显示

### 9.2 `evo_id`

由 [`extract_evoid(tag)`](../../RD-Agent/rdagent/log/utils/__init__.py) 从 tag 字符串提取。tag 形如 `evo_loop_2.evolving code`，提取 `evo_loop_` 后的数字。

前端使用：

- `evolving.codes` 和 `evolving.feedbacks` 消息带 `evo_id` 字段
- `ResultPage.getLastEvoEntries()` 取**最新 evo_id** 的所有 entries，作为该 loop 的最终代码
- 同一 loop 内可能有多代 evo（CoSTEER 演化迭代），前端只展示最后一代

---

## 10. 配置/初始化类信息（非轮次相关）

部分信息只取**首次出现**的消息，不随 loop 变化：

| 字段 | 来源 tag | 取值规则 |
|---|---|---|
| `config`（任务配置表） | `feedback.config` | `firstConfig` = 第一条 `feedback.config` 消息的 content |
| `initialTasks`（初始因子列表） | `research.tasks` 且 `loop_id === 0` | `firstTasksLoop0` = 第一条 `loop_id=0` 的 `research.tasks` |

解析在 [`buildTraceView`](../../RD-Agent/web/src/multialpha/trace-model.ts#L30-L48) 的单遍扫描中完成。

---

## 11. 数据源分类速查

按"数据从哪里来"分类：

### 11.1 实时消息流（绝大多数展示）

API：`POST /trace`（`fetchTrace`）

- 来源：子进程 `WebStorage.log()` → `POST /receive` → `task.messages`
- 持久化：`FileStorage` 同时把 pickle 写到 `<trace_root>/<scenario>/<trace_name>/`
- 历史加载：服务重启后 `read_trace()` 从 FileStorage pickle 还原 `task.messages`

### 11.2 stdout 日志（仅日志下载按钮）

API：`GET /stdout?id=<trace_id>`

- 来源：子进程 stdout 重定向到 `<trace_root>/<scenario>/<trace_name>.log`
- 解析规则：见 [trace-storage-paths.md §6.2](./trace-storage-paths.md#62-gets-stdoutidtrace_id)

### 11.3 SOTA 查询（仅 SOTA 弹窗）

API：`GET /sota?trace_name=...`

- 双路径：`__session__/` 存在 → 加载 session pickle；不存在 → 从消息流回退提取
- 详见 [trace-storage-paths.md §5](./trace-storage-paths.md#5-已知路径不一致webui-任务的-__session__-错位)

### 11.4 静态资源（仅 PDF 图像）

- PDF 模式下 `research.pdf_image` 消息的 `image` 字段是相对路径
- 实际文件：`<UI_STATIC_PATH>/pdf_images/<timestamp>.jpg`
- 由 [`storage.py:60-66`](../../RD-Agent/rdagent/log/ui/storage.py#L60-L66) 在 `log()` 时落盘

---

## 12. 附录：组件 → 字段 → tag 完整对照表

| 组件 | 字段 / 区块 | TraceViewModel 字段 | 来源 tag（取最新） | 后端 Python 对象 |
|---|---|---|---|---|
| DetailHeader | 状态 | `hasEnd`/`hasError` | `END` / `*error*` | server 追加 |
| DetailHeader | 当前轮次 | `loops` | 所有带 `loop_id` 的消息 | `LoopBase.loop_idx` |
| PipelineStages | 研究环节 | — | `research.hypothesis` / `research.tasks` | `Hypothesis` / `FactorTask` |
| PipelineStages | 编码环节 | — | `evolving.codes` | `list[FBWorkspace]` |
| PipelineStages | 回测环节 | — | `feedback.metric` / `feedback.return_chart` | `Experiment.result` / qlib 结果 |
| PipelineStages | 反馈环节 | — | `evolving.feedbacks` / `feedback.hypothesis_feedback` | `CoSTEERSingleFeedback` / `HypothesisFeedback` |
| AgentFlow | 假设产物 | `hypothesis` | `research.hypothesis` | `Hypothesis` |
| AgentFlow | 设计产物 | `factors` | `research.tasks` | `list[FactorTask]` |
| AgentFlow | 编码产物 | `codes` | `evolving.codes` | `list[FBWorkspace]` |
| AgentFlow | 回测产物 | `metricValues` | `feedback.metric` | `Experiment.result` |
| AgentFlow | 反馈产物 | `feedback` | `feedback.hypothesis_feedback` | `HypothesisFeedback` |
| MetricsPanel | 8 个指标 | `metrics` | `feedback.metric` | `Experiment.result` |
| MetricsPanel | 因子数 | `factors.length` | `research.tasks` | `list[FactorTask]` |
| MetricsPanel | 假设摘要 | `hypothesis` | `research.hypothesis` | `Hypothesis` |
| MetricsPanel | 反馈摘要 | `feedback` | `feedback.hypothesis_feedback` | `HypothesisFeedback` |
| ResultWorkspace.conclusion | 4 核心指标 | `metrics`（前 4） | `feedback.metric` | `Experiment.result` |
| ResultWorkspace.conclusion | 决策 chip | `feedback.decision` | `feedback.hypothesis_feedback` | `HypothesisFeedback.decision` |
| ResultWorkspace.conclusion | 决定理由 | `feedback.reason` | 同上 | `HypothesisFeedback.reason` |
| ResultWorkspace.conclusion | 实验观察 | `feedback.observations` | 同上 | `HypothesisFeedback.observations` |
| ResultWorkspace.conclusion | 假设评估 | `feedback.evaluation` | 同上 | `HypothesisFeedback.hypothesis_evaluation` |
| ResultWorkspace.conclusion | 下一轮假设 | `feedback.newHypothesis` | 同上 | `HypothesisFeedback.new_hypothesis` |
| ResultWorkspace.conclusion | 异常信息 | `feedback.exception` | 同上 | `HypothesisFeedback.exception` |
| ResultWorkspace.factors | 因子名 | `factors[].name` | `research.tasks` | `FactorTask.factor_name` |
| ResultWorkspace.factors | 因子描述 | `factors[].description` | 同上 | `FactorTask.factor_description` |
| ResultWorkspace.factors | 因子公式 | `factors[].formula` | 同上 | `FactorTask.factor_formulation` |
| ResultWorkspace.factors | 因子变量 | `factors[].variables` | 同上 | `FactorTask.variables` |
| ResultWorkspace.chart | 收益曲线 | `chartHtml` | `feedback.return_chart` | qlib 回测结果 → plotly HTML |
| ResultWorkspace.code | 代码文件名 | `codes[].name` | `evolving.codes` | `FBWorkspace.file_dict` key |
| ResultWorkspace.code | 代码内容 | `codes[].content` | 同上 | `FBWorkspace.file_dict` value |
| ResultWorkspace.code | 目标任务 | `codes[].target` | 同上 | `FBWorkspace.target_task.name` |
| ResultWorkspace.code | 演化代 | `codes[].evoId` | 同上 | tag 中 `evo_loop_<n>` 提取 |
| ResultWorkspace.SOTA | 全部字段 | — | `GET /sota`（独立） | `__session__/` 或消息流回退 |
| ResultPage | 摘要表 | `currentData[]` | 全部 loop 的 `research.hypothesis` + `feedback.hypothesis_feedback` | 同上 |
| ResultPage | 趋势图 | `metricData` | 全部 loop 的 `feedback.metric` | `Experiment.result` |
| ResultPage | 日志下载 | — | `GET /stdout`（独立） | stdout 重定向文件 |
| ResultPage | 全部循环文件 | — | 全部 loop 的 `evolving.codes` | `list[FBWorkspace]` |
| TraceLoading | Token 统计 | `promptTokens`/`completionTokens`/`totalTokens`/`callCount` | `token_cost` | litellm 字典 |

---

## 13. 一句话总结

webUI 任务详情看板的**所有展示内容**都来自 `/trace` 返回的消息流（按 tag 提取最新一条 / 全量聚合），唯一例外是 SOTA 弹窗（`/sota` API）和日志下载（`/stdout` API）。每条消息的 `tag` 由后端 `WebStorage._obj_to_json` 按字符串匹配决定 schema，`loop_id` / `evo_id` 从 tag 字符串中提取，前端按这两个 ID 实现按轮次/按演化代的筛选。
