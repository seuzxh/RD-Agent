---
title: FT-Dojo 自主LLM微调
layout: default
---

{% raw %}

# FT-Dojo 自主LLM微调

> 论文：*FT-Dojo: Towards Autonomous LLM Fine-Tuning with Language Agents*
> 作者：Qizheng Li 等（2026）
> arXiv：[2603.01712](https://arxiv.org/abs/2603.01712)
> 接收会议：ICML 2026

## 概述

微调（Fine-Tuning）一个大语言模型（LLM）听起来简单——准备点数据、跑个训练脚本就行——但真正做过的人都知道，这里面坑非常多：用什么数据集？数据怎么清洗和格式化？学习率设多少？训练几轮？用 LoRA 还是全参数微调？怎么判断模型有没有变好？

这些决策以往都需要有经验的工程师手工完成。FT-Dojo 提出了一个名为 **FT-Agent** 的语言智能体，让它像一名不知疲倦的"AI 训练工程师"一样，**自主完成数据集选择、超参数配置、训练执行、效果评估和下一轮改进**的完整闭环。

FT-Dojo 同时提供了一个标准化的微调基准（benchmark），用来衡量不同智能体在"自动完成 LLM 微调任务"这件事上的表现。

对于非专业读者，可以这样理解：过去调一个模型像是老师傅凭手感做菜，咸了加水、淡了加盐；FT-Agent 则是一个装备了自动盐度计和菜谱库的自动炒菜机，它自己尝、自己调，一遍一遍直到味道达标。

## 核心思想

### 问题：微调不是"一键运行"

一次成功的 LLM 微调包含若干相互依赖的决策：

1. **数据准备**：选择哪些数据集？如何划分训练/验证/测试？怎样格式化指令？
2. **训练配置**：学习率、batch size、训练轮数、权重衰减、warmup 步数等超参数。
3. **训练方式**：全参数微调、LoRA、QLoRA 等不同策略的选择。
4. **评估与迭代**：在验证集上评估，根据损失曲线和指标判断下一步调整方向。

每一步都可能出错，而错误往往在训练跑了几小时之后才暴露，成本很高。

### FT-Agent 的闭环

FT-Agent 把微调变成一个与 RD-Agent 类似的自动研发循环：

1. **规划（Plan）**：分析目标任务，选择候选数据集和训练策略。
2. **配置（Configure）**：自动生成训练所需的全部超参数和配置文件。
3. **执行（Execute）**：启动训练作业，监控损失曲线和资源使用。
4. **评估（Evaluate）**：在验证集和测试集上运行评估，提取关键指标。
5. **诊断与迭代（Diagnose & Iterate）**：分析失败原因（过拟合、欠拟合、数据噪声等），调整配置后重新训练。

### 关键设计要点

- **Fail-fast 校验**：在正式训练前先做小规模烟雾测试（smoke test），快速发现数据格式错误、显存不足等问题，避免浪费数小时 GPU 时间。
- **多级反馈分析**：不仅看最终指标，还分析训练过程中的损失曲线、验证集表现变化，从而判断是该调学习率、增加数据还是提前停止。
- **经验复用**：成功的微调配置和失败的错误模式被记录下来，供后续任务参考——这与 RD-Agent 框架中的 Trace/知识图谱思路一脉相承。

## 在项目中的应用

需要首先说明：**multialpha 项目的核心场景是量化投资（基于 Qlib），LLM 微调是框架中的一个独立、次要场景**，而非主线功能。

RD-Agent 框架本身是一个通用的数据科学自动研发框架，量化（qlib）只是其中一个场景实现。FT-Dojo 所描述的微调场景对应框架中的 `finetune` 场景设计：

- 框架核心中预留了 finetune 场景的支持，例如
  [rdagent/core/proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py)
  的 `get_sota_experiment()` 方法注释中明确标注"first used in the finetune scenario"；
- 工作区环境配置
  [rdagent/utils/env.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/env.py)
  中也将 `"finetune"` 作为一个标准场景名称示例。

FT-Dojo 对本项目的启示主要体现在**方法论层面**：

1. **结构化迭代规划**：FT-Agent 的"规划→配置→执行→评估→诊断"循环，与 quant 场景中"假设生成→代码实现→Qlib 回测→反馈总结→下一轮假设"的循环是同构的。
2. **Fail-fast 思想**：CoSTEER 代码进化模块在正式提交完整回测前会先做代码可执行性检查，这与 FT-Dojo 的烟雾测试理念一致。
3. **多级反馈**：项目中 Summarizer 不仅提取 IC、年化收益等最终指标，还让 LLM 分析指标变化原因并生成新假设（New Hypothesis），这种"诊断式反馈"与 FT-Agent 的多级反馈分析思路相同。

如果读者希望研究 LLM 微调场景的完整实现，可以参考 RD-Agent 上游项目中 `rdagent/app/finetune/` 目录的设计（特别是 `rdagent/app/finetune/llm/` 子目录），其中包含了 FT-Agent 的具体落地代码。

## 通俗例子

假设你想微调一个模型来做中文情感分类。

**传统手工方式：**

1. 你从网上下载几个数据集，不知道哪个质量好，先随便选一个；
2. 学习率设为 2e-5（网上教程都这么写），batch size 设为 16；
3. 训练跑了 3 小时，结果验证集准确率只有 60%；
4. 你猜可能是学习率太大，改成 1e-5 又跑 3 小时；
5. 这次准确率 65%，但你不确定是数据问题还是模型问题，只能继续试。

**FT-Agent 方式：**

1. 智能体先分析任务类型，从候选数据集中挑选两个最相关的，并用小样本做烟雾测试；
2. 它发现数据集 A 格式有问题，自动修正后再启动正式训练；
3. 训练过程中监控到验证损失在第 2 轮后开始上升，判定为过拟合，自动提前停止；
4. 评估后给出诊断："数据量不足导致过拟合，建议增加数据并降低学习率"；
5. 下一轮自动加载更多数据、调整学习率后重新训练，准确率提升到 82%。

整个过程就像一个经验丰富的工程师在操作，但不需要人盯着——这就是 FT-Dojo 的目标。

## 相关链接

- **arXiv 论文**：[https://arxiv.org/abs/2603.01712](https://arxiv.org/abs/2603.01712)
- **论文标题**：*FT-Dojo: Towards Autonomous LLM Fine-Tuning with Language Agents*
- **作者**：Qizheng Li 等
- **年份**：2026
- **会议**：ICML 2026
- **项目中 finetune 场景相关引用**：
  [rdagent/core/proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py)（
  `get_sota_experiment` 注释提及 finetune 场景）
- **项目中工作区场景配置**：
  [rdagent/utils/env.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/env.py)

{% endraw %}
