# RD-Agent 智能体框架架构

> 本文从框架设计者视角解释 RD-Agent 的智能体抽象：核心基类如何定义契约、组件如何组合、执行引擎如何驱动循环。如果你熟悉 LangGraph/LangChain，文末有概念对照表帮你快速定位。

---

## 1. 设计哲学

RD-Agent 的智能体框架不是一个通用的"图编排器"（如 LangGraph 的 StateGraph），也不是一个"链式调用器"（如 LangChain 的 Runnable）。它的设计围绕一个具体问题展开：

**如何用 LLM 驱动"假设 → 实验 → 编码 → 执行 → 反馈"的科学研发闭环，并让代码在多轮反馈中自动进化？**

因此框架的核心抽象不是 Node/Edge/Chain，而是：

| 概念 | 角色 | 类比 |
|------|------|------|
| `Scenario` | 场景上下文，注入所有组件 | LangGraph 的 configurable context |
| `Developer` | 对实验做一次"开发"（写代码/跑代码） | 一个有副作用的 Node |
| `Experiment` | 在多步骤间传递的状态对象 | LangGraph 的 State（但可变） |
| `EvolvingStrategy` + `EvoAgent` | 内层迭代：生成→评估→修复的循环 | 一个 while 循环 + LLM call |
| `RDLoop` + `LoopBase` | 外层编排：5 步流水线 + 检查点恢复 | LangGraph 的 Graph + Checkpointer |
| `RAGStrategy` | 知识检索与积累 | 外挂长期记忆 |

关键设计选择：

1. **原地修改（in-place mutation）**：`Developer.develop(exp)` 不返回新对象，而是直接修改传入的 `exp`。这与 LangGraph 的 immutable state reducer 截然相反，好处是代码简单、支持异常时保留中间结果。
2. **生成器协议（generator protocol）**：内层进化用 Python generator 的 `yield`/`send()` 实现"生成一点→评估一点"的交替，不需要额外的调度器。
3. **元类自动收集步骤**：RDLoop 的5个步骤不是用装饰器或DSL声明的，而是通过 metaclass 扫描类中按定义顺序排列的方法自动收集。
4. **组合优于继承**：CoSTEER 不是一个巨大的类，而是 `Coder` 组合 `EvolvingStrategy` + `RAGStrategy` + `Evaluator`，每个都可独立替换。

---

## 2. 核心抽象层

核心代码位于 [rdagent/core/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/)。

### 2.1 Scenario — 场景上下文

[scenario.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/scenario.py) 定义场景信息接口：

```python
class Scenario(ABC):
    @property
    def background(self) -> str: ...
    def get_source_data_desc(self) -> str: ...
    def get_scenario_all_desc(self) -> str: ...
    def get_runtime_environment(self) -> str: ...
```

`Scenario` 是几乎所有组件的构造参数——`Developer`、`HypothesisGen`、`EvolvingStrategy` 都持有 `self.scen`。它提供 prompt 所需的背景描述、数据格式说明、运行环境信息。具体场景（Qlib 因子/模型/量化）继承此类并填充领域知识。

### 2.2 Task / Workspace / Experiment — 状态对象

[experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py) 定义了三层状态结构：

```
Task（任务规格）
  ├── name, version, description, user_instructions
  └── get_task_information()  → 给 LLM 看的任务描述

Workspace（工作区，泛型 [Task, Feedback]）
  ├── target_task: Task
  ├── feedback: Feedback
  ├── execute(env, entry)     → 在 Env 中运行代码
  ├── all_codes               → 工作区所有代码
  ├── create_ws_ckp()         → zip 打包目录做内存快照
  └── recover_ws_ckp()        → 从快照恢复
  子类: FBWorkspace（文件型工作区）

Experiment（实验，泛型 [Task, WSExp, WSSub]）
  ├── hypothesis: Hypothesis
  ├── sub_tasks: Sequence[Task]
  ├── sub_workspace_list: list[Workspace]   ← 每个子任务一个工作区
  ├── experiment_workspace: Workspace        ← 实验级共享工作区
  ├── based_experiments: list[Experiment]    ← 基于哪些历史实验
  ├── result                                 ← 执行结果
  └── create_ws_ckp() / recover_ws_ckp()    ← 委托给所有 workspace
```

