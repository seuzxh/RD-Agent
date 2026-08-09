---
title: CoSTEER 协同进化策略
layout: default
---

{% raw %}

# CoSTEER：会记笔记的程序员

> arXiv:2407.18690 · Xu Yang 等 · 2024
>
> *Collaborative Evolving Strategy for Automatic Data-Centric Development*

---

## 1. 论文概述

CoSTEER 就像一个**有记忆的程序员**——每次踩坑都记下来，下次遇到类似问题直接翻笔记。

大语言模型（LLM）写代码时有一个让人头疼的毛病：**第一次写出来的代码经常跑不通**。可能是数据列名拼错、除以零、类型不匹配、或者逻辑与目标对不上。普通做法是让 LLM"自己再看看"（self-reflection），但它往往反复犯同样的错——因为它没有真正记住上次错在哪里、怎么修好的。

CoSTEER 提出的思路很朴素：**把每一次成功和失败都存进一个知识库，下次写代码前先检索类似的历史经验。** 这就像一个经验丰富的工程师，脑子里装着一本"踩坑日记"："上次这个 NaN 错误，用 `.fillna(0)` 修好了"、"这种索引对不齐的问题，通常是因为没有 `sort_index()`"。

论文的关键贡献在于：它证明了这种"带着记忆写代码"的方式，比一次性生成（one-shot）和单纯自我反思（self-reflection）都要有效得多，而且经验可以跨任务、跨运行积累复用。

需要特别澄清的是：**CoSTEER 不是遗传算法（Genetic Algorithm）。** 它没有交叉（crossover）、没有变异（mutation）、没有种群选择。它的本质是**RAG（检索增强生成）加持的 LLM 迭代调试**——每一轮都基于真实执行反馈和检索到的历史经验，让 LLM 生成更准确的代码。

---

## 2. 核心思想

### 2.1 进化循环（Evolution Loop）

CoSTEER 的核心是一个反复转动的"进化循环"：

```
        ┌─────────────────────────────────────────────┐
        │                                             │
        ▼                                             │
   ┌──────────┐   ┌──────────┐   ┌──────────────┐    │
   │ 生成代码  │──▶│ 执行代码  │──▶│ 获取错误/反馈 │    │
   └──────────┘   └──────────┘   └──────────────┘    │
        ▲                                 │           │
        │                                 ▼           │
   ┌──────────┐                   ┌──────────────┐    │
   │ LLM 修正  │◀──────────────────│ RAG 检索知识库│    │
   └──────────┘                   └──────────────┘    │
        │                                             │
        └───────────── 成功 or 到达最大轮数 ──────────┘
```

每轮做这些事：生成代码 → 真实执行 → 获取结构化反馈（执行错误、返回值检查、代码审查）→ RAG 检索三类经验（类似任务的成功实现、类似错误的失败→成功修复对、本任务之前的失败尝试）→ LLM 基于上一轮代码修正（而非从头重写）→ 重复直到通过检查或达到最大迭代次数。

### 2.2 与一次性生成的对比

| 维度 | 一次性生成（One-shot） | 自我反思（Self-reflection） | CoSTEER |
|------|----------------------|---------------------------|---------|
| 历史经验 | 无 | 仅当前对话内 | 跨运行持久化知识库 |
| 错误处理 | 出错即失败 | LLM 自己猜哪里错了 | 检索类似错误的真实修复方案 |
| 成功复用 | 不借鉴 | 不借鉴 | 检索类似任务的成功代码做参考 |
| 迭代方式 | 无 | 纯语言层面推理 | 真实执行反馈 + 检索增强 |
| 知识积累 | 无 | 无 | 每次成功/失败都写入知识库 |

### 2.3 知识库：成功与失败的配对

CoSTEER 知识库的核心不是"存正确答案"，而是存**"错误 → 修复"的配对经验**。这包含三类知识组件：

1. **成功实现（Successful Implementation）**：一个任务最终跑通的代码及其反馈。
   当遇到类似任务时，这些成功代码可以作为参考模板。

2. **失败实现 + 错误信息（Failed Implementation with Error）**：每一次失败的代码和对应的报错。
   这些失败痕迹记录了"哪条路走不通"，避免重蹈覆辙。

3. **错误摘要（Error Summary）**：对错误类型的提炼（如 `ValueError`、除零、索引不对齐），
   以及"曾遇到同样错误但最终修好了"的案例配对。

知识库底层用**无向图（UndirectedGraph）**组织：任务描述、组件、错误、成功实现等节点通过边连接。检索时从组件和错误两个维度交叉查询，能找到"虽然任务不同但犯过一模一样的错"的修复经验——这比单纯的向量相似度更精准。

---

## 3. 核心结论

论文通过实验得出以下关键结论：

1. **CoSTEER 显著优于一次性生成和自我反思。**
   借助知识库中的历史经验，LLM 能更快定位错误、更少走弯路，首次成功率和最终通过率都明显更高。

2. **知识可以跨运行保留和积累。**
   这是 CoSTEER 区别于普通迭代调试的关键：本轮修过的 bug、写对的代码，会被序列化保存到磁盘，
   下一次运行时加载进来继续用。系统越用越"聪明"，知识库越积越厚。

