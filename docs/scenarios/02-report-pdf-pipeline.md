# PDF 上传与因子识别流程详解

> 本文档深入讲解研报复现场景中，从 PDF 文件上传到因子任务生成的完整技术管道。适用于想理解 NLP 提取细节、调试提取效果或扩展 PDF 处理能力的开发者。

---

## 1. 两种入口方式

### 1.1 WebUI 上传

用户在浏览器中选择场景 **"Finance Data Building (Reports)"**，拖拽或选择一个或多个 PDF 文件后点击启动。

**前端 → 后端交互**：

```
浏览器 (POST /upload, multipart/form-data)
  ├─ scenario: "Finance Data Building (Reports)"
  ├─ files[]: report1.pdf, report2.pdf, ...
  ├─ loops: (可选，研报场景实际忽略此参数)
  └─ all_duration: (可选，最大运行时长)
        │
        ▼
Flask 后端 upload_file() [app.py:938]
  ├─ 生成随机 trace_name（如 "happy-tiger"）
  ├─ 文件保存到: <log_folder>/uploads/<scenario>/<trace_name>/*.pdf
  ├─ 文件名经过 secure_filename() 消毒，防路径穿越
  ├─ 并发限制检查（上限 max_concurrent_tasks=10）
  ├─ 构造 kwargs = {"report_folder": "<uploads路径>", "all_duration": ...}
  └─ 启动 RDAgentTask 子进程 → rdagent fin_factor_report --report_folder <路径>
```

