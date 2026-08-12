# 新建任务

> 入口：首页 TopBar「新建任务」按钮 / LandingTerminal 任务入口卡片
> 组件：`NewTaskDialog` + `MultiAlphaApp.handleCreate` + `useMultiAlpha.createTask`
> 本页覆盖：任务表单、文件上传、并发限制、启动流程

---

## 1. 功能需求（PRD）

### 1.1 任务入口
- **F3.1.1** 顶栏「新建任务」按钮 → 打开对话框（默认文字描述模式）
- **F3.1.2** 首屏入口卡片支持多种方式：
  - 文字描述建任务（可用）
  - 研报 PDF 因子提取（可用）
  - 因子迭代优化（可用）
  - K 线图形分析（即将上线，禁用）
  - 交割单分析（即将上线，禁用）

### 1.2 表单字段
- **F3.2.1** 模式切换：文字描述 / 研报上传 / 因子优化（Tab 切换）
- **F3.2.2** 策略描述（text/optimize）：自然语言描述
- **F3.2.3** 挖掘场景（text）：因子挖掘 fin_factor / 量化全流程 fin_quant / 模型实现 fin_model
- **F3.2.4** 验证模型：LightGBM（默认）/ Linear / XGBoost / CatBoost
- **F3.2.5** 文件上传（pdf/optimize）：PDF 拖拽上传 / 因子代码 .py
- **F3.2.6** 循环次数：1 / 3 / 5 / 10 轮
- **F3.2.7** 运行模式（text）：全自动 / 交互式

### 1.3 并发限制
- **F3.3.1** 运行中任务达上限（默认 10）时，禁止打开新建对话框，弹出 warning 提示
- **F3.3.2** 绕过前端直接请求时，后端返回 429 拒绝

### 1.4 提交后行为
- **F3.4.1** 提交成功：关闭对话框 → 刷新任务列表 → 跳转到新任务详情页 → `ElMessage.success`
- **F3.4.2** 提交失败：`ElMessage.error` 展示错误信息

---

## 2. 技术方案

### 2.1 提交流程

```
NewTaskDialog.submit()
  ├─ 前端校验（描述非空 / PDF 必传）
  ├─ emit('submit', payload)
  ▼
MultiAlphaApp.handleCreate(payload)
  ├─ openDialog 预检：running 数 >= 10 → ElMessage.warning 拦截
  ▼
useMultiAlpha.createTask(payload)
  ├─ 构造 FormData（scenario/loops/description/model_selector/auto_mode/files）
  ├─ POST /upload (multipart/form-data)
  │    ├─ 后端并发检查：running >= max → 429
  │    ├─ 保存文件 → fork RD-Agent 子进程
  │    └─ 返回 { id }
  ├─ cache.delete(id)
  ├─ loadTraceIds()  刷新列表
  └─ selectTrace(id) 跳详情
```

### 2.2 场景映射

前端 method/scenario 到后端 target_name 的映射：

| 前端 method | 前端 scenario | 后端 target_name | 说明 |
|---|---|---|---|
| `text` | `Finance Data Building` | `fin_factor` | 因子挖掘 |
| `text` | `Finance Whole Pipeline` | `fin_quant` | 量化全流程 |
| `text` | `Finance Model Implementation` | `fin_model` | 模型实现 |
| `pdf` | `Finance Data Building (Reports)` | `fin_factor_report` | 研报因子提取 |
| `optimize` | `Finance Data Building` | `fin_factor` | 因子迭代优化 |

### 2.3 并发限制

详见 [TASK_CONCURRENCY_LIMIT](../design/TASK_CONCURRENCY_LIMIT.md)：

- **配置项**：`UI_MAX_CONCURRENT_TASKS`（默认 10，`rdagent/log/ui/conf.py`）
- **后端拦截**：`/upload` 前置检查 `running_count >= max_concurrent` → 返回 429
- **前端预检**：`openDialog` 检查 `tasks.filter(running).length >= 10` → 弹 warning

---

## 3. 接口契约

### 3.1 `POST /upload` — 新建任务

| 项 | 值 |
|---|---|
| 触发 | NewTaskDialog 提交（`use-multialpha.ts:157` `createTask`） |
| Content-Type | `multipart/form-data` |
| 并发检查 | `running_count >= UI_MAX_CONCURRENT_TASKS` → 429 |

**表单字段**：

| 字段 | 必填 | 说明 |
|---|---|---|
| `scenario` | ✅ | 场景名（如 `Finance Data Building`） |
| `loops` | ✅ | 循环次数（1/3/5/10） |
| `description` | text/optimize | 策略描述 |
| `model_selector` | 非 lgbm 时 | 验证模型（linear/xgboost/catboost） |
| `auto_mode` | ✅ | 全自动/交互式（true/false） |
| `files` | pdf/optimize | 上传文件（PDF 或 .py） |

**响应**：
- 成功：`200 { "id": "Finance Data Building/xxx" }`
- 并发超限：`429 { "error": "当前有 N 个任务正在运行（上限 M），请等待..." }`
- 未知场景：`400 { "error": "Unknown scenario" }`

**成功后续**：`cache.delete(id)` → `loadTraceIds()` 刷新列表 → `selectTrace(id)` 跳详情。

---

## 4. 实现索引

### 新建任务组件
| 文件 | 职责 |
|---|---|
| `components/NewTaskDialog.vue` | 任务表单对话框（模式切换/字段/文件上传/校验） |
| `MultiAlphaApp.vue:25` | `openDialog`：预检并发 + 打开对话框 |
| `MultiAlphaApp.vue:26` | `handleCreate`：调 createTask + 跳转 + 消息提示 |

### 数据层关键位置
| 文件:行 | 作用 |
|---|---|
| `use-multialpha.ts:157-169` | `createTask()`：构造 FormData + uploadTask + 刷新 + 跳转 |

### 后端路由
| 路由 | 方法 | 文件:行 | 实现函数 |
|---|---|---|---|
| `/upload` | POST | `app.py:902` | `upload_file()`（含并发检查 `:960`） |

### 配置
| 配置项 | 文件 | 默认值 | 环境变量 |
|---|---|---|---|
| `max_concurrent_tasks` | `rdagent/log/ui/conf.py:27` | `10` | `UI_MAX_CONCURRENT_TASKS` |
