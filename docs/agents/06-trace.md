# Trace：实验轨迹与记忆系统

> Trace 是 multialpha R&D 循环的"记忆中枢"——它记录每一轮迭代的完整过程，包括假设、实验、代码、执行结果和反馈，并通过 DAG 结构组织实验演化历史，为后续假设生成和 SOTA 追踪提供数据基础。

---

## 1. 什么是 Trace？

Trace 是贯穿整个 R&D 循环的核心数据结构，它解决以下问题：

1. **历史记忆**：记录从第一轮至今的所有实验及其反馈
2. **SOTA 追踪**：跟踪当前最优实验结果
3. **演化关系**：通过 DAG（有向无环图）表达实验之间的父子继承关系
4. **断点恢复**：序列化为 pickle 文件，支持从中断处恢复运行
5. **知识积累**：为 HypothesisGen 和 CoSTEER 提供历史参考

核心定义位于 [proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L341)。

---

## 2. Trace 数据结构

### 2.1 类定义

```python
class Trace(Generic[ASpecificScen, ASpecificKB]):
    scen: ASpecificScen                          # 场景实例（如Qlib场景）
    hist: list[tuple[Experiment, ExperimentFeedback]]  # 实验历史
    dag_parent: list[tuple[int, ...]]            # DAG父节点索引
    idx2loop_id: dict[int, int]                  # 实验索引→loop轮次映射
    knowledge_base: ASpecificKB | None           # 知识库实例
    current_selection: tuple[int, ...]           # 当前选择的扩展点
```

