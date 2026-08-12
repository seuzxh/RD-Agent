# CoSTEER 知识库与知识图谱

> CoSTEER 在 LLM 迭代纠错过程中，通过一个**基于无向图的 RAG 知识库**积累历史经验：成功过的因子代码、犯过的错误及修复方式、组件间的关联关系。这些知识在后续迭代和后续任务中被检索，作为参考注入 prompt，让 LLM "站在经验的肩膀上"改代码，而不是每次从零开始。

---

## 1. 一句话理解

CoSTEER 的知识库本质是一个**无向图 + 向量索引**：

- 图节点有五种类型：组件、任务描述、失败轨迹、成功实现、错误
- 节点之间通过无向边连接，表达"任务用了什么组件""在哪一步报了什么错""最终怎么改好的"
- 每次 evo_loop 开始前，系统从图中检索三类知识喂给 LLM：自己之前怎么失败的、相似任务怎么成功的、同样的错误别人怎么修好的
- 任务成功后，整条失败→成功的轨迹才被沉淀进图；失败中的尝试暂存在内存里，不污染知识库

核心代码位于 [knowledge_management.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py) 和 [graph.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/graph.py)。

---

## 2. 整体架构

```
CoSTEERRAGStrategyV2          ← RAG 策略：编排"查知识"和"存知识"
  ├── knowledgebase: CoSTEERKnowledgeBaseV2
  │     ├── graph: UndirectedGraph         ← 无向图（持久化为 graph.pkl）
  │     │     └── nodes: dict[id, UndirectedNode]
  │     │           └── vector_base: PDVectorBase  ← 每个节点有 embedding，支持语义搜索
  │     ├── working_trace_knowledge        ← 当前未完成任务的临时轨迹
  │     ├── working_trace_error_analysis   ← 与轨迹对齐的错误解析
  │     ├── success_task_to_knowledge_dict ← 已成功任务的最新知识
  │     └── node_to_implementation_knowledge_dict  ← 节点ID → 知识对象反查表
  └── config: CoSTEERSettings              ← 检索数量、失败上限等参数
```

抽象基类定义在 [evolving_framework.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_framework.py)：
- `Knowledge`：一条知识
- `QueriedKnowledge`：一次查询的结果
- `EvolvingKnowledgeBase`：知识库（需实现 `query()`）
- `RAGStrategy`：RAG 策略（加载/查询/生成/持久化四个方法）

---

## 3. 知识单元与数据结构

### 3.1 CoSTEERKnowledge — 一条知识

