# multialpha 智能体说明文档

> multialpha 是一个面向量化投研的多智能体自动研发平台。它通过五个核心智能体的协作，构建了一个从"研究假设"到"可执行策略"再到"结果反馈"的闭环研发系统。每个智能体各司其职，通过标准化的数据结构进行通信，共同驱动因子挖掘和模型调优的自动化迭代。

---

## 智能体总览

multialpha 的 R&D 循环由以下五个智能体组成，按执行顺序排列：

| 序号 | 智能体 | 核心职责 | 输入 | 输出 | 文档 |
|------|--------|----------|------|------|------|
| 1 | **HypothesisGen**（假设生成） | 基于历史反馈和市场观察，生成新的研究方向和假设 | Trace（历史轨迹） | Hypothesis（假设对象） | [01-hypothesis-gen.md](01-hypothesis-gen.md) |
| 2 | **Hypothesis2Experiment**（假设转实验） | 将抽象假设转化为结构化的可执行任务列表 | Hypothesis + Trace | Experiment（含 Task 列表） | [05-hypothesis2experiment.md](05-hypothesis2experiment.md) |
| 3 | **CoSTEER**（编码进化） | 通过"生成→执行→评估→修正"多轮循环，为每个 Task 编写可运行的 Python 代码 | Experiment（含 Task 规格） | Experiment（含可运行代码） | [02-costeer.md](02-costeer.md) |
| 4 | **Runner**（方案执行） | 在隔离的 Qlib 环境中执行代码，产出因子计算结果和回测指标 | Experiment（含代码） | Experiment（含执行结果） | [03-runner.md](03-runner.md) |
| 5 | **Summarizer**（反馈总结） | 分析回测结果，与 SOTA 对比，生成结构化反馈并决定是否更新 SOTA | Experiment（含结果）+ Trace | Feedback（反馈与决策） | [04-summarizer.md](04-summarizer.md) |

---

## R&D 闭环流程图

```
                          ┌─────────────────────────────────────────────────┐
                          │                    Trace                        │
                          │    (历史假设、实验、反馈、SOTA 的累积记录)         │
                          └───────────────┬─────────────────────────────────┘
                                          │ 读取历史
                                          ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐    ┌──────────────┐
│HypothesisGen │───▶│Hypothesis2Exp    │───▶│   CoSTEER    │───▶│    Runner    │
│  (假设生成)   │    │  (假设转实验)     │    │  (编码进化)   │    │  (方案执行)   │
│              │    │                  │    │              │    │              │
│ minimax-m3   │    │ minimax-m3       │    │ deepseek-v4  │    │ deepseek-v4- │
│ temp=0.7     │    │ temp=0.7         │    │ temp=0.5     │    │ flash        │
│              │    │                  │    │              │    │ temp=0.0     │
│ 核心能力:    │    │ 核心能力:        │    │ 核心能力:    │    │ 核心能力:    │
│ 创意发散     │    │ 结构化映射       │    │ 代码生成+修复│    │ 纯代码执行   │
│ 金融理解     │    │ 任务规格设计     │    │ JSON稳定输出 │    │ 无LLM调用    │
└──────────────┘    └──────────────────┘    └──────┬───────┘    └──────┬───────┘
                                                   │                   │
                                                   ▼                   │
                                          ┌──────────────┐             │
                                          │ Summarizer   │◀────────────┘
                                          │  (反馈总结)   │
                                          │              │
                                          │ glm-5.2      │
                                          │ temp=0.4     │
                                          │              │
                                          │ 核心能力:    │
                                          │ 数值推理     │
                                          │ 指标对比     │
                                          │ 决策判断     │
                                          └──────┬───────┘
                                                 │
                                                 ▼
                                          Feedback + SOTA 更新
                                                 │
                                    ┌────────────┘
                                    ▼
                            写入 Trace，进入下一轮循环
```

---

## 各智能体详细说明

### 1. HypothesisGen — 假设生成智能体

**文档**：[01-hypothesis-gen.md](01-hypothesis-gen.md)

**定义位置**：
- 抽象基类：[proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py)
- LLM 基类：[components/proposal/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py)
- Qlib 因子实现：[factor_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py)
- Qlib 模型实现：[model_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py)
- Quant 全流程实现：[quant_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py)

