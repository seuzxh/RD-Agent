---
title: WebUI 研报上传测试报告（2026-08-08）
---

# WebUI 研报上传测试报告（2026-08-08）

> 对应测试规范：[`WEBUI_REPORT_UPLOAD_TEST_PLAN.md`](WEBUI_REPORT_UPLOAD_TEST_PLAN.md)  
> 测试范围：MultiAlpha 研报上传 UI、`POST /upload`、任务调度、PDF 解析、trace/stdout、文件落盘及异常边界。  
> 固定研报：`国泰君安－基于短周期价量特征的多因子选股体系.pdf`

## 1. 结论

本轮共执行 30 条用例：

| 结果 | 数量 |
|---|---:|
| 通过 | 17 |
| 失败 | 13 |
| 跳过 | 0 |

P0 主流程结果为 **7 通过、3 失败**。上传接口、文件落盘和任务调度可以工作，但有效研报没有完成因子提取链路，页面最终错误显示“已完成”。因此研报上传功能当前不能按业务成功验收。

核心阻断问题：

1. 有效研报在 LLM 返回 `{}` 时触发 `KeyError: 'factors'`，任务中止。
2. 子进程异常被吞掉，trace 仍生成 `END(end_code=0)`，页面显示“已完成”。
3. 创建成功后的首次路由出现 `404 · TRACE NOT FOUND`，刷新后恢复。
4. 上传文件状态在取消重开、Tab 切换时残留，可能提交用户看不到或类型不匹配的文件。

## 2. 测试环境

| 项目 | 实际值 |
|---|---|
| 测试日期 | 2026-08-08 15:06–15:20（Asia/Shanghai） |
| 前端 | Vite，`http://127.0.0.1:8083/multialpha.html` |
| 后端 | Flask，`http://127.0.0.1:19899` |
| 浏览器 | Playwright Chromium 151，无头模式，1440×1000 |
| 后端健康 | LLM、Docker、Qlib、Conda、MLflow 共 5 项 pass |
| 固定 PDF | 2,024,514 bytes，32 页，可提取约 52,710 字符 |
| 非量化 PDF | 1,017 bytes，内容为员工手册，无金融或投资研究内容 |
| 大文件 PDF | 9,813,987 bytes，由固定样本重复合并为 192 页 |
| 主流程 trace | `Finance Data Building (Reports)/eager-antenna` |

环境观察：`/health` 显示 `CONDA_DEFAULT_ENV=rdagent4qlib`，但实际任务 traceback 中的依赖路径来自 `/home/zxh/miniconda3/envs/multialphav/`。当前功能可以启动，但健康检查显示的环境名不能证明服务实际 Python 解释器来自同名 Conda 环境。

## 3. 主流程执行记录

### 3.1 浏览器操作

1. 打开 MultiAlpha 首页。
2. 点击“研报因子提取”。
3. 确认 PDF Tab 显示上传区和循环次数，不显示策略描述、验证模型和运行模式。
4. 上传固定国泰君安研报。
5. 选择 `1 轮`。
6. 点击“启动任务”。

HTTP 结果：

```json
{
  "id": "Finance Data Building (Reports)/eager-antenna"
}
```

- HTTP 状态：200。
- 浏览器出现“任务已启动”。
- URL 跳转到 `#/tasks/Finance%20Data%20Building%20(Reports)%2Feager-antenna`。
- 首次跳转显示 `404 · TRACE NOT FOUND`。
- 刷新页面后任务可以正常显示为“运行中”。

### 3.2 文件落盘

上传文件实际保存为：

```text
git_ignore_folder/traces/uploads/Finance Data Building (Reports)/eager-antenna/-.pdf
```

文件大小为 2,024,514 bytes，与原文件一致。`secure_filename()` 将中文文件名清洗成了 `-.pdf`。

stdout：

```text
git_ignore_folder/traces/Finance Data Building (Reports)/eager-antenna.log
```

### 3.3 trace 结果

完整 trace 只有 6 条消息：

```text
feedback.config
token_cost
token_cost
token_cost
token_cost
END
```

没有出现：

```text
task.user_input
research.pdf_image
research.hypothesis
research.tasks
evolving.codes
feedback.metric
feedback.return_chart
feedback.hypothesis_feedback
```

结束消息：

```json
{
  "tag": "END",
  "content": {
    "end_code": 0,
    "error_msg": "RD-Agent process has completed."
  }
}
```

