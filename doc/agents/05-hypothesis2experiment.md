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
- **历史感知的任务生成**：生成新任务时，会参考历史假设与反馈、最近一轮实验结果、SOTA 实验信息，避免重复已有因子/模型，并根据历史反馈调整方向。
- **去重即效率**：因子实验中，若新生成的因子名已在历史实验中出现，则自动去重，避免 CoSTEER 重复编写相同因子代码。
- **与假设生成的解耦**：HypothesisGen 负责"做什么方向"，Hypothesis2Experiment 负责"具体做哪几个"。两者使用不同的提示词和输出格式，可以独立优化。

---

## 2. 技术架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                     RDLoop.direct_exp_gen()                          │
│                     hypothesis2experiment.convert(hypo, trace)       │
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
│  │  ① 构建场景描述（scenario）                                  │    │
│  │  ② 从 trace 中筛选同类型历史实验                             │    │
│  │  ③ 渲染 hypothesis_and_feedback（历史轨迹）                  │    │
│  │  ④ 渲染 last_hypothesis_and_feedback（最近一轮）             │    │
│  │  ⑤ 渲染 SOTA_hypothesis_and_feedback（最优实验）             │    │
│  │  ⑥ 设置 RAG 启发策略文本                                    │    │
│  │  ⑦ 加载输出格式规范（experiment_output_format）              │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  2. 渲染 system/user 提示词                                 │    │
│  │     system: 角色 + 场景描述 + 输出格式                       │    │
│  │     user: 目标假设 + 历史反馈 + 最近反馈 + SOTA反馈          │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  3. APIBackend LLM 调用（JSON mode）                        │    │
│  │     json_target_type=dict[str, dict[str, str|dict]]         │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  4. convert_response(response, hypothesis, trace)           │    │
│  │     (子类实现)                                               │    │
│  │                                                             │    │
│  │  ① JSON 解析                                                │    │
│  │  ② 遍历 JSON key 构建 Task 对象                              │    │
│  │  ③ 构建 Experiment 对象（关联 hypothesis）                   │    │
│  │  ④ 从 trace.hist 构建 based_experiments 基线链              │    │
│  │  ⑤ 因子去重：跳过已存在的因子名                              │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│                                ▼                                     │
│                    返回 Experiment（含 sub_tasks 列表）               │
│                    → 传递给 CoSTEER 进行编码                         │
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

由子类实现，返回 `(context_dict, json_flag)` 元组。`context_dict` 包含：

| 键 | 说明 |
|----|------|
| `target_hypothesis` | 目标假设的字符串表示 |
| `scenario` | 场景描述（背景、接口、数据格式等） |
| `hypothesis_and_feedback` | 历史假设与反馈（按类型筛选后的 trace） |
| `last_hypothesis_and_feedback` | 最近一轮假设与反馈 |
| `SOTA_hypothesis_and_feedback` | SOTA 实验的假设与反馈 |
| `experiment_output_format` | 输出 JSON 格式规范 |
| `target_list` | 历史相似任务列表（当前为空列表 `[]`） |
| `RAG` | 启发式策略文本（非向量检索，见下文） |

### 4.2 提示词渲染

