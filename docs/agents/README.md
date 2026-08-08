# multiα1pha 智能体说明文档

> multiα1pha 是一个面向量化投研的多智能体自动研发平台。它通过五个核心智能体的协作，构建了一个从"研究假设"到"可执行策略"再到"结果反馈"的闭环研发系统。每个智能体各司其职，通过标准化的数据结构进行通信，共同驱动因子挖掘和模型调优的自动化迭代。

---

## 智能体总览

multiα1pha 的 R&D 循环由以下五个智能体和一个核心记忆系统组成，按执行顺序排列：

| 序号 | 智能体/系统 | 核心职责 | 输入 | 输出 | 文档 |
|------|------------|----------|------|------|------|
| 1 | **HypothesisGen**（假设生成） | 基于历史反馈和市场观察，生成新的研究方向和假设 | Trace（历史轨迹） | Hypothesis（假设对象） | [01-hypothesis-gen.md](01-hypothesis-gen.md) |
| 2 | **Hypothesis2Experiment**（假设转实验） | 将抽象假设转化为结构化的可执行任务列表 | Hypothesis + Trace | Experiment（含 Task 列表） | [05-hypothesis2experiment.md](05-hypothesis2experiment.md) |
| 3 | **CoSTEER**（编码进化） | 通过"生成→执行→评估→修正"多轮循环，为每个 Task 编写可运行的 Python 代码 | Experiment（含 Task 规格） | Experiment（含可运行代码） | [02-costeer.md](02-costeer.md) |
| 4 | **Runner**（方案执行） | 在隔离的 Qlib 环境中执行代码，产出因子计算结果和回测指标 | Experiment（含代码） | Experiment（含执行结果） | [03-runner.md](03-runner.md) |
| 5 | **Summarizer**（反馈总结） | 分析回测结果，与 SOTA 对比，生成结构化反馈并决定是否更新 SOTA | Experiment（含结果）+ Trace | Feedback（反馈与决策） | [04-summarizer.md](04-summarizer.md) |
| — | **Trace**（实验轨迹） | 贯穿全循环的记忆中枢，记录所有实验历史、SOTA、DAG演化关系，支持断点恢复 | 各步骤输出 | 持久化历史 | [06-trace.md](06-trace.md) |

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
- 多层评估流水线：执行检查 → 形状检查 → 值检查 → 代码审查 → 最终决策
- V2 图知识库（无向图）存储任务、组件、错误和成功实现（5 种节点标签）
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

multiα1pha 采用**多模型分工策略**，为不同特性的任务匹配最适合的 LLM，而非"一个模型打天下"。以下是推荐配置及选型理由：

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

### CHAT_MODEL_MAP 配置参数说明

