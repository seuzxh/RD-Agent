---
title: WebUI 研报上传测试计划
---

# WebUI 研报上传测试文档

> 范围：MultiAlpha 前端“研报上传”功能，以及对应 Flask `/upload`、研报任务执行、trace 查询和文件落盘链路。
>
> 文档性质：测试流程与测试用例规范。执行后请在“状态”列填写结果，不把接口返回 200 直接等同于研报处理成功。
>
> 版本：v1.1  
> 编写日期：2026-08-08
>
> 执行报告：[`WEBUI_REPORT_UPLOAD_TEST_REPORT_20260808.md`](WEBUI_REPORT_UPLOAD_TEST_REPORT_20260808.md)

## 1. 测试目标

验证用户从网页上传一份或多份研报 PDF 后，系统能够正确完成以下链路：

```text
进入研报上传入口
  → 选择 PDF
  → 前端校验
  → POST /upload
  → 保存上传文件
  → 启动 fin_factor_report 子进程
  → 轮询 /trace 和 /stdout
  → 展示研报提取结果或明确的失败/跳过原因
```

测试分为四层：

1. 前端交互和表单行为。
2. `/upload` 请求字段及 HTTP 响应。
3. 文件、trace、stdout 的后端产物。
4. 研报任务的实际执行结果。

## 2. 源码依据与已确认行为

| 模块 | 文件 | 已确认内容 |
|---|---|---|
| 上传弹窗 | [`web/src/multialpha/components/NewTaskDialog.vue`](../../web/src/multialpha/components/NewTaskDialog.vue) | PDF Tab、文件选择、循环数、空文件校验 |
| 前端提交 | [`web/src/multialpha/use-multialpha.ts`](../../web/src/multialpha/use-multialpha.ts) | FormData 构造、场景映射、提交后刷新和跳转 |
| Flask 接口 | [`rdagent/log/server/app.py`](../../rdagent/log/server/app.py) | `/upload`、并发检查、文件保存、子进程启动 |
| 研报入口 | [`rdagent/app/qlib_rd_loop/factor_from_report.py`](../../rdagent/app/qlib_rd_loop/factor_from_report.py) | 扫描 PDF、按报告执行循环 |
| PDF 管道 | [`rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py`](../../rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py) | PDF 解析、报告分类、因子提取和可行性检查 |
| 存储配置 | [`rdagent/log/ui/conf.py`](../../rdagent/log/ui/conf.py) | `UI_TRACE_FOLDER`、默认并发上限和报告上限 |

当前源码中的关键事实：

- PDF 模式发送的场景固定为 `Finance Data Building (Reports)`，后端目标固定为 `fin_factor_report`。
- PDF 模式不显示 description，也不提交 `description`。
- 前端 `accept=".pdf"` 只是上传控件提示；后端当前没有扩展名白名单校验。
- 前端允许多文件上传，后端使用 `request.files.getlist("files")`。
- 后端研报分支没有把 `loops` 传给 `fin_factor_report`；实际处理数量为 `min(扫描到的 PDF 数量, report_limit)`，默认 `report_limit=20`。
- `fin_factor_report` 属于不启用用户交互的目标，不应产生 `user_interaction.request`。
- 后端在并发检查之前保存上传文件；并发超限时可能留下已保存的孤儿文件，这是需要验证并记录的现状。
- 子进程异常在 `RDAgentTask._run()` 中被捕获并打印到 stdout；因此必须同时检查 `END`、`stdout` 和 trace 内容，不能只看 HTTP 状态码。

## 3. 测试环境

### 3.1 后端

从仓库根目录启动，以确保 CLI 加载当前目录的 `.env`：

```bash
cd /home/zxh/projects/1.multialphaV/RD-Agent
conda activate rdagent4qlib
mkdir -p /tmp/rdagent-report-test
UI_TRACE_FOLDER=/tmp/rdagent-report-test \
rdagent server_ui --port 19899
```

检查服务：

```bash
curl http://127.0.0.1:19899/health
```

### 3.2 前端

```bash
cd /home/zxh/projects/1.multialphaV/RD-Agent/web
npm ci
npm run dev
```

默认访问：`http://localhost:8080/multialpha.html`。如果 8080 已被占用，Vite 会自动递增端口；本次准备环境实际使用 `http://localhost:8083/multialpha.html`。

Vite 开发代理默认将 `/upload`、`/trace`、`/traces`、`/logs`、`/stdout`、`/health` 等请求转发到 `localhost:19899`。

### 3.3 运行前检查