3. **组件级复用提升了泛化能力。**
   系统会把任务拆解成组件（如"滚动均值"、"换手率计算"），通过组件匹配找到相关经验，
   即使两个任务表面描述不同，只要共享底层组件，经验就能迁移。

4. **"失败→成功"的错误配对比单纯看成功代码更有价值。**
   知道"这个错是怎么修的"比只看"正确代码长什么样"对调试更有指导意义——
   前者直接告诉 LLM 问题出在哪、改哪里，后者只提供了一个静态参考。

5. **反复失败的任务会被自动淘汰。**
   当一个任务失败次数超过阈值（默认 20 次），系统会将其标记为"不可实现"并跳过，
   避免在不可能的任务上无限浪费资源。

---

## 4. 在 multialpha 中的应用

multialpha 项目（基于 RD-Agent 的量化因子挖掘平台）是 CoSTEER 的主要工程落地，它贯穿因子编码和模型编码两条主线。

### 4.1 主类：CoSTEER

CoSTEER 主类定义在
[rdagent/components/coder/CoSTEER/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/__init__.py)，
继承自 `Developer`，初始化时组装三个核心部件：**evaluator**（执行代码并反馈）、**es**（生成和修正代码的进化策略）、**rag**（知识库查询与更新）。

`develop()` 方法（第 93 行）是入口：把实验包装成 `EvolvingItem`，创建 `RAGEvoAgent`，通过 `multistep_evolve` 驱动循环。循环还维护 **fallback 机制**——如果某轮把之前对的代码改坏了，会回退到最近一个可接受版本（第 120-127 行）。

### 4.2 六步 CoSTEER 流程

进化循环的具体实现在
[rdagent/core/evolving_agent.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py)
的 `RAGEvoAgent.multistep_evolve()` 方法中（第 140 行），每轮分为六步：

