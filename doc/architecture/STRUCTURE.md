# `rdagent/` 目录文件作用与功能清单

> RD-Agent 是微软开源的**自动化研发（R&D）智能体框架**，核心思想是用 LLM 驱动
> 「假设 → 实验 → 编码 → 运行 → 反馈」的闭环，当前主要落地在量化投资（Qlib）场景。
> 整个 `rdagent/` 包按职责分层，下面对每个子目录与文件进行清单式说明。
>
> 本文档基于源码整理，最后更新：2026-07-26。

---

## 目录总览

```
rdagent/
├── core/          # 核心抽象层（基类与数据结构）
├── components/    # 可复用组件库（agent / coder / workflow 等）
├── scenarios/     # 场景实现（qlib 量化 + shared 共享）
├── oai/           # LLM 集成层（统一调用与后端抽象）
├── log/           # 日志与可视化（FileStorage + Streamlit + Flask）
├── utils/         # 通用基础设施（env / workflow / agent / repo）
└── app/           # 应用入口（CLI + 各场景 RD 循环 + benchmark）
```

### 总体架构关系

```
app/ (业务入口: cli + 各场景 RDLoop)
   ↓ 基于
components/workflow/rd_loop.RDLoop (研发循环编排)
   ↓ 动态组合
components/ (proposal → coder → runner → feedback 各阶段组件)
   ↓ 实现
core/ (抽象基类: Developer / Evaluator / Experiment / EvolvingFramework)
   ↓ 依赖
scenarios/qlib/ (Qlib 具体场景: 因子 / 模型 / 联合)
   ↓ 调用
oai/ (LLM 统一调用) + utils/env.py (Docker/conda 执行) + utils/workflow/loop.py (可恢复循环引擎)
   ↓ 全程记录
log/ (FileStorage + Streamlit UI + Flask 实时服务器)
```

**核心设计**：通过 `core/` 的抽象基类与 `evolving_framework` 解耦，`components/` 提供 CoSTEER
代码进化框架等可复用积木，`scenarios/` 落地具体场景（当前为 Qlib 量化），`utils/` 提供执行环境
与循环引擎两大支柱，`oai/` 统一 LLM 调用，`log/` 服务离线/在线两种可视化，`app/` 对外暴露 CLI。

---

## 一、`core/` — 核心抽象层（约 14 个文件）

定义全框架共用的抽象基类与数据结构，所有具体场景都基于它们组合实现。

| 文件 | 作用 |
|---|---|
| `conf.py` | `ExtendedBaseSettings`：在 pydantic-settings 基础上扩展配置源（env、yaml、文件覆盖），全局单例 `RD_AGENT_SETTINGS`。 |
| `exception.py` | 自定义异常：`WorkflowError`（循环不可继续）、`FormatError` / `CodeBlockParseError`（格式/代码块解析失败）。 |
| `experiment.py` | **实验抽象核心**。`AbsTask` / `Task`、`Experiment` / `FBWorkspace`（带反馈的文件式工作区，支持 zip 打包、subprocess 执行）、`ExperimentPlan` / `ASpecificExp` 泛型，组织 RD-Agent 中所有「任务-实验」关系。 |
| `evaluation.py` | `Feedback`（dataclass 风格反馈）、`EvaluableObj`、`Evaluator` 抽象基类，定义评估接口与 `is_acceptable()` 判定。 |
| `proposal.py` | `Hypothesis`（研究假设数据类）、`HypothesisGen` / `Hypothesis2Experiment` / `ExpGenerator`（异步实验生成）、`HypothesisFB`（假设级反馈）。 |
| `scenario.py` | `Scenario` 抽象基类，定义 `background` / `get_source_data_desc` / `output_format` / `interface` 等场景信息接口。 |
| `developer.py` | `Developer(ABC, Generic[ASpecificExp])`：把实验「开发」为可运行产物的抽象基类（coder / runner 都继承它）。 |
| `interactor.py` | `Interactor(ABC)`：人机交互抽象接口，`interact()` 用于获取用户确认 / 反馈。 |
| `knowledge_base.py` | `KnowledgeBase`：基于 dill pickle 的知识库加载 / 保存基类。 |
| `prompts.py` | `Prompts`：单例式 yaml prompt 模板加载器。 |
| `evolving_framework.py` | **进化框架核心**。`Knowledge`、`EvolvableSubjects`、`EvolvingStrategy`、`EvoStep`、`IterEvaluator`、`EvoAgent`、`RAGStrategy` —— 定义「可进化主体 + 进化策略 + 迭代评估」的通用进化闭环（CoSTEER 即基于此）。 |
| `evolving_agent.py` | `EvoAgent`：基于 `EvolvingStrategy` 的进化驱动器，含 tqdm 进度、超时控制、文件锁、多步迭代 `multistep_evolve()`。 |
| `utils.py` | 核心工具：`SingletonBaseClass`、`RDAgentException`、`import_class`（动态类加载）、文件锁封装等。 |