设计要点：
- **一个 Experiment 包含多个子任务**（如10个因子），每个子任务有独立 Workspace，但共享一个 experiment_workspace
- Workspace 的 `execute()` 委托给 `Env`（Docker/Conda），实现代码执行与环境的解耦
- `FBWorkspace` 用内存 zip bytes 实现轻量级检查点，CoSTEER 的 fallback 机制靠它回滚到最佳版本

### 2.3 Developer — 开发者抽象

[developer.py#L12-L34](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/developer.py#L12-L34)：

```python
class Developer(ABC, Generic[ASpecificExp]):
    def __init__(self, scen: Scenario) -> None:
        self.scen = scen

    @abstractmethod
    def develop(self, exp: ASpecificExp) -> ASpecificExp:
        """Should inplace edit the exp. Return value will be removed in future."""
```

契约极简：接收一个 Experiment，原地修改它。两个核心实现：

| 实现 | 职责 | 做了什么 |
|------|------|---------|
| `CoSTEER`（Coder） | 写代码 | 调用 LLM 生成 factor.py/model.py，多轮迭代修复 |
| `CachedRunner`（Runner） | 跑代码 | 在 Docker/Conda 中执行，产出回测指标 |

它们都继承 `Developer`，所以 RDLoop 可以用统一的 `.develop(exp)` 接口编排。

### 2.4 Feedback / Evaluator — 评估抽象

[evaluation.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evaluation.py)：

```python
class Feedback:
    def is_acceptable(self) -> bool: ...
    def finished(self) -> bool: ...       # 全部通过，可提前终止
    def __bool__(self) -> bool: ...       # 是否有有效反馈

class Evaluator(ABC):
    @abstractmethod
    def evaluate(self, eo: EvaluableObj) -> Feedback: ...
```

反馈体系有两个层级：

- **CoSTEER 内部**：`CoSTEERSingleFeedback`（execution/return_checking/code/final_decision 四阶段）→ `CoSTEERMultiFeedback`（多个子任务的反馈列表）
- **RDLoop 外层**：`ExperimentFeedback`（decision/reason/exception）→ `HypothesisFeedback`（增加 observations/hypothesis_evaluation/new_hypothesis）

### 2.5 Proposal — 假设与实验生成

[proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py) 定义三个抽象：

| 抽象类 | 方法 | 职责 |
|--------|------|------|
| `HypothesisGen` | `gen(trace, plan) → Hypothesis` | 基于历史生成新研究假设 |
| `Hypothesis2Experiment` | `convert(hypothesis, trace) → Experiment` | 把假设转化为可执行任务列表 |
| `Experiment2Feedback` | `generate_feedback(exp, trace) → ExperimentFeedback` | 分析执行结果，产生反馈 |

### 2.6 Trace — 实验历史 DAG

[proposal.py#L141](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141) 的 `Trace` 维护所有历史实验的 DAG 结构：

- `hist: list[tuple[Experiment, Feedback]]`：按时间排列的实验历史
- `dag_parent`：实验间的父子关系（基于哪个实验改进）
- 支持 SOTA 选择、祖先追踪、checkpoint 选择

---

## 3. 进化框架（Evolving Framework）

这是 RD-Agent 最有特色的部分，代码位于 [evolving_framework.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py) 和 [evolving_agent.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py)。

### 3.1 四元组

进化框架由四个角色协作：

```
EvolvableSubjects     ← 被进化的对象（Experiment 继承它）
       │
       ▼
EvolvingStrategy      ← 怎么变（LLM 生成代码）
       │
       ▼
IterEvaluator         ← 怎么评（运行代码 + 检查结果）
       │
       ▼
RAGStrategy           ← 参考什么经验（知识图谱检索）
```

### 3.2 EvolvableSubjects — 可进化对象

[evolving_framework.py#L33-L37](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py#L33-L37)：

```python
class EvolvableSubjects(EvaluableObj):
    def clone(self) -> EvolvableSubjects:
        return copy.deepcopy(self)
```

`Experiment` 继承此类，意味着实验可以被评估和进化。

### 3.3 EvolvingStrategy — 进化策略

[evolving_framework.py#L61-L91](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py#L61-L91)：

```python
class EvolvingStrategy(ABC, Generic[ASpecificEvolvableSubjects]):
    @abstractmethod
    def evolve_iter(
        self, evo, queried_knowledge=None, evolving_trace=None
    ) -> Generator[ASpecificEvolvableSubjects, None, None]:
```

关键设计：**用生成器（generator）产出部分解**。不是一次性生成完整代码，而是可以分阶段 yield（如先生成框架，再填充细节），每阶段都可以被评估器立即评估。

契约注释明确说明：yield 出的 evo 与入参是**同一个对象**（in-place 修改）。

### 3.4 IterEvaluator — 迭代评估器

[evolving_framework.py#L94-L138](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py#L94-L138)：

```python
class IterEvaluator(Evaluator):
    @abstractmethod
    def evaluate_iter(self) -> Generator[Feedback, EvaluableObj | None, Feedback]:
        ...
```

这也是一个生成器，通过 Python 的 `generator.send()` 协议与 `evolve_iter` 交替协作：

```python
# evolving_agent.py 中的核心协作逻辑
evo_iter = evolving_strategy.evolve_iter(evo, ...)
eva_iter = eva.evaluate_iter(...)
next(eva_iter)  # 启动评估器
for evolved_evo in evo_iter:
    step_feedback = eva_iter.send(evolved_evo)  # 把部分解发给评估器
```

```
evolve_iter          evaluate_iter
    │                     │
    │── yield evo ───────▶│
    │                     │── 运行代码，检查结果
    │◀── send(feedback) ──│
    │                     │
    │── yield evo' ──────▶│
    │                     │── 再次评估
    │◀── send(feedback) ──│
    │                     │
    │                  return overall_fb  ← StopIteration
```

这种设计让"生成一点、评估一点"成为可能，不需要等所有代码写完才发现错误。

### 3.5 RAGStrategy — 知识检索策略

[evolving_framework.py#L141-L187](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py#L141-L187)：

```python
class RAGStrategy(ABC, Generic[ASpecificEvolvableSubjects]):
    def __init__(self, *args, **kwargs):
        self.knowledgebase = self.load_or_init_knowledge_base(...)

    @abstractmethod
    def query(self, evo, evolving_trace) -> QueriedKnowledge: ...
    @abstractmethod
    def generate_knowledge(self, evolving_trace) -> Knowledge | None: ...
    @abstractmethod
    def dump_knowledge_base(self) -> None: ...
    @abstractmethod
    def load_dumped_knowledge_base(self) -> None: ...
```

每轮进化前调 `query()` 获取参考知识，每轮结束后调 `generate_knowledge()` 沉淀新经验。CoSTEER 的 V2 实现使用无向图知识图谱，详见 [costeer-knowledge-base.md](costeer-knowledge-base.md)。

### 3.6 RAGEvoAgent — 进化驱动器

[evolving_agent.py#L78-L198](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L78-L198) 把上述三者编排为一个完整循环：

```
for evo_loop_id in range(max_loop):
    │
    ├── 1. rag.query(evo, trace)           → 获取知识
    ├── 2. evolve_iter ⇄ evaluate_iter     → 生成+评估（generator 交替）
    ├── 3. EvoStep(evo, knowledge, fb)     → 打包记录
    ├── 4. evolving_trace.append(es)       → 追加历史
    ├── 5. rag.generate_knowledge(trace)   → 知识自增殖（可选，文件锁保护）
    ├── 6. yield evo                       → 交还控制权给 Coder
    └── 7. if feedback.finished(): break   → 全部通过则提前退出
```

这是一个**双层生成器**：`multistep_evolve` 本身也是 generator，每轮 yield 一次进化结果。外层的 `CoSTEER.develop()` 消费这个 generator，做 fallback 选择和超时控制。

---

## 4. RDLoop — 外层流水线编排

### 4.1 元类自动收集步骤

[loop.py#L33-L74](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L33-L74) 的 `LoopMeta` 元类在类定义时：

1. 递归收集基类的 `steps`
2. 扫描当前类中所有**不以 `_` 开头、callable、非 type、非 load/dump** 的属性
3. 按定义顺序拼成 `steps` 列表

所以定义一个循环只需要按顺序写方法：

```python
class RDLoop(LoopBase, metaclass=LoopMeta):
    def direct_exp_gen(self, prev_out): ...   # step 0
    def coding(self, prev_out): ...           # step 1
    def running(self, prev_out): ...          # step 2
    def feedback(self, prev_out): ...         # step 3
    def record(self, prev_out): ...           # step 4
```

不需要装饰器、不需要注册、不需要 DSL——方法定义顺序就是执行顺序。

### 4.2 五个步骤

[rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py)：

| 顺序 | 方法 | 行号 | 调用 | 作用 |
|------|------|------|------|------|
| 1 | `direct_exp_gen` | [L199](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L199) | `hypothesis_gen.gen()` + `hypothesis2experiment.convert()` | 生成假设和实验任务（async，支持并行） |
| 2 | `coding` | [L212](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L212) | `coder.develop(exp)` | CoSTEER 写代码 |
| 3 | `running` | [L217](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L217) | `runner.develop(exp)` | Docker/Conda 中执行回测 |
| 4 | `feedback` | [L222](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L222) | `summarizer.generate_feedback(exp, trace)` | LLM 分析结果 |
| 5 | `record` | [L238](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py#L238) | `trace.sync_dag_parent_and_hist()` | 写入历史 DAG |

步骤间通过 `prev_out: dict[str, Any]` 传递数据。每个步骤的返回值以方法名为 key 存入字典，下一个步骤按名取值。

### 4.3 并行调度

- `direct_exp_gen` 是 async 方法，用 `get_unfinished_loop_cnt() < max_parallel` 控制并发
- 非最后一步通过 `ProcessPoolExecutor` + deepcopy 在**子进程**中执行（`force_subproc`）
- `feedback` 和 `record` 用信号量限制并发为 1，防止 DAG 写入冲突

### 4.4 配置驱动的组件组装

组件不是硬编码的，而是通过配置字符串 + `import_class()` 动态加载。[conf.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py) 中每个 PropSetting 定义了六个组件的完整类路径：

```python
class FactorBasePropSetting:
    scen: str = "rdagent.scenarios.qlib.factor_experiment.QlibFactorScenario"
    hypothesis_gen: str = "rdagent.scenarios.qlib.proposal.factor_proposal.QlibFactorHypothesisGen"
    hypothesis2experiment: str = "..."
    coder: str = "rdagent.components.coder.factor_coder.FactorCoSTEER"
    runner: str = "..."
    summarizer: str = "..."
```

RDLoop 构造时用 `import_class(path)(scen=scen)` 实例化每个组件。切换场景（因子/模型/量化）只需换一个 PropSetting。

### 4.5 Quant 场景的双轨分派

[quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py) 的 `QuantRDLoop` 同时持有 factor 和 model 两套组件，在 `coding`/`running`/`feedback` 步骤中根据 `hypo.action`（"factor" 或 "model"）动态选择走哪条轨道。Action 选择支持 bandit（多臂老虎机）、LLM、random 三种策略。

---

## 5. 检查点与恢复

[loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py) 实现了两层恢复机制。

### 5.1 Loop 级别的 pickle 快照

每步成功执行后，在 `finally` 中自动 dump：

```
__session__/<loop_id>/<step_idx>_<step_name>
```

[loop.py#L426-L432](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L426-L432)：

```python
def dump(self, path):
    with path.open("wb") as f:
        pickle.dump(self, f)
```

整个 LoopBase 实例（含 trace、prev_out、所有组件状态）被 pickle 序列化。不可序列化的运行时对象（asyncio.Queue、semaphores、multiprocessing.Queue）在 `__getstate__` 中排除，`__setstate__` 中重建。

### 5.2 Workspace 级别的 zip 快照

[experiment.py#L324-L378](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py#L324-L378) 的 `FBWorkspace` 用内存 zip bytes 实现工作目录的轻量级快照：

- `create_ws_ckp()`：把目录打包成 zip bytes 存在内存中
- `recover_ws_ckp()`：清空目录后从 zip 恢复

CoSTEER 的 fallback 机制用它：每轮如果反馈可接受就存一份快照，如果后续退化就恢复到最佳版本。

### 5.3 withdraw（回退）机制

当步骤抛出 `withdraw_loop_error` 时，系统回退到前一个 loop 的最新快照，整体覆盖当前状态后重新启动。这支持"当前路线走不通，退回上一步换条路"的场景。

### 5.4 skip（跳过）机制

抛出 `skip_loop_error` 时跳到指定步骤（默认 feedback），在 `prev_out` 中标记异常，后续步骤可以感知到。

---

## 6. 执行环境抽象

[utils/env.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/env.py) 定义了统一的 `Env` 抽象：

```
Env(Generic[Conf])
  ├── LocalEnv       → subprocess 执行（符号链接模拟 volume）
  │     └── QlibCondaEnv  → conda 环境
  └── DockerEnv      → Docker 容器执行
        └── QTDockerEnv  → Qlib + Torch 镜像
```

核心接口 `Env.run(entry, local_path, env) → EnvResult` 返回 `(stdout, exit_code, running_time)`。Workspace 的 `execute()` 委托给 Env，因此同一份代码可以在本地 conda 或 Docker 中运行，只需改配置。

---

## 7. 组件组合实例：CoSTEER 如何组装

以 [FactorCoSTEER](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/__init__.py) 为例：

```
FactorCoSTEER (Developer)
  │
  ├── scen: QlibFactorScenario
  ├── settings: CoSTEERSettings (max_loop=10, knowledge paths, etc.)
  │
  ├── eva: CoSTEERMultiEvaluator
  │     └── FactorEvaluatorForCoder    ← 单因子评估：执行+return检查+代码检查
  │
  ├── es: FactorMultiProcessEvolvingStrategy (EvolvingStrategy)
  │     └── implement_one_task()       ← LLM 生成 factor.py（多进程并行）
  │
  └── rag: CoSTEERRAGStrategyV2 (RAGStrategy)
        └── knowledgebase: CoSTEERKnowledgeBaseV2
              └── graph: UndirectedGraph  ← 五类节点的知识图谱
```

`develop(exp)` 的执行流：

```
CoSTEER.develop(exp)
  │
  ├── EvolvingItem.from_experiment(exp)     ← 包装为可进化对象
  ├── RAGEvoAgent(max_loop, es, rag, ...)  ← 创建驱动器
  │
  └── for evo_exp in evolve_agent.multistep_evolve(evo_exp, eva):
        │   （每轮：RAG查询 → LLM修复 → 多进程评估 → 知识沉淀）
        │
        ├── should_use_new_evo()? → 保存 fallback 快照
        ├── logger.log_object(sub_workspace_list, tag="evolving code")
        └── 超时检查 → break
  │
  └── fallback 到最佳可接受版本 → recover_ws_ckp() → 后处理
```

---

## 8. 与 LangGraph / LangChain 的对照

如果你熟悉 LangGraph 或 LangChain，这张表帮你建立直觉映射：

| 维度 | LangGraph | LangChain | RD-Agent |
|------|-----------|-----------|----------|
| **核心抽象** | StateGraph（Node + Edge + State） | Chain / Runnable | Developer + Experiment + Loop |
| **状态传递** | Immutable state + reducer 合并 | dict 在 chain 间传递 | **Mutable Experiment**，原地修改 |
| **流程定义** | 声明式：`add_node` / `add_edge` / `add_conditional_edges` | 链式：`prompt | llm | parser` | **方法定义顺序即执行顺序**（metaclass 收集） |
| **循环** | `add_conditional_edges` 指回已有节点 | `RunnableWithMessageHistory` | for 循环 + generator yield，`feedback.finished()` 控制退出 |
| **并行** | `Send` API 或 async nodes | `RunnableParallel` | asyncio 信号量 + ProcessPoolExecutor 子进程 |
| **检查点** | Checkpointer（SqliteSaver/PostgresSaver） | 无内置 | pickle 快照每步自动 dump + zip workspace 快照 |
| **人工干预** | `interrupt()` | HumanInputLLM / Tool | multiprocessing Queue + `Interactor` 抽象 |
| **LLM 调用** | 直接调 llm.invoke | ChatModel / LLMChain | `APIBackend`（litellm 统一后端） |
| **工具调用** | ToolNode / bind_tools | Tool / AgentExecutor | `PAIAgent`（Pydantic-AI + MCP toolsets） |
| **RAG/记忆** | 自建（vector store + retriever） | VectorStore + Retriever | `RAGStrategy` + 无向图知识库（内置知识自增殖） |
| **评估** | 需自建 | LangSmith evaluator | 内置 `Evaluator` + generator 协议的迭代评估 |
| **配置** | Builder 代码配置 | RunnableConfig | pydantic-settings + 类路径字符串动态加载 |

### 关键区别

1. **RD-Agent 是为"代码进化"这个特定领域设计的**，不是通用 Agent 框架。它的抽象（Experiment/Workspace/CoSTEER/EvolvingStrategy）直接映射科学研发过程，而不是通用的"消息→工具→消息"循环。

2. **状态是可变的，不是 immutable 的**。LangGraph 强调 state reducer 和不可变性以支持时间旅行；RD-Agent 选择原地修改因为代码执行天然有副作用（文件系统变更），且异常时需要保留中间产物。

3. **内层循环用 generator 而非图**。CoSTEER 的"生成→评估→修复"不需要画成图，Python generator 的 `yield`/`send()` 天然表达这种交替协议，代码更简洁。

4. **知识积累是内置的**。LangGraph 需要自己接 vector store；RD-Agent 的 `RAGStrategy` 是进化循环的一等公民，每轮自动查询和沉淀知识，且支持图结构检索而非纯向量相似度。

5. **没有 DSL**。不写 `graph.add_node().add_edge()`，而是按顺序定义 Python 方法。框架约定优于配置，但牺牲了静态可视化能力。

---

## 9. 扩展点

框架设计了多个可替换点：

| 想做什么 | 继承/实现 | 参考 |
|---------|----------|------|
| 新增一个研发场景 | `Scenario` + 五个组件实现 | [scenarios/qlib/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/) |
| 替换代码生成策略 | `EvolvingStrategy` | [CoSTEER/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evolving_strategy.py) |
| 替换知识库 | `RAGStrategy` + `EvolvingKnowledgeBase` | [costeer-knowledge-base.md](costeer-knowledge-base.md) |
| 新增评估维度 | `IterEvaluator` / `Evaluator` | [CoSTEER/evaluators.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/evaluators.py) |
| 自定义循环步骤 | 继承 `LoopBase` + metaclass 自动收集 | [rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py) |
| 新增执行环境 | `Env` | [utils/env.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/env.py) |
| 接入新 LLM | `APIBackend` 子类 | [oai/backend/](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/oai/backend/) |
