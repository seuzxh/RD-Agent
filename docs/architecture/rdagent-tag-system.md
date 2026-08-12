# Tag 体系

> tag 是 multiα1pha 中每条日志消息的"分类路径"。它决定了消息**存到磁盘的哪个目录**、**以什么格式推送给前端**、以及**在前端哪个位置展示**。

---

## 1. 一句话理解

tag 是一个用 `.` 分隔的字符串，例如：

```
Loop_0.coding.evo_loop_1.evolving code.3855634-3857820
```

它由代码中嵌套的 `with logger.tag(...)` 自动拼接而成，表达了"这条消息来自哪一轮 loop、哪个步骤、哪一代 CoSTEER 演化"。

tag 的三个作用：

| 作用 | 由谁处理 | 做了什么 |
|------|---------|---------|
| **落盘路径** | [FileStorage](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/storage.py) | 把 `.` 替换成 `/`，生成目录路径，每个对象存成一个 `.pkl` |
| **消息格式** | [WebStorage._obj_to_json](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/storage.py#L66-L300) | 按 tag 中的关键字匹配，决定如何把 Python 对象序列化成前端消息 |
| **前端展示** | 前端 `trace-model.ts` | 按规范化后的 tag（如 `research.hypothesis`）取最新消息渲染到对应面板 |

---

## 2. tag 是怎么拼出来的

### 2.1 嵌套上下文

tag 通过 `ContextVar` 在协程/线程中累积。进入 `with logger.tag("xxx")` 时自动追加，退出时自动还原：

```python
with logger.tag("Loop_0"):
    # 当前 tag = "Loop_0"
    with logger.tag("coding"):
        # 当前 tag = "Loop_0.coding"
        with logger.tag("evo_loop_1"):
            # 当前 tag = "Loop_0.coding.evo_loop_1"
            logger.log_object(workspaces, tag="evolving code")
            # 最终 tag = "Loop_0.coding.evo_loop_1.evolving code.3855634-3857820"
```

实现见 [logger.py#L91-L104](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/logger.py#L91-L104)。`ContextVar` 保证了协程安全——不同 asyncio task 的 tag 互不干扰。

### 2.2 三个层级

一个完整的 tag 由三部分组成：

```
Loop_0.coding.evo_loop_1.evolving code.3855634-3857820
└──────┬──────┘ └──────────┬──────────┘ └─────┬────┘ └──────┬──────┘
   上下文 tag         上下文 tag          一次性 tag      PID 链
(LoopBase 打)     (EvolvingAgent 打)   (log_object 传)  (自动追加)
```

| 层级 | 来源 | 说明 |
|------|------|------|
| `Loop_{n}.{step}` | [loop.py#L218](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L218) | 主循环命名空间。step 固定为 `direct_exp_gen`/`coding`/`running`/`feedback`/`record` |
| `evo_loop_{n}` | [evolving_agent.py#L146](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L146) | CoSTEER 演化代次，只在 `coding` 步内出现，每轮从 0 开始 |
| 业务 tag | 各业务代码的 `log_object(tag=...)` | 标记消息类型，如 `hypothesis generation`、`evolving code` |
| `{pid}-{ppid}-...` | [logger.py#L117-L130](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/logger.py#L117-L130) | 自动追加的进程链，用于区分子进程 |

> **注意**：`log_object` 的 tag 参数不是替换而是追加。内部实现是 `f"{self._tag}.{tag}.{pid_chain}"`（[logger.py#L133](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/logger.py#L133)），所以不需要自己拼前缀。

---

## 3. tag → 磁盘路径

FileStorage 把 tag 中的 `.` 替换为路径分隔符，每个对象存为带时间戳的 `.pkl` 文件：

```python
cur_p = self.path / tag.replace(".", "/")
path = cur_p / f"{timestamp}.pkl"
```

实现见 [storage.py#L38-L66](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/storage.py#L38-L66)。

示例：

| 完整 tag | 磁盘路径 |
|---------|---------|
| `Loop_0.direct_exp_gen.hypothesis generation.3855634-3857820` | `Loop_0/direct_exp_gen/hypothesis generation/3855634-3857820/2026-07-20_15-08-11.pkl` |
| `Loop_0.coding.evo_loop_0.evolving code.3855634-3857820` | `Loop_0/coding/evo_loop_0/evolving code/3855634-3857820/<ts>.pkl` |
| `RDLOOP_SETTINGS.3855634-3857820` | `RDLOOP_SETTINGS/3855634-3857820/<ts>.pkl` |

tag 中的空格（如 `hypothesis generation`）会原样保留在目录名中。同一个 tag 下可以有多个 `.pkl`（按时间戳区分），例如多次 LLM 调用产生的多个 `token_cost`。

---

## 4. tag → 前端消息（核心）

这是 tag 体系最关键的一环。[WebStorage._obj_to_json](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/storage.py#L66-L300) 是一个按顺序匹配的 if-elif 链，它根据 tag 中是否包含某些关键字，决定如何把 Python 对象转成前端能识别的 JSON 消息。

### 4.1 匹配规则总表

| tag 包含关键字 | 规范化 tag | 对象类型 | 前端用途 |
|---------------|-----------|---------|---------|
| `hypothesis generation` | `research.hypothesis` | `Hypothesis` | 假设面板 |
| `experiment generation` 或 `load_experiment` | `research.tasks` | `list[FactorTask/ModelTask]` | 任务列表 |
| `pdf_image` 或 `load_pdf_screenshot` | `research.pdf_image` | 图片 | PDF 截图 |
| `evo_loop_{n}.evolving code`（且不含 `running`） | `evolving.codes` | `list[FBWorkspace]` | 代码文件 |
| `evo_loop_{n}.evolving feedback`（且不含 `running`） | `evolving.feedbacks` | `list[Feedback]` | 演化反馈 |
| `scenario` | `feedback.config` | `Scenario` | 配置面板 |
| `Quantitative Backtesting Chart` | `feedback.return_chart` | plotly 图表 | 收益曲线 |
| `running`（且对象是 Experiment 且 result 非空） | `feedback.metric` | `Experiment.result` | 回测指标 |
| `feedback`（且对象是 ExperimentFeedback） | `feedback.hypothesis_feedback` | `HypothesisFeedback` | 反馈详情 |
| `token_cost` | `token_cost` | dict | Token 统计 |

### 4.2 匹配是"子串包含"而非"相等"

后端用的是 Python 的 `in` 操作符：

```python
if "hypothesis generation" in tag:
    ...
elif f"evo_loop_{ei}.evolving code" in tag and "running" not in tag:
    ...
elif "running" in tag:
    ...
```

这意味着：

- `Loop_0.direct_exp_gen.hypothesis generation.3855634-3857820` 能匹配 `"hypothesis generation" in tag` ✓
- 匹配是**顺序敏感**的，第一个命中的分支生效
- `evolving code` 分支特意加了 `and "running" not in tag`，防止 CoSTEER 内部运行时的消息被误判为回测指标

### 4.3 loop_id 和 evo_id 的提取

在匹配之前，`_obj_to_json` 会先用正则从 tag 中提取两个 ID：

```python
li, fn = extract_loopid_func_name(tag)   # 提取 Loop_<n> 和 step 名
ei = extract_evoid(tag)                   # 提取 evo_loop_<n>
```

实现见 [log/utils/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/utils/__init__.py)：

- `extract_loopid_func_name`：正则 `Loop_(\d+)\.([^.]+)`，返回 `(loop_id, step_name)`
- `extract_evoid`：正则 `evo_loop_(\d+)\.`，返回 `evo_id`

这两个 ID 会被塞进消息体，前端据此筛选当前选中的 loop 和演化代次。

### 4.4 未匹配的消息会被丢弃

如果 tag 不包含上述任何关键字，`_obj_to_json` 返回空 dict，WebStorage 输出 `"Normal log, skipped"`，**该消息不会推送给前端**。常见被丢弃的 tag：

| tag | 原因 |
|-----|------|
| `coder result` | 被 `evolving.codes` 取代 |
| `RDLOOP_SETTINGS` / `RD_AGENT_SETTINGS` / `LITELLM_SETTINGS` | 配置快照只落盘 |
| `llm_messages` | LLM 请求/响应文本 |
| `Qlib_execute_log` | Qlib 执行日志 |
| `debug_llm` / `debug_tpl` / `time_info` | 调试日志 |

这些消息的 `.pkl` 文件仍然在磁盘上，可以通过 trace 加载查看，但前端不会展示。

---

## 5. 前端如何消费

前端用 `latest(messages, tag)` 函数按**规范化 tag 完整相等**取最新一条：

```typescript
function latest(messages: TraceMessage[], tag: string) {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].tag === tag) return messages[i]
  }
}
```

这里有一个重要区别：

- **后端**：用子串包含匹配**原始 tag**（`"hypothesis generation" in tag`）
- **前端**：用完整相等匹配**规范化 tag**（`message.tag === "research.hypothesis"`）

所以前端只认识 `research.hypothesis`、`evolving.codes` 等规范化名称，不关心原始 tag 中的 `Loop_0`、`evo_loop_1` 等前缀。loop/evo 的筛选通过消息体中的 `loop_id`/`evo_id` 字段完成。

### 5.1 前端识别的规范化 tag

| 规范化 tag | 前端位置 |
|-----------|---------|
| `research.hypothesis` | 研究阶段：假设文本 |
| `research.tasks` | 研究阶段：因子/模型任务列表 |
| `research.pdf_image` | 研究阶段：PDF 截图（研报场景） |
| `evolving.codes` | 编码阶段：代码文件（按 evo_id 分组） |
| `evolving.feedbacks` | 编码阶段：演化反馈（按 evo_id 分组） |
| `feedback.metric` | 回测阶段：指标表格 |
| `feedback.return_chart` | 回测阶段：收益曲线图 |
| `feedback.hypothesis_feedback` | 反馈阶段：LLM 反馈详情 |
| `feedback.config` | 顶部：任务配置 |
| `token_cost` | 顶部：Token 花费 |
| `END` | 任务完成标记 |

---

## 6. 一个完整 loop 的 tag 流转

以因子挖掘第 0 轮为例，5 个步骤依次产生以下消息：

```
Loop_0.direct_exp_gen
├── hypothesis generation    → research.hypothesis     （假设生成）
├── experiment generation    → research.tasks          （因子任务列表）
└── token_cost ×N            → token_cost              （LLM 调用统计）

Loop_0.coding
├── evo_loop_0
│   ├── evolving code        → evolving.codes (evo=0)  （第0代代码）
│   ├── evolving feedback    → evolving.feedbacks (evo=0)
│   └── token_cost ×N
├── evo_loop_1
│   ├── evolving code        → evolving.codes (evo=1)  （第1代代码，若需要修复）
│   ├── evolving feedback    → evolving.feedbacks (evo=1)
│   └── token_cost ×N
└── coder result             → （丢弃）

Loop_0.running
├── runner result            → feedback.metric         （回测指标）
├── Quantitative Backtesting Chart → feedback.return_chart （收益曲线）
└── Qlib_execute_log         → （丢弃）

Loop_0.feedback
├── feedback                 → feedback.hypothesis_feedback （LLM 反馈）
└── token_cost

Loop_0.record
└── time_info                → （丢弃）
```

### 6.1 几个容易混淆的点

**Q: 为什么 `feedback` 出现了两次？**

`Loop_0.feedback` 中的第一个 `feedback` 是**步骤名**（RDLoop 的第4步），第二个 `feedback` 是 `log_object(feedback, tag="feedback")` 传入的**业务 tag**。拼在一起就是 `Loop_0.feedback.feedback`，看起来重复但含义不同。

**Q: evo_id 每轮都从 0 开始吗？**

是的。`evo_loop_0` 是每轮 `coding` 步内部的局部计数，不跨轮累积。Loop 1 的 coding 步也会从 `evo_loop_0` 开始。

**Q: token_cost 为什么有多个 .pkl？**

每次 LLM 调用都会打一次 `token_cost`。同一个 tag 路径下，FileStorage 用时间戳区分不同次调用。前端只取最新一条显示累计花费。

**Q: `session_{conv_id}` 在哪里？**

[base.py#L316](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/base.py#L316) 中定义了 `session_{conversation_id}` 上下文 tag，但实际走 litellm backend 时不经过该 wrapper，所以实际产物中通常看不到这一层。

### 6.2 evo_loop 的执行粒度

一个常见误解是：每个 evo_loop 只处理一个因子，如果有 10 个因子、max_loop=5，就会执行 50 次。**实际并非如此。**

每个 evo_loop 处理的是**当前实验中的全部因子**，而不是逐个因子。关键代码在 [CoSTEER/__init__.py#L129](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/__init__.py#L129)：

```python
logger.log_object(evo_exp.sub_workspace_list, tag="evolving code")
```

`sub_workspace_list` 是一个列表，包含所有因子的 workspace。因此 `evolving.codes` 消息的内容是一个列表，10 个因子就有 10 个元素。

以 10 个因子、max_loop=5 为例：

```
coding 步开始，调用 CoSTEER.develop(experiment)  （experiment 含10个因子）
│
├── evo_loop_0  ── 同时为10个因子生成代码，一起运行、一起评估
│   ├── evolving code     → [因子0, 因子1, ..., 因子9]  ← 一个列表，10个元素
│   ├── evolving feedback → [通过, 失败, 通过, ..., 失败]
│   └── 假设3个失败，7个通过
│
├── evo_loop_1  ── 只修复那3个失败的因子（通过的7个直接复用，不再调LLM）
│   ├── evolving code     → [因子0, 因子1', ..., 因子9]  ← 部分更新
│   ├── evolving feedback → [通过, 通过, ..., 失败]
│   └── 还剩1个失败
│
├── evo_loop_2  ── 修复最后1个
│   └── 全部通过 → feedback.finished() = True → 提前 break
│
└── 结束（实际只跑了3轮，不是5轮，更不是50轮）
```

终止条件有两个（[evolving_agent.py#L196-L198](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L196-L198)）：

1. **全部因子通过** → `feedback.finished()` 返回 True，提前退出
2. **达到 max_loop 上限**（如5）→ 强制结束，未通过的因子保留最近一次可接受的版本（fallback 机制）

所以实际 evo_loop 轮数取决于代码质量，通常远小于 max_loop。

### 6.3 evo_loop 与遗传算法的关系

CoSTEER 的名字虽然包含"Evolutionary"，但它**不是传统意义上的遗传算法**。代码中没有染色体交叉（crossover）、随机变异（mutation）、锦标赛选择等经典遗传算子。它的"进化"本质是 **RAG 增强的 LLM 迭代纠错循环**。

不过，两者在概念上确实有对应关系，可以帮助理解：

| 遗传算法概念 | CoSTEER 中的对应机制 | 区别 |
|-------------|---------------------|------|
| **种群** | 一个 `EvolvingItem` 中的多个 `sub_tasks`（多个因子） | 不是多种群竞争，而是单个体内多个子任务并行修复 |
| **适应度（Fitness）** | `final_decision`（bool）+ 回测指标 | 只有通过/不通过的二元判断，没有连续适应度分数 |
| **选择（Selection）** | 每轮开始时任务三分类：已成功→复用，失败超限→淘汰，其余→修复 | 由 RAG 知识库和上轮反馈决定，不是概率选择 |
| **变异（Mutation）** | LLM 根据反馈生成修正代码 | 是**定向修复**而非随机变异，提示词明确要求"基于上一轮修改，不要推倒重来" |
| **交叉（Crossover）** | RAG 检索到的相似成功实现注入 prompt | LLM 借鉴参考代码，不做字面拼接 |
| **精英保留（Elitism）** | fallback 机制：每轮保存可接受版本的快照，退化时回退 | 保留最后一个通过的版本，防止越改越差 |

核心循环见 [evolving_agent.py#L145-L198](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L145-L198)，每轮做三件事：

1. **RAG 查询**：检索相似成功代码、相似错误修复对、历史失败轨迹
2. **LLM 修复**：把"上一轮代码 + 错误反馈 + 参考知识"喂给 LLM，生成修正版
3. **评估**：运行代码，收集反馈，判断是否全部通过

用一句话概括：**evo_loop 是"写代码 → 跑代码 → 看报错 → 让 LLM 改"的迭代循环，不是遗传算法中的代际进化。** 它借用了"进化"的隐喻（逐代改进、适者生存），但驱动力是 LLM 的代码理解能力 + RAG 知识检索，而非随机搜索。

---

## 7. 设计上的注意事项

### 7.1 子串匹配的脆弱性

`_obj_to_json` 用 `in` 做子串匹配，理论上存在误命中风险。目前的安全保障：

- `"running"` 分支依赖 `isinstance(obj, Experiment)` 类型检查兜底
- `"scenario"` 只在初始化时打一次
- `evolving code` 分支显式排除了 `running`

如果未来新增 tag，应注意避免与现有关键字冲突。

### 7.2 没有 evo_loop 前缀的 evolving code 会被丢弃

`evolving.codes`/`evolving.feedbacks` 的匹配条件是 `f"evo_loop_{ei}.evolving code" in tag`。如果 `extract_evoid(tag)` 返回 `None`，则匹配串变成 `evo_loop_None.evolving code`，永远不会命中，消息被静默丢弃。因此 CoSTEER 演化中的 `log_object` 必须在 `with logger.tag(f"evo_loop_{n}")` 上下文内调用。

### 7.3 tag 中空格的处理

业务 tag 如 `"hypothesis generation"`、`"evolving code"`、`"Quantitative Backtesting Chart"` 都含空格。这在三个环节中都正常工作：

- FileStorage：空格原样进入目录名（Linux 支持）
- `_obj_to_json`：用 `in` 匹配，空格无影响
- 前端：只看规范化 tag（无空格），不受影响
