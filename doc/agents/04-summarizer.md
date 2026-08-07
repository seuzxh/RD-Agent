# 反馈智能体（Summarizer / Experiment2Feedback）

> **定位**：multialpha R&D 循环的"分析师"与"决策者"。接收 Runner 执行完成的回测结果，通过 LLM 分析当前实验绩效与历史最优（SOTA）的差异，判断本轮假设是否成立、是否应替换 SOTA，并生成下一轮的新假设方向。反馈智能体是闭环迭代的关键枢纽——它的决策直接决定了知识沉淀的方向和后续假设生成的输入。

---

## 目录

1. [论文来源与设计理念](#1-论文来源与设计理念)
2. [技术架构](#2-技术架构)
3. [类继承体系](#3-类继承体系)
4. [核心数据结构](#4-核心数据结构)
5. [QlibFactorExperiment2Feedback（因子反馈）](#5-qlibfactorexperiment2feedback因子反馈)
6. [QlibModelExperiment2Feedback（模型反馈）](#6-qlibmodelexperiment2feedback模型反馈)
7. [指标对比处理](#7-指标对比处理)
8. [提示词工程](#8-提示词工程)
9. [Trace 与 SOTA 检索](#9-trace-与-sota-检索)
10. [异常处理与人工交互](#10-异常处理与人工交互)
11. [配置与模型绑定](#11-配置与模型绑定)
12. [输入输出示例](#12-输入输出示例)
13. [流程图](#13-流程图)

---

## 1. 论文来源与设计理念

反馈智能体的设计来源于以下学术工作：

| 论文/框架 | arXiv/会议 | 核心贡献 |
|-----------|-----------|----------|
| **R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science** | [arXiv:2505.14738](https://arxiv.org/abs/2505.14738) | 整体技术报告，定义了 R&D 循环中 Feedback 阶段的职责：基于实验结果生成假设反馈、决定是否替换 SOTA、引导下一轮探索方向 |
| **R&D-Agent-Quant** | [arXiv:2505.15155](https://arxiv.org/abs/2505.15155) · NeurIPS 2025 | 量化场景中因子反馈与模型反馈的具体提示词设计、SOTA 对比机制，以及基于 annualized return 的替换决策准则 |
| **Towards Data-Centric Automatic R&D** | [arXiv:2404.11276](https://arxiv.org/abs/2404.11276) | 以数据为中心的自动研发范式，反馈环节承担"数据驱动的假设验证与方向修正"职责 |
| **Collaborative Evolving Strategy for Automatic Data-Centric Development (CoSTEER)** | [arXiv:2407.18690](https://arxiv.org/abs/2407.18690) | 协同进化策略中的反馈思想——成功经验与失败教训均被纳入知识管理，反馈决策指导进化方向 |

**设计理念**：

- **数据驱动决策**：反馈不是主观臆断，而是基于真实的回测指标（IC、年化收益、最大回撤等）进行量化对比。LLM 的角色是"读懂数据"而非"创造数据"。
- **SOTA 驱动的迭代**：每轮实验都与历史最优结果对比。只有当新实验在关键指标（年化收益）上取得提升时，才会被标记为新的 SOTA，确保系统始终朝着更优方向进化。
- **假设可证伪**：每个假设都必须经过回测验证。反馈明确给出"支持"或"反驳"假设的结论，未验证的假设不会进入下一轮。
- **失败也是信息**：当实验失败或表现不佳时，反馈不仅标记 `decision=False`，还会生成 `New Hypothesis` 建议转向新方向，避免在无效路径上重复投入。
- **人机协同**：反馈结果在自动模式下直接进入下一轮，在交互模式下可由人工审核和修改，兼顾自动化效率与人类专家判断。

---

## 2. 技术架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                     RDLoop.feedback()                                │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  异常检测：prev_out[EXCEPTION_KEY] 是否存在？                │    │
│  │  ├── 有异常 → 构造 decision=False 的失败反馈                 │    │
│  │  └── 无异常 → 调用 summarizer.generate_feedback(exp, trace) │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│         ┌──────────────────────┼──────────────────────┐              │
│         ▼                      ▼                      ▼              │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │ 异常反馈      │    │ Factor Summarizer│    │ Model Summarizer │   │
│  │ (无 LLM)     │    │ (因子反馈)       │    │ (模型反馈)       │   │
│  └──────┬───────┘    └────────┬─────────┘    └────────┬─────────┘   │
│         │                     │                       │             │
│         │                     ▼                       ▼             │
│         │          ┌─────────────────────────────────────────┐      │
│         │          │  1. 提取假设、任务、回测结果             │      │
│         │          │  2. 从 Trace 获取 SOTA 假设/实验/结果    │      │
│         │          │  3. process_results() 筛选关键指标       │      │
│         │          │  4. 渲染 system/user 提示词              │      │
│         │          │  5. APIBackend LLM 调用 (JSON mode)     │      │
│         │          │  6. 解析 JSON → HypothesisFeedback       │      │
│         │          └────────────────────┬────────────────────┘      │
│         │                               │                           │
│         └───────────────┬───────────────┘                           │
│                         ▼                                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  _interact_feedback(feedback)                               │    │
│  │  交互模式：发送到用户审核队列，等待修改后返回                │    │
│  │  自动模式：直接返回原反馈                                    │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│                                ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  RDLoop.record()                                            │    │
│  │  trace.sync_dag_parent_and_hist((exp, feedback), loop_idx)  │    │
│  │  将 (实验, 反馈) 二元组追加到 Trace.hist，更新 DAG 父子关系  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

**核心组件**：

| 组件 | 定义位置 | 职责 |
|------|----------|------|
| `Experiment2Feedback` | [proposal.py#L451-L471](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L451-L471) | 抽象基类，定义 `generate_feedback(exp, trace)` 接口 |
| `QlibFactorExperiment2Feedback` | [feedback.py#L54-L118](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L54-L118) | 因子实验反馈生成器，对比因子 IC/收益指标 |
| `QlibModelExperiment2Feedback` | [feedback.py#L121-L186](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L121-L186) | 模型实验反馈生成器，对比模型绩效并分析训练日志 |
| `HypothesisFeedback` | [proposal.py#L96-L120](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L96-L120) | 反馈数据结构，含观察、假设评估、新假设、决策 |
| `Trace` | [proposal.py#L141-L255](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L255) | 实验轨迹，维护历史 (实验, 反馈) DAG，提供 SOTA 检索 |
| `process_results` | [feedback.py#L24-L51](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L24-L51) | 指标对比格式化函数，筛选关键指标并生成对比文本 |

---

## 3. 类继承体系

```
Experiment2Feedback(ABC)                    # rdagent/core/proposal.py
    │
    │  抽象方法:
    │    generate_feedback(exp, trace, exception=None) -> ExperimentFeedback
    │
    ├── QlibFactorExperiment2Feedback       # rdagent/scenarios/qlib/developer/feedback.py
    │     # 因子反馈：对比 IC、年化收益、最大回撤
    │     # 决策字段: "Replace Best Result" (yes/no)
    │
    └── QlibModelExperiment2Feedback        # rdagent/scenarios/qlib/developer/feedback.py
          # 模型反馈：对比模型绩效 + 分析训练日志/超参数
          # 决策字段: "Decision" (true/false)
          # 注意：当前实现中 LLM 被调用了两次（第二次结果覆盖第一次）
```

**在 RDLoop 中的注册**：

| 循环类型 | 配置字段 | 默认实现 |
|----------|----------|----------|
| 因子循环 (`FactorRDLoop`) | `summarizer` | `QlibFactorExperiment2Feedback` |
| 模型循环 (`ModelRDLoop`) | `summarizer` | `QlibModelExperiment2Feedback` |
| 量化全流程 (`QuantRDLoop`) | `factor_summarizer` + `model_summarizer` | 根据 `hypothesis.action` 分别路由到因子/模型反馈器 |

---

## 4. 核心数据结构

### 4.1 HypothesisFeedback

定义于 [proposal.py#L96-L120](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L96-L120)，继承自 `ExperimentFeedback`：

```python
class HypothesisFeedback(ExperimentFeedback):
    observations: str | None        # LLM 对实验结果的整体观察
    hypothesis_evaluation: str | None  # 对假设的支持/反驳评估
    new_hypothesis: str | None      # 建议的下一轮新假设
    acceptable: bool | None         # 结果是否可接受（当前未在主流程使用）
    # 继承自 ExperimentFeedback:
    #   reason: str                  # 决策理由
    #   decision: bool               # 是否替换 SOTA
    #   code_change_summary: str     # 代码变更摘要
    #   exception: Exception | None  # 关联异常
```

`decision` 是最关键字段：
- `True`：本轮实验表现优于 SOTA，将被标记为新的 SOTA 基线
- `False`：本轮实验未超越 SOTA，不更新基线，但反馈中的 `new_hypothesis` 仍会引导下一轮方向

### 4.2 Trace（实验轨迹）

定义于 [proposal.py#L141-L255](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L255)：

```python
class Trace:
    hist: list[tuple[Experiment, ExperimentFeedback]]  # 按时间排列的 (实验, 反馈) 列表
    dag_parent: list[tuple[int, ...]]                   # DAG 父节点索引
    idx2loop_id: dict[int, int]                         # 记录索引→循环ID映射
    current_selection: tuple[int, ...]                  # 当前扩展点选择
```

**SOTA 检索方法** [get_sota_hypothesis_and_experiment](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L178-L185)：

```python
def get_sota_hypothesis_and_experiment(self):
    for experiment, feedback in self.hist[::-1]:  # 逆序遍历
        if feedback.decision:  # 找到最近一个 decision=True 的节点
            return experiment.hypothesis, experiment
    return None, None
```

即：**SOTA = 历史上最近一个被标记为 `decision=True` 的实验**。这意味着 SOTA 不一定是全局最优，而是"最后一次被认可的最优"。

### 4.3 关注的核心指标

定义于 [feedback.py#L17-L21](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L17-L21)：

```python
IMPORTANT_METRICS = [
    "IC",                                              # 信息系数
    "1day.excess_return_with_cost.annualized_return",  # 年化超额收益（扣费）
    "1day.excess_return_with_cost.max_drawdown",       # 最大回撤（扣费）
]
```

反馈时仅将这三个核心指标传递给 LLM，避免指标过多导致分析分散。

---

## 5. QlibFactorExperiment2Feedback（因子反馈）

定义于 [feedback.py#L54-L118](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L54-L118)。

### 5.1 执行流程

**① 提取上下文信息**

```python
hypothesis = exp.hypothesis
current_result = exp.result
tasks_factors = [task.get_task_information_and_implementation_result() for task in exp.sub_tasks]
sota_result = exp.based_experiments[-1].result
```

- `hypothesis`：本轮因子假设
- `current_result`：本轮回测指标 Series
- `tasks_factors`：每个子任务的因子名称、描述、公式、变量、实现状态
- `sota_result`：基线实验（SOTA）的回测指标

**② 格式化指标对比**

调用 `process_results(current_result, sota_result)` 生成类似如下文本：

```
IC of Current Result is 0.045000, of SOTA Result is 0.038000;
1day.excess_return_with_cost.annualized_return of Current Result is 0.180000, of SOTA Result is 0.150000;
1day.excess_return_with_cost.max_drawdown of Current Result is -0.120000, of SOTA Result is -0.140000
```

**③ 渲染提示词**

- System prompt：`scenarios.qlib.prompts:factor_feedback_generation.system`，注入场景描述
- User prompt：`scenarios.qlib.prompts:factor_feedback_generation.user`，注入假设文本、任务详情、对比结果

**④ LLM 调用与解析**

```python
response = APIBackend().build_messages_and_create_chat_completion(
    user_prompt=usr_prompt,
    system_prompt=sys_prompt,
    json_mode=True,
    json_target_type=Dict[str, str | bool | int],
)
response_json = json.loads(response)
```

期望的 JSON 结构：

```json
{
  "Observations": "整体观察...",
  "Feedback for Hypothesis": "对假设的评估...",
  "New Hypothesis": "新假设建议...",
  "Reasoning": "推理过程...",
  "Replace Best Result": "yes"
}
```

**⑤ 构造反馈对象**

```python
decision = convert2bool(response_json.get("Replace Best Result", "no"))
return HypothesisFeedback(
    observations=response_json.get("Observations"),
    hypothesis_evaluation=response_json.get("Feedback for Hypothesis"),
    new_hypothesis=response_json.get("New Hypothesis"),
    reason=response_json.get("Reasoning"),
    decision=decision,
)
```

### 5.2 因子反馈的特殊逻辑

- 因子反馈的 SOTA 结果直接来自 `exp.based_experiments[-1].result`，而非通过 `trace.get_sota_hypothesis_and_experiment()` 检索。这是因为因子实验的基线链通过 `based_experiments` 显式维护。
- 提示词中明确告知 LLM："所有超越 SOTA 的因子会被纳入 SOTA 因子库，新因子会与库中因子组合后回测"，这影响了 LLM 对"新方向"vs"优化现有方向"的判断。
- 决策准则：**年化收益有任何小幅提升都应建议替换 SOTA**；其他指标的小幅波动可接受。

---

## 6. QlibModelExperiment2Feedback（模型反馈）

定义于 [feedback.py#L121-L186](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L121-L186)。

### 6.1 执行流程

**① 提取 SOTA 信息**

```python
SOTA_hypothesis, SOTA_experiment = trace.get_sota_hypothesis_and_experiment()
```

与因子反馈不同，模型反馈通过 Trace 逆序查找最近的 `decision=True` 节点获取 SOTA。

**② 构建丰富的对比上下文**

User prompt 中包含：
- SOTA 假设、SOTA 任务描述、SOTA 模型代码（`model.py`）、SOTA 核心指标
- 当前假设、当前任务描述、当前模型代码、训练日志（`exp.stdout`）、当前核心指标

模型反馈比因子反馈多了**代码对比**和**训练日志分析**两个维度，因为模型性能问题可能源于架构设计或超参数设置。

**③ LLM 调用（两次）**

当前实现中 LLM 被调用了两次（[L160-L179](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L160-L179)），第二次结果覆盖第一次。这可能是代码遗留问题，但不影响最终输出——最终使用第二次调用的结果。

期望的 JSON 结构：

```json
{
  "Observations": "首先分析训练日志判断超参数是否有问题，然后总结当前结果与SOTA结果...",
  "Feedback for Hypothesis": "基于具体数据确认或反驳假设...",
  "New Hypothesis": "提出修正后的假设...",
  "Reasoning": "新假设的理由...",
  "Decision": true
}
```

**④ 构造反馈对象**

```python
decision = convert2bool(response_json_hypothesis.get("Decision", "false"))
return HypothesisFeedback(
    observations=...,
    hypothesis_evaluation=...,
    new_hypothesis=...,
    reason=...,
    decision=decision,
)
```

注意：模型反馈的 JSON 决策字段名为 `"Decision"`（布尔值），而因子反馈为 `"Replace Best Result"`（yes/no 字符串）。

### 6.2 首轮特殊处理

当 `SOTA_hypothesis` 为 `None`（首轮实验，无历史 SOTA）时，提示词中会注入特殊指令：

> "This is the first round. No previous information available. As long as the performance is not too negative (eg. ICIR is greater than 0), treat it as successful. Do not set the threshold too high."

首轮降低了 SOTA 替换门槛，避免冷启动问题。

---

## 7. 指标对比处理

定义于 [process_results](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L24-L51)：

```python
def process_results(current_result, sota_result):
    current_df = pd.DataFrame(current_result)
    sota_df = pd.DataFrame(sota_result)
    combined_df = pd.concat([current_df, sota_df], axis=1)
    filtered_combined_df = combined_df.loc[IMPORTANT_METRICS]
    # 格式化为 "metric of Current Result is X, of SOTA Result is Y"
    return format_filtered_combined_df(filtered_combined_df)
```

处理步骤：
1. 将当前结果和 SOTA 结果转为 DataFrame
2. 按指标名拼接为对比表
3. 仅保留 `IMPORTANT_METRICS` 中的三个核心指标
4. 格式化为 LLM 易读的分号分隔文本

该函数仅在因子反馈中使用；模型反馈直接在模板中通过 `exp.result.loc[IMPORTANT_METRICS]` 筛选。

---

## 8. 提示词工程

### 8.1 因子反馈提示词

定义于 [prompts.yaml#L165-L225](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L165-L225)。

**System prompt 核心要点**：
- 角色定位：专业金融结果分析助手
- 解释 SOTA 因子库的运作逻辑（超越 SOTA 的因子会被纳入库中，新因子与库中因子组合回测）
- 开发方向指引：新方向 vs 优化现有方向
- 决策准则：年化收益有小幅提升即建议替换；与 SOTA 差距显著时考虑换方向
- 输出 JSON 格式规范

**User prompt 模板变量**：
- `{{ hypothesis_text }}`：本轮假设文本
- `{{ task_details }}`：任务列表（因子名称、描述、公式、变量、实现状态）
- `{{ combined_result }}`：格式化的指标对比文本

### 8.2 模型反馈提示词

定义于 [prompts.yaml#L227-L273](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L227-L273)。

**System prompt 核心要点**：
- 角色定位：顶级对冲基金的专业量化分析助手
- 要求分析训练日志判断超参数问题
- 各字段有明确的句数限制（Observations ≤ 3 句，其他 ≤ 2 句）
- 输出 JSON 格式规范

**User prompt 模板变量**：
- SOTA 信息（条件渲染）：`sota_hypothesis`、`sota_task`、`sota_code`、`sota_result`
- 当前信息：`hypothesis`（含 reason）、`exp.sub_tasks[0]`、`model.py` 代码、`exp.stdout`（训练日志）、`exp_result`

### 8.3 两种提示词的关键差异

| 维度 | 因子反馈 | 模型反馈 |
|------|----------|----------|
| 分析重点 | 因子 IC/收益对比 | 模型绩效 + 训练日志 + 超参数 + 代码架构 |
| SOTA 来源 | `exp.based_experiments[-1]` | `trace.get_sota_hypothesis_and_experiment()` |
| 决策字段 | `"Replace Best Result"` (yes/no) | `"Decision"` (true/false) |
| 代码对比 | 无（因子代码不在反馈 prompt 中） | 有（SOTA model.py vs 当前 model.py） |
| 训练日志 | 无 | 有（`exp.stdout` 传入 LLM） |
| 首轮策略 | 无特殊指令 | 降低门槛（ICIR > 0 即视为成功） |
| 句数限制 | 无 | 有（各字段限制句数） |

---

## 9. Trace 与 SOTA 检索

### 9.1 Trace 的 DAG 结构

Trace 维护一个有向无环图（DAG），记录实验之间的继承关系：

```
hist = [
    (exp_0, feedback_0),   # 根节点，dag_parent=()
    (exp_1, feedback_1),   # 基于 exp_0，dag_parent=(0,)
    (exp_2, feedback_2),   # 基于 exp_1，dag_parent=(1,)
    (exp_3, feedback_3),   # 新分支，基于 exp_0，dag_parent=(0,)
]
```

每个节点的 `dag_parent` 记录其父节点索引。`based_experiments` 链与 DAG 父节点关系对应。

### 9.2 SOTA 检索逻辑

`get_sota_hypothesis_and_experiment()` 逆序遍历 `hist`，返回**第一个** `feedback.decision == True` 的节点。这意味着：

- SOTA 是"最近一次被认可的最优"，而非"全局历史最优"
- 一旦某个实验被标记为 `decision=True`，它就成为后续所有实验的对比基线，直到被下一个 `decision=True` 的实验取代
- 即使某个更早的实验指标实际更好，只要其后有 `decision=True` 的节点，SOTA 就以最新的为准

### 9.3 记录到 Trace

在 [RDLoop.record()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L238-L241) 中：

```python
def record(self, prev_out):
    feedback = prev_out["feedback"]
    exp = prev_out.get("running") or prev_out.get("coding") or ...
    self.trace.sync_dag_parent_and_hist((exp, feedback), prev_out[self.LOOP_IDX_KEY])
```

` (exp, feedback)` 二元组被追加到 `trace.hist`，DAG 父子关系根据 `based_experiments` 链自动同步。

---

## 10. 异常处理与人工交互

### 10.1 异常反馈

当 Runner 或 CoSTEER 抛出异常（如 `FactorEmptyError`、`ModelEmptyError`、`CoderError`）时，[RDLoop.feedback()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L222-L236) 会拦截异常并构造失败反馈，**不调用 LLM**：

```python
e = prev_out.get(self.EXCEPTION_KEY, None)
if e is not None:
    feedback = HypothesisFeedback(
        reason=str(e),
        decision=False,
        code_change_summary="",
        acceptable=False,
    )
```

在 QuantRDLoop 中（[quant.py#L111-L128](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py#L111-L128)），异常反馈还会填充 `observations` 字段为异常信息。

这些异常类型在循环类的 `skip_loop_error` 中注册：
- 因子循环：`(FactorEmptyError, CoderError)`
- 量化循环：`(FactorEmptyError, ModelEmptyError)`

异常发生时当前轮次被跳过，但循环继续进行下一轮。

### 10.2 人工交互

定义于 [_interact_feedback](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L169-L182)：

```python
def _interact_feedback(self, feedback):
    if not (hasattr(self, "user_request_q") and hasattr(self, "user_response_q")):
        return feedback  # 自动模式，直接返回
    self.user_request_q.put(feedback.__dict__)
    res_dict = self.user_response_q.get()
    return HypothesisFeedback(**res_dict)
```

- **自动模式**（CLI 或 `auto_mode=True`）：无交互队列，反馈直接传递
- **交互模式**（Web UI）：反馈被序列化为 dict 发送到用户审核队列，等待前端返回（可能被人工修改的）反馈 dict，再重构为 `HypothesisFeedback`

这使得用户可以在 Web 界面中查看 LLM 生成的反馈，修改决策（如将 `decision=False` 改为 `True`）或编辑新假设文本。

---

## 11. 配置与模型绑定

### 11.1 类路径配置

| 配置类 | 字段 | 默认值 |
|--------|------|--------|
| `FactorBasePropSetting` | `summarizer` | `rdagent.scenarios.qlib.developer.feedback.QlibFactorExperiment2Feedback` |
| `ModelBasePropSetting` | `summarizer` | `rdagent.scenarios.qlib.developer.feedback.QlibModelExperiment2Feedback` |
| `QuantBasePropSetting` | `factor_summarizer` | `rdagent.scenarios.qlib.developer.feedback.QlibFactorExperiment2Feedback` |
| `QuantBasePropSetting` | `model_summarizer` | `rdagent.scenarios.qlib.developer.feedback.QlibModelExperiment2Feedback` |

### 11.2 LLM 模型绑定

在 `.env` 中通过 `CHAT_MODEL_MAP` 按日志标签路由模型：

```json
{
  "feedback": {
    "model": "openai/glm-5.2",
    "temperature": "0.6"
  }
}
```

路由机制（[litellm.py#L106-L119](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py#L106-L119)）：LLM 调用时遍历 `chat_model_map`，若 key 出当前 logger tag 栈中，则使用对应模型配置。反馈阶段的 logger tag 为 `"feedback"`（在 [rd_loop.py#L235](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L235) 设置）。

选择 GLM-5.2（temperature=0.6）用于反馈的原因：反馈需要稳定的数值分析能力，较低的温度减少幻觉，同时保留一定的创造性以生成多样化的新假设方向。

### 11.3 各智能体模型配置总览

| 阶段 | logger tag | 模型 | temperature |
|------|-----------|------|-------------|
| 假设生成 | `direct_exp_gen` | `openai/minimax-m3` | 0.7 |
| 编码进化 | `coding` | `openai/kimi-k2.7-code` | 1.0 |
| 方案执行 | `running` | `openai/deepseek-v4-flash` | 0.0 |
| **反馈** | **`feedback`** | **`openai/glm-5.2`** | **0.6** |

---

## 12. 输入输出示例

### 12.1 输入示例

```python
# 输入：已执行完成的因子实验
exp = QlibFactorExperiment(
    hypothesis=QlibQuantHypothesis(
        hypothesis="高换手率因子在震荡市中具有超额收益",
        reason="近期市场成交量放大，换手效应显著",
        action="factor",
        ...
    ),
    sub_tasks=[FactorTask(factor_name="Turnover20", ...)],
    sub_workspace_list=[...],  # CoSTEER 生成并执行通过的代码
    based_experiments=[sota_exp],  # 上一轮 SOTA 实验
    result=pd.Series({
        "IC": 0.045,
        "1day.excess_return_with_cost.annualized_return": 0.18,
        "1day.excess_return_with_cost.max_drawdown": -0.12,
        ...
    }),
    stdout="Epoch1: train -0.045, valid -0.038\nbest score: -0.038 @ 15 epoch",
)

trace = Trace(hist=[(sota_exp, sota_feedback), ...])
```

### 12.2 LLM 输出（JSON）

```json
{
  "Observations": "The new turnover factor achieved an IC of 0.045 compared to SOTA's 0.038, an 18% improvement. Annualized return increased from 15% to 18% while max drawdown improved from -14% to -12%. The factor shows consistent predictive power across the test period.",
  "Feedback for Hypothesis": "The results support the hypothesis that high turnover factors generate excess returns in volatile markets. The IC improvement and return enhancement validate the turnover effect.",
  "New Hypothesis": "Explore combining turnover with volatility factors to capture the interaction between trading activity and market uncertainty, potentially enhancing returns further.",
  "Reasoning": "The turnover factor demonstrated robust performance. Combining it with volatility measures could provide orthogonal alpha sources since volume and volatility often co-move but capture different market microstructures.",
  "Replace Best Result": "yes"
}
```

### 12.3 输出：HypothesisFeedback 对象

```python
HypothesisFeedback(
    observations="The new turnover factor achieved an IC of 0.045...",
    hypothesis_evaluation="The results support the hypothesis...",
    new_hypothesis="Explore combining turnover with volatility factors...",
    reason="The turnover factor demonstrated robust performance...",
    decision=True,  # → 本轮实验成为新 SOTA
)
```

### 12.4 异常输入输出

```python
# 输入：Runner 抛出 FactorEmptyError
exception = FactorEmptyError("Factors failed to run on the full sample...")

# 输出：不调用 LLM，直接构造失败反馈
HypothesisFeedback(
    reason="Factors failed to run on the full sample, this round of experiment failed.",
    decision=False,
    code_change_summary="",
    acceptable=False,
    observations=None,
    hypothesis_evaluation=None,
    new_hypothesis=None,
)
```

---

## 13. 流程图

### 13.1 反馈生成整体流程

```
          ┌─────────────────────┐
          │  Runner 执行完成    │
          │  或抛出异常         │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  异常存在？         │
          └───┬─────────────┬───┘
          是  │             │ 否
              ▼             ▼
    ┌─────────────────┐  ┌──────────────────────┐
    │ 构造失败反馈     │  │ 判断实验类型         │
    │ decision=False  │  │ (factor / model)     │
    │ 不调用 LLM      │  └───┬──────────────┬───┘
    └────────┬────────┘  因子 │              │ 模型
             │                ▼              ▼
             │     ┌──────────────────┐ ┌──────────────────┐
             │     │ Factor           │ │ Model            │
             │     │ Summarizer       │ │ Summarizer       │
             │     │                  │ │                  │
             │     │ ① 提取假设/任务  │ │ ① 从Trace取SOTA  │
             │     │ ② 取SOTA结果     │ │ ② 提取SOTA代码/  │
             │     │ ③ process_results│ │ │   指标/假设      │
             │     │ ④ 渲染prompt     │ │ ③ 提取当前代码/  │
             │     │ ⑤ LLM JSON调用   │ │ │   日志/指标      │
             │     │ ⑥ 解析JSON       │ │ ④ 渲染prompt     │
             │     │   "Replace Best  │ │ ⑤ LLM JSON调用   │
             │     │    Result"       │ │ ⑥ 解析JSON       │
             │     └────────┬─────────┘ │   "Decision"     │
             │              │           └────────┬─────────┘
             │              │                    │
             └──────────────┼────────────────────┘
                            ▼
                   ┌─────────────────┐
                   │ HypothesisFeedback│
                   │ - observations   │
                   │ - hypo_evaluation│
                   │ - new_hypothesis │
                   │ - reason         │
                   │ - decision       │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │ 人工交互审核？   │
                   └───┬─────────┬───┘
                   是  │         │ 否
                       ▼         ▼
             ┌────────────┐ ┌────────────┐
             │ 发送到用户  │ │ 直接返回   │
             │ 审核队列    │ │ 原反馈     │
             │ 等待修改    │ │            │
             └─────┬──────┘ └─────┬──────┘
                   │              │
                   └──────┬───────┘
                          ▼
                 ┌─────────────────┐
                 │ RDLoop.record() │
                 │ 写入 Trace.hist │
                 │ 更新 DAG 关系   │
                 └─────────────────┘
```

### 13.2 SOTA 替换决策逻辑

```
                    ┌──────────────────┐
                    │  LLM 输出决策    │
                    │  decision=True?  │
                    └───┬──────────┬───┘
                   是   │          │ 否
                       ▼          ▼
              ┌────────────┐ ┌────────────────────┐
              │ 本轮实验    │ │ 本轮实验未超越SOTA │
              │ 成为新SOTA  │ │                    │
              │            │ │ new_hypothesis 仍  │
              │ 下一轮的    │ │ 会传递给假设生成   │
              │ based_exp   │ │ 引导换方向或优化   │
              │ 指向本轮    │ │                    │
              └────────────┘ └────────────────────┘
```

### 13.3 反馈在 R&D 循环中的位置

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Hypothesis  │───▶│   CoSTEER    │───▶│    Runner    │───▶│  Summarizer  │
│  Generation  │    │   Coding     │    │   Running    │    │   Feedback   │
│              │    │              │    │              │    │              │
│ (minimax-m3) │    │(kimi-k2.7-   │    │(deepseek-v4- │    │  (glm-5.2)   │
│  temp=0.7    │    │  code)       │    │  flash)      │    │  temp=0.6    │
│              │    │  temp=1.0    │    │  temp=0.0    │    │              │
└──────▲───────┘    └──────────────┘    └──────────────┘    └──────┬───────┘
       │                                                           │
       │              ┌──────────────────────────────────────────┘
       │              │
       │              ▼
       │     ┌──────────────────┐
       │     │  Trace / SOTA    │
       │     │  (实验历史+反馈)  │
       │     └────────┬─────────┘
       │              │
       └──────────────┘
          new_hypothesis
          + SOTA context
          引导下一轮方向
```

反馈智能体输出的 `new_hypothesis` 和 `decision` 结果被写入 Trace，成为下一轮假设生成的上下文输入。当 `decision=True` 时，本轮实验成为新的 SOTA 基线，Runner 在下一轮会自动将本轮因子/模型纳入组合；`new_hypothesis` 则为假设生成智能体提供方向建议。这就是 multialpha 持续进化的闭环核心。