- 浏览器 DevTools 的 Network 和 Console 可用。
- 后端端口 `19899` 未被其他服务占用。
- LLM、Docker、Qlib 等运行依赖可用。
- 测试目录为空或已使用独立目录，避免历史 trace 干扰。
- 对长时间任务设置人工观察窗口，不要仅以页面跳转成功判定通过。

## 4. 测试数据

至少准备以下文件：

| 数据编号 | 文件 | 用途 |
|---|---|---|
| PDF-VALID-01 | `国泰君安－基于短周期价量特征的多因子选股体系.pdf` | 固定主流程样本 |
| PDF-VALID-02 | 第二份可正常解析的 PDF | 多文件上传 |
| PDF-NONQUANT-01 | 可解析但不含可用量化因子的报告 | 分类/跳过场景 |
| PDF-BROKEN-01 | 损坏或无法解析的 PDF | 子进程异常场景 |
| FILE-TXT-01 | `sample.txt` | 非 PDF 输入 |
| FILE-NAME-01 | 含中文、空格或路径字符的 PDF | 文件名清洗和路径安全 |

有效研报不要求固定文件名；测试关注点是“可解析”和“内容确实能够进入 PDF 提取流程”。

### 4.1 固定主流程样本

本轮测试指定以下附件作为 `PDF-VALID-01`：

```text
/home/zxh/.codex/attachments/b8513c56-1eca-44b2-abe4-07268e798cfe/国泰君安－基于短周期价量特征的多因子选股体系.pdf
```

已做的只读预检查：

- 文件大小约 2.0 MB。
- 使用本地 `fitz` 可读取，共 32 页。
- 首页能够提取文本，内容包含“短周期价量特征”“多因子选股”“阿尔法因子”等量化研报信息。
- 该检查证明文件本身可读取；实际服务仍需在安装了 `langchain_community`、`pypdf` 等项目依赖的运行环境中验证 `load_and_process_pdfs_by_langchain()`。

如果需要把附件复制到临时测试目录，可执行：

```bash
mkdir -p /tmp/rdagent-report-fixtures
cp '/home/zxh/.codex/attachments/b8513c56-1eca-44b2-abe4-07268e798cfe/国泰君安－基于短周期价量特征的多因子选股体系.pdf' \
   '/tmp/rdagent-report-fixtures/gtja_short_cycle_price_volume_multi_factor.pdf'
```

之后将该复制文件作为 `PDF-VALID-01` 使用。浏览器测试时直接选择原附件或复制后的文件均可，但执行记录中应注明实际路径。

## 5. 用户主流程

### 5.1 打开研报上传弹窗

1. 访问 MultiAlpha 首页。
2. 点击“研报因子提取”，或点击“新建任务”后切换到“研报上传”。
3. 检查弹窗中的字段。

预期：

- 当前 Tab 为“研报上传”。
- 显示上传研报 PDF 区域和循环次数。
- 不显示策略描述、挖掘场景、验证模型和运行模式。

### 5.2 选择和删除文件

1. 选择 `PDF-VALID-01`。
2. 再选择 `PDF-VALID-02`。
3. 删除其中一个文件。
4. 再次确认文件列表。

预期：

- 两次选择后显示两份文件。
- 删除后只保留一份。
- 提交前不产生 `/upload` 请求。

### 5.3 提交并检查请求

1. 选择循环数 `1`。
2. 点击“启动任务”。
3. 在 Network 中打开 `POST /upload` 的 FormData。

请求应包含：

```text
scenario = Finance Data Building (Reports)
loops = 1
auto_mode = true
files = <selected PDF>
```

请求不应包含 `description` 和 `model_selector`。

### 5.4 检查创建结果

预期：

- HTTP `200`。
- 响应包含 `id`，形如 `Finance Data Building (Reports)/<random-name>`。
- 弹窗关闭，任务列表刷新，页面跳转到新任务详情，并显示“任务已启动”。

### 5.5 检查 trace、stdout 和文件

保存返回的 trace id，然后查询：

```bash
curl -X POST http://127.0.0.1:19899/trace \
  -H 'Content-Type: application/json' \
  -d '{"id":"Finance Data Building (Reports)/<random-name>","all":true,"reset":true}'
```

同时检查：

```bash
find /tmp/rdagent-report-test -type f -print
```

必须检查：

- 上传文件位于 `uploads/Finance Data Building (Reports)/<trace_name>/`。
- 对应 stdout 日志已生成。
- `/trace` 返回 `task.user_input`。
- 研报任务没有 `user_interaction.request`。
- 最终出现 `END` 消息。
- 若任务失败，stdout 中有具体 traceback 或错误原因。