---

## 二、`components/` — 可复用组件库

### 1. `agent/` — LLM 智能体（Pydantic-AI + MCP）

| 文件 | 作用 |
|---|---|
| `base.py` | `BaseAgent` 抽象类 + `PAIAgent`（基于 Pydantic-AI，封装 MCP Server，支持 Prefect 缓存）。 |
| `context7/conf.py` + `__init__.py` | 对接 Context7 MCP 服务（按错误查文档），`Settings` + `Agent`。 |
| `rag/conf.py` + `__init__.py` | 对接 RAG MCP 服务，`Settings` + `Agent`。 |
| `mcp/__init__.py` | MCP 子模块规范说明（每个 MCP 需含 `Settings` 与 `health_check()`）。 |

### 2. `coder/` — 代码生成与进化（CoSTEER 框架，核心）

#### `coder/CoSTEER/`（通用代码进化框架）

| 文件 | 作用 |
|---|---|
| `__init__.py` | `CoSTEER(Developer)` 主类，整合 evaluator + strategy + RAG，多轮迭代 `develop()`。 |
| `config.py` | `CoSTEERSettings`（max_loop、fail_task_trial_limit、知识库路径等）。 |
| `task.py` | `CoSTEERTask(Task)`，含 `base_code`。 |
| `evaluators.py` | `CoSTEERSingleFeedback` / `CoSTEERMultiFeedback`、`CoSTEEREvaluator` / `CoSTEERMultiEvaluator`。 |
| `evolvable_subjects.py` | `EvolvingItem` 进化中间产物。 |
| `evolving_strategy.py` | `MultiProcessEvolvingStrategy`，多进程实现 `implement_one_task()`。 |
| `knowledge_management.py` | CoSTEER 知识库 + RAG 策略（V2 基于无向图谱做组件 / 错误分析）。 |

#### `coder/factor_coder/`（因子代码生成）

| 文件 | 作用 |
|---|---|
| `__init__.py` | `FactorCoSTEER`。 |
| `factor.py` | `FactorTask` / `FactorFBWorkspace`（执行 factor.py 读 result.h5）。 |
| `config.py` | `FactorCoSTEERSettings` + `get_factor_env()`。 |
| `evaluators.py` | `FactorEvaluatorForCoder`，串联执行→值检查→代码评审→最终决策。 |
| `eva_utils.py` | 大量具体评估器：IC / rankIC、单列 / 行数 / 索引 / 缺失值 / 等值比 / 相关性 等。 |
| `evolving_strategy.py` | 因子代码多进程生成策略（JSON 模式 + python 代码块兜底解析）。 |

#### `coder/model_coder/`（模型代码生成）

| 文件 | 作用 |
|---|---|
| `__init__.py` | `ModelCoSTEER`。 |
| `model.py` | `ModelTask` / `ModelFBWorkspace`（PyTorch 模型执行工作区）。 |
| `conf.py` | `ModelCoSTEERSettings`，`env_type`（conda / docker）。 |
| `evaluators.py` | `ModelCoSTEEREvaluator`，串联 shape / value / code / final 评估。 |
| `eva_utils.py` | `shape_evaluator` / `value_evaluator` / `ModelCodeEvaluator` / `ModelFinalEvaluator`。 |
| `evolving_strategy.py` | 模型代码生成策略（动态裁剪 prompt 防超长）。 |
| `task_loader.py` | 从文档 / PDF 提取模型任务（`extract_model_from_doc` + Loader 类）。 |
| `one_shot/__init__.py` | `ModelCodeWriter`：一次性（非迭代）代码生成器。 |
| `benchmark/eval.py` | `ModelImpValEval`：通过改变输入 / 初始化参数对比 gen 与 gt 输出相关性评估。 |
| `benchmark/gt_code/*.py` | 多个 ground truth 模型（A-DGN / dirgnn / gpsconv / linkx / pmlp / visnet）。 |

