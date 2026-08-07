# 假设生成智能体（HypothesisGen）

> **定位**：multialpha R&D 循环的"大脑"与"研究员"。基于历史实验反馈、SOTA 结果和领域知识，生成可验证、可执行的科学假设，为后续的代码实现与实验验证提供方向。

---

## 目录

1. [论文来源与设计理念](#1-论文来源与设计理念)
2. [技术架构](#2-技术架构)
3. [核心数据结构](#3-核心数据结构)
4. [类继承体系](#4-类继承体系)
5. [执行流程](#5-执行流程)
6. [提示词工程](#6-提示词工程)
7. [三种场景化实现](#7-三种场景化实现)
8. [PDF 研报模式的特殊路径](#8-pdf-研报模式的特殊路径)
9. [人机交互机制](#9-人机交互机制)
10. [配置与模型绑定](#10-配置与模型绑定)
11. [输入输出示例](#11-输入输出示例)
12. [流程图](#12-流程图)

---

## 1. 论文来源与设计理念

假设生成智能体的设计遵循 **数据驱动研发自动化（Data-Driven R&D Automation）** 的研究范式，其核心思想来源于以下学术工作：

| 论文/框架 | arXiv/会议 | 核心贡献 |
|-----------|-----------|----------|
| **R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science** | [arXiv:2505.14738](https://arxiv.org/abs/2505.14738) | 整体技术报告，提出了"假设→实验→实现→反馈"的自主数据科学智能体框架 |
| **Towards Data-Centric Automatic R&D** | [arXiv:2404.11276](https://arxiv.org/abs/2404.11276) | 提出以数据为中心的自动研发范式，建立了持续提出假设、验证假设、从反馈中学习的基础方法框架 |
| **Collaborative Evolving Strategy for Automatic Data-Centric Development (CoSTEER)** | [arXiv:2407.18690](https://arxiv.org/abs/2407.18690) | 协同进化策略，将成功经验与失败错误统一纳入知识管理，引导智能体在迭代中持续提升 |
| **R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization** | [arXiv:2505.15155](https://arxiv.org/abs/2505.15155) · NeurIPS 2025 | 量化金融场景的多智能体框架，实现因子与模型的联合自动优化，包含 Bandit 动作选择机制 |

**设计理念**：

- **科学方法的形式化**：将真实量化研究员的"观察→假设→实验→反馈"循环抽象为 `Trace`（历史轨迹）驱动的假设生成过程。这一理念源自"Towards Data-Centric Automatic R&D"论文，是首个支持与真实验证环境联动的科研自动化框架。
- **反馈驱动**：新假设不是凭空产生，而是综合分析全部历史实验（成功与失败）后，提出改进方向或全新探索方向。
- **SOTA 意识**：始终将当前最优结果（State-of-the-Art）作为基准，明确新假设需要超越的目标。
- **渐进式复杂度**：因子场景中明确要求"先简单后复杂"（1-15轮尝试简单因子，15轮后探索ML-based因子）。
- **协同进化知识管理**：CoSTEER 框架不仅沉淀成功经验，还将错误和失败作为一等知识公民，用于指导后续假设生成。

---

## 2. 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                     RDLoop (主循环)                          │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │  _propose() │───▶│ _exp_gen()   │───▶│   coding()   │   │
│  └──────┬──────┘    └──────┬───────┘    └──────────────┘   │
│         │                  │                                │
│         ▼                  ▼                                │
│  ┌──────────────────────────────────┐                       │
│  │     HypothesisGen (抽象基类)      │                       │
│  │  + gen(trace, plan) → Hypothesis │                       │
│  └──────────────┬───────────────────┘                       │
│                 │                                           │
│     ┌───────────┼───────────┐                               │
│     ▼           ▼           ▼                                │
│  FactorHyp   ModelHyp   FactorAndModelHyp                   │
│  (因子)      (模型)      (量化全流程+Bandit)                 │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM 调用层                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  system_prompt: 场景描述 + 输出格式 + 假设规范         │    │
│  │  user_prompt:   历史Trace + 最近反馈 + SOTA + RAG    │    │
│  │  ───────────────────────────────────────────────     │    │
│  │  APIBackend().build_messages_and_create_chat_completion │
│  │  (json_mode=True, json_target_type=dict[str,str])    │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                    │
│                         ▼                                    │
│              JSON Response → Hypothesis 对象                 │
└─────────────────────────────────────────────────────────────┘
```

**核心组件**：

- **抽象基类** [HypothesisGen](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L414-L434)：定义 `gen(trace, plan)` 接口。
- **LLM 模板方法基类** [LLMHypothesisGen](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L18-L65)：实现通用的 LLM 调用流程，子类只需实现 `prepare_context()` 和 `convert_response()`。
- **场景子类**：在 Qlib 量化场景中提供因子、模型、全流程三种具体实现。

---

## 3. 核心数据结构

### 3.1 Hypothesis（假设）

定义于 [proposal.py#L24-L53](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L24-L53)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `hypothesis` | `str` | 精确、可测试、有创新性的假设陈述（2-3句话） |
| `reason` | `str` | 提出该假设的逻辑依据，基于历史证据和领域原理 |
| `concise_reason` | `str` | 精简版理由 |
| `concise_observation` | `str` | 精简版观察 |
| `concise_justification` | `str` | 精简版论证 |
| `concise_knowledge` | `str` | 可沉淀为知识的精简总结 |

量化全流程场景扩展了 `action` 字段（见 [quant_proposal.py#L23-L43](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L23-L43)）：

- `action: str`：取值为 `"factor"` 或 `"model"`，指示本轮假设的优化方向。

### 3.2 Trace（实验轨迹）

定义于 [proposal.py#L141-L318](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L318)，是假设生成的核心上下文：

| 属性 | 说明 |
|------|------|
| `hist: list[tuple[Experiment, ExperimentFeedback]]` | 按时间顺序排列的（实验，反馈）对列表 |
| `dag_parent: list[tuple[int,...]]` | DAG 父节点索引，支持分支探索 |
| `knowledge_base` | 关联的 RAG 知识库 |
| `current_selection` | 当前扩展点选择（默认 SOTA） |

关键方法：

- `get_sota_hypothesis_and_experiment()`：反向遍历 hist，返回最近一个 `decision=True` 的实验及其假设。
- `get_sota_experiment(node_id)`：沿祖先链向上查找 SOTA 节点。

### 3.3 ExperimentPlan（实验计划）

传递给 `gen()` 的可选参数，包含：

- `features`：基础因子集合（默认为 ALPHA20，也支持 ALPHA158）
- `feature_codes`：基础因子代码文件
- `user_instruction`：用户自然语言指令

---

## 4. 类继承体系

```
ABC (Python)
 └── HypothesisGen                          # core/proposal.py
      ├── abstract gen(trace, plan)
      │
      └── LLMHypothesisGen                  # components/proposal/__init__.py
           ├── prepare_context()  (abstract)
           ├── convert_response() (abstract)
           └── gen()  —— 模板方法，实现完整 LLM 调用流程
                │
                ├── FactorHypothesisGen            (targets="factors")
                │    └── QlibFactorHypothesisGen   # scenarios/qlib/proposal/factor_proposal.py
                │
                ├── ModelHypothesisGen             (targets="model tuning")
                │    └── QlibModelHypothesisGen    # scenarios/qlib/proposal/model_proposal.py
                │
                └── FactorAndModelHypothesisGen    (targets="feature engineering and model building")
                     └── QlibQuantHypothesisGen    # scenarios/qlib/proposal/quant_proposal.py
                          └── (含 Bandit/LLM/random action 选择)
```

**模板方法模式**：`LLMHypothesisGen.gen()` 固化了"准备上下文→渲染提示词→调用 LLM→解析响应"的流程，场景子类只需关注两个钩子方法：

- `prepare_context(trace)`：从 Trace 中提取并组装提示词变量。
- `convert_response(response)`：将 LLM 返回的 JSON 字符串解析为 `Hypothesis` 对象。

> 代码见 [LLMHypothesisGen.gen](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L29-L65)。

---

## 5. 执行流程

### 5.1 主循环中的调用

在 [RDLoop](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L183-L209) 中，假设生成发生在 `direct_exp_gen` 阶段：

```python
async def direct_exp_gen(self, prev_out):
    while True:
        if self.get_unfinished_loop_cnt(self.loop_idx) < RD_AGENT_SETTINGS.get_max_parallel():
            hypo = self._propose()           # ① 生成假设
            exp = self._exp_gen(hypo)        # ② 将假设转化为具体实验任务
            exp.base_features = self.plan["features"]
            ...
            return {"propose": hypo, "exp_gen": exp}
        await asyncio.sleep(1)
```

`_propose()` 内部还会触发**人机交互钩子** `_interact_hypo()`，允许用户在非自动模式下审核和修改假设。

### 5.2 LLMHypothesisGen.gen() 的完整流程

1. **准备上下文**：调用子类 `prepare_context(trace)` 获取上下文字典和 JSON 模式标志。
2. **渲染系统提示词**：使用 Jinja2 模板 `hypothesis_gen.system_prompt`，注入：
   - `targets`：优化目标（factors / model tuning / feature engineering and model building）
   - `scenario`：场景描述（通过 `scen.get_scenario_all_desc()` 获取）
   - `hypothesis_output_format`：输出 JSON schema
   - `hypothesis_specification`：领域特定的假设生成规范
   - `user_instruction`：用户指令（如有）
3. **渲染用户提示词**：使用 `hypothesis_gen.user_prompt`，注入：
   - `hypothesis_and_feedback`：全部历史实验及反馈（渲染为文本）
   - `last_hypothesis_and_feedback`：最近一轮的详细信息（含训练日志 stdout）
   - `sota_hypothesis_and_feedback`：SOTA 实验的详细信息
   - `RAG`：策略引导文本（注意：此处的 RAG 变量并非向量检索，而是根据迭代轮次等状态注入的启发式策略提示，如"先尝试简单因子"或"现在尝试高IC的ML因子"。真正的向量知识库检索发生在 CoSTEER 编码阶段）
4. **调用 LLM**：`APIBackend().build_messages_and_create_chat_completion()`，强制 JSON 输出。
5. **解析响应**：调用子类 `convert_response(resp)` 将 JSON 转为 `Hypothesis` 对象。

### 5.3 首轮与后续轮次的差异

| 情况 | 行为 |
|------|------|
| 首轮（`len(trace.hist)==0`） | `hypothesis_and_feedback` 设为"No previous hypothesis..."，RAG 引导从简单因子开始 |
| 因子场景 < 15 轮 | RAG: "Try the easiest and fastest factors from various perspectives first." |
| 因子场景 ≥ 15 轮 | RAG: "Now try factors that can achieve high IC (e.g., ML-based factors)." |
| 存在 SOTA | 反向遍历 hist 找到最近 `decision=True` 的节点，渲染其完整信息 |
| 全部失败 | SOTA 字段提示"No SOTA available since previous experiments were not accepted" |

---

## 6. 提示词工程

提示词模板使用 Jinja2，定义在以下两个 YAML 文件中：

### 6.1 通用模板

[components/proposal/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml)

**system_prompt 关键指令**：
> "analyze previous experiments, reflect on the decision made in each experiment, and consider why experiments with a decision of true were successful while those with a decision of false failed. Then, think about how to improve further — either by refining the existing approach or by exploring an entirely new direction."

**user_prompt 三段式结构**：
1. 全部历史假设与反馈摘要
2. 最近一轮的详细信息（含训练日志、新假设建议）
3. SOTA 轮次的详细信息
4. RAG 引导信息

### 6.2 Qlib 场景模板

[scenarios/qlib/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml)

**因子假设输出格式**（`factor_hypothesis_output_format`）：
```json
{
  "hypothesis": "新假设，2-3句话",
  "reason": "提出该假设的综合逻辑理由"
}
```

**因子假设规范**（`factor_hypothesis_specification`）共5条规则：
1. 每次生成 1-5 个因子
2. 优先简单有效的因子
3. 逐步增加复杂度（ML因子、多维数据因子）
4. 连续失败时切换新方向
5. 避免重复实现已超越 SOTA 的因子

**模型假设规范**（`model_hypothesis_specification`）共8条规则，重点包括：
- 聚焦 PyTorch 模型架构设计（层配置、激活函数、正则化）
- 不做特征相关处理
- 训练超参调整也是有效改进策略
- 鼓励探索 NeurIPS/ICML 级别的创新时序模型结构
- 训练集约100万样本、验证集约25万，据此控制模型规模

---

## 7. 三种场景化实现

### 7.1 QlibFactorHypothesisGen（因子挖掘）

文件：[factor_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L15-L58)

- `targets = "factors"`
- 上下文包含：全部历史、最近一轮、RAG 渐进策略
- **注意**：因子场景目前未单独提取 SOTA 字段（仅使用全量历史），模型场景则显式提取了 SOTA。

### 7.2 QlibModelHypothesisGen（模型实现/调优）

文件：[model_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L14-L70)

- `targets = "model tuning"`
- 额外提取 `sota_hypothesis_and_feedback`：反向遍历找到第一个 `decision=True` 的实验
- RAG 包含明确的模型规模指导（训练集<100万样本，验证集~25万）
- 提示模型超参调整也是有效策略，可返回相同模型但调整参数

### 7.3 QlibQuantHypothesisGen（量化全流程）

文件：[quant_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L46-L179)

最复杂的实现，增加了 **action 选择机制**：

#### Action 选择策略

由配置项 `QUANT_PROP_SETTING.action_selection` 控制：

| 策略 | 实现 | 说明 |
|------|------|------|
| `bandit`（默认） | [LinearThompsonTwoArm](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py#L55-L92) | 线性 Thompson Sampling 双臂赌博机，基于8维指标向量（IC/ICIR/Rank IC/Rank ICIR/ARR/IR/-MDD/Sharpe）决策 |
| `llm` | LLM 调用 `action_gen` 提示词 | 让 LLM 分析历史后决定优化因子还是模型 |
| `random` | `random.choice(["factor","model"])` | 随机选择（用于消融实验） |

**Bandit 奖励函数权重**（[bandit.py#L97](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py#L97)）：

```python
weights = (0.1, 0.1, 0.05, 0.05, 0.25, 0.15, 0.1, 0.2)
#          IC   ICIR  RankIC RankICIR ARR   IR   MDD  Sharpe
```

#### Trace 过滤

全流程场景中，假设生成时会根据 action 过滤历史轨迹：
- 当 `action="factor"`：包含全部因子实验 + 最近一个 SOTA 模型实验
- 当 `action="model"`：包含全部模型实验 + 最近一个 SOTA 因子实验

这种设计确保 LLM 看到的是与当前决策相关的历史上下文，避免信息干扰。

---

## 8. PDF 研报模式的特殊路径

PDF 研报复现场景（[factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py)）**不走** `HypothesisGen.gen()` 的 LLM 假设生成路径，而是采用确定性提取流程：

```
PDF文件
  │
  ▼
load_and_process_pdfs_by_langchain()    # LangChain解析PDF文本
  │
  ▼
classify_report_from_dict()             # LLM分类：是否为金工研报
  │
  ▼
extract_factors_from_report_dict()      # 多进程提取因子（名称+描述）
  │
  ▼
__extract_factors_formulation_from_content()  # 提取LaTeX公式和变量
  │
  ▼
check_factor_viability()                # LLM判断因子可行性
  │
  ▼
FactorExperimentLoaderFromDict().load() # 转为FactorExperiment
  │
  ▼
generate_hypothesis()                   # 基于因子结果+报告内容生成Hypothesis
```

`generate_hypothesis()` 函数（[factor_from_report.py#L26-L58](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py#L26-L58)）使用独立的提示词模板，将提取到的因子字典和报告原文拼接后调用 LLM 生成假设。

PDF 加载器还包含**KMeans + LLM 去重**管线（[pdf_loader.py#L397-L564](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L397-L564)）：使用 Embedding + KMeans 聚类 + LLM 判断语义重复，对研报中的因子进行去重。

---

## 9. 人机交互机制

在非自动模式（`auto_mode=False`）下，RDLoop 在假设生成后、实验生成前插入人工审核环节：

```python
def _interact_hypo(self, hypo: Hypothesis) -> Hypothesis:
    if not (hasattr(self, "user_request_q") and hasattr(self, "user_response_q")):
        return hypo
    self.user_request_q.put(hypo.__dict__)   # 发送给前端
    res_dict = self.user_response_q.get()     # 等待用户修改
    modified_hypo = type(hypo)(**res_dict)
    return modified_hypo
```

前端通过 `UserInteractionDialog.vue` 展示假设内容，用户可以：
- 直接批准（无修改）
- 编辑假设文本和理由
- 拒绝并要求重新生成

> 代码见 [rd_loop.py#L153-L166](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L153-L166)。

---

## 10. 配置与模型绑定

### 10.1 LLM 模型配置

假设生成对应的日志标签为 `direct_exp_gen`，在 `.env` 中通过 `CHAT_MODEL_MAP` 绑定模型：

```bash
CHAT_MODEL_MAP={
  "direct_exp_gen": {"model": "openai/minimax-m3", "temperature": "0.7"},
  ...
}
```

LiteLLM 后端在调用时检测日志标签栈 `logger._tag`，当包含 `direct_exp_gen` 时自动路由到 MiniMax-M3 模型。

> 路由实现见 [litellm.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py)。

### 10.2 关键配置项

| 配置 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `hypothesis_gen` | `*_PROP_SETTING` | 场景化类路径 | 假设生成类的完整导入路径 |
| `hypothesis2experiment` | `*_PROP_SETTING` | 场景化类路径 | 假设转实验类的完整导入路径 |
| `action_selection` | `QUANT_PROP_SETTING` | `"bandit"` | 全流程场景的动作选择策略 |
| `evolving_n` | 各 PROP_SETTING | `10` | 最大迭代轮数 |
| `auto_mode` | RDLoop | `false`(CLI) | 是否自动跳过人工审核 |

### 10.3 Hypothesis2Experiment（假设转实验）

假设生成后，由 [Hypothesis2Experiment](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L437-L445) 将抽象假设转化为具体的可执行任务：

- 因子场景：输出 JSON 包含每个因子的 `description`、`formulation`（LaTeX）、`variables`
- 模型场景：输出 JSON 包含 `architecture`、`hyperparameters`、`training_hyperparameters`、`model_type`
- 全流程场景：输出还包含 `action` 字段

该组件使用 `@wait_retry(retry_n=5)` 装饰器，在 JSON 解析失败时自动重试最多5次。

---

## 11. 输入输出示例

### 11.1 输入（Trace 上下文中的历史信息）

```
Trial 3:
Hypothesis: 基于成交量加权的动量因子在中小盘股上具有更强的预测能力...
Specific task:
- Factor: VOL_WEIGHTED_MOM_20
  Formulation: (close/Ref(close,20)-1) * volume/MA(volume,20)
Backtest Result:
  IC: 0.045
  annualized_return: 0.182
  max_drawdown: -0.085
Observation: 因子在中证500成分股上IC达到0.052，显著高于沪深300...
Hypothesis Evaluation: 假设成立，成交量加权确实提升了动量信号...
Decision: True
```

### 11.2 输出（Hypothesis 对象）

```json
{
  "hypothesis": "引入换手率调整的成交量加权动量因子（TURN_ADJ_VW_MOM），通过除以换手率均值来降低高换手股票的噪声权重，预期在中证500上IC可从0.045提升至0.055以上。",
  "reason": "前序实验证实成交量加权动量在中小盘有效，但高换手股票的成交量信号噪声较大。换手率调整可过滤投机性成交量，提升信号质量。",
  "concise_reason": "换手率过滤可降低成交量噪声",
  "concise_observation": "VW动量在中小盘IC=0.045",
  "concise_justification": "高换手股成交量含投机噪声",
  "concise_knowledge": "成交量加权动量在中小盘有效，换手率调整可进一步降噪"
}
```

量化全流程场景的输出还包含：
```json
{
  "action": "factor",
  "hypothesis": "...",
  "reason": "..."
}
```

---

## 12. 流程图

### 12.1 假设生成整体流程

```
                    ┌──────────────────┐
                    │   RDLoop 启动     │
                    │  direct_exp_gen  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  _propose()      │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │  prepare_context(trace)     │
              │                             │
              │  ┌─ trace.hist 是否为空?    │
              │  │  ├─ 是 → "首轮"提示      │
              │  │  └─ 否 → 渲染全部历史    │
              │  │                          │
              │  ├─ 提取 last_trial         │
              │  ├─ 提取 SOTA_trial         │
              │  ├─ 组装 RAG 引导文本       │
              │  └─ (全流程) Bandit选action │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  渲染 Jinja2 提示词模板       │
              │  system_prompt + user_prompt │
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  APIBackend LLM 调用         │
              │  model: minimax-m3           │
              │  temperature: 0.7            │
              │  json_mode: True             │
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  convert_response(json_str)  │
              │  → Hypothesis 对象           │
              └──────────────┬───────────────┘
                             │
                    ┌────────┴─────────┐
                    │ auto_mode?       │
                    ├─ Yes → 直接返回   │
                    └─ No → _interact_hypo()
                              │
                              ▼
                    ┌──────────────────┐
                    │ 用户审核/编辑    │
                    │ (IPC Queue)      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ 返回 Hypothesis  │
                    │ → _exp_gen()     │
                    └──────────────────┘
```

### 12.2 全流程场景的 Bandit Action 选择

```
              上一轮实验结果(Metrics)
                    │
                    ▼
         ┌─────────────────────┐
         │ extract_metrics()   │
         │ IC/ICIR/RankIC/     │
         │ RankICIR/ARR/IR/    │
         │ MDD/Sharpe (8维)    │
         └─────────┬───────────┘
                   │
                   ▼
         ┌─────────────────────┐
         │ controller.record() │
         │ 更新后验分布        │
         └─────────┬───────────┘
                   │
                   ▼
         ┌─────────────────────┐
         │ controller.decide() │
         │ Thompson Sampling   │
         │ 从 factor/model 后验│
         │ 采样奖励, 选最大者  │
         └─────────┬───────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
     action=factor     action=model
          │                 │
          ▼                 ▼
   因子假设规范       模型假设规范
   因子RAG引导        模型RAG引导
   过滤Trace:         过滤Trace:
   全部因子实验       全部模型实验
   +最新SOTA模型      +最新SOTA因子
```

### 12.3 PDF 研报模式流程

```
PDF文件夹
    │
    ▼
LangChain PDF解析
    │
    ▼
LLM分类(投票) ──→ 非金工研报 → 跳过
    │
    ▼ (是金工研报)
多进程因子提取:
  ├─ LLM提取因子名称+描述（最多10轮追问）
  └─ LLM提取LaTeX公式+变量（最多10轮补全）
    │
    ▼
多报告合并去重
    │
    ▼
Embedding + KMeans聚类
    │
    ▼
LLM语义去重（分批，每批≤50因子）
    │
    ▼
LLM可行性筛选
    │
    ▼
generate_hypothesis()
  (因子结果 + 报告原文 → LLM假设)
    │
    ▼
FactorExperiment (含Hypothesis)
    │
    ▼
进入CoSTEER编码阶段
```

---

## 相关代码索引

| 模块 | 文件路径 |
|------|----------|
| 抽象基类 | [rdagent/core/proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py) |
| LLM模板基类 | [rdagent/components/proposal/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py) |
| 通用提示词 | [rdagent/components/proposal/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml) |
| 因子假设生成 | [rdagent/scenarios/qlib/proposal/factor_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py) |
| 模型假设生成 | [rdagent/scenarios/qlib/proposal/model_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py) |
| 全流程假设生成 | [rdagent/scenarios/qlib/proposal/quant_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py) |
| Bandit实现 | [rdagent/scenarios/qlib/proposal/bandit.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py) |
| Qlib场景提示词 | [rdagent/scenarios/qlib/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml) |
| PDF研报加载器 | [rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py) |
| PDF研报循环 | [rdagent/app/qlib_rd_loop/factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py) |
| 主循环调用 | [rdagent/components/workflow/rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L183-L209) |
| LiteLLM路由 | [rdagent/oai/backend/litellm.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py) |