页面据此显示“已完成”，但没有因子、代码、指标或最终结论。

### 3.4 真实异常

stdout 中的最终异常：

```text
File "rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py", line 131,
in __extract_factors_name_and_desc_from_content
    factors = ret_dict["factors"]
KeyError: 'factors'
```

异常前，LLM 在“继续提取因子”的请求中返回：

```json
{}
```

代码直接读取 `ret_dict["factors"]`，没有对缺失字段、空对象或不符合 schema 的响应做容错。

## 4. 用例结果

### 4.1 P0 主链路

| 编号 | 结果 | 证据摘要 |
|---|---|---|
| FR-P0-01 | 通过 | 单 PDF 经真实浏览器上传，HTTP 200，返回 `eager-antenna` |
| FR-P0-02 | 通过 | 双文件真实上传保存 2 个文件；随后主动停止任务避免重复执行 |
| FR-P0-03 | 通过 | 空提交提示“请上传研报 PDF”，Network 中 `/upload` 请求数为 0 |
| FR-P0-04 | 通过 | 删除第二个文件后列表从 2 变为 1 |
| FR-P0-05 | 失败 | 创建成功、toast 和 URL 跳转正常，但首次详情页显示 404；刷新恢复 |
| FR-P0-06 | 通过 | 场景为 `Finance Data Building (Reports)`，目标为 `fin_factor_report` |
| FR-P0-07 | 通过 | 文件正确落盘，大小与原文件一致 |
| FR-P0-08 | 通过 | trace 中没有 `user_interaction.request` |
| FR-P0-09 | 失败 | 任务以 `END(end_code=0)` 结束，但 stdout 实际有未处理异常 |
| FR-P0-10 | 失败 | 页面无因子、代码、指标、图表或明确失败提示 |

### 4.2 P1 字段和状态

| 编号 | 结果 | 证据摘要 |
|---|---|---|
| FR-P1-01 | 通过 | 下拉存在 1/3/5/10 四个值；请求可发送所选 loops |
| FR-P1-02 | 通过 | Flask 调度参数中没有 `loop_n`，研报流程忽略前端 loops |
| FR-P1-03 | 通过 | 21 个 PDF 时 `FactorReportLoop.loop_n == 20` |
| FR-P1-04 | 通过 | `average-mayonnaise` 将员工手册 PDF 判为 `class=0`，提取 0 份报告并正常 END(0)，未进入编码、未挂死 |
| FR-P1-05 | 失败 | 取消重开后列表显示 0 个文件，但点击启动仍发出 `/upload`，没有空文件提示 |
| FR-P1-06 | 失败 | PDF 切换到因子优化后，控件 accept 变为 `.py`，原 PDF 仍保留 |
| FR-P1-07 | 通过 | 直接刷新 `eager-antenna` 路由后任务详情恢复 |
| FR-P1-08 | 通过 | `internal-slur` 停止返回 200，END 为 `end_code=-1` |

### 4.3 P1 文件和异常输入

| 编号 | 结果 | 证据摘要 |
|---|---|---|
| FR-P1-09 | 失败 | `sample.txt` 被接受并保存，接口返回 200，随后任务伪完成 |
| FR-P1-10 | 失败 | 损坏 PDF 返回 200；stdout 为 `PdfStreamError`，END 却为 0 |
| FR-P1-11 | 失败 | 0 字节 PDF 返回 200；stdout 为 `EmptyFileError`，END 却为 0 |
| FR-P1-12 | 通过 | `../../evil.pdf` 被保存为 `evil.pdf`，未写出允许目录 |
| FR-P1-13 | 失败 | 两个同名文件返回 400，但第一份文件已经残留 |
| FR-P1-14 | 通过 | 9,813,987-byte、192 页 PDF 上传 HTTP 200，耗时 0.092105 秒，落盘大小一致；随后主动停止，END 为 -1 |

### 4.4 P1 API 和并发边界

| 编号 | 结果 | 证据摘要 |
|---|---|---|
| FR-P1-15 | 通过 | 未知场景返回 400 `Unknown scenario` |
| FR-P1-16 | 失败 | 缺少 scenario 触发 `TypeError`，返回 HTML 500 |
| FR-P1-17 | 失败 | 不传 files 仍返回 200 并启动任务 |
| FR-P1-18 | 失败 | `loops=abc` 触发未捕获 `ValueError`，返回 HTML 500 |
| FR-P1-19 | 失败 | 并发达到上限返回 429，但文件已在检查前写入并残留 |
| FR-P1-20 | 通过 | 路径穿越文件名被清洗，没有写出根目录 |

