---
title: Reasoning as Gradient 推理即梯度
layout: default
---

{% raw %}

# Reasoning as Gradient 推理即梯度

> 论文：*Reasoning as Gradient: Scaling MLE Agents Beyond Tree Search*
> 作者：Yifei Zhang 等（2026）
> arXiv：[2603.01692](https://arxiv.org/abs/2603.01692)
> 接收会议：ACL 2026 Findings
> 相关系统：Gome（含 GPT-5 Traces 执行轨迹数据集，发布于 HuggingFace）

## 概述

让 AI 智能体解决复杂的机器学习工程（MLE）或代码任务时，一种常见做法是**树搜索**：让模型探索很多条可能的路径，就像下棋时用蒙特卡洛树搜索（MCTS）评估各种走法，最后选最优的一条。

这个方法听起来合理，但有一个致命问题：**扩展性差**。每多探索一个分支，就要多跑一次代码、多等一次训练，成本随分支数指数增长。对于需要真实执行的 MLE 任务（训练模型、跑回测），这种开销往往无法承受。

这篇论文提出了一个截然不同的思路：**把推理步骤类比为优化中的梯度**。与其在一棵巨大的搜索树上枚举各种可能，不如从当前的执行反馈中计算一个"改进方向"，然后沿着这个方向直接迈出一步。这正是 Gome 系统的核心思想，相关执行轨迹（GPT-5 Traces）已公开在 HuggingFace 上，供研究者分析智能体的真实推理路径。

对于非专业读者：树搜索就像在迷宫里把每条岔路都走一遍记录下来，最后选最短的；而"推理即梯度"则像带了一个指南针——你不需要走遍所有路，只需要知道"出口在北边"，然后一直朝北走就行。

## 核心思想

### 树搜索为什么不够用

传统树搜索式智能体的工作方式：

1. 从当前状态出发，生成若干候选动作（分支）；
2. 对每个分支执行（或模拟）一段，评估其结果；
3. 选择表现最好的分支继续；
4. 重复以上过程直到完成任务。

问题在于：

- **执行成本高**：每个分支都要真实运行代码或训练模型，MLE 任务单次执行可能耗时数十分钟；
- **分支组合爆炸**：每一步都有多种选择，搜索空间随深度指数增长；
- **反馈利用不充分**：很多分支的结果被"看过即弃"，没有转化为对下一步方向的系统性指导。

### 核心类比：推理 = 梯度，经验 = 动量

论文借用数值优化中的两个概念：

- **梯度（Gradient）**：当前点的反馈指明了"损失下降最快的方向"。在智能体场景中，执行结果（报错、指标变化、日志）就像梯度——它告诉你下一步应该往哪个方向改进，而不需要枚举所有可能性。
- **动量（Momentum）**：优化中动量累积历史梯度方向，加速收敛并减少震荡。对应到智能体，历史上成功的解决方案和失败经验被累积为"动量"，让后续步骤更稳定、更有方向性。

于是智能体的推理过程变成：

1. 执行当前方案，获得真实反馈（梯度）；
2. 将反馈结构化为"诊断 + 改进方向"；
3. 结合历史成功经验（动量）生成下一步方案；
4. 沿该方向执行一步，再获取新的反馈；
5. 重复直到收敛（任务完成或指标不再提升）。

这与梯度下降算法"计算梯度 → 更新参数 → 重新计算梯度"的迭代模式高度同构。

### 执行轨迹的作用

Gome 系统强调**执行轨迹（execution traces）**的价值：智能体每一步的输入、执行输出、诊断推理都被完整记录。这些轨迹既是"动量"的来源（历史经验库），也是分析智能体行为的研究材料。GPT-5 Traces 数据集的公开，正是为了让社区能够研究"基于梯度的推理"在真实任务中的表现。

## 在项目中的应用

需要首先说明：**这篇论文对 multialpha 是方法论影响（influence），而非直接代码实现**。项目没有逐行复刻 Gome 系统，但其"用反馈指引方向、而非盲目搜索分支"的理念，深刻影响了项目的反馈与假设生成设计。

### Summarizer 的方向性反馈

最直接的体现是量化场景中的反馈模块：

- 代码位置：
  [rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)

在 `QlibFactorExperiment2Feedback.generate_feedback()`（feedback.py:55）中，系统将本轮实验结果与 SOTA 结果并排比较，然后让 LLM 返回结构化 JSON，其中包含五个关键字段：

```text
Observations          观察到的现象
Feedback for Hypothesis  对当前假设的评价
New Hypothesis        新假设（下一步方向）
Reasoning             推理过程
Replace Best Result   是否替换当前最优
```

这里的 **"New Hypothesis"** 字段正是论文中"梯度方向"的工程对应物：

- 树搜索式做法：本轮同时提出 5 个不同方向的假设，全部跑一遍，选最好的；
- 梯度式做法（项目采用）：本轮只沿一个方向做实验，拿到 IC/收益/回撤的真实反馈后，由 Summarizer 诊断"这个方向哪里好、哪里不好"，然后生成**一个**新的假设作为下一步方向。

这避免了昂贵的多分支并行探索，每一轮反馈都直接指向下一轮的改进方向。

### Trace 作为"动量"

项目的 Trace 机制（见
[rdagent/core/proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py)
中的 `Trace` 类）记录了每一轮的假设、实验、反馈和决策。下一轮假设生成时，会读取：

- 当前 SOTA 假设与结果（当前最优点）；
- 最近一次反馈（最新梯度）；
- 完整历史链（动量/累积经验）。

这正是"动量"思想的体现：不是每轮从零开始，而是带着历史经验沿已有方向继续前进。

### 与 Bandit 方向选择的互补

在 quant 联合优化场景中，项目还使用 Bandit/Thompson Sampling 在"因子方向"和"模型方向"之间做选择（见
[rdagent/scenarios/qlib/proposal/bandit.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py)
）。这与"推理即梯度"并不矛盾：Bandit 决定大的探索方向（类似于选择在哪个参数空间上计算梯度），而 Summarizer 的方向性反馈则在选定方向内做精细的梯度更新。两者共同构成了"有方向的探索"而非"盲目的树搜索"。

## 通俗例子

假设你是一个量化研究员，正在尝试提升一个选股模型的 IC。

**树搜索式做法（笨办法）：**

> 本轮同时尝试 10 个方向：改学习率、加层、换激活函数、加因子、减因子、加 dropout、换优化器……
> 每个方向都跑一遍完整回测（每遍 1 小时），共花 10 小时。最后发现"加层 + 降学习率"组合最好。
> 下一轮再围绕这个组合枚举 10 个变种……
> 几轮下来，GPU 账单暴涨，但你也不确定是不是漏掉了更好的方向。

**梯度式做法（Gome / multialpha 的思路）：**

> 第 1 轮：先加一层网络，跑回测。IC 从 0.040 升到 0.045，但回撤变大了。
> 反馈（梯度）："加层有效但过拟合，下一步应加 dropout 并增大训练数据。"
>
> 第 2 轮：加 dropout = 0.2，IC 升到 0.048，回撤恢复正常。
> 反馈："方向正确，可继续微调 dropout 并尝试加入换手率因子。"
>
> 第 3 轮：加入换手率因子，IC 升到 0.052……

每一轮只走一步，但每一步都有真实反馈指明方向。就像梯度下降一样，虽然每步不大，但几步下来就能走到一个不错的最优点——而且总成本远低于"枚举所有分支"。

## 相关链接

- **arXiv 论文**：[https://arxiv.org/abs/2603.01692](https://arxiv.org/abs/2603.01692)
- **论文标题**：*Reasoning as Gradient: Scaling MLE Agents Beyond Tree Search*
- **作者**：Yifei Zhang 等
- **年份**：2026
- **会议**：ACL 2026 Findings
- **项目反馈模块（"New Hypothesis" 字段）**：
  [rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)
- **项目 Trace 记忆机制（动量对应物）**：
  [rdagent/core/proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py)
- **方向选择 Bandit（与梯度式更新互补）**：
  [rdagent/scenarios/qlib/proposal/bandit.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py)

{% endraw %}
