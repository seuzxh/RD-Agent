# 研报复现场景（Factor from Report）

> 从券商/学术 PDF 研报中自动提取因子公式和变量定义，由 CoSTEER 编码实现并回测验证。绕过 HypothesisGen，创意来源是研报内容而非 LLM 自主探索。

---

## 1. 场景概述

研报复现场景的目标是将量化研报中的文字描述和数学公式自动转化为可运行的因子代码并验证效果。与因子挖掘场景不同，**因子的创意来自研报而非 LLM 自主生成**，系统负责从 PDF 中理解、提取、实现和验证。

**核心特点**：
- 📄 **PDF 输入**：支持单文件或文件夹批量处理 PDF 研报
- 🔍 **多阶段 NLP 管道**：分类→因子名提取→公式提取→可行性检查→去重
- 🚫 **绕过 HypothesisGen/H2E**：直接从 PDF 构建 Experiment，不经过 LLM 假设生成
- 🤖 **事后假设生成**：提取因子后 LLM 生成描述性假设（用于 trace 记录）
- 📦 **每轮一份研报**：循环轮次=研报数量（受 report_limit 限制）
- 🧹 **自动跳过无效报告**：非量化研报或无法提取因子的报告自动跳过

---

## 2. 启动方式

```bash
# 默认：从 git_ignore_folder/report_list.json 加载PDF路径列表
dotenv run -- python rdagent/app/qlib_rd_loop/factor_from_report.py

# 指定包含PDF的文件夹（自动扫描*.pdf）
dotenv run -- python rdagent/app/qlib_rd_loop/factor_from_report.py --report_folder ./reports/

# 限制处理的研报数量
QLIB_FACTOR_REPORT_LIMIT=10 dotenv run -- python rdagent/app/qlib_rd_loop/factor_from_report.py --report_folder ./reports/

# 从断点恢复
dotenv run -- python rdagent/app/qlib_rd_loop/factor_from_report.py $LOG_PATH/__session__/0/0_propose
```

### CLI 参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `path` | str | None | 断点恢复路径 |
| `report_folder` | str | None | PDF 文件夹路径（与默认 JSON 二选一） |
| `all_duration` | str | None | 最大运行时长 |
| `checkout` | bool | True | 恢复时是否截断后续记录 |

> ⚠️ 注意：研报场景的 `main()` 不接受 `loop_n`/`step_n` 参数（与因子/模型/全流程场景不同）。循环份数由构造函数中的 `min(len(pdfs), QLIB_FACTOR_REPORT_LIMIT)` 固定。

---

## 3. 配置

环境变量前缀：**`QLIB_FACTOR_`**（继承自 FactorBasePropSetting）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `QLIB_FACTOR_SCEN` | QlibFactorFromReportScenario | 场景类（不同于纯因子） |
| `QLIB_FACTOR_CODER` | QlibFactorCoSTEER | 复用因子编码进化 |
| `QLIB_FACTOR_RUNNER` | QlibFactorRunner | 复用因子回测 |
| `QLIB_FACTOR_SUMMARIZER` | QlibFactorExperiment2Feedback | 复用因子反馈 |
| `QLIB_FACTOR_REPORT_RESULT_JSON_FILE_PATH` | `git_ignore_folder/report_list.json` | PDF路径列表JSON |
| `QLIB_FACTOR_MAX_FACTORS_PER_EXP` | 6 | 每份研报最多实现因子数 |
| `QLIB_FACTOR_REPORT_LIMIT` | 20 | 最多处理研报份数 |
| `QLIB_FACTOR_EVOLVING_N` | 10 | CoSTEER 内部迭代轮数 |

### report_list.json 格式

```json
[
  "/absolute/path/to/report1.pdf",
  "/absolute/path/to/report2.pdf",
  "/absolute/path/to/report3.pdf"
]
```

---

## 4. 与因子挖掘场景的核心差异