### 3. `knowledge_management/` — 通用知识存储

| 文件 | 作用 |
|---|---|
| `graph.py` | `UndirectedGraph` 无向知识图谱（节点去重、BFS 邻域、语义检索、组合查询）。 |
| `vector_base.py` | `PDVectorBase`（基于 Pandas 的 cosine 向量检索）+ `Document` 分块。 |

### 4. `loader/` — 任务 / 实验加载器

| 文件 | 作用 |
|---|---|
| `task_loader.py` | `FactorTaskLoader` / `ModelTaskLoader` / `ModelTaskLoaderJson` / `ModelWsLoader`。 |
| `experiment_loader.py` | `FactorExperimentLoader` / `ModelExperimentLoader`（占位）。 |

### 5. `proposal/` — 假设与实验生成

| 文件 | 作用 |
|---|---|
| `__init__.py` | `LLMHypothesisGen`（Factor / Model / FactorAndModel 三子类）+ `LLMHypothesis2Experiment`（假设→实验转换）。 |

### 6. `runner/` — 实验运行（带缓存）

| 文件 | 作用 |
|---|---|
| `__init__.py` | `CachedRunner`，基于 md5 任务 key 缓存实验结果避免重复运行。 |

### 7. `interactor/` — 用户交互

| 文件 | 作用 |
|---|---|
| `__init__.py` | `SkipInteractor`（默认空实现，不与用户交互）。 |

### 8. `document_reader/` — 文档读取

| 文件 | 作用 |
|---|---|
| `document_reader.py` | langchain PyPDF 加载、Azure Document Intelligence OCR、PDF 首页截图。 |

### 9. `benchmark/` — 基准评估

| 文件 | 作用 |
|---|---|
| `eval_method.py` | `TestCase` / `BaseEval` / `FactorImplementEval`（5 个在线评估器 + 多进程评估 + 结果汇总）。 |
| `conf.py` | `BenchmarkSettings`（bench_data_path、test_round、method_cls）。 |
| `utils.py` | OpenCompass 数据集导入工具（避免 `import *` 序列化问题）。 |
| `configs/__init__.py` | 共享 OpenCompass 基准配置目录标记。 |

### 10. `workflow/` — 研发循环编排

| 文件 | 作用 |
|---|---|
| `rd_loop.py` | **`RDLoop`**（研发循环主控，按 PROP_SETTING 动态加载各阶段组件，含人机交互钩子、异步实验生成；循环步骤：propose → exp_gen → coding → running → feedback → record）。 |
| `conf.py` | `BasePropSetting`（RD Loop 通用配置，组件类路径动态注入，`evolving_n=10`）。 |

---

## 三、`scenarios/` — 场景实现

### `shared/` — 跨场景运行环境探测

| 文件 | 作用 |
|---|---|
| `runtime_info.py` | 可执行脚本，采集 Python 版本、OS、GPU 信息（PyTorch CUDA → nvidia-smi 回退）。 |
| `get_runtime_info.py` | `get_runtime_environment_by_env()` / `check_runtime_environment()`（注入目标环境执行 + strace / coverage 校验）。 |

### `qlib/` — Qlib 量化场景（主落地）

#### `qlib/experiment/`（实验定义与执行）

