---
title: R&D-Agent-Quant 量化多智能体框架
layout: default
---

{% raw %}

# R&D-Agent-Quant 量化多智能体框架

> arXiv:2505.15155 · Yuante Li 等 · 2025 · 被 NeurIPS 2025 接收
>
> 如果说 RD-Agent 是"让 AI 做自动研发"的通用框架，那么这篇论文就是它在**量化金融**领域的专业化落地：
> **让 AI 同时做"选因子"和"调模型"两件事，像一个完整的量化团队。**

---

## 1. 论文概述

一个真实的量化团队通常由两拨人组成：一拨人挖**因子**（什么样的信号能预测未来涨跌），
另一拨人做**模型**（用什么算法把这些信号组合成交易信号）。
传统自动化方案往往只做其中一半——要么自动挖因子、模型固定用 LightGBM；
要么自动调模型、因子库固定不变。

R&D-Agent-Quant 的核心突破是：**把"因子"和"模型"放进同一个自动研发闭环里联合优化。**
系统每一轮都要先决定"这一轮去探索新因子，还是去调模型"，然后提出假设、写代码、跑回测、看反馈，
再进入下一轮。它还能直接"读"卖方研报 PDF，把里面的因子复现出来。

一句话总结这篇论文：**它不是只会搬砖的因子矿工，也不是只会调参的炼丹师，而是一个会自己决定"今天该干嘛"的量化团队。**

这篇论文是 RD-Agent 系列在量化金融场景的延伸，相关基础范式可参考
[02-data-centric.md](02-data-centric.md)。

---

## 2. 核心思想

### 2.1 联合优化：因子与模型不再各干各的

论文指出，因子和模型是**相互依赖**的：

- 好因子配烂模型，信号被浪费；
- 好模型配烂因子，等于"垃圾进、垃圾出"；
- 只优化其中一个，会很快遇到瓶颈。

因此 R&D-Agent-Quant 让智能体在同一个历史轨迹（Trace）上同时积累因子库和模型库，
并根据上一轮的真实回测结果决定下一步往哪个方向发力。

### 2.2 Bandit 动作选择：这一轮挖因子还是调模型

这是论文最核心的机制设计。每一轮开始时，系统面临一个**两臂老虎机（Two-Armed Bandit）**选择：

- `factor` 臂：探索新因子；
- `model` 臂：调整模型结构或超参数。

论文采用**线性 Thompson Sampling** 来做这个决策。它把上一轮的回测指标
（IC、ICIR、Rank IC、年化收益、信息比率、最大回撤、夏普等共 8 维）组成特征向量，
分别为 factor 和 model 两个臂维护一个后验分布，每轮采样后选择期望收益更高的那个臂。

奖励函数是这 8 个指标的加权和，权重在代码里写死为
`(0.1, 0.1, 0.05, 0.05, 0.25, 0.15, 0.1, 0.2)`，其中年化收益权重最高。

### 2.3 因子库的累积与 SOTA 因子组合

系统会维护一个**SOTA 因子库**。每轮新因子回测时：

1. 先把历史上所有"被接受"的 SOTA 因子拼接成基线特征矩阵；
2. 新因子与 SOTA 因子两两计算截面相关性，**相关系数 ≥ 0.99 的新因子被视为重复、直接剔除**；
3. 去重后的新因子与 SOTA 因子拼接在一起，重新跑回测；
4. 如果组合后的指标超过原 SOTA，则新因子被"收编"进因子库，成为下一轮的基线。

这意味着因子库是**只增不减、持续积累**的，越跑越强。

### 2.4 模型的 SOTA 替换

模型侧类似但规则不同：

- 当新模型在**年化超额收益**上优于当前 SOTA 模型时，替换 SOTA；
- 之后挖因子时，会自动用当前 SOTA 模型来回测新因子（而不是退回 LightGBM）；
- 反过来，调模型时也会基于当前 SOTA 因子库来评估，保证两边始终"门当户对"。

### 2.5 因子任务卡与模型任务卡

为了让 LLM 能结构化地输出假设，论文设计了两种"任务卡"：

**因子任务卡**包含：因子名、类型标签（如 `[Momentum Factor]`）、LaTeX 公式、变量说明。
例如一个反转因子会写成 $R_t = (C_{t-1} - C_{t-n}) / C_{t-n}$，并注明每个变量含义。

**模型任务卡**包含：模型名、描述、LaTeX 形式化、网络结构、变量、模型超参数、训练超参数、模型类型
（`Tabular` 或 `TimeSeries`）。

