# Trace：实验轨迹与记忆系统

> Trace 是 multialpha R&D 循环的"记忆中枢"——它记录每一轮迭代的完整过程，包括假设、实验、代码、执行结果和反馈，并通过 DAG 结构组织实验演化历史，为后续假设生成和 SOTA 追踪提供数据基础。

---

## 1. 什么是 Trace？

Trace 是贯穿整个 R&D 循环的核心数据结构，它解决以下问题：

1. **历史记忆**：记录从第一轮至今的所有实验及其反馈
2. **SOTA 追踪**：跟踪当前最优实验结果
3. **演化关系**：通过 DAG（有向无环图）表达实验之间的父子继承关系
4. **断点恢复**：序列化为 pickle 文件，支持从中断处恢复运行
5. **知识积累**：为 HypothesisGen 和 CoSTEER 提供历史参考

核心定义位于 [proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L318)。

---

## 2. Trace 数据结构

### 2.1 类定义

```python
class Trace(Generic[ASpecificScen, ASpecificKB]):
    scen: ASpecificScen                          # 场景实例（如Qlib场景）
    hist: list[tuple[Experiment, ExperimentFeedback]]  # 实验历史
    dag_parent: list[tuple[int, ...]]            # DAG父节点索引
    idx2loop_id: dict[int, int]                  # 实验索引→loop轮次映射
    knowledge_base: ASpecificKB | None           # 知识库实例
    current_selection: tuple[int, ...]           # 当前选择的扩展点
```

### 2.2 核心字段详解

| 字段 | 类型 | 说明 |
|------|------|------|
| `hist` | `list[tuple[Experiment, ExperimentFeedback]]` | **核心字段**。按时间顺序排列的历史记录，每个元素是 `(实验, 反馈)` 二元组 |
| `dag_parent` | `list[tuple[int, ...]]` | 与 `hist` 一一对应的父节点索引列表。`()` 表示根节点（无父），`(-1,)` 表示以最新节点为父 |
| `idx2loop_id` | `dict[int, int]` | 因为多进程并发执行时 hist 入队顺序可能与 loop_id 不一致，此映射记录每个 hist 索引属于第几轮 |
| `current_selection` | `tuple[int, ...]` | 当前选择的扩展节点，默认 `SEL_LATEST_SOTA = (-1,)` 表示基于最新 SOTA 继续演化 |

### 2.3 类常量

| 常量 | 值 | 含义 |
|------|-----|------|
| `NodeType` | `tuple[Experiment, ExperimentFeedback]` | 历史节点类型别名 |
| `NEW_ROOT` | `()` | 创建全新实验树的根节点标记 |
| `SEL_LATEST_SOTA` | `(-1,)` | 选择最新 SOTA 作为下一轮的基线 |

---

## 3. Experiment 与 Feedback 结构

### 3.1 Experiment（实验）

每个实验包含从假设到执行结果的完整信息（[experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py)）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `hypothesis` | `Hypothesis \| None` | 该实验基于的研究假设（包含方向和理由） |
| `sub_tasks` | `Sequence[Task]` | 子任务列表（如 `FactorTask` 或 `ModelTask`），每个包含名称、描述、公式、变量 |
| `sub_workspace_list` | `list[FBWorkspace \| None]` | 各子任务的代码工作区，包含实际编写的 Python 代码 |
| `based_experiments` | `Sequence[Experiment]` | 该实验的基线实验（通常是当前 SOTA），新因子会与 SOTA 因子组合 |
| `experiment_workspace` | `Workspace \| None` | 实验级共享工作区 |
| `result` | `object` | 执行结果（如回测指标 `pd.Series`，包含 IC、年化收益、最大回撤等） |
| `stdout` | `str` | 执行过程中的标准输出（用于调试和日志） |
| `local_selection` | `tuple[int, ...] \| None` | 该实验指定的父节点选择（支持分支演化） |

### 3.2 FBWorkspace（代码工作区）

每个子任务的代码存储在 FBWorkspace 中：

```python
class FBWorkspace(Workspace):
    file_dict: dict[str, str]  # {文件名: 文件内容} 字典
    # 例如: {"factor.py": "import pandas as pd\ndef calculate(df):...", "config.yaml": "..."}
    workspace_path: Path       # 工作目录路径（RD-Agent_workspace/<UUID>/）
```

代码同时存储在内存（`file_dict`）和磁盘（`workspace_path`），随 pickle 序列化。

### 3.3 ExperimentFeedback（实验反馈）

