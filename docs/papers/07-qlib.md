---
title: Qlib 量化投资平台
layout: default
---

{% raw %}

# Qlib 量化投资平台

> 论文：*Qlib: An AI-oriented Quantitative Investment Platform*
> 作者：Xiao Yang 等（Microsoft Research）
> arXiv：[2009.11189](https://arxiv.org/abs/2009.11189)
> 年份：2020

## 论文概述

Qlib 是微软亚洲研究院开源的一个**面向 AI 的量化投资平台**。它的目标很简单：把量化研究中那些反复造轮子的工作——数据清洗、因子计算、模型训练、回测、组合构建——全部统一到一个框架里，让研究员可以把精力集中在"想出更好的因子和模型"上，而不是"怎么把数据管道跑通"。

在 Qlib 出现之前，量化研究的典型状态是：每个团队都有自己的一套数据格式、自己的训练脚本、自己的回测引擎，彼此不兼容，复现别人的结果极其困难。Qlib 提供了一套从数据到组合的端到端标准，使得"写一个因子 → 训练模型 → 回测看效果"这个流程可以用几行配置完成。

multialpha 项目正是构建在 Qlib 之上的：智能体（Agent）负责"想点子、写代码"，而 Qlib 负责"真刀真枪地跑数据、训练模型、算收益"。可以说，**Qlib 是 multialpha 的手脚和实验室，智能体是大脑**。

## 核心思想

### 三层架构：数据 → 模型 → 回测

Qlib 的核心是一条清晰的流水线：

```
原始行情数据
    ↓ （数据层：清洗、对齐、存储为高效二进制格式）
Qlib 数据格式（.bin 文件）
    ↓ （因子/表达式引擎：计算 Alpha158、Alpha360 或自定义因子）
特征矩阵（datetime × instrument × features）
    ↓ （模型层：LightGBM / 线性模型 / PyTorch 神经网络）
预测收益
    ↓ （回测层：TopkDropoutStrategy 等策略构建组合）
组合净值曲线、IC、年化收益、最大回撤
```

### 数据层：统一、高效的行情存储

Qlib 把 A 股（或美股）的日线行情预处理成自己的二进制格式，按交易日和股票代码对齐。研究员不需要自己处理停牌、复权、缺失值这些脏活，直接通过表达式引擎取数即可：

```text
$close          收盘价
$volume         成交量
Ref($close, 5)  5 天前的收盘价
Mean($close, 10) 10 日均价
```

multialpha 中使用的主要数据域是：

- **CSI300（沪深 300）**：市值最大、流动性最好的 300 只股票，作为默认股票池；
- **CSI500（中证 500）**：中盘 500 只股票，可作为扩展池；
- **Alpha158 因子集**：Qlib 内置的 158 个人工因子（动量、波动率、成交量、技术指标等），是默认的基线特征集；
- **Alpha360 因子集**：360 个基于过去 60 天价量序列的因子，更适合时序模型。

### 模型层：从 LightGBM 到自定义神经网络

Qlib 内置了多种模型：

- **LGBModel**：基于 LightGBM 的梯度提升树，是量化界最常用的基线模型，训练快、可解释性好；
- **LinearModel**：基于 OLS（普通最小二乘）的线性模型，作为最简单的对照；
- **PyTorch NN 模型**：支持用户自定义 `torch.nn.Module`，Qlib 负责数据加载、训练循环、早停等样板代码。

在 multialpha 中，LGBModel 是**验证新因子时的默认基线模型**——因为它训练快、稳定性好，能快速判断一个因子"有没有信号"；而当智能体尝试改进模型结构时，则会用自定义的 PyTorch 模型。

### 回测层：从预测到组合

模型输出每只股票的预测收益后，Qlib 的回测引擎根据策略构建模拟组合：

- **TopkDropoutStrategy**：每天买入预测收益最高的前 k 只股票，同时卖出排名跌出前 k+n 只的股票（n_drop 控制换手率）；
- **交易成本建模**：考虑买入佣金（open_cost）、卖出印花税（close_cost）、最小交易成本（min_cost）和涨跌停限制（limit_threshold）；
- **组合分析**：计算净值曲线、超额收益、夏普比率、最大回撤等。

### 为什么 AI 量化需要统一平台

AI 量化研究的迭代速度取决于"从想法到结果"的距离。Qlib 把这个距离缩短到：改一行配置或写一个表达式 → 一条命令跑出完整结果。没有统一平台，研究员 80% 的时间会花在数据对齐、bug 修复和格式转换上；有了 Qlib，这些时间可以用来想更多的因子和模型。

## 在 multialpha 中的应用

multialpha 中所有量化场景（因子挖掘、模型进化、量化联合、研报因子）都构建在 Qlib 之上。下面对照代码说明具体如何使用。

### Runner：智能体与 Qlib 的桥梁

智能体生成的因子代码或模型代码，最终都由 Runner 送入 Qlib 执行。

**因子 Runner**：
[rdagent/scenarios/qlib/developer/factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py)

`QlibFactorRunner.develop()`（factor_runner.py:78）的核心流程：

1. 收集智能体本轮生成的新因子，以及历史 SOTA（当前最优）因子；
2. 通过 `deduplicate_new_factors()`（factor_runner.py:47）计算新因子与 SOTA 因子的 IC 相关性，剔除相关系数 > 0.99 的冗余因子，避免"换汤不换药"；
3. 将合并后的因子数据保存为 parquet 文件；
4. 将数据和配置注入 Docker 工作区，调用 Qlib 执行完整训练 → 预测 → 回测流程；
5. 回测结果（IC、年化收益、最大回撤）被封装回实验对象，供 Summarizer 使用。

**模型 Runner**：
[rdagent/scenarios/qlib/developer/model_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py)

`QlibModelRunner.develop()`（model_runner.py:28）负责训练智能体设计的自定义 PyTorch 模型：

1. 注入 `model.py`（智能体生成的网络结构）；
2. 根据模型类型（Tabular 表格型 / TimeSeries 时序型）选择 Qlib 的 `DatasetH` 或 `TSDatasetH`；
3. 将训练超参数（n_epochs、lr、batch_size、weight_decay、early_stop）传入 Qlib；
4. 在 Docker 中训练并回测，返回结果。

### Simulator Prompt：告诉智能体 Qlib 怎么跑

智能体在写代码之前，需要知道"我的代码将在什么环境里运行、Qlib 会怎么用它"。这些信息通过 prompt 模板注入：

- 文件位置：
  [rdagent/scenarios/qlib/experiment/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml)

关键字段：

- **`qlib_factor_simulator`**（prompts.yaml:97）：告诉智能体因子将被送入 Qlib，依次完成"生成因子表 → 训练 LightGBM/LSTM/PyTorch 模型 → 基于预测构建组合 → 评估收益/夏普/回撤"。
- **`qlib_model_simulator`**（prompts.yaml:225）：告诉智能体模型将在 Qlib 中训练，Qlib 会自动生成基线因子表、训练自定义模型、构建组合并评估 IC/回撤等指标。
- **`qlib_factor_experiment_setting`**（prompts.yaml:161）：以表格形式告知智能体当前实验设置——"CSI300 股票池、LGBModel 模型、Alpha158 Plus 因子集、训练/验证/测试时间段"。

这些 prompt 让智能体对运行环境有准确的心理模型，从而写出格式正确、可执行的代码。

### Qlib 配置文件：训练与回测的完整定义

Qlib 的每次运行由一个 YAML 配置驱动，multialpha 在模板目录中维护了多套配置：

- [factor_template/conf_baseline.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_template/conf_baseline.yaml)：基线（仅 Alpha158，无新因子）；
- [factor_template/conf_combined_factors.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_template/conf_combined_factors.yaml)：新因子 + SOTA 因子合并，使用 LGBModel；
- [factor_template/conf_combined_factors_sota_model.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_template/conf_combined_factors_sota_model.yaml)：合并因子 + 已发现的最优自定义模型；
- [model_template/conf_baseline_factors_model.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/model_template/conf_baseline_factors_model.yaml)：基线因子 + 新自定义模型；
- [model_template/conf_sota_factors_model.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/model_template/conf_sota_factors_model.yaml)：SOTA 因子 + 新自定义模型。

这些 YAML 使用 Jinja2 模板，Runner 在执行时注入训练/验证/测试日期、特征名、模型超参数等。以 `conf_baseline.yaml` 为例，关键配置包括：

- **市场与基准**：`market: csi300`，`benchmark: SH000300`（沪深 300 指数）；
- **标签**：`Ref($close, -2)/Ref($close, -1) - 1`，即未来 2 日相对未来 1 日的收益率（预测下下期收益）；
- **模型**：默认为 `LGBModel`（LightGBM），支持通过 `model_selector` 切换为 LinearModel、XGBModel、CatBoostModel；
- **策略**：`TopkDropoutStrategy`，topk=50，n_drop=5；
- **交易成本**：买入 0.05%、卖出 0.15%、涨跌停限制 9.5%。

### 训练/验证/测试时间段

日期范围配置在
[rdagent/app/qlib_rd_loop/conf.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py)
中：

```text
训练集：2008-01-01 ～ 2014-12-31
验证集：2015-01-01 ～ 2016-12-31
测试集：2017-01-01 ～ 最新交易日（auto）
```

`test_end` 支持 `"auto"` 模式（conf.py:9），运行时自动取 Qlib 数据中的最新交易日，保证回测始终覆盖到最近。

### 提取哪些指标

反馈模块
[rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)
定义了三个核心指标（feedback.py:17）：

```text
IC
1day.excess_return_with_cost.annualized_return
1day.excess_return_with_cost.max_drawdown
```

Runner 从 Qlib 的 mlflow 记录中提取这些指标，Summarizer 将本轮结果与 SOTA 结果并排比较，再交给 LLM 生成反馈和下一轮假设。

### Docker 环境：可复现的 Qlib 执行沙箱

Qlib 运行在 Docker 容器中，配置位于
[rdagent/scenarios/qlib/docker/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/docker/)：

- [Dockerfile](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/docker/Dockerfile)：基于 PyTorch 2.2.1 + CUDA 12.1 镜像，从本地源码包安装 Qlib（对应官方 commit 2fb9380b，版本 0.9.7），并通过 `requirements.lock.txt` 锁定所有 Python 依赖版本；
- 行情数据以只读方式挂载到容器内 `~/.qlib/qlib_data/cn_data`；
- 智能体生成的代码在容器内真实执行，结果通过 mlflow 写回工作区。

这保证了每次回测的环境完全一致，结果可复现。

## 通俗例子

**Qlib 就像一个设备齐全的量化实验室。**

想象 multialpha 的智能体是一名研究员，而 Qlib 是实验室：

- **数据层是实验室的样品柜**：所有股票的行情数据已经清洗好、贴好标签，研究员不需要自己去采集和整理，直接取用即可；
- **因子表达式引擎是实验台**：研究员写下一个公式（如"5 日动量"），实验台自动算出全市场所有股票每天的因子值；
- **模型层是训练器材**：有 LightGBM 跑步机（快、稳）、也有 PyTorch 重型器械（灵活、强大），研究员选一个用来"训练预测能力"；
- **回测层是跑道**：模型预测出"哪些股票会涨"后，跑道模拟真实交易规则（手续费、涨跌停、滑点），跑出一条净值曲线；
- **IC、年化收益、最大回撤是计时器和成绩单**：告诉研究员这次实验到底好不好。

没有 Qlib，研究员每次想验证一个想法，都要自己找数据、洗数据、写训练脚本、搭回测引擎——可能光准备工作就要一周；有了 Qlib，研究员只需要说"我想试试这个因子"，Qlib 几分钟内就能给出成绩单。multialpha 的智能体之所以能"自主研发"，正是因为 Qlib 把这些基础设施全部准备好了——**智能体负责出主意，Qlib 负责把主意变成真实的数字**。

## 关键名词解释

### IC（Information Coefficient，信息系数）

IC 衡量模型预测值与未来真实收益之间的**相关性**（通常用 Spearman 秩相关系数）。

- IC = 1：预测和真实完全一致（完美）；
- IC = 0：预测和随机猜差不多（没用）；
- IC < 0：预测方向反了（反指）。

在 A 股选股中，IC 长期稳定在 0.03 ～ 0.08 就已经是不错的因子。IC 越高、越稳定，因子的预测能力越强。

### ICIR（IC Information Ratio）

ICIR = IC 的均值 / IC 的标准差。

它衡量的是 IC 的**稳定性**：两个因子平均 IC 可能相同，但一个时好时坏、另一个持续有效，ICIR 能区分它们。ICIR 越高，说明因子的预测能力越稳定可靠。Qlib 的 `SigAnaRecord` 会自动计算 IC 和 ICIR。

### 年化收益（Annualized Return）

将一段时间的收益率换算为"以年为单位"的复合增长率，方便不同长度的策略之间比较。multialpha 关注的是**扣费后的年化超额收益**（`excess_return_with_cost.annualized_return`），即策略收益相对基准（沪深 300 指数）的超额部分，且已经扣除了交易佣金和印花税。

### 最大回撤（Max Drawdown）

策略净值从历史最高点跌到后续最低点的最大跌幅，衡量**最坏情况下投资者可能亏多少**。

- 最大回撤 = -10%：最糟糕的时候从高点亏了 10%；
- 最大回撤 = -50%：最糟糕的时候腰斩。

最大回撤越大，策略风险越高。投资者通常希望在相同收益下选择回撤更小的策略。

### Alpha158

Qlib 内置的一套**人工因子库**，包含 158 个基于价量数据的特征，覆盖动量、反转、波动率、成交量、换手率、技术指标（MACD、RSI、KDJ 等）等类别。它是量化研究中最常用的基线特征集——任何新因子都应该在 Alpha158 的基础上证明自己提供了**增量信息**，而不是重复已有信号。multialpha 的因子实验默认就在 Alpha158 的基础上叠加智能体挖掘的新因子。

### TopkDropoutStrategy

Qlib 内置的一个经典选股策略：

1. 每个交易日，模型对所有股票打分（预测收益）；
2. 买入得分最高的前 `topk` 只股票（multialpha 中 topk=50）；
3. 持有的股票中，如果得分跌出前 `topk + n_drop` 名（multialpha 中 n_drop=5），则卖出；
4. 用腾出的资金买入新进入前 50 的股票。

这个策略简单、直观，且通过 n_drop 参数控制换手率（避免每天都大量交易导致手续费过高）。multialpha 所有回测都使用这一策略，保证结果的可比性。

## 相关链接

- **arXiv 论文**：[https://arxiv.org/abs/2009.11189](https://arxiv.org/abs/2009.11189)
- **论文标题**：*Qlib: An AI-oriented Quantitative Investment Platform*
- **作者**：Xiao Yang 等（Microsoft Research）
- **年份**：2020
- **Qlib 官方仓库**：[https://github.com/microsoft/qlib](https://github.com/microsoft/qlib)
- **项目中因子 Runner**：
  [rdagent/scenarios/qlib/developer/factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py)
- **项目中模型 Runner**：
  [rdagent/scenarios/qlib/developer/model_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py)
- **项目中反馈模块（指标提取）**：
  [rdagent/scenarios/qlib/developer/feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)
- **Simulator Prompt 定义**：
  [rdagent/scenarios/qlib/experiment/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/prompts.yaml)
- **Qlib 配置模板目录**：
  [rdagent/scenarios/qlib/experiment/factor_template/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_template/)
  和
  [rdagent/scenarios/qlib/experiment/model_template/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/model_template/)
- **训练/验证/测试日期配置**：
  [rdagent/app/qlib_rd_loop/conf.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py)
- **Docker 执行环境**：
  [rdagent/scenarios/qlib/docker/Dockerfile](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/docker/Dockerfile)

{% endraw %}