`CHAT_MODEL_MAP` 通过 `.env` 文件配置，是一个 JSON 对象，key 为 logger tag（对应 R&D 步骤），value 为该步骤的模型配置。代码实现在 [litellm.py#L106-L125](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py#L106-L125)，通过匹配当前日志上下文中的 tag 来选择模型。

#### 配置格式

```json
CHAT_MODEL_MAP={
  "<logger_tag>": {
    "model": "<provider/model_name>",
    "temperature": "<float>",
    "max_tokens": "<int>",
    "reasoning_effort": "<low|medium|high>"
  }
}
```

#### 各参数含义

| 参数 | 类型 | 默认值 | 含义 | 取值范围与说明 |
|------|------|--------|------|--------------|
| **model** | string | `gpt-4-turbo` | LLM 模型名称 | 格式为 `provider/model_name`，通过 [LiteLLM](https://docs.litellm.ai/) 统一调用。支持 OpenAI 兼容接口，常用值：`openai/gpt-4o`、`openai/minimax-m3`、`openai/kimi-k2.5`、`openai/deepseek-v4`、`openai/glm-5.2` 等 |
| **temperature** | float | `0.5` | 采样温度，控制输出随机性 | **0.0** = 确定性输出（总是选最高概率 token），适合精确代码执行；**0.3-0.5** = 平衡稳定与变化，适合代码生成和分析判断；**0.7-1.0** = 高创造性，适合头脑风暴和假设生成。过高（>1.0）容易产生不连贯或格式错误的输出 |
| **max_tokens** | int | `None`（模型上限） | 单次回复最大生成 token 数 | 控制输出长度。代码生成任务建议不低于 4096，防止代码被截断；纯分析/反馈任务 2048 通常足够。设为 `None` 时使用模型默认上限 |
| **reasoning_effort** | string | `None` | 推理努力程度（仅推理模型支持） | 可选值：`low`/`medium`/`high`。仅 o1/o3、DeepSeek-R1 等推理模型支持，控制 Chain-of-Thought 的深度。普通聊天模型设置此参数会被忽略 |

#### 模型路由匹配机制

```python
# litellm.py 中的匹配逻辑（简化）
for tag, model_config in chat_model_map.items():
    if tag in logger._tag:  # 当前日志上下文包含该tag
        model = model_config["model"]
        temperature = float(model_config.get("temperature", 0.5))
        max_tokens = int(model_config["max_tokens"]) if "max_tokens" in model_config else None
        break
```

系统通过 logger tag 进行子串匹配。例如当日志 tag 为 `coding.factor_coder.evolving` 时，包含子串 `coding`，因此使用 `coding` 对应的模型配置。

#### 其他全局 LLM 参数（.env 中可配置）

除 `CHAT_MODEL_MAP` 外，[llm_conf.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/llm_conf.py) 还定义了以下全局参数：

| 参数 | 环境变量 | 默认值 | 含义 |
|------|---------|--------|------|
| `chat_temperature` | `LITELLM_CHAT_TEMPERATURE` | `0.5` | 默认温度（被 CHAT_MODEL_MAP 中的 temperature 覆盖） |
| `chat_max_tokens` | `LITELLM_CHAT_MAX_TOKENS` | `None` | 默认最大输出 token 数 |
| `chat_stream` | `LITELLM_CHAT_STREAM` | `True` | 是否流式输出（日志中实时显示） |
| `chat_seed` | `LITELLM_CHAT_SEED` | `None` | 随机种子（设为固定值可复现输出，调试时有用） |
| `max_retry` | `LITELLM_MAX_RETRY` | `10` | API 调用失败最大重试次数 |
| `retry_wait_seconds` | `LITELLM_RETRY_WAIT_SECONDS` | `1` | 重试等待秒数 |
| `enable_response_schema` | `LITELLM_ENABLE_RESPONSE_SCHEMA` | `True` | 是否启用 JSON Schema 约束输出（设为 False 可兼容不支持 structured output 的模型） |
| `reasoning_think_rm` | `LITELLM_REASONING_THINK_RM` | `False` | 是否移除推理模型输出中的 `<think>...</think>` 标签 |
| `use_chat_cache` | `LITELLM_USE_CHAT_CACHE` | `False` | 是否启用 LLM 调用缓存（相同 prompt 直接返回缓存结果，节省成本） |
| `chat_token_limit` | `LITELLM_CHAT_TOKEN_LIMIT` | `100000` | 输入 token 上限提示（超限时自动截断 RAG 检索结果） |
| `embedding_model` | `LITELLM_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding 模型（用于知识库向量检索） |

#### 常用模型参考速查

##### 豆包 Seed 系列（火山方舟，主要推荐）

豆包 Seed 系列通过火山方舟调用，模型名为 `openai/doubao-seed-*`（Base URL 指向 `https://ark.cn-beijing.volces.com/api/v3`），均原生支持深度思考、JSON 结构化输出、工具调用和 256K 上下文。

| 模型名（model 字段值） | 定位 | 核心能力 | 价格(输入/输出 元/百万token) | multiα1pha 推荐场景 |
|----------------------|------|---------|--------------------------|-------------------|
| `openai/doubao-seed-2-1-pro-260628` | **旗舰版**（最强） | Coding 工程交付顶尖（开发者评测对 Claude Opus 4.6 胜率 59%），Agent 长链路任务执行、多模态理解、SWE-Bench/Terminal-Bench 高分，完整 MoE 稠密激活+加长思维链自校验 | 6 / 30 | **coding 步骤首选**（替代 deepseek-v4），复杂代码进化和 Bug 修复 |
| `openai/doubao-seed-2-1-turbo-260628` | **高效版**（性价比） | Pro 版蒸馏优化，能力接近 Pro，INT4 量化+动态批推理，时延比 Pro 低 40%，支持与 Pro 完全相同的能力集 | 3 / 15 | **大规模运行推荐**，coding 步骤的高性价比选择，或 feedback/direct_exp_gen 日常使用 |
| `openai/doubao-seed-evolving` | **动态迭代版** | 周级频率自动更新版本，始终使用最新最强的 Seed 模型（当前等同 2.1 Pro），无需切换 Model ID | 6 / 30 | **持续迭代实验**，愿意尝鲜的开发/研究场景；不推荐生产环境（版本变化不可控） |
| `openai/doubao-seed-2-0-code-preview-260215` | **代码专用版**（上一代） | 编程场景深度优化，前端代码生成出众，多模态视觉理解（可从设计图生成代码），代码调试/重构能力精准 | 按方舟定价 | 纯代码任务的备选方案；综合能力已被 2.1 Pro 超越 |
| `openai/doubao-seed-code-preview-251028` | **代码预览版**（早期） | 专注编程场景优化，精准代码调试与重构，适合中小项目快速开发 | 按方舟定价 | 历史版本，不推荐新项目使用 |
| `openai/doubao-seed-2-0-pro-260215` | **2.0 旗舰**（上一代） | 复杂推理与长链路任务，代码架构设计与多模块协同 | 按方舟定价 | 2.0 时代旗舰，已被 2.1 Pro 替代 |
| `openai/doubao-seed-2-0-lite-260428` | **轻量版** | 能力约为 Pro 的 80%，成本更低速度更快，RPM/TPM 限额更高（30000 RPM / 5M TPM） | 按方舟定价 | 高并发简单任务、开发调试、批量预处理 |
| `openai/doubao-seed-2-0-mini-260428` | **迷你版** | 最轻量快速，适合高频简单调用 | 按方舟定价 | 最基础的文本处理任务，一般不用于 agent 核心环节 |

> **豆包深度思考参数**：Seed 系列默认开启深度思考模式，可通过 `reasoning_effort` 参数调节思考长度，支持 `minimal`/`low`/`medium`/`high` 四档（默认 `high`）。coding 场景建议设为 `high` 或 `medium`，feedback 场景可设为 `medium` 以节省 token。

##### 其他国产模型

| 模型名（model 字段值） | 提供商 | 特长 | 上下文窗口 | 适合场景 |
|----------------------|--------|------|-----------|---------|
| `openai/deepseek-v4` | DeepSeek | 代码生成顶尖，数学推理强，JSON 稳定 | 128K | coding 步骤备选 |
| `openai/deepseek-v4-flash` | DeepSeek | 速度快，成本低，能力略逊 | 128K | running/简单任务/高并发 |
| `openai/deepseek-v4-pro` | DeepSeek | Pro 版更强推理 | 1M | 超长代码库上下文场景 |
| `openai/minimax-m3` | MiniMax | 中文创意好，发散性强 | 128K | direct_exp_gen 备选 |
| `openai/glm-5.2` | 智谱 AI | 中文金融适配好，结构化输出稳定 | 128K | feedback 备选 |
| `openai/kimi-k2.5` | Moonshot | 超长上下文（200K+），代码不错 | 200K+ | RAG 检索结果极长时备选 |
| `openai/kimi-k2.7-code` | Moonshot | 代码专用版本 | 200K+ | 代码生成备选 |

##### 海外模型

| 模型名（model 字段值） | 提供商 | 特长 | 上下文窗口 | 适合场景 |
|----------------------|--------|------|-----------|---------|
| `openai/gpt-4o` | OpenAI | 综合能力最强，代码+推理+JSON 均优 | 128K | 预算充足时的 coding 备选 |
| `openai/gpt-4o-mini` | OpenAI | 速度快成本低，简单任务够用 | 128K | 开发调试/轻量任务 |

##### 多模型推荐配置（火山方舟生态）

如果所有模型均通过火山方舟调用（Base URL 统一），推荐配置：

```json
CHAT_MODEL_MAP={
  "direct_exp_gen": {"model": "openai/doubao-seed-2-1-turbo-260628", "temperature": "0.7", "reasoning_effort": "medium"},
  "coding": {"model": "openai/doubao-seed-2-1-pro-260628", "temperature": "0.5", "reasoning_effort": "high"},
  "running": {"model": "openai/doubao-seed-2-0-lite-260428", "temperature": "0.0"},
  "feedback": {"model": "openai/doubao-seed-2-1-turbo-260628", "temperature": "0.4", "reasoning_effort": "medium"}
}
```

---

## 四种运行场景

multiα1pha 支持四个入口场景，均复用相同的五个智能体：

### 场景一：因子挖掘（Factor）

- 入口：[factor.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py)
- 配置：`FactorBasePropSetting`
- 流程：假设生成 → 因子任务 → CoSTEER 编写因子代码 → 因子计算+IC验证+回测 → 反馈
- 环境变量前缀：`QLIB_FACTOR_`

### 场景二：研报复现（Factor from Report）

- 入口：[factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py)
- 配置：`FactorFromReportPropSetting`
- 流程：PDF提取因子 → CoSTEER 编写因子代码 → 因子计算+IC验证+回测 → 反馈
- 环境变量前缀：`QLIB_FACTOR_`（继承因子场景）

### 场景三：模型调优（Model）

- 入口：[model.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/model.py)
- 配置：`ModelBasePropSetting`
- 流程：假设生成 → 模型任务 → CoSTEER 编写模型代码 → 模型训练+预测+回测 → 反馈
- 环境变量前缀：`QLIB_MODEL_`

### 场景四：全流程研发（Quant）

- 入口：[quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py)
- 配置：`QuantBasePropSetting`
- 流程：每轮通过 Bandit/LLM/Random 选择做因子还是模型，两套智能体动态切换
- 环境变量前缀：`QLIB_QUANT_`

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

multiα1pha 的智能体设计基于以下学术研究：

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
- 想要了解实验历史如何记录、SOTA如何追踪？→ [06-trace.md](06-trace.md)