**System prompt**（[components/proposal/prompts.yaml#L42-L52](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L42-L52)）：

```
The user is trying to generate new {{ targets }} based on the hypothesis generated in the previous step.
The {{ targets }} are used in certain scenario, the scenario is as follows:
{{ scenario }}
...
Please generate the output following the format below:
{{ experiment_output_format }}
```

**User prompt**（[components/proposal/prompts.yaml#L54-L71](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L54-L71)）：

```
The target hypothesis you are targeting to generate {{ targets }} for is as follows:
{{ target_hypothesis }}
[历史假设与反馈（条件渲染）]
[最近假设与反馈（条件渲染）]
[SOTA假设与反馈（条件渲染）]
Please generate the new {{ targets }} based on the information above.
```

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

从 `trace.hist` 逆序遍历，仅保留因子类型的实验（无 `action` 属性或 `action == "factor"`），构建 `specific_trace`。这确保在量化全流程场景中，模型实验不会干扰因子任务生成。

**RAG 启发策略**（[L91](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L91)）：

```python
"RAG": (
    "Try the easiest and fastest factors to experiment with from various perspectives first."
    if len(trace.hist) < 15
    else "Now, you need to try factors that can achieve high IC (e.g., machine learning-based factors)."
),
```

注意：这里的 `RAG` 不是向量检索，而是根据迭代轮次动态调整的启发式策略文本：
- 前 15 轮：鼓励从多种角度尝试简单快速的因子（广泛探索）
- 15 轮后：引导尝试高 IC 因子，如机器学习类因子（深度挖掘）

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

基线链以一个空实验开头，后跟所有历史因子实验。这使得 Runner 可以沿链回溯获取 SOTA 因子。

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
| 基线链 | 空实验 + 所有因子实验 | 所有模型实验 |
| SOTA 上下文 | 不单独提取 | 单独提取 last 和 SOTA |
| RAG 策略 | 按轮次分阶段（探索/深挖） | 数据规模约束 + 超参数调整建议 |

---

## 7. 去重与基线构建机制

### 7.1 based_experiments 基线链

`based_experiments` 是一个实验列表，表示当前实验的依赖链：

```
exp.based_experiments = [
    QlibFactorExperiment(sub_tasks=[]),   # [0] 空基线（仅因子场景）
    factor_exp_1,                          # [1] 第一轮因子实验
    factor_exp_2,                          # [2] 第二轮因子实验
    ...
]
```

Runner 在执行时会递归执行基线链中未完成的实验（`result is None`），并从中提取 SOTA 因子。这使得每轮实验都能继承历史所有已验证的因子。

### 7.2 去重的意义

因子去重确保：
1. CoSTEER 不会重复编写已有因子代码，节省 LLM 调用
2. Runner 不会因重复因子导致 IC 去重时全部被剔除（IC ≥ 0.99）
3. 假设生成的探索方向始终是新的

去重仅按 `factor_name` 精确匹配，不做语义相似度判断。若 LLM 生成了语义相同但名称不同的因子，仍会被保留，后续 Runner 的 IC 去重会处理这种情况。

---

## 8. 提示词工程

### 8.1 通用提示词（components/proposal/prompts.yaml）

System prompt 定义角色和输出格式要求，User prompt 组织目标假设和历史信息。提示词使用 Jinja2 模板，条件渲染三个历史段落：

```
{% if hypothesis_and_feedback %}...{% endif %}
{% if last_hypothesis_and_feedback %}...{% endif %}
{% if sota_hypothesis_and_feedback %}...{% endif %}
```

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

- 最多重试 5 次
- 当 LLM 返回的 JSON 格式错误或 `convert_response` 抛出异常时触发重试
- 重试间有等待间隔（`wait`），避免频繁调用 API
- 这对于处理 LLM 偶尔返回格式错误 JSON 的情况至关重要

---

## 10. 在 R&D 循环中的位置

Hypothesis2Experiment 在循环中由 `direct_exp_gen` 步骤调用：

```python
async def direct_exp_gen(self, prev_out):
    hypo = self._propose()                           # HypothesisGen
    exp = self.factor_hypothesis2experiment.convert(  # Hypothesis2Experiment
        hypo, self.trace
    )
    exp.base_features = self.plan["features"]
    return {"propose": hypo, "exp_gen": exp}
```

在量化全流程（QuantRDLoop）中，根据 `hypothesis.action` 路由到因子或模型转换器：

```python
if hypo.action == "factor":
    exp = self.factor_hypothesis2experiment.convert(hypo, self.trace)
elif hypo.action == "model":
    exp = self.model_hypothesis2experiment.convert(hypo, self.trace)
```

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