量化全流程场景使用一个子类 `QuantTrace`（[quant_proposal.py#L16-L20](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L16-L20)）：

```python
class QuantTrace(Trace):
    def __init__(self, scen: Scenario) -> None:
        super().__init__(scen)
        self.controller = EnvController()   # bandit 动作选择控制器，记录指标并决策 factor/model
```

即 `QuantTrace` 在基类基础上仅新增了一个 `controller = EnvController()` 字段，供 bandit 模式的 HypothesisGen 调用 `trace.controller.record(...)` / `trace.controller.decide(...)`。LLM/random 模式下该 controller 不参与决策。

### 2.2 核心字段详解

| 字段 | 类型 | 说明 |
|------|------|------|
| `hist` | `list[tuple[Experiment, ExperimentFeedback]]` | **核心字段**。按时间顺序排列的历史记录，每个元素是 `(实验, 反馈)` 二元组 |
| `dag_parent` | `list[tuple[int, ...]]` | 与 `hist` 一一对应的父节点索引列表。`()` 表示根节点（无父）；非根元素存的是**真实索引**（如 `(0,)`、`(1,)`）。`(-1,)` 只作为 `current_selection` 中的语法糖表示"最新节点"，落盘到 `dag_parent` 前会被解析为真实下标 |
| `idx2loop_id` | `dict[int, int]` | 因为多进程并发执行时 hist 入队顺序可能与 loop_id 不一致，此映射记录每个 hist 索引属于第几轮 |
| `current_selection` | `tuple[int, ...]` | 当前选择的扩展节点，默认 `SEL_LATEST_SOTA = (-1,)` 表示基于最新 SOTA 继续演化 |

### 2.3 类常量

| 常量 | 值 | 含义 |
|------|-----|------|
| `NodeType` | `tuple[Experiment, ExperimentFeedback]` | 历史节点类型别名 |
| `NEW_ROOT` | `()` | 创建全新实验树的根节点标记 |
| `SEL_LATEST_SOTA` | `(-1,)` | 选择最新 SOTA 作为下一轮的基线 |

---

## 3. Experiment 与 Feedback 结构

### 3.1 Experiment（实验）

每个实验包含从假设到执行结果的完整信息（[experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py)）。基类 `Experiment.__init__` 中声明的字段如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `hypothesis` | `Hypothesis \| None` | 该实验基于的研究假设（包含方向和理由） |
| `sub_tasks` | `Sequence[Task]` | 子任务列表（如 `FactorTask` 或 `ModelTask`），每个包含名称、描述、公式、变量 |
| `sub_workspace_list` | `list[FBWorkspace \| None]` | 各子任务的代码工作区，包含实际编写的 Python 代码 |
| `based_experiments` | `Sequence[Experiment]` | 该实验的基线实验（通常是当前 SOTA），新因子会与 SOTA 因子组合 |
| `experiment_workspace` | `Workspace \| None` | 实验级共享工作区 |
| `prop_dev_feedback` | `Feedback \| None` | 跨 developer 传递的反馈（生命周期：上一 developer 赋值，workflow 控制清除） |
| `running_info` | `RunningInfo` | 运行信息对象，含 `result` 和 `running_time`；注意 `result` 是通过该对象暴露的 **property**，不是基类 `__init__` 中直接声明的字段 |
| `sub_results` | `dict[str, float]` | 子结果字典（Kaggle 等场景使用，Qlib 因子场景结果走 `running_info.result`） |
| `local_selection` | `tuple[int, ...] \| None` | 该实验指定的父节点选择（支持分支演化） |
| `plan` | `ExperimentPlan \| None` | 该实验的规划信息（应在 exp_gen 阶段生成） |
| `user_instructions` | `UserInstructions \| None` | 附加到该实验及其子任务/工作区的用户指令 |
| `result`（property） | `object` | **property**：getter 返回 `self.running_info.result`，setter 写入 `self.running_info.result`。执行结果如回测指标 `pd.Series`（包含 IC、年化收益、最大回撤等） |

> ⚠️ **`stdout` 不是基类字段**：`Experiment` 基类并没有声明 `stdout` 属性。`stdout` 是 Qlib 场景子类在各自 `__init__` 中动态添加的——`QlibFactorExperiment`（[factor_experiment.py#L23](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_experiment.py#L23)）和 `QlibModelExperiment`（[model_experiment.py#L22](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/model_experiment.py#L22)）都会初始化 `self.stdout = ""`，随后由 factor_runner/model_runner 在执行后赋值（`exp.stdout = stdout`）。基类实验对象并不保证存在该属性。

### 3.2 FBWorkspace（代码工作区）

每个子任务的代码存储在 FBWorkspace 中（[experiment.py#L139-L169](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py#L139-L169)）：

```python
class FBWorkspace(Workspace):
    file_dict: dict[str, Any]   # {文件名: 文件内容} 字典，值类型为 Any（通常是 str）
    # 例如: {"factor.py": "import pandas as pd\ndef calculate(df):...", "config.yaml": "..."}
    workspace_path: Path        # 工作目录路径（RD-Agent_workspace/<UUID>/）
    ws_ckp: bytes | None        # create_ws_ckp() 生成的内存 zip 检查点（字节）
    change_summary: str | None  # 相对上一版工作区的变更摘要
```

> 说明：`file_dict` 的类型标注是 `dict[str, Any]`（不是 `dict[str, str]`），虽然注入代码时值一般是字符串；`ws_ckp` 由 `create_ws_ckp()` 将工作区目录打包成 zip 字节写入，供 `recover_ws_ckp()` 还原；`change_summary` 用于记录本版相对前版的改动。基类 `Workspace` 还提供 `feedback`（该工作区对应的反馈）和 `running_info` 字段。

代码同时存储在内存（`file_dict`）和磁盘（`workspace_path`），随 pickle 序列化。

### 3.3 ExperimentFeedback（实验反馈）

multialpha 系统中有**两个层级**的反馈，分别对应 R&D 循环的不同阶段：

#### 3.3.1 编码阶段反馈：CoSTEERSingleFeedback（CoSTEER 评估器）

由 [FactorEvaluatorForCoder](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evaluators.py#L20) / ModelEvaluatorForCoder 在**编码-演化循环**中生成。单个子任务的反馈（`CoSTEERSingleFeedback`）最终被赋值到该子任务对应工作区的 `Workspace.feedback` 属性上（[experiment.py#L95](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py#L95)），随 `sub_workspace_list` 一起在 CoSTEER 演化循环中流转，**不会**直接写入 `Trace.hist`（Trace.hist 存的是回测后的 `HypothesisFeedback`）。CoSTEER 内部确实有一个 `EvolvingItem(Experiment, EvolvableSubjects)` 类（[evolvable_subjects.py#L6](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolvable_subjects.py#L6)）作为演化中间载体，但反馈数据本身附着在其 `sub_workspace_list[i].feedback` 上。它通过四级管线评估单个子任务（因子/模型）的代码实现：

| 评估级 | 对应反馈字段 | 评估器 | 评估内容 |
|--------|-------------|--------|---------|
| 执行检查 | `execution_feedback` | `FactorFBWorkspace.execute()` | 代码是否能运行，包含 stdout/stderr 和 traceback，过滤 warning 和超长数值列表 |
| 返回值检查 | `value_feedback` | `FactorValueEvaluator`（条件性组合多个子检查器） | 输出 DataFrame 的格式与数值校验：单列检查、Inf值检查、输出格式LLM判定、日频检查、行数比、索引相似度、缺失值、等值率、IC/RankIC 相关性 |
| **代码评审** | `code_feedback` | `FactorCodeEvaluator` | **LLM 驱动的 Code Review**：检查代码逻辑是否与因子任务描述一致、是否与 GT 代码对齐（如有）、结合执行错误和值差异指出关键问题 |
| 最终决策 | `final_decision` | `FactorFinalDecisionEvaluator` | LLM 综合 execution + value + code 三方信息，输出布尔决策（是否接受该实现） |

> 注意：四个级别并非每次都全部执行。代码中根据值检查结果有三种分支（[evaluators.py#L88-L119](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evaluators.py#L88-L119)）：
> - 值检查明确通过（`decision_from_value_check is True`）：跳过 code review 和 final_decision，直接接受；
> - 值检查明确失败（`decision_from_value_check is False`）：执行 code review 供后续修正参考，但跳过 final_decision，直接拒绝；
> - 值检查结果不明确（`decision_from_value_check is None`）：执行 code review 和 final_decision，由 LLM 综合判断。

**代码评审（Code Review）详细机制**（[FactorCodeEvaluator](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/eva_utils.py#L67-L117)）：

- **输入**：因子任务描述、完整 Python 代码（`all_codes`，排除 test 文件）、执行反馈、值检查反馈、GT 代码（benchmark 模式下提供）
- **Prompt 设计**：系统提示强调"评审意见发送给编码 agent 用于修正代码，不给用户看"，要求：不写代码、只指出关键问题、简短明确、忽略非重要问题、每个批评附改进建议、无问题则返回"No critics found"
- **GT 模式**：有 GT 代码时以 GT 为准检查一致性；无 GT 时检查代码合理性和正确性
- **Token 截断保护**：若 prompt 超 token 限制，自动从 execution_feedback 中部截断（最多 10 次）
- **输出格式**：自由文本，每行一条 critic，格式为 `critic N: <批评内容>`
- **触发条件**：值检查未明确通过时才触发 code review（值检查明确失败 → code review + final_decision=False；值检查不明确 → code review + LLM 最终决策）

**返回值检查（Value Evaluator）的子检查器（条件性执行，并非每次都跑全部）**：

`FactorValueEvaluator.evaluate`（[eva_utils.py#L389-L475](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/eva_utils.py#L389-L475)）根据 `version` 和是否提供 `gt_implementation` **条件性**地调用下列子检查器，最多 9 个：

| 检查器 | 检查内容 | 失败条件 | 执行条件 |
|--------|---------|---------|---------|
| `FactorSingleColumnEvaluator` | 输出是否只有一列（v1 因子） | 列数 ≠ 1 | 仅 `version == 1` |
| `FactorInfEvaluator` | 是否存在 Inf/-Inf 值 | Inf 数量 > 0 | 始终执行 |
| `FactorOutputFormatEvaluator` | LLM 判断输出格式是否正确 | JSON `output_format_decision=false` | 始终执行 |
| `FactorDatetimeDailyEvaluator` | 索引是否为 datetime 且为日频 | 含分钟级数据或非 datetime 索引 | 仅 `version == 1` |
| `FactorRowCountEvaluator` | 行数与 GT 的比率 | ratio ≤ 0.99 | 仅当 `gt_implementation is not None` |
| `FactorIndexEvaluator` | 索引 Jaccard 相似度与 GT | similarity ≤ 0.99 | 仅当 `gt_implementation is not None` |
| `FactorMissingValuesEvaluator` | 缺失值数量是否与 GT 一致 | 缺失值数不等 | 仅当 `gt_implementation is not None` |
| `FactorEqualValueRatioEvaluator` | 等值率（误差 < 1e-6） | ratio 较低 | 仅当 `gt_implementation is not None` |
| `FactorCorrelationEvaluator` | IC/RankIC 与 GT 相关性（hard_check） | IC ≤ 0.99 或 RankIC ≤ 0.99 | 仅当 `gt_implementation is not None` 且 `index_result > 0.99` |

> 因此"7个"与"9个"的说法都不准确：在无 GT（`gt_implementation is None`）时只跑单列(v1)/Inf/输出格式/日频(v1)这几个；在 v1 且提供 GT 时才可能跑满上述 9 个具名检查器，且相关性检查还需索引相似度先达标。`version == 2`（Kaggle 特征处理）不跑单列/日频检查，改以内联消息检查输出列数。

多子任务反馈聚合为 [CoSTEERMultiFeedback](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py#L199-L228)，`final_decision` 取所有子反馈的 AND（全部通过才算通过）。

#### 3.3.2 实验结果反馈：HypothesisFeedback（Summarizer 生成）

由 [QlibFactorExperiment2Feedback](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L54) / QlibModelExperiment2Feedback 在**回测执行后**生成，直接存入 `Trace.hist`。它**不包含 code review**，而是基于回测指标评估假设是否成立：

| 字段 | 类型 | 说明 |
|------|------|------|
| `observations` | `str \| None` | 对实验结果的观察（IC、年化收益、最大回撤等指标对比） |
| `hypothesis_evaluation` | `str \| None` | 对假设的评估（假设方向是否正确、为什么） |
| `new_hypothesis` | `str \| None` | 建议的下一步研究假设 |
| `reason` | `str` | 决策理由的详细推理 |
| `decision` | `bool` | 是否替换当前 SOTA（即本次实验是否超越基线） |
| `acceptable` | `bool \| None` | 是否可接受（由子类 `HypothesisFeedback` 新增，区别于基类 `decision`；Qlib 因子/模型 Summarizer 正常流程中从不设置此字段，始终为默认值 `None`。但**异常分支存在差异**：基类 RDLoop 的 feedback 步骤在异常时设置 `acceptable=False`，而 QuantRDLoop 的异常分支不设置该字段，使用默认值 `None`） |
| `exception` | `Exception \| None` | 若实验因异常未能生成可运行结果，记录异常对象；正常回测时为 `None`（继承自基类 `ExperimentFeedback`） |
| `eda_improvement` | `str \| None` | EDA（探索性数据分析）改进建议（继承自基类 `ExperimentFeedback`，量化反馈生成流程通常不设置） |
| `code_change_summary` | `str \| None` | 代码变更摘要（继承自基类 `ExperimentFeedback`，异常分支中为空字符串） |

**生成过程**：Summarizer 将当前实验结果与 SOTA 结果的关键指标（`IMPORTANT_METRICS` 中的 IC、扣费年化超额收益、扣费最大回撤，见 4.1）拼接成文本，连同假设文本和各子任务信息一起发给 LLM，LLM 以 JSON 模式返回 `observations`、`hypothesis_evaluation`、`new_hypothesis`、`reason`、`decision` 等字段，其中 `decision` 决定是否更新 SOTA。

**异常分支有两套实现，字段差异如下**：

- **基类 `RDLoop.feedback`**（因子/模型场景，见 [rd_loop.py#L222-L236](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L222-L236)）：异常时构造 `HypothesisFeedback(reason=str(e), decision=False, code_change_summary="", acceptable=False)`，异常信息放在 `reason`，`observations` 为 `None`，`acceptable=False`。
- **`QuantRDLoop.feedback`**（全流程场景，见 [quant.py#L111-L128](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py#L111-L128)）：异常时构造 `HypothesisFeedback(observations=str(e), hypothesis_evaluation="", new_hypothesis="", reason="", decision=False)`，异常信息放在 `observations`，`reason` 为空字符串，`acceptable` 未设置（使用默认值 `None`）。

两者均不经过 LLM，且 `decision=False`、`code_change_summary=""`，但 `reason`/`observations`/`acceptable` 的赋值不同，属于代码层面的不一致。

> **关键区别**：CoSTEER 反馈评估的是**代码实现是否正确**（编码阶段，含 code review），HypothesisFeedback 评估的是**研究假设是否成立**（回测阶段，基于指标）。前者决定代码是否需要重写，后者决定研究方向是否调整。

---

## 4. SOTA（State-of-the-Art）追踪机制

### 4.1 SOTA 判定标准

一个实验成为新的 SOTA 当且仅当：
- 该实验的 `HypothesisFeedback.decision == True`
- Summarizer 根据回测指标综合判断

用于 SOTA 判定的关键指标由 `IMPORTANT_METRICS`（[feedback.py#L17-L21](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L17-L21)）明确定义，只有以下 **3 项**：

1. `IC`
2. `1day.excess_return_with_cost.annualized_return`（扣费年化超额收益）
3. `1day.excess_return_with_cost.max_drawdown`（扣费最大回撤）

> ⚠️ **不存在"夏普比率"**：`IMPORTANT_METRICS` 中并没有夏普比率（Sharpe Ratio），SOTA 判定只基于上述 IC、扣费年化收益、扣费最大回撤三项。
>
> 💰 **with_cost vs without_cost**：反馈（Summarizer 的 `factor_feedback_generation` / `model_feedback_generation` 模板）用于 SOTA 判定时取的是 **`with_cost`** 版本指标（见 `process_results` 与模型反馈中 `.loc[IMPORTANT_METRICS]`）；而 `hypothesis_and_feedback`、`last_hypothesis_and_feedback`、`sota_hypothesis_and_feedback` 等模板在向 HypothesisGen/H2E 展示历史结果时，使用的是 **`without_cost`** 版本（[qlib/prompts.yaml#L15](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L15) 等处：`experiment.result.loc[["IC", "1day.excess_return_without_cost.annualized_return", "1day.excess_return_without_cost.max_drawdown"]]`）。也就是说，**决定是否替换 SOTA 看扣费指标，给假设生成看历史时看不扣费指标**，两者刻意区分。

### 4.2 SOTA 查询方法

```python
# 获取当前 SOTA 的假设和实验
hypothesis, sota_exp = trace.get_sota_hypothesis_and_experiment()
```

[get_sota_hypothesis_and_experiment()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L178-L185) 反向遍历 `hist` 列表，返回**最后一个** `decision=True` 的实验。这意味着 SOTA 是线性更新的——新的成功实验会取代旧的 SOTA。

### 4.3 SOTA 的作用

- **基线链**：新实验默认基于 SOTA 生成，新因子会与 SOTA 因子组合后一起回测
- **假设生成**：HypothesisGen 根据 SOTA 结果和历史反馈生成新假设
- **避免重复**：已进入 SOTA 的因子不会再被重复生成（去重机制）
- **对比基准**：Runner 回测时会同时计算 SOTA 表现作为对比

---

## 5. 目录结构与文件存储

### 5.1 三套存储目录

| 存储类型 | 配置项 | 默认路径 | 存储内容 |
|---------|--------|---------|---------|
| **Session 快照** | `LOG_SETTINGS.trace_path` | `log/<UTC时间戳>/` | pickle 序列化的完整 LoopBase 对象 |
| **工作区代码** | `RD_AGENT_SETTINGS.workspace_path` | `git_ignore_folder/RD-Agent_workspace/` | 每个实验的 Python 代码文件 |
| **日志对象** | `LOG_SETTINGS.trace_path` | `log/<UTC时间戳>/<tag.path>/` | FileStorage 的 pickle 日志（hypothesis、feedback 等） |
| **WebUI 聚合** | `UI_SETTING.trace_folder` | `git_ignore_folder/traces/` | WebUI 服务端扫描的任务目录 |

### 5.2 Session 快照目录结构

```
log/2026-08-07_10-30-00-000000/           # LOG_TRACE_PATH（UTC时间戳）
├── __session__/                          # LoopBase 序列化快照
│   ├── 0/                                # 第0轮迭代
│   │   ├── 0_direct_exp_gen              # step_idx=0, 假设+实验生成后
│   │   ├── 1_coding                      # step_idx=1, 代码编写后
│   │   ├── 2_running                     # step_idx=2, 执行回测后
│   │   ├── 3_feedback                    # step_idx=3, 反馈生成后
│   │   └── 4_record                      # step_idx=4, 记录到trace后
│   ├── 1/                                # 第1轮迭代（文件更大，因hist增长）
│   │   ├── 0_direct_exp_gen
│   │   ├── 1_coding
│   │   ├── 2_running
│   │   ├── 3_feedback
│   │   └── 4_record
│   └── N/                                # 第N轮
│
├── direct_exp_gen/                       # FileStorage日志tag目录
│   └── <PID链>/
│       └── <YYYY-MM-DD_HH-MM-SS-ffffff>.pkl
├── coding/
│   └── <PID链>/
│       └── <时间戳>.pkl
├── running/
├── feedback/
└── token_cost/                           # Token消耗记录
```

**文件命名规则**：
- 目录名格式：`<loop_idx>/<step_idx>_<step_name>`
- 每完成一个 step 就 dump 一次，文件大小随轮次增长（因为包含完整 trace.hist）
- 加载时自动选择最新的 session 文件

### 5.3 工作区代码目录

```
git_ignore_folder/RD-Agent_workspace/
├── 031c2a22cc84491f8b72d5aa4db12290/    # UUID命名的工作区
│   ├── factor.py                         # 生成的因子代码
│   ├── config.yaml                       # Qlib配置
│   ├── combined_factors_df.parquet       # 中间数据
│   └── mlruns/                           # mlflow实验记录
├── 0349c86f1b574253980f828dfa7694d7/
└── ...
```

每个 UUID 目录对应一个 Experiment 的工作空间，由 Runner 在执行时创建。

### 5.4 FileStorage 日志文件

调用 `logger.log_object(obj, tag="xxx.yyy")` 时：
1. tag 中的 `.` 替换为路径分隔符 `/`
2. 加上 PID 链（多进程隔离）
3. 文件名为 UTC 微秒时间戳

示例路径：
```
Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-00-45-072528.pkl
```

### 5.5 WebUI 目录结构

```
git_ignore_folder/traces/
├── uploads/                              # 上传文件隔离区
│   └── <scenario>/
│       └── <trace_name>/
│           └── <filename>
├── <scenario>/                           # 场景名称（如"Finance Data Building"）
│   ├── <trace_name>/                     # 任务trace目录
│   │   ├── Loop_0/...                    # FileStorage日志
│   │   ├── RDLOOP_SETTINGS/...
│   │   └── scenario/...
│   └── <trace_name>.log                  # 子进程stdout日志
```

---

## 6. DAG 演化关系

### 6.1 DAG 结构

Trace 不是简单的线性历史，而是通过 `dag_parent` 构成有向无环图。在默认线性演化模式下，每个新节点的父节点是 **hist 中的上一个节点**（不论其 feedback 是否为 True）：

```
轮次0: Exp0(feedback=True)  ← SOTA0
          ↓ dag_parent=(0,)
轮次1: Exp1(feedback=False, based_experiments=[SOTA0])
          ↓ dag_parent=(1,)   ← 注意：父节点是 Exp1（失败节点），不是 Exp0
轮次2: Exp2(feedback=True, based_experiments=[SOTA0])  ← SOTA2
          ↓ dag_parent=(2,)
轮次3: Exp3(feedback=True, based_experiments=[SOTA2])  ← SOTA3
```

> ⚠️ **DAG 父节点 ≠ SOTA 基线**：`dag_parent` 记录的是实验**时序上的前驱**（默认 `(-1,)` 解析为 `len(hist)-1`，即最新入队节点，不看 decision）；而 `based_experiments`（新因子与之组合回测的基线）才取最新 SOTA。两者是不同概念：DAG 表达"从哪个实验继续演化"，based_experiments 表达"和谁对比/组合"。常量名 `SEL_LATEST_SOTA` 有误导性，实际选中的是"最新节点"而非"最新 SOTA 节点"。

### 6.2 sync_dag_parent_and_hist

每次 record 步骤调用 [sync_dag_parent_and_hist()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L256-L284) 追加新节点：

```python
def record(self, prev_out):
    exp = prev_out.get("running") or prev_out.get("coding") or ...
    feedback = prev_out["feedback"]
    self.trace.sync_dag_parent_and_hist((exp, feedback), prev_out[self.LOOP_IDX_KEY])
```

该方法负责在追加 `hist` 的同时计算并写入对应的 `dag_parent`、`idx2loop_id`。它是 record 步骤追加节点的标准入口，但**不是 Trace 被更新的唯一入口**——下列路径也会修改 Trace 状态：

- `Trace.set_current_selection(selection)`：直接改写 `self.current_selection`（[proposal.py#L200-L201](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L200-L201)），用于切换下一轮扩展点；
- QuantTrace 场景下，`QuantTrace.controller`（`EnvController`）由 HypothesisGen 直接读写（如 `trace.controller.record(...)`、`trace.controller.decide(...)`，见 [quant_proposal.py#L57-L58](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L57-L58)）；
- 其它代码路径也可能直接对 `trace.hist` 进行构造/插入（例如 H2E 中创建临时 `specific_trace` 用于渲染提示词，但那是局部对象，不会写回主 trace）。

### 6.3 dag_parent 中存的是实际索引，`(-1,)` 只是 current_selection 的语法糖

`sync_dag_parent_and_hist` 在写入 `dag_parent` 时：

- 根节点写入 `NEW_ROOT = ()`；
- 非根节点读取 `selection[0]` 作为父节点索引，若该值为 `-1`，则在写入**之前**把它替换为 `len(self.hist) - 1`（即当前最新节点的真实索引），再追加 `(current_node_idx,)`。

因此 `dag_parent` 列表中存储的永远是**实际的整数索引**（如 `(0,)`、`(1,)`），而不会出现 `(-1,)`。`(-1,)` 这个值只存在于 `current_selection`（以及 `SEL_LATEST_SOTA` 常量）中，作为"选择最新节点"的语法糖，在真正落盘到 `dag_parent` 时已被解析为真实下标。

### 6.4 支持的演化模式

- **线性演化**：默认模式，`current_selection` 保持 `(-1,)`（最新 SOTA），`sync_dag_parent_and_hist` 把它解析为上一节点的真实索引后写入 `dag_parent`；
- **分支探索**：通过 `exp.local_selection` 或 `set_current_selection` 选择不同父节点分支；
- **回溯恢复**：从 session pickle 加载后继续运行（断点续跑）。

---

## 7. 持久化与恢复

### 7.1 Dump 机制

[LoopBase.dump()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L426-L432) 在每个 step 成功后执行：

```python
def dump(self, path: str | Path) -> None:
    if RD_Agent_TIMER_wrapper.timer.started:
        RD_Agent_TIMER_wrapper.timer.update_remain_time()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(self, f)
```

在 pickle 之前，若全局 `RD_Agent_TIMER_wrapper.timer` 已启动（用于 `all_duration` 总时长预算控制），会先调用 `update_remain_time()` 把剩余时间快照写回 timer，确保反序列化后续跑时能正确继承剩余预算。随后整个 `LoopBase` 对象（包含 `self.trace`）被 pickle 序列化。

### 7.2 Load 机制

[LoopBase.load()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L453-L527) 支持：
- 从目录自动加载最新 session
- Checkout 模式：截断到指定轮次，实现"时光倒流"重新实验
- 断点续跑：从上次中断的 step 继续

### 7.3 不可序列化字段

`__getstate__` 方法排除以下不可 pickle 的字段：
- `queue`（asyncio.Queue）
- `semaphores`（asyncio.Semaphore）
- `_pbar`（tqdm 进度条）
- `multiprocessing.queues.Queue`（用户交互队列）

### 7.4 知识图谱持久化

CoSTEER 的知识库（历史成功/失败实现的向量库）独立于 Trace 存储：
- 路径由配置项 `CoSTEER.knowledge_base_path`（读取旧库）和 `CoSTEER.new_knowledge_base_path`（dump 新库）决定，两者默认值均为 `None`（[config.py#L30-L34](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/config.py#L30-L34)）。未配置时不会从磁盘加载、也不会落盘（`dump_knowledge_base_path is None` 时仅打印 warning 并跳过）。
- 代码中**没有**硬编码 `Path.cwd() / "graph.pkl"` 这样的路径；`graph.pkl` 只是某些部署脚本/示例里可能采用的文件名，并非框架默认行为。
- LoopBase session pickle 中包含的是运行时内存里的 KB 对象引用，但跨运行复用必须显式配置上述路径。

---

## 8. Trace 在 R&D 循环中的流转

```
┌─────────────────────────────────────────────────────────────────┐
│                        Trace (记忆中枢)                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ hist: [(Exp0, FB0), (Exp1, FB1), ..., (ExpN, FBN)]         ││
│  │   │                                                         ││
│  │   ├─→ get_sota_hypothesis_and_experiment() → 最新SOTA       ││
│  │   └─→ 供HypothesisGen读取历史反馈生成新方向                   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────┬───────────────────┬───────────────────┬───────────┘
              │ 读取SOTA+历史     │ 读取SOTA          │
              ▼                   ▼                   ▼
     ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
     │HypothesisGen │    │Hypothesis2Exp│    │   CoSTEER    │
     │ 生成假设方向  │───▶│ 转化为Task   │───▶│ 编写代码      │
     └──────────────┘    └──────────────┘    └──────┬───────┘
                                                    │ 代码
                                                    ▼
                                          ┌──────────────┐
                                          │    Runner    │
                                          │ 执行+回测    │
                                          └──────┬───────┘
                                                 │ 结果
                                                 ▼
                                          ┌──────────────┐
                                          │ Summarizer   │
                                          │ 生成反馈     │
                                          └──────┬───────┘
                                                 │ (exp, feedback)
                                                 ▼
                                          ┌──────────────┐
                                          │   record     │
                                          │ trace.hist.  │
                                          │ append()     │
                                          └──────────────┘
```

**关键观察**：
- Trace 是循环的**共享状态**，几乎每个智能体都从中读取
- 只有 record 步骤写入 Trace（追加新节点）
- 每轮迭代后，Trace 增长约一个 `(Experiment, Feedback)` 二元组

---

## 9. 示例：一次完整的 Trace 记录

假设因子挖掘场景运行 3 轮后，Trace 的内容示意：

```python
trace.hist = [
    # (Experiment, Feedback)
    (Exp0(hypothesis="探索动量类因子", sub_tasks=[FactorTask("MOM_5", ...)]),
     FB0(decision=False, reason="IC值仅0.02，未超越基线")),

    (Exp1(hypothesis="探索换手率因子", sub_tasks=[FactorTask("TURNOVER_20", ...)],
          based_experiments=[SOTA0]),
     FB1(decision=True, reason="IC=0.06, 年化15%, 超越SOTA")),  # → SOTA更新

    (Exp2(hypothesis="优化换手率因子参数", sub_tasks=[FactorTask("TURNOVER_10", ...)],
          based_experiments=[SOTA1]),
     FB2(decision=False, reason="参数优化后IC下降至0.04")),
]

trace.dag_parent = [
    (),        # Exp0: 根节点（无父）
    (0,),      # Exp1: 父节点是 hist[0]（current_selection 中的 (-1,) 在写入时被解析为 0）
    (1,),      # Exp2: 父节点是 hist[1]（current_selection 中的 (-1,) 在写入时被解析为 1）
]
```

> 注意：这里 `dag_parent` 里存的是真实索引 `(0,)`、`(1,)` 而不是 `(-1,)`。`(-1,)` 只出现在 `trace.current_selection`（默认 `SEL_LATEST_SOTA`）中，`sync_dag_parent_and_hist` 写入前会把它替换为 `len(hist) - 1`。

对应的 session pickle 文件大小变化（以下均为**示例值**，实际大小取决于工作区代码、数据与历史长度）：
```
0/0_direct_exp_gen  ~50KB    (空hist)            # 示例值
0/4_record          ~52KB    (1条历史)           # 示例值
1/0_direct_exp_gen  ~470KB   (1条历史)           # 示例值
1/4_record          ~495KB   (2条历史)           # 示例值
2/4_record          ~520KB   (3条历史)           # 示例值
```

---

## 10. SOTA 查询工具

### 10.1 CLI 命令

```bash
rdagent sota --log-path log/2026-08-07_10-30-00-000000
```

[sota_query.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/sota_query.py) 加载 session pickle，提取结构化 SOTA 信息。

### 10.2 WebUI API

```
GET /traces/{trace_name}/sota
```

返回包含 hypothesis、feedback、metrics、factor/model code、workspace 路径的 JSON。

---

## 11. 相关代码索引

| 模块 | 文件路径 |
|------|----------|
| Trace 类定义 | [rdagent/core/proposal.py#L141-L341](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L341) |
| Experiment/Workspace 定义 | [rdagent/core/experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py) |
| RDLoop 五步主循环 | [rdagent/components/workflow/rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py) |
| LoopBase dump/load | [rdagent/utils/workflow/loop.py#L85-L566](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L85-L566) |
| FileStorage pickle存储 | [rdagent/log/storage.py#L28-L115](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/storage.py#L28-L115) |
| 日志配置(trace_path) | [rdagent/log/conf.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/conf.py) |
| SOTA 查询工具 | [rdagent/log/sota_query.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/sota_query.py) |
| 存储路径详细规则 | [docs/architecture/trace-storage-paths.md](file:///home/zxh/projects/1.multialphaV/RD-Agent/docs/architecture/trace-storage-paths.md) |