1. **分析组件 / RAG 检索**（第 149-151 行）：调用 `self.rag.query(evo, self.evolving_trace)`，检索本任务之前的失败痕迹、相似组件任务的成功实现、相似错误的失败→成功配对。
2. **生成代码**（第 158-162 行）：进化策略的 `evolve_iter()` 并行对每个子任务执行 `implement_one_task()`，把检索知识填入 prompt 让 LLM 生成代码。
3. **执行**：评估器 `evaluate_iter()` 在真实环境运行代码，产生执行反馈。
4. **LLM 审查 / 代码反馈**：评估器让 LLM 审查代码逻辑是否与任务描述一致，对应 prompt 为 `evaluator_code_feedback`。
5. **错误摘要（RAG 增强）**：因子编码策略的 `error_summary()` 方法（[factor_coder/evolving_strategy.py:29](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evolving_strategy.py#L29)）参考"同样错误曾经怎么修好的"，生成精准修改建议，而非泛泛地说"请检查代码"。
6. **选择可实现因子**：反复失败超过 `fail_task_trial_limit`（默认 20 次）的因子会被加入 `failed_task_info_set` 并在后续跳过。对应 prompt `select_implementable_factor` 让 LLM 审查历史尝试，淘汰信息不足或过于复杂的因子，把资源集中在可实现的因子上。

### 4.3 evo_loop_N 标签系统

在 `multistep_evolve` 第 146 行，每轮进化被包裹在 `logger.tag(f"evo_loop_{evo_loop_id}")` 中。第 0、1、2 轮的日志、代码快照、反馈分别标记为 `evo_loop_0`、`evo_loop_1` 等，在 WebUI 和日志系统中可按轮次查看代码如何从满是 bug 演化到通过检查。默认最大轮数 `max_loop = 10`（[CoSTEER/config.py:15](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/config.py#L15)）。

### 4.4 因子编码（Factor Coder）

因子进化策略在 [factor_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evolving_strategy.py)，核心类 `FactorMultiProcessEvolvingStrategy`。其 `implement_one_task()`（第 60 行）从检索结果提取三类信息：类似因子的成功代码、类似错误的失败→成功配对、本因子之前的失败尝试。这些填入 `evolving_strategy_factor_implementation` prompt（[factor_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/prompts.yaml)），prompt 明确要求 LLM **"基于上一轮代码修正，不要改动已正确的部分"**，避免每轮从头重写把对的地方改坏。

因子编码还有独特的 **error_summary 机制**（第 29-58 行）：检索到类似错误时，不直接把原始失败/成功代码堆给 LLM，而是先让另一个 LLM 参考这些配对生成精炼的修改建议（critics），再交给编码 LLM，有效减少 token 占用并提高准确性。

### 4.5 模型编码（Model Coder）

模型进化策略在 [model_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/evolving_strategy.py)，类为 `ModelMultiProcessEvolvingStrategy`。结构与因子编码类似但更简洁：检索类似模型的成功实现和之前的失败痕迹，把当前代码（`current_code`）也传入 prompt 让 LLM 在现有代码上修改；没有 error_summary 环节（模型错误通常更直接）。

### 4.6 知识库与 RAG 实现

知识库核心逻辑在 [CoSTEER/knowledge_management.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py)，底层图结构由 [knowledge_management/graph.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/graph.py) 提供，向量相似度由 [knowledge_management/vector_base.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/vector_base.py) 支持。

`CoSTEERRAGStrategyV2`（第 354 行）是当前 RAG 策略，包含三种查询：

- **former_trace_query**（第 530 行）：取本任务最近几次失败尝试；失败次数超限则标记为不可实现。
- **component_query**（第 593 行）：先用 `analyze_component`（借助 [CoSTEER/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/prompts.yaml) 中的 `analyze_component_prompt`）识别任务涉及的组件，再通过图查询找到共享组件的成功任务，最后用 embedding 相似度补充候选。
- **error_query**（第 723 行）：分析上一轮错误类型，在知识图谱中找到"犯过同样错误且最终成功"的案例，返回"错误描述 → (失败代码, 成功代码)"配对。

每轮结束后（evolving_agent.py 第 187-191 行），`generate_knowledge()` 把成功任务的完整进化轨迹写入知识图谱，失败尝试的错误分析记录为错误节点。成功轨迹经 `update_success_task()`（第 884 行）转化为持久节点供未来检索。知识库通过 pickle 序列化到磁盘（`knowledge_base_path` / `new_knowledge_base_path`），支持 `FileLock` 防并发写入冲突，实现跨运行的经验积累。

---

## 5. 通俗例子

假设系统要实现一个量化因子：**"收盘价与收盘价之比的 5 日均值"**（close-to-close ratio）。

**第 1 轮：首次尝试（无经验）**

LLM 凭直觉写出代码：

```python
ratio = close / close.shift(1)
factor = ratio.rolling(5).mean()
```

代码执行后报错：

```
ValueError: The source dataframe and the ground truth dataframe have different index.
```

系统把这个错误存入工作痕迹，并进行错误分析：识别出错误类型为"索引不对齐"。

**第 2 轮：RAG 检索经验**

在生成新代码前，RAG 在知识库中检索：
- 找到一个类似任务"成交量比率"，它之前也犯过索引不对齐的错误；
- 那个任务的失败代码没有排序索引，最终成功代码加了 `.sort_index()`；
- 还找到了几个涉及 `fillna` 的成功因子实现。

error_summary 环节综合这些经验，给出建议：
> critic 1: 计算比率后可能存在 NaN（首日 shift 产生），且索引未排序会导致比对失败。请确保索引对齐并处理缺失值。

LLM 据此修正代码：

```python
ratio = close / close.shift(1)
factor = ratio.rolling(5).mean().sort_index()
```

**第 3 轮：又一个错误**

执行通过了，但返回值检查发现：因子值在首日为 NaN，与 ground truth 不一致。
RAG 检索到另一个因子曾经用 `.fillna(0)` 解决了同样的 NaN 问题。

LLM 再次修正：

```python
ratio = close / close.shift(1)
factor = ratio.rolling(5).mean().fillna(0).sort_index()
```

执行成功，返回值与 ground truth 完全匹配，最终决策为 SUCCESS。

**知识积累**

这轮进化结束后，系统把完整轨迹写入知识库：
- 任务描述节点："收盘价比率 5 日均值"；
- 组件节点："rolling mean"、"ratio"、"fillna"；
- 错误节点："索引不对齐"、"NaN 值"；
- 成功实现节点：最终正确代码；
- 中间的失败痕迹节点：两次失败代码及其错误信息。

这些节点在图中相互连接。下次遇到任何涉及"rolling mean + NaN"的因子，
RAG 就能沿着图找到这次的经验——即使新因子的描述完全不同。**这就是 CoSTEER "越用越聪明"的秘密。**

---

## 6. 相关链接

- 论文原文（arXiv）：<https://arxiv.org/abs/2407.18690>
- 论文标题：*Collaborative Evolving Strategy for Automatic Data-Centric Development*
- 作者：Xu Yang 等
- 年份：2024
- CoSTEER 主类：
  [rdagent/components/coder/CoSTEER/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/__init__.py)
- 进化代理基类（evo_loop 标签）：
  [rdagent/core/evolving_agent.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py)
- 因子进化策略：
  [rdagent/components/coder/factor_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evolving_strategy.py)
- 模型进化策略：
  [rdagent/components/coder/model_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/evolving_strategy.py)
- 因子编码 prompts（evolving_strategy_factor_implementation / evaluator_code_feedback / select_implementable_factor）：
  [rdagent/components/coder/factor_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/prompts.yaml)
- 组件分析 prompt：
  [rdagent/components/coder/CoSTEER/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/prompts.yaml)
- 知识库与 RAG 策略：
  [rdagent/components/coder/CoSTEER/knowledge_management.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py)
- 知识图谱底层结构：
  [rdagent/components/knowledge_management/graph.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/graph.py)
- CoSTEER 配置（max_loop / fail_task_trial_limit）：
  [rdagent/components/coder/CoSTEER/config.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/config.py)
- 评估器与反馈结构：
  [rdagent/components/coder/CoSTEER/evaluators.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py)

{% endraw %}