### 2.6 PDF 研报复现

论文的第三个输入源是**卖方研报 PDF**。系统会：

1. 用 LangChain 读取 PDF 文本；
2. 用 LLM 从文本中抽取因子公式、变量定义；
3. 把抽取结果转成标准的因子任务卡；
4. 进入与自动生成因子相同的"编码 → 回测 → 反馈"流程。

这使得系统能直接"读懂"人类研究员的成果并验证其在给定数据集上是否成立。

### 2.7 渐进式复杂度：先简单因子，后机器学习因子

论文通过提示词工程控制因子探索的节奏：

- 前 15 轮：要求从各种角度尝试**最简单、最快见效**的因子（价格、成交量、波动率等）；
- 第 15 轮之后：鼓励尝试**高 IC 的复杂因子**，特别是机器学习类因子，并避免与因子库中已有因子重复。

在 quant 联合场景里，这个阈值缩短为 6 轮（因为模型探索会分散轮次）。

---

## 3. 核心结论

论文在 A 股行情数据上做了大量对比实验，主要结论如下：

1. **联合优化显著优于只做因子或只做模型的基线。**
   只挖因子的方案会在因子库扩充到一定程度后遭遇边际收益递减；
   只调模型的方案受限于固定因子的信息量。联合优化通过 Bandit 在两条路径间动态分配轮次，
   最终取得更高的年化收益和 IC。

2. **SOTA 因子组合机制有效。**
   把新因子与历史最优因子组合后回测，比单独评估新因子更能反映其真实增量价值；
   去重机制避免了因子库膨胀但信息量不增的问题。

3. **SOTA 模型替换基于年化收益提升。**
   以年化超额收益作为模型替换的硬指标，比用 IC 或损失函数更贴近量化实战目标。

4. **PDF 研报复现达到人类水平。**
   在标注好的研报数据集上，系统自动抽取并复现的因子，其回测表现与人工复现基本一致，
   证明了"读研报 → 写代码 → 回测"这条链路的可行性。

5. **Bandit 策略优于固定顺序或随机选择。**
   相比"先挖 N 轮因子再调 M 轮模型"的固定策略，Thompson Sampling 能根据近期表现自适应切换，
   在有限轮次内取得更高的累计奖励。

---

## 4. 在 multialpha 中的应用

multialpha（基于 RD-Agent + Qlib 的量化研究平台）完整实现了这篇论文的全部机制，
并且这些机制不是隐藏在论文里的概念，而是**可以直接在代码里逐行追踪**的。

### 4.1 四个入口场景

项目在 [rdagent/app/qlib_rd_loop/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/)
下提供了四个独立入口，对应论文的四种运行模式：

| 场景 | 入口文件 | 作用 |
|------|----------|------|
| 纯因子 | [factor.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py) | 只挖因子，模型固定为 LightGBM |
| 纯模型 | [model.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/model.py) | 只调模型，因子固定为 Alpha158/Alpha20 |
| 联合（quant） | [quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py) | Bandit 决定挖因子还是调模型 |
| 研报复现 | [factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py) | 从 PDF 研报抽取因子并回测 |

其中 `QuantRDLoop` 在每一轮通过 `hypo.action` 字段分流到因子或模型的编码/回测/反馈链路。

### 4.2 Bandit 动作选择的代码实现

联合假设生成器位于
[rdagent/scenarios/qlib/proposal/quant_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py)：

- `QlibQuantHypothesisGen` 支持三种动作选择策略：`bandit`、`llm`、`random`，由配置项 `action_selection` 控制；
- 默认使用 bandit，第一轮默认走 `factor`（因为还没有历史指标）；
- 每轮结束后，调用 `trace.controller.record(metric, prev_action)` 把上一轮的指标和动作喂给 Bandit，
  再调用 `trace.controller.decide(metric)` 选出下一轮动作。

Bandit 本体在
[rdagent/scenarios/qlib/proposal/bandit.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py)：

- `LinearThompsonTwoArm` 为 factor/model 各维护一个 8 维高斯后验；
- `EnvController.reward()` 用固定权重把指标向量压成标量奖励；
- `extract_metrics_from_experiment()` 从 Qlib 回测结果中抽取 IC、ICIR、Rank IC、年化收益、IR、MDD、Sharpe。

值得注意的是，quant 场景在构造上下文时会做**动作相关的轨迹筛选**：
选 factor 时只把历史 factor 实验和最近一个被接受的 model 实验塞进 prompt；
选 model 时则反过来。这避免了无关历史干扰 LLM 的判断。