| 文件 | 作用 |
|---|---|
| `factor_experiment.py` | `QlibFactorExperiment` + `QlibFactorScenario`（含 base_features）。 |
| `model_experiment.py` | `QlibModelExperiment` + `QlibModelScenario`。 |
| `quant_experiment.py` | `QlibQuantScenario`（factor + model 联合场景）。 |
| `factor_from_report_experiment.py` | `QlibFactorFromReportScenario`（研报复现场景）。 |
| `workspace.py` | **`QlibFBWorkspace`**（注入模板 → qrun 回测 → 解析结果，支持 Docker / conda）。 |
| `utils.py` | 数据生成、文件描述、数据文件夹介绍。 |
| `factor_template/` | 因子回测模板（conf_baseline / conf_combined_factors 等 yaml + predict_infer.py + read_exp_res.py）。 |
| `model_template/` | 模型回测模板（conf_baseline_factors_model / conf_sota_factors_model + read_exp_res.py）。 |
| `factor_data_template/` | 因子数据生成模板（generate.py 调 Qlib 拉 OHLCV 落盘 h5）。 |

#### `qlib/developer/`（代码生成与运行）

| 文件 | 作用 |
|---|---|
| `factor_coder.py` | `QlibFactorCoSTEER = FactorCoSTEER`（别名复用）。 |
| `model_coder.py` | `QlibModelCoSTEER = ModelCoSTEER`（别名复用）。 |
| `factor_runner.py` | **`QlibFactorRunner`**（baseline → 因子 IC 去重 → 合并 → 回测）。 |
| `model_runner.py` | **`QlibModelRunner`**（注入 model.py + 训练超参 → 回测）。 |
| `utils.py` | 因子 DataFrame 加工（索引规范化、有效性校验、合并）。 |
| `feedback.py` | `QlibFactorExperiment2Feedback` / `QlibModelExperiment2Feedback`（对比 SOTA 关键指标 IC / 年化 / 回撤，LLM 生成假设反馈）。 |

#### `qlib/proposal/`（假设生成与实验转换）

| 文件 | 作用 |
|---|---|
| `factor_proposal.py` | `QlibFactorHypothesisGen` + `QlibFactorHypothesis2Experiment`。 |
| `model_proposal.py` | `QlibModelHypothesisGen` + `QlibModelHypothesis2Experiment`。 |
| `quant_proposal.py` | 联合主线：`QuantTrace` + `QlibQuantHypothesisGen`（按 bandit / llm / random 决定下一轮做 factor 还是 model）。 |
| `bandit.py` | `LinearThompsonTwoArm`（两臂线性 Thompson Sampling）+ `EnvController`（多臂老虎机决策器）。 |

#### `qlib/factor_experiment_loader/`（研报复现入口）

| 文件 | 作用 |
|---|---|
| `json_loader.py` | JSON / dict → `QlibFactorExperiment`（含带 ground-truth code 的测试用例加载器）。 |
| `pdf_loader.py` | 研报 PDF → 因子完整流水线（LLM 分类、因子 / 公式抽取、相关性 / 可行性判定、embedding + KMeans + LLM 去重）。 |
| `prompts.yaml` | 中文 prompt 模板（分类、抽取、判定）。 |

#### `qlib/docker/`

| 文件 | 作用 |
|---|---|
| `Dockerfile` / `requirements.lock.txt` / `qlib-src.tar.gz` / `README.md` | 构建 `local_qlib:v2.1` 标准执行镜像（基于 pytorch 2.2.1 + cuda12.1）。 |

---

## 四、`oai/` — LLM 集成层

| 文件 | 作用 |
|---|---|
| `llm_conf.py` | `LLMSettings` 全局配置（backend、模型名、温度、max_token、Azure / 各类 endpoint、缓存开关、按 tag 切换模型的 `chat_model_map`）。 |
| `llm_utils.py` | `get_api_backend()` 后端工厂（别名 `APIBackend`）+ `calculate_embedding_distance_between_str_list()`。 |
| `backend/base.py` | **抽象基类核心**：`JSONParser`（多策略 JSON 解析）、`CodeBlockParser`（代码块提取）、`SQliteLazyCache`（SQLite 持久缓存）、`SessionChatHistoryCache`、`APIBackend`（自动重试、缓存、续写、`<think>` 清理、格式校验）。 |
| `backend/litellm.py` | `LiteLLMAPIBackend`（默认实现，基于 litellm，含 token 计数、流式、成本统计、按 tag 切模型）。 |
| `backend/pydantic_ai.py` | `get_agent_model()`：LiteLLM 配置 → pydantic-ai 模型。 |
| `backend/deprec.py` | `DeprecBackend`（已废弃旧后端，支持 Azure / OpenAI / llama2 / DeepSeek / GCR 等历史调用）。 |
| `utils/embedding.py` | embedding 文本截断（三级回退获取 max_tokens + 精确截断 + 内置模型 token 上限表）。 |