[knowledge_management.py#L36-L52](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L36-L52)，三元组：

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_task` | `Task` | 任务对象（因子/模型描述） |
| `implementation` | `FBWorkspace` | 代码工作区（构造时 `.copy()`，防止外部修改） |
| `feedback` | `Feedback` | 评估反馈（通过/失败 + 错误信息） |

方法 `get_implementation_and_feedback_str()` 把代码和反馈拼成文本块，作为图节点的 `content`。

### 3.2 CoSTEERQueriedKnowledgeV2 — 查询结果

[knowledge_management.py#L281-L351](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L281-L351)，每次 evo_loop 开始时 `query()` 返回的对象，包含四类知识：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success_task_to_knowledge_dict` | `dict[str, CoSTEERKnowledge]` | 已成功任务的最新实现（直接复用，不调 LLM） |
| `failed_task_info_set` | `set[str]` | 失败次数超限（默认20次）的任务，直接放弃 |
| `task_to_former_failed_traces` | `dict[str, tuple[list, latest]]` | 自身最近 N 次失败轨迹 |
| `task_to_similar_task_successful_knowledge` | `dict[str, list]` | 相似组件任务的成功实现 |
| `task_to_similar_error_successful_knowledge` | `dict[str, list]` | 犯过相同错误并最终修复的（出错代码, 成功代码）对 |

### 3.3 UndirectedNode — 图节点

[graph.py#L22-L51](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/graph.py#L22-L51)，继承自 `KnowledgeMetaData`：

| 属性 | 说明 |
|------|------|
| `id` | 唯一标识 |
| `content` | 文本内容（代码+反馈、任务描述、错误信息等） |
| `label` | 节点类型标签（五种，见下表） |
| `embedding` | 向量表示，加入图时自动计算 |
| `neighbors` | 邻居节点集合（无向边，双向添加） |
| `appendix` | 附加信息 |

五种节点标签：

| label | 含义 | 创建时机 |
|-------|------|---------|
| `component` | 任务涉及的组件（如数据加载、模型结构） | 知识库初始化时注入 |
| `task_description` | 任务描述 | 任务成功后入图时创建 |
| `task_trace` | 中间失败尝试的代码+反馈 | 成功路径上除最后一步外的每步 |
| `task_success_implement` | 最终成功实现 | 成功路径的最后一步 |
| `error` | 从反馈中解析出的错误 | 从 traceback 或值校验中提取 |

---

## 4. 图结构长什么样

任务成功后，[CoSTEERKnowledgeBaseV2.update_success_task()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py) 把整条轨迹沉淀入图。典型拓扑：

```
                    component (数据加载)
                   /
component (模型) ─┼── task_description ("计算RSI因子")
                   \        │
                    │       ├── task_trace (第1次尝试 + KeyError)
                    │       │        └── error ("KeyError: 'close'")
                    │       │
                    │       ├── task_trace (第2次尝试 + 长度不匹配)
                    │       │        └── error ("ValueError: length mismatch")
                    │       │
                    │       └── task_success_implement (第3次，成功)
                    │
                    └── (另一个任务也可能连接到同一个 component 或同一个 error)
```

关键连接规则：

- `task_description` 连接到该任务用到的所有 `component` 节点
- 每次失败的 `task_trace` 同时连接到 `task_description` 和该步解析出的 `error` 节点
- 最终的 `task_success_implement` 只连接到 `task_description`
- **相同内容的节点会被复用**（通过 embedding 0.999 阈值去重），所以不同任务犯同一个错误时会共享同一个 `error` 节点

这种结构让系统可以回答三类问题：
1. **哪些任务用了相似的组件？** → 从 component 出发找 task_description
2. **谁犯过同样的错误？** → 从 error 出发找 task_trace
3. **那个错误最后是怎么修好的？** → 从 task_trace 沿图走到 task_success_implement

---

## 5. 知识检索：每次 evo_loop 开始前查什么

[CoSTEERRAGStrategyV2.query()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py) 顺序组合三个子查询：

```python
queried = CoSTEERQueriedKnowledgeV2(...)
queried = self.former_trace_query(...)   # 1. 自己之前怎么失败的
queried = self.component_query(...)      # 2. 相似任务怎么成功的
queried = self.error_query(...)          # 3. 同样的错误怎么修好的
```

### 5.1 former_trace_query — 自身历史

检索当前任务**自己最近几次失败**的代码和反馈，让 LLM 看到"之前试过什么、报了什么错"。

关键处理：
- 超过 `fail_task_trial_limit`（默认20）次仍未成功 → 加入 `failed_task_info_set`，直接放弃
- **剔除退化尝试**：如果某一步从"能产出返回值"退化为"不能产出返回值"，认为是恶化，删掉该步
- 截取最近 `v2_query_former_trace_limit`（默认3）条

### 5.2 component_query — 相似成功经验

找到**用到相似组件的任务**，检索它们的成功实现作为参考。

检索策略（三层补充）：

1. **多组件交集**：如果任务涉及多个组件，优先找同时关联这些组件的任务（交集度越高越相关）
2. **单组件扩展**：从每个组件节点出发，找 1 步可达的其他任务描述，按配额补充
3. **Embedding 兜底**：计算当前任务与所有成功任务描述的语义相似度，补充图结构未覆盖的

找到候选任务后，从 `task_description` 沿图走最多 50 步找到对应的 `task_success_implement` 节点，反查得到代码。

**GT 比例保障**：结果中保证至少有 `v2_query_component_limit // 2 + 1` 条来自 `final_decision_based_on_gt=True` 的高质量知识（ground truth 验证过的），其余由普通知识填充。

### 5.3 error_query — 同错修复范例

找到**犯过完全相同错误并最终修复成功**的知识对。这是最精准的检索——直接告诉 LLM "别人遇到这个报错时，错误代码长什么样、改成什么样就好了"。

流程：
1. 从最近一次失败中解析出错误节点（如 `KeyError: 'close'`）
2. 如果有多个错误，找**同时关联这些错误**的 task_trace（交集检索）
3. 单错误也单独扩展
4. 从 task_trace 沿图走到 task_success_implement，取出（出错代码, 成功代码）对

返回结构是 `(错误描述, (trace_knowledge, success_knowledge))`，prompt 中会展示"曾经这样写报了这个错，后来改成那样就通过了"。

---

## 6. 知识生成：什么时候往图里写

知识不是每轮都写入图，而是在任务**成功之后**才沉淀。进行中的失败尝试暂存在内存中。

### 6.1 generate_knowledge 的流程

[evolving_agent.py#L186-L191](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L186-L191) 在每个 evo_loop 结束时调用，[knowledge_management.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py) 中的处理：

```
每个 evo_loop 结束
  │
  ├── 对每个子任务取 (task, code, feedback)，构造 CoSTEERKnowledge
  │
  ├── 任务还没成功？
  │     ├── 首次见到 → analyze_component() 用 LLM 识别相关组件
  │     ├── 追加到 working_trace_knowledge（内存临时存储）
  │     └── analyze_error() 解析错误，追加到 working_trace_error_analysis
  │
  └── 任务成功了（final_decision=True）？
        ├── 记入 success_task_to_knowledge_dict
        └── update_success_task() → 把整条轨迹写入图
              ├── 创建 task_description 节点，连接到 component
              ├── 为每步失败创建 task_trace + error 节点
              └── 创建 task_success_implement 节点
```

### 6.2 analyze_component — LLM 识别组件

[knowledge_management.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py) 把所有已知 `component` 节点的内容拼入 prompt，让 LLM 返回当前任务相关的组件编号列表（JSON `List[int]`）。

### 6.3 analyze_error — 错误解析

两种反馈类型，用正则提取结构化错误签名：

| feedback_type | 提取方式 | 示例 |
|--------------|---------|------|
| `execution` | 从 Python traceback 提取 `error_type` + `error_line` | `KeyError: 'close'\nError line: df['close']` |
| `value` | 匹配值校验错误（行数不一致、索引不一致、容差超限、相关性不足等） | `Length mismatch: expected 100, got 98` |

解析出的错误字符串会与图中已有 `error` 节点比对（0.999 embedding 阈值），相同则复用节点，不同则等任务成功后创建新节点。

---

## 7. 图的检索能力

[UndirectedGraph](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/knowledge_management/graph.py) 提供四种查询方式：

| 方法 | 作用 | 使用场景 |
|------|------|---------|
| `get_nodes_within_steps(node, steps, constraint_labels)` | BFS 找 N 步内可达节点 | 从 component 找 task_description，从 trace 找 success |
| `get_nodes_intersection(nodes, steps, constraint_labels)` | 多节点 N 步可达集合的**交集** | 多组件共同关联的任务、多错误共同出现的 trace |
| `semantic_search(node, threshold, topk)` | 基于 embedding 的**语义相似**检索 | 兜底召回，图结构未覆盖时 |
| `query_by_content(content, ...)` | 先语义搜索 topk，再对每个结果做图遍历，合并去重 | 通用内容查询入口 |

交集检索是 V2 图谱的核心优势：相比 V1 纯向量相似度，它能找到"同时满足多个结构条件"的节点。例如，一个任务用到了组件 A 和组件 B，纯语义搜索可能找到只涉及 A 的任务，但交集检索能优先找到**同时涉及 A 和 B** 的任务——后者显然更相关。

---

## 8. 持久化与多进程

| 机制 | 说明 |
|------|------|
| **graph.pkl** | 图通过 pickle 持久化到 `Path.cwd() / "graph.pkl"`，重启后可加载 |
| **dump/load** | [CoSTEERRAGStrategy](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/knowledge_management.py#L55-L99) 提供 `dump_knowledge_base()` / `load_dumped_knowledge_base()`，支持多进程共享同一知识库 |
| **文件锁** | `enable_filelock=True` 时，知识自增殖阶段加文件锁，防止多进程并发写入损坏图 |
| **多进程编码** | 因子代码生成在多个子进程中并行执行（`multi_proc_n` 控制并发数），它们共享同一份知识库快照 |

---

## 9. 配置参数

定义于 [config.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/CoSTEER/config.py)，环境变量前缀 `CoSTEER_`：

| 参数 | 默认值 | 作用 |
|------|--------|------|
| `max_loop` | 10 | evo_loop 最大轮数 |
| `fail_task_trial_limit` | 20 | 失败超过此次数标记为放弃 |
| `v2_query_former_trace_limit` | 3 | 自身历史失败轨迹返回条数 |
| `v2_query_component_limit` | 1 | 组件相似成功知识返回条数 |
| `v2_query_error_limit` | 1 | 同错修复范例返回条数 |
| `v2_add_fail_attempt_to_latest_successful_execution` | False | 是否在成功知识后附加最新一次失败尝试（防死循环） |
| `v2_knowledge_sampler` | 1.0 | 知识采样概率（<1 时随机丢弃，用于增加多样性） |
| `knowledge_base_path` | None | 知识库加载路径 |
| `new_knowledge_base_path` | None | 新知识库存放路径 |
| `enable_filelock` | False | 多进程写入时是否加文件锁 |

> 默认 `v2_query_component_limit=1`、`v2_query_error_limit=1`，即每个任务每轮最多参考 1 条相似成功经验和 1 条同错修复范例。增大这些值可以给 LLM 更多参考，但也会增加 token 消耗和 prompt 长度。

---

## 10. V1 与 V2 的区别

| 维度 | V1（已弃用） | V2（当前默认） |
|------|-------------|---------------|
| 存储结构 | 纯字典 + 向量相似度 | 无向图 + 向量索引 |
| 相似任务检索 | embedding 语义相似度 | 组件拓扑交集 + embedding 兜底 |
| 错误检索 | 无 | 错误节点交集 + 图遍历找修复对 |
| 多条件查询 | 不支持 | 交集检索（多组件/多错误） |
| 代码状态 | `raise NotImplementedError`，标注 deprecated | 完整实现 |

V1 的 `CoSTEERRAGStrategyV1` 保留在代码中仅作历史参考，实际不可用。

---

## 11. 在 evo_loop 中的位置

知识库的查询和生成嵌入在 [RAGEvoAgent.multistep_evolve()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/evolving_agent.py#L140-L198) 的每轮循环中：

```
for evo_loop_id in range(max_loop):
    with logger.tag(f"evo_loop_{evo_loop_id}"):
        │
        ├── 1. RAG 查询
        │     queried_knowledge = self.rag.query(evo, evolving_trace)
        │     ├── former_trace_query  (自己最近的失败)
        │     ├── component_query     (相似任务的成功代码)
        │     └── error_query         (同错修复范例)
        │
        ├── 2. LLM 生成/修复代码
        │     把 queried_knowledge 注入 prompt，LLM 输出修正代码
        │     （已成功的任务直接复用知识库代码，不调 LLM）
        │
        ├── 3. 运行 + 评估
        │     evolved_evo → evaluator → feedback
        │
        ├── 4. 记录反馈
        │     logger.log_object(feedback, tag="evolving feedback")
        │
        ├── 5. 知识自增殖
        │     self.rag.generate_knowledge(evolving_trace)
        │     ├── 失败：暂存 working_trace，解析错误
        │     └── 成功：写入图（task_trace + error + success 节点）
        │
        └── 6. 判断终止
              feedback.finished() → break（全部通过）
```

这就是为什么知识库能让 CoSTEER 越跑越好：每解决一个因子，它的成功路径和踩过的坑都会被图记住，下一个相似因子可以直接参考。
