# CoSTEER 编码进化智能体（CoSTEER Developer）

> **定位**：multialpha R&D 循环的"工程师"与"调试专家"。将假设生成阶段输出的抽象任务（因子描述/模型架构）转化为可运行的 Python 代码，通过"生成→执行→评估→纠错"的多轮进化循环，自动修正代码错误，沉淀成功经验与失败教训到图知识库，实现越用越强的代码生成能力。

---

## 目录

1. [论文来源与设计理念](#1-论文来源与设计理念)
2. [技术架构](#2-技术架构)
3. [核心数据结构](#3-核心数据结构)
4. [类继承体系](#4-类继承体系)
5. [进化主循环（RAGEvoAgent）](#5-进化主循环rageevoagent)
6. [多进程进化策略](#6-多进程进化策略)
7. [图知识库与 RAG 检索](#7-图知识库与-rag-检索)
8. [反馈评估体系](#8-反馈评估体系)
9. [提示词工程](#9-提示词工程)
10. [两种场景化实现](#10-两种场景化实现)
11. [配置与模型绑定](#11-配置与模型绑定)
12. [输入输出示例](#12-输入输出示例)
13. [流程图](#13-流程图)

---

## 1. 论文来源与设计理念

CoSTEER（**Co**llaborative **S**tra**te**gy for **E**volving and **R**etrieval）的设计直接来源于以下学术工作：

| 论文/框架 | arXiv/会议 | 核心贡献 |
|-----------|-----------|----------|
| **Collaborative Evolving Strategy for Automatic Data-Centric Development (CoSTEER)** | [arXiv:2407.18690](https://arxiv.org/abs/2407.18690) | 提出协同进化策略，将成功经验与失败错误统一纳入知识管理；通过 RAG 检索相似成功实现和相似错误修复方案，引导 LLM 在迭代中持续提升代码质量 |
| **Towards Data-Centric Automatic R&D** | [arXiv:2404.11276](https://arxiv.org/abs/2404.11276) | 建立以数据为中心的自动研发范式，为 CoSTEER 的"实现→执行→反馈→修正"闭环提供了基础方法框架 |
| **R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science** | [arXiv:2505.14738](https://arxiv.org/abs/2505.14738) | 整体技术报告，将 CoSTEER 定位为 R&D 循环中的 Developer 角色 |
| **R&D-Agent-Quant** | [arXiv:2505.15155](https://arxiv.org/abs/2505.15155) · NeurIPS 2025 | 量化金融场景中因子编码与模型编码的具体应用验证 |

**设计理念**：

- **代码即进化主体**：代码不是一次性生成，而是通过多轮"生成→执行→评估→纠错"逐步进化到正确状态。每一轮的失败反馈都被显式记录和利用。
- **失败是一等知识公民**：传统 RAG 只检索成功案例，CoSTEER 同时将错误类型、错误代码、修复方案存入知识图谱。当新任务遇到相似错误时，可直接检索到"曾犯相同错误→最终修复成功"的代码对，大幅提升纠错效率。
- **组件级语义检索**：V2 知识库将任务拆解为组件（component），通过图结构建立"组件→任务描述→执行轨迹→成功实现"的关联路径，检索精度高于纯向量相似度。
- **多进程并行实现**：一个实验可能包含多个子任务（如多个因子、模型的多个组件），各子任务的代码生成与评估可并行执行，显著缩短迭代时间。
- **知识自我增殖**：每轮进化结束后，成功的实现自动写入知识库，失败的错误模式也被分析和存储。知识库随使用持续增长。

---

## 2. 技术架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                        RDLoop.coding()                               │
│                        coder.develop(exp)                            │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     CoSTEER.develop(exp)                             │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  1. EvolvingItem.from_experiment(exp)                       │    │
│  │     将 Experiment 转换为可进化对象（含 sub_tasks）            │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  2. RAGEvoAgent.multistep_evolve(evo, evaluator)            │    │
│  │     （max_loop 轮进化循环）                                   │    │
│  │                                                             │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  每轮:                                               │   │    │
│  │  │  ① rag.query(evo, trace) → QueriedKnowledge         │   │    │
│  │  │  ② evolving_strategy.evolve_iter()                  │   │    │
│  │  │     ├─ 多进程并行实现各子任务                         │   │    │
│  │  │     └─ yield 部分进化结果                            │   │    │
│  │  │  ③ evaluator.evaluate_iter()                        │   │    │
│  │  │     ├─ 执行代码                                      │   │    │
│  │  │     ├─ 值/形状校验                                   │   │    │
│  │  │     ├─ LLM 代码评审                                  │   │    │
│  │  │     └─ 最终决策（True/False）                        │   │    │
│  │  │  ④ EvoStep 打包并追加到 evolving_trace               │   │    │
│  │  │  ⑤ rag.generate_knowledge(trace)                    │   │    │
│  │  │     ├─ 成功 → 更新图知识库（节点+边）                 │   │    │
│  │  │     └─ 失败 → 分析错误模式并存储                     │   │    │
│  │  │  ⑥ feedback.finished()? → break                     │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  3. Fallback 选择最后一个 acceptable 的进化结果              │    │
│  │     （即使后续轮次失败，也能回退到最近一次正确版本）          │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐    │
│  │  4. 后处理：若全部子任务失败则抛 CoderError                  │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
                    返回含 sub_workspace_list 的 Experiment
```

**核心组件**：

- **入口类** [CoSTEER](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/__init__.py#L20-L178)：继承 `Developer`，实现 `develop(exp)` 接口，协调 RAG、进化策略、评估器三者。
- **进化引擎** [RAGEvoAgent](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L78-L198)：实现多轮进化循环，是 CoSTEER 的核心调度器。
- **进化策略** [MultiProcessEvolvingStrategy](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolving_strategy.py#L22-L172)：抽象基类，子类实现具体的 LLM 代码生成逻辑；基类负责任务调度和多进程并行。
- **RAG 策略** [CoSTEERRAGStrategyV2](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L354-L849)：图知识库的查询与知识生成。
- **评估器** [CoSTEERMultiEvaluator](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py#L253-L333)：多任务并行评估，支持评估链。

---

## 3. 核心数据结构

### 3.1 EvolvingItem（可进化项）

定义于 [evolvable_subjects.py#L6-L32](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolvable_subjects.py#L6-L32)，同时继承 `Experiment` 和 `EvolvableSubjects`：

| 属性 | 类型 | 说明 |
|------|------|------|
| `sub_tasks` | `list[Task]` | 待实现的子任务列表（如多个因子、一个模型） |
| `sub_workspace_list` | `list[FBWorkspace]` | 每个子任务对应的工作区（含生成的代码文件） |
| `sub_gt_implementations` | `list[FBWorkspace]` | Ground truth 实现（如有，用于值比对评估） |
| `based_experiments` | — | 所基于的历史实验（提供上下文） |

通过 `from_experiment(exp)` 类方法从 Experiment 转换而来。

### 3.2 CoSTEERSingleFeedback（单子任务反馈）

定义于 [evaluators.py#L32-L123](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py#L32-L123)，采用分层反馈结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `execution` | `str` | 代码执行反馈（stdout/stderr 的摘要） |
| `return_checking` | `str \| None` | 返回值校验反馈（因子值与 GT 的比对结果、形状检查） |
| `code` | `str` | LLM 代码评审意见 |
| `final_decision` | `bool \| None` | 最终是否通过（True=实现正确） |
| `raw_execution` | `str` | 完整原始 stdout（供 UI 展示） |
| `source_feedback` | `dict[str, bool]` | 反馈来源标签→决策的映射（支持多评估器合并） |

反馈层次遵循 **Execution → Return Value → Code → Final Decision** 的流水线：先执行代码，再检查返回值，再评审代码质量，最后综合决策。

### 3.3 CoSTEERMultiFeedback（多任务反馈）

定义于 [evaluators.py#L199-L228](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py#L199-L228)，是 `CoSTEERSingleFeedback` 的列表容器。

关键方法：
- `is_acceptable()`：所有子任务反馈都 acceptable（非 None 且通过）时返回 True。
- `finished()`：所有非 None 的子任务反馈 final_decision 都为 True 时返回 True。允许部分任务被跳过（None），只要正确部分被接受。

### 3.4 EvoStep（进化步骤）

定义于 [evolving_framework.py#L43-L58](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py#L43-L58)，记录每轮进化的快照：

```python
@dataclass
class EvoStep:
    evolvable_subjects: EvolvableSubjects  # 本轮进化后的代码
    queried_knowledge: QueriedKnowledge | None  # 本轮检索到的知识
    feedback: Feedback | None  # 本轮的评估反馈
```

`evolving_trace: list[EvoStep]` 构成完整的进化历史。

### 3.5 CoSTEERKnowledge（知识条目）

定义于 [knowledge_management.py#L36-L52](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L36-L52)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_task` | `Task` | 任务描述 |
| `implementation` | `FBWorkspace` | 代码实现（工作区副本） |
| `feedback` | `Feedback` | 对应的反馈 |

方法 `get_implementation_and_feedback_str()` 将代码和反馈拼接为文本，用于图节点内容存储和提示词渲染。

### 3.6 CoSTEERQueriedKnowledgeV2（检索结果）

定义于 [knowledge_management.py#L281-L351](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L281-L351)，包含四类检索结果：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success_task_to_knowledge_dict` | `dict[str, CoSTEERKnowledge]` | 已成功完成的任务→直接复用其实现 |
| `failed_task_info_set` | `set[str]` | 失败次数超限的任务（跳过，不再尝试） |
| `task_to_former_failed_traces` | `dict[str, tuple[list, Knowledge\|None]]` | 本任务近期失败轨迹（含代码+反馈） |
| `task_to_similar_task_successful_knowledge` | `dict[str, list[CoSTEERKnowledge]]` | 相似组件任务的成功实现 |
| `task_to_similar_error_successful_knowledge` | `dict[str, list[tuple[str, tuple[Knowledge, Knowledge]]]]` | 曾犯相似错误但最终修复的（错误代码，成功代码）对 |

---

## 4. 类继承体系

```
Developer (ABC)                         # core/developer.py
 └── CoSTEER                            # components/coder/CoSTEER/__init__.py
      ├── __init__(settings, eva, es, ...)
      ├── develop(exp) → Experiment     # 模板方法：编排进化全流程
      ├── should_use_new_evo()          # 选择可接受的进化结果
      └── _exp_postprocess_by_feedback()

EvoAgent (ABC, Generic)                 # core/evolving_agent.py
 └── RAGEvoAgent                        # core/evolving_agent.py
      ├── multistep_evolve(evo, eva)    # ★ 多轮进化主循环
      └── _get_overall_feedback()

EvolvingStrategy (ABC, Generic)         # core/evolving_framework.py
 └── MultiProcessEvolvingStrategy       # components/coder/CoSTEER/evolving_strategy.py
      ├── implement_one_task() (abstract)  # 子类实现：LLM生成代码
      ├── implement_func_list()            # 可拆分为多步实现
      ├── assign_code_list_to_evo() (abstract)
      └── evolve_iter()                    # ★ 多进程任务调度
           ├── FactorMultiProcessEvolvingStrategy   # factor_coder/
           └── ModelMultiProcessEvolvingStrategy    # model_coder/

RAGStrategy (ABC, Generic)              # core/evolving_framework.py
 └── CoSTEERRAGStrategy                 # components/coder/CoSTEER/knowledge_management.py
      ├── load_or_init_knowledge_base()
      ├── dump_knowledge_base()
      ├── load_dumped_knowledge_base()
      ├── CoSTEERRAGStrategyV1 (deprecated)
      └── CoSTEERRAGStrategyV2          # ★ 当前版本
           ├── generate_knowledge()     # 从进化轨迹生成图知识
           ├── query()                  # 三路检索
           ├── former_trace_query()     # 检索①：本任务历史轨迹
           ├── component_query()        # 检索②：组件相似成功实现
           ├── error_query()            # 检索③：相似错误修复方案
           ├── analyze_component()      # LLM分析任务涉及哪些组件
           └── analyze_error()          # 正则/规则提取错误类型

Evaluator (ABC)
 └── CoSTEEREvaluator                   # components/coder/CoSTEER/evaluators.py
      └── FactorEvaluatorForCoder       # factor_coder/evaluators.py
      └── ModelCoSTEEREvaluator         # model_coder/evaluators.py

IterEvaluator (ABC)
 └── RAGEvaluator (ABC)
      └── CoSTEERMultiEvaluator         # 多任务并行评估 + 多评估器链式合并
```

---

## 5. 进化主循环（RAGEvoAgent）

核心方法 [RAGEvoAgent.multistep_evolve()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L140-L198) 是一个生成器，每轮产出进化后的 `EvolvingItem`：

```python
for evo_loop_id in range(self.max_loop):
    # ① RAG 知识检索
    if self.with_knowledge:
        queried_knowledge = self.rag.query(evo, self.evolving_trace)

    # ② 进化（代码生成/修正）
    evo_iter = self.evolving_strategy.evolve_iter(
        evo=evo,
        evolving_trace=self.evolving_trace,
        queried_knowledge=queried_knowledge,
    )

    # ③ 评估（生成器，与 evo_iter 交替推进）
    eva_iter = eva.evaluate_iter(
        evolving_trace=self.evolving_trace,
        queried_knowledge=queried_knowledge,
    )
    next(eva_iter)  # 启动评估生成器

    # ④ 交替推进"进化"和"评估"
    for evolved_evo in evo_iter:
        step_feedback = eva_iter.send(evolved_evo)
        # 若某步评估失败且配置了 stop_eval_chain_on_fail，则中断评估链

    # ⑤ 获取本轮综合反馈
    overall_feedback = self._get_overall_feedback(eva_iter, evolved_evo, ...)

    # ⑥ 记录进化步骤
    es = EvoStep(evolved_evo, queried_knowledge, overall_feedback)
    self.evolving_trace.append(es)

    # ⑦ 知识自我增殖（文件锁保证多进程安全）
    if self.knowledge_self_gen:
        with FileLock(self.filelock_path) if self.enable_filelock else nullcontext():
            self.rag.load_dumped_knowledge_base()
            self.rag.generate_knowledge(self.evolving_trace)
            self.rag.dump_knowledge_base()

    yield evo  # 交还给 CoSTEER.develop()

    # ⑧ 终止条件：所有子任务都完成
    if es.feedback is not None and es.feedback.finished():
        break
```

**关键设计点**：

1. **进化-评估交替生成器**：`evolve_iter` 和 `evaluate_iter` 都是生成器，通过 `send()` 交替推进。这支持"部分实现→部分评估→继续实现"的增量模式（当前因子/模型实现中通常一次性生成全部代码后评估，但框架支持更细粒度）。
2. **Fallback 机制**：CoSTEER.develop() 在每轮保存可接受的结果快照（`fallback_evo_exp`），即使最后一轮因修改导致退化，也能回退到最近一次正确版本。
3. **超时控制**：支持 `max_seconds` 时间限制和全局 Timer，防止无限进化。
4. **知识文件锁**：多进程并行编码时，通过 `FileLock` 保证知识库读写安全。

---

## 6. 多进程进化策略

[MultiProcessEvolvingStrategy.evolve_iter()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolving_strategy.py#L108-L172) 负责任务调度：

### 6.1 任务分类

每轮开始时，遍历所有子任务，根据知识库状态分为三类：

| 分类 | 条件 | 处理方式 |
|------|------|----------|
| **已成功** | 任务描述在 `success_task_to_knowledge_dict` 中 | 直接复用知识库中的实现文件，不调用 LLM |
| **已失败超限** | 任务描述在 `failed_task_info_set` 中（失败次数 ≥ `fail_task_trial_limit`，默认20） | 跳过，不实现 |
| **待实现** | 以上都不是 | 加入 `to_be_finished_task_index`，调用 LLM 生成/修正代码 |

在 `improve_mode` 下，首轮不实现任何任务（因为没有失败反馈可依据），仅从第二轮开始基于反馈修正。

### 6.2 多进程并行

```python
result = multiprocessing_wrapper(
    [
        (implement_func, (task, queried_knowledge, workspace, prev_feedback))
        for target_index in to_be_finished_task_index
    ],
    n=RD_AGENT_SETTINGS.multi_proc_n,  # 并行进程数
)
```

每个待实现任务在独立进程中调用 `implement_one_task()`，进程数由 `RD_AGENT_SETTINGS.multi_proc_n` 控制。

### 6.3 代码注入

生成的代码通过 `assign_code_list_to_evo()` 注入到对应子任务的工作区：
- 因子任务：注入 `factor.py` 文件
- 模型任务：注入 `model.py` 文件
- 支持特殊 key `__change_summary__` 记录本次修改摘要

---

## 7. 图知识库与 RAG 检索

### 7.1 图结构

V2 知识库 [CoSTEERKnowledgeBaseV2](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L852-L1053) 使用 [UndirectedGraph](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/graph.py#L108-L443) 存储知识，节点有四种标签：

```
┌─────────────────┐
│   component     │  组件节点（如"动量因子"、"LSTM模型"、"数据加载"）
│   (预定义/初始化) │
└────────┬────────┘
         │ 1
         │
         ▼ N
┌─────────────────┐    N    ┌─────────────────┐
│ task_description│◄────────│   task_trace    │
│  (任务描述)      │────────►│  (中间失败轨迹)   │
└────────┬────────┘  1      └────────┬────────┘
         │ 1                        │ N
         │                          │
         ▼ N                        ▼
┌─────────────────┐         ┌─────────────────┐
│task_success_    │         │     error       │
│  implement      │         │  (错误类型节点)   │
│ (最终成功实现)    │         └─────────────────┘
└─────────────────┘
```

- **component 节点**：预定义的组件分类，初始化时通过 `init_component_list` 注入。
- **task_description 节点**：任务的自然语言描述，与相关 component 节点相连。
- **task_trace 节点**：进化过程中每一轮的代码+反馈（包括失败轮次），与 task_description 和遇到的 error 节点相连。
- **task_success_implement 节点**：最终成功的代码+反馈，是链的终点。
- **error 节点**：从失败反馈中提取的错误类型（如 `ValueError`、形状不匹配），连接相关的 task_trace。

每个节点携带 embedding 向量，支持语义相似度搜索。图同时维护向量索引（PDVectorBase）用于内容检索。

### 7.2 知识生成（generate_knowledge）

当一个任务成功时，[update_success_task()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L884-L924) 将工作轨迹写入图：

1. 创建 `task_description` 节点，连接到 LLM 分析出的 component 节点。
2. 遍历所有历史轮次（除最后一轮）：为每轮创建 `task_trace` 节点，内容为代码+反馈文本；同时分析该轮遇到的错误，创建/连接 `error` 节点。
3. 最后一轮（成功轮）：创建 `task_success_implement` 节点。

失败轮次的错误分析：
- **执行错误**：用正则提取 `File "...", line N, in func\n  error_line\nErrorType: message` 中的错误类型和错误行。
- **值校验错误**：匹配预定义的错误模式（行数不同、索引不同、值超出容差、相关性不足等）。

### 7.3 三路检索（query）

[CoSTEERRAGStrategyV2.query()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L431-L455) 依次执行三路检索：

#### 检索①：former_trace_query（本任务历史轨迹）

- 检查本任务在当前工作会话中的失败次数。若 ≥ `fail_task_trial_limit`（默认20），加入 `failed_task_info_set`（永久跳过）。
- 返回近期失败轨迹（最多 `v2_query_former_trace_limit`，默认3条），并做退化检测：若某轮"值校验通过→下一轮值校验失败"（类似梯度下降走反方向），则删除退化的轮次。
- 可选地附加"成功后又失败的最新尝试"（`v2_add_fail_attempt_to_latest_successful_execution`），警告 LLM 不要重蹈覆辙。

#### 检索②：component_query（组件相似成功实现）

1. 调用 LLM (`analyze_component`) 分析当前任务涉及哪些预定义组件。
2. 在图中查找与这些 component 节点相连的 `task_description` 节点（多组件时取交集，优先高频交集）。
3. 沿图遍历到 `task_success_implement` 节点，获取成功代码。
4. 补充向量相似度检索：将任务描述与所有成功任务描述做 embedding 余弦相似度，取最相似的。
5. **GT 知识比例保证**：确保检索结果中至少一半来自 Ground Truth（`final_decision_based_on_gt=True`）的知识。
6. 随机采样（`v2_knowledge_sampler`，默认1.0=全部保留）。

#### 检索③：error_query（相似错误修复方案）

1. 获取上一轮失败的错误分析结果。
2. 在图中查找与这些 error 节点相连的 `task_trace` 节点。
3. 从这些 trace 节点继续遍历，找到同一条成功路径上的 `task_success_implement` 节点。
4. 返回 `(错误描述, (失败代码知识, 成功代码知识))` 对，让 LLM 看到"犯了什么错→怎么改对的"完整案例。

### 7.4 V1 与 V2 的区别

| 维度 | V1（已废弃） | V2（当前使用） |
|------|-------------|---------------|
| 存储结构 | 扁平字典 `task → [knowledge]` | 无向图 + 向量索引 |
| 成功检索 | 纯 embedding 相似度 | component 图遍历 + embedding |
| 错误检索 | 无 | error 节点→trace→success 路径 |
| 组件感知 | 无 | LLM 分析任务组件，图交集查询 |
| 退化检测 | 无 | 删除"先对后错"的轨迹 |

V1 的 `generate_knowledge` 和 `query` 方法已直接 `raise NotImplementedError`，代码注释明确鼓励使用 V2。

---

## 8. 反馈评估体系

### 8.1 三层级联评估（以因子为例）

[FactorEvaluatorForCoder.evaluate()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evaluators.py#L31-L120) 实现了三层评估流水线：

```
代码执行 (implementation.execute())
    │
    ├─ 执行成功？
    │   ├─ 否 → execution_feedback = 错误信息
    │   └─ 是 → gen_df = 因子值DataFrame
    │
    ▼
值/形状校验 (FactorValueEvaluator)
    │
    ├─ gen_df is None?
    │   └─ 是 → value_generated_flag=False
    │
    ├─ 有 GT 实现？
    │   ├─ 值完全一致（容差1e-6）→ decision=True，跳过代码评审
    │   ├─ 值高度相关（IC/Rank IC）→ decision=True
    │   └─ 值不匹配 → decision=False
    │
    └─ 无 GT？→ decision=None（需后续判断）
    │
    ▼
LLM 代码评审 (FactorCodeEvaluator)
    │  （仅在值校验未明确通过时执行）
    │  输入：因子描述 + 代码 + 执行反馈 + 值反馈 + GT代码（如有）
    │  输出：代码问题列表（不含具体代码，仅建议）
    │
    ▼
最终决策 (FactorFinalDecisionEvaluator)
    │  综合 execution + value + code 反馈
    │  判定规则：
    │  1. 有GT时值完全一致/高相关 → 正确
    │  2. 无GT时代码执行成功且代码无问题 → 正确
    │  3. 任何执行异常 → 错误
    │  输出：final_decision (bool) + final_feedback (str)
```

### 8.2 多任务并行评估

[CoSTEERMultiEvaluator.evaluate_iter()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py#L261-L333)：

1. 对每个子任务并行调用 `single_evaluator.evaluate()`（多进程）。
2. 支持评估器链：`single_evaluator` 可以是列表，每个评估器独立产出反馈，最后通过 `CoSTEERSingleFeedback.merge()` 合并。
3. 合并规则：`final_decision = all(决策)`（全部通过才通过）；文本字段用 `\n\n` 拼接。
4. 若配置了 `stop_eval_chain_on_fail`，任一子任务失败即中断后续评估器。

---

## 9. 提示词工程

### 9.1 因子实现提示词

定义于 [factor_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/prompts.yaml)。

**system_prompt（`evolving_strategy_factor_implementation_v1_system`）核心指令**：

- 场景描述（通过 `scen.get_scenario_all_desc(filtered_tag="feature")` 获取）。
- 说明三类辅助信息：相似成功代码、历史失败代码+反馈、相似错误修复对。
- **关键约束**："必须基于上一轮尝试进行修改，仔细阅读前次代码，不要修改正确的部分"——这是防止 LLM 每次推倒重来的核心指令。
- 输出 JSON：`{"code": "Python代码字符串"}`。

**user_prompt（`v2_user`）四段式结构**：
1. 目标因子信息（名称、描述、公式、变量）。
2. 相似错误修复对（错误描述 + 错误代码 + 修复后代码），可附 LLM 错误摘要。
3. 相似组件成功代码（参考实现）。
4. 最近一次失败尝试（代码+反馈）。

### 9.2 错误摘要提示词

当相似错误知识较多时，[error_summary()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evolving_strategy.py#L29-L58) 调用独立 LLM 将错误修复案例浓缩为简洁的批评建议，避免 prompt 过长。system_prompt 特别提醒："处理数据时避免时间泄露"。

### 9.3 模型实现提示词

定义于 [model_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/prompts.yaml)。与因子类似，但 system_prompt 额外注入当前工作区的 `model.py` 代码（`current_code`），强调增量修改。

### 9.4 Prompt 长度自适应

因子和模型的 `implement_one_task()` 都有最多10次的截断循环：当 token 数超过模型限制时，按优先级依次裁剪：历史失败轨迹 → 相似成功代码 → 相似错误知识，确保 prompt 不超长。

---

## 10. 两种场景化实现

### 10.1 FactorCoSTEER（因子编码）

文件：[factor_coder/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/__init__.py)

```python
class FactorCoSTEER(CoSTEER):
    def __init__(self, scen, ...):
        setting = FACTOR_COSTEER_SETTINGS
        eva = CoSTEERMultiEvaluator(FactorEvaluatorForCoder(scen=scen), scen=scen)
        es = FactorMultiProcessEvolvingStrategy(scen=scen, settings=FACTOR_COSTEER_SETTINGS)
        super().__init__(settings=setting, eva=eva, es=es, evolving_version=2, ...)
```

- 进化策略：[FactorMultiProcessEvolvingStrategy](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evolving_strategy.py#L23-L178)，生成 `factor.py`。
- 评估器：三层级联（执行→值校验→代码评审→最终决策）。
- 工作区：`FactorFBWorkspace`，执行后产出因子值 DataFrame。
- 额外：develop 完成后将最后一轮反馈存入 `exp.prop_dev_feedback`，供后续反馈阶段使用。

### 10.2 ModelCoSTEER（模型编码）

文件：[model_coder/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/__init__.py)

- 进化策略：[ModelMultiProcessEvolvingStrategy](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/evolving_strategy.py#L20-L89)，生成 `model.py`。
- system_prompt 额外注入 `current_code`（当前 model.py 内容），支持增量修改。
- 评估器：模型代码执行 + 形状检查 + 代码评审。

### 10.3 Qlib 场景封装

- [QlibFactorCoSTEER](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_coder.py)：FactorCoSTEER 的别名/子类。
- [QlibModelCoSTEER](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_coder.py)：ModelCoSTEER 的别名。

量化全流程场景（quant）同时使用两个 coder：因子编码用 `FactorCoSTEER`，模型编码用 `ModelCoSTEER`，分别配置。

---

## 11. 配置与模型绑定

### 11.1 LLM 模型配置

CoSTEER 编码阶段对应 RDLoop 的 `coding` 步骤。工作流引擎为每个步骤自动添加日志标签 `Loop_{li}.coding`，LiteLLM 后端检测到标签中包含 `coding` 时路由到指定模型。

`.env` 配置：

```bash
CHAT_MODEL_MAP={
  "direct_exp_gen": {"model": "openai/minimax-m3", "temperature": "0.7"},
  "coding": {"model": "openai/kimi-k2.7-code", "temperature": "1.0"},
  "running": {"model": "openai/deepseek-v4-flash", "temperature": "0.0"},
  "feedback": {"model": "openai/glm-5.2", "temperature": "0.6"}
}
```

CoSTEER 代码生成使用 **kimi-k2.7-code**（temperature=1.0），该模型针对代码生成优化。温度较高（1.0）有助于在纠错时产生多样化的修复方案。

路由实现见 [litellm.py#L106-L119](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py#L106-L119)：遍历 `chat_model_map`，当 key（如 `"coding"`）出现在当前日志标签栈中时，覆盖默认模型和温度。

### 11.2 关键配置项

[CoSTEERSettings](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/config.py#L6-L40)（环境变量前缀 `CoSTEER_`）：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `max_loop` | `10` | 最大进化轮数 |
| `fail_task_trial_limit` | `20` | 任务失败次数上限，超过后跳过 |
| `coder_use_cache` | `False` | 是否缓存 LLM 响应（调试用） |
| `v2_query_component_limit` | `1` | 组件检索返回的成功实现数量 |
| `v2_query_error_limit` | `1` | 错误检索返回的修复案例数量 |
| `v2_query_former_trace_limit` | `3` | 返回的历史失败轨迹条数 |
| `v2_error_summary` | `False` | 是否启用 LLM 错误摘要 |
| `v2_knowledge_sampler` | `1.0` | 知识随机采样率（1.0=全部） |
| `v2_add_fail_attempt_to_latest_successful_execution` | `False` | 是否附加成功后又失败的尝试 |
| `knowledge_base_path` | `None` | 预加载知识库路径（pickle） |
| `new_knowledge_base_path` | `None` | 新知识库 dump 路径 |
| `enable_filelock` | `False` | 多进程知识库文件锁 |
| `filelock_path` | `None` | 锁文件路径 |

因子和模型场景有各自的 Settings 子类（`FACTOR_COSTEER_SETTINGS`、`MODEL_COSTEER_SETTINGS`），继承上述配置。

### 11.3 并行进程数

`RD_AGENT_SETTINGS.multi_proc_n` 控制多进程进化和评估的并发度。

---

## 12. 输入输出示例

### 12.1 输入（Experiment 中的子任务）

因子任务（FactorTask）：
```
Factor name: VOL_WEIGHTED_MOM_20
Factor description: 成交量加权动量因子，用过去20日收益率乘以成交量比率
Factor formulation: (close/Ref(close,20)-1) * volume/MA(volume,20)
Variables: close=收盘价, volume=成交量, Ref=滞后函数, MA=移动平均
```

模型任务（ModelTask）：
```
Model architecture: 2层LSTM，hidden_size=64，后接全连接层输出预测
Hyperparameters: dropout=0.2, lr=0.001
Model type: pytorch
```

### 12.2 RAG 检索结果（QueriedKnowledgeV2）

```python
CoSTEERQueriedKnowledgeV2(
    success_task_to_knowledge_dict={},  # 本任务未成功过
    failed_task_info_set=set(),  # 未超限
    task_to_former_failed_traces={
        "VOL_WEIGHTED_MOM_20": (
            [CoSTEERKnowledge(  # 上一轮失败
                implementation=FBWorkspace(file_dict={"factor.py": "..."}),
                feedback=CoSTEERSingleFeedback(
                    execution="NameError: name 'Ref' is not defined",
                    final_decision=False,
                ),
            )],
            None,  # 无"成功后又失败"
        ),
    },
    task_to_similar_task_successful_knowledge={
        "VOL_WEIGHTED_MOM_20": [
            CoSTEERKnowledge(  # 相似的MOM因子成功实现
                target_task=FactorTask(factor_name="MOM_20", ...),
                implementation=FBWorkspace(file_dict={"factor.py": "import pandas as pd\ndef calculate(...): ..."}),
                feedback=CoSTEERSingleFeedback(final_decision=True),
            ),
        ],
    },
    task_to_similar_error_successful_knowledge={
        "VOL_WEIGHTED_MOM_20": [
            ("ErrorType: NameError; Error line: Ref(close,20)",
             (CoSTEERKnowledge(...未导入Ref...), CoSTEERKnowledge(...导入了Ref...))),
        ],
    },
)
```

### 12.3 输出（生成的 factor.py）

```python
import pandas as pd
import numpy as np

def calculate(df):
    close = df['close']
    volume = df['volume']
    mom = close / close.shift(20) - 1
    vol_ratio = volume / volume.rolling(20).mean()
    factor = mom * vol_ratio
    return factor
```

### 12.4 反馈（CoSTEERSingleFeedback）

```
------------------Execution------------------
Factor executed successfully, generated DataFrame with shape (10000, 1)
------------------Return Checking------------------
value feedback: Values match ground truth within tolerance 1e-6. Correlation: 1.0
shape feedback: Output shape matches expected (10000, 1)
------------------Code------------------
No critics found
------------------Final Decision------------------
This implementation is SUCCESS.
```

若失败：
```
------------------Execution------------------
Traceback (most recent call last):
  File "factor.py", line 5, in calculate
    mom = close / close.shift(20) - 1
AttributeError: 'Series' object has no attribute 'shift'
------------------Final Decision------------------
This implementation is FAIL.
critic 1: The 'close' variable may not be a pandas Series. Check data loading.
```

---

## 13. 流程图

### 13.1 CoSTEER 整体进化流程

```
              Experiment (含 sub_tasks)
                        │
                        ▼
              ┌──────────────────┐
              │ EvolvingItem     │
              │ .from_experiment │
              └────────┬─────────┘
                       │
                       ▼
         ┌──────────────────────────┐
         │   RAGEvoAgent 循环开始    │
         │   loop = 0..max_loop     │
         └────────────┬─────────────┘
                      │
          ┌───────────┴───────────┐
          │  rag.query()          │
          │  ① former_trace       │
          │  ② component          │
          │  ③ error              │
          └───────────┬───────────┘
                      │ QueriedKnowledge
                      ▼
          ┌───────────────────────┐
          │ evolve_iter()         │
          │  ┌─────────────────┐  │
          │  │ 任务分类:        │  │
          │  │ • 已成功→复用    │  │
          │  │ • 已失败超限→跳过│  │
          │  │ • 待实现→LLM生成 │  │
          │  └────────┬────────┘  │
          │           │           │
          │  ┌────────▼────────┐  │
          │  │ multiprocessing │  │
          │  │ _wrapper        │  │
          │  │ (并行N个任务)    │  │
          │  └────────┬────────┘  │
          │           │ code_list │
          │  ┌────────▼────────┐  │
          │  │ assign_code_    │  │
          │  │ list_to_evo()   │  │
          │  │ 注入 factor.py/ │  │
          │  │ model.py        │  │
          │  └────────┬────────┘  │
          └───────────┼───────────┘
                      │ yield evo
                      ▼
          ┌───────────────────────┐
          │ evaluate_iter()       │
          │  ┌─────────────────┐  │
          │  │ 多进程并行执行   │  │
          │  │ 每个子任务:      │  │
          │  │ 1. execute()    │  │
          │  │ 2. value check  │  │
          │  │ 3. code review  │  │
          │  │ 4. final decide │  │
          │  └────────┬────────┘  │
          │           │           │
          │  ┌────────▼────────┐  │
          │  │ merge feedback  │  │
          │  │ (多评估器合并)   │  │
          │  └────────┬────────┘  │
          └───────────┼───────────┘
                      │ MultiFeedback
                      ▼
          ┌───────────────────────┐
          │ EvoStep 打包          │
          │ evolving_trace.append │
          └───────────┬───────────┘
                      │
          ┌───────────┴───────────┐
          │ knowledge_self_gen?   │
          │ ┌───────────────────┐ │
          │ │ FileLock          │ │
          │ │ load_dumped_kb    │ │
          │ │ generate_knowledge│ │
          │ │  ├─ 成功→图更新   │ │
          │ │  └─ 失败→错误分析 │ │
          │ │ dump_knowledge    │ │
          │ └───────────────────┘ │
          └───────────┬───────────┘
                      │
          ┌───────────┴───────────┐
          │ feedback.finished()?  │
          ├─ Yes → break，返回    │
          └─ No → 下一轮循环      │
                      │
                      ▼
          ┌───────────────────────┐
          │ Fallback 选择          │
          │ 最后一个acceptable结果 │
          │ (create_ws_ckp快照)   │
          └───────────┬───────────┘
                      │
                      ▼
              返回 Experiment
          (含 sub_workspace_list)
```

### 13.2 图知识库结构与检索路径

```
                    ┌──────────────┐
                    │  component   │
                    │ "动量因子"    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
     ┌──────────────┐ ┌──────────┐ ┌──────────────┐
     │task_descript.│ │task_desc.│ │task_descript.│
     │ "MOM_20"     │ │"VW_MOM"  │ │"TS_MOM_60"   │
     └──────┬───────┘ └────┬─────┘ └──────┬───────┘
            │              │              │
     ┌──────┴──────┐       │       ┌──────┴──────┐
     │             │       │       │             │
     ▼             ▼       ▼       ▼             ▼
┌─────────┐  ┌─────────┐ ┌──────┐ ┌─────────┐ ┌─────────┐
│task_    │  │task_    │ │error │ │task_    │ │task_    │
│trace    │  │success_ │ │"Name-│ │trace    │ │success_ │
│(失败轮)  │──│implement│ │Error"│─│(失败轮)  │──│implement│
└────┬────┘  └─────────┘ └──┬───┘ └────┬────┘ └─────────┘
     │                       │          │
     │    ┌──────────────────┘          │
     │    │  (error_query路径)          │
     └────┼─────────────────────────────┘
          │
          ▼
   相似错误修复对:
   (失败代码, 成功代码)
```

**检索路径示意**：
- **component_query**：`component → task_description → task_success_implement`
- **error_query**：`当前错误 → error节点 → task_trace(曾犯此错) → task_success_implement(最终修复)`
- **former_trace_query**：直接从 `working_trace_knowledge` 内存字典读取当前任务的近期历史

### 13.3 因子代码纠错示例流程

```
  轮次1: LLM生成 factor.py (忘记导入 Ref)
    │
    ▼
  执行 → NameError: name 'Ref' is not defined
    │
    ▼
  值校验: gen_df=None (执行失败，无输出)
    │
    ▼
  代码评审: critic 1: Ref函数未导入
    │
    ▼
  final_decision=False
    │
    ▼
  知识生成: analyze_error() → error_node "NameError: Ref"
    │
    ▼
  ────────────── 下一轮 ──────────────
    │
    ▼
  RAG检索:
   ① former_trace: 返回轮次1的代码+反馈
   ② component: 找到MOM_20成功实现（其中正确导入了Ref）
   ③ error: 找到另一个任务曾犯NameError→修复的代码对
    │
    ▼
  LLM生成新代码:
   system: "基于上一轮修改，不要改正确部分"
   user: [目标因子] + [相似错误修复对] + [MOM_20参考代码] + [上轮失败代码]
    │
    ▼
  新 factor.py: from qlib.data import Ref; ... (已修复)
    │
    ▼
  执行成功 → 值校验通过(与GT相关性1.0) → 跳过代码评审
    │
    ▼
  final_decision=True → finished()=True → 进化结束
    │
    ▼
  知识生成: update_success_task()
   创建 task_description → task_trace(轮1,含error) → task_success_implement(轮2)
   （未来任务遇到相同错误时可检索到这条修复路径）
```

---

## 相关代码索引

| 模块 | 文件路径 |
|------|----------|
| CoSTEER 入口 | [rdagent/components/coder/CoSTEER/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/__init__.py) |
| 配置 | [rdagent/components/coder/CoSTEER/config.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/config.py) |
| 可进化对象 | [rdagent/components/coder/CoSTEER/evolvable_subjects.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolvable_subjects.py) |
| 多进程进化策略基类 | [rdagent/components/coder/CoSTEER/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolving_strategy.py) |
| 知识库与RAG | [rdagent/components/coder/CoSTEER/knowledge_management.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py) |
| 评估器 | [rdagent/components/coder/CoSTEER/evaluators.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py) |
| 提示词(CoSTEER) | [rdagent/components/coder/CoSTEER/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/prompts.yaml) |
| 进化引擎 RAGEvoAgent | [rdagent/core/evolving_agent.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py) |
| 进化框架抽象 | [rdagent/core/evolving_framework.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py) |
| Developer 抽象基类 | [rdagent/core/developer.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/developer.py) |
| 无向图知识库 | [rdagent/components/knowledge_management/graph.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/graph.py) |
| 因子进化策略 | [rdagent/components/coder/factor_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evolving_strategy.py) |
| 因子评估器 | [rdagent/components/coder/factor_coder/evaluators.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/evaluators.py) |
| 因子提示词 | [rdagent/components/coder/factor_coder/prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/prompts.yaml) |
| 因子CoSTEER | [rdagent/components/coder/factor_coder/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/__init__.py) |
| 模型进化策略 | [rdagent/components/coder/model_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/evolving_strategy.py) |
| 模型CoSTEER | [rdagent/components/coder/model_coder/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/__init__.py) |
| LiteLLM模型路由 | [rdagent/oai/backend/litellm.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/litellm.py) |
| 主循环调用 | [rdagent/components/workflow/rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L212-L215) |