**核心功能**：
- 读取 Trace 中的历史假设与反馈
- 支持三种动作选择策略：Bandit（多臂老虎机）、LLM 决策、Random
- 生成包含假设描述、理由、观察、论证和知识提炼的结构化 Hypothesis 对象
- 在 Quant 场景中决定本轮做"因子挖掘"还是"模型调优"

**关键数据结构**：
```python
Hypothesis(
    hypothesis="...",           # 假设描述
    reason="...",               # 详细理由
    concise_reason="...",       # 简要理由
    concise_observation="...",  # 简要观察
    concise_justification="...",# 简要论证
    concise_knowledge="...",    # 简要知识
    action="factor" | "model",  # 仅 Quant 场景
)
```

---

### 2. Hypothesis2Experiment — 假设转实验智能体

**文档**：[05-hypothesis2experiment.md](05-hypothesis2experiment.md)

**定义位置**：
- 抽象基类：[proposal.py#L437-L445](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L437-L445)
- LLM 基类：[components/proposal/__init__.py#L86-L121](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L86-L121)
- Qlib 因子实现：[factor_proposal.py#L61-L132](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L61-L132)
- Qlib 模型实现：[model_proposal.py#L73-L159](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L73-L159)

**核心功能**：
- 将自然语言假设转化为结构化的 Task 列表
- 因子任务：因子名称、描述、LaTeX 公式、变量定义
- 模型任务：模型名称、架构、超参数、训练参数、模型类型
- 自动构建 `based_experiments` 基线链，继承历史 SOTA 因子
- 因子场景自动去重已存在的因子名
- 使用 `@wait_retry(retry_n=5)` 处理 LLM JSON 解析失败

**关键数据结构**：
```python
# 因子任务
FactorTask(factor_name, factor_description, factor_formulation, variables)

# 模型任务
ModelTask(name, description, architecture, hyperparameters,
          training_hyperparameters, formulation, variables, model_type)

# 实验
Experiment(sub_tasks=[Task1, Task2, ...], based_experiments=[...], hypothesis=...)
```

---

### 3. CoSTEER — 编码进化智能体

**文档**：[02-costeer.md](02-costeer.md)

**全称**：**Co**llaborative Evolving **S**trategy for Automatic Da**t**a-C**e**ntric D**e**velopment

**定义位置**：
- 核心框架：[components/coder/CoSTEER/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/)
- 因子实现：[factor_coder.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_coder.py)
- 模型实现：[model_coder.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_coder.py)

**核心功能**：
- 多轮"生成→执行→评估→修正"进化循环
- 每个子任务独立进化，支持多进程并行
- 三级评估流水线：执行检查 → 值/形状检查 → 代码审查
- V2 图知识库（无向图）存储任务、组件、错误和成功实现
- RAG 三步检索：历史任务轨迹 → 组件相似成功实现 → 错误相似修复
- 自动提取代码中的可复用组件并更新知识库

**进化循环**：
```
生成代码 → 沙箱执行 → 收集错误/结果 → 评估器打分
    ↑                                    │
    │         未通过                     ↓
    └──────── 修正反馈 ←──── 决定是否继续进化
              (通过则输出)
```

---

### 4. Runner — 方案执行智能体

**文档**：[03-runner.md](03-runner.md)

**定义位置**：
- 缓存基类：[components/runner/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/runner/__init__.py)
- 因子执行：[factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py)
- 模型执行：[model_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py)

**核心功能**：
- 在 Docker/Conda 隔离环境中执行代码
- `CachedRunner` 基类通过任务信息 MD5 哈希实现缓存
- 因子 Runner：计算因子值 → 合并基线因子 → IC 去重 → LightGBM 训练 → 回测
- 模型 Runner：数据集准备 → 模型训练 → 预测 → 信号生成 → 回测
- 自动递归执行 `based_experiments` 基线链中未完成的实验
- 因子验证模型可配置：LightGBM（默认）、Linear、XGBoost、CatBoost

**缓存机制**：
```python
cache_key = md5(all_task_information)  # 包含基线链中所有任务
```

---

### 5. Summarizer — 反馈总结智能体（Experiment2Feedback）

**文档**：[04-summarizer.md](04-summarizer.md)

**定义位置**：
- 抽象基类：[proposal.py#L451-L467](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L451-L467)
- Qlib 实现：[feedback.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py)

**核心功能**：
- 分析回测结果（IC、年化收益、最大回撤等）
- 与历史 SOTA 进行对比
- 生成结构化反馈：观察、假设评估、新假设方向、决策
- 决定是否将当前实验更新为新的 SOTA（`decision=True/False`）
- 异常处理：当 Runner 抛出异常时，生成包含错误信息的负面反馈
- 支持人工交互审核反馈

**关键数据结构**：
```python
HypothesisFeedback(
    observations="...",           # 实验观察
    hypothesis_evaluation="...",  # 假设评估
    new_hypothesis="...",         # 新假设方向
    reason="...",                 # 决策理由
    decision=True | False,        # 是否接受为 SOTA
)
```

---

## 多 LLM 模型配置

multialpha 采用**多模型分工策略**，为不同特性的任务匹配最适合的 LLM，而非"一个模型打天下"。以下是推荐配置及选型理由：

### 推荐配置

| R&D 步骤 | Logger Tag | LLM 模型 | Temperature | 核心能力需求 |
|----------|-----------|----------|-------------|------------|
| 假设生成 + 假设转实验 | `direct_exp_gen` | **minimax-m3** | **0.7** | 创意发散 + 金融领域理解 |
| 编码进化 | `coding` | **deepseek-v4** | **0.5** | 代码生成 + Bug 修复 + JSON 稳定输出 |
| 方案执行 | `running` | deepseek-v4-flash | 0.0 | 无 LLM 调用，配置保留 |
| 反馈总结 | `feedback` | **glm-5.2** | **0.4** | 数值推理 + 指标对比 + 决策判断 |

```json
CHAT_MODEL_MAP={
  "direct_exp_gen": {"model": "openai/minimax-m3", "temperature": "0.7"},
  "coding": {"model": "openai/deepseek-v4", "temperature": "0.5"},
  "running": {"model": "openai/deepseek-v4-flash", "temperature": "0.0"},
  "feedback": {"model": "openai/glm-5.2", "temperature": "0.4"}
}
```

### 选型理由详解

**① direct_exp_gen → minimax-m3 (temp=0.7)**

假设生成与实验设计属于**创意探索型任务**：
- 需要发散性思维，从历史反馈中发现新的研究方向
- MiniMax-M3 中文理解和创意生成能力强，适合头脑风暴
- temperature=0.7 在确定性和创造性之间取得平衡：既不会太随机产生无意义假设，也不会太保守陷入局部最优
- 失败代价低：错误假设会被后续的反馈环节淘汰，不会浪费太多计算资源

**② coding → deepseek-v4 (temp=0.5)**

CoSTEER 编码进化是整个系统的**核心瓶颈**，也是 LLM 调用最频繁、上下文最长、失败代价最高的环节：
- **代码能力顶尖**：DeepSeek-V4 在 Python/PyTorch/pandas 代码生成和修复上国内领先
- **JSON 输出稳定**：代码生成要求严格 JSON 格式返回 `code` 字段，DeepSeek 的 JSON 遵循度高，减少解析失败重试
- **数学/逻辑推理强**：因子公式实现涉及数值计算逻辑，需要强推理能力
- **长上下文支持**：256K 窗口足够容纳历史代码+错误信息+RAG 检索结果
- temperature=0.5 的考量：代码必须遵循严格接口（如必须有 `def calculate(df)` 函数），不宜像之前用 1.0 那样过于随机；但进化需要探索不同方案，也不宜低于 0.3 陷入重复
- 备选：追求极致代码质量可用 gpt-4o（成本高）；超长上下文刚需可用 kimi-k2.5（需将 temp 降到 0.5）

**③ running → deepseek-v4-flash (temp=0.0)**

Runner（[factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py) / [model_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py)）在当前版本中**不调用 LLM**，仅执行 Python 代码和计算回测指标。配置此条目是为了未来扩展（如动态代码调整），用最便宜快速的模型即可。

**④ feedback → glm-5.2 (temp=0.4)**

反馈总结属于**分析判断型任务**：
- 需要理解 IC、年化收益、最大回撤、夏普比率等量化指标的含义
- 要进行 SOTA 对比，权衡"年化提升但 IC 下降"这类复杂判断
- 智谱 GLM-5.2 在中文金融领域适配好，结构化输出稳定
- temperature=0.4：决策判断（是否更新 SOTA）应尽量确定，但新假设方向建议需要一定创意；0.6 偏高可能导致同一组结果产生不一致判断

### 选型原则

| 维度 | 假设生成 | 编码进化 | 反馈总结 |
|------|---------|---------|---------|
| 任务类型 | 创意发散 | 精确执行 | 分析推理 |
| 温度策略 | 高（0.7）探索多样性 | 中（0.5）平衡探索与规范 | 低（0.4）保证决策一致 |
| 模型导向 | 通用强模型 | 代码专用模型 | 推理强模型 |
| 关键约束 | JSON 输出稳定 | 长上下文+接口遵循 | 金融指标理解 |
| 失败代价 | 低（反馈环节淘汰） | **高**（浪费进化轮次） | 中（影响迭代方向） |
| 调用频率 | 每轮1次 | **每轮多次**（最多N次进化） | 每轮1-2次 |

---

## 三种运行场景

multialpha 支持三个入口场景，均复用相同的五个智能体：

### 场景一：因子挖掘（Factor）

- 入口：[factor.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py)
- 配置：`FactorBasePropSetting`
- 流程：假设生成 → 因子任务 → CoSTEER 编写因子代码 → 因子计算+IC验证+回测 → 反馈
- 环境变量前缀：`QLIB_FACTOR_`

### 场景二：模型调优（Model）

- 入口：[model.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/model.py)
- 配置：`ModelBasePropSetting`
- 流程：假设生成 → 模型任务 → CoSTEER 编写模型代码 → 模型训练+预测+回测 → 反馈
- 环境变量前缀：`QLIB_MODEL_`

### 场景三：全流程研发（Quant）

- 入口：[quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py)
- 配置：`QuantBasePropSetting`
- 流程：每轮通过 Bandit/LLM/Random 选择做因子还是模型，两套智能体动态切换
- 环境变量前缀：`QLIB_QUANT_`

### 特殊入口：PDF 研报复现

- 入口：[factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py)
- 从 PDF 研报中直接提取因子定义，绕过 HypothesisGen 和 Hypothesis2Experiment
- 后续仍使用 CoSTEER → Runner → Summarizer 进行代码实现和验证

---

## 核心数据流转

智能体之间通过以下核心数据结构传递信息：

```
Trace
  └── hist: List[Tuple[Experiment, Feedback]]
        │
        ├── Experiment
        │     ├── hypothesis: Hypothesis
        │     ├── sub_tasks: List[FactorTask | ModelTask]
        │     ├── based_experiments: List[Experiment]  (基线链)
        │     ├── sub_workspace_list: List[FBWorkspace] (代码工作区)
        │     └── result: ExperimentResult (执行结果)
        │
        └── Feedback
              ├── observations
              ├── hypothesis_evaluation
              ├── new_hypothesis
              ├── reason
              └── decision: bool (是否更新 SOTA)
```

**Trace** 是贯穿整个循环的记忆载体，每个智能体都从 Trace 中读取历史信息，并将自己的输出追加到 Trace 中。

---

## 论文来源

multialpha 的智能体设计基于以下学术研究：

| 论文 | arXiv | 相关智能体 |
|------|-------|-----------|
| R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science | [2505.14738](https://arxiv.org/abs/2505.14738) | 整体 R&D 循环框架 |
| R&D-Agent-Quant (NeurIPS 2025) | [2505.15155](https://arxiv.org/abs/2505.15155) | 量化场景因子/模型任务设计 |
| Towards Data-Centric Automatic R&D | [2404.11276](https://arxiv.org/abs/2404.11276) | CoSTEER 数据-centric 开发范式 |
| Automating Quantitative Finance Research with LLM-based Multi-Agent System | [2505.13172](https://arxiv.org/abs/2505.13172) | 多智能体协作机制 |

---

## 快速导航

- 想要了解假设如何生成？→ [01-hypothesis-gen.md](01-hypothesis-gen.md)
- 想要了解假设如何变成具体任务？→ [05-hypothesis2experiment.md](05-hypothesis2experiment.md)
- 想要了解代码如何自动编写和进化？→ [02-costeer.md](02-costeer.md)
- 想要了解代码如何执行和回测？→ [03-runner.md](03-runner.md)
- 想要了解结果如何分析和反馈？→ [04-summarizer.md](04-summarizer.md)