反馈分为两类：通用反馈和因子/模型场景专用反馈：

**基类**：`ExperimentFeedback`

**因子场景反馈**（`QlibFactorFeedback`）包含三级管线的评估结果：

| 评估级 | 对应字段 | 评估内容 |
|--------|---------|---------|
| 执行检查 | `execution` | 代码是否能运行（traceback 信息） |
| 值/形状检查 | `return_checking` | 输出 DataFrame 的形状、数值范围、与 GT 相关性 |
| 代码评审 | `code_review` | LLM 代码质量评审 |
| 最终决策 | `final_decision` | 布尔值，是否接受为 SOTA |

**假设反馈**（`HypothesisFeedback`，由 Summarizer 生成）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `observations` | `str \| None` | 对实验结果的观察（指标分析） |
| `hypothesis_evaluation` | `str \| None` | 对假设的评估（假设方向是否正确） |
| `new_hypothesis` | `str \| None` | 建议的下一步研究方向 |
| `reason` | `str` | 决策理由 |
| `decision` | `bool` | 是否更新 SOTA |
| `acceptable` | `bool \| None` | 结果是否可接受 |
| `code_change_summary` | `str \| None` | 代码变更摘要 |
| `exception` | `Exception \| None` | 异常信息（执行失败时） |

---

## 4. SOTA（State-of-the-Art）追踪机制

### 4.1 SOTA 判定标准

一个实验成为新的 SOTA 当且仅当：
- 该实验的 `HypothesisFeedback.decision == True`
- Summarizer 根据回测指标（IC、年化收益、夏普比率、最大回撤等）综合判断

### 4.2 SOTA 查询方法

```python
# 获取当前 SOTA 的假设和实验
hypothesis, sota_exp = trace.get_sota_hypothesis_and_experiment()
```

[get_sota_hypothesis_and_experiment()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L178-L185) 反向遍历 `hist` 列表，返回**最后一个** `decision=True` 的实验。这意味着 SOTA 是线性更新的——新的成功实验会取代旧的 SOTA。

### 4.3 SOTA 的作用

- **基线链**：新实验默认基于 SOTA 生成，新因子会与 SOTA 因子组合后一起回测
- **假设生成**：HypothesisGen 根据 SOTA 结果和历史反馈生成新假设
- **避免重复**：已进入 SOTA 的因子不会再被重复生成（去重机制）
- **对比基准**：Runner 回测时会同时计算 SOTA 表现作为对比

---

## 5. 目录结构与文件存储

### 5.1 三套存储目录

| 存储类型 | 配置项 | 默认路径 | 存储内容 |
|---------|--------|---------|---------|
| **Session 快照** | `LOG_SETTINGS.trace_path` | `log/<UTC时间戳>/` | pickle 序列化的完整 LoopBase 对象 |
| **工作区代码** | `RD_AGENT_SETTINGS.workspace_path` | `git_ignore_folder/RD-Agent_workspace/` | 每个实验的 Python 代码文件 |
| **日志对象** | `LOG_SETTINGS.trace_path` | `log/<UTC时间戳>/<tag.path>/` | FileStorage 的 pickle 日志（hypothesis、feedback 等） |
| **WebUI 聚合** | `UI_SETTING.trace_folder` | `git_ignore_folder/traces/` | WebUI 服务端扫描的任务目录 |

### 5.2 Session 快照目录结构

```
log/2026-08-07_10-30-00-000000/           # LOG_TRACE_PATH（UTC时间戳）
├── __session__/                          # LoopBase 序列化快照
│   ├── 0/                                # 第0轮迭代
│   │   ├── 0_direct_exp_gen              # step_idx=0, 假设+实验生成后
│   │   ├── 1_coding                      # step_idx=1, 代码编写后
│   │   ├── 2_running                     # step_idx=2, 执行回测后
│   │   ├── 3_feedback                    # step_idx=3, 反馈生成后
│   │   └── 4_record                      # step_idx=4, 记录到trace后
│   ├── 1/                                # 第1轮迭代（文件更大，因hist增长）
│   │   ├── 0_direct_exp_gen
│   │   ├── 1_coding
│   │   ├── 2_running
│   │   ├── 3_feedback
│   │   └── 4_record
│   └── N/                                # 第N轮
│
├── direct_exp_gen/                       # FileStorage日志tag目录
│   └── <PID链>/
│       └── <YYYY-MM-DD_HH-MM-SS-ffffff>.pkl
├── coding/
│   └── <PID链>/
│       └── <时间戳>.pkl
├── running/
├── feedback/
└── token_cost/                           # Token消耗记录
```