---

## 五、`log/` — 日志与可视化

### 核心

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 `rdagent_logger`（`RDAgentLog` 单例）+ `LogColors`。 |
| `logger.py` | `RDAgentLog`（基于 loguru，ContextVar 线程安全 tag、按 PID 链组织、子进程重绑 stdout）。 |
| `conf.py` | `LogSettings`（trace_path、ui_server_port、storages）。 |
| `base.py` | 抽象 `Storage` / `View` + `Message` dataclass。 |
| `storage.py` | `FileStorage`（按 tag 路径 + 时间戳落盘 pkl / json / text，反向扫描 `.pkl`）。 |
| `timer.py` | `RDAgentTimer`（倒计时 / 超时 / 动态加时）+ 全局 `RD_Agent_TIMER_wrapper`。 |
| `sota_query.py` | `query_sota()`（加载 session 提取最佳实验的假设 / 反馈 / 指标 / 代码）。 |

### `utils/`

| 文件 | 作用 |
|---|---|
| `__init__.py` | `LogColors`（ANSI 颜色码）、`CallerInfo`、tag 解析工具、session 定位。 |
| `folder.py` | `get_first_session_file_after_duration()`，按累计运行时长定位 session 文件。 |

### `ui/`（Streamlit 前端）

| 文件 | 作用 |
|---|---|
| `app.py`（~1058 行） | 主 Streamlit 应用，按 loop round 渲染场景 / 指标曲线 / 假设表 / R&D Loops / 反馈 / 图表。 |
| `web.py` | `StWindow` 体系（`WebView` / `HypothesisWindow` / `WorkspaceWindow` / `TraceWindow` 等）。 |
| `storage.py` | `WebStorage`（HTTP POST 推送到 Flask 服务器）。 |
| `conf.py` | `UIBasePropSetting`（log_folders、baseline_result_path、trace_folder 等）。 |
| `llm_st.py` | LLM 调试日志查看页。 |
| `aide.py` | AIDE trace 可视化。 |
| `qlib_report_figure.py` | Qlib 回测报告 plotly 图。 |
| `st_fixed_container.py` | Streamlit 固定容器组件（sticky 布局）。 |

### `server/`（Flask 实时服务器）

| 文件 | 作用 |
|---|---|
| `app.py`（~1200+ 行） | 主 Flask 服务（性能观测中间件、`RDAgentTask`、trace 状态机、路由 `/receive` / `/trace` / `/traces` / `/upload` / `/user_interaction/submit` / `/control` / `/health`、SOTA 提取）。 |
| `debug_app.py` | 精简调试版 Flask。 |

---

## 六、`utils/` — 通用基础设施

| 文件 | 作用 |
|---|---|
| `env.py`（~1250 行，**核心**） | 环境管理：`Env` 泛型基类 + `LocalEnv` / `CondaEnv` / `QlibCondaEnv` / `DockerEnv` / `QTDockerEnv`（run / cached_run / check_output、超时、GPU 透传、镜像 build / pull）。 |
| `qlib.py` | `ALPHA20` / `ALPHA158` 标准因子表达式 + `validate_qlib_features()`。 |
| `fmt.py` | `shrink_text()` 文本折叠。 |
| `__init__.py` | `get_module_by_module_path`、`convert2bool`、`filter_redundant_text`、`md5_hash` 等。 |
| `agent/tpl.py` | **`RDAT` / `T`**：基于 Jinja2 的模板系统（相对 / 绝对 URI、include、StrictUndefined、debug 记录）。 |
| `agent/ret.py` | `AgentOut` 输出规范（`PythonAgentOut` / `MarkdownAgentOut` / `BatchEditOut` / `PythonBatchPatchOut`）。 |
| `agent/apply_patch.py` | 纯 Python「伪 diff」补丁解析与应用（改自 OpenAI cookbook）。 |
| `agent/workflow.py` | `build_cls_from_json_with_retry()`：LLM 生成 JSON + 重试实例化类。 |
| `agent/__init__.py` | 导出 `build_cls_from_json_with_retry`。 |
| `repo/diff.py` | 目录 / dict diff 生成。 |
| `repo/repo_utils.py` | `RepoAnalyzer`：基于 AST 的代码仓库自然语言摘要。 |
| `workflow/loop.py`（**核心**） | `LoopBase`：可序列化 / 恢复的工作流循环引擎（asyncio.Queue 驱动 step 链、续跑、并发信号量、session dump / load）。 |
| `workflow/__init__.py` | 导出 `LoopBase` / `LoopMeta` / `WorkflowTracker` / `wait_retry`。 |
| `workflow/tracking.py` | `WorkflowTracker`（可选 MLflow 指标追踪）。 |
| `workflow/misc.py` | `wait_retry` 重试装饰器。 |