## 6. 测试用例

状态列使用：`未执行`、`通过`、`失败`、`阻塞`、`跳过`。

### 6.1 P0 主链路

| 编号 | 用例 | 前置条件 | 操作 | 预期结果 | 状态 |
|---|---|---|---|---|---|
| FR-P0-01 | 单 PDF 正常上传 | 服务正常，准备 PDF-VALID-01 | 进入研报上传，选择文件并启动 | `/upload` 返回 200 和 id | 通过 |
| FR-P0-02 | 多 PDF 正常上传 | 准备 PDF-VALID-01、02 | 一次选择两份 PDF 后启动 | FormData 有两个 `files`，任务创建成功 | 通过 |
| FR-P0-03 | 空文件提交校验 | 打开研报上传弹窗 | 不选文件直接点击启动 | 提示“请上传研报 PDF”，不发送 `/upload` | 通过 |
| FR-P0-04 | 文件删除 | 已选择两份 PDF | 删除其中一份后启动 | 请求只携带剩余文件 | 通过 |
| FR-P0-05 | 创建后页面行为 | `/upload` 返回 200 | 观察页面 | 弹窗关闭、列表刷新、跳转任务详情 | 失败 |
| FR-P0-06 | 场景映射 | 已成功创建任务 | 检查请求和 stdout | 场景为 `Finance Data Building (Reports)`，目标为 `fin_factor_report` | 通过 |
| FR-P0-07 | 上传文件落盘 | 已获得 trace id | 检查 `UI_TRACE_FOLDER` | 文件出现在对应 `uploads` 子目录 | 通过 |
| FR-P0-08 | 无用户交互 | 研报任务运行中 | 轮询 `/trace` | 不出现 `user_interaction.request` | 通过 |
| FR-P0-09 | 任务结束 | 有效量化研报和完整运行环境 | 等待任务结束 | 出现 `END`，页面停止继续轮询 | 失败 |
| FR-P0-10 | 结果展示 | 任务产生有效因子结果 | 查看任务详情 | 因子、代码、指标或明确的跳过/失败信息可见 | 失败 |

### 6.2 P1 字段和状态

| 编号 | 用例 | 操作 | 预期/检查点 | 状态 |
|---|---|---|---|---|
| FR-P1-01 | 循环数请求值 | 分别选择 1、3、5、10，检查 Network | `loops` 字段值与选择一致 | 通过 |
| FR-P1-02 | 循环数实际语义 | 上传 2 份 PDF，选择 10 轮 | 实际处理数不应按 10 份计算；检查 trace/stdout | 通过 |
| FR-P1-03 | 报告数量上限 | 准备超过 20 份 PDF | 检查实际处理数量是否受 `report_limit=20` 限制 | 通过 |
| FR-P1-04 | 非量化研报 | 上传 PDF-NONQUANT-01 | 任务不挂死；日志说明无可用实验或跳过 | 通过 |
| FR-P1-05 | 取消后再次打开 | 选文件后取消，再次打开上传弹窗 | 检查旧文件是否残留；当前源码没有显式清空 `files` | 失败 |
| FR-P1-06 | Tab 切换文件残留 | 选 PDF 后切换到“因子优化” | 检查提交是否错误携带之前的 PDF | 失败 |
| FR-P1-07 | 页面刷新恢复 | 任务运行中刷新浏览器 | 任务仍能从 `/traces` 和 `/trace` 查询 | 通过 |
| FR-P1-08 | 停止运行任务 | 任务运行中点击停止 | `/control` 返回 stopped，trace 出现停止产生的 `END` | 通过 |

### 6.3 P1 文件和异常输入

| 编号 | 用例 | 操作 | 源码基线/预期 | 状态 |
|---|---|---|---|---|
| FR-P1-09 | 非 PDF 文件 | 上传 FILE-TXT-01 | 前端 accept 不是强校验，后端也无扩展名校验；记录是否被接受及后续行为 | 失败 |
| FR-P1-10 | 损坏 PDF | 上传 PDF-BROKEN-01 | 记录 `/upload`、stdout、`END`；不能只依据 200 判定成功 | 失败 |
| FR-P1-11 | 空 PDF | 上传 0 字节 PDF | 任务应结束并能从日志解释失败原因 | 失败 |
| FR-P1-12 | 特殊文件名 | 上传 FILE-NAME-01 | 检查 `secure_filename` 后的文件名，不能越出上传目录 | 通过 |
| FR-P1-13 | 同名文件 | 一次提交两个同名文件 | 当前后端第二次保存可能返回 400；检查是否留下部分文件 | 失败 |
| FR-P1-14 | 大文件 | 上传大体积 PDF | 当前源码无显式大小限制，记录耗时、内存和任务结果 | 通过 |