## 5. 问题清单

### RPT-001 [P0] 有效研报提取因子时因空 JSON 崩溃

复现步骤：

1. 上传固定国泰君安研报。
2. 等待 PDF 文本解析和 LLM 因子提取。
3. LLM 首轮返回大量因子，后续“继续提取”返回 `{}`。
4. 任务在 `pdf_loader.py` 中触发 `KeyError: 'factors'`。

根因位置：[`pdf_loader.py`](../../rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py)

```python
ret_dict = json.loads(extract_result_resp)
factors = ret_dict["factors"]
```

建议修复方向：

- 校验响应必须是 dict。
- 使用 `ret_dict.get("factors", {})` 并校验 factors 类型。
- `{}` 应按“没有更多因子”正常结束，而不是异常。
- JSON 不合法或 schema 不匹配时执行有限重试，并记录原始响应摘要。

### RPT-002 [P0] 子进程异常被标记为成功完成

复现 trace：

- `eager-antenna`：`KeyError: 'factors'`。
- `resonnt-hertz`：`PdfStreamError`。
- `sunny-novel`：`EmptyFileError`。
- `mint-cistern`：非 PDF 导致无可处理研报。

四个任务最终均显示：

```json
{"end_code": 0, "error_msg": "RD-Agent process has completed."}
```

根因位置：[`app.py`](../../rdagent/log/server/app.py)

`RDAgentTask._run()` 捕获异常后只打印 traceback，没有重新抛出，也没有保存失败状态，因此 multiprocessing 进程以 0 退出。

建议修复方向：

- 捕获异常后保存错误摘要并让进程以非零状态退出，或重新抛出异常。
- `/trace` 生成 END 时根据进程退出码填写 error_msg。
- 前端根据 `END.content.end_code != 0` 显示“异常”，不能仅凭 END 显示“已完成”。

### RPT-003 [P0] 创建成功后首次路由显示 404

复现步骤：

1. 从首页通过研报上传创建任务。
2. `/upload` 返回 200 和 id。
3. toast 显示“任务已启动”。
4. URL 已跳转到新 id，但正文显示 `404 · TRACE NOT FOUND`。
5. 刷新相同 URL 后正常显示任务。

证据：创建截图和刷新后截图见 §6。

建议检查：

- `createTask()` 中 `/upload → loadTraceIds → selectTrace` 与 `router.push()` 的时序。
- `invalidTrace` 是否在新任务列表状态提交前过早判定。
- `/traces` 刷新结果是否存在短暂旧响应或 generation 覆盖。

### RPT-004 [P1] 取消后存在不可见的旧文件

复现步骤：

1. 打开研报上传，选择 PDF。
2. 点击取消。
3. 再次打开研报上传。
4. 页面文件列表为空。
5. 不选文件直接点击启动。

实际结果：

- 没有“请上传研报 PDF”提示。
- 发出了 `/upload` 请求。

说明组件外层 `files` ref 仍保留旧文件，而 `destroy-on-close` 只清空了上传控件的可见列表。

建议在 open/close 或 visible 关闭时统一重置表单和 `files.value`。

### RPT-005 [P1] Tab 切换保留不匹配类型文件

复现步骤：

1. 在研报 Tab 选择 PDF。
2. 切换到“因子优化”。

实际结果：

- accept 已变为 `.py`。
- 原 PDF 仍显示并保留在提交数据中。

建议 method 变化时清空文件，或分别维护 PDF 和 Python 文件队列并重新验证扩展名。

### RPT-006 [P1] 后端缺少文件类型和必填校验

实际行为：

- 不传 files：200，启动任务。
- 上传 `.txt`：200，保存文件并启动任务。
- 损坏/空 PDF：200，随后子进程异常。

建议 `/upload` 在保存和启动进程之前校验：

- 研报场景至少一份文件。
- 文件扩展名和 MIME 类型。
- PDF 能否打开及是否至少一页。
- 合理的单文件和总大小限制。

### RPT-007 [P1] API 参数错误返回 500

- 缺少 scenario：`Path / None` 触发 TypeError。
- `loops=abc`：`int("abc")` 触发 ValueError。

建议在任何路径拼接和文件保存前完成字段校验，并统一返回 JSON 400。

### RPT-008 [P1] 上传失败会留下部分文件

