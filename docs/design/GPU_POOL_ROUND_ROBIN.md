# 多 GPU 轮转分配方案

> 类型：技术方案设计（新功能）
> 创建：2026-08-10
> 关联代码：`rdagent/log/server/app.py`
> 状态：**已实施**（commit `bcf8dba6`）

---

## 1. 背景

机器有 8 张 NVIDIA H20 GPU（每张 96GB），但其中 7 张被 sglang（DeepSeek-V3.1 LLM 推理服务）常驻占用，每张只剩 ~13GB 空闲。之前所有 RD-Agent 任务共享全部 GPU（Docker `count=-1`），实际只用 `cuda:0`，多个并发任务争抢同一张卡。

**目标**：每个新建任务自动分配到不同的物理 GPU，实现任务间 GPU 隔离。

---

## 2. 方案

### 2.1 原理

利用已有的 `_gpu_kwargs` 机制（`rdagent/utils/env.py:968`）：
- 当 `os.environ["CUDA_VISIBLE_DEVICES"]` 有值时 → `DeviceRequest(device_ids=[...])` 物理隔离
- 未设时 → `DeviceRequest(count=-1)` 暴露全部 GPU

让每个子进程在 `_run()` 入口设置不同的 `CUDA_VISIBLE_DEVICES`，即可把不同任务分配到不同物理 GPU。

### 2.2 工作机制

```
Flask 启动
  ↓
_detect_gpu_count()  →  nvidia-smi 探测 → 8 张卡
_gpu_pool = {}  （空的，表示全空闲）
  ↓
新建任务 1  →  _acquire_gpu() → GPU 0  →  CUDA_VISIBLE_DEVICES=0
新建任务 2  →  _acquire_gpu() → GPU 1  →  CUDA_VISIBLE_DEVICES=1
新建任务 3  →  _acquire_gpu() → GPU 2  →  CUDA_VISIBLE_DEVICES=2
...
新建任务 9  →  全部占用 → None → 共享全部 GPU（降级）
  ↓
任务 1 结束  →  下次 /upload 时检测 is_alive()=False → _release_gpu(0)
  ↓
新建任务 10 →  _acquire_gpu() → GPU 0（回收复用）
```

### 2.3 降级行为

| 场景 | 行为 |
|---|---|
| 无 GPU（CPU 环境） | `_gpu_total=0` → `_acquire_gpu()` 返回 None → 不设 `CUDA_VISIBLE_DEVICES` → `count=-1`（与之前一致） |
| 全部 GPU 占用 | 返回 None → 共享全部 GPU（不阻塞任务创建） |
| 任务结束 | 下次 `/upload` 时 `is_alive()=False` → 自动回收 GPU |

---

## 3. 改动详情（`rdagent/log/server/app.py`，单文件 +51 行）

### 3.1 GPU 池（模块级，`rdagent_processes` 之后）

```python
import threading

def _detect_gpu_count() -> int:
    """启动时自动探测可用 GPU 数量。"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5)
        return len([l for l in result.stdout.strip().split("\n") if l.strip()])
    except Exception:
        return 0

_gpu_pool_lock = threading.Lock()
_gpu_pool: set[int] = set()       # 已分配的 GPU id
_gpu_total: int = _detect_gpu_count()

def _acquire_gpu() -> int | None:
    """分配一个空闲 GPU。全部占用时返回 None。"""
    ...

def _release_gpu(gpu_id: int) -> None:
    """归还 GPU。"""
    ...
```

### 3.2 RDAgentTask 加 `assigned_gpu` 字段

```python
class RDAgentTask:
    def __init__(self, ..., assigned_gpu: int | None = None):
        self.assigned_gpu = assigned_gpu
```

### 3.3 `_run()` 子进程入口设置 CUDA_VISIBLE_DEVICES

```python
def _run(self) -> None:
    import os as _os
    # GPU 轮转：子进程隔离到分配的物理 GPU
    if self.assigned_gpu is not None:
        _os.environ["CUDA_VISIBLE_DEVICES"] = str(self.assigned_gpu)
```

> **关键**：`multiprocessing.Process` fork 时子进程继承父进程 environ 快照。`_run()` 在 fork 后的子进程内修改 `os.environ`，`_gpu_kwargs` 读到的是子进程的值（非父进程）。多个并发子进程互不干扰。

### 3.4 `/upload` 分配 + 回收

```python
# 并发限制 + GPU 回收
running_count = 0
for t in rdagent_processes.values():
    if t.is_alive():
        running_count += 1
    elif t.assigned_gpu is not None:
        _release_gpu(t.assigned_gpu)   # 回收已结束任务的 GPU
        t.assigned_gpu = None

# ... scenario 分发 ...

assigned_gpu = _acquire_gpu()
task = RDAgentTask(..., assigned_gpu=assigned_gpu)
task.start()
```

---

## 4. 为什么不改 Qlib YAML 或 env.py

| 组件 | 理由 |
|---|---|
| `env.py` `_gpu_kwargs` | **已支持** `CUDA_VISIBLE_DEVICES` → `device_ids` 物理隔离，无需改 |
| Qlib YAML `GPU: 0` | 物理隔离下容器只有 1 张卡，`cuda:0` 自动指向它，无需改 |
| `.env` | 不设 `CUDA_VISIBLE_DEVICES`（由 GPU 池动态分配，而非静态配置） |
| 前端 | 无需改 |

---

## 5. 验证结果（2026-08-10）

| 验证项 | 结果 |
|---|---|
| GPU 探测 | ✅ 自动探测到 8 张 H20 |
| 任务 1（blaring-relaxation） | ✅ GPU 0：`GPU selection: using specific GPUs ['0']` |
| 任务 2（green-nest） | ✅ GPU 1：`GPU selection: using specific GPUs ['1']` |
| Docker 物理隔离 | ✅ `DeviceIDs=[1]`（容器只看到分配的卡） |
| GPU 回收 | ✅ 代码确认 `_release_gpu` 在 `/upload` 并发检查中执行 |

---

## 6. 注意事项

- **sglang 不受影响**：sglang 是独立进程，不走 RD-Agent 的 GPU 池。GPU 池只管 RD-Agent 的 Docker 训练容器。
- **每张卡剩余显存**：sglang 占了 ~83GB/卡，RD-Agent 任务用剩余 ~13GB。对 LSTM（0.05MB 模型）和 LightGBM 足够。
- **单任务多卡**：当前方案是「多任务各用不同卡」（任务间隔离），不是「单任务用多卡」（DataParallel）。Qlib `GeneralPTNN` 不支持 DataParallel，单任务多卡需要改 Qlib 库代码。
