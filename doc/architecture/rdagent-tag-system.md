# RD-Agent tag 体系详解

> 本文档梳理 rd-agent 中的 tag 体系：从代码中的打 tag 入口 → ContextVar 嵌套合并 → 完整 tag 字符串形态 → 后端 `_obj_to_json` 按 tag 匹配 → 前端按 tag 提取展示。tag 是贯穿整个 trace 数据流的"分类键"。

---

## 1. tag 是什么

**tag 是一条 trace 消息的分类标识字符串**，用 `.` 分隔的多段命名，形如：

```
Loop_0.direct_exp_gen.evo_loop_2.evolving code.3851031-3853142
```

它由代码中多个 `with logger.tag(...)` context manager **嵌套合并**生成，最终决定：

1. **落盘位置**：FileStorage 把 tag 的 `.` 转为路径分隔符（`Loop_0/direct_exp_gen/.../`）
2. **消息 schema**：`WebStorage._obj_to_json` 按 tag 字符串匹配决定如何把 Python 对象转成 JSON
3. **前端展示**：前端按规范化 tag（`research.hypothesis` 等）提取最新一条消息渲染看板
4. **loop_id / evo_id 提取**：从 tag 字符串中正则提取 `Loop_<n>` / `evo_loop_<n>`

---

## 2. tag 的生成机制

### 2.1 三个入口