两种已确认场景：

1. 同一请求包含两个同名文件：第一份保存，第二份返回 400，第一份残留。
2. 并发达到上限：先保存文件，后返回 429，上传文件残留。

建议：

- 并发检查移到保存文件之前。
- 使用临时目录完成全部校验后再原子移动。
- 请求失败时清理当前 trace_name 对应的上传目录。

### RPT-009 [P1] 中文文件名被过度清洗

固定研报文件名被保存为 `-.pdf`。这不影响本次读取，但会丢失可追踪性，也可能造成多个中文文件名清洗后碰撞。

建议保存时使用服务端生成的唯一文件名，同时在元数据中保留原始文件名。

### RPT-010 [P1] Web 运行实例缺少 `task.user_input`

当前源码 `/upload` 会 append `task.user_input`，但实际运行实例的 `/test` 和 `/trace` 中均没有该消息。任务详情因此无法显示用户原始上传配置。

结合“服务 traceback 使用 multialphav 环境，而健康接口显示 rdagent4qlib”，应检查运行中的 server 是否为最新代码和预期解释器启动。

## 6. 截图证据

| 截图 | 内容 |
|---|---|
| [`home.png`](artifacts/20260808-report-upload/home.png) | MultiAlpha 首页和研报入口 |
| [`dialog-two-files.png`](artifacts/20260808-report-upload/dialog-two-files.png) | 研报弹窗选择两份文件 |
| [`tab-retained-file.png`](artifacts/20260808-report-upload/tab-retained-file.png) | 切换 Tab 后文件残留 |
| [`create-route-404.png`](artifacts/20260808-report-upload/create-route-404.png) | 创建成功后首次详情显示 404 |
| [`task-running-after-refresh.png`](artifacts/20260808-report-upload/task-running-after-refresh.png) | 刷新后任务恢复运行中 |
| [`task-false-completed.png`](artifacts/20260808-report-upload/task-false-completed.png) | 后端异常但页面显示已完成 |

## 7. 补充样本与边界执行记录

### 7.1 非量化研报

构造了一份结构有效的单页 PDF，正文为员工手册，明确不含金融、交易、因子或投资研究内容。真实上传创建任务：

```text
Finance Data Building (Reports)/average-mayonnaise
```

LLM 返回 `{"class": 0}`，日志记录 `Factor extraction completed for 0 reports`，工作流在进入编码前触发停止条件。trace 最终为 `END(end_code=0)`，没有 traceback，也没有挂死，符合“识别并跳过非量化研报”的预期。

### 7.2 大体积 PDF

将固定样本重复合并，得到 192 页、9,813,987 bytes 的有效 PDF。真实上传结果：

```text
trace: Finance Data Building (Reports)/feasible-force
HTTP: 200
curl total time: 0.092105 s
curl multipart upload size: 9,814,418 bytes
落盘文件大小: 9,813,987 bytes
```

上传完成后为避免触发重复 LLM/回测费用，立即调用停止接口，返回 `{"status":"stopped"}`，trace 为 `END(end_code=-1)`。受当前运行环境的进程隔离限制，无法读取后端宿主进程 RSS，因此本项验证的是约 10 MB 文件的接口接收、完整落盘、任务创建和可停止性，不代表内存压力上限。

### 7.3 范围说明

- 30 条计划用例均已执行，无跳过或阻塞项。
- 超过 20 份 PDF 的数量限制通过隔离测试验证为 20；未运行 20 份 PDF 的完整 LLM/回测链路，以避免无必要的模型和计算费用。

## 8. 修复优先级建议

建议按以下顺序处理：

1. RPT-002：异常状态必须准确传播，否则所有测试结果都会被“已完成”误导。
2. RPT-001：兼容 `{}` 和不完整 LLM JSON，使有效研报能继续执行。
3. RPT-003：修复创建后首次 404。
4. RPT-004/RPT-005：修复前端隐藏文件和跨 Tab 文件污染。
5. RPT-006/RPT-007/RPT-008：补齐后端输入校验、错误码和失败清理。
6. RPT-009/RPT-010：改善文件追踪和运行环境一致性。

修复完成后至少复测：FR-P0-01、FR-P0-03、FR-P0-05、FR-P0-09、FR-P0-10、FR-P1-05、FR-P1-06、FR-P1-09、FR-P1-10、FR-P1-11、FR-P1-16、FR-P1-17、FR-P1-18、FR-P1-19。
