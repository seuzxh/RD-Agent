# 任务状态判断修复：stop/异常终止后仍显示 running

> 类型：技术方案设计（bug 修复）
> 创建：2026-07-26
> 关联代码：`rdagent/log/server/app.py`
> 状态：**已实施**（commit `bd24aa9a`，2026-07-26 验证通过）

---

## 目录

- [1. 问题现象](#1-问题现象)
- [2. 根因分析](#2-根因分析)
- [3. 状态判断规则真值表](#3-状态判断规则真值表)
- [4. 修复方案](#4-修复方案)
- [5. 验证计划](#5-验证计划)
- [6. 风险与边界](#6-风险与边界)

---

## 1. 问题现象

用户点击「停止」或任务进程异常终止后，首页任务列表仍显示 **运行中（running）**，且状态永不纠正。

> **背景强化**：commit `45f6bbd0` 删除了首页 `/traces/status` 失败时的 N+1 降级路径（逐个调 `/trace` 推导状态）。降级路径删除后，**首页状态完全依赖 `/traces/status` 的准确性**，不再有前端纠正机制。因此本修复（让 `/traces/status` 给出正确状态）的必要性进一步提升。

实测（2026-07-26，`/traces/status`，仅统计 `Finance Data Building` 场景）：

| 状态 | 数量 | 说明 |
|---|---|---|
| running | 3 | **全部是幽灵任务**：`loops=[]`、`updated_at` 是 6 天前、进程早已不存在 |
| done | 4 | 正常 |

> 注：`Finance Prediction` 场景的任务不在本统计范围（该场景即将由另一会话移除）。

抽样 `Finance Data Building/baked-yeast`：
- `/traces/status` → `running`
- `/trace` 查消息流 → **12 条消息，含 END**（task.messages 里有 END，但没投影到 trace_states）
- 进程状态 → 不存在（6 天前启动，早已终止）

---

## 2. 根因分析

3 个相互关联的 bug，核心缺陷：**状态判断只看 tag，从不结合进程存活状态**。

### bug 1：`/control` stop 后未投影状态

**位置**：`app.py:1221-1228`（`/control` 端点，action=stop）

```python
# 现状：只 append 到 task.messages
if not task.messages or task.messages[-1].get("tag") != "END":
    task.messages.append({"tag": "END", ...})
    # ❌ 未调用 _update_trace_state()
    # → trace_states 里永远没有 END，_tags_seen 不含 END
```

**影响**：用户手动 stop 的任务，`/traces/status` 永远返回 running。

### bug 2：`/trace` 检测进程死亡补 END 后未投影状态

**位置**：`app.py:820-831`（`/trace` 端点，检测到 `task.process` 已死）

```python
# 现状：同样只 append，不投影
if task.process is not None and not task.is_alive():
    if not task.messages or task.messages[-1].get("tag") != "END":
        task.messages.append({"tag": "END", ...})
        # ❌ 未调用 _update_trace_state()
```

**影响**：进程崩溃/异常退出的任务，catalog 状态永不纠正。

### bug 3：状态判断逻辑不检查进程存活

**位置**：`app.py:240-250`（`_derive_status_from_tags`）+ `app.py:635-638`（`_index_trace_catalog_from_files`）

```python
def _derive_status_from_tags(tags_seen: set[str]) -> str:
    if "END" in tags_seen:
        return "done"
    if has_final_feedback and has_metric:
        return "done"
    if any("error" in t.lower() for t in tags_seen):
        return "error"
    return "running"   # ❌ 兜底默认 running，不检查进程是否真的在跑
```

**影响**：任何没收到 END/error/反馈+指标 的 trace（无论原因：崩溃、被 kill、stop、从未启动），都会被判 running，且由于 bug 1+2 的存在，状态永远不会被纠正。

### 数据流脱节示意

```
正常消息路径（/receive）:
  消息进来 → task.messages.append + _update_trace_state ✅（双写）

stop / 进程死亡路径（bug 1+2）:
  END 消息 → task.messages.append ✅
              _update_trace_state ❌（漏写）
              → trace_states 与 task.messages 脱节

状态查询（/traces/status）:
  只读 trace_states ❌（不知道进程已死）
  → 即使 task.messages 有 END，catalog 仍说 running
```

### bug 4：内存路径与 catalog 路径的「END 补齐」不一致

**位置**：`app.py:442-450`（`_read_trace_into`）vs `app.py:635-638`（`_index_trace_catalog_from_files`）

内存路径加载历史 trace 时，若最后消息距今 > 30 分钟会**自动补 END**：

```python
# _read_trace_into（内存路径，/trace 端点用）
now = datetime.now(timezone.utc)
if last_timestamp and (now - last_timestamp).total_seconds() > 1800:
    task.messages.append({"tag": "END", ...})   # ✅ 补 END
```

但 catalog 路径（启动时索引、`/traces/status` 查询用）**只看 pkl 文件路径名**，从不补 END：

```python
# _index_trace_catalog_from_files（catalog 路径）
if 'END' in tags_seen or ('feedback' in tags_seen and 'hypothesis' in tags_seen):
    status = 'done'
else:
    status = 'running'   # ❌ pkl 路径名不含 END 关键字 → 永远 running
```

**实测**：`baked-yeast`（6 天前终止）—— 内存消息流有 12 条含 END（30 分钟超时补的），但磁盘 26 个 pkl 的路径名里**没有 END** → catalog 判 running。

**影响**：两条路径对同一 trace 给出矛盾状态。重启后尤为严重（见下）。

### 进程重启后的状态（关键场景）

当 rdagent server 进程被杀（含所有子进程）后重启：

| 数据结构 | 重启后状态 |
|---|---|
| `rdagent_processes`（内存） | **清空** —— 所有进程对象消失 |
| `trace_states`（catalog） | 由 `_load_existing_traces` 从磁盘 pkl **重建** |

重建逻辑（`_index_trace_catalog_from_files`）的问题：
1. 只看 pkl **路径名**里的关键字（`END`/`feedback`/`hypothesis`），但 END 消息**通常不落盘成独立 pkl**（它是运行时/加载时动态追加的）
2. 因此正常完成的历史任务，只要磁盘没 END pkl，重建后一律判 running
3. 结合 bug 3 的「进程不在内存」，这些任务永远 running

**这意味着**：原方案中 `_resolve_trace_status` 若简单地把「进程不在内存」判为 error，会**把正常完成的历史任务误判 error**。必须区分「从未运行的幽灵」与「曾经运行但已结束」。

---

## 3. 状态判断规则真值表

修复后的完整判断逻辑：**tag 推导结果 × 进程存活 → 最终状态**。

> 实测验证（见下方），tag 本身足以区分「正常完成」与「异常终止」，无需引入时间新鲜度：
> - **done 任务**（5/5）：磁盘 pkl 路径都含 `feedback` + `hypothesis`
> - **running 幽灵**（3/3）：只有 `feedback`，**没有 `hypothesis`**（跑到一半死了）
>
> 因此 `_index_trace_catalog_from_files:635` 的 `feedback+hypothesis → done` 判断**本身有效**。真正的问题是：既没 END、也没 feedback+hypothesis 的任务（异常终止），兜底判 running 且永不纠正。

| tag 推导（`_derive_status_from_tags`） | 进程存活检查 | **最终状态** | 场景 |
|---|---|---|---|
| `done`（有 END，或 feedback+metric） | （不检查） | **done** | 正常完成 |
| `error`（有 error tag） | （不检查） | **error** | 运行中报错 |
| `running` | 存活（`is_alive()=True`） | **running** | 正在跑 |
| `running` | 已死/不在内存 | **error** | 异常终止 / 历史幽灵 |

**设计决策**：进程已死但无完成信号（END/feedback+hypothesis）的任务判 `error`，理由：
- 区分「正常完成」与「异常终止」，用户看到红色「异常」能察觉问题
- 避免把崩溃/被 kill 的任务误标为「已完成」
- 不会误伤正常完成的历史任务（它们有 feedback+hypothesis，tag 判定优先返回 done，不走到进程检查）

---

## 4. 修复方案

4 处改动，1 个新函数。全部在 `rdagent/log/server/app.py`。

### 改动 1：新增 `_resolve_trace_status` 函数

**位置**：`app.py:250`（`_derive_status_from_tags` 之后）

```python
def _resolve_trace_status(external_id: str, catalog_status: str) -> str:
    """结合 catalog 状态 + 进程存活状态，给出最终对外状态。

    - catalog 已判 done/error → 直接采用（完成信号可靠，无需检查进程）
    - catalog 判 running → 检查进程是否真的存活：
        存活 → running；已死/不存在 → error（异常终止）

    注意：直接用 catalog 已存的 status（由 _index_trace_catalog_from_files
    或 _update_trace_state 推导），不重新调 _derive_status_from_tags——
    因为 catalog 路径的 _tags_seen 存的是路径关键字（'feedback'/'hypothesis'），
    粒度与 _derive_status_from_tags 要求的完整 tag 名不一致。
    """
    if catalog_status != "running":
        return catalog_status

    internal_id = str(log_folder_path / external_id)
    task = rdagent_processes.get(internal_id)
    if task is not None and task.is_alive():
        return "running"
    return "error"
```

**要点**：
- 直接读 `state["status"]`（catalog 已推导好的），不重新调 `_derive_status_from_tags`——避免 tag 粒度不一致问题（catalog 存 `'feedback'`，而 `_derive_status_from_tags` 找 `'feedback.hypothesis_feedback'`）
- catalog 判 done 的历史任务（有 feedback+hypothesis 路径关键字）直接返回 done，不走进程检查 → **不会被误判 error**
- 只有 catalog 判 running 时才查进程存活

### 改动 2：`/traces/status` 查询出口实时校正

**位置**：`app.py:894-897`（`list_trace_statuses`）

```python
# 现状
items = [
    {"id": tid, **_trace_state_public(state)}
    for tid, state in trace_states.items()
]

# 修复后：用 _resolve_trace_status 校正 status
items = [
    {"id": tid, **_trace_state_public({
        **state,
        "status": _resolve_trace_status(tid, state["status"]),
    })}
    for tid, state in trace_states.items()
]
```

**作用**：即使 catalog 没更新（bug 1/2 的漏写），查询时也能结合进程存活给出正确状态。这是**兜底防线**，确保任何情况下 `/traces/status` 都不会误报 running。

### 改动 3：`/control` stop 后投影状态（修 bug 1）

**位置**：`app.py:1228`（append END 之后追加一行）

```python
            task.messages.append({"tag": "END", ...})
            _update_trace_state(_trace_id_to_external(id), task.messages[-1])  # 新增
```

**效果**：stop 后 `trace_states` 立即含 END → `_derive_status_from_tags` 判 done。

### 改动 4：`/trace` 检测进程死亡补 END 后投影状态（修 bug 2）

**位置**：`app.py:831`（append END 之后追加一行）

```python
            task.messages.append({"tag": "END", ...})
            _update_trace_state(_trace_id_to_external(trace_id), task.messages[-1])  # 新增
```

**效果**：进程异常终止被检测到时，catalog 立即同步。

> 注：改动 3/4 让 catalog 保持准确（写入路径修复）；改动 2 是查询出口的兜底（读取路径修复）。三者结合，无论哪一层出问题，状态都不会误报。

---

## 5. 验证计划

### 5.1 语法校验
```bash
python3 -c "import ast; ast.parse(open('rdagent/log/server/app.py').read()); print('OK')"
```

### 5.2 重启服务后实测 `/traces/status`

| 预期 | 验证方法 |
|---|---|
| 原 9 个幽灵 running → 全部变 error | `curl /traces/status \| grep running` 应为空或仅剩真存活任务 |
| 原 5 个 done 保持 done | tag 判定优先，不受进程检查影响 |
| 真正运行中的任务仍显示 running | 新建任务后立即查询 |

### 5.3 功能回归

| 场景 | 操作 | 预期状态 |
|---|---|---|
| 手动 stop | 新建任务 → 点停止 → 查 status | done（stop 写了 END） |
| 进程崩溃 | 新建任务 → kill 进程 → 查 status | error（进程已死 + END 被补投影） |
| 正常完成 | 任务跑完 → 查 status | done（收到 END/feedback） |

---

## 6. 风险与边界

### 不改动的部分
- `_derive_status_from_tags`：保持纯 tag 判断，作为 `_resolve_trace_status` 的子步骤
- `_update_trace_state`：收到 END 后自然判 done，逻辑正确
- 前端：`error` 状态已有完整 UI 映射（TaskSidebar 红色点 + 「异常」标签，见 `TaskSidebar.vue:17-18,38`）

### 已知边界
- **LRU 驱逐后的历史任务**：被 `_evict_if_needed` 从 `rdagent_processes` 删除的任务，`_resolve_trace_status` 会判 error（进程不在内存）。这是正确行为——驱逐的前提就是 `is_alive()=False`（见 `app.py:397`）。
- **性能**：`_resolve_trace_status` 对每个 trace 做一次字典查找（`rdagent_processes.get`），O(1)，`/traces/status` 整体仍为 O(n)，无性能影响。

---

## 附：改动清单

| 文件 | 行（约） | 改动类型 | 内容 |
|---|---|---|---|
| `rdagent/log/server/app.py` | 250 后 | 新增函数 | `_resolve_trace_status(external_id, tags_seen)` |
| `rdagent/log/server/app.py` | 894 | 修改 | `list_trace_statuses` 出口校正 status |
| `rdagent/log/server/app.py` | 831 | 新增 1 行 | `/trace` 补 END 后调 `_update_trace_state` |
| `rdagent/log/server/app.py` | 1228 | 新增 1 行 | `/control` stop 后调 `_update_trace_state` |