| 入口 | API | 用途 |
|---|---|---|
| `with logger.tag(name)` | [`RDAgentLog.tag()`](../../RD-Agent/rdagent/log/logger.py#L90-L103) | 上下文管理器，进入时把 `name` 追加到当前 tag |
| `logger.log_object(obj, tag="...")` | [`RDAgentLog.log_object()`](../../RD-Agent/rdagent/log/logger.py#L135-L136) | 一次性 tag，与当前上下文 tag 合并 |
| `logger.info(msg, tag="...")` / `.warning()` / `.error()` | 同上 | 文本日志带 tag |

### 2.2 ContextVar 嵌套合并

tag 通过 `ContextVar` 在协程/线程本地状态中累积（[`logger.py:24`](../../RD-Agent/rdagent/log/logger.py#L24)）：

```python
_tag_ctx: ContextVar[str] = ContextVar("_tag_ctx", default="")

@contextmanager
def tag(self, tag: str) -> Generator[None, None, None]:
    if tag.strip() == "":
        raise ValueError("Tag cannot be empty.")
    current_tag = self._tag_ctx.get()           # 父级 tag
    new_tag = tag if current_tag == "" else f"{current_tag}.{tag}"
    token = self._tag_ctx.set(new_tag)
    try:
        yield
    finally:
        self._tag_ctx.reset(token)              # 退出时还原
```

关键特性：

- **嵌套累加**：内层 tag 自动拼到外层 tag 后面，用 `.` 连接
- **协程安全**：`ContextVar` 保证每个 asyncio task / 线程有独立 tag 栈
- **fork 继承**：Linux fork 子进程会继承父进程当前 tag（注释明确说明，[`logger.py:24`](../../RD-Agent/rdagent/log/logger.py#L24)）
- **空值禁止**：`tag=""` 会抛 `ValueError`

### 2.3 一次性 tag 的合并

`log_object(obj, tag="...")` 内部把传入的 `tag` 与当前 ContextVar 中的 tag 合并后传给 storage（[`logger.py:135-136`](../../RD-Agent/rdagent/log/logger.py#L135-L136)）：

```python
def log_object(self, obj: object, *, tag: str = "") -> None:
    full_tag = f"{self._tag}.{tag}" if tag else self._tag
    storage.log(obj, tag=full_tag)
```

所以 `logger.log_object(hypothesis, tag="hypothesis generation")` 在 `with logger.tag("Loop_0.direct_exp_gen")` 上下文里产生的完整 tag 是：

```
Loop_0.direct_exp_gen.hypothesis generation
```

---

## 3. 项目中实际打的所有 tag

### 3.1 上下文 tag（`with logger.tag(...)`）

全项目共 7 处（grep 结果）：

| tag 片段 | 文件 | 作用 |
|---|---|---|
| `Loop_{li}.{name}` | [`loop.py:218`](../../RD-Agent/rdagent/utils/workflow/loop.py#L218) | 主循环每步的命名空间（li=loop_idx，name=step_name） |
| `evo_loop_{evo_loop_id}` | [`evolving_agent.py:146`](../../RD-Agent/rdagent/core/evolving_agent.py#L146) | CoSTEER 演化代次命名空间 |
| `session_{conversation_id}` | [`base.py:316`](../../RD-Agent/rdagent/oai/backend/base.py#L316) | LLM 会话隔离（每个 conversation 一个） |
| `docs` | [`pdf_loader.py:569`](../../RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L569) | PDF 文档处理 |
| `file_to_factor_result` | [`pdf_loader.py:575`](../../RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L575) | 文件转因子结果 |
| `factor_dict` | [`pdf_loader.py:579`](../../RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L579) | 因子字典 |
| `filtered_factor_dict` | [`pdf_loader.py:583`](../../RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L583) | 过滤后的因子字典 |

### 3.2 一次性 tag（`log_object(..., tag=...)` / `info(..., tag=...)`）

按场景分类：

#### 3.2.1 RDLoop 主流程 5 步（[`components/workflow/rd_loop.py`](../../RD-Agent/rdagent/components/workflow/rd_loop.py)）

| tag 字面值 | 打点位置 | Python 对象 | webUI 规范化 tag |
|---|---|---|---|
| `"hypothesis generation"` | [`rd_loop.py:190`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L190) | `Hypothesis` | `research.hypothesis` |
| `"experiment generation"` | [`rd_loop.py:195`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L195) | `list[FactorTask]` / `list[ModelTask]` | `research.tasks` |
| `"coder result"` | [`rd_loop.py:214`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L214) | `list[FBWorkspace]` | （未规范化，被跳过） |
| `"runner result"` | [`rd_loop.py:219`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L219) | `Experiment` | `feedback.metric`（含 running tag 时） |
| `"feedback"` | [`rd_loop.py:235`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L235) | `HypothesisFeedback` | `feedback.hypothesis_feedback` |

#### 3.2.2 CoSTEER 演化（[`components/coder/CoSTEER/__init__.py`](../../RD-Agent/rdagent/components/coder/CoSTEER/__init__.py)）

| tag 字面值 | 打点位置 | Python 对象 | webUI 规范化 tag |
|---|---|---|---|
| `"evolving code"` | [`__init__.py:129`](../../RD-Agent/rdagent/components/coder/CoSTEER/__init__.py#L129) | `list[FBWorkspace]` | `evolving.codes` |
| `"evolving feedback"` | [`evolving_agent.py:181`](../../RD-Agent/rdagent/core/evolving_agent.py#L181) | `list[CoSTEERSingleFeedback]` | `evolving.feedbacks` |

#### 3.2.3 Qlib 场景特定（[`scenarios/qlib/`](../../RD-Agent/rdagent/scenarios/qlib/)）

| tag 字面值 | 文件 | 说明 |
|---|---|---|
| `"Quantitative Backtesting Chart"` | [`workspace.py:45`](../../RD-Agent/rdagent/scenarios/qlib/experiment/workspace.py#L45) | 回测图表（plotly HTML） |
| `"Qlib_execute_log"` | [`workspace.py:34`](../../RD-Agent/rdagent/scenarios/qlib/experiment/workspace.py#L34) | Qlib 执行日志 |
| `"scenario"` | [`rd_loop.py:35`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L35) | Scenario 配置 |
| `"load_pdf_screenshot"` | [`factor_from_report.py:77`](../../RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py#L77) | PDF 截图（factor_from_report 场景） |

#### 3.2.4 配置类（初始化时打一次）

| tag 字面值 | 文件 | 说明 |
|---|---|---|
| `"RDLOOP_SETTINGS"` | [`rd_loop.py:36`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L36) | RDLoop 配置快照 |
| `"RD_AGENT_SETTINGS"` | [`rd_loop.py:37`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L37) | 全局配置快照 |
| `"LITELLM_SETTINGS"` | [`litellm.py:56`](../../RD-Agent/rdagent/oai/backend/litellm.py#L56) | LiteLLM 配置快照 |

#### 3.2.5 LLM 调用相关（[`oai/backend/`](../../RD-Agent/rdagent/oai/backend/)）

| tag 字面值 | 文件 | 说明 |
|---|---|---|
| `"llm_messages"` | [`litellm.py:150-181`](../../RD-Agent/rdagent/oai/backend/litellm.py#L150-L181) | LLM 请求/响应消息（流式 + 非流式） |
| `"token_cost"` | [`litellm.py:222`](../../RD-Agent/rdagent/oai/backend/litellm.py#L222) | 每次 LLM 调用的 token 统计 |
| `"debug_litellm_token"` | [`litellm.py:68`](../../RD-Agent/rdagent/oai/backend/litellm.py#L68) | token 数调试日志 |
| `"debug_litellm_emb"` | [`litellm.py:76`](../../RD-Agent/rdagent/oai/backend/litellm.py#L76) | embedding 模型调试日志 |

#### 3.2.6 其他

| tag 字面值 | 文件 | 说明 |
|---|---|---|
| `"prediction.top20"` | [`predict.py:86`](../../RD-Agent/rdagent/app/qlib_rd_loop/predict.py#L86) | 预测 Top20 结果 |
| `"context7"` | [`context7/__init__.py:37`](../../RD-Agent/rdagent/components/agent/context7/__init__.py#L37) | context7 调试日志 |

---

## 4. 完整 tag 嵌套结构

结合 §3.1 的上下文 tag 和 §3.2 的一次性 tag，一个完整的因子挖掘 loop 产出的 tag 树如下：

```
Loop_0.direct_exp_gen                          # 主循环第 0 轮、direct_exp_gen 步
├── .hypothesis generation                     # → research.hypothesis
├── .experiment generation                     # → research.tasks
└── .session_<conv_id>.llm_messages            # LLM 调用消息
    └── .session_<conv_id>.llm_messages.token_cost  # token 统计

Loop_0.coding                                  # 主循环第 0 轮、coding 步
└── .evo_loop_0                                # CoSTEER 第 0 代演化
    ├── .evolving code                         # → evolving.codes
    │   └── .3851031-3853142                   # PID 链（自动追加）
    │       └── <timestamp>.pkl
    ├── .evolving feedback                     # → evolving.feedbacks
    │   └── .3851031-3853142
    ├── .evo_loop_0.session_<conv_id>.llm_messages  # 嵌套层加深
    │   └── .llm_messages.token_cost
    └── .evo_loop_0.scenario                   # scenario 配置

Loop_0.running                                 # 主循环第 0 轮、running 步
├── .runner result                             # → feedback.metric（含 running）
├── .Qlib_execute_log
└── .Quantitative Backtesting Chart            # → feedback.return_chart

Loop_0.feedback                                # 主循环第 0 轮、feedback 步
└── .feedback                                  # → feedback.hypothesis_feedback
```

**关键观察**：

- `Loop_<n>.<step_name>` 是顶层命名空间，5 个 step 名固定：`direct_exp_gen` / `coding` / `running` / `feedback` / `record`
- `evo_loop_<n>` 只出现在 `coding` 步内（CoSTEER 演化）
- `session_<conv_id>` 跟随 LLM 调用，每个 conversation 一个
- PID 链 `3851031-3853142` 由 [`logger.py:122-133`](../../RD-Agent/rdagent/log/logger.py#L122-L133) 的 `get_pids()` 自动追加到最内层

---

## 5. tag → 路径转换（FileStorage）

[`FileStorage.log()`](../../RD-Agent/rdagent/log/storage.py#L38-L66) 把 tag 转为目录路径：

```python
cur_p = self.path / tag.replace(".", "/")
cur_p.mkdir(parents=True, exist_ok=True)
path = cur_p / f"{timestamp.strftime('%Y-%m-%d_%H-%M-%S-%f')}.pkl"
```

实例映射：

| 完整 tag | 落盘路径（相对 storage.path） |
|---|---|
| `Loop_0.direct_exp_gen.hypothesis generation` | `Loop_0/direct_exp_gen/hypothesis generation/<ts>.pkl` |
| `Loop_0.coding.evo_loop_0.evolving code.3851031-3853142` | `Loop_0/coding/evo_loop_0/evolving code/3851031-3853142/<ts>.pkl` |
| `RDLOOP_SETTINGS` | `RDLOOP_SETTINGS/<ts>.pkl` |

注意 tag 中的空格（如 `"hypothesis generation"`）会原样进入路径，文件系统支持但前端 URL 需 encode。

---

## 6. tag → 消息 schema（WebStorage._obj_to_json）

[`_obj_to_json`](../../RD-Agent/rdagent/log/ui/storage.py#L55-L295) 按**完整 tag 字符串包含子串**匹配，决定如何把 Python 对象转成消息。匹配是**顺序敏感**的 if-elif 链：

| 匹配条件（tag 包含子串） | 输出规范化 tag | 输入 Python 对象 | content 关键字段 |
|---|---|---|---|
| `"hypothesis generation"` | `research.hypothesis` | `Hypothesis` | `hypothesis`、`reason`、`concise_*` |
| `"pdf_image"` / `"load_pdf_screenshot"` | `research.pdf_image` | 图像 | `image`（jpg 路径） |
| `"experiment generation"` / `"load_experiment"` | `research.tasks` | `list[FactorTask/ModelTask]` | `name`、`description`、`formulation`、`variables` |
| `f"evo_loop_{ei}.evolving code"` 且不含 `"running"` | `evolving.codes` | `list[FBWorkspace]` | `evo_id`、`target_task_name`、`workspace` |
| `f"evo_loop_{ei}.evolving feedback"` 且不含 `"running"` | `evolving.feedbacks` | `list[CoSTEERSingleFeedback]` | `evo_id`、`final_decision`、`execution` |
| `"scenario"` | `feedback.config` | `Scenario` | `config`（= `experiment_setting`） |
| `"Quantitative Backtesting Chart"` | `feedback.return_chart` | qlib 结果 | `chart_html`（plotly HTML） |
| `"running"` 且对象是 `Experiment` 且 `result` 非空 | `feedback.metric` | `Experiment.result` | `result`（to_json 字符串） |
| `"feedback"` 且对象是 `ExperimentFeedback` | `feedback.hypothesis_feedback` | `HypothesisFeedback` | `observations`、`decision`、`reason`、`new_hypothesis`、`exception` |
| `"token_cost"` | `token_cost` | litellm 字典 | `prompt_tokens`、`completion_tokens`、`cost` |

### 6.1 匹配规则的微妙之处

1. **顺序敏感**：if-elif 链，第一个匹配的分支生效。例如 `"running"` 同时出现在 `Loop_0.running` 和 `evo_loop_0.evolving code.running` 中，但 `evo_loop_*` 分支在前且要求不含 `"running"`，所以演化代码的 running 不会被误判为回测结果。
2. **evo_loop 必须显式提取**：`f"evo_loop_{ei}.evolving code"` 用 f-string 把 evo_id 嵌入匹配条件，因此 `_obj_to_json` 内部调用 `extract_evoid(tag)` 拿到 `ei` 才能构造匹配串。
3. **未被任何分支匹配的 tag**：返回空 dict `{}`，`log()` 输出 `"Normal log, skipped"`，**前端不会收到该消息**。例如 `coder result` / `RDLOOP_SETTINGS` / `llm_messages` 都属于此类。
4. **`"running"` 的双重含义**：`Loop_0.running` 上下文里的 `runner result` 对象会被识别为 `feedback.metric`；但 `evo_loop_*` 上下文里的 running 会被前一个分支的 `and "running" not in tag` 排除掉。

### 6.2 tag 包含子串匹配的潜在问题

- `"scenario"` 是子串匹配，会命中 `Loop_0.coding.scenario` 等任何含 scenario 的 tag，但实际只在初始化时打一次 `tag="scenario"`
- `"feedback"` 同理，会命中 `feedback.hypothesis_feedback` 自身（不影响结果，因为 elif 已到最后）

---

## 7. tag → loop_id / evo_id 提取

两个正则提取函数（[`log/utils/__init__.py`](../../RD-Agent/rdagent/log/utils/__init__.py)）：

### 7.1 `extract_loopid_func_name`

```python
def extract_loopid_func_name(tag: str) -> tuple[str, str] | tuple[None, None]:
    match = re.search(r"Loop_(\d+)\.([^.]+)", tag)
    return match.groups() if match else (None, None)
```

匹配 `Loop_<数字>.<非点字符序列>`，返回 `(loop_id, step_name)`。

| 输入 tag | 输出 |
|---|---|
| `Loop_0.direct_exp_gen.hypothesis generation` | `("0", "direct_exp_gen")` |
| `Loop_1.coding.evo_loop_2.evolving code` | `("1", "coding")` |
| `evo_loop_0.evolving code`（无 Loop_ 前缀） | `(None, None)` |
| `RDLOOP_SETTINGS` | `(None, None)` |

### 7.2 `extract_evoid`

```python
def extract_evoid(tag: str) -> str | None:
    match = re.search(r"evo_loop_(\d+)\.", tag)
    return match.group(1) if match else None
```

匹配 `evo_loop_<数字>.`，返回 evo_id。

| 输入 tag | 输出 |
|---|---|
| `Loop_0.coding.evo_loop_2.evolving code.3851031` | `"2"` |
| `Loop_0.direct_exp_gen.hypothesis generation` | `None` |

### 7.3 提取规则对前端的影响

- **loop_id 为 None 的消息**：前端 `buildTraceView` 仍会处理，但不进入任何具体 loop 的视图（只在"全部"视图显示）。例如 `RDLOOP_SETTINGS` / `RD_AGENT_SETTINGS` / `scenario` 都是 loop 无关的全局消息。
- **evo_id 为 None 的消息**：不会被识别为 `evolving.codes` / `evolving.feedbacks`（因为 `_obj_to_json` 的匹配条件需要 `evo_loop_{ei}` 字面值）。

---

## 8. 前端按 tag 提取的规则

前端 [`trace-model.ts`](../../RD-Agent/web/src/multialpha/trace-model.ts) 用 `latest(messages, tag)` 函数按**完整字符串相等**提取最新一条：

```typescript
function latest(messages: TraceMessage[], tag: string) {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].tag === tag) return messages[i]
  }
  return undefined
}
```

**与后端的关键差异**：

- 后端 `_obj_to_json` 用**子串包含**匹配原始 tag
- 前端用**完整相等**匹配规范化后的 tag（`research.hypothesis` 等）

所以前端只认规范化 tag，原始 tag 中的 `Loop_0.direct_exp_gen.` 前缀在前端被忽略——但 `loop_id` 字段已经由后端提取并塞进消息体的 `loop_id` 字段，前端按 `message.loop_id === selectedLoop` 过滤。

### 8.1 前端识别的规范化 tag 清单

从 [`trace-model.ts`](../../RD-Agent/web/src/multialpha/trace-model.ts) 和 [`PipelineStages.vue`](../../RD-Agent/web/src/multialpha/components/PipelineStages.vue) 提取：

| 规范化 tag | 前端用途 |
|---|---|
| `research.hypothesis` | 假设产物、研究环节 done 判定 |
| `research.tasks` | 因子列表、设计环节 done 判定 |
| `evolving.codes` | 代码文件、编码环节 done 判定 |
| `evolving.feedbacks` | 反馈环节 done 判定 |
| `feedback.metric` | 指标、回测环节 done 判定 |
| `feedback.return_chart` | 收益曲线、回测环节 done 判定 |
| `feedback.hypothesis_feedback` | 反馈详情、反馈环节 done 判定 |
| `feedback.config` | 任务配置表（首次出现） |
| `token_cost` | Token 统计 |
| `END` | 任务结束判定 |
| `*error*`（正则） | 任务异常判定 |

---

## 9. 完整 tag 生命周期示例

以一次 `fin_factor` 任务的 loop 0 为例，tag 的完整生命周期：

```
1. 应用启动
   tag = "" (ContextVar default)

2. 进入 Loop_0.direct_exp_gen
   with logger.tag("Loop_0.direct_exp_gen")
   → tag = "Loop_0.direct_exp_gen"

   2.1 调用 LLM 生成假设
       # 注：build_chat_completion wrapper 会打 session_<conv_id>，
       # 但 litellm backend 走更底层入口，实际产物中无此层（见 §13 实测验证）
       
           logger.log_object(hypothesis, tag="hypothesis generation")
           → 完整 tag = "Loop_0.direct_exp_gen.hypothesis generation"
           ⚠️ 但 _obj_to_json 只看 "hypothesis generation" in tag，匹配成功
           → 输出消息 {tag: "research.hypothesis", loop_id: "0", content: {...}}
           
           logger.log_object(token_data, tag="token_cost")
           → 完整 tag = "Loop_0.direct_exp_gen.token_cost"
           → 输出消息 {tag: "token_cost", loop_id: "0", content: {...}}

3. 退出 direct_exp_gen，进入 Loop_0.coding
   with logger.tag("Loop_0.coding")
   → tag = "Loop_0.coding"

   3.1 CoSTEER 第 0 代演化
       with logger.tag("evo_loop_0")
       → tag = "Loop_0.coding.evo_loop_0"
       
           logger.log_object(sub_workspace_list, tag="evolving code")
           → 完整 tag = "Loop_0.coding.evo_loop_0.evolving code"
           → _obj_to_json 匹配 f"evo_loop_0.evolving code" in tag ✓
           → 输出消息 {tag: "evolving.codes", loop_id: "0", evo_id: "0", content: [...]}

4. 进入 Loop_0.running
   with logger.tag("Loop_0.running")
   → tag = "Loop_0.running"
   
       logger.log_object(exp, tag="runner result")
       → 完整 tag = "Loop_0.running.runner result"
       → _obj_to_json: "running" in tag ✓ 且对象是 Experiment ✓
       → 输出消息 {tag: "feedback.metric", loop_id: "0", content: {result: "..."}}

5. 进入 Loop_0.feedback
   with logger.tag("Loop_0.feedback")
   → tag = "Loop_0.feedback"
   
       logger.log_object(feedback, tag="feedback")
       → 完整 tag = "Loop_0.feedback.feedback"
       → _obj_to_json: "feedback" in tag ✓ 且对象是 ExperimentFeedback ✓
       → 输出消息 {tag: "feedback.hypothesis_feedback", loop_id: "0", content: {...}}
```

---

## 10. tag 体系的潜在问题

### 10.1 子串匹配的脆弱性

`_obj_to_json` 用 `in` 做子串匹配，存在误命中风险：

- `"scenario"` 会命中任何含 scenario 的 tag（实际只在初始化打一次，目前安全）
- `"running"` 会命中 `Loop_0.running.xxx` 下的所有 tag（依赖 `isinstance(obj, Experiment)` 兜底）
- `"feedback"` 会命中 `feedback.hypothesis_feedback` 自身（无副作用，因为 elif 顺序）

### 10.2 未规范化的 tag 被丢弃

以下 tag 不被 `_obj_to_json` 任何分支匹配，**前端永远看不到**：

- `coder result`（[`rd_loop.py:214`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L214)）—— 被 `evolving.codes` 取代
- `RDLOOP_SETTINGS` / `RD_AGENT_SETTINGS` / `LITELLM_SETTINGS` —— 配置快照只落盘不进消息流
- `llm_messages` —— LLM 请求/响应文本
- `Qlib_execute_log` —— Qlib 执行日志
- `debug_litellm_token` / `debug_litellm_emb` —— 调试日志

这些 tag 的 pickle 仍在 FileStorage 落盘，可通过 `read_trace` 加载到 `task.messages`，但前端 `buildTraceView` 不会消费它们（因为不在识别清单里）。

### 10.3 空格在 tag 中的处理

原始 tag 含空格（如 `"hypothesis generation"`、`"evolving code"`、`"Quantitative Backtesting Chart"`）：

- FileStorage 落盘：空格原样进入路径（Linux 支持）
- `_obj_to_json` 匹配：用 `in` 子串匹配，空格不影响
- 前端：只看规范化 tag（`research.hypothesis` 等，无空格），不受影响

### 10.4 evo_id 提取的隐式依赖

`_obj_to_json` 中 `evolving.codes` / `evolving.feedbacks` 分支的匹配条件是 f-string：

```python
elif f"evo_loop_{ei}.evolving code" in tag and "running" not in tag:
```

其中 `ei = extract_evoid(tag)`。如果 `extract_evoid` 返回 `None`，`f"evo_loop_None.evolving code"` 永远不会匹配，消息会被丢弃。所以**没有 `evo_loop_<n>` 上下文的 evolving code 打点会被静默丢弃**。

---

## 11. tag 速查表

### 11.1 上下文 tag（影响嵌套）

| tag | 引入位置 | 影响 |
|---|---|---|
| `Loop_{n}.{step}` | LoopBase | 决定 loop_id 和 step_name |
| `evo_loop_{n}` | EvolvingAgent | 决定 evo_id，是 evolving.* 消息的必需前缀 |
| `session_{conv_id}` | LLM backend | 隔离不同 LLM 会话（不影响前端展示） |

### 11.2 一次性 tag（按场景）

| 场景 | tag 字面值 | 规范化 tag | Python 对象 |
|---|---|---|---|
| 假设生成 | `hypothesis generation` | `research.hypothesis` | `Hypothesis` |
| 实验生成 | `experiment generation` | `research.tasks` | `list[FactorTask/ModelTask]` |
| 演化代码 | `evolving code` | `evolving.codes` | `list[FBWorkspace]` |
| 演化反馈 | `evolving feedback` | `evolving.feedbacks` | `list[CoSTEERSingleFeedback]` |
| 回测结果 | `runner result`（在 running 上下文） | `feedback.metric` | `Experiment.result` |
| 回测图表 | `Quantitative Backtesting Chart` | `feedback.return_chart` | qlib 结果 |
| 假设反馈 | `feedback` | `feedback.hypothesis_feedback` | `HypothesisFeedback` |
| Scenario | `scenario` | `feedback.config` | `Scenario` |
| Token 统计 | `token_cost` | `token_cost` | litellm 字典 |
| PDF 截图 | `load_pdf_screenshot` / `pdf_image` | `research.pdf_image` | 图像对象 |
| 预测结果 | `prediction.top20` | （未规范化） | 预测结果 |

### 11.3 被丢弃的 tag（不进消息流）

| tag 字面值 | 落盘但不进 /trace 消息 |
|---|---|
| `coder result` | 被 `evolving.codes` 取代 |
| `RDLOOP_SETTINGS` / `RD_AGENT_SETTINGS` / `LITELLM_SETTINGS` | 配置快照 |
| `llm_messages` | LLM 请求/响应文本 |
| `Qlib_execute_log` | Qlib 执行日志 |
| `debug_litellm_token` / `debug_litellm_emb` | 调试日志 |

---

## 12. 一句话总结

tag 是 `.` 分隔的多段字符串，由 `with logger.tag(...)` 上下文嵌套合并 + `log_object(tag=...)` 一次性追加生成，完整形态形如 `Loop_0.coding.evo_loop_2.evolving code.3851031-3853142`。FileStorage 按 `.` 转路径落盘，WebStorage 按**子串包含**匹配决定消息 schema 并提取 loop_id / evo_id，前端按**完整相等**匹配规范化 tag（`research.hypothesis` 等）渲染看板。未被 `_obj_to_json` 任何分支匹配的 tag 会被静默丢弃（不进 `/trace` 消息流，但 pickle 仍在文件系统）。

---

## 13. 实际示例（基于项目快照）

以 `Finance Data Building/plain-transformation` 任务为例（跑了 3 轮 loop，loop 0 完整覆盖了 5 个 step + CoSTEER 演化）。所有路径来自实际 pickle 文件扫描，PID 链为 `3855634-3857820`。

### 13.1 任务初始化阶段（无 Loop 前缀）

应用启动时打的 3 个全局 tag，**没有 Loop_xxx 前缀**，落盘在根目录：

| 完整 tag 字符串 | 落盘路径 | 规范化 tag | 说明 |
|---|---|---|---|
| `scenario.3855634-3857820` | `scenario/3855634-3857820/2026-07-20_15-07-56-141392.pkl` | `feedback.config` | Scenario 配置（先于 Loop_0 打） |
| `RDLOOP_SETTINGS.3855634-3857820` | `RDLOOP_SETTINGS/3855634-3857820/2026-07-20_15-07-56-145601.pkl` | （被丢弃） | RDLoop 配置快照 |
| `RD_AGENT_SETTINGS.3855634-3857820` | `RD_AGENT_SETTINGS/3855634-3857820/<ts>.pkl` | （被丢弃） | 全局配置快照 |

**前端影响**：`extract_loopid_func_name("scenario.3855634-3857820")` 返回 `(None, None)`，loop_id 为 None 的消息只在"全部"视图显示。`feedback.config` 是首次出现，DetailHeader 会用它填充任务配置表。

### 13.2 Loop 0 完整 tag 字符串表

#### 13.2.1 direct_exp_gen 步（研究环节）

| 完整 tag 字符串 | 落盘路径 | 规范化 tag | _obj_to_json 匹配 |
|---|---|---|---|
| `Loop_0.direct_exp_gen.hypothesis generation.3855634-3857820` | `Loop_0/direct_exp_gen/hypothesis generation/3855634-3857820/2026-07-20_15-08-11-681180.pkl` | `research.hypothesis` | `"hypothesis generation" in tag` ✓ |
| `Loop_0.direct_exp_gen.experiment generation.3855634-3857820` | `Loop_0/direct_exp_gen/experiment generation/3855634-3857820/<ts>.pkl` | `research.tasks` | `"experiment generation" in tag` ✓ |
| `Loop_0.direct_exp_gen.token_cost.3855634-3857820` | `Loop_0/direct_exp_gen/token_cost/3855634-3857820/<ts>.pkl` | `token_cost` | `"token_cost" in tag` ✓ |
| `Loop_0.direct_exp_gen.LITELLM_SETTINGS.3855634-3857820` | `Loop_0/direct_exp_gen/LITELLM_SETTINGS/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配任何分支 |
| `Loop_0.direct_exp_gen.debug_tpl.3855634-3857820` | `Loop_0/direct_exp_gen/debug_tpl/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配任何分支 |
| `Loop_0.direct_exp_gen.time_info.3855634-3857820` | `Loop_0/direct_exp_gen/time_info/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配任何分支 |
| `Loop_0.direct_exp_gen.debug_llm.3855634-3857820` | `Loop_0/direct_exp_gen/debug_llm/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配任何分支 |

**关键观察**：

- **没有 `session_<conv_id>` 中间层** —— litellm backend 走底层入口，未经过 [`base.py:316`](../../RD-Agent/rdagent/oai/backend/base.py#L316) 的 `build_chat_completion` wrapper
- **1 个 hypothesis + 1 个 experiment generation** —— `_propose()` 和 `_exp_gen()` 各打 1 次
- **多个 token_cost .pkl** —— 每次 LLM 调用都打一次（hypothesis 生成 + experiment 生成 + 可能的 RAG 查询）

#### 13.2.2 coding 步（编码环节，含 CoSTEER 2 代演化）

| 完整 tag 字符串 | 落盘路径 | 规范化 tag | _obj_to_json 匹配 |
|---|---|---|---|
| `Loop_0.coding.evo_loop_0.evolving code.3855634-3857820` | `Loop_0/coding/evo_loop_0/evolving code/3855634-3857820/2026-07-20_15-15-15-587672.pkl` | `evolving.codes` | `f"evo_loop_0.evolving code" in tag and "running" not in tag` ✓ |
| `Loop_0.coding.evo_loop_0.evolving feedback.3855634-3857820` | `Loop_0/coding/evo_loop_0/evolving feedback/3855634-3857820/<ts>.pkl` | `evolving.feedbacks` | `f"evo_loop_0.evolving feedback" in tag and "running" not in tag` ✓ |
| `Loop_0.coding.evo_loop_1.evolving code.3855634-3857820` | `Loop_0/coding/evo_loop_1/evolving code/3855634-3857820/<ts>.pkl` | `evolving.codes` | 同上（evo_id=1） |
| `Loop_0.coding.evo_loop_1.evolving feedback.3855634-3857820` | `Loop_0/coding/evo_loop_1/evolving feedback/3855634-3857820/2026-07-20_15-17-29-133056.pkl` | `evolving.feedbacks` | 同上（evo_id=1） |
| `Loop_0.coding.coder result.3855634-3857820` | `Loop_0/coding/coder result/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配任何分支（被 `evolving.codes` 取代） |
| `Loop_0.coding.evo_loop_0.token_cost.3855634-3857820` | `Loop_0/coding/evo_loop_0/token_cost/3855634-3857820/<ts>.pkl` | `token_cost` | `"token_cost" in tag` ✓ |
| `Loop_0.coding.evo_loop_0.debug_llm.3855634-3857820` | `Loop_0/coding/evo_loop_0/debug_llm/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配 |

**关键观察**：

- **CoSTEER 跑了 2 代**（evo_loop_0 + evo_loop_1），每代都有 evolving code + evolving feedback
- **evo_id 提取验证**：`extract_evoid("Loop_0.coding.evo_loop_1.evolving code.3855634-3857820")` → `"1"` ✓
- **coder result 被丢弃**：[`rd_loop.py:214`](../../RD-Agent/rdagent/components/workflow/rd_loop.py#L214) 打的 `coder result` 不进消息流，但 pickle 仍在文件系统
- **前端展示**：AgentFlow 卡片会展示 evo_id=0 和 evo_id=1 两代演化产物，每代显示其代码文件 + 反馈

#### 13.2.3 running 步（回测环节）

| 完整 tag 字符串 | 落盘路径 | 规范化 tag | _obj_to_json 匹配 |
|---|---|---|---|
| `Loop_0.running.runner result.3855634-3857820` | `Loop_0/running/runner result/3855634-3857820/2026-07-20_15-19-55-189091.pkl` | `feedback.metric` | `"running" in tag and isinstance(obj, Experiment) and obj.result` ✓ |
| `Loop_0.running.Quantitative Backtesting Chart.3855634-3857820` | `Loop_0/running/Quantitative Backtesting Chart/3855634-3857820/2026-07-20_15-19-55-080179.pkl` | `feedback.return_chart` | `"Quantitative Backtesting Chart" in tag` ✓ |
| `Loop_0.running.Qlib_execute_log.3855634-3857820` | `Loop_0/running/Qlib_execute_log/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配任何分支 |
| `Loop_0.running.time_info.3855634-3857820` | `Loop_0/running/time_info/3855634-3857820/<ts>.pkl` | （被丢弃） | 不匹配 |

**关键观察**：

- **runner result 和 Quantitative Backtesting Chart 时间戳几乎一致**（`15-19-55-189091` vs `15-19-55-080179`）—— 说明它们在 `running.develop()` 中几乎同时打点
- **`"running" in tag` 双重含义**：这里 `Loop_0.running.runner result` 被识别为 `feedback.metric`，但 `Loop_0.coding.evo_loop_*.evolving code` 不会误判（因为 `evolving code` 分支在前且要求 `and "running" not in tag`）
- **前端展示**：MetricsPanel 显示 `feedback.metric.content.result`，ResultWorkspace 的"收益曲线"Tab 显示 `feedback.return_chart.content.chart_html`

#### 13.2.4 feedback 步（反馈环节）

| 完整 tag 字符串 | 落盘路径 | 规范化 tag | _obj_to_json 匹配 |
|---|---|---|---|
| `Loop_0.feedback.feedback.3855634-3857820` | `Loop_0/feedback/feedback/3855634-3857820/2026-07-20_15-20-17-927834.pkl` | `feedback.hypothesis_feedback` | `"feedback" in tag and isinstance(obj, ExperimentFeedback)` ✓ |

**关键观察**：

- **tag 字面值是 `feedback`**，嵌套在 `Loop_0.feedback` 上下文里 → 完整 tag 是 `Loop_0.feedback.feedback`（看起来重复，但前半是 step 名，后半是 tag 字面值）
- **`"feedback" in tag` 子串匹配**会同时命中 `Loop_0.feedback.feedback` 自身（无副作用，因为 elif 顺序）

#### 13.2.5 record 步（仅 time_info）

| 完整 tag 字符串 | 落盘路径 | 规范化 tag |
|---|---|---|
| `Loop_0.record.time_info.3855634-3857820` | `Loop_0/record/time_info/3855634-3857820/<ts>.pkl` | （被丢弃） |

**关键观察**：record 步只打 `time_info`，没有任何业务对象 → 前端无对应展示，PipelineStages 的"反馈"环节 done 判定依赖 `feedback.hypothesis_feedback`（来自 feedback 步），不依赖 record 步。

### 13.3 多轮 loop 对比（Loop 0/1/2）

`plain-transformation` 跑了 3 轮 loop，每轮结构高度一致。以 `evolving code` 为例：

| 轮次 | 完整 tag 字符串 | 落盘路径 | evo_id | loop_id |
|---|---|---|---|---|
| Loop 0, evo 0 | `Loop_0.coding.evo_loop_0.evolving code.3855634-3857820` | `Loop_0/coding/evo_loop_0/evolving code/.../2026-07-20_15-15-15-587672.pkl` | 0 | 0 |
| Loop 0, evo 1 | `Loop_0.coding.evo_loop_1.evolving code.3855634-3857820` | `Loop_0/coding/evo_loop_1/evolving code/.../<ts>.pkl` | 1 | 0 |
| Loop 1, evo 0 | `Loop_1.coding.evo_loop_0.evolving code.3855634-3857820` | `Loop_1/coding/evo_loop_0/evolving code/.../2026-07-20_15-29-47-566054.pkl` | 0 | 1 |
| Loop 2, evo 0 | `Loop_2.coding.evo_loop_0.evolving code.3855634-3857820` | `Loop_2/coding/evo_loop_0/evolving code/.../<ts>.pkl` | 0 | 2 |

**关键观察**：

- **PID 链不变**（都是 `3855634-3857820`）—— 同一进程内多轮 loop
- **每轮 evo_id 从 0 重新计数** —— `evo_loop_0` 是每轮 coding 步内部的局部计数
- **前端筛选**：用户选 loop=1 时，前端按 `message.loop_id === "1"` 过滤，evo_id 0/1 都会展示
- **时间戳递增**：`15-15-15`（Loop 0 evo 0）→ `15-29-47`（Loop 1 evo 0）→ Loop 2 更晚，符合顺序执行

### 13.4 与 baked-yeast 任务对比（未跑完的 loop）

`baked-yeast` 任务只跑了 direct_exp_gen 步就停了（PID 链 `3851031-3853142`）：

| 完整 tag 字符串 | 落盘路径 | 说明 |
|---|---|---|
| `Loop_0.direct_exp_gen.token_cost.3851031-3853142` | `Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_14-59-56-558042.pkl` | 第 1 次 LLM 调用 |
| `Loop_0.direct_exp_gen.token_cost.3851031-3853142` | `Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-00-10-144457.pkl` | 第 2 次 |
| `Loop_0.direct_exp_gen.token_cost.3851031-3853142` | `Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-00-23-241147.pkl` | 第 3 次 |
| ...（共 11 个 token_cost .pkl） | ... | 14:59 ~ 15:01 期间多次 LLM 调用 |
| `Loop_0.direct_exp_gen.time_info.3851031-3853142` | `Loop_0/direct_exp_gen/time_info/3851031-3853142/2026-07-20_15-01-56-907077.pkl` | 步骤结束计时 |

**关键观察**：

- **同一 tag 下多个 .pkl** —— 11 次 LLM 调用都打 `Loop_0.direct_exp_gen.token_cost`，FileStorage 用 timestamp 区分文件名
- **前端只取最新一条** —— `latest(messages, "token_cost")` 返回时间戳最大的那条，所以看板上只显示最后一次的累计 cost
- **无 coding/running/feedback 路径** —— 任务在 direct_exp_gen 步中断，PipelineStages 的"编码/回测/反馈"3 个圆点不会变绿
- **缺少 hypothesis generation / experiment generation** —— 这两个 tag 也没出现在 baked-yeast 的扫描结果中，说明任务在 LLM 调用阶段就失败了（可能是 token 超限或 API 错误）

### 13.5 完整 loop 0 tag 树（实际产物）

```
plain-transformation/Loop_0/
├── direct_exp_gen/                          # tag: Loop_0.direct_exp_gen
│   ├── hypothesis generation/               # → research.hypothesis
│   │   └── 3855634-3857820/<ts>.pkl
│   ├── experiment generation/               # → research.tasks
│   │   └── 3855634-3857820/<ts>.pkl
│   ├── token_cost/                          # → token_cost
│   │   └── 3855634-3857820/<ts>.pkl × N
│   ├── LITELLM_SETTINGS/                    # （被丢弃）
│   ├── debug_llm/                           # （被丢弃）
│   ├── debug_tpl/                           # （被丢弃）
│   └── time_info/                           # （被丢弃）
├── coding/                                  # tag: Loop_0.coding
│   ├── evo_loop_0/                          # tag: Loop_0.coding.evo_loop_0
│   │   ├── evolving code/                   # → evolving.codes (evo_id=0)
│   │   ├── evolving feedback/               # → evolving.feedbacks (evo_id=0)
│   │   ├── token_cost/                      # → token_cost
│   │   ├── debug_llm/                       # （被丢弃）
│   │   └── debug_tpl/                       # （被丢弃）
│   ├── evo_loop_1/                          # tag: Loop_0.coding.evo_loop_1
│   │   ├── evolving code/                   # → evolving.codes (evo_id=1)
│   │   ├── evolving feedback/               # → evolving.feedbacks (evo_id=1)
│   │   ├── token_cost/                      # → token_cost
│   │   ├── debug_llm/                       # （被丢弃）
│   │   └── debug_tpl/                       # （被丢弃）
│   ├── coder result/                        # （被丢弃，被 evolving.codes 取代）
│   └── time_info/                           # （被丢弃）
├── running/                                 # tag: Loop_0.running
│   ├── runner result/                       # → feedback.metric
│   ├── Quantitative Backtesting Chart/      # → feedback.return_chart
│   ├── Qlib_execute_log/                    # （被丢弃）
│   ├── debug_tpl/                           # （被丢弃）
│   └── time_info/                           # （被丢弃）
├── feedback/                                # tag: Loop_0.feedback
│   ├── feedback/                            # → feedback.hypothesis_feedback
│   ├── debug_llm/                           # （被丢弃）
│   ├── debug_tpl/                           # （被丢弃）
│   ├── token_cost/                          # → token_cost
│   └── time_info/                           # （被丢弃）
└── record/                                  # tag: Loop_0.record
    └── time_info/                           # （被丢弃）

plain-transformation/                        # 根目录（无 Loop 前缀）
├── scenario/                                # → feedback.config (loop_id=None)
├── RDLOOP_SETTINGS/                         # （被丢弃）
├── RD_AGENT_SETTINGS/                       # （被丢弃）
└── debug_tpl/                               # （被丢弃）
```

**统计**：

- **进入消息流的 tag**：9 类（research.hypothesis / research.tasks / evolving.codes×2 / evolving.feedbacks×2 / feedback.metric / feedback.return_chart / feedback.hypothesis_feedback / token_cost×N / feedback.config）
- **被丢弃的 tag**：8 类（LITELLM_SETTINGS / debug_llm / debug_tpl / time_info / coder result / Qlib_execute_log / RDLOOP_SETTINGS / RD_AGENT_SETTINGS）
- **被丢弃比例**：约 47%（8/17），说明 `_obj_to_json` 的过滤作用明显

### 13.6 token_cost tag 的多次累积

`baked-yeast` 任务在 direct_exp_gen 步打了 11 次 `token_cost`，时间戳从 `14-59-56` 到 `15-01-55`，约 2 分钟内 11 次 LLM 调用：

| 序号 | 完整路径 | 时间戳 |
|---|---|---|
| 1 | `Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_14-59-56-558042.pkl` | 14:59:56 |
| 2 | `Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-00-10-144457.pkl` | 15:00:10 |
| 3 | `Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-00-23-241147.pkl` | 15:00:23 |
| ... | ... | ... |
| 11 | `Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-01-55-902525.pkl` | 15:01:55 |

**前端行为**：

- `latest(messages, "token_cost")` 返回第 11 条（时间戳最大）
- `content.accumulated_cost` 字段是 litellm 累积值（[`litellm.py:222`](../../RD-Agent/rdagent/oai/backend/litellm.py#L222) 输出 `accumulated_cost`）
- 看板 Token 统计卡片显示的就是第 11 条的 `accumulated_cost`（而非 11 条求和，因为 litellm 内部已累积）

**潜在问题**：如果用户想看每次调用的明细，前端目前不提供（只展示最新一条），需要直接读 pickle 文件。
