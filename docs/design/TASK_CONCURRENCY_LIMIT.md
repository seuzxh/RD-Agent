# 任务并发限制：运行中任务达上限禁止新建

> 类型：技术方案设计（新功能）
> 创建：2026-07-26
> 关联代码：`rdagent/log/ui/conf.py`、`rdagent/log/server/app.py`、`web/src/multialpha/`
> 状态：**已实施**（commit `bd24aa9a`，2026-07-26 验证通过）

---

## 目录

- [1. 需求](#1-需求)
- [2. 现状分析](#2-现状分析)
- [3. 方案设计](#3-方案设计)
- [4. 改动清单](#4-改动清单)
- [5. 验证计划](#5-验证计划)

---

## 1. 需求

当已有 **10 个任务在执行**时，禁止新建任务，并给出明确提示。

**背景**：每个 RD-Agent 任务会 fork 子进程 + 拉起 Docker 容器跑 Qlib 回测，资源消耗大。无限制并发会导致机器资源耗尽、任务互相抢占、OOM 崩溃。

---

## 2. 现状分析

### 2.1 当前无任何并发限制

`/upload`（`app.py:902`）创建任务时直接 `task.start()` + 加入 `rdagent_processes`，不检查当前运行中的任务数。

### 2.2 判断「运行中」的依据

`RDAgentTask.is_alive()`（`app.py:142`）：
```python
def is_alive(self) -> bool:
    return self.process is not None and self.process.is_alive()
```

统计运行中任务数：
```python
running_count = sum(1 for t in rdagent_processes.values() if t.is_alive())
```

### 2.3 配置项已有先例

`UI_SETTING`（`rdagent/log/ui/conf.py`）已有 `max_inmemory_traces: int = 20`（LRU 上限），并发限制可同样加一个配置项，env_prefix 为 `UI_`（即环境变量 `UI_MAX_CONCURRENT_TASKS`）。

### 2.4 前端错误处理链路已就绪

```
NewTaskDialog.submit() → emit('submit') → MultiAlphaApp.handleCreate()
  → useMultiAlpha.createTask() → uploadTask() → POST /upload
  → 失败: result.error → throw new Error(result.error)
  → MultiAlphaApp.handleCreate catch → ElMessage.error(error.message)
```

后端只需返回 `{ "error": "..." }`，前端会自动弹 `ElMessage.error` 展示。

---

## 3. 方案设计

### 3.1 后端：配置项 + `/upload` 前置检查

**新增配置项**（`rdagent/log/ui/conf.py`）：
```python
# 运行中任务并发上限；超过则拒绝新建
max_concurrent_tasks: int = 10
```

**`/upload` 前置检查**（`app.py:970`，`target_name is None` 判断之前插入）：
```python
    # 并发限制：运行中任务达上限时拒绝新建
    max_concurrent = getattr(UI_SETTING, 'max_concurrent_tasks', 10)
    running_count = sum(1 for t in rdagent_processes.values() if t.is_alive())
    if running_count >= max_concurrent:
        return jsonify({
            "error": f"当前有 {running_count} 个任务正在运行（上限 {max_concurrent}），请等待部分任务完成后再新建"
        }), 429
```

**位置选择**：放在文件保存（`:919-931`）之后、scenario 分发（`:939+`）之前。理由：
- 文件已落盘（不浪费用户上传）
- 在 fork 子进程前拦截（不占资源）
- 早于 `target_name` 判断（所有 scenario 统一受限）

**HTTP 状态码**：`429 Too Many Requests`——语义最匹配（资源配额限制）。前端 `parseResponse`（`rdagent-api.ts:17`）对非 2xx 会抛 `ApiError`，但 `uploadTask` 的返回类型是 `{ id?, error? }`，走的是 `result.error` 分支（`use-multialpha.ts:166`），状态码不影响前端处理。

### 3.2 前端：打开对话框时预检（可选优化）

**目的**：在用户填完表单点「启动」之前就提示，体验更好。

**TopBar「新建任务」按钮**（`TopBar.vue:10`）打开对话框时，检查 `tasks` 中 running 数量，若达上限则禁用按钮或弹提示：

```ts
// MultiAlphaApp.vue:25 附近，openDialog 改造
function openDialog(method: TaskMethod) {
  const runningCount = tasks.value.filter(t => t.status === 'running').length
  if (runningCount >= 10) {  // 与后端 UI_MAX_CONCURRENT_TASKS 一致
    ElMessage.warning(`当前有 ${runningCount} 个任务运行中（上限 10），请等待部分完成后再新建`)
    return
  }
  dialogOpen.value = true
  requestAnimationFrame(() => dialogRef.value?.open(method))
}
```

> 注：前端的 `tasks` 状态来自 `/traces/status`（经 `_resolve_trace_status` 校正后准确）。前端 10 是硬编码（与后端默认值一致），若后端改了配置需同步。可接受——并发上限很少改。

---

## 4. 改动清单

| 文件 | 改动 | 类型 |
|---|---|---|
| `rdagent/log/ui/conf.py` | 新增 `max_concurrent_tasks: int = 10` | 配置 |
| `rdagent/log/server/app.py:970` 附近 | `/upload` 加并发计数检查，达上限返回 429 | 后端 |
| `web/src/multialpha/MultiAlphaApp.vue:25` | `openDialog` 加 running 计数预检（可选） | 前端 |

---

## 5. 验证计划

### 5.1 后端单元验证
```bash
# 模拟：将上限设为 0，验证任何新建都被拒
UI_MAX_CONCURRENT_TASKS=0 rdagent server_ui --port 19899
curl -X POST http://localhost:19899/upload -F "scenario=Finance Data Building" -F "loops=1" ...
# 预期：429 + {"error":"当前有 0 个任务...上限 0..."}
```

### 5.2 正常路径回归
```bash
# 默认上限 10，当前 0 个运行 → 新建成功
curl -X POST http://localhost:19899/upload ...
# 预期：200 + {"id":"Finance Data Building/xxx"}
```

### 5.3 前端验证
- running 任务 < 10：点「新建任务」→ 对话框正常打开 → 提交成功
- running 任务 = 10：点「新建任务」→ 弹 warning 提示，对话框不打开
- running 任务 = 10 且绕过前端直接 POST：后端返回 429 → `ElMessage.error` 展示错误信息