| 方面 | 因子挖掘 (Factor) | 研报复现 (Report) |
|------|-----------------|------------------|
| **创意来源** | LLM 自主生成假设 | PDF 研报内容 |
| **HypothesisGen** | ✅ 每轮调用 | ❌ 绕过（仅事后生成描述） |
| **H2E (假设→实验)** | ✅ LLM 转化为 FactorTask | ❌ PDF Loader 直接构建 Experiment |
| **direct_exp_gen 返回值** | `{"propose": hypo, "exp_gen": exp}` | 直接返回 `exp`（Experiment 对象） |
| **coding 参数** | `prev_out["direct_exp_gen"]["exp_gen"]` | `prev_out["direct_exp_gen"]`（直接取） |
| **循环终止** | loop_n 轮或超时 | `min(len(pdfs), report_limit)` 份研报 |
| **循环控制变量** | loop_idx 递增 | loop_idx + shift_report（跳过无效报告） |
| **场景类** | QlibFactorScenario | QlibFactorFromReportScenario |
| **预处理** | 无 | PDF分类、因子提取、公式提取、可行性检查 |
| **CoSTEER 输入** | LLM 生成的因子任务（可能模糊） | 研报提取的因子任务（有明确公式和变量） |

---

## 5. PDF 处理管道

研报复现的核心是一个多阶段的 NLP 管道，将 PDF 文件转化为结构化的 Experiment 对象：

```
PDF文件
  │
  ├─① load_and_process_pdfs_by_langchain()
  │     PyPDFLoader/PyPDFDirectoryLoader → 全文文本(dict[path, text])
  │
  ├─② classify_report_from_dict()
  │     LLM分类：是否为有用的量化/金工研报（vote_time=1，单次判断）
  │     → selected_report_dict（过滤掉非量化报告）
  │
  ├─③ extract_factors_from_report_dict() [多进程]
  │     对每份有用研报并行处理：
  │     ├─③a __extract_factors_name_and_desc_from_content()
  │     │     LLM多轮对话（最多10轮）→ {因子名: 因子描述}
  │     └─③b __extract_factors_formulation_from_content()
  │           LLM多轮对话（最多10轮）→ {因子名: {formulation, variables}}
  │     → file_to_factor_result (dict[path, factor_dict])
  │
  ├─④ merge_file_to_factor_dict_to_factor_dict()
  │     跨报告合并：同名因子取公式最长的版本
  │     → factor_dict (合并后的大字典)
  │
  ├─⑤ check_factor_viability() [多进程]
  │     LLM判断每个因子是否可代码实现（按每批50个切分传给LLM，
  │     多进程由 RD_AGENT_SETTINGS.multi_proc_n 控制）
  │     → filtered_factor_dict（过滤掉不可实现的）
  │
  ├─⑥ FactorExperimentLoaderFromDict().load()
  │     将因子字典转为 QlibFactorExperiment（含 FactorTask 列表）
  │
  └─⑦ generate_hypothesis() [事后]
        LLM基于因子结果+报告全文生成Hypothesis对象
        → exp.hypothesis = hypothesis
```

### 5.1 研报分类（classify_report_from_dict）

系统提示词指导 LLM 判断每份报告是否包含可实现的量化因子。当前调用传入 `vote_time=1`（单次分类判断）；代码支持多次投票取多数（`vote_time` 参数），但当前 `FactorExperimentLoaderFromPDFfiles.load()` 中实际传 1。内容超过 token 限制时自动截断。

### 5.2 因子名称与描述提取

使用多轮对话 chat session 持续追问，直到提取完所有因子。LLM 被要求从研报文字中识别出明确描述的因子，输出结构化的因子名和描述。

### 5.3 因子公式与变量提取

基于已提取的因子名和描述，进一步追问数学公式（LaTeX格式）和变量定义。这是关键步骤——公式和变量直接传递给 CoSTEER 作为编码依据，精度直接影响代码生成质量。

