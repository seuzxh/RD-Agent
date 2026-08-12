---
title: 引用论文
layout: default
---

{% raw %}

# 引用论文

本目录收录 multiα1pha 项目在设计与实现过程中参考、复现或直接依赖的学术论文。这些论文共同构成了项目的方法论基础：从自主研发智能体框架（RD-Agent）、数据中心自动研发基准（RD2Bench）、代码进化引擎（CoSTEER），到量化金融场景落地（RD-Agent-Quant），以及细粒度微调（FT-Dojo）、梯度式推理优化（Gome）等扩展方向，并以微软 Qlib 作为量化研究基础设施底座。

每篇论文对应一份中文解读文档，按编号 `01` 至 `07` 排列，可点击"文档链接"查看。

## 论文索引

### 核心框架论文

| 序号 | 论文标题 | arXiv / 链接 | 发表会议 / 年份 | 在项目中的应用 | 文档链接 |
|------|----------|--------------|-----------------|----------------|----------|
| 01 | R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science | [arXiv:2505.14738](https://arxiv.org/abs/2505.14738) | arXiv 2025 | 项目整体框架来源：两阶段（Research / Development）六组件的自主研发闭环，定义 Hypothesis、Experiment、CoSTEER、Feedback 等核心流程 | [01-rd-agent.md](01-rd-agent.md) |
| 02 | Towards Data-Centric Automatic R&D（RD2Bench） | [arXiv:2404.11276](https://arxiv.org/abs/2404.11276) | arXiv 2024 | 数据中心自动研发（D-CARD）任务定义与评测基准，支撑 factor_from_report 场景中"从研报提取公式并编码实现"的方法抽取与实现评估 | [02-data-centric.md](02-data-centric.md) |
| 03 | Collaborative Evolving Strategy for Automatic Data-Centric Development（CoSTEER） | [arXiv:2407.18690](https://arxiv.org/abs/2407.18690) | arXiv 2024 | 代码自动生成与进化引擎：多轮"生成—执行—评估—修正"循环，配合成功/失败经验库 RAG 检索，是项目因子与模型代码迭代的核心执行器 | [03-costeer.md](03-costeer.md) |
| 04 | R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization | [arXiv:2505.15155](https://arxiv.org/abs/2505.15155) | NeurIPS 2025 | 量化金融场景落地：因子—模型联合优化、Bandit/Thompson Sampling 方向调度、Qlib 回测闭环，直接对应 quant 全流程协同场景 | [04-rd-agent-quant.md](04-rd-agent-quant.md) |

### 扩展场景论文

| 序号 | 论文标题 | arXiv / 链接 | 发表会议 / 年份 | 在项目中的应用 | 文档链接 |
|------|----------|--------------|-----------------|----------------|----------|
| 05 | FT-Dojo: Towards Autonomous LLM Fine-Tuning with Language Agents | [arXiv:2603.01712](https://arxiv.org/abs/2603.01712) | ICML 2026 | 端到端 LLM 自主微调基准与 FT-Agent，其结构化迭代规划、fail-fast 校验、多级反馈分析为项目模型微调与数据构建提供参考 | [05-ft-dojo.md](05-ft-dojo.md) |
| 06 | Reasoning as Gradient: Scaling MLE Agents Beyond Tree Search（Gome） | [arXiv:2603.01692](https://arxiv.org/abs/2603.01692) | ACL 2026 | 将结构化诊断推理建模为梯度、成功记忆建模为动量的 MLE 智能体，为项目从树搜索转向有向更新的优化范式提供思路 | [06-reasoning-as-gradient.md](06-reasoning-as-gradient.md) |

### 基础设施

| 序号 | 论文标题 | arXiv / 链接 | 发表会议 / 年份 | 在项目中的应用 | 文档链接 |
|------|----------|--------------|-----------------|----------------|----------|
| 07 | Qlib: An AI-oriented Quantitative Investment Platform | [arXiv:2009.11189](https://arxiv.org/abs/2009.11189) | arXiv 2020（微软） | 量化基础设施底座：提供行情数据、因子表达式引擎、模型训练、回测与组合生成全链路，项目四个量化场景均构建于 Qlib 之上 | [07-qlib.md](07-qlib.md) |

{% endraw %}
