---
title: R&D-Agent 整体框架
layout: default
---

{% raw %}

# R&D-Agent 整体框架

> 论文：*R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science*
> 作者：Xu Yang 等（2025）
> arXiv：[2505.14738](https://arxiv.org/abs/2505.14738)

## 1. 论文概述

数据科学（例如量化因子挖掘、模型调优）本质上是一个不断"提出想法、做实验、看结果、再改进"的循环过程。传统上，这个循环高度依赖人类研究员的经验和手工操作，既耗时又容易遗漏有价值的方向。R&D-Agent 提出了一个由大语言模型（LLM）驱动的**自主研发智能体框架**，让 AI 像一名不知疲倦的"AI 研究员"一样，独立完成从假设提出到实验验证再到知识沉淀的完整闭环。

打个比方：如果把数据科学研究比作做菜，传统方式是厨师（人类研究员）亲自尝菜、调配方、再尝；而 R&D-Agent 则是一个配备了"尝味机器人"和"菜谱记忆库"的自动厨房，它能自己决定下一道菜尝试什么口味，自己下厨，自己品尝并记录哪道菜受欢迎，然后在下一轮做得更好。

## 2. 核心思想

R&D-Agent 的核心是一个**五阶段研发循环（R&D Loop）**：

```
假设生成 (Hypothesis)
    ↓
实验设计 (Experiment)
    ↓
代码实现 (Implementation / CoSTEER)
    ↓
执行运行 (Running)
    ↓
反馈总结 (Feedback)
    ↓
（回到假设生成，基于反馈继续迭代）
```

以量化研究员挖掘因子为例：

1. **假设生成**：研究员观察历史数据后想——"短期动量反转可能在小盘股上有效"。
2. **实验设计**：决定构造 3 个具体因子（如 5 日反转、10 日反转、成交量加权反转），并设定回测时间段和评价指标（IC、年化收益、最大回撤）。
3. **代码实现**：把因子表达式写成可运行的 Python 代码，并通过多轮自我纠错确保代码能跑通。
4. **执行运行**：在 Docker 容器中运行回测，得到 IC、收益等指标。
5. **反馈总结**：对比当前结果与历史最优（SOTA），判断新因子是否更好；如果更好则替换 SOTA，并总结经验用于下一轮假设。

这个循环不断重复，AI 研究员的"经验"通过 Trace（实验轨迹）和知识图谱持续积累，从而越做越好。

## 3. 核心结论与贡献

### 3.1 自主研发闭环

R&D-Agent 首次将数据科学的完整研发流程形式化为一个可自动执行的多智能体循环，无需人工在每一步介入。五个阶段各司其职，又通过统一的 Trace 机制串联，实现了从"想法"到"可运行代码"再到"结论"的端到端自动化。

### 3.2 多智能体协作

框架中每个阶段由专门的智能体负责：假设生成 Agent 负责提出有创意的方向，实验设计 Agent 负责将想法转化为可执行任务，编码 Agent（CoSTEER）负责代码生成与自我纠错，执行 Agent 负责在隔离环境中运行实验，反馈 Agent 负责分析结果并决策。这种分工使得每个环节都可以独立优化。

### 3.3 基于 SOTA 与 Trace 的知识积累

框架引入了两个关键记忆机制：

- **Trace（实验轨迹）**：以有向无环图（DAG）的形式记录所有历史实验及其反馈，支持分支探索和回溯。当前最优结果（SOTA, State-of-the-Art）始终作为下一轮实验的对比基线。
- **知识图谱（CoSTEER RAG）**：在编码层面，成功的代码实现、失败的错误模式、组件复用关系被组织成知识图谱，通过检索增强生成（RAG）指导后续代码编写，避免重复犯错。

### 3.4 真实场景验证

论文在量化投资（Qlib 因子挖掘与模型调优）等真实数据科学场景中进行了实验，结果表明 R&D-Agent 能够自主发现有效的因子和模型改进，部分结果甚至超越了人工设计的基线，验证了框架的实用性。

## 4. 论文在 multialpha 项目中的应用

multialpha 项目基于 RD-Agent 框架实现了量化因子的自主研发流程。下面对照论文中的五阶段循环，逐一说明代码中的对应实现。

### 4.1 主循环：RDLoop

整个研发循环的编排由 `RDLoop` 类负责，它继承自 `LoopBase`，通过元类 `LoopMeta` 自动发现并按顺序执行各个步骤。

- 循环基类（负责步骤调度、并行执行、断点续跑）：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py)
- 研发循环具体实现（定义了 `direct_exp_gen` → `coding` → `running` → `feedback` → `record` 五个步骤）：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py)
- 因子场景入口：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py)

在 `rd_loop.py` 中，五个步骤方法清晰对应论文的五阶段：

