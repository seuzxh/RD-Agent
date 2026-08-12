---
layout: default
title: Prompt 模板系统
permalink: /agents/07-prompts.html
---
{% raw %}

# Prompt 模板系统

> multialpha 的所有 LLM 调用均通过 **Jinja2 模板 + YAML 配置**驱动。本文档系统梳理项目中 12 个 `prompts.yaml` 文件、约 40 个 prompt 模板的作用、变量、渲染示例及调用链路。

---

## 1. 架构总览

### 1.1 Prompt 加载与渲染机制

multialpha 使用自研的 [RDAT 模板类](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/agent/tpl.py#L85-L148)（简称 `T`）统一管理 prompt 的加载和渲染：

```python
from rdagent.utils.agent.tpl import T

# 加载并渲染 prompt
system_prompt = T(".prompts:hypothesis_gen.system_prompt").r(
    targets="factors",
    scenario=scen.get_scenario_all_desc(),
)
```

**两步工作流**：

1. **加载**（`__init__`）：通过 URI 定位 YAML 文件并提取模板字符串
2. **渲染**（`.r(**context)`）：使用 Jinja2 将 `{{ variable }}` 和 `{% if %}` 等替换为实际值

### 1.2 URI 语法

| URI 格式 | 含义 | 示例 |
|---------|------|------|
| `.prompts:key.subkey` | 相对于调用者所在目录的 `prompts.yaml`，取 `key.subkey` | `T(".prompts:hypothesis_gen.system_prompt")` → 加载当前目录的 prompts.yaml |
| `a.b.c:x.y.z` | 相对于 `rdagent/` 包根目录的 `a/b/c.yaml` | `T("scenarios.qlib.experiment.prompts:qlib_factor_background")` |
| `a.b.c` (ftype="txt") | 加载 `a/b/c.txt` 纯文本 | 用于代码模板文件 |

### 1.3 文件查找优先级

对于同一个 URI，`RDAT` 按以下顺序查找文件（高优先级在前）：

1. 调用者目录（`.` 前缀的相对路径）
2. `rdagent/app_tpl/` 应用覆盖目录（由 `RD_AGENT_SETTINGS.app_tpl` 配置）
3. 当前工作目录下的对应路径
4. `rdagent/` 包内默认路径

### 1.4 Prompt 文件清单

| 文件路径 | Prompt 数量 | 所属模块 |
|---------|------------|---------|
| [components/proposal/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml) | 2 组 + 1 个 action | 假设生成 & 假设转实验（通用） |
| [scenarios/qlib/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml) | 14 个 | Qlib 场景历史链渲染、输出格式、场景规范 |
| [components/coder/CoSTEER/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/prompts.yaml) | 1 个 | CoSTEER 组件索引分析 |
| [components/coder/factor_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/prompts.yaml) | 10 个 | 因子编码、评估、演化、筛选 |
| [components/coder/model_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/prompts.yaml) | 5 个 | 模型编码、评估 |
| [scenarios/qlib/experiment/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml) | 17 个 | Qlib 场景背景、接口、输出格式、模拟器描述 |
| [scenarios/qlib/factor_experiment_loader/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml) | 9 个 | PDF 研报因子抽取、分类、可行性/相关性/去重检查 |
| [app/qlib_rd_loop/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/prompts.yaml) | 1 组 | 研报场景假设生成 |
| [utils/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/prompts.yaml) | 1 组 | stdout 日志过滤 |
| [components/agent/context7/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/agent/context7/prompts.yaml) | 3 个 | Context7 文档查询增强 |

---

## 2. 假设生成阶段（HypothesisGen）

### 2.1 `hypothesis_gen` — 核心假设生成 Prompt

**文件**：[components/proposal/prompts.yaml#L1-L39](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L1-L39)

**调用者**：[HypothesisGen.gen()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L36-L60)

**作用**：指导 LLM 基于历史实验反馈，生成下一轮的研究假设（因子方向或模型架构方向）。

**System Prompt 模板变量**：

| 变量 | 类型 | 说明 |
|------|------|------|
| `targets` | str | 研究目标，因子场景为 `"factors"`，模型场景为 `"model tuning"` |
| `scenario` | str | 场景描述，由 `scen.get_scenario_all_desc()` 生成 |
| `user_instruction` | str \| None | 用户全局指令（来自 ExperimentPlan），可为空 |
| `hypothesis_specification` | str \| None | 场景定制规范（因子/模型各有不同），控制探索策略 |
| `hypothesis_output_format` | str | JSON 输出 schema 定义 |

**User Prompt 模板变量**：

| 变量 | 类型 | 说明 |
|------|------|------|
| `hypothesis_and_feedback` | str | 完整历史链渲染结果（可能很长） |
| `last_hypothesis_and_feedback` | str \| None | 最近一轮详情，含 stdout 和新假设建议 |
| `sota_hypothesis_and_feedback` | str \| None | SOTA 实验详情 |
| `RAG` | str \| None | 检索增强生成内容（分阶段策略提示等） |

**渲染示例**（因子场景首轮）：

```text
[System]
The user is working on generating new hypotheses for the factors in a data-driven research and development process.
The factors are used in the following scenario:
The factor is a characteristic or variable used in quant investment...
[场景描述，由 qlib_factor_background + qlib_factor_interface + ... 拼接]

The user has already proposed several hypotheses...
To assist you in formulating new hypotheses, the user has provided some additional information:
1. **1-5 Factors per Generation:** ...
2. **Simple and Effective Factors First:** ...
[factor_hypothesis_specification 的内容]

Please generate the output using the following format and specifications:
The output should follow JSON format. The schema is as follows:
{"hypothesis": "...", "reason": "..."}

[User]
It is the first round of hypothesis generation. The user has no hypothesis on this scenario yet.
```

### 2.2 `action_gen` — Quant 场景动作选择

**文件**：[components/proposal/prompts.yaml#L274-L300](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L274-L300)

**作用**：仅用于 **Quant 全流程场景**，决定下一轮探索因子（`"factor"`）还是模型（`"model"`）。因子和模型场景不使用此 prompt。

**输出格式**：

```json
{ "action": "factor" }
```

---

## 3. 假设转实验阶段（Hypothesis2Experiment）

### 3.1 `hypothesis2experiment` — 假设转任务 Prompt

**文件**：[components/proposal/prompts.yaml#L41-L71](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L41-L71)

**调用者**：[Hypothesis2Experiment.gen()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L96-L115)

**作用**：将 HypothesisGen 生成的抽象假设，转化为结构化的可执行任务列表（FactorTask 或 ModelTask）。此阶段**不做方向决策**，只负责"拆解施工图纸"。

**与 hypothesis_gen 的关键区别**：

| 维度 | hypothesis_gen | hypothesis2experiment |
|------|---------------|----------------------|
| 目的 | 决定研究方向 | 将假设拆解为具体任务 |
| 历史查询 | 为方向决策提供依据 | 为去重和构建基线链提供参考 |
| RAG | 可能注入分阶段策略 | 不注入探索策略 |
| 输出 | `{hypothesis, reason}` | `{factor_name: {description, formulation, variables}}` |

**System Prompt 变量**：

| 变量 | 说明 |
|------|------|
| `targets` | 同 hypothesis_gen |
| `scenario` | 同 hypothesis_gen |
| `experiment_output_format` | 因子或模型的 JSON schema |

**User Prompt 变量**：

| 变量 | 说明 |
|------|------|
| `target_hypothesis` | 本轮要转化的目标假设（核心输入） |
| `hypothesis_and_feedback` | 历史链（用于去重） |
| `last_hypothesis_and_feedback` | 最近一轮（同上） |
| `sota_hypothesis_and_feedback` | SOTA 详情（同上） |

**渲染示例**：

```text
[System]
The user is trying to generate new factors based on the hypothesis generated in the previous step.
The factors are used in certain scenario, the scenario is as follows:
[场景描述]

Please generate the output following the format below:
The output should follow JSON format. The schema is as follows:
{
    "factor name 1": {
        "description": "[Momentum Factor] description...",
        "formulation": "\\frac{C_t - C_{t-5}}{C_{t-5}}",
        "variables": {"C_t": "Close price on day t", ...}
    }
}

[User]
The target hypothesis you are targeting to generate factors for is as follows:
"Explore momentum reversal factors using 5-20 day windows..."

Please generate the new factors based on the information above.
```

---

## 4. 历史链渲染模板

这些模板定义了如何将 Trace 中的实验历史序列化为 LLM 可读的文本，是 hypothesis_gen 和 hypothesis2experiment 的 `hypothesis_and_feedback` 等变量的内容来源。

**文件**：[scenarios/qlib/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml)

### 4.1 `hypothesis_and_feedback` — 完整历史链

**位置**：[L1-L21](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L1-L21)

**作用**：遍历 `trace.hist` 中所有实验，渲染每一轮的假设、子任务摘要、回测指标、观察、评估和决策。

**模板结构**：

```jinja2
{% for experiment, feedback in trace.hist %}
# Trial {{ loop.index }}:
## Hypothesis
{{ experiment.hypothesis }}
## Specific task:
{% for task in experiment.sub_tasks %}
  {{ task.get_task_brief_information() }}
{% endfor %}
## Backtest Analysis and Feedback:
Backtest Result: {{ experiment.result.loc[["IC", "annualized_return", "max_drawdown"]] }}
Observation: {{ feedback.observations }}
Hypothesis Evaluation: {{ feedback.hypothesis_evaluation }}
Decision: {{ feedback.decision }}
{% endfor %}
```

### 4.2 `last_hypothesis_and_feedback` — 最近一轮详情

**位置**：[L23-L43](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L23-L43)

与完整历史链相比，额外包含：
- `experiment.stdout`：训练日志（用于诊断训练问题）
- `feedback.new_hypothesis`：Summarizer 建议的新假设（仅供参考，可采纳或拒绝）
- `feedback.reason`：新假设的推理依据

### 4.3 `sota_hypothesis_and_feedback` — SOTA 详情

**位置**：[L45-L61](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L45-L61)

渲染当前最优实验的完整信息，作为基线对比参考。

---

## 5. 输出格式与场景规范

**文件**：[scenarios/qlib/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml)

### 5.1 输出格式模板

| 模板名 | 位置 | 适用场景 |
|--------|------|---------|
| `hypothesis_output_format` | [L63-L68](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L63-L68) | 通用假设输出 |
| `factor_hypothesis_output_format` | [L70-L75](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L70-L75) | 因子假设输出 |
| `hypothesis_output_format_with_action` | [L77-L83](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L77-L83) | Quant 场景（含 action 字段） |
| `factor_experiment_output_format` | [L114-L134](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L114-L134) | 因子任务 JSON schema（名称、描述、LaTeX 公式、变量） |
| `model_experiment_output_format` | [L136-L163](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L136-L163) | 模型任务 JSON schema（架构、超参、训练参数、model_type） |

### 5.2 场景规范模板

| 模板名 | 位置 | 核心策略 |
|--------|------|---------|
| `factor_hypothesis_specification` | [L95-L112](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L95-L112) | 1-5 个因子/轮；先简单后复杂；ML 因子在积累足够结果后引入；避免重复 SOTA 因子 |
| `model_hypothesis_specification` | [L85-L93](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L85-L93) | 聚焦 PyTorch 架构；从小模型开始；连续失败时转向新方向；目标达到顶会创新水平 |

---

## 6. 反馈总结阶段（Summarizer）

### 6.1 `factor_feedback_generation`

**文件**：[scenarios/qlib/prompts.yaml#L165-L225](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L165-L225)

**作用**：分析因子回测结果，与 SOTA 对比，生成观察、假设评估、新假设建议和替换决策。

**System Prompt 要点**：
- 角色设定：专业金融结果分析助手
- SOTA 因子库逻辑：超过 SOTA 的因子被累积，新因子与库中因子组合回测
- 决策规则：年化收益有提升即建议替换 SOTA（"Replace Best Result": "yes"）
- 方向切换：与 SOTA 差距大时建议探索新因子类型

**输出格式**：

```json
{
  "Observations": "整体观察...",
  "Feedback for Hypothesis": "对假设的验证结论...",
  "New Hypothesis": "建议的新假设...",
  "Reasoning": "新假设的推理依据...",
  "Replace Best Result": "yes"
}
```

### 6.2 `model_feedback_generation`

**文件**：[scenarios/qlib/prompts.yaml#L227-L273](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L227-L273)

**作用**：分析模型回测结果和训练日志，诊断超参数/架构问题。

**与因子反馈的区别**：
- 角色设定：顶级对冲基金量化分析师
- 额外分析训练日志（`experiment.stdout`）判断参数设置问题
- 首轮无 SOTA 时降低门槛（ICIR > 0 即视为成功）
- 输出 `Decision: true/false`（布尔值，而非 "yes/no"）

---

## 7. CoSTEER 编码进化阶段

CoSTEER 的 prompt 分布在三个文件中：通用组件分析、因子专用编码 prompt、模型专用编码 prompt。

### 7.1 组件索引分析

**文件**：[components/coder/CoSTEER/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/prompts.yaml)

`analyze_component_prompt_v1_system`：分析新任务需要哪些已有组件（基于 component_index），返回组件索引列表，用于知识检索。

### 7.2 因子编码 Prompt

**文件**：[components/coder/factor_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/prompts.yaml)

| Prompt 名 | 阶段 | 作用 |
|-----------|------|------|
| `evaluator_code_feedback_v1_system/user` | 代码评审 | LLM 审查因子代码是否与描述一致，输出简短批评（不给用户看，发给编码 agent 修正） |
| `evolving_strategy_factor_implementation_v1_system` | 代码生成 | 基于上次失败代码+反馈+相似成功代码，生成修正后的因子代码（JSON: `{"code": "..."}`） |
| `evolving_strategy_factor_implementation_v2_user` | 代码生成（用户侧） | 注入 RAG 知识：相似错误的成功修复对、相似因子的正确实现、最新尝试的反馈 |
| `evolving_strategy_error_summary_v2_system/user` | 错误归纳 | 参考相似错误及其解决方案，生成精简的错误修正建议（不包含代码） |
| `select_implementable_factor_system/user` | 因子筛选 | 从候选因子中选出最易实现的子集，丢弃反复失败的因子 |
| `evaluator_output_format_system` | 输出格式检查 | 验证因子输出 DataFrame 格式是否符合要求 |
| `evaluator_final_decision_v1_system/user` | 最终决策 | 综合执行反馈、代码评审、值检查，输出 `{final_decision: bool, final_feedback: str}` |

**最终决策规则**（来自 [L190-L193](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/prompts.yaml#L190-L193)）：

1. 值与 GT 完全一致（小容差内）→ 正确
2. 值与 GT 有高 IC/RankIC 相关性 → 正确
3. 无 GT 时：代码执行成功 + 代码反馈与场景/描述一致 → 正确；任何异常都视为失败

### 7.3 模型编码 Prompt

**文件**：[components/coder/model_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/prompts.yaml)

| Prompt 名 | 作用 |
|-----------|------|
| `extract_model_formulation_system` | 从论文描述中提取模型架构为结构化 JSON（LaTeX 公式、层结构、超参） |
| `evolving_strategy_model_coder.system/user` | 基于历史代码和反馈生成/修正 PyTorch 模型代码，要求与前次代码 90%+ 相同 |
| `evaluator_code_feedback.system/user` | 模型代码评审（逻辑与因子评审类似） |
| `evaluator_final_feedback.system/user` | 模型最终决策（执行成功 + 形状正确 + 代码对齐描述） |

---

## 8. Qlib 场景描述模板

这些模板拼接成 `scenario` 变量，注入到 hypothesis_gen、hypothesis2experiment、coder 等所有 prompt 中，为 LLM 提供统一的运行环境上下文。

**文件**：[scenarios/qlib/experiment/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml)

### 8.1 背景模板

| 模板名 | 位置 | 内容 |
|--------|------|------|
| `qlib_quant_background` | [L1-L10](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml#L1-L10) | Quant 场景总背景：因子+模型双管线说明 |
| `qlib_factor_background` | [L12-L28](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml#L12-L28) | 因子定义：名称/描述/公式/变量四要素，一个窗口参数=一个因子 |
| `qlib_model_background` | [L167-L183](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml#L167-L183) | 模型定义：名称/描述/架构/超参/训练参数/ModelType |

### 8.2 接口规范模板

| 模板名 | 位置 | 规范内容 |
|--------|------|---------|
| `qlib_factor_interface` | [L30-L33](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml#L30-L33) | 因子代码接口：`calculate_{name}()` 函数、输出 `result.h5`、MultiIndex(datetime, instrument)、禁止 try-except |
| `qlib_model_interface` | [L185-L218](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml#L185-L218) | 模型代码接口：继承 `nn.Module`、`model_cls` 变量、Tabular/TimeSeries 两种输入形状、禁止 try-except |

### 8.3 策略与输出格式模板

| 模板名 | 作用 |
|--------|------|
| `qlib_factor_strategy` | 数据处理规范：MultiIndex 操作、groupby、merge 等步骤需加注释说明（含代码示例） |
| `qlib_factor_output_format` | 因子输出 DataFrame 的精确格式示例（MultiIndex、单列 float64、非空数可不同） |
| `qlib_model_output_format` | 模型输出 shape (batch_size, 1)，保存为 output.pth |

### 8.4 模拟器描述模板

| 模板名 | 作用 |
|--------|------|
| `qlib_factor_simulator` | 描述 Qlib 如何使用因子：生成因子表 → 训练 LGBModel → 构建组合 → 评估收益/夏普/回撤 |
| `qlib_model_simulator` | 描述 Qlib 如何使用模型：基线因子表 → 训练自定义模型 → 组合构建 → 评估迭代 |

### 8.5 实验设置模板

| 模板名 | 变量 | 渲染示例 |
|--------|------|---------|
| `qlib_factor_experiment_setting` | `train_start/end`, `valid_start/end`, `test_start/end` | CSI300 + LGBModel + Alpha158 Plus，数据划分表 |
| `qlib_model_experiment_setting` | 同上 | CSI300 + RDAgent-dev + 20 factors (Alpha158) |

---

## 9. PDF 研报处理 Prompt

**文件**：[scenarios/qlib/factor_experiment_loader/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml)

这些 prompt 用于研报场景（factor_from_report），在 HypothesisGen 之前执行，从 PDF 中提取因子信息。

### 9.1 处理流水线

```
PDF 文本
  ↓ classify_system（分类：是否为量化选股研报）
  ↓ extract_factors_system（抽取：summary + factors + models）
  ↓ extract_factor_formulation_system（公式：LaTeX + 变量说明）
  ↓ factor_viability_system（可行性：日频/个股/数据源可计算）
  ↓ factor_relevance_system（相关性：纯数学计算，非主观判断）
  ↓ factor_duplicate_system（去重：合并等价因子）
  ↓ 输出 FactorTask 列表
```

### 9.2 各 Prompt 详解

**`classify_system_chinese` / `classify_system`**（[L73-L96](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L73-L96)）

- 中文/英文双语版本
- 判断条件：金工量化领域 + 选股方向（非择时/选基）+ 涉及因子或模型构成/表现
- 输出：`{"class": 1}` 或 `{"class": 0}`

**`extract_factors_system`**（[L1-L20](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L1-L20)）

- 抽取研报摘要、所有因子（英文名称，下划线连接）、所有模型
- 表格中的因子也不能遗漏
- 输出：`{"summary": "...", "factors": {...}, "models": {...}}`

**`extract_factors_follow_user`**（[L22-L31](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L22-L31)）

- 长文档分页时的续写 prompt，忽略已出现的因子

**`extract_factor_formulation_system`**（[L33-L64](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L33-L64)）

- 为每个因子提取 LaTeX 公式和变量说明
- 提供 5 类可用数据源（行情、财务、基本面、高频、一致预期）
- 注意 JSON 中 LaTeX 反斜杠转义

**`factor_viability_system`**（[L98-L144](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L98-L144)）

- 可行性判断：日频 + 个股级别 + 基于提供的数据源可计算
- 输出每个因子的 viability 和 reason

**`factor_relevance_system`**（[L146-L184](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L146-L184)）

- 相关性判断：纯数学操作，非主观判断或自然语言分析
- 输出每个因子的 relevance 和 reason

**`factor_duplicate_system`**（[L187-L227](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L187-L227)）

- 去重：找出等价因子组（名称/公式不同但计算同一因子）
- 周期参数（1日/5日/10日）不同的不算重复
- 输出：`[["factor_a", "factor_b"], ["factor_c", "factor_d", "factor_e"]]`
- 约束：每组 ≥2 个因子，每组 ≤10 个，总数 ≤50 组

---

## 10. 工具类 Prompt

### 10.1 stdout 日志过滤

**文件**：[utils/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/prompts.yaml)

`filter_redundant_text`：分析子进程 stdout，生成正则表达式过滤冗余内容（进度条、重复 warning、无意义 NaN 日志），保留有效训练指标。

**输出**：

```json
{
  "needs_sub": true,
  "regex_patterns": ["\\d+%\\|██+\\|.*", "Warning:.*NaN.*"]
}
```

### 10.2 Context7 文档查询增强

**文件**：[components/agent/context7/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/agent/context7/prompts.yaml)

当 CoSTEER 编码遇到错误时，通过 Context7 MCP 查询库文档：

- `system_prompt`：设定助手角色
- `context7_enhanced_query_template`：结构化错误查询模板，强制 resolve-library-id → get-library-docs 完整工作流，只返回 API 文档不给完整代码
- `code_context_template`：注入当前代码上下文
- `timm_special_case`：timm 库的特殊 ID 映射规则

### 10.3 研报场景假设生成

**文件**：[app/qlib_rd_loop/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/prompts.yaml)

`hypothesis_generation`：研报场景专用，基于提取的因子描述和报告内容生成假设，变量为 `factor_descriptions` 和 `report_content`。

---

## 11. Prompt 调用全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Qlib R&D Loop                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  PDF 研报场景额外步骤:                                               │
│  ┌──────────────────────────────────────────┐                      │
│  │ classify_system → extract_factors_system │                      │
│  │ → extract_factor_formulation_system      │                      │
│  │ → factor_viability/relevance/duplicate   │                      │
│  └──────────────────┬───────────────────────┘                      │
│                     ↓                                               │
│  ┌──────────────────────────────────────────┐                      │
│  │ HypothesisGen                            │                      │
│  │  T(".prompts:hypothesis_gen.system/user")│                      │
│  │  注入: scenario + specification + 历史链  │                      │
│  │  输出: {hypothesis, reason}              │                      │
│  └──────────────────┬───────────────────────┘                      │
│                     ↓                                               │
│  ┌──────────────────────────────────────────┐                      │
│  │ Hypothesis2Experiment                    │                      │
│  │  T(".prompts:hypothesis2experiment.*")   │                      │
│  │  注入: target_hypothesis + 历史链(去重)   │                      │
│  │  输出: [{factor_name: {formulation...}}] │                      │
│  └──────────────────┬───────────────────────┘                      │
│                     ↓                                               │
│  ┌──────────────────────────────────────────┐                      │
│  │ CoSTEER (多轮生成→执行→评估→修正)         │                      │
│  │  ┌─ analyze_component_prompt (组件检索)  │                      │
│  │  ├─ evolving_strategy_*_implementation   │                      │
│  │  │   (注入: 相似成功代码 + 失败反馈 + RAG)│                      │
│  │  ├─ evaluator_code_feedback (LLM评审)    │                      │
│  │  ├─ evaluator_output_format (格式检查)    │                      │
│  │  ├─ evolving_strategy_error_summary      │                      │
│  │  │   (相似错误归纳)                       │                      │
│  │  ├─ select_implementable_factor (筛选)    │                      │
│  │  └─ evaluator_final_decision (最终决策)   │                      │
│  └──────────────────┬───────────────────────┘                      │
│                     ↓                                               │
│  ┌──────────────────────────────────────────┐                      │
│  │ Runner (Docker 隔离执行, 无 LLM 调用)     │                      │
│  │  stdout → filter_redundant_text (日志过滤)│                      │
│  └──────────────────┬───────────────────────┘                      │
│                     ↓                                               │
│  ┌──────────────────────────────────────────┐                      │
│  │ Summarizer                               │                      │
│  │  T(".prompts:factor_feedback_generation")│                      │
│  │  或 model_feedback_generation            │                      │
│  │  注入: hypothesis + task_details + result│                      │
│  │  输出: {Observations, New Hypothesis,    │                      │
│  │         Replace Best Result, Decision}   │                      │
│  └──────────────────┬───────────────────────┘                      │
│                     ↓                                               │
│              写入 Trace，进入下一轮                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

横向贯穿所有阶段的模板:
┌─────────────────────────────────────────────────────────────────┐
│ scenario 变量 =                                                  │
│   qlib_factor_background + qlib_factor_interface                │
│   + qlib_factor_output_format + qlib_factor_simulator           │
│   + qlib_factor_strategy + qlib_factor_experiment_setting       │
│   (模型场景替换为 model_* 版本)                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12. 自定义 Prompt 的方法

### 12.1 应用模板覆盖机制

通过环境变量 `RD_AGENT_APP_TPL` 指定自定义模板目录，RDAT 会优先从该目录加载：

```bash
export RD_AGENT_APP_TPL=my_templates
```

目录结构需镜像 `rdagent/` 包内路径，例如：

```
my_templates/
└── scenarios/
    └── qlib/
        └── prompts.yaml          # 覆盖默认的 qlib 场景规范
```

### 12.2 添加新 Prompt 模板

1. 在模块目录下创建/编辑 `prompts.yaml`：
   ```yaml
   my_custom_prompt:
     system: |-
       You are a helpful assistant for {{ task_type }}.
     user: |-
       Please process: {{ input_data }}
   ```

2. 在代码中通过 `T(".prompts:my_custom_prompt.system").r(task_type="...", input_data="...")` 加载渲染

3. 注意使用 Jinja2 语法：`{{ var }}` 输出变量，`{% if cond %}...{% endif %}` 条件块，`{% for x in list %}...{% endfor %}` 循环

### 12.3 Prompt 调试

所有 prompt 的渲染过程会通过 `rdagent_logger.log_object(tag="debug_tpl")` 记录到 Trace，包含 URI、原始模板、上下文变量和渲染结果，可在 WebUI 任务详情的 debug_tpl 消息中查看。

---

## 13. 相关文件索引

| 文件 | 说明 |
|------|------|
| [rdagent/utils/agent/tpl.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/agent/tpl.py) | RDAT 模板引擎核心：加载、查找优先级、Jinja2 渲染 |
| [rdagent/core/prompts.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/prompts.py) | 旧版 Prompts 字典类（已被 RDAT 取代，仍有少量使用） |
| [rdagent/components/proposal/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py) | HypothesisGen 和 Hypothesis2Experiment 的 prompt 调用处 |
| [rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py) | Summarizer 的 prompt 调用处 |
| [rdagent/components/coder/factor_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evolving_strategy.py) | 因子 CoSTEER 演化策略 prompt 调用处 |
| [rdagent/components/coder/model_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/evolving_strategy.py) | 模型 CoSTEER 演化策略 prompt 调用处 |
| [rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py) | PDF 研报处理流水线 prompt 调用处 |

{% endraw %}