**文件命名规则**：
- 目录名格式：`<loop_idx>/<step_idx>_<step_name>`
- 每完成一个 step 就 dump 一次，文件大小随轮次增长（因为包含完整 trace.hist）
- 加载时自动选择最新的 session 文件

### 5.3 工作区代码目录

```
git_ignore_folder/RD-Agent_workspace/
├── 031c2a22cc84491f8b72d5aa4db12290/    # UUID命名的工作区
│   ├── factor.py                         # 生成的因子代码
│   ├── config.yaml                       # Qlib配置
│   ├── combined_factors_df.parquet       # 中间数据
│   └── mlruns/                           # mlflow实验记录
├── 0349c86f1b574253980f828dfa7694d7/
└── ...
```

每个 UUID 目录对应一个 Experiment 的工作空间，由 Runner 在执行时创建。

### 5.4 FileStorage 日志文件

调用 `logger.log_object(obj, tag="xxx.yyy")` 时：
1. tag 中的 `.` 替换为路径分隔符 `/`
2. 加上 PID 链（多进程隔离）
3. 文件名为 UTC 微秒时间戳

示例路径：
```
Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-00-45-072528.pkl
```

### 5.5 WebUI 目录结构

```
git_ignore_folder/traces/
├── uploads/                              # 上传文件隔离区
│   └── <scenario>/
│       └── <trace_name>/
│           └── <filename>
├── <scenario>/                           # 场景名称（如"Finance Data Building"）
│   ├── <trace_name>/                     # 任务trace目录
│   │   ├── Loop_0/...                    # FileStorage日志
│   │   ├── RDLOOP_SETTINGS/...
│   │   └── scenario/...
│   └── <trace_name>.log                  # 子进程stdout日志
```

---

## 6. DAG 演化关系

### 6.1 DAG 结构

Trace 不是简单的线性历史，而是通过 `dag_parent` 构成有向无环图：

```
轮次0: Exp0 ──(feedback=True)──→ SOTA0
         │
轮次1: Exp1(based=[SOTA0]) ──(feedback=False)──→ 失败
         │
轮次2: Exp2(based=[SOTA0]) ──(feedback=True)──→ SOTA2 (新SOTA)
         │                              ↑
轮次3: Exp3(based=[SOTA2]) ──(feedback=True)──→ SOTA3 (最新SOTA)
```

### 6.2 sync_dag_parent_and_hist

每次 record 步骤调用 [sync_dag_parent_and_hist()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L256-L284) 追加新节点：

```python
def record(self, prev_out):
    exp = prev_out.get("running") or prev_out.get("coding") or ...
    feedback = prev_out["feedback"]
    self.trace.sync_dag_parent_and_hist((exp, feedback), prev_out[self.LOOP_IDX_KEY])
```

这是 Trace 被更新的**唯一入口**。

### 6.3 支持的演化模式

- **线性演化**：默认模式，每轮基于最新 SOTA 继续（`dag_parent` 追加 `(-1,)`）
- **分支探索**：通过 `local_selection` 选择不同父节点分支
- **回溯恢复**：从 session pickle 加载后继续运行（断点续跑）

---

## 7. 持久化与恢复

### 7.1 Dump 机制

[LoopBase.dump()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L426-L432) 在每个 step 成功后执行：

```python
def dump(self, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(self, f)
```

整个 `LoopBase` 对象（包含 `self.trace`）被 pickle 序列化。

### 7.2 Load 机制

[LoopBase.load()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L453-L527) 支持：
- 从目录自动加载最新 session
- Checkout 模式：截断到指定轮次，实现"时光倒流"重新实验
- 断点续跑：从上次中断的 step 继续

### 7.3 不可序列化字段

`__getstate__` 方法排除以下不可 pickle 的字段：
- `queue`（asyncio.Queue）
- `semaphores`（asyncio.Semaphore）
- `_pbar`（tqdm 进度条）
- `multiprocessing.queues.Queue`（用户交互队列）

### 7.4 知识图谱持久化

CoSTEER 的知识图谱（graph.pkl）独立于 Trace 存储：
- 位于当前工作目录 `Path.cwd() / "graph.pkl"`
- 通过 `knowledge_base_path` 配置可跨运行复用
- LoopBase session pickle 中包含完整 KB 引用

---

## 8. Trace 在 R&D 循环中的流转