| 论文阶段 | 代码方法 | 行号参考 |
|---------|---------|---------|
| 假设生成 + 实验设计 | `direct_exp_gen` | rd_loop.py:199 |
| 代码实现 | `coding` | rd_loop.py:212 |
| 执行运行 | `running` | rd_loop.py:217 |
| 反馈总结 | `feedback` | rd_loop.py:222 |
| 记录入 Trace | `record` | rd_loop.py:238 |

### 4.2 五个核心智能体

#### (1) HypothesisGen —— 假设生成

`HypothesisGen` 是抽象基类，具体实现为 `LLMHypothesisGen`，它通过调用 LLM 基于历史 Trace 生成新的假设。因子场景使用 `FactorHypothesisGen`。

- 代码位置：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py)
- 核心方法 `gen()`（proposal/\_\_init\_\_.py:29）：准备上下文 → 渲染 system/user prompt → 调用 LLM → 解析为 `Hypothesis` 对象。
- 假设对象包含：假设描述、理由、简洁理由、观察、论证、知识点等字段（定义于 `rdagent/core/proposal.py:24`）。

#### (2) Hypothesis2Experiment —— 实验设计

`Hypothesis2Experiment` 将自然语言假设转化为具体的可执行实验（包含多个子任务）。因子场景使用 `FactorHypothesis2Experiment`。

- 代码位置：同上文件，`LLMHypothesis2Experiment` 类（proposal/\_\_init\_\_.py:86）。
- 核心方法 `convert()`（proposal/\_\_init\_\_.py:94）：将假设 + Trace 上下文传给 LLM，输出包含多个因子任务的 `Experiment` 对象。

#### (3) CoSTEER —— 代码实现

CoSTEER（**Co**de **S**elf-**T**eaching **E**volving **R**efinement）是负责代码生成与自我纠错的核心模块。它不是一次性生成代码，而是通过多轮进化（evolve）不断修正代码，直到通过评估器的检查。

- 代码位置：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/__init__.py)
- 核心方法 `develop()`（CoSTEER/\_\_init\_\_.py:93）：
  - 将 Experiment 包装为可进化的 `EvolvingItem`；
  - 创建 `RAGEvoAgent`，在最大循环次数内反复"生成代码 → 执行评估 → 根据反馈修改"；
  - 维护一个 fallback 方案，确保即使最后一轮失败也能提交最近一个可接受的版本。
- 知识管理（RAG）：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py)
  - `CoSTEERRAGStrategyV2` 通过知识图谱检索相似任务的成功实现、历史失败轨迹、相似错误的解决经验，辅助代码生成。

#### (4) Runner —— 执行运行

`QlibFactorRunner` 负责在 Docker 容器中执行因子回测。它将新生成的因子与历史 SOTA 因子合并，去重（通过 IC 相关性过滤高度相似的因子），然后调用 qlib 进行回测。

- 代码位置：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py)
- 核心方法 `develop()`（factor_runner.py:78）：
  - 处理基线实验（SOTA）；
  - 合并新旧因子并通过 `deduplicate_new_factors` 去除高相关因子；
  - 将合并后的因子数据写入 parquet，注入 Docker 工作区执行回测；
  - 返回包含 IC、年化收益、最大回撤等指标的结果。

#### (5) Summarizer —— 反馈总结

`QlibFactorExperiment2Feedback` 负责将执行结果与 SOTA 对比，调用 LLM 生成结构化反馈，并决定是否用当前结果替换 SOTA。

- 代码位置：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)
- 核心方法 `generate_feedback()`（feedback.py:55）：
  - 提取关键指标（IC、年化超额收益、最大回撤）；
  - 将当前结果与 SOTA 结果并排呈现给 LLM；
  - LLM 返回 JSON 格式的反馈：观察（Observations）、假设评价（Feedback for Hypothesis）、新假设建议（New Hypothesis）、推理过程（Reasoning）、是否替换 SOTA（Replace Best Result）。

### 4.3 Prompt 模板

假设生成和实验设计的 Prompt 定义在 YAML 文件中，使用 Jinja2 模板语法，支持注入场景描述、历史假设与反馈、SOTA 信息、RAG 检索结果等上下文。

- 文件位置：
  [file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml)
- `hypothesis_gen.system_prompt`：指导 LLM 分析既往实验、反思成败原因、提出改进或新方向。
- `hypothesis_gen.user_prompt`：注入历史假设链、最近一次实验、SOTA 实验以及 RAG 辅助信息。
- `hypothesis2experiment.system_prompt` / `user_prompt`：指导 LLM 将假设转化为具体的因子/模型任务。

这些 Prompt 是连接 LLM 推理能力与研发流程的关键纽带。

### 4.4 Trace 与 SOTA 记忆机制

Trace 是框架的"记忆中枢"，定义于：

[file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py)

`Trace` 类（proposal.py:141）的核心设计：

- **历史记录 `hist`**：按时间顺序存储 `(Experiment, Feedback)` 元组列表。
- **DAG 结构 `dag_parent`**：记录实验之间的父子关系，支持分支探索（类似 Git 的提交树）。
- **SOTA 检索 `get_sota_hypothesis_and_experiment()`**（proposal.py:178）：从最近的实验向前回溯，找到最近一个 `decision=True`（被判定为优于基线）的实验，作为当前最优。
- **当前选择点 `current_selection`**：标记下一轮实验从哪个节点出发，默认选择最新的 SOTA 节点（`SEL_LATEST_SOTA = (-1,)`）。

