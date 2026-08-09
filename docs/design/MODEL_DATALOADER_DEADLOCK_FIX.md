# Model 场景 DataLoader 死锁修复方案

> 类型：技术方案设计（bug 修复）
> 创建：2026-08-09
> 关联：[测试报告](../testing/WEBUI_MODEL_QUANT_TEST_REPORT_20260809.md) §3、RD-Agent 官方 [Issue #918](https://github.com/microsoft/RD-Agent/issues/918)
> 状态：**待决策**

---

## 1. 问题

Model 场景（fin_model）的 LSTM/GRU 等神经网络模型在 Docker 容器内训练时，Epoch 1 的 evaluating（验证集推理）阶段永久死锁。

- CPU 0.03%、GPU 0% — 进程活着但不工作
- Qlib `TSDatasetH` 配置 `n_jobs=20`（20 个 DataLoader worker）
- Docker `ipc_mode=private`、`shm_size=16g`

本质是 PyTorch DataLoader `num_workers > 0` 在 Docker 容器内的经典死锁问题（[pytorch#1579](https://github.com/pytorch/pytorch/issues/1579)）。

---

## 2. 修复方案对比

### 方案 A：Qlib config 设 `n_jobs: 1`（推荐）

**改动位置**：`rdagent/scenarios/qlib/experiment/model_template/` 下的 Qlib config YAML 模板

**原理**：将 DataLoader worker 数从 20 改为 1（单进程加载数据），从根本上消除多进程 IPC 死锁。

**优点**：
- 根治死锁
- 改动极小（YAML 配置一行）
- 不影响 Docker/GPU 配置

**缺点**：
- 数据加载速度变慢（单进程 vs 20 进程并行）。但实测训练本身只需 ~8s/epoch，瓶颈在 GPU 计算而非数据加载，单进程影响有限

**具体改动**：
```yaml
# model_template/conf_baseline_factors_model.yaml（或等价配置）
# 将 n_jobs 从默认 20 改为 1
n_jobs: 1
```

或在不改模板的前提下，在 Docker env 中注入：
```python
# model_runner.py 或 env_to_use 字典里加
"n_jobs": "1"
```

---

### 方案 B：Docker `--ipc=host`

**改动位置**：`rdagent/utils/env.py` `QlibDockerConf` 或 Docker run 参数

**原理**：让容器使用宿主机的 IPC namespace，避免 private IPC 的共享内存限制导致的 worker 死锁。

**优点**：
- 保持 `n_jobs=20` 的并行加载速度
- 社区广泛推荐的 Docker DataLoader 死锁修复方法

**缺点**：
- 降低容器隔离性（共享宿主机 IPC namespace）
- 需要确认 Docker daemon 允许 `--ipc=host`
- 不是 100% 可靠（部分 case 仍可能死锁）

**具体改动**：
```python
# rdagent/utils/env.py QlibDockerConf
# 方式 1：加 ipc_mode 配置
ipc_mode: str | None = "host"  # 使用宿主机 IPC

# 方式 2：在 docker run 时加参数
# env.py 的 run 方法里：
# containers.run(..., ipc_mode="host", ...)
```

---

### 方案 C：`multiprocessing_context='spawn'`

**改动位置**：Qlib 的 PyTorch NN 训练代码（`qlib/contrib/model/pytorch_nn.py`）

**原理**：将 DataLoader 的多进程启动方式从 `fork`（默认）改为 `spawn`，避免 fork 导致的文件描述符/锁状态继承问题。

**优点**：
- 根治 fork 导致的死锁
- 保持并行加载

**缺点**：
- 改的是 Qlib 库代码（非本项目代码），升级 Qlib 后改动会丢失
- `spawn` 启动慢（每次创建 worker 需重新 import）

**具体改动**：
```python
# qlib/contrib/model/pytorch_nn.py 的 DataLoader 创建处
DataLoader(
    dataset,
    batch_size=batch_size,
    num_workers=self.n_jobs,
    multiprocessing_context="spawn",  # 新增
)
```

---

### 方案 D：限制 LLM 生成的 `n_epochs`（缓解，非根治）

**改动位置**：Model 场景的 LLM prompt（system prompt 或 hypothesis specification）

**原理**：约束 LLM 生成的模型配置中 `n_epochs` 为较小值（如 3-5），减少 epoch 切换次数，降低死锁触发概率。

**优点**：
- 不改任何运行时代码
- 加快单次验证速度

**缺点**：
- **不能根治**——死锁可能在第 1 次 epoch 切换就触发（实测 Epoch 1 即死锁）
- 减少训练轮次可能影响模型质量

---

## 3. 推荐方案

**方案 A（`n_jobs: 1`）为主**，理由：

1. **根治**：从源头消除多进程死锁
2. **最小改动**：一行配置
3. **性能影响可接受**：实测 epoch 训练 ~8s（GPU 计算），数据加载不是瓶颈
4. **官方社区主流建议**：PyTorch 社区对 Docker 内 DataLoader 死锁的首选修复

**可选叠加方案 B（`--ipc=host`）**：如果 `n_jobs=1` 后仍有偶发问题，叠加 `ipc=host` 双保险。

---

## 4. 验证计划

1. 改 `n_jobs: 1` 后重新创建 Model 任务（LSTM, loops=1）
2. 观察：Epoch 0→1→2... 是否连续完成（不再卡在 evaluating）
3. 确认：训练完成后产出 `feedback.metric`（IC/年化等指标）
4. 确认：前端详情页显示完整结论（不再"拒绝 · 跳过"）