### 4.3 因子假设生成与渐进复杂度

纯因子假设生成器在
[rdagent/scenarios/qlib/proposal/factor_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py)。
它的 RAG 提示词根据轮次切换：

- `len(trace.hist) < 15` 时："Try the easiest and fastest factors..."；
- 否则："Now, you need to try factors that can achieve high IC (e.g., machine learning-based factors)."。

在 quant 场景中，这个阈值由 `QlibQuantHypothesisGen` 改为 6 轮。

因子任务卡的格式规范定义在
[rdagent/scenarios/qlib/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml)
的 `factor_hypothesis_specification` 和 `factor_experiment_output_format` 中，
明确要求每轮生成 **1–5 个因子**、先简单后复杂、必须包含 LaTeX 公式和变量说明。

`QlibFactorHypothesis2Experiment.convert_response()` 会把 LLM 返回的 JSON 解析成 `FactorTask` 列表，
并基于历史 SOTA 实验做**去重**（同名因子不再重复实验）。

### 4.4 模型假设生成

模型侧在
[rdagent/scenarios/qlib/proposal/model_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py)。
其提示词规范要求：

- 只关注 PyTorch 模型架构，不做特征处理；
- 优先尝试 GRU/LSTM 等时序模型，暂不生成 GNN；
- 根据训练样本规模（约 47.8 万训练 / 12.8 万验证）控制模型大小；
- 如果上一个模型结构本身没问题，可以返回同名模型只调超参数。

模型任务卡比因子卡多出 `architecture`、`hyperparameters`、`training_hyperparameters`、`model_type` 等字段。

### 4.5 因子回测、IC 去重与 SOTA 因子继承

这是论文"因子库累积"机制的核心实现，位于
[rdagent/scenarios/qlib/developer/factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py)：

1. `develop()` 先递归执行基线实验（即上一轮 SOTA），拿到其因子数据；
2. `process_factor_data()` 把 SOTA 实验列表中的因子合并成 `SOTA_factor` 矩阵；
3. 对本轮新因子同样处理成 `new_factors`；
4. `deduplicate_new_factors()` 按日计算 SOTA 因子与新因子的截面相关系数，取时间均值后，
   **与任一 SOTA 因子相关系数 ≥ 0.99 的新因子列被剔除**；
5. 去重后的新因子与 SOTA 因子 `pd.concat` 拼接，保存为 parquet；
6. 如果当前存在 SOTA 模型（`QlibModelExperiment`），则注入其 `model.py` 和训练超参数，
   用 `conf_combined_factors_sota_model.yaml` 回测；否则用默认 LightGBM 配置
   `conf_combined_factors.yaml` 回测。

这意味着每次新因子都是在**当前最强因子 + 当前最强模型**的组合上接受检验，
而不是孤立地评分——这正是论文"联合优化"的精髓。

### 4.6 反馈决策规则

反馈生成位于
[rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)。

系统关注的三个核心指标定义在文件开头：

```python
IMPORTANT_METRICS = [
    "IC",
    "1day.excess_return_with_cost.annualized_return",
    "1day.excess_return_with_cost.max_drawdown",
]
```

`process_results()` 会把本轮结果与 SOTA 结果按这三个指标格式化成对比文本，喂给 LLM。
因子反馈的决策字段是 `Replace Best Result`（布尔值），模型反馈的决策字段是 `Decision`。
LLM 输出 JSON 后，由 `convert2bool()` 解析成最终的 `decision` 标志：

- `decision=True`：本轮结果成为新的 SOTA，因子/模型被收编进库；
- `decision=False`：本轮结果被丢弃，但观察和经验仍会进入 Trace 供下一轮参考。

### 4.7 PDF 研报抽取管线

研报复现相关代码集中在
[rdagent/scenarios/qlib/factor_experiment_loader/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/)：

- [pdf_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py)
  负责读取 PDF、分类（是否为含因子的金工研报）、调用 LLM 抽取因子；
- [json_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/json_loader.py)
  把抽取结果转成标准的 `QlibFactorExperiment`；
- [prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml)
  定义了研报分类和因子抽取的提示词。

入口
[factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py)
遍历指定文件夹下的 PDF，逐份抽取后进入与纯因子场景完全相同的编码/回测/反馈循环。
每份研报默认最多抽取 `max_factors_per_exp` 个因子，避免单份研报产生过多任务。

---

## 5. 通俗例子