### 6.4 P1 直接 API 和并发边界

这些用例不要求通过浏览器操作，可用 curl 验证后端边界。

| 编号 | 请求/操作 | 预期/源码基线 | 状态 |
|---|---|---|---|
| FR-P1-15 | `scenario=Unknown` | HTTP 400，错误为 `Unknown scenario` | 通过 |
| FR-P1-16 | 不传 `scenario` | 记录实际 HTTP 响应和是否创建目录 | 失败 |
| FR-P1-17 | 只传场景、不传 files | 当前后端没有文件前置校验，可能返回 200 并启动空任务；应记录为缺陷候选 | 失败 |
| FR-P1-18 | `loops=abc` | 当前代码直接执行 `int()`，预期 HTTP 500 | 失败 |
| FR-P1-19 | 运行任务达到 10 个 | 再发一次上传请求 | HTTP 429；检查是否已提前写入上传文件 | 失败 |
| FR-P1-20 | 路径穿越文件名 | 上传名包含 `../../` | 文件名被清洗，不能写到 `UI_TRACE_FOLDER` 外 | 通过 |

## 7. API 验证示例

### 7.1 正常上传

```bash
curl -X POST http://127.0.0.1:19899/upload \
  -F 'scenario=Finance Data Building (Reports)' \
  -F 'loops=1' \
  -F 'auto_mode=true' \
  -F 'files=@/home/zxh/.codex/attachments/b8513c56-1eca-44b2-abe4-07268e798cfe/国泰君安－基于短周期价量特征的多因子选股体系.pdf'
```

### 7.2 多文件上传

```bash
curl -X POST http://127.0.0.1:19899/upload \
  -F 'scenario=Finance Data Building (Reports)' \
  -F 'loops=10' \
  -F 'auto_mode=true' \
  -F 'files=@/absolute/path/to/report-1.pdf' \
  -F 'files=@/absolute/path/to/report-2.pdf'
```

### 7.3 未知场景

```bash
curl -i -X POST http://127.0.0.1:19899/upload \
  -F 'scenario=Unknown' \
  -F 'loops=1'
```

### 7.4 查询完整 trace

```bash
curl -X POST http://127.0.0.1:19899/trace \
  -H 'Content-Type: application/json' \
  -d '{"id":"Finance Data Building (Reports)/<trace-name>","all":true,"reset":true}'
```

## 8. 通过判定

### P0 通过条件

- 空文件提交被前端拦截。
- 单文件和多文件请求字段正确。
- `/upload` 返回有效 trace id。
- 文件正确落盘。
- 后端确实启动 `fin_factor_report`。
- 研报任务不会等待用户交互。
- 任务最终能产生 `END`，或产生可解释的失败结果。
- 正常量化研报能够进入 PDF 提取和后续因子流程。

### 缺陷判定

下列情况应记录为缺陷或改进项：

- 非 PDF 文件被后端无条件接受。
- 无文件请求仍返回 200。
- 选择的 loops 与实际处理数量不一致且产品要求认为二者应一致。
- 取消或切换 Tab 后旧文件被再次提交。
- 子进程异常后页面显示完成，但 stdout 有 traceback 或 `END.end_code` 表示异常。
- 并发 429 后遗留上传文件。

## 9. 执行记录模板

每条用例执行后补充：

```text
用例编号：
执行时间：
执行人：
浏览器/Node/Python 环境：
测试文件：
操作步骤：
Network 请求：
HTTP 状态码：
响应内容：
trace id：
trace 消息标签：
END.content：
stdout 路径及关键日志：
文件落盘路径：
结果：通过 / 失败 / 阻塞 / 跳过
问题描述：
```

## 10. 执行顺序建议

1. 先执行 `FR-P0-01` 至 `FR-P0-10`，确认主链路。
2. 再执行 `FR-P1-01` 至 `FR-P1-14`，确认边界和前端状态。
3. 最后执行 `FR-P1-15` 至 `FR-P1-20`，验证后端异常和并发行为。
4. 所有失败用例必须同时保留浏览器 Network、`/trace` 响应、stdout 和文件目录证据。