在每轮循环的 `record` 步骤中（rd_loop.py:238），当前实验及其反馈通过 `sync_dag_parent_and_hist()` 写入 Trace，成为后续轮次的记忆。下一轮的假设生成会读取 Trace 中的 SOTA 假设、最近反馈和完整历史链，从而做出有依据的决策。

CoSTEER 层面的知识积累则通过 `CoSTEERKnowledgeBaseV2`（knowledge_management.py:852）实现，它维护一个无向图知识图谱，节点类型包括：组件（component）、任务描述（task_description）、任务轨迹（task_trace）、成功实现（task_success_implement）、错误（error）。当代码任务成功时，其完整进化轨迹和错误分析被写入图谱；未来遇到相似任务时，通过组件交集查询、错误匹配和嵌入相似度检索相关经验。

## 5. 通俗例子：一轮完整的因子研发迭代

让我们跟随系统走一遍，看看"动量反转"假设是如何被验证的。

### 第一步：假设生成

系统启动，Trace 为空（或已有若干轮记录）。`FactorHypothesisGen.gen()` 被调用，Prompt 中注入了场景描述和历史反馈。LLM 思考后输出：

> **假设**：基于短期收益率反转的因子在中小盘股上可能产生超额收益，因为这类股票更容易出现过度反应后的回调。
> **理由**：行为金融学中的过度反应理论，以及近期观察到前期跌幅较大的股票在随后 5 日有反弹倾向。

这个假设被封装为 `Hypothesis` 对象。

### 第二步：实验设计

`FactorHypothesis2Experiment.convert()` 将假设转化为 3 个具体的因子任务：

1. 5 日反转因子：`-1 * Ref($close, -5) / $close`
2. 10 日成交量加权反转因子
3. 20 日波动率调整反转因子

每个任务包含因子名称、表达式、描述等信息，组成一个 `QlibFactorExperiment`。

### 第三步：CoSTEER 代码实现

CoSTEER 接收到实验后，为每个因子任务生成 Python 代码。第一轮生成的代码可能存在语法错误或返回值格式不对，评估器（Evaluator）执行代码后给出反馈：

> "执行失败：NameError: name 'np' is not defined"

CoSTEER 的进化策略根据反馈修改代码，同时从知识库中检索相似任务的成功实现作为参考。经过 2-3 轮迭代后，代码通过执行检查和返回值检查，3 个因子的代码文件被生成到工作区。

### 第四步：Runner 回测执行

`QlibFactorRunner.develop()` 将新因子与 SOTA 因子合并：

- 先计算新因子与 SOTA 因子的 IC 相关性，剔除相关系数 > 0.99 的冗余因子；
- 将合并后的因子数据保存为 parquet；
- 在 Docker 容器中调用 qlib，使用 LightGBM 模型在训练集上训练、验证集上调参、测试集上评估；
- 得到结果：IC = 0.045，年化超额收益 = 8.2%，最大回撤 = -6.1%。

### 第五步：Summarizer 反馈总结

`QlibFactorExperiment2Feedback.generate_feedback()` 将当前结果与 SOTA 结果对比：

| 指标 | 当前结果 | SOTA 结果 |
|------|---------|----------|
| IC | 0.045 | 0.038 |
| 年化超额收益 | 8.2% | 6.5% |
| 最大回撤 | -6.1% | -7.3% |

LLM 分析后输出：

> **观察**：新因子在 IC 和收益上均优于 SOTA，回撤也更小。
> **假设评价**：短期反转假设得到支持，尤其是 5 日反转因子贡献最大。
> **新假设建议**：可以尝试将反转因子与换手率结合，因为高换手率股票的反转效应可能更强。
> **推理**：三项关键指标全面改善，且新因子与现有 SOTA 因子相关性低，提供了增量信息。
> **是否替换 SOTA**：是（True）

### 第六步：记录与下一轮

`record` 步骤将实验和反馈写入 Trace，SOTA 被更新为本次实验。下一轮循环开始时，假设生成 Agent 读取到新的 SOTA 和反馈，沿着"反转 + 换手率"的方向继续探索。系统就这样像一名真正的量化研究员一样，一轮一轮地积累和进步。

## 6. 相关链接

- **arXiv 论文**：[https://arxiv.org/abs/2505.14738](https://arxiv.org/abs/2505.14738)
- **项目代码仓库**：[https://github.com/microsoft/RD-Agent](https://github.com/microsoft/RD-Agent)

### BibTeX

```bibtex
@article{yang2025rdagent,
  title={R\&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science},
  author={Yang, Xu and others},
  journal={arXiv preprint arXiv:2505.14738},
  year={2025}
}
```

{% endraw %}