关键代码：[app.py#L938-L1071](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py#L938-L1071)

> 💡 WebUI 上传时 `loop_n` 参数不生效——研报场景的循环份数由 PDF 文件数量自动决定。

### 1.2 CLI 启动

```bash
# 方式一：指定 PDF 文件夹
dotenv run -- python rdagent/app/qlib_rd_loop/factor_from_report.py \
    --report_folder ./my_reports/

# 方式二：使用默认 JSON 列表
# 在 git_ignore_folder/report_list.json 中放置 PDF 绝对路径数组
dotenv run -- python rdagent/app/qlib_rd_loop/factor_from_report.py
```

或通过统一 CLI：

```bash
rdagent fin_factor_report --report_folder ./my_reports/
```

关键代码：
- 入口函数：[factor_from_report.py#L146-L162](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py#L146-L162)
- CLI 注册：[cli.py#L99-L108](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/cli.py#L99-L108)

### 1.3 PDF 文件发现

构造 `FactorReportLoop` 时，根据入口方式收集 PDF 列表：

```python
if report_folder is None:
    # 默认模式：从 JSON 文件读取路径列表
    self.judge_pdf_data_items = json.load(
        open(FACTOR_FROM_REPORT_PROP_SETTING.report_result_json_file_path)
    )
else:
    # 文件夹模式：递归扫描 *.pdf
    self.judge_pdf_data_items = [i for i in Path(report_folder).rglob("*.pdf")]

self.loop_n = min(len(self.judge_pdf_data_items), report_limit)  # 默认上限 20
self.shift_report = 0
```

关键代码：[factor_from_report.py#L96-L110](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py#L96-L110)

---

## 2. PDF 文本提取

### 2.1 默认提取器：LangChain + PyPDF

`load_and_process_pdfs_by_langchain()` 是默认的 PDF 文本提取入口，支持单文件和文件夹：

```python
def load_documents_by_langchain(path: str) -> list:
    if Path(path).is_dir():
        loader = PyPDFDirectoryLoader(path, silent_errors=True)
    else:
        loader = PyPDFLoader(path)
    return loader.load()
```

返回 `Document` 对象列表后，按文件路径聚合成 `dict[文件绝对路径, 全文文本]`：

```python
def process_documents_by_langchain(docs) -> dict[str, str]:
    content_dict = {}
    for doc in docs:
        doc_name = str(Path(doc.metadata["source"]).resolve())
        if doc_name not in content_dict:
            content_dict[doc_name] = doc.page_content
        else:
            content_dict[doc_name] += doc.page_content
    return content_dict
```

关键代码：[document_reader.py#L20-L64](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/document_reader/document_reader.py#L20-L64)

**特点**：
- 基于 `pypdf` 纯 Python 解析，无需外部服务
- 多页 PDF 的文本按页拼接
- `silent_errors=True`：损坏页面不中断，跳过继续
- 文本质量取决于 PDF 本身——扫描版 PDF 提取效果差

### 2.2 备选：Azure Document Intelligence

对于扫描版或排版复杂的 PDF，代码内置了 Azure 文档智能服务的提取器：

```python
def load_and_process_one_pdf_by_azure_document_intelligence(path, key, endpoint):
    pages = len(PyPDFLoader(str(path)).load())
    client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key))
    with path.open("rb") as file:
        result = client.begin_analyze_document("prebuilt-document", file, pages=f"1-{pages}").result()
    return result.content
```

需要配置环境变量：
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`

关键代码：[document_reader.py#L67-L109](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/document_reader/document_reader.py#L67-L109)

> ⚠️ Azure 提取器虽然代码存在，但**当前 NLP 管道默认使用 LangChain/PyPDF 路径**。如需切换为 Azure，需修改 `FactorExperimentLoaderFromPDFfiles.load()` 中的调用。

### 2.3 首页截图

每份研报处理时，会额外截取 PDF 首页作为图片，记录到日志供前端展示：

```python
def extract_first_page_screenshot_from_pdf(pdf_path: str) -> Image:
    doc = fitz.open(pdf_path)          # PyMuPDF
    page = doc.load_page(0)
    pix = page.get_pixmap()
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
```

截图通过 `logger.log_object(pdf_screenshot, tag="load_pdf_screenshot")` 记录，WebStorage 特殊处理 `load_pdf_screenshot` 标签，将图片保存为 JPEG 并发送 `research.pdf_image` 消息到前端。

关键代码：
- 截图函数：[document_reader.py#L112-L121](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/document_reader/document_reader.py#L112-L121)
- 前端消息处理：[storage.py#L96-L106](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/storage.py#L96-L106)

---

## 3. NLP 因子识别管道

这是研报复现的核心。`FactorExperimentLoaderFromPDFfiles.load()` 编排了一个六阶段管道，将 PDF 文本转化为结构化的因子任务：

```
PDF 文本(dict[path, text])
  │
  ├─ ① classify_report_from_dict()        研报分类（是否有用）
  ├─ ② extract_factors_from_report_dict()  并行提取因子名+描述+公式
  ├─ ③ merge_file_to_factor_dict_to_factor_dict()  跨报告合并
  ├─ ④ check_factor_viability()            可行性过滤
  ├─ ⑤ FactorExperimentLoaderFromDict()    构建 Experiment 对象
  └─ ⑥ generate_hypothesis()               事后生成假设
```

关键代码：[pdf_loader.py#L581-L603](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L581-L603)

### 3.1 阶段一：研报分类

LLM 判断每份 PDF 是否为**包含可实现量化因子的金工研报**。

```python
def classify_report_from_dict(report_dict, vote_time=1):
    for key, value in report_dict.items():
        # 内容超长时自动截断（从尾部按比例裁剪）
        while token_count(content) > chat_token_limit:
            content = content[: -(chat_token_limit // 100)]

        # LLM 分类
        res = APIBackend().build_messages_and_create_chat_completion(
            system_prompt=T(".prompts:classify_system").r(),
            user_prompt=content,
            json_mode=True,
        )
        res_dict[key] = {"class": int(json.loads(res)["class"])}
```

分类提示词要求 LLM 同时检查三个条件：
1. 文档属于金融领域（非生物/物理/化学等）
2. 是选股方向（非择时、选基）
3. 涉及因子/模型的构成或表现测试

三个条件全满足返回 `{"class": 1}`，否则返回 `{"class": 0}`。

关键代码：[pdf_loader.py#L29-L112](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L29-L112)

**投票机制**：`vote_time` 参数支持多次投票取多数（超过半数即停止），但当前管道固定传 `vote_time=1`，即单次判断。

### 3.2 阶段二：因子名称与描述提取

对分类为"有用"的研报，使用**多轮对话**逐步提取所有因子名称和描述。

```python
def __extract_factors_name_and_desc_from_content(content):
    session = APIBackend().build_chat_session(
        session_system_prompt=T(".prompts:extract_factors_system").r()
    )
    extracted = {}
    current_prompt = content

    for _ in range(10):                          # 最多 10 轮追问
        resp = session.build_chat_completion(
            user_prompt=current_prompt,
            json_mode=True,
        )
        ret = json.loads(resp)
        factors = ret.get("factors", {})
        if not factors:                          # 无新因子时停止
            break
        extracted.update(factors)
        current_prompt = T(".prompts:extract_factors_follow_user").r()  # 追问提示

    return extracted
```

**System Prompt 要点**（[prompts.yaml#L1-L20](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L1-L20)）：
- 概述研报主要研究思路
- 抽取所有因子，概述计算过程（注意表格中的因子不要遗漏）
- 因子名使用英文、无空格、下划线连接
- 同时抽取模型信息（但研报场景主要关注因子）
- 输出 JSON schema：`{"summary": "...", "factors": {name: desc}, "models": {}}`

**追问 Prompt**（[prompts.yaml#L22-L31](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L22-L31)）：
- 要求继续提取，忽略已出现的因子
- 提醒不要遗漏（因子可能在研报中多次出现）
- 无因子时返回空字典

### 3.3 阶段三：因子公式与变量提取

在获得因子名称和描述后，第二轮 LLM 对话提取每个因子的**数学公式（LaTeX 格式）和变量定义**：

```python
def __extract_factors_formulation_from_content(content, factor_dict):
    factor_df = pd.DataFrame(factor_dict.items(), columns=["factor_name", "factor_description"])

    for _ in range(10):
        resp = session.build_chat_completion(
            user_prompt=T(".prompts:extract_factor_formulation_user").r(
                report_content=content,
                factor_dict=factor_df.to_string(),
            ),
            json_mode=True,
        )
        ret = json.loads(resp)
        for name, data in ret.items():
            if name in factor_dict:
                factor_to_formulation[name] = data

        if len(factor_to_formulation) == len(factor_dict):
            break  # 所有因子公式已提取
        # 有遗漏时，发送剩余因子列表继续追问
```

**System Prompt 要点**（[prompts.yaml#L33-L64](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L33-L64)）：
- 每个因子给出 LaTeX 格式计算公式
- 变量名不含空格，用下划线连接
- 提供变量和函数的英文解释
- 基于四类可用数据源扩展公式：
  1. 股票交易数据（开高低收/VWAP/成交量/换手率）
  2. 财务数据（资产负债表/利润表/现金流量表）
  3. 股票基本面数据（总股本/流通股本/行业/市场分类）
  4. 高频数据（分钟级开高低收/量/VWAP）
- 注意 JSON 中的反斜杠和下划线转义

输出 schema：
```json
{
  "factor_name": {
    "formulation": "LaTeX formula...",
    "variables": {
      "var_name": "variable description",
      "func_name": "function description"
    }
  }
}
```

### 3.4 公式后处理：下划线转义

提取到公式后，代码会对公式中的下划线做 LaTeX 转义处理，防止因子名和变量名中的 `_` 被 Markdown/LaTeX 解析为下标：

```python
formulation = factor_to_formulation[factor_name]["formulation"]
if factor_name in formulation:
    formulation = formulation.replace(factor_name, factor_name.replace("_", r"\_"))
for variable in factor_to_formulation[factor_name]["variables"]:
    if variable in formulation:
        formulation = formulation.replace(variable, variable.replace("_", r"\_"))
```

关键代码：[pdf_loader.py#L178-L184](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L178-L184)

### 3.5 阶段四：跨报告合并

多份研报可能描述相同因子。`merge_file_to_factor_dict_to_factor_dict()` 以因子名为键合并：

```python
def merge_file_to_factor_dict_to_factor_dict(file_to_factor_dict):
    factor_dict = {}
    for file_name in file_to_factor_dict:
        for factor_name in file_to_factor_dict[file_name]:
            factor_dict.setdefault(factor_name, []).append(
                file_to_factor_dict[file_name][factor_name]
            )

    # 同名因子取公式描述最长的版本（通常更详细）
    result = {}
    for factor_name, versions in factor_dict.items():
        if len(versions) > 1:
            result[factor_name] = max(versions, key=lambda x: len(x["formulation"]))
        else:
            result[factor_name] = versions[0]
    return result
```

关键代码：[pdf_loader.py#L254-L277](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L254-L277)

> 💡 这是基于**因子名精确匹配**的简单去重。更复杂的语义去重（KMeans 聚类 + LLM 判断）函数 `deduplicate_factors_by_llm()` 已实现但当前被注释未启用。

### 3.6 阶段五：可行性检查

LLM 逐一判断因子是否可以用代码实现，过滤掉不可行的因子：

```python
def check_factor_viability(factor_dict):
    factor_df = pd.DataFrame(factor_dict).T

    while factor_df.shape[0] > 0:
        # 每批 50 个因子，多进程并行调用 LLM
        batches = [factor_df.iloc[i:i+50] for i in range(0, len(factor_df), 50)]
        results = multiprocessing_wrapper(
            [(__check_viability, (batch.to_string(),)) for batch in batches],
            n=RD_AGENT_SETTINGS.multi_proc_n,
        )
        # 收集结果，未覆盖的因子进入下一轮
        ...

    filtered = {name: data for name, data in factor_dict.items()
                if viability_dict[name]["viability"]}
    return viability_dict, filtered
```

**可行性标准**（[prompts.yaml#L98-L144](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml#L98-L144)）：
1. 能以**日频**计算
2. 能按**个股**计算
3. 能基于提供的五类数据源计算（量价/财务/基本面/高频/一致预期）

不可行的典型情况：
- 需要非公开数据（如另类数据、卫星图像、新闻情绪）
- 频率不匹配（如需要 Tick 级但只有日线）
- 描述过于主观或模糊，无法转化为代码

输出 schema：
```json
{
  "factor_name": {
    "viability": true,
    "reason": "This factor can be calculated using daily close prices..."
  }
}
```

关键代码：[pdf_loader.py#L327-L369](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py#L327-L369)

### 3.7 多进程并行

因子提取和可行性检查阶段使用 `multiprocessing_wrapper` 并行处理：

```python
factor_dict_list = multiprocessing_wrapper(
    [(__extract_factor_and_formulation_from_one_report, (content,))
     for content in useful_reports.values()],
    n=RD_AGENT_SETTINGS.multi_proc_n,    # 默认 11
)
```

进程数由 `RD_AGENT_SETTINGS.multi_proc_n` 控制（默认 11），可在 `.env` 中通过 `RD_AGENT_MULTI_PROC_N` 调整。

---

## 4. 构建 Experiment 对象

通过可行性过滤后，因子字典被转换为 `QlibFactorExperiment`：

```python
class FactorExperimentLoaderFromDict(FactorExperimentLoader):
    def load(self, factor_dict: dict) -> QlibFactorExperiment:
        tasks = []
        for factor_name, data in factor_dict.items():
            task = FactorTask(
                factor_name=factor_name,
                factor_description=data["description"],
                factor_formulation=data["formulation"],
                variables=data["variables"],
            )
            tasks.append(task)
        return QlibFactorExperiment(sub_tasks=tasks)
```

每个 `FactorTask` 包含四个核心字段：

| 字段 | 类型 | 来源 | 用途 |
|------|------|------|------|
| `factor_name` | str | LLM 提取 | 因子标识符，英文下划线命名 |
| `factor_description` | str | LLM 提取 | 因子的自然语言描述 |
| `factor_formulation` | str | LLM 提取 | LaTeX 数学公式，CoSTEER 编码的核心依据 |
| `variables` | dict | LLM 提取 | 公式中变量/函数的解释 |

关键代码：[json_loader.py#L15-L28](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/json_loader.py#L15-L28)

---

## 5. 事后假设生成

研报场景**不经过 HypothesisGen**，但为了 trace 记录和前端展示，会在因子提取完成后由 LLM 生成一个描述性的 Hypothesis：

```python
def extract_hypothesis_and_exp_from_reports(report_file_path):
    # 1. NLP 管道提取因子
    exp = FactorExperimentLoaderFromPDFfiles().load(report_file_path)
    if exp is None or exp.sub_tasks == []:
        return None

    # 2. 首页截图
    pdf_screenshot = extract_first_page_screenshot_from_pdf(report_file_path)
    logger.log_object(pdf_screenshot, tag="load_pdf_screenshot")

    # 3. 重新加载全文（用于假设生成的上下文）
    docs_dict = load_and_process_pdfs_by_langchain(report_file_path)
    report_content = "\n".join(docs_dict.values())

    # 4. 构造因子结果摘要
    factor_result = {
        task.factor_name: {
            "description": task.factor_description,
            "formulation": task.factor_formulation,
            "variables": task.variables,
            "resources": task.factor_resources,
        }
        for task in exp.sub_tasks
    }

    # 5. LLM 生成假设
    exp.hypothesis = generate_hypothesis(factor_result, report_content)
    return exp
```

关键代码：[factor_from_report.py#L60-L93](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py#L60-L93)

> ⚠️ 注意：PDF 文本被加载了**两次**——一次在 `FactorExperimentLoaderFromPDFfiles.load()` 内部用于因子提取，另一次在此处用于假设生成。这是一个可优化的重复 I/O。

---

## 6. 循环编排：每份研报的处理流程

`FactorReportLoop.direct_exp_gen()` 是主循环的核心，每轮处理一份研报：

```
async def direct_exp_gen(prev_out):
    while True:
        if 并行槽位可用:
            # 1. 取当前研报路径（loop_idx + shift_report 跳过无效报告）
            pdf_path = judge_pdf_data_items[loop_idx + shift_report]

            # 2. NLP 管道提取因子 + 生成假设
            exp = extract_hypothesis_and_exp_from_reports(pdf_path)

            # 3. 无效报告跳过
            if exp is None:
                shift_report += 1
                loop_n -= 1
                if loop_n < 0:
                    raise LoopTerminationError
                continue

            # 4. 截断因子数量（每份研报最多 6 个）
            exp.sub_tasks = exp.sub_tasks[:max_factors_per_exp]
            exp.sub_workspace_list = exp.sub_workspace_list[:max_factors_per_exp]

            # 5. 构建基线实验链（空基线 + 历史成功实验）
            exp.based_experiments = [
                QlibFactorExperiment(sub_tasks=[], hypothesis=exp.hypothesis)
            ] + [t[0] for t in self.trace.hist if t[1]]

            # 6. 设置基础特征（ALPHA20）
            exp.base_features = self.plan["features"]

            return exp
        await asyncio.sleep(1)
```

### 6.1 无效报告跳过机制

`shift_report` 是研报场景特有的偏移量。当某份 PDF 无法提取有效因子时（非量化报告、因子为空、全部被可行性过滤），循环不会终止，而是：

```
shift_report += 1    # 跳过当前报告
loop_n -= 1          # 总轮次减 1
continue             # 处理下一份
```

这意味着如果文件夹中有 20 份 PDF，其中 5 份无效，实际会处理 15 份有效报告（在 `report_limit=20` 范围内）。

### 6.2 与因子挖掘场景的返回值差异

| 场景 | direct_exp_gen 返回 | coding 取法 |
|------|---------------------|------------|
| 因子挖掘 | `{"propose": hypo, "exp_gen": exp}` | `prev_out["direct_exp_gen"]["exp_gen"]` |
| 研报复现 | 直接返回 `exp`（Experiment） | `prev_out["direct_exp_gen"]` |

因此研报场景重写了 `coding()` 方法：

```python
def coding(self, prev_out):
    exp = self.coder.develop(prev_out["direct_exp_gen"])  # 直接取
    return exp
```

关键代码：[factor_from_report.py#L112-L143](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py#L112-L143)

---

## 7. 完整端到端时序

```
用户/CLI                    FactorReportLoop           PDF Loader              LLM API              CoSTEER/Runner
  │                            │                         │                       │                      │
  │── 启动(report_folder) ────>│                         │                       │                      │
  │                            │── 扫描 *.pdf ──────────>│                       │                      │
  │                            │<─ pdf_paths [] ────────│                       │                      │
  │                            │                         │                       │                      │
  │              ══════════════ 第 N 轮循环 ══════════════╪═══════════════════════╪══════════════════════╡
  │                            │                         │                       │                      │
  │                            │── extract_*_from_reports(pdf_path) ──>          │                      │
  │                            │                         │── PyPDFLoader ──>     │                      │
  │                            │                         │<─ full_text ─────────│                      │
  │                            │                         │                       │                      │
  │                            │                         │── classify ─────────>│                      │
  │                            │                         │<─ {class: 1} ────────│                      │
  │                            │                         │                       │                      │
  │                            │                         │── extract factors ──>│ (多轮对话, 最多10轮)  │
  │                            │                         │<─ {name: desc} ──────│                      │
  │                            │                         │                       │                      │
  │                            │                         │── extract formulas ─>│ (多轮对话, 最多10轮)  │
  │                            │                         │<─ {name: {formula, vars}} ──────────────────│
  │                            │                         │                       │                      │
  │                            │                         │── viability check ──>│ (每批50个, 多进程)    │
  │                            │                         │<─ {name: viable} ────│                      │
  │                            │                         │                       │                      │
  │                            │                         │── FactorTask[] ──────│                      │
  │                            │<─ QlibFactorExperiment ─┘                       │                      │
  │                            │                         │                       │                      │
  │                            │── screenshot + hypothesis ─────────────────────>│                      │
  │                            │<─ Hypothesis ──────────────────────────────────│                      │
  │                            │                         │                       │                      │
  │                            │── coder.develop(exp) ──────────────────────────────────────────────────>│
  │                            │<─ exp with code ───────────────────────────────────────────────────────│
  │                            │                         │                       │                      │
  │                            │── runner.develop(exp) ────────────────────────────────────────────────>│
  │                            │<─ exp with results ────────────────────────────────────────────────────│
  │                            │                         │                       │                      │
  │                            │── feedback + record ──>│                       │                      │
  │                            │                         │                       │                      │
  │              ══════════════ 下一份研报 ═══════════════╪═══════════════════════╪══════════════════════╡
```

---

## 8. 数据结构总览

### 8.1 管道各阶段数据形态

```
PDF 文件
  ↓ load_and_process_pdfs_by_langchain()
dict[str, str]                          # {"/path/to/report.pdf": "全文文本..."}
  ↓ classify_report_from_dict()
dict[str, dict]                         # {"/path/to/report.pdf": {"class": 1}}
  ↓ extract_factors_from_report_dict()
dict[str, dict[str, dict]]              # 按文件分组的因子
# {
#   "/path/to/report.pdf": {
#     "Momentum_1M": {
#       "description": "1-month price momentum...",
#       "formulation": "\\frac{P_t - P_{t-20}}{P_{t-20}}",
#       "variables": {"P_t": "Closing price at day t"}
#     }
#   }
# }
  ↓ merge_file_to_factor_dict_to_factor_dict()
dict[str, dict]                         # 合并后的因子字典（去重）
  ↓ check_factor_viability()
tuple[dict, dict]                       # (全部可行性结果, 过滤后的因子字典)
  ↓ FactorExperimentLoaderFromDict()
QlibFactorExperiment                    # 含 FactorTask 列表的实验对象
  ↓ generate_hypothesis()
QlibFactorExperiment(exp.hypothesis=Hypothesis(...))
```

### 8.2 日志与可观测性

管道每个阶段都通过 `logger.log_object()` 记录中间结果，在 WebUI 中可查看：

| Tag | 内容 |
|-----|------|
| `docs` | PDF 全文文本字典 |
| `file_to_factor_result` | 按文件分组的因子提取结果 |
| `factor_dict` | 合并后的因子字典 |
| `filtered_factor_dict` | 可行性过滤后的因子 |
| `load_pdf_screenshot` | PDF 首页截图（`research.pdf_image`） |
| `hypothesis generation` | LLM 事后生成的假设 |
| `experiment generation` | 最终 FactorTask 列表 |

---

## 9. 配置参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `report_result_json_file_path` | `QLIB_FACTOR_REPORT_RESULT_JSON_FILE_PATH` | `git_ignore_folder/report_list.json` | 默认 PDF 路径列表 JSON |
| `max_factors_per_exp` | `QLIB_FACTOR_MAX_FACTORS_PER_EXP` | 6 | 每份研报最多实现的因子数 |
| `report_limit` | `QLIB_FACTOR_REPORT_LIMIT` | 20 | 最多处理的研报份数 |
| `multi_proc_n` | `RD_AGENT_MULTI_PROC_N` | 11 | 因子提取并行进程数 |
| `chat_token_limit` | - | 模型上下文窗口 | 超长文本自动截断阈值 |

配置类定义：[conf.py#L130-L143](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py#L130-L143)

---

## 10. 已知限制与优化方向

| 限制 | 说明 | 可能的改进 |
|------|------|-----------|
| **扫描版 PDF 效果差** | PyPDF 无法提取图片中的文字 | 启用 Azure Document Intelligence 或 OCR 预处理 |
| **文本重复加载** | `extract_hypothesis_and_exp_from_reports` 中 PyPDF 加载了两次 | 缓存首次加载结果传入 |
| **单次分类投票** | `vote_time=1` 可能误判 | 支持配置多次投票 |
| **精确名称去重** | 跨报告合并仅按因子名精确匹配 | 启用已实现的 `deduplicate_factors_by_llm()` 语义去重 |
| **因子截断** | 超过 6 个因子直接截断，无优先级排序 | 按可行性/相关性评分排序后截断 |
| **无相关性检查** | `check_factor_relevance()` 已实现但未在管道中调用 | 在可行性检查前增加相关性过滤 |
| **公式下划线转义** | 简单字符串替换可能误伤 | 使用更精确的 LaTeX AST 处理 |

---

## 11. 关键代码索引

| 模块 | 文件路径 |
|------|----------|
| 主循环/入口 | [factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py) |
| NLP 管道（核心） | [pdf_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py) |
| LLM 提示词 | [prompts.yaml](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/prompts.yaml) |
| 字典→Experiment | [json_loader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/factor_experiment_loader/json_loader.py) |
| PDF 读取/截图 | [document_reader.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/document_reader/document_reader.py) |
| WebUI 上传接口 | [app.py#L938-L1071](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py#L938-L1071) |
| 场景配置 | [conf.py#L130-L143](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py#L130-L143) |
| 场景类 | [factor_from_report_experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_from_report_experiment.py) |