---

## 七、`app/` — 应用入口

### 顶层

| 文件 | 作用 |
|---|---|
| `cli.py` | 统一 typer CLI 入口：`fin_factor` / `fin_model` / `fin_quant` / `fin_factor_report` / `ui` / `server_ui` / `health_check` / `collect_info` / `sota`。 |

### `qlib_rd_loop/`（Qlib 金融 RD 循环）

| 文件 | 作用 |
|---|---|
| `conf.py` | `FactorBasePropSetting` / `ModelBasePropSetting` / `QuantBasePropSetting` / `FactorFromReportPropSetting`（组件类路径 + 时间段 + model_selector）。 |
| `factor.py` | `FactorRDLoop`（重写 running 步骤，支持新建 / 续跑 session、auto_mode）。 |
| `model.py` | `ModelRDLoop`，针对模型场景。 |
| `quant.py` | `QuantRDLoop`（factor + model 双路径，bandit / llm / random 选择 action，ALPHA20 初始特征）。 |
| `factor_from_report.py` | `FactorReportLoop`（从研报 PDF 提取因子）。 |
| `predict.py` | T+1 预测入口（SOTA 因子 → QTDockerEnv → Top20 JSON 推前端）。 |

### `benchmark/`

| 文件 | 作用 |
|---|---|
| `factor/eval.py` | 因子基准评估入口（读 JSON 测试用例 → `FactorImplementEval`）。 |
| `factor/analysis.py` | `BenchmarkAnalyzer`（按 Category / Difficulty 分组分析与可视化）。 |
| `model/eval.py` | 模型基准评估（model_dict.json → ModelCoSTEER → ModelImpValEval）。 |

### `CI/`

| 文件 | 作用 |
|---|---|
| `run.py` | CI 自动修复循环（tree_sitter 解析 + ruff / mypy 检查 + 演进框架修复）。 |

### `utils/`

| 文件 | 作用 |
|---|---|
| `health_check.py` | `check_docker_status()` / `is_port_in_use()` / `check_and_list_free_ports()`。 |
| `info.py` | `collect_info()`（OS / CPU / Python / Docker / 依赖版本）。 |
| `ape.py` | 自动化 Prompt Engineering（APE）初版（从 debug_llm.pkl 读 LLM QA 历史）。 |

---

## 附：关键数据流（一次 RD 循环）

1. **`proposal`**：由 trace 驱动生成 `Hypothesis`，转换为 `QlibFactorExperiment` / `QlibModelExperiment`。
2. **`coding`（`developer/*_coder`）**：生成因子 / 模型代码。
3. **`running`（`developer/*_runner`）**：在 `experiment/workspace.QlibFBWorkspace` 中通过 Docker / conda 跑 Qlib 回测得到结果。
4. **`feedback`（`developer/feedback`）**：把结果与 SOTA 对比，调用 LLM 产出 `HypothesisFeedback`，写回 trace 进入下一轮。
5. **辅助**：`experiment/utils` 与 `developer/utils` 负责数据生成与因子 DataFrame 加工；`factor_experiment_loader` 提供「从研报 / PDF / JSON 启动研发」的入口；`shared/` 提供跨场景的运行环境探测能力。
