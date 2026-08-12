# Trace 存储路径规则

> 本文档说明 multialpha 系统中任务产物（trace pickle、stdout 日志、session 快照、上传文件等）的落盘位置、命名规则和发现机制。

---

## 1. 概念总览

multialpha 运行时产生三类持久化数据：

| 数据类型 | 写入者 | 格式 | 用途 |
|---------|--------|------|------|
| **Trace 日志** | `FileStorage.log_object()` | `.pkl` / `.json` / `.txt` | 记录每一步的消息对象（hypothesis、code、feedback 等），供 WebUI 实时展示和历史回放 |
| **Session 快照** | `LoopBase.dump()` | 无扩展名 pickle | 每完成一个 step 序列化整个 LoopBase（含 Trace），支持断点恢复 |
| **stdout 日志** | 子进程重定向 | `.log` 文本 | 子进程的标准输出/错误，用于调试 |

这些数据的落盘位置取决于**任务启动方式**（WebUI vs CLI）和**两套独立的路径配置**。

---

## 2. 核心配置

系统有两个互不感知的路径根目录，这是理解所有路径问题的关键：

| 配置项 | 环境变量 | 默认值 | 控制范围 |
|--------|---------|--------|---------|
| `UI_SETTING.trace_folder` | `UI_TRACE_FOLDER` | `./git_ignore_folder/traces` | WebUI 服务端：扫描历史任务、存放上传文件、存放 WebUI 任务的 trace 日志和 stdout |
| `LOG_SETTINGS.trace_path` | `LOG_TRACE_PATH` | `./log/<UTC时间戳>/` | 日志子系统：`FileStorage` 默认写入根；`LoopBase.session_folder` 也基于此路径 |

