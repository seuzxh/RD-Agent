{% raw %}
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

定义于 [proposal.py#L141-L341](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L341)，是假设生成的核心上下文：

| 属性 | 说明 |
|------|------|
| `hist: list[tuple[Experiment, ExperimentFeedback]]` | 按时间顺序排列的（实验，反馈）对列表；类型标注为 `ExperimentFeedback`，实际运行时存放的是其子类 `HypothesisFeedback` |
| `dag_parent: list[tuple[int,...]]` | DAG 父节点索引，支持分支探索 |
| `knowledge_base` | 关联的 RAG 知识库 |
| `current_selection` | 当前扩展点选择（默认 SOTA） |

关键方法：

- `get_sota_hypothesis_and_experiment()`：反向遍历 hist，返回最近一个 `decision=True` 的实验及其假设。
- `get_sota_experiment(node_id)`：沿祖先链向上查找 SOTA 节点。

### 3.3 ExperimentPlan（实验计划）

传递给 `gen()` 的可选参数，包含：

- `features`：基础因子集合（默认为 ALPHA20）
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

在 [RDLoop](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L199-L210) 中，假设生成发生在 `direct_exp_gen` 阶段：

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
   - `RAG`：策略引导文本（注意：此处的 RAG 变量并非向量检索，而是根据迭代轮次等状态注入的启发式策略提示，如"先尝试简单因子"或"现在尝试高IC的ML因子"。CoSTEER 编码阶段另有知识检索机制）
4. **调用 LLM**：`APIBackend().build_messages_and_create_chat_completion()`，强制 JSON 输出。
5. **解析响应**：调用子类 `convert_response(resp)` 将 JSON 转为 `Hypothesis` 对象。

### 5.3 首轮与后续轮次的差异

| 情况 | 行为 |
|------|------|
| 首轮（`len(trace.hist)==0`） | `hypothesis_and_feedback` 设为"No previous hypothesis..."，RAG 引导从简单因子开始 |
| 因子场景前15轮（`len(trace.hist)<15`） | RAG: "Try the easiest and fastest factors to experiment with from various perspectives first." |
| 因子场景第16轮起（`len(trace.hist)>=15`） | RAG: "Now, you need to try factors that can achieve high IC (e.g., machine learning-based factors)." |
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

**因子假设规范**（`factor_hypothesis_specification`）共5条规则（第5条含两个要点）：
1. 每次生成 1-5 个因子
2. 优先简单有效的因子
3. 逐步增加复杂度（ML因子、多维数据因子）
4. 连续失败时切换新方向
5. 超越SOTA的因子已入库，避免重复实现；不论生成几个因子，**只返回一组 hypothesis + reason**

**模型假设规范**（`model_hypothesis_specification`）共8条规则，重点包括：
- 聚焦 PyTorch 模型架构设计（层配置、激活函数、正则化）
- 不做特征相关处理（但可对输入时序数据做创新性变换）
- 训练超参调整也是有效改进策略
- 鼓励探索 NeurIPS/ICLR/ICML/SIGKDD 级别的创新时序模型结构
- 首轮从简单小架构开始，连续失败可回归简单架构
- 注意：数据规模约束（训练集约100万样本、验证集约25万）来自 RAG 文本，**不在** `model_hypothesis_specification` 规范中

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
#          IC   ICIR  RankIC RankICIR ARR   IR   -MDD Sharpe
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

PDF 加载器代码中存在 **KMeans + LLM 去重**管线（[pdf_loader.py#L397-L564](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L397-L564)），使用 Embedding + KMeans 聚类 + LLM 判断语义重复，但该功能当前在 [pdf_loader.py#L587](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L587) 被注释禁用，并非活跃功能。

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

> 代码见 [rd_loop.py#L154-L167](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L154-L167)。

---

## 10. 配置与模型绑定

### 10.1 LLM 模型配置

假设生成对应的日志标签为 `direct_exp_gen`，在 `.env` 中通过 `CHAT_MODEL_MAP` 绑定模型。以下为 `.env` 示例值，非代码默认：

```bash
CHAT_MODEL_MAP={
  "direct_exp_gen": {"model": "openai/minimax-m3", "temperature": "0.7"},
  ...
}
```

LiteLLM 后端在调用时检测日志标签栈 `logger._tag`，当包含 `direct_exp_gen` 时按 `CHAT_MODEL_MAP` 配置路由到对应模型。

> 路由实现见 [litellm.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py)。

### 10.2 关键配置项

| 配置 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `hypothesis_gen` | `*_PROP_SETTING` | 场景化类路径 | 假设生成类的完整导入路径 |
| `hypothesis2experiment` | `*_PROP_SETTING` | 场景化类路径 | 假设转实验类的完整导入路径 |
| `action_selection` | `QUANT_PROP_SETTING` | `"bandit"` | 全流程场景的动作选择策略 |
| `evolving_n` | 各 PROP_SETTING | `10`（各 PropSetting 中定义） | 最大迭代轮数 |
| `auto_mode` | `main()` 函数 kwargs | `false`(CLI) | 是否自动跳过人工审核 |

### 10.3 Hypothesis2Experiment（假设转实验）

假设生成后，由 [Hypothesis2Experiment](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L437-L445) 将抽象假设转化为具体的可执行任务：

- 因子场景：输出 JSON 包含每个因子的 `description`、`formulation`（LaTeX）、`variables`
- 模型场景：输出 JSON 包含 `description`、`formulation`、`architecture`、`variables`、`hyperparameters`、`training_hyperparameters`、`model_type`
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
              │  model: 由CHAT_MODEL_MAP配置路由 │
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
         │ -MDD/Sharpe (8维)   │
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
LLM分类(单次分类, vote_time=1) ──→ 非金工研报 → 跳过
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
LLM可行性筛选 check_factor_viability（分批，每批≤50因子）
    │
    ▼
[代码中存在但当前被注释禁用: Embedding + KMeans聚类 + LLM语义去重]
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

## 三种 `gen()` 实现详解

HypothesisGen 有三个具体子类，分别对应三种场景：`QlibFactorHypothesisGen`（纯因子场景）、`QlibModelHypothesisGen`（纯模型场景）、`QlibQuantHypothesisGen`（全流程场景）。三者都继承自 `LLMHypothesisGen`，复用统一的 `gen()` 流程（prepare_context → 组装提示词 → LLM 调用 → convert_response），仅在 `prepare_context()` 和 `convert_response()` 上有差异。

### 1. QlibFactorHypothesisGen — 因子假设生成

[factor_proposal.py#L15-L58](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L15-L58)

#### prepare_context 上下文组装

因子场景的 `prepare_context()` 组装以下 5 个键值：

| 键 | 内容 | 来源/逻辑 |
|----|------|----------|
| `hypothesis_and_feedback` | 完整历史的假设+反馈链 | 非首轮时用 `T("prompts:hypothesis_and_feedback")` 模板渲染整个 `trace.hist`；首轮返回提示文本 |
| `last_hypothesis_and_feedback` | 最近一轮的假设+反馈 | 非首轮时取 `trace.hist[-1]` 渲染；首轮返回提示文本 |
| `RAG` | 渐进式复杂度引导 | `hist < 15` 轮：先简单因子；`hist >= 15` 轮：探索 ML-based 高 IC 因子 |
| `hypothesis_output_format` | 因子 JSON 输出格式 | `T("prompts:factor_hypothesis_output_format")` — 仅要求 `hypothesis` + `reason` 两个字段 |
| `hypothesis_specification` | 因子生成规范 | `T("prompts:factor_hypothesis_specification")` — 包含"1-5个因子/轮"、"先简单后复杂"、"失败换方向"等规则 |

**targets 值**：`"factors"`（在基类 `FactorHypothesisGen.__init__` 中设置）

**关键特点**：因子场景的 `prepare_context` 未提供 SOTA 键，仅使用全量历史；模型场景则显式提取了 `sota_hypothesis_and_feedback`。

---

### 2. QlibModelHypothesisGen — 模型假设生成

[model_proposal.py#L14-L70](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L14-L70)

#### prepare_context 上下文组装

模型场景比因子场景多一个 `SOTA_hypothesis_and_feedback`：

| 键 | 内容 | 来源/逻辑 |
|----|------|----------|
| `hypothesis_and_feedback` | 完整历史链 | 同因子场景，渲染整个 `trace.hist` |
| `last_hypothesis_and_feedback` | 最近一轮 | 同因子场景，取 `trace.hist[-1]` |
| `SOTA_hypothesis_and_feedback` | **SOTA 轮的假设+反馈** | 反向遍历 `trace.hist`，找到第一个 `feedback.decision == True` 的实验并渲染；无 SOTA 时返回提示文本 |
| `RAG` | 模型场景硬约束 | 固定文本：①时序数据适合 GRU/LSTM，不生成 GNN；②训练集约100万样本/验证集约25万，控制模型大小；③可以只调超参不换架构 |
| `hypothesis_output_format` | 通用 JSON 输出格式 | `T("prompts:hypothesis_output_format")` — 同样是 `hypothesis` + `reason` |
| `hypothesis_specification` | 模型生成规范 | `T("prompts:model_hypothesis_specification")` — 8条规则（聚焦PyTorch架构、层数/激活函数/正则化、超参调整、创新对标顶会等） |

**targets 值**：`"model tuning"`

> ⚠️ **代码 bug：SOTA 键名大小写不匹配**：`prepare_context` 返回字典中使用大写 `SOTA_hypothesis_and_feedback`（[model_proposal.py#L53](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L53)），但基类 `gen()` 读取时用的是小写 `sota_hypothesis_and_feedback`（[components/proposal/__init__.py#L53-L55](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L53-L55)）。由于 `"sota_hypothesis_and_feedback" in context_dict` 判断为 `False`，基类会取默认值 `""`，导致 user prompt 中 `{% if sota_hypothesis_and_feedback != "" %}` 分支**永远不渲染**——即模型场景虽然计算了 SOTA 文本，但实际上并未发送给 LLM。同样的问题也存在于全流程场景（[quant_proposal.py#L157](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L157)）。这是代码缺陷，不是预期行为。

**关键特点**：
- 模型场景**意图**额外提供 SOTA 引用（但受上述大小写 bug 影响，当前实际未送达 LLM）
- RAG 引导是**硬约束**而非渐进式——模型训练成本高，不鼓励早期尝试复杂模型
- `last_hypothesis_and_feedback` 特别包含了 `training_log`（stdout），帮助 LLM 分析训练问题（过拟合/欠拟合/梯度消失等）

---

### 3. QlibQuantHypothesisGen — 全流程假设生成（含动作选择）

[quant_proposal.py#L46-L179](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L46-L179)

全流程场景最复杂，额外包含 **action 选择**（决定本轮做 factor 还是 model），并使用定制化的 `QuantTrace`（[quant_proposal.py#L16-L20](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L16-L20)，在标准 Trace 基础上增加了 Bandit 控制器）。

#### Action 选择的三种策略

由 `QUANT_PROP_SETTING.action_selection` 配置决定：

| 策略 | 实现逻辑 |
|------|---------|
| **Bandit**（默认推荐） | 使用 `LinearThompsonTwoArm`（[bandit.py#L55-L92](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py#L55-L92)）：①提取上轮实验的 8 维指标向量（IC/ICIR/RankIC/RankICIR/ARR/IR/-MDD/Sharpe）；②计算加权奖励（权重 0.1/0.1/0.05/0.05/0.25/0.15/0.1/0.2，年化收益权重最高0.25）；③线性 Thompson Sampling 更新后验，选择期望奖励更高的 arm；首轮默认 `factor` |
| **LLM** | 单独调用一次 LLM，使用 `action_gen.system`/`action_gen.user` 提示词（[prompts.yaml#L274-L300](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L274-L300)），输入历史反馈链，输出 JSON `{"action": "factor" | "model"}` |
| **Random** | `random.choice(["factor", "model"])`，纯随机，用于对照实验 |

#### prepare_context 上下文组装（选择action后）

选定 action 后，历史链**过滤**逻辑不同于纯因子/纯模型场景：

- **action = factor** 时：保留所有 factor 实验 + **最近一个 SOTA model 实验**（factor 优化需要知道当前模型的输入能力边界）
- **action = model** 时：保留所有 model 实验 + **最近一个 SOTA factor 实验**（model 优化需要知道可用的特征集）
- 渐进式复杂度：factor 前 6 轮先简单（不是15轮），6 轮后探索 ML-based 高 IC 因子；model 使用硬约束 RAG（训练集约 478k 样本/验证集约 128k，与纯模型场景的 <1M/250k 数值不同）
- 输出格式使用 `hypothesis_output_format_with_action`，额外要求 LLM 返回 `action` 字段

**targets 值**：`"feature engineering and model building"`

**关键特点**：
- `QlibQuantHypothesis` 比普通 `Hypothesis` 多一个 `action` 字段（`"factor"` 或 `"model"`），用于记录本轮选择
- Bandit 权重中**年化收益(0.25)和Sharpe(0.2)权重最高**，引导 Bandit 关注盈利能力而非纯 IC
- 历史链过滤确保 LLM 不会被另一个领域的失败案例误导（factor 决策不看 model 失败，反之亦然）

---

## 提示词组装机制

HypothesisGen 的提示词分两层：**通用框架提示词**（`rdagent/components/proposal/prompts.yaml`）和**场景定制提示词**（`rdagent/scenarios/qlib/prompts.yaml`）。模板引擎使用 Jinja2，通过 `T()` 工具类加载和渲染。

### 系统提示词组装

[LLMHypothesisGen.gen()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L29-L65) 中系统提示词通过 `T(".prompts:hypothesis_gen.system_prompt")` 加载，填充以下变量：

{% raw %}
```
{{ targets }}                → "factors" / "model tuning" / "feature engineering and model building"
{{ scenario }}               → 场景描述（过滤后），由 scen.get_scenario_all_desc() 生成
                               代码判断: if self.targets in ["factor", "model"]
                               - factor场景(targets="factors"): 不匹配，走else → filtered_tag="hypothesis_and_experiment"
                               - model场景(targets="model tuning"): 不匹配，走else → filtered_tag="hypothesis_and_experiment"
                               - quant场景(action选择后targets="factor"/"model"): 命中if → filtered_tag=self.targets
{{ user_instruction }}       → 用户全局指令（如有，来自ExperimentPlan）
{{ hypothesis_specification }}→ 场景定制规范（factor_hypothesis_specification 或 model_hypothesis_specification）
{{ hypothesis_output_format }}→ JSON输出格式要求
```
{% endraw %}

**系统提示词核心结构**（[prompts.yaml#L2-L20](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/prompts.yaml#L2-L20)）：

{% raw %}
```
1. 角色设定："你在为{targets}生成新假设"
2. 场景描述：{{scenario}}（Qlib数据接口、可用字段、baseline模型等）
3. 用户指令（可选）
4. 核心任务：分析历史实验→反思成功/失败原因→改进现有方向或探索新方向
5. 附加规范：{{hypothesis_specification}}（因子/模型场景特定规则）
6. 输出格式：{{hypothesis_output_format}}（JSON schema）
```
{% endraw %}

### 用户提示词组装

用户提示词通过 `T(".prompts:hypothesis_gen.user_prompt")` 加载，条件性地填充区块：

{% raw %}
```
首轮判断（Jinja if）:
  {% if hypothesis_and_feedback|length == 0 %}
    "It is the first round..."              → 首轮提示
  {% else %}
    "The former hypothesis and feedbacks:"
    {{ hypothesis_and_feedback }}          → 完整历史链渲染结果

最近一轮（仅factor/model/quant都传了此键时显示）:
  {% if last_hypothesis_and_feedback %}
    "Here is the last trial's..."
    {{ last_hypothesis_and_feedback }}     → 最近一轮的假设+任务+结果+反馈+新假设建议
    注意：提示词特别说明"The main feedback contains a new hypothesis for your reference only.
          You need to evaluate the complete trace chain to decide whether to adopt it..."
          （上轮反馈中的new_hypothesis仅作参考，需自主判断）

SOTA轮（仅model和quant场景传了此键时显示）:
  {% if sota_hypothesis_and_feedback != "" %}
    "Here is the SOTA trail's..."
    {{ sota_hypothesis_and_feedback }}     → SOTA实验详情

RAG引导:
  {% if RAG %}
    "To assist you..., we have provided: {{RAG}}"
```
{% endraw %}

### 历史反馈链渲染模板

`hypothesis_and_feedback` 使用 [qlib/prompts.yaml#L1-L21](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L1-L21) 的模板，遍历 `trace.hist` 对每个实验渲染：

```
=========================================================
# Trial N:
## Hypothesis
{experiment.hypothesis}
## Specific task:
- {factor_name}: {factor_description}    (每个子任务的简要信息)
## Backtest Analysis and Feedback:
Backtest Result: IC=xx, ARR(without_cost)=xx, MDD(without_cost)=xx
Observation: {feedback.observations}
Hypothesis Evaluation: {feedback.hypothesis_evaluation}
Decision (Whether the hypothesis was successful): {feedback.decision}
=========================================================
```

> ⚠️ **注意指标口径**：假设生成阶段的历史渲染使用的是**扣费前**（`without_cost`）的年化收益和最大回撤（[prompts.yaml#L15](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L15)），而反馈智能体（Summarizer）的 `IMPORTANT_METRICS` 使用的是**扣费后**（`with_cost`）指标。两者口径不同，阅读代码时需注意区分。

`last_hypothesis_and_feedback` 额外包含：
- **Training Log**（`experiment.stdout`）：模型训练日志，帮助分析训练问题
- 一段固定提示："Here, you need to focus on analyzing whether there are any issues with the training..."
- **New Hypothesis**（`feedback.new_hypothesis`）和 **Reasoning**（`feedback.reason`）：上轮反馈建议的新方向（仅参考）

`sota_hypothesis_and_feedback` 额外包含：
- **Training Log**（`experiment.stdout`）：SOTA 实验的训练日志
- 注意：SOTA 模板**不包含** `New Hypothesis`/`Reasoning` 字段（与 last 模板不同）

### factor_hypothesis_specification 规范要点

[prompts.yaml#L95-L112](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L95-L112)：

1. 每轮生成 1-5 个因子，平衡简单与复杂度
2. 先简单有效因子，避免一开始就用复杂/组合因子
3. 积累结果后逐步增加复杂度（ML-based、多维原始数据），简单因子验证后再组合
4. 连续失败则换方向，可回到简单因子
5. 超越SOTA的因子已入库，避免重复实现；不论生成几个因子，**只返回一组 hypothesis + reason**

### model_hypothesis_specification 规范要点

[prompts.yaml#L85-L93](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/prompts.yaml#L85-L93)：

1. 分析整体实验进展，找出设计不足之处（参数/架构/缺乏创新）
2. 重点关注 last 和 SOTA 两轮，可基于其一优化或提出新方向
3. 首轮从简单小架构开始
4. 连续失败则探索全新方向，可回归简单架构
5. **只聚焦 PyTorch 模型架构**（层配置、激活函数、正则化、模型结构），不做特征处理，但可对输入时序数据做创新性变换
6. 避免包含与架构无关的内容（如输入特征、优化策略）
7. 超参调整也是有效策略
8. 可用标准库基线，鼓励自定义架构，创新对标 NeurIPS/ICLR/ICML/SIGKDD

---

## Hypothesis 解析与响应处理

### convert_response 解析逻辑

三个场景的 `convert_response()` 结构类似（[factor_proposal.py#L48-L58](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L48-L58)、[model_proposal.py#L60-L70](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L60-L70)、[quant_proposal.py#L168-L179](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L168-L179)）：

```python
def convert_response(self, response: str) -> Hypothesis:
    response_dict = json.loads(response)          # 1. JSON解析
    hypothesis = QlibFactorHypothesis(            # 2. 构造Hypothesis对象
        hypothesis=response_dict.get("hypothesis"),
        reason=response_dict.get("reason"),
        concise_reason=response_dict.get("concise_reason"),
        concise_observation=response_dict.get("concise_observation"),
        concise_justification=response_dict.get("concise_justification"),
        concise_knowledge=response_dict.get("concise_knowledge"),
        # action=response_dict.get("action"),     # quant场景额外有此字段
    )
    return hypothesis
```

### Hypothesis 字段释义

| 字段 | 类型 | 来源 | 含义 |
|------|------|------|------|
| `hypothesis` | `str` | LLM JSON 输出的 `hypothesis` 字段 | 核心假设陈述（2-3句话，精确可测试） |
| `reason` | `str` | LLM JSON 输出的 `reason` 字段 | 提出该假设的理由（基于历史证据，2-3句） |
| `concise_reason` | `str \| None` | LLM JSON 输出的 `concise_reason` | 理由精简版（供后续提示词压缩上下文用） |
| `concise_observation` | `str \| None` | LLM JSON 输出的 `concise_observation` | 观察精简版 |
| `concise_justification` | `str \| None` | LLM JSON 输出的 `concise_justification` | 论证精简版 |
| `concise_knowledge` | `str \| None` | LLM JSON 输出的 `concise_knowledge` | 可复用知识精简版 |
| `action` | `str` | 仅 Quant 场景有，`"factor"` 或 `"model"` | 本轮选择的动作类型 |

**注意**：`concise_*` 字段虽然在 `convert_response` 中通过 `.get()` 提取，但当前 factor/model 场景的 `hypothesis_output_format` 提示词**并未要求 LLM 输出这些字段**（factor 只要求 hypothesis+reason，通用格式也只要求 hypothesis+reason）。这些字段是为未来版本预留的，用于在长循环中压缩历史上下文（用精简版替代完整版以节省 token）。Quant 场景的 `hypothesis_output_format_with_action` 多了 `action` 字段。

### LLM 调用参数

[proposal/__init__.py#L59-L61](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L59-L61)：

```python
resp = APIBackend().build_messages_and_create_chat_completion(
    user_prompt, system_prompt,
    json_mode=True,                          # 强制JSON输出
    json_target_type=dict[str, str]          # 声明目标类型为 {string: string}
)
```

- `json_mode=True`：启用 LiteLLM 的 `response_format={"type": "json_object"}`，确保 LLM 输出合法 JSON
- `json_target_type=dict[str, str]`：用于 Pydantic 校验返回格式

### 重试机制

`gen()` 方法**自身没有重试装饰器**，但 `Hypothesis2Experiment.convert()` 使用了 `@wait_retry(retry_n=5)`（[proposal/__init__.py#L93](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/proposal/__init__.py#L93)）。HypothesisGen 的 JSON 解析失败会直接抛异常；RDLoop 的 `feedback()` 方法中存在将异常包装为 `HypothesisFeedback(decision=False, reason=str(e))` 的兜底逻辑（见 [rd_loop.py#L224-L231](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L224-L231)），但该逻辑处理的是前序阶段（coding/running）存入 `EXCEPTION_KEY` 的异常，`direct_exp_gen` 阶段的异常不会被包装为 feedback，会直接向上传播。

### 输入输出示例

**输入（user_prompt 第3轮片段）**：
```
The former hypothesis and the corresponding feedbacks are as follows:
=========================================================
# Trial 1:
## Hypothesis
Generate simple momentum factors using close prices over different windows.
## Specific task:
MOM_5: [Momentum Factor] 5-day price momentum...
## Backtest Analysis and Feedback:
Backtest Result: IC=0.021, ARR=0.03, MDD=-0.12
Observation: Low IC, momentum effect weak in short window.
Decision: False
=========================================================
# Trial 2:
## Hypothesis
Explore turnover-rate-based factors that capture liquidity premium.
...
Decision: True     ← 第2轮成为SOTA
=========================================================

Here is the last trial's hypothesis and the corresponding feedback:
## Hypothesis
Explore turnover-rate-based factors...
Training Log: ...
Observation: Turnover factors show IC=0.06, significantly above baseline.
Decision: True
New Hypothesis: Consider volatility-adjusted turnover factors...

To assist you in generating new factors, we have provided the following information:
Try the easiest and fastest factors to experiment with from various perspectives first.
```

**输出（LLM JSON 响应）**：
```json
{
  "hypothesis": "Explore volatility-adjusted momentum factors that combine price momentum with realized volatility to capture risk-adjusted return patterns, as pure momentum showed weak predictive power while liquidity factors demonstrated significant IC.",
  "reason": "Momentum underperformed in short windows but the SOTA turnover factor confirms liquidity premium exists; volatility adjustment should separate true momentum from noisy price movements, building on the SOTA observation that risk-adjusted metrics outperform raw price-based factors."
}
```

**解析后的 Hypothesis 对象**：
```python
Hypothesis(
    hypothesis="Explore volatility-adjusted momentum factors...",
    reason="Momentum underperformed...",
    concise_reason=None,        # 当前提示词不要求输出
    concise_observation=None,
    concise_justification=None,
    concise_knowledge=None,
)
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
| 主循环调用 | [rdagent/components/workflow/rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L199-L210) |
| LiteLLM路由 | [rdagent/oai/backend/litellm.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py) |

{% endraw %}