```
┌─────────────────────────────────────────────────────────────────┐
│                        Trace (记忆中枢)                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ hist: [(Exp0, FB0), (Exp1, FB1), ..., (ExpN, FBN)]         ││
│  │   │                                                         ││
│  │   ├─→ get_sota_hypothesis_and_experiment() → 最新SOTA       ││
│  │   └─→ 供HypothesisGen读取历史反馈生成新方向                   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────┬───────────────────┬───────────────────┬───────────┘
              │ 读取SOTA+历史     │ 读取SOTA          │
              ▼                   ▼                   ▼
     ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
     │HypothesisGen │    │Hypothesis2Exp│    │   CoSTEER    │
     │ 生成假设方向  │───▶│ 转化为Task   │───▶│ 编写代码      │
     └──────────────┘    └──────────────┘    └──────┬───────┘
                                                    │ 代码
                                                    ▼
                                          ┌──────────────┐
                                          │    Runner    │
                                          │ 执行+回测    │
                                          └──────┬───────┘
                                                 │ 结果
                                                 ▼
                                          ┌──────────────┐
                                          │ Summarizer   │
                                          │ 生成反馈     │
                                          └──────┬───────┘
                                                 │ (exp, feedback)
                                                 ▼
                                          ┌──────────────┐
                                          │   record     │
                                          │ trace.hist.  │
                                          │ append()     │
                                          └──────────────┘
```

**关键观察**：
- Trace 是循环的**共享状态**，几乎每个智能体都从中读取
- 只有 record 步骤写入 Trace（追加新节点）
- 每轮迭代后，Trace 增长约一个 `(Experiment, Feedback)` 二元组

---

## 9. 示例：一次完整的 Trace 记录

假设因子挖掘场景运行 3 轮后，Trace 的内容示意：

```python
trace.hist = [
    # (Experiment, Feedback)
    (Exp0(hypothesis="探索动量类因子", sub_tasks=[FactorTask("MOM_5", ...)]),
     FB0(decision=False, reason="IC值仅0.02，未超越基线")),

    (Exp1(hypothesis="探索换手率因子", sub_tasks=[FactorTask("TURNOVER_20", ...)],
          based_experiments=[SOTA0]),
     FB1(decision=True, reason="IC=0.06, 年化15%, 超越SOTA")),  # → SOTA更新

    (Exp2(hypothesis="优化换手率因子参数", sub_tasks=[FactorTask("TURNOVER_10", ...)],
          based_experiments=[SOTA1]),
     FB2(decision=False, reason="参数优化后IC下降至0.04")),
]

trace.dag_parent = [
    (),        # Exp0: 根节点（无父）
    (-1,),     # Exp1: 父节点是上一轮
    (-1,),     # Exp2: 父节点是上一轮（SOTA1）
]
```

对应的 session pickle 文件大小变化：
```
0/0_direct_exp_gen  ~50KB    (空hist)
0/4_record          ~52KB    (1条历史)
1/0_direct_exp_gen  ~470KB   (1条历史)
1/4_record          ~495KB   (2条历史)
2/4_record          ~520KB   (3条历史)
```

---

## 10. SOTA 查询工具

### 10.1 CLI 命令

```bash
rdagent sota --log-path log/2026-08-07_10-30-00-000000
```

[sota_query.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/sota_query.py) 加载 session pickle，提取结构化 SOTA 信息。

### 10.2 WebUI API

```
GET /traces/{trace_name}/sota
```

返回包含 hypothesis、feedback、metrics、factor/model code、workspace 路径的 JSON。

---

## 11. 相关代码索引

| 模块 | 文件路径 |
|------|----------|
| Trace 类定义 | [rdagent/core/proposal.py#L141-L318](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/proposal.py#L141-L318) |
| Experiment/Workspace 定义 | [rdagent/core/experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/experiment.py) |
| RDLoop 五步主循环 | [rdagent/components/workflow/rd_loop.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/workflow/rd_loop.py) |
| LoopBase dump/load | [rdagent/utils/workflow/loop.py#L85-L566](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L85-L566) |
| FileStorage pickle存储 | [rdagent/log/storage.py#L28-L115](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/storage.py#L28-L115) |
| 日志配置(trace_path) | [rdagent/log/conf.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/conf.py) |
| SOTA 查询工具 | [rdagent/log/sota_query.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/sota_query.py) |
| 存储路径详细规则 | [doc/architecture/trace-storage-paths.md](file:///home/zxh/projects/1.multialphaV/RD-Agent/doc/architecture/trace-storage-paths.md) |