让我们跟着一个具体的 quant 联合场景走两轮，看看整个系统是怎么运转的。

### 第一轮：Bandit 选择"挖因子"

系统刚启动，Trace 为空，Bandit 没有历史数据，默认选择 `factor`。

**提出假设：** LLM 根据提示词"先从各种角度尝试简单因子"，提出假设：
"短期反转效应在 A 股小盘股中显著，过去 5 日跌幅越大的股票未来 1 日反弹概率越高。"
它一次性给出 3 个因子任务卡，其中一个是 5 日反转因子
$R_5 = (C_{t-1} - C_{t-5}) / C_{t-5}$。

**编码实现：** CoSTEER 为每个因子生成 `data.py`，在 Docker 里跑通因子计算，
失败的因子会自动迭代修复直到通过。

**回测：** `QlibFactorRunner` 把新因子送进 Qlib 容器。因为还没有 SOTA 模型，
使用默认 LightGBM，配置为 `conf_combined_factors.yaml`。
Qlib 跑完训练/验证/测试，返回 IC、年化收益、最大回撤。

**反馈：** 反馈模块把本轮结果与基线（Alpha158）并列：
IC 从 0.06 提升到 0.08，年化超额收益从 8% 提升到 11%。
LLM 判断 `Replace Best Result = true`，反转因子被收编进 SOTA 因子库。

**Bandit 更新：** `EnvController.record()` 把这轮的 8 维指标和 `factor` 动作喂给 Thompson Sampling，
更新 factor 臂的后验分布。

### 第二轮：Bandit 选择"调模型"

第二轮开始，Bandit 采样后认为 model 臂的期望奖励更高，于是选择 `model`。

**提出假设：** LLM 观察到当前 LightGBM 在时序数据上捕捉短期依赖能力有限，
提出假设："用一层 GRU 替代 LightGBM，利用过去 20 日的时序特征可以提升反转因子的收益。"
模型任务卡写明了 GRU 的 hidden_size、层数、dropout，以及学习率、batch_size、epoch 等训练超参数。

**编码实现：** 模型 CoSTEER 生成 `model.py`，定义 PyTorch GRU 网络，
Docker 内完成训练。因为当前存在 SOTA 因子库（含上一轮的反转因子），
回测配置自动切到 `conf_combined_factors_sota_model.yaml`，把 GRU 和 SOTA 因子组合起来评估。

**回测：** 结果显示 GRU 的年化超额收益从 11% 提升到 14%，但最大回撤略增。
LLM 在反馈中权衡后给出 `Decision = true`，GRU 成为新的 SOTA 模型。

**后续：** 从第三轮起，无论是挖新因子还是调模型，都会在"GRU + 反转因子库"这个新基线上进行。
如果某轮新因子和已有因子相关性过高，`deduplicate_new_factors()` 会直接把它剔除；
如果连续多轮因子都没超过 SOTA，Bandit 会更倾向于把轮次分配给 model 臂。

整个过程就像一个量化团队每周开一次会：因子研究员和模型研究员轮流推进，
谁最近进展好就给谁更多资源，好的成果沉淀下来成为团队的公共资产。

---

## 6. 相关链接

- 论文原文（arXiv）：<https://arxiv.org/abs/2505.15155>
- 论文标题：*R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization*
- 作者：Yuante Li 等
- 年份：2025（NeurIPS 2025）
- 联合场景入口：
  [rdagent/app/qlib_rd_loop/quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py)
- Bandit 动作选择：
  [rdagent/scenarios/qlib/proposal/quant_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py)
- Thompson Sampling 实现：
  [rdagent/scenarios/qlib/proposal/bandit.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py)
- 因子假设生成：
  [rdagent/scenarios/qlib/proposal/factor_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py)
- 模型假设生成：
  [rdagent/scenarios/qlib/proposal/model_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py)
- 因子实验定义：
  [rdagent/scenarios/qlib/experiment/factor_experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_experiment.py)
- 模型实验定义：
  [rdagent/scenarios/qlib/experiment/model_experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/model_experiment.py)
- 因子回测与 SOTA 继承：
  [rdagent/scenarios/qlib/developer/factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py)
- 因子/模型反馈决策：
  [rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)
- 提示词与任务卡规范：
  [rdagent/scenarios/qlib/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml)
- PDF 研报抽取管线：
  [rdagent/scenarios/qlib/factor_experiment_loader/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/)
- 研报复现入口：
  [rdagent/app/qlib_rd_loop/factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py)

{% endraw %}