### 5.4 跨报告去重

多份研报可能描述相同因子（同名或同义），`merge_file_to_factor_dict_to_factor_dict` 以因子名为主键合并，同名因子取**公式描述最长**的版本（通常意味着更详细）。

### 5.5 可行性检查

`check_factor_viability()` 让 LLM 判断因子是否可以用代码实现，过滤掉：
- 依赖非公开数据的因子
- 描述过于模糊无法编码的因子
- 需要另类数据（如新闻情绪、卫星图像）但系统无法获取的因子

### 5.6 未启用的步骤

以下函数在代码中存在但**当前未在 NLP 管道中被调用**：
- `check_factor_relevance()`：因子相关性检查（函数定义于 [pdf_loader.py:281](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L281)，但管道中无调用）
- `deduplicate_factors_by_llm()`：基于 KMeans 聚类 + LLM 判断的语义去重（其调用在 [pdf_loader.py:587](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L587) 被注释）

---

## 6. 完整工作流程

```
┌─────────────────────────────────────────────────────────────────┐
│               FactorReportLoop 主循环                            │
│                                                                 │
│  [初始化]                                                       │
│  ├─ 加载judge_pdf_data_items:                                   │
│  │   ├─ 有report_folder → 扫描*.pdf文件                         │
│  │   └─ 默认 → 从report_list.json加载路径数组                    │
│  ├─ loop_n = min(len(pdfs), report_limit=20)                   │
│  ├─ shift_report = 0（无效报告跳过时递增）                        │
│  └─ plan = {features: ALPHA20}                                  │
│                                                                 │
│  ┌─── Loop N (处理第 N+shift_report 份研报) ─────────────────┐  │
│  │                                                           │  │
│  │  ① direct_exp_gen() [重写]                                │  │
│  │  ├─ 等待并行槽位                                          │  │
│  │  ├─ pdf_path = judge_pdf_data_items[loop_idx+shift_report]│  │
│  │  ├─ extract_hypothesis_and_exp_from_reports(pdf_path):    │  │
│  │  │   ├─ FactorExperimentLoaderFromPDFfiles.load(pdf_path) │  │
│  │  │   │   (上述6阶段NLP管道)                                │  │
│  │  │   ├─ 如果exp为空或无sub_tasks：                         │  │
│  │  │   │   shift_report+=1, loop_n-=1, continue             │  │
│  │  │   ├─ extract_first_page_screenshot_from_pdf() 首页截图 │  │
│  │  │   ├─ generate_hypothesis(factor_result, report_content)│  │
│  │  │   │   LLM事后生成Hypothesis对象（函数注解标str但实际  │  │
│  │  │   │   返回Hypothesis）                                  │  │
│  │  │   └─ exp.hypothesis = hypothesis                       │  │
│  │  ├─ 截断因子数: sub_tasks[:max_factors_per_exp=6]         │  │
│  │  ├─ 设置based_experiments:                                 │  │
│  │  │   空基线实验 + [t[0] for t in trace.hist if t[1]]      │  │
│  │  │   (t[1]为feedback对象，truthy意味着feedback非None；    │  │
│  │  │    异常轮feedback也可能存在但decision=False)           │  │
│  │  ├─ 设置base_features = ALPHA20                           │  │
│  │  └─ 返回exp (直接返回Experiment对象，不是dict)             │  │
│  │                                                           │  │
│  │  ② coding() [重写，适配返回值差异]                         │  │
│  │  └─ self.coder.develop(prev_out["direct_exp_gen"])        │  │
│  │      （注意：不是prev_out["direct_exp_gen"]["exp_gen"]）   │  │
│  │      QlibFactorCoSTEER 为每个因子生成代码（多轮进化）       │  │
│  │                                                           │  │
│  │  ③ running() [继承FactorRDLoop]                           │  │
│  │  └─ QlibFactorRunner.develop(exp):                        │  │
│  │      SOTA因子+新因子→去重→组合→Docker回测→指标             │  │
│  │      失败→FactorEmptyError→跳过                            │  │
│  │                                                           │  │
│  │  ④ feedback() [继承RDLoop]                                │  │
│  │  └─ QlibFactorExperiment2Feedback.generate_feedback()     │  │
│  │      （与因子挖掘相同，对比SOTA判断是否更新）                │  │
│  │                                                           │  │
│  │  ⑤ record() [继承RDLoop]                                  │  │
│  │  └─ trace.sync_dag_parent_and_hist((exp, feedback))       │  │
│  │                                                           │  │
│  └─── 下一份研报 ────────────────────────────────────────────┘  │
│                                                                 │
│  终止条件: loop_n < 0 (所有有效报告处理完毕) 或 超时              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 关键机制

### 7.1 无效报告跳过（shift_report）

不是所有 PDF 都是有用的量化研报。如果某份报告：
- 被分类器判定为非量化报告
- 提取后因子列表为空
- 所有因子都被可行性检查过滤

则 `shift_report += 1`，`loop_n -= 1`，自动跳过该报告处理下一份，不会中断整体流程。

### 7.2 因子数量上限

每份研报最多实现 `max_factors_per_exp=6` 个因子。截断发生在 `direct_exp_gen` 返回前：
```python
exp.sub_workspace_list = exp.sub_workspace_list[:max_factors_per_exp]
exp.sub_tasks = exp.sub_tasks[:max_factors_per_exp]
```

### 7.3 多进程并行提取

PDF 文本提取和因子提取使用 `multiprocessing_wrapper` 并行处理多份研报，进程数由 `RD_AGENT_SETTINGS.multi_proc_n` 控制。

### 7.4 based_experiments 链

研报场景的 `based_experiments` 包含：
1. 一个空基线 `QlibFactorExperiment(sub_tasks=[], hypothesis=exp.hypothesis)`
2. 所有历史实验 `[t[0] for t in self.trace.hist if t[1]]`

注意 `t[1]` 是 feedback 对象，`if t[1]` 是 truthy 判断（即 feedback 非 `None`），并不严格等于 `feedback.decision=True`。异常轮也会生成 decision=False 的 feedback 进入该列表。这使得 CoSTEER 可以参考之前研报中实现的因子代码作为范例，Runner 也能将之前研报的成功因子合并入 SOTA 库。

---

## 8. 加载器继承体系

```
Loader(ABC)                              # rdagent/core/experiment.py
  └── FactorExperimentLoader             # rdagent/components/loader/experiment_loader.py
        ├── FactorExperimentLoaderFromPDFfiles  ← 研报场景使用
        ├── FactorExperimentLoaderFromDict      ← PDF管道最后一步使用
        ├── FactorExperimentLoaderFromJsonFile
        └── FactorExperimentLoaderFromJsonString
```

`FactorExperimentLoaderFromPDFfiles.load(file_or_folder_path)` 是研报场景的入口加载器，内部完成从 PDF 路径到 Experiment 对象的完整转换。

---

## 9. 关键代码索引

| 模块 | 文件路径 |
|------|----------|
| 入口/主循环 | [rdagent/app/qlib_rd_loop/factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py) |
| 配置类 | [rdagent/app/qlib_rd_loop/conf.py#L130-L143](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py#L130-L143) |
| PDF加载器(NLP管道) | [rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py) |
| 字典加载器 | [rdagent/scenarios/qlib/factor_experiment_loader/json_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/json_loader.py) |
| 研报场景定义 | [rdagent/scenarios/qlib/experiment/factor_from_report_experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_from_report_experiment.py) |
| PDF文档读取 | [rdagent/components/document_reader/document_reader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/document_reader/document_reader.py) |
| CoSTEER/Runner/Summarizer | 复用因子场景组件（参见 [01-factor.md](01-factor.md)） |
