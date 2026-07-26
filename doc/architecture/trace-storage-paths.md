# RD-Agent 场景任务信息存放路径规则

> 本文档梳理 rd-agent 场景任务（webUI 任务 + CLI 任务）所有产物的存放路径规则，覆盖 trace pickle、stdout 日志、上传文件、session dump 等落盘位置，并指出两个独立根目录的错位陷阱。

---

## 1. 两个相互独立的根目录

rd-agent 的存储路径由**两套独立配置**控制，务必先区分：

| 配置 | 环境变量 | 默认值 | 作用 | 定义位置 |
|---|---|---|---|---|
| `UI_SETTING.trace_folder` | `UI_TRACE_FOLDER` | `./git_ignore_folder/traces` | **服务端聚合视图根**：HTTP `/upload` `/traces` `/stdout` 用它扫历史、落盘 webUI 任务 | [`rdagent/log/ui/conf.py:21`](../../RD-Agent/rdagent/log/ui/conf.py#L21) |
| `LOG_SETTINGS.trace_path` | `LOG_TRACE_PATH` | `./log/<UTC timestamp>` | **单进程写入根**：`FileStorage` 写 pickle 的目录；`LoopBase.session_folder` 也基于它 | [`rdagent/log/conf.py:13`](../../RD-Agent/rdagent/log/conf.py#L13) |

两者在 webUI 任务里**不会自动对齐**（见 [§5](#5-已知路径不一致webui-任务的-__session__-错位)）。

代码中 `log_folder_path = Path(UI_SETTING.trace_folder).absolute()`（[`app.py:175`](../../RD-Agent/rdagent/log/server/app.py#L175)），即 `trace_root`。

---

## 2. WebUI 任务路径规则（`POST /upload`）

对一次上传任务：

- `scenario` = 表单字面值（如 `"Finance Data Building"`）
- `trace_name` = `randomname.get_name()`；Data Science 场景为 `f"{competition}-{randomname.get_name()}"`
- 返回给前端的 trace_id = `f"{scenario}/{trace_name>"`（相对路径）

### 2.1 落盘规则

参考 [`app.py:497-503`](../../RD-Agent/rdagent/log/server/app.py#L497-L503)、[`app.py:507-520`](../../RD-Agent/rdagent/log/server/app.py#L507-L520)：

| 内容 | 路径 |
|---|---|
| 上传的原始文件 | `<trace_root>/uploads/<scenario>/<trace_name>/<filename>`（`secure_filename` + 路径越界校验） |
| Trace pickle（FileStorage 主输出） | `<trace_root>/<scenario>/<trace_name>/` |
| 子进程 stdout 日志 | `<trace_root>/<scenario>/<trace_name>.log`（**注意是 trace_name 加 `.log` 后缀，与 trace 目录同级**） |
| 进程字典 key | `str(<trace_root>/<scenario>/<trace_name>)`（绝对路径） |

### 2.2 子进程启动时的路径重写

子进程启动时（[`app.py:130-135`](../../RD-Agent/rdagent/log/server/app.py#L130-L135)）调用：

```python
rdagent_logger.set_storages_path(self.log_trace_path)
```

把 `FileStorage.path` 和 `WebStorage.path` 都改写成 `<trace_root>/<scenario>/<trace_name>`，所以 webUI 任务的**实时 trace pickle** 落在 trace 目录下。

### 2.3 scenario → target_name 映射

[`app.py:524-556`](../../RD-Agent/rdagent/log/server/app.py#L524-L556) 中硬编码：

| scenario 字面值 | target_name | 入口 |
|---|---|---|
| `Finance Data Building` | `fin_factor` | [`factor.py`](../../RD-Agent/rdagent/app/qlib_rd_loop/factor.py) |
| `Finance Model Implementation` | `fin_model` | [`model.py`](../../RD-Agent/rdagent/app/qlib_rd_loop/model.py) |
| `Finance Whole Pipeline` | `fin_quant` | [`quant.py`](../../RD-Agent/rdagent/app/qlib_rd_loop/quant.py) |
| `Finance Data Building (Reports)` | `fin_factor_report` | [`factor_from_report.py`](../../RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py) |

未知 scenario 返回 `{"error": "Unknown scenario"}`。

---

## 3. CLI 任务路径规则（`rdagent fin_factor` 等）

- 写入根 = `LOG_SETTINGS.trace_path`（默认 `./log/<UTC timestamp>`）
- `FileStorage` pickle：直接写在该根下
- `LoopBase.session_folder = Path(LOG_SETTINGS.trace_path) / "__session__"`（[`loop.py:127`](../../RD-Agent/rdagent/utils/workflow/loop.py#L127)）
- Session dump 文件：`<trace_path>/__session__/<loop_idx>/<step_idx>_<step_name>`（如 `__session__/1/0_propose`，见 [`loop.py:307`](../../RD-Agent/rdagent/utils/workflow/loop.py#L307)）
- `--path` 恢复：可指向旧 trace 目录（含或不含 `__session__` 后缀均兼容，见 [`loop.py:480-515`](../../RD-Agent/rdagent/utils/workflow/loop.py#L480-L515)）

---

## 4. FileStorage 内部布局（任意根目录下通用）

`log_object(obj, tag="a.b.c")` 的落盘规则，参考 [`storage.py:38-66`](../../RD-Agent/rdagent/log/storage.py#L38-L66)：

- **目录**：`<storage.path>/a/b/c/`（tag 中的 `.` 转换为路径分隔符）
- **文件名**：`<YYYY-MM-DD_HH-MM-SS-ffffff>.<ext>`，扩展名由 `save_type` 决定：
  - `pkl`（默认）—— pickle 二进制
  - `json` —— JSON 文本
  - `text` —— 纯文本
- `iter_msg()` 用 `**/*.pkl` 递归扫描，从相对路径反推 tag；`debug_llm.pkl` 会被跳过
- `truncate(time)` 直接删除 timestamp 晚于 `time` 的所有 `.pkl`，并清理空目录

---

## 5. 已知路径不一致：webUI 任务的 `__session__` 错位

**关键坑**：webUI 任务的 `__session__/` **不在** `<trace_root>/<scenario>/<trace_name>/` 下，而在默认的 `LOG_SETTINGS.trace_path` 下（即 `./log/<UTC timestamp>/__session__/`）。

### 5.1 根因

`LoopBase.__init__` 在 `fin_factor(**kwargs)` 内部实例化时才计算 `session_folder`（[`loop.py:127`](../../RD-Agent/rdagent/utils/workflow/loop.py#L127)），此时读的是 `LOG_SETTINGS.trace_path`；而 `set_storages_path()` 只改 `storage.path`，**不会**回写 `LOG_SETTINGS.trace_path`。

### 5.2 后果与回退策略

参考 [`app.py:780-818`](../../RD-Agent/rdagent/log/server/app.py#L780-L818)、[API.md §2.8](../reference/API.md)：

- SOTA 查询找不到 `<trace_root>/<scenario>/<trace_name>/__session__/`
- 回退到从 `/trace` 消息流提取 SOTA（找最后一条 `research.hypothesis` + `feedback.metric` + `evolving.codes` + `feedback.hypothesis_feedback`），结果带 `"source": "message_stream"`

### 5.3 webUI task vs CLI task 的差异

| 任务类型 | session 位置 | SOTA 查询路径 |
|---|---|---|
| CLI task | `log/<timestamp>/__session__/` | 直接加载 session pickle |
| webUI task | 默认 `LOG_SETTINGS.trace_path/__session__/`（与 trace pickle 不同目录） | 消息流回退（`source: "message_stream"`） |

---

## 6. 历史 trace 发现与 stdout 解析

### 6.1 `GET /traces`

`_collect_existing_trace_ids`（[`app.py:355-374`](../../RD-Agent/rdagent/log/server/app.py#L355-L374)）：

- 扫描 `<trace_root>/*/*`（即 `<scenario>/<trace_name>` 二级结构）
- 排除 `uploads/` 出现在相对路径中的目录
- 要求目录内 `rglob("*.pkl")` 至少命中一个
- 返回相对 posix id 列表

### 6.2 `GET /stdout?id=<trace_id>`

`_resolve_stdout_path`（[`app.py:200-232`](../../RD-Agent/rdagent/log/server/app.py#L200-L232)）：

1. **运行中任务**：直接取内存里 `task.stdout_path`（验证在 `trace_root` 内）
2. **历史任务**：由 `<trace_id>` 推导为 `<trace_root>/<scenario>/<trace_name>.log`（把尾部 trace_name 替换为 `trace_name.log`）
3. 路径越界或文件不存在 → 400/404

---

## 7. 路径规则速查表

设 `trace_root = Path(UI_SETTING.trace_folder).absolute()`：

```
<trace_root>/
├── uploads/                                    # 上传文件隔离区
│   └── <scenario>/
│       └── <trace_name>/
│           └── <filename>                      # secure_filename 处理后
├── <scenario>/
│   ├── <trace_name>/                           # FileStorage 主输出（pickle/json/text）
│   │   └── <tag.path>/                         # tag 中的 . 转为 /
│   │       └── <YYYY-MM-DD_HH-MM-SS-ffffff>.pkl
│   └── <trace_name>.log                        # 子进程 stdout（与 trace 目录同级）
└── (CLI 任务不在此根下，见 §3)
```

CLI 任务独立根 `LOG_SETTINGS.trace_path`（默认 `./log/<UTC timestamp>/`）：

```
<LOG_TRACE_PATH>/
├── <tag.path>/
│   └── <timestamp>.pkl                         # FileStorage pickle
└── __session__/                                # LoopBase session dump
    └── <loop_idx>/
        └── <step_idx>_<step_name>              # 如 0_propose
```

---

## 8. 一句话总结

webUI 任务的所有产物都在 `<UI_TRACE_FOLDER>/<scenario>/<trace_name>{/,*.log}` 下（上传文件另走 `uploads/` 子树）；CLI 任务在 `<LOG_TRACE_PATH>/` 下（含 `__session__/`）。两者唯一的交叉陷阱是 webUI 任务的 `__session__/` 仍落到默认 `LOG_TRACE_PATH` 而非 trace 目录，SOTA 查询走消息流回退解决。

---

## 9. 实际产物示例（基于当前项目快照）

以下示例取自 `RD-Agent/git_ignore_folder/traces/` 与 `RD-Agent/log/` 的真实任务产物，用于印证上述规则。`UI_TRACE_FOLDER` 当前值为默认 `./git_ignore_folder/traces`。

### 9.1 webUI 任务：`Finance Data Building/baked-yeast`

对应 §2.1 落盘规则，目录结构（实际扫描结果）：

```
git_ignore_folder/traces/
├── Finance Data Building/
│   ├── baked-yeast/                          # trace pickle 目录（§2.1）
│   │   ├── Loop_0/                           # tag "Loop_0.direct_exp_gen.token_cost" → 目录
│   │   │   └── direct_exp_gen/
│   │   │       ├── token_cost/3851031-3853142/2026-07-20_15-00-45-072528.pkl
│   │   │       ├── debug_tpl/3851031-3853142/2026-07-20_*.pkl
│   │   │       ├── LITELLM_SETTINGS/3851031-3853142/
│   │   │       └── time_info/3851031-3853142/
│   │   ├── RDLOOP_SETTINGS                   # tag → 单文件
│   │   ├── RD_AGENT_SETTINGS
│   │   ├── debug_tpl/
│   │   └── scenario/
│   └── baked-yeast.log                       # stdout 日志（与 trace 目录同级，143KB）
└── uploads/Finance Data Building/baked-yeast/  # 该任务未上传文件，但路径已预留
```

印证点：

- **§2.1 同级规则**：`baked-yeast/` 与 `baked-yeast.log` 同在 `Finance Data Building/` 下
- **§4 tag → 目录**：tag `Loop_0.direct_exp_gen.token_cost` 转换为 `Loop_0/direct_exp_gen/token_cost/`
- **§4 PID 维度**：`token_cost/3851031-3853142/` 中的 `3851031-3853142` 是父 PID-子 PID 链（[`logger.py:122-133`](../../RD-Agent/rdagent/log/logger.py#L122-L133) 的 `get_pids()` 生成）
- **§4 文件名**：`2026-07-20_15-00-45-072528.pkl` 符合 `<YYYY-MM-DD_HH-MM-SS-ffffff>.pkl`
- **§5 错位印证**：`baked-yeast/` 下**无 `__session__/`** 子目录（`grep -i session` 无命中），session 实际落到了 `RD-Agent/log/<某个 UTC timestamp>/__session__/`
- **§2.2 路径重写印证**：`baked-yeast.log` 第二行日志显示子进程在 `_init_base_features` 阶段访问的 uploads 路径为 `traces/uploads/Finance Data Building/baked-yeast`，但该子目录不存在（任务未上传文件），代码降级为 "Keeping default base features"

### 9.2 webUI 任务：`Finance Prediction/bipartite-module-20260724`

`Finance Prediction` scenario 在 §2.3 映射表里未列出（实际为平台新增的预测场景），但目录布局仍遵循 §2.1：

```
git_ignore_folder/traces/Finance Prediction/
├── bipartite-module-20260724/                # trace_name 含日期后缀
├── bipartite-module-20260724.log
├── grouchy-clerk-20260724/
├── grouchy-clerk-20260724.log
└── ...
```

说明 `randomname.get_name()` 生成的随机名后可附加日期标记（多为人工指定或场景特化逻辑）。

### 9.3 CLI 任务：`log/2026-07-20_15-04-04-760544`

对应 §3 CLI 任务路径规则。`LOG_TRACE_PATH` 默认值为 `./log/<UTC timestamp>`，实际目录：

```
RD-Agent/log/2026-07-20_15-04-04-760544/
└── __session__/
    ├── 0/                                    # loop_idx = 0
    ├── 1/                                    # loop_idx = 1
    │   ├── 0_direct_exp_gen                  # step_idx=0, step_name=direct_exp_gen
    │   ├── 1_coding                          # step_idx=1, step_name=coding
    │   ├── 2_running                         # step_idx=2, step_name=running
    │   ├── 3_feedback                        # step_idx=3, step_name=feedback
    │   └── 4_record                          # step_idx=4, step_name=record
    └── 2/                                    # loop_idx = 2
```

印证点：

- **§3 session_folder**：`Path(LOG_SETTINGS.trace_path) / "__session__"` → `log/2026-07-20_15-04-04-760544/__session__/`
- **§3 dump 文件命名**：`<step_idx>_<step_name>` → `0_direct_exp_gen`、`1_coding`、`2_running`、`3_feedback`、`4_record`，对应 [`loop.py:307`](../../RD-Agent/rdagent/utils/workflow/loop.py#L307) 的 `self.dump(self.session_folder / f"{li}" / f"{si}_{name}")`
- **§3 五步主循环**：5 个 step 文件印证了 [data-flow.md §1](./data-flow.md) 中 RDLoop 的 5 步迭代（propose/coding/running/feedback/record），其中 `direct_exp_gen` 即 propose 步的实现名

### 9.4 SOTA 查询场景对照

基于上述两类任务，SOTA 查询路径分流（§5.2 回退策略的实际效果）：

| 任务 | `__session__/` 位置 | SOTA 查询路径 | 响应 `source` 字段 |
|---|---|---|---|
| CLI 任务 §9.3 | `log/2026-07-20_15-04-04-760544/__session__/` ✅ 存在 | 直接加载 session pickle | 无 `source` 字段 |
| webUI 任务 §9.1 | `traces/.../baked-yeast/__session__/` ❌ 不存在 | 从 `/trace` 消息流提取 | `"message_stream"` |

### 9.5 `/traces` 历史列表的实际返回

`GET /traces` 扫描 `traces/*/*` 后实际返回（按字典序）：

```
Finance Data Building/adaptive-map
Finance Data Building/angry-gear        # 注意：仅 .log 无目录的会被跳过
Finance Data Building/atomic-pixel       # （前提是该目录下有 *.pkl）
Finance Data Building/baked-yeast
Finance Data Building/best-quail
Finance Data Building/camel-technician
Finance Data Building/careful-levee
...
Finance Prediction/bipartite-module-20260724
Finance Prediction/grouchy-clerk-20260724
...
```

印证点（§6.1）：

- 二级结构 `<scenario>/<trace_name>` 作为相对 posix id
- `Invalid Scenario/` 下无 pkl 的目录不会出现
- `Prediction History/` 下是 `.json` 文件（非 pkl）也不会出现
- `uploads/` 子树被排除

---

## 附录：路径规则与文档章节对照

| 真实示例 | 印证章节 | 关键规则 |
|---|---|---|
| `baked-yeast/` 与 `baked-yeast.log` 同级 | §2.1 | stdout 与 trace 目录同级，加 `.log` 后缀 |
| `Loop_0/direct_exp_gen/token_cost/` | §4 | tag 的 `.` 转为路径分隔符 |
| `3851031-3853142/`（PID 链子目录） | §4 + logger.py docstring | 按 PID 维度隔离并发 trace |
| `2026-07-20_15-00-45-072528.pkl` | §4 | `<YYYY-MM-DD_HH-MM-SS-ffffff>.pkl` |
| `baked-yeast/` 无 `__session__/` | §5 | webUI 任务的 session 错位到 `LOG_TRACE_PATH` |
| `log/2026-07-20_15-04-04-760544/__session__/1/0_direct_exp_gen` | §3 | `<loop_idx>/<step_idx>_<step_name>` |
| `traces/uploads/Finance Data Building/baked-yeast/` 不存在但日志引用 | §2.1 | uploads 路径已预留，无文件时降级 |
