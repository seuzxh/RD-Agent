{% raw %}
# 假设转实验智能体（Hypothesis2Experiment）

> **定位**：multialpha R&D 循环的"任务规划师"。位于假设生成（HypothesisGen）与编码进化（CoSTEER）之间，将自然语言描述的抽象假设（如"高换手率因子在震荡市中具有超额收益"）转化为结构化的、可执行的具体任务列表（FactorTask / ModelTask），包括因子名称、描述、数学公式、变量定义、模型架构、超参数等。Hypothesis2Experiment 是连接"创意"与"工程实现"的桥梁，它的输出直接决定了 CoSTEER 需要编写什么代码。

---

## 目录

1. [论文来源与设计理念](#1-论文来源与设计理念)
2. [技术架构](#2-技术架构)
3. [类继承体系](#3-类继承体系)
4. [核心执行流程（LLMHypothesis2Experiment.convert）](#4-核心执行流程llmhypothesis2experimentconvert)
5. [QlibFactorHypothesis2Experiment（因子假设转实验）](#5-qlibfactorhypothesis2experiment因子假设转实验)
6. [QlibModelHypothesis2Experiment（模型假设转实验）](#6-qlibmodelhypothesis2experiment模型假设转实验)
7. [去重与基线构建机制](#7-去重与基线构建机制)
8. [提示词工程](#8-提示词工程)
9. [重试机制](#9-重试机制)
10. [在 R&D 循环中的位置](#10-在-rd-循环中的位置)
11. [配置与模型绑定](#11-配置与模型绑定)
12. [输入输出示例](#12-输入输出示例)
13. [流程图](#13-流程图)

---

## 1. 论文来源与设计理念

Hypothesis2Experiment 的设计来源于以下学术工作：

| 论文/框架 | arXiv/会议 | 核心贡献 |
|-----------|-----------|----------|
| **R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science** | [arXiv:2505.14738](https://arxiv.org/abs/2505.14738) | 整体技术报告，定义了 R&D 循环中从 Hypothesis 到 Experiment 的转换阶段，将抽象假设分解为可执行的任务卡片（implementation cards） |
| **R&D-Agent-Quant** | [arXiv:2505.15155](https://arxiv.org/abs/2505.15155) · NeurIPS 2025 | 量化场景中因子任务卡片和模型任务卡片的具体结构设计，包括因子公式/变量和模型架构/超参数的规范 |
| **Towards Data-Centric Automatic R&D** | [arXiv:2404.11276](https://arxiv.org/abs/2404.11276) | 以数据为中心的自动研发范式，假设到实验的转换是数据驱动验证的前提步骤 |

**设计理念**：

- **抽象到具体的结构化映射**：假设生成阶段输出的是方向性、描述性的研究方向（如"探索动量因子"），而编码阶段需要精确的因子名称、LaTeX 公式和变量定义。Hypothesis2Experiment 通过 LLM 将模糊创意转化为结构化任务规格。
- **任务卡片（Implementation Card）模式**：每个子任务被封装为一张"卡片"，包含完整的实现规格。这使得 CoSTEER 可以并行处理多个子任务（如一次生成 3 个因子），也便于去重和知识检索。
- **历史感知的任务生成**：生成新任务时，会参考历史实验信息，主要目的是**避免重复设计已有的因子/模型**（去重），同时构建基线链让 Runner 能继承历史 SOTA。注意：决定"探索什么方向"是 HypothesisGen 的职责，Hypothesis2Experiment 不负责方向决策。
- **去重即效率**：因子实验中，若新生成的因子名已在历史实验中出现，则自动去重，避免 CoSTEER 重复编写相同因子代码。
- **与假设生成的解耦**：HypothesisGen 负责"做什么方向"，Hypothesis2Experiment 负责"具体做哪几个"。两者使用不同的提示词和输出格式，可以独立优化。

---

## 2. 技术架构

### 2.1 与 HypothesisGen 的职责边界

你可能会注意到：Hypothesis2Experiment 和 HypothesisGen 都采用了相似的四步 LLM 流程（prepare_context → 提示词渲染 → LLM 调用 → convert_response），也都会查询历史 trace。但两者的**核心目的和输入输出完全不同**：

| 维度 | HypothesisGen（假设生成） | Hypothesis2Experiment（假设转实验） |
|------|--------------------------|-----------------------------------|
| **核心问题** | "基于之前的结果，下一轮**探索什么方向**？" | "为了验证这个假设，**具体要实现哪几个因子/模型**？" |
| **输入** | 只有 `trace`（历史实验与反馈） | `hypothesis`（Gen 给出的方向）+ `trace` |
| **参考历史的目的** | 决定研究方向（基于反馈调整策略） | **去重 + 构建基线链**（避免重复造轮子） |
| **输出** | `Hypothesis`：自然语言描述的方向性想法<br>- hypothesis: 假设描述<br>- reason: 推理理由<br>- concise_*: 知识沉淀用简洁版本 | `Experiment`：结构化可执行任务列表<br>- FactorTask[]/ModelTask[]：名称、公式、变量、架构、超参数<br>- based_experiments：历史基线链 |
| **抽象层级** | 战略层：做什么方向 | 战术层：具体怎么做，有完整的实现规格 |
| **类比** | 产品经理决定"这个版本做支付功能" | 技术主管拆解为"实现微信支付、支付宝、银行卡三个接口"，给出接口文档 |

**关键理解**：HypothesisGen 输出的是一个模糊的创意（如"探索换手率因子在震荡市的表现"），CoSTEER 无法直接基于这句话写代码。Hypothesis2Experiment 的职责是将这句话翻译成 CoSTEER 能理解的施工图纸：具体是哪几个因子（TurnoverRate20、TurnoverMomentum...）、每个因子的 LaTeX 公式是什么、用到哪些变量。

查询历史 trace 的目的也完全不同：
- **HypothesisGen**：看之前做了什么、效果如何，决定"下一步往哪走"
- **Hypothesis2Experiment**：看之前已经实现过哪些同名因子，避免重复生成；构建基线链让 Runner 能继承历史 SOTA 因子

### 2.2 Hypothesis2Experiment 执行流程

```
┌──────────────────────────────────────────────────────────────────────┐
│  输入: hypothesis (来自 HypothesisGen) + trace (历史轨迹)             │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│              LLMHypothesis2Experiment.convert()                      │
│              (@wait_retry(retry_n=5))                                │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  1. prepare_context(hypothesis, trace)                      │    │
│  │     (子类实现)                                               │    │
│  │                                                             │    │
│  │  ① 构建场景描述（scenario：接口/数据格式/编码规范）          │    │
│  │  ② 从 trace 中筛选同类型历史实验（仅因子/仅模型）            │    │
│  │     → 目的：让 LLM 知道哪些已经做过，避免重复设计            │    │
│  │  ③ 渲染历史/最近/SOTA 反馈（条件渲染，可为空）                │    │
│  │     → 目的：让 LLM 了解之前的尝试结果，设计更合理的任务       │    │
│  │  ④ 模型场景：设置数据规模约束 RAG 文本                       │    │
│  │     注意：因子场景 RAG = None，前15轮策略属于 HypothesisGen  │    │
│  │  ⑤ 加载输出格式规范（experiment_output_format）              │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  2. 渲染 system/user 提示词                                 │    │
│  │     system: 角色("你需要根据假设生成具体任务") + 场景 + 格式  │    │
│  │     user: 目标假设 + [历史反馈] + [最近反馈] + [SOTA反馈]    │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  3. APIBackend LLM 调用（JSON mode）                        │    │
│  │     json_target_type=dict[str, dict[str, str|dict]]         │    │
│  │     输出: {factor_name: {description, formulation, vars}}   │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  4. convert_response(response, hypothesis, trace)           │    │
│  │     (子类实现，纯代码逻辑，不再调用 LLM)                     │    │
│  │                                                             │    │
│  │  ① JSON 解析                                                │    │
│  │  ② 遍历 JSON key 构建 FactorTask/ModelTask 对象              │    │
│  │  ③ 构建 Experiment 对象（关联传入的 hypothesis）              │    │
│  │  ④ 从 trace.hist 构建 based_experiments 基线链              │    │
│  │  ⑤ 因子去重：跳过已在历史中存在的同名因子                    │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│                                ▼                                     │
│                    返回 Experiment（含 sub_tasks 列表）               │
│                    → 传递给 CoSTEER 为每个 Task 编写代码              │
└──────────────────────────────────────────────────────────────────────┘
```

**核心组件**：

| 组件 | 定义位置 | 职责 |
|------|----------|------|
| `Hypothesis2Experiment` | [proposal.py#L437-L445](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L437-L445) | 抽象基类，定义 `convert(hypothesis, trace)` 接口 |
| `LLMHypothesis2Experiment` | [components/proposal/__init__.py#L86-L121](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L86-L121) | LLM 驱动的转换基类，实现提示词渲染、LLM 调用、重试 |
| `QlibFactorHypothesis2Experiment` | [factor_proposal.py#L61-L132](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L61-L132) | 因子场景实现，生成 FactorTask 列表并去重 |
| `QlibModelHypothesis2Experiment` | [model_proposal.py#L73-L159](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L73-L159) | 模型场景实现，生成 ModelTask 列表 |

---

## 3. 类继承体系

```
Hypothesis2Experiment(ABC, Generic[ASpecificExp])    # rdagent/core/proposal.py
    │
    │  抽象方法: convert(hypothesis, trace) -> Experiment
    │
    └── LLMHypothesis2Experiment(Hypothesis2Experiment)  # components/proposal/__init__.py
            │
            │  属性: targets = "factors" | "model tuning" | ...
            │  方法:
            │    prepare_context(hypothesis, trace) -> (dict, bool)   [抽象]
            │    convert_response(response, hypothesis, trace) -> Exp [抽象]
            │    convert(hypothesis, trace) -> Experiment             [具体, @wait_retry]
            │
            ├── FactorHypothesis2Experiment(LLMHypothesis2Experiment)
            │     targets = "factors"
            │     └── QlibFactorHypothesis2Experiment
            │           # rdagent/scenarios/qlib/proposal/factor_proposal.py
            │
            ├── ModelHypothesis2Experiment(LLMHypothesis2Experiment)
            │     targets = "model tuning"
            │     └── QlibModelHypothesis2Experiment
            │           # rdagent/scenarios/qlib/proposal/model_proposal.py
            │
            └── FactorAndModelHypothesis2Experiment(LLMHypothesis2Experiment)
                  targets = "feature engineering and model building"
```

**设计要点**：

- `Hypothesis2Experiment` 是纯抽象基类，不绑定 LLM，允许未来使用规则引擎等非 LLM 方式实现。
- `LLMHypothesis2Experiment` 封装了通用的 LLM 调用流程（提示词渲染→API 调用→JSON 解析），子类只需实现 `prepare_context` 和 `convert_response` 两个钩子方法。
- `FactorHypothesis2Experiment` 和 `ModelHypothesis2Experiment` 分别设置 `targets` 属性，控制提示词中的目标描述。
- Qlib 场景子类在通用基类基础上增加了场景特定的上下文构建和响应解析逻辑。

---

## 4. 核心执行流程（LLMHypothesis2Experiment.convert）

定义于 [components/proposal/__init__.py#L93-L121](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L93-L121)，使用 `@wait_retry(retry_n=5)` 装饰器包裹。

### 4.1 prepare_context

由子类实现，运行时返回二元组 `(context_dict, json_mode_flag)`：第一个元素是上下文字典，第二个元素是布尔值，传给 LLM 调用的 `json_mode` 参数（因子/模型场景均为 `True`）。

> ⚠️ **类型标注瑕疵**：抽象基类 `LLMHypothesis2Experiment.prepare_context` 标注为 `Tuple[dict, bool]`（[components/proposal/__init__.py#L88](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L88)），但 `QlibFactorHypothesis2Experiment` 的覆盖标注写成了 `Tuple[dict | bool]`（[factor_proposal.py#L61](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L61)）——缺少逗号，会被 Python 解析为"元素类型为 `dict | bool` 的一元组类型"，与实际返回的二元组不符。以运行时实际行为为准。

`context_dict` 包含：

| 键 | 说明 |
|----|------|
| `target_hypothesis` | 目标假设的字符串表示 |
| `scenario` | 子类在 `prepare_context` 中构建的场景描述变量（**注意：此键虽然被返回，但 system prompt 渲染时并不读取它**，详见 4.2） |
| `hypothesis_and_feedback` | 历史假设与反馈（按类型筛选后的 trace） |
| `last_hypothesis_and_feedback` | 最近一轮假设与反馈 |
| `SOTA_hypothesis_and_feedback` | SOTA 实验的假设与反馈（模型场景键名为大写 `SOTA_hypothesis_and_feedback`） |
| `experiment_output_format` | 输出 JSON 格式规范 |
| `target_list` | 始终硬编码为空列表 `[]`，属于死代码（见下文说明） |
| `RAG` | 启发式策略文本（非向量检索，因子场景为 `None`） |

> 🧹 **死代码说明**：`target_list` 在因子/模型两个子类中都被硬编码为 `[]`，并且虽然 `convert()` 把它作为模板变量传入 `user_prompt`，但 `prompts.yaml` 的 user 模板中**并没有 {% raw %}`{{ target_list }}`{% endraw %} 占位符**，因此该变量实际上不会渲染到提示词中。`RAG` 同理被传入 user 模板，但模板中也没有 {% raw %}`{{ RAG }}`{% endraw %} 占位符——模型场景返回的 RAG 文本同样不会出现在最终提示词里。

### 4.2 提示词渲染

**System prompt**（[components/proposal/prompts.yaml#L42-L52](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L42-L52)）：

{% raw %}
```
The user is trying to generate new {{ targets }} based on the hypothesis generated in the previous step.
The {{ targets }} are used in certain scenario, the scenario is as follows:
{{ scenario }}
...
Please generate the output following the format below:
{{ experiment_output_format }}
```
{% endraw %}

> ⚠️ **`scenario` 的实际来源**：模板中的 {% raw %}`{{ scenario }}`{% endraw %} 占位符由基类 `convert()` 直接渲染，传入的值是 `trace.scen.get_scenario_all_desc(filtered_tag=self.targets)`（[components/proposal/__init__.py#L98](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L98)），**并不读取** `context["scenario"]`。子类 `prepare_context` 中构建的 `scenario` 局部变量（例如因子场景调用 `get_scenario_all_desc(action="factor")`）虽然被放进了返回字典，但在 system prompt 渲染时被忽略。两者通常恰好都来自同一个 scenario 对象，只是过滤参数不同（基类用 `filtered_tag=self.targets`，子类用 `action="factor"`/`"model"`）。

**User prompt**（[components/proposal/prompts.yaml#L54-L71](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L54-L71)）：

{% raw %}
```
The target hypothesis you are targeting to generate {{ targets }} for is as follows:
{{ target_hypothesis }}
[历史假设与反馈（条件渲染）]
[最近假设与反馈（条件渲染）]
[SOTA假设与反馈（条件渲染）]
Please generate the new {{ targets }} based on the information above.
```
{% endraw %}

> 📌 **传入但模板未使用的变量**：基类 `convert()` 在渲染 user_prompt 时额外传入了 `target_list=context["target_list"]` 和 `RAG=context["RAG"]`（[components/proposal/__init__.py#L113-L114](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L113-L114)），但该 YAML 模板里既没有 {% raw %}`{{ target_list }}`{% endraw %} 也没有 {% raw %}`{{ RAG }}`{% endraw %} 占位符。Jinja2 对未使用的额外变量静默忽略，因此这两个值（无论因子场景的 `RAG=None` 还是模型场景返回的那段数据规模约束文本）都不会出现在最终发给 LLM 的 user prompt 中。

### 4.3 LLM 调用

```python
resp = APIBackend().build_messages_and_create_chat_completion(
    user_prompt, system_prompt,
    json_mode=json_flag,
    json_target_type=dict[str, dict[str, str | dict]],
)
```

使用 JSON 模式强制 LLM 返回结构化 JSON，目标类型为 `dict[str, dict[str, str | dict]]`，即每个 key 是任务名称，value 是任务属性字典。

### 4.4 convert_response

由子类实现，将 JSON 响应解析为 Task 对象列表并构建 Experiment。

---

## 5. QlibFactorHypothesis2Experiment（因子假设转实验）

定义于 [factor_proposal.py#L61-L132](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L61-L132)。

### 5.1 prepare_context 特殊逻辑

**历史轨迹筛选**（[L72-L83](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L72-L83)）：

从 `trace.hist` 逆序遍历，仅保留因子类型的实验（无 `action` 属性或 `action == "factor"`），构建 `specific_trace`。这确保在量化全流程场景中，模型实验不会干扰因子任务生成——量化场景会交替进行因子和模型实验，Hypothesis2Experiment 需要只参考同类型的历史。

**RAG 策略**（[L91](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L91)）：

```python
"RAG": None,
```

因子场景的 Hypothesis2Experiment **不设置额外的 RAG 启发策略**。

> ⚠️ **注意**："前15轮尝试简单因子、15轮后尝试ML因子"的分阶段策略属于 **HypothesisGen**（[factor_proposal.py#L38-L42](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L38-L42)），用于指导假设生成方向，而非假设转实验。Hypothesis2Experiment 只负责把假设翻译成具体任务，不负责决定探索方向。

### 5.2 convert_response 任务构建

[L94-L132](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L94-L132)：

```python
for factor_name in response_dict:
    description = response_dict[factor_name]["description"]
    formulation = response_dict[factor_name]["formulation"]
    variables = response_dict[factor_name]["variables"]
    tasks.append(FactorTask(
        factor_name=factor_name,
        factor_description=description,
        factor_formulation=formulation,
        variables=variables,
    ))
```

每个因子任务包含：
- `factor_name`：因子名称（JSON key）
- `factor_description`：因子描述（以类型标签开头，如 `[Momentum Factor]`）
- `factor_formulation`：LaTeX 格式的因子公式
- `variables`：变量/函数名到描述的映射

### 5.3 基线链构建

```python
exp.based_experiments = [QlibFactorExperiment(sub_tasks=[])] + [
    t[0] for t in trace.hist if t[1] and isinstance(t[0], FactorExperiment)
]
```

基线链以一个空实验开头，后跟所有**被接受的**（`feedback.decision == True`）历史因子实验。

> ⚠️ **`if t[1]` 的含义**：`ExperimentFeedback.__bool__` 返回 `self.decision`（[proposal.py#L78-L79](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L78-L79)），因此 `if t[1]` 等价于 `if t[1].decision == True`。这意味着 `based_experiments` 只包含历史上被标记为 SOTA（`decision=True`）的因子实验，而非全部历史实验。被拒绝（`decision=False`）的实验不会进入基线链。这使得 Runner 沿链回溯时只会继承已被验证的 SOTA 因子。

### 5.4 因子去重

[L116-L131](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L116-L131)：

```python
unique_tasks = []
for task in tasks:
    duplicate = False
    for based_exp in exp.based_experiments:
        if isinstance(based_exp, QlibModelExperiment):
            continue
        for sub_task in based_exp.sub_tasks:
            if task.factor_name == sub_task.factor_name:
                duplicate = True
                break
        if duplicate:
            break
    if not duplicate:
        unique_tasks.append(task)
exp.tasks = unique_tasks
```

遍历所有基线实验的子任务，若新任务的 `factor_name` 已存在，则跳过。模型实验被排除在去重检查之外（`isinstance(based_exp, QlibModelExperiment)` 时 continue）。

> ⚠️ **`exp.tasks` vs `exp.sub_tasks`**：去重结果赋值给的是 `exp.tasks`（[factor_proposal.py#L131](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L131)），这是一个**动态挂载的属性**，并非 `Experiment` 基类构造函数中声明的字段。`Experiment.sub_tasks` 才是构造时传入、由基类正式声明的任务列表（[experiment.py#L411](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py#L411)）。在 `QlibFactorHypothesis2Experiment.convert_response` 中，`exp = QlibFactorExperiment(tasks, hypothesis=hypothesis)` 把 LLM 生成的**全部**任务作为 `sub_tasks` 传入，因此去重后：
> - `exp.sub_tasks`：仍保留 LLM 本轮生成的全部任务（包括与历史重名的）；
> - `exp.tasks`：去重后的唯一任务列表。
>
> **需要特别注意**：下游 CoSTEER 实际编码时读取的是 `exp.sub_tasks`（见 [evolvable_subjects.py#L29](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolvable_subjects.py#L29) `cls(sub_tasks=exp.sub_tasks)`），并**不读取 `exp.tasks`**。全仓库中 `exp.tasks` 仅在日志记录（`research.tasks` tag）处被引用。因此这里的名称去重结果当前并未实际阻止重复因子进入 CoSTEER 编码流程——真正防止重复因子进入回测的是 Runner 阶段的 IC 去重（`deduplicate_new_factors`）。阅读代码时不要误以为 `exp.tasks` 会替换 `sub_tasks`。

---

## 6. QlibModelHypothesis2Experiment（模型假设转实验）

定义于 [model_proposal.py#L73-L159](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L73-L159)。

### 6.1 prepare_context 特殊逻辑

**历史轨迹筛选**（[L89-L105](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L89-L105)）：

与因子类似，但额外提取最近一轮模型实验（`last_experiment`）和最近一个 SOTA 模型实验（`sota_experiment`，`decision is True`）。

**三层历史上下文**：

| 上下文 | 来源 | 用途 |
|--------|------|------|
| `hypothesis_and_feedback` | 所有模型类型历史实验 | 全局历史视角 |
| `last_hypothesis_and_feedback` | 最近一轮模型实验 | 了解最近尝试 |
| `SOTA_hypothesis_and_feedback` | 最近一个 decision=True 的模型实验 | 对比最优基线 |

> ⚠️ **已知代码 Bug（大写键名不匹配）**：模型 H2E 的 `prepare_context` 返回的键名为大写 `SOTA_hypothesis_and_feedback`（[model_proposal.py#L128](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L128)），但基类 `LLMHypothesis2Experiment.convert()` 读取的是小写 `sota_hypothesis_and_feedback`（[components/proposal/__init__.py#L110-L112](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L110-L112)，使用 `if "sota_hypothesis_and_feedback" in context` 判断）。由于大小写不匹配，`"sota_hypothesis_and_feedback" in context` 为 `False`，基类传入空字符串 `""`，导致 **SOTA 假设与反馈段落实际不会被渲染到 user prompt 中**。`hypothesis_and_feedback` 和 `last_hypothesis_and_feedback` 键名小写正确，不受影响。此 bug 与模型 HypothesisGen 中的同名 bug 一致（见 [01-hypothesis-gen.md](01-hypothesis-gen.md)）。

**RAG 启发策略**（[L131](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L131)）：

```
Note, the training data consists of less than 1 million samples for the training set and
approximately 250,000 samples for the validation set. Please design the hyperparameters
accordingly and control the model size. If you believe that the previous model itself is
good but the training hyperparameters or model hyperparameters are not optimal, you can
return the same model and adjust these parameters instead.
```

模型 RAG 策略关注：
- 数据规模约束（训练集 < 100 万样本，验证集约 25 万），引导控制模型大小
- 允许返回相同模型架构但调整超参数，支持超参数优化场景

> 🧹 如 4.2 节所述，这段 RAG 文本虽然由 `prepare_context` 返回并传入模板渲染，但 user 模板中没有 {% raw %}`{{ RAG }}`{% endraw %} 占位符，因此当前版本实际不会发送给 LLM，属于未生效的预留逻辑。`target_list=[]` 同理。

### 6.2 convert_response 任务构建

[L134-L157](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L134-L157)：

```python
for model_name in response_dict:
    tasks.append(ModelTask(
        name=model_name,
        description=response_dict[model_name]["description"],
        formulation=response_dict[model_name]["formulation"],
        architecture=response_dict[model_name]["architecture"],
        variables=response_dict[model_name]["variables"],
        hyperparameters=response_dict[model_name]["hyperparameters"],
        training_hyperparameters=response_dict[model_name]["training_hyperparameters"],
        model_type=response_dict[model_name]["model_type"],
    ))
```

每个模型任务包含：
- `name`：模型名称
- `description`：模型详细描述
- `formulation`：LaTeX 公式
- `architecture`：架构描述（神经网络层/树结构等）
- `variables`：变量映射
- `hyperparameters`：模型超参数（网络结构相关）
- `training_hyperparameters`：训练超参数（lr、epochs、batch_size 等）
- `model_type`：`"Tabular"` 或 `"TimeSeries"`

### 6.3 与因子转换器的区别

| 维度 | 因子转换器 | 模型转换器 |
|------|-----------|-----------|
| 任务类型 | `FactorTask` | `ModelTask` |
| 输出字段 | name, description, formulation, variables | + architecture, hyperparameters, training_hyperparameters, model_type |
| 每轮任务数 | 可多个因子 | 提示词要求"only design one model" |
| 去重 | 有（按 factor_name） | 无 |
| 基线链 | 空实验 + 所有被接受的因子实验（decision=True） | 所有被接受的模型实验（decision=True），无空实验前缀 |
| SOTA 上下文 | 不单独提取 | prepare_context 中提取，但因大写键名 bug 实际未渲染（见上文说明） |
| RAG 策略 | `None`（不设置；分阶段 RAG 属于 HypothesisGen，不属于 H2E） | 代码中返回数据规模约束 + 超参数调整建议文本，但同样因模板无 {% raw %}`{{ RAG }}`{% endraw %} 占位符而未被渲染 |

---

## 7. 去重与基线构建机制

### 7.1 based_experiments 基线链

`based_experiments` 是一个实验列表，表示当前实验的依赖链：

```
exp.based_experiments = [
    QlibFactorExperiment(sub_tasks=[]),   # [0] 空基线（仅因子场景）
    factor_exp_1,                          # [1] 第一轮被接受的因子实验（decision=True）
    factor_exp_2,                          # [2] 第二轮被接受的因子实验（decision=True）
    ...
]
```

注意：只有 `feedback.decision == True`（即被标记为 SOTA）的实验才会进入基线链，被拒绝的实验不会包含在内。Runner 在执行时会递归执行基线链中未完成的实验（`result is None`），并从中提取 SOTA 因子。这使得每轮实验都能继承历史所有已验证的因子。

### 7.2 去重的意义

> ⚠️ **实际效果说明**：如 5.4 节所述，去重结果赋值给 `exp.tasks`，而 CoSTEER 实际读取的是 `exp.sub_tasks`（未去重），因此**名称去重当前并未阻止重复因子进入 CoSTEER 编码流程**。真正防止重复因子进入回测的是 Runner 阶段的 IC 去重（`deduplicate_new_factors`，阈值 IC ≥ 0.99）。名称去重的结果仅用于日志记录（`research.tasks` tag）。

因子去重（设计意图）确保：
1. 避免与历史 SOTA 因子重名（但由于 `exp.tasks` 未被 CoSTEER 使用，此效果当前未实际生效）
2. Runner 阶段的 IC 去重会处理语义重复因子（IC ≥ 0.99 的因子被剔除），这是真正生效的去重机制
3. 假设生成的探索方向始终是新的

去重仅按 `factor_name` 精确匹配，不做语义相似度判断。若 LLM 生成了语义相同但名称不同的因子，仍会被保留，后续 Runner 的 IC 去重会处理这种情况。

---

## 8. 提示词工程

### 8.1 通用提示词（components/proposal/prompts.yaml）

System prompt 定义角色和输出格式要求，User prompt 组织目标假设和历史信息。提示词使用 Jinja2 模板，条件渲染三个历史段落：

{% raw %}
```
{% if hypothesis_and_feedback %}...{% endif %}
{% if last_hypothesis_and_feedback %}...{% endif %}
{% if sota_hypothesis_and_feedback %}...{% endif %}
```
{% endraw %}

首轮实验时三个段落均为空，LLM 仅基于目标假设生成任务。

### 8.2 因子输出格式

定义于 [qlib/prompts.yaml#L114-L134](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L114-L134)：

```json
{
    "factor name 1": {
        "description": "[Momentum Factor] description...",
        "formulation": "latex formulation",
        "variables": {"var1": "description", "var2": "description"}
    }
}
```

关键要求：
- description 必须以类型标签开头（如 `[Momentum Factor]`、`[Machine Learning based Factor]`）
- formulation 使用 LaTeX 格式
- 不允许添加省略号等可能导致 JSON 解析错误的填充文本

### 8.3 模型输出格式

定义于 [qlib/prompts.yaml#L136-L163](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L136-L163)：

```json
{
    "model_name": {
        "description": "detailed description",
        "formulation": "LaTeX formula",
        "architecture": "neural network layers or tree structures",
        "variables": {"\\hat{y}_u": "predicted output", ...},
        "hyperparameters": {"param1": "value", ...},
        "training_hyperparameters": {
            "n_epochs": "100", "lr": "1e-3", "early_stop": 10,
            "batch_size": 256, "weight_decay": 1e-4
        },
        "model_type": "Tabular or TimeSeries"
    }
}
```

关键要求：
- 明确要求"**only design one model**"（每次只设计一个模型）
- `training_hyperparameters` 的值是参考默认值，LLM 可根据历史训练日志调整
- `model_type` 必须是 `"Tabular"` 或 `"TimeSeries"` 之一

---

## 9. 重试机制

`convert` 方法使用 `@wait_retry(retry_n=5)` 装饰器（[components/proposal/__init__.py#L93](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L93)）：

- `retry_n=5` 表示**在首次调用失败后最多再重试 5 次**，即总共最多尝试 **6 次**（首次 + 5 次重试）。装饰器内部循环为 `for i in range(retry_n + 1)`（[misc.py#L37](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/misc.py#L37)），最后一次（`i == retry_n`）仍失败则抛出异常。
- 当 LLM 返回的 JSON 格式错误或 `convert_response` 抛出异常时触发重试
- 每次重试间有等待间隔（`sleep_time=1` 秒），避免频繁调用 API
- 这对于处理 LLM 偶尔返回格式错误 JSON 的情况至关重要

---

## 10. 在 R&D 循环中的位置

Hypothesis2Experiment 在循环中由 `direct_exp_gen` 步骤调用（[rd_loop.py#L199-L210](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L199-L210)）：

```python
async def direct_exp_gen(self, prev_out: dict[str, Any]):
    while True:
        if self.get_unfinished_loop_cnt(self.loop_idx) < RD_AGENT_SETTINGS.get_max_parallel():
            hypo = self._propose()
            exp = self._exp_gen(hypo)
            exp.base_features = self.plan["features"]
            exp.base_feature_codes = self.plan["feature_codes"]
            if exp.based_experiments:
                exp.based_experiments[-1].base_features = self.plan["features"]
                exp.based_experiments[-1].base_feature_codes = self.plan["feature_codes"]
            return {"propose": hypo, "exp_gen": exp}
        await asyncio.sleep(1)
```

`while True` + `get_unfinished_loop_cnt(...) < get_max_parallel()` 构成一个简单的并发闸门：当正在执行的 loop 数达到 `RD_AGENT_SETTINGS.get_max_parallel()` 上限时，该协程每秒轮询一次，直到有 slot 空出才真正调用 HypothesisGen/H2E。此外，除了 `base_features`（算子形式的基线因子，如 `"RESI5": "Resi($close, 5)/$close"`），还会设置 `base_feature_codes`（代码形式的基线因子），并同步赋值给基线链的最后一个实验（通常是 SOTA），供 Runner 组合回测使用。

在量化全流程（QuantRDLoop）中，根据 `hypothesis.action` 路由到因子或模型转换器（[quant.py#L74-L90](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py#L74-L90)）：

```python
async def direct_exp_gen(self, prev_out):
    while True:
        if self.get_unfinished_loop_cnt(self.loop_idx) < RD_AGENT_SETTINGS.get_max_parallel():
            hypo = self._propose()
            assert hypo.action in ["factor", "model"]
            if hypo.action == "factor":
                exp = self.factor_hypothesis2experiment.convert(hypo, self.trace)
            else:
                exp = self.model_hypothesis2experiment.convert(hypo, self.trace)
            logger.log_object(exp.sub_tasks, tag="experiment generation")
            exp.base_features = self.plan["features"]
            exp.base_feature_codes = self.plan["feature_codes"]
            if exp.based_experiments:
                exp.based_experiments[-1].base_features = self.plan["features"]
                exp.based_experiments[-1].base_feature_codes = self.plan["feature_codes"]
            return {"propose": hypo, "exp_gen": exp}
        await asyncio.sleep(1)
```

注意 QuantRDLoop 用 `assert hypo.action in ["factor", "model"]` 做前置校验，然后用 `if/else`（不是 `if/elif`）二选一路由；与基类一样会设置 `base_features` 与 `base_feature_codes`，并透传给基线链末尾的实验。

输出的 `Experiment` 对象随后传递给 CoSTEER 进行代码生成：

```python
def coding(self, prev_out):
    exp = self.factor_coder.develop(prev_out["direct_exp_gen"]["exp_gen"])
```

---

## 11. 配置与模型绑定

### 11.1 类路径配置

| 配置类 | 字段 | 默认值 |
|--------|------|--------|
| `FactorBasePropSetting` | `hypothesis2experiment` | `rdagent.scenarios.qlib.proposal.factor_proposal.QlibFactorHypothesis2Experiment` |
| `ModelBasePropSetting` | `hypothesis2experiment` | `rdagent.scenarios.qlib.proposal.model_proposal.QlibModelHypothesis2Experiment` |
| `QuantBasePropSetting` | `factor_hypothesis2experiment` | 同上因子转换器 |
| `QuantBasePropSetting` | `model_hypothesis2experiment` | 同上模型转换器 |

### 11.2 LLM 模型绑定

Hypothesis2Experiment 与 HypothesisGen 在同一个 `direct_exp_gen` 步骤中执行，共享该步骤的 logger tag。根据 `.env` 配置：

```json
{"direct_exp_gen": {"model": "openai/minimax-m3", "temperature": "0.7"}}
```

因此 Hypothesis2Experiment 使用 **minimax-m3**（temperature=0.7），与假设生成相同。这是合理的，因为两者都是创造性任务，需要一定的随机性来生成多样化的因子/模型设计。

### 11.3 完整的步骤模型路由

| 步骤 | logger tag | 模型 | temperature |
|------|-----------|------|-------------|
| 假设生成 + 假设转实验 | `direct_exp_gen` | `openai/minimax-m3` | 0.7 |
| 编码进化 | `coding` | `openai/kimi-k2.7-code` | 1.0 |
| 方案执行 | `running` | `openai/deepseek-v4-flash` | 0.0 |
| 反馈 | `feedback` | `openai/glm-5.2` | 0.6 |

---

## 12. 输入输出示例

### 12.1 输入示例

```python
hypothesis = QlibQuantHypothesis(
    hypothesis="High turnover rate factors demonstrate excess returns in volatile markets",
    reason="Recent market volume expansion makes turnover effect significant",
    concise_reason="Volume expansion",
    concise_observation="Turnover anomaly detected",
    concise_justification="Microstructure theory",
    concise_knowledge="Turnover factor",
    action="factor",
)

trace = Trace(hist=[
    (prev_exp_1, prev_feedback_1),  # decision=True (SOTA)
    (prev_exp_2, prev_feedback_2),  # decision=False
])
```

### 12.2 LLM 输出（JSON）

```json
{
    "TurnoverRate20": {
        "description": "[Volume Factor] 20-day average turnover rate measuring trading activity",
        "formulation": "\\frac{1}{20}\\sum_{t=1}^{20}\\frac{Volume_t}{SharesOutstanding_t}",
        "variables": {
            "Volume_t": "Trading volume on day t",
            "SharesOutstanding_t": "Total shares outstanding on day t"
        }
    },
    "TurnoverMomentum": {
        "description": "[Volume Factor] Turnover rate momentum comparing recent vs historical average",
        "formulation": "\\frac{Volume_5}{Volume_{20}} - 1",
        "variables": {
            "Volume_5": "5-day average trading volume",
            "Volume_{20}": "20-day average trading volume"
        }
    }
}
```

### 12.3 输出：Experiment 对象

```python
QlibFactorExperiment(
    sub_tasks=[
        FactorTask(
            factor_name="TurnoverRate20",
            factor_description="[Volume Factor] 20-day average turnover rate...",
            factor_formulation="\\frac{1}{20}\\sum_{t=1}^{20}...",
            variables={"Volume_t": "Trading volume on day t", ...},
        ),
        FactorTask(
            factor_name="TurnoverMomentum",
            factor_description="[Volume Factor] Turnover rate momentum...",
            factor_formulation="\\frac{Volume_5}{Volume_{20}} - 1",
            variables={"Volume_5": "5-day average...", ...},
        ),
    ],
    hypothesis=hypothesis,
    based_experiments=[
        QlibFactorExperiment(sub_tasks=[]),  # 空基线
        prev_exp_1,  # SOTA 因子实验
        prev_exp_2,  # 上一轮因子实验
    ],
)
```

该 Experiment 随后传递给 CoSTEER，CoSTEER 会为每个 FactorTask 生成可运行的 `factor.py` 代码。

### 12.4 模型任务输出示例

```python
QlibModelExperiment(
    sub_tasks=[
        ModelTask(
            name="GRU_Predictor",
            description="GRU-based time series model for return prediction",
            formulation="\\hat{y}_{t+1} = f_{GRU}(x_{t-19:t})",
            architecture="2-layer GRU with hidden_size=64, followed by 2 FC layers",
            variables={"\\hat{y}_{t+1}": "predicted return", "x_t": "factor features"},
            hyperparameters={"hidden_size": "64", "num_layers": "2", "dropout": "0.2"},
            training_hyperparameters={
                "n_epochs": "100", "lr": "1e-3", "early_stop": "10",
                "batch_size": "256", "weight_decay": "1e-4",
            },
            model_type="TimeSeries",
        ),
    ],
    based_experiments=[prev_model_exp_1, ...],
)
```

---

## 13. 流程图

### 13.1 Hypothesis2Experiment 整体流程

```
          ┌─────────────────────┐
          │  HypothesisGen.gen  │
          │  输出 Hypothesis    │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  prepare_context()  │
          │                     │
          │ ① 获取场景描述       │
          │ ② 筛选同类型历史     │
          │ ③ 构建三层历史上下文  │
          │   - all history     │
          │   - last round      │
          │   - SOTA            │
          │ ④ 设置RAG启发策略    │
          │ ⑤ 加载输出格式规范   │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  渲染提示词          │
          │  system + user      │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  LLM 调用 (JSON)    │
          │  minimax-m3         │
          │  temperature=0.7    │
          └──────────┬──────────┘
                     │
              ┌──────┴──────┐
              │ JSON 解析成功？│
              └──┬───────┬───┘
             否 │       │ 是
                ▼       ▼
    ┌──────────────┐ ┌─────────────────────┐
    │ wait_retry   │ │  convert_response() │
    │ 最多重试5次   │ │                     │
    └──────┬───────┘ │ ① 解析JSON         │
           │         │ ② 构建Task列表      │
           │         │ ③ 构建Experiment    │
           │         │ ④ 构建based_exps    │
           │         │ ⑤ 因子去重          │
           │         └──────────┬──────────┘
           │                    │
           └────────┬───────────┘
                    ▼
          ┌─────────────────────┐
          │  Experiment 对象     │
          │  (含 sub_tasks)     │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  CoSTEER.develop()  │
          │  为每个Task生成代码  │
          └─────────────────────┘
```

### 13.2 因子任务生成与去重流程

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM 输出 JSON                             │
│  {                                                           │
│    "Momentum10": {...},                                      │
│    "Turnover20": {...},                                      │
│    "RESI5": {...}   ← 可能与历史因子重名                     │
│  }                                                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ 遍历 JSON key          │
              │ 构建 FactorTask 列表    │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ 构建 based_experiments  │
              │ [空实验] + 所有历史实验  │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ 去重检查               │
              │                        │
              │ 对每个新 task:         │
              │  遍历 based_experiments│
              │   遍历 sub_tasks       │
              │    factor_name 匹配？  │
              └─────────┬──────────────┘
                        │
           ┌────────────┴────────────┐
           │ 是                      │ 否
           ▼                          ▼
    ┌──────────────┐          ┌──────────────┐
    │ 跳过该因子    │          │ 加入唯一列表  │
    │ (不重复编码)  │          │              │
    └──────┬───────┘          └──────┬───────┘
           │                         │
           └────────────┬────────────┘
                        ▼
              ┌────────────────────────┐
              │ exp.tasks = unique_tasks│
              │ 传递给 CoSTEER          │
              └────────────────────────┘
```

### 13.3 在 R&D 闭环中的位置

```
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│ HypothesisGen│───▶│Hypothesis2Exp    │───▶│   CoSTEER    │
│ (假设生成)    │    │(假设转实验)       │    │  (编码进化)   │
│              │    │                  │    │              │
│ minimax-m3   │    │ minimax-m3       │    │ kimi-k2.7-   │
│ temp=0.7     │    │ temp=0.7         │    │ code         │
│              │    │                  │    │ temp=1.0     │
│ 输出:        │    │ 输出:            │    │ 输出:        │
│ Hypothesis   │    │ Experiment       │    │ 可运行代码    │
│ (方向+理由)  │    │ (Task列表+基线)  │    │ (factor.py)  │
└──────────────┘    └──────────────────┘    └──────┬───────┘
                                                   │
                                                   ▼
                                          ┌──────────────┐
                                          │   Runner     │
                                          │ (方案执行)    │
                                          │              │
                                          │ deepseek-v4- │
                                          │ flash        │
                                          │ temp=0.0     │
                                          └──────┬───────┘
                                                 │
                                                 ▼
                                          ┌──────────────┐
                                          │ Summarizer   │
                                          │ (反馈)        │
                                          │              │
                                          │ glm-5.2      │
                                          │ temp=0.6     │
                                          └──────┬───────┘
                                                 │
                                                 ▼
                                          Trace/SOTA 沉淀
                                                 │
                                    ┌────────────┘
                                    ▼
                            反馈传入下一轮 HypothesisGen
                            和 Hypothesis2Experiment
```

{% endraw %}