定义位置：
- [conf.py (UI)](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/ui/conf.py#L19)
- [conf.py (LOG)](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/conf.py#L13)

> **关键区别**：WebUI 服务端通过 `set_storages_path()` 将子进程的 `FileStorage.path` 重定向到 `trace_folder` 下，但**不会**修改 `LOG_SETTINGS.trace_path` 本身。这导致 session 快照的位置与 trace 日志不一致（详见 [§6](#6-session-快照与-webui-错位问题)）。

---

## 3. FileStorage 通用规则

无论 WebUI 还是 CLI，`FileStorage` 的落盘逻辑相同，定义于 [storage.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/storage.py#L28-L113)。

### 3.1 Tag → 目录映射

调用 `log_object(obj, tag="a.b.c")` 时：

```
<storage.path>/a/b/c/<PID链>/<时间戳>.pkl
```

- tag 中的 `.` 替换为路径分隔符 `/`
- PID 链子目录由 `logger.get_pids()` 生成（格式 `父PID-子PID`），用于多进程隔离
- 文件名格式：`<YYYY-MM-DD_HH-MM-SS-ffffff>.pkl`（UTC 微秒时间戳）

**示例**：tag = `"Loop_0.direct_exp_gen.token_cost"`

```
<storage.path>/Loop_0/direct_exp_gen/token_cost/3851031-3853142/2026-07-20_15-00-45-072528.pkl
```

### 3.2 文件格式

`save_type` 参数决定扩展名和序列化方式：

| save_type | 扩展名 | 序列化 |
|-----------|--------|--------|
| `pkl`（默认） | `.pkl` | `pickle.dump()` |
| `json` | `.json` | `json.dump()` |
| `text` | `.txt` | 纯文本写入 |

### 3.3 消息回放

`iter_msg()` 使用 `**/*.pkl` 递归扫描目录，从文件相对路径反推 tag，按时间戳排序后逐条 yield。名为 `debug_llm.pkl` 的文件会被跳过。

---

## 4. WebUI 任务存储布局

### 4.1 任务标识

通过 `POST /upload` 创建任务时（[app.py#L940-L1043](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py#L940-L1043)）：

- **scenario**：表单字段，如 `"Finance Data Building"`
- **trace_name**：`randomname.get_name()` 生成的随机名（如 `baked-yeast`）；预测场景为 `{随机名}-{YYYYMMDD}`
- **trace_id**：`f"{scenario}/{trace_name}"`（如 `Finance Data Building/baked-yeast`）

### 4.2 完整目录树

设 `trace_root = Path(UI_SETTING.trace_folder).absolute()`：

```
<trace_root>/
├── uploads/                                    # 上传文件隔离区
│   └── <scenario>/
│       └── <trace_name>/
│           └── <filename>                      # secure_filename 处理，路径越界校验
│
├── <scenario>/
│   ├── <trace_name>/                           # Trace 日志根目录
│   │   ├── Loop_0/
│   │   │   ├── direct_exp_gen/
│   │   │   │   ├── token_cost/<PID链>/<时间戳>.pkl
│   │   │   │   ├── debug_tpl/<PID链>/<时间戳>.pkl
│   │   │   │   └── ...
│   │   │   ├── coding/
│   │   │   ├── running/
│   │   │   └── feedback/
│   │   ├── RDLOOP_SETTINGS                     # 单文件 tag（无子目录）
│   │   ├── RD_AGENT_SETTINGS
│   │   └── scenario/
│   │
│   └── <trace_name>.log                        # 子进程 stdout（与 trace 目录同级）
```

### 4.3 路径重写机制

子进程启动时（[app.py#L184](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py#L184)）：

```python
rdagent_logger.set_storages_path(self.log_trace_path)
```

这会将 `FileStorage.path` 和 `WebStorage.path` 都指向 `<trace_root>/<scenario>/<trace_name>`，使所有 trace pickle 写入该目录。但 `LOG_SETTINGS.trace_path` 本身**不被修改**。

### 4.4 Scenario → 入口映射

| scenario 字面值 | target_name | 入口模块 |
|----------------|-------------|---------|
| `Finance Data Building` | `fin_factor` | [factor.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py) |
| `Finance Model Implementation` | `fin_model` | [model.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/model.py) |
| `Finance Whole Pipeline` | `fin_quant` | [quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py) |
| `Finance Data Building (Reports)` | `fin_factor_report` | [factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py) |
| `Finance Prediction` | `fin_predict` | [predict.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/predict.py) |

---

## 5. CLI 任务存储布局

CLI 命令（`rdagent fin_factor` 等）不经过 WebUI，直接使用 `LOG_SETTINGS.trace_path`：

```
<LOG_TRACE_PATH>/                              # 默认 ./log/<UTC时间戳>/
├── direct_exp_gen/                            # FileStorage trace 日志
│   └── <PID链>/<时间戳>.pkl
├── coding/
├── running/
├── feedback/
└── __session__/                               # Session 快照（见 §6）
    ├── 0/
    ├── 1/
    │   ├── 0_direct_exp_gen
    │   ├── 1_coding
    │   ├── 2_running
    │   ├── 3_feedback
    │   └── 4_record
    └── 2/
```

`--path` 参数支持从旧 trace 恢复，指向含或不含 `__session__` 后缀的目录均可（[loop.py#L453-L527](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L453-L527)）。

---

## 6. Session 快照与 WebUI 错位问题

### 6.1 Session 快照是什么

`LoopBase` 每完成一个 step 就调用 `dump()` 将整个对象（包含完整 Trace）序列化为 pickle，写入：

```
<LOG_SETTINGS.trace_path>/__session__/<loop_idx>/<step_idx>_<step_name>
```

定义于 [loop.py#L127](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L127) 和 [loop.py#L306](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/workflow/loop.py#L306)。

这些文件是断点恢复和 SOTA 查询的主要数据源。

### 6.2 WebUI 任务的错位

**问题**：WebUI 子进程中，`set_storages_path()` 只修改了 `FileStorage.path`，但 `session_folder` 在 `LoopBase.__init__` 时已经基于 `LOG_SETTINGS.trace_path` 计算完成，不会被重定向。

| 任务类型 | Trace pickle 位置 | Session 快照位置 |
|---------|------------------|-----------------|
| CLI | `LOG_SETTINGS.trace_path/` | `LOG_SETTINGS.trace_path/__session__/` ✅ 同目录 |
| WebUI | `UI_SETTING.trace_folder/<scenario>/<trace_name>/` | `LOG_SETTINGS.trace_path/__session__/` ❌ 不同目录 |

### 6.3 SOTA 查询的回退策略

由于 WebUI 任务的 `__session__/` 不在 trace 目录下，SOTA 查询（[app.py#L1432-L1478](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py#L1432-L1478)）采用两级策略：

1. **优先**：尝试加载 `<trace_root>/<scenario>/<trace_name>/__session__/`（CLI 任务可命中）
2. **回退**：从 `/trace` SSE 消息流中提取最后一条 hypothesis + metrics + codes + feedback，响应中标记 `"source": "message_stream"`

---

## 7. 历史任务发现

### 7.1 GET /traces

[_collect_existing_trace_ids()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py#L592-L610) 扫描规则：

1. 遍历 `<trace_root>/*/*`（二级结构：`<scenario>/<trace_name>`）
2. 排除路径中含 `uploads/` 的目录
3. 要求目录内 `rglob("*.pkl")` 至少命中一个 `.pkl` 文件
4. 返回相对 posix 路径列表（按字典序）

> **注意**：正在运行但尚未写入第一个 `.pkl` 的任务不会出现在列表中（这是新任务创建后短暂"不可见"的原因）。

### 7.2 GET /stdout

[_resolve_stdout_path()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py#L480-L509) 解析规则：

1. **运行中任务**：直接使用内存中 `task.stdout_path`（校验在 `trace_root` 内）
2. **历史任务**：由 `trace_id` 推导为 `<trace_root>/<scenario>/<trace_name>.log`
3. 路径越界返回 400，文件不存在返回 404

---

## 8. 速查表

### 8.1 WebUI vs CLI 对比

| 维度 | WebUI 任务 | CLI 任务 |
|------|-----------|---------|
| 触发方式 | `POST /upload` | `rdagent fin_factor` 等 |
| Trace 根目录 | `UI_SETTING.trace_folder/<scenario>/<trace_name>/` | `LOG_SETTINGS.trace_path/` |
| stdout 位置 | `<trace_root>/<scenario>/<trace_name>.log` | 继承终端 stdout |
| Session 快照 | `LOG_SETTINGS.trace_path/__session__/`（错位） | `LOG_SETTINGS.trace_path/__session__/`（一致） |
| 上传文件 | `<trace_root>/uploads/<scenario>/<trace_name>/` | 无 |
| SOTA 查询 | 消息流回退 | 直接加载 session pickle |
| 历史列表 | `GET /traces` 扫描 | 不适用 |

### 8.2 路径模板汇总

| 产物 | 路径模板 |
|------|---------|
| Trace pickle | `<storage_path>/<tag.path>/<PID链>/<时间戳>.pkl` |
| Session 快照 | `<LOG_SETTINGS.trace_path>/__session__/<loop_idx>/<step_idx>_<step_name>` |
| WebUI stdout | `<UI_SETTING.trace_folder>/<scenario>/<trace_name>.log` |
| WebUI 上传文件 | `<UI_SETTING.trace_folder>/uploads/<scenario>/<trace_name>/<filename>` |
| 工作区代码 | `RD_AGENT_SETTINGS.workspace_path/<UUID>/`（独立于 trace 系统） |

### 8.3 一句话总结

WebUI 任务的 trace 日志和 stdout 在 `UI_TRACE_FOLDER/<scenario>/<trace_name>/` 下，上传文件在 `uploads/` 子树；CLI 任务的所有产物在 `LOG_TRACE_PATH/` 下。两者唯一的交叉陷阱是 WebUI 任务的 `__session__/` 仍落到 `LOG_TRACE_PATH` 而非 trace 目录，SOTA 查询通过消息流回退来弥补。
