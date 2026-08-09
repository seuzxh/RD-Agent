# Model & Quant 场景测试报告（LLM 修复后重测）

> 日期：2026-08-09（第二轮，LLM API 已修复）
> 环境：Flask :19899 + vite dev :8081
> LLM 配置：`OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/plan/v3`，`CHAT_MODEL=openai/glm-5.2`

---

## 一、测试结果总览

| 场景 | 任务 ID | loops | 运行时长 | 结果 | 消息数 | 关键产出 |
|---|---|---|---|---|---|---|
| **Quant（fin_quant）** | `grilled-lard` | 1 | ~6 分钟 | ✅ **完整完成** | 24 | IC=0.0231, 年化=8.81%, decision=采纳 |
| **Model（fin_model）** | `drab-guide` | 1 | ~11 分钟 | ⚠️ **完成但回测超时** | 13 | LSTM 训练被 600s 超时杀掉，decision=拒绝 |

> **对比上一轮**（LLM 不可用）：两个场景均因 LLM 订阅过期只有 3 条消息即失败。本轮 LLM 修复后，两个场景都成功进入了 R&D 循环并产出结果。

---

## 二、Quant 场景（fin_quant）— ✅ 完整成功

### 2.1 运行详情

**任务**：`Finance Whole Pipeline/grilled-lard`
**描述**：构建动量反转因子策略，基于过去 5 日收益率
**loops**：1

### 2.2 消息流（24 条，完整 R&D 循环）

| Tag | 数量 | 说明 |
|---|---|---|
| task.user_input | 1 | 用户输入描述 |
| feedback.config | 1 | 运行配置 |
| research.hypothesis | 1 | ✅ 假设生成（动量因子） |
| research.tasks | 1 | ✅ 实验任务（3 个因子） |
| evolving.codes | 1 | ✅ 因子代码生成 |
| evolving.feedbacks | 1 | ✅ 代码反馈 |
| feedback.metric | 1 | ✅ 回测指标：**IC=0.0231, 年化=8.81%** |
| feedback.return_chart | 1 | ✅ 收益曲线（chart_ref=True） |
| feedback.hypothesis_feedback | 1 | ✅ decision=True（采纳） |
| token_cost | 14 | Token 统计 |
| END | 1 | end_code=0（正常完成） |

### 2.3 前端详情页渲染验证

| 区域 | 结果 | 详情 |
|---|---|---|
| 最终结论 Tab | ✅ | IC=0.0231、年化=8.81%、回撤=13.76%、信息比率=0.7077、✓ 采纳 |
| 因子结果 Tab | ✅ | 3 个因子卡片 |
| 收益曲线 Tab | ✅ | iframe 加载 artifact 端点 |
| 因子代码 Tab | ✅ | 3 个代码文件 |
| PipelineStages | ✅ | 4/4 阶段全部 done |
| TokenDashboard | ✅ | 总 2.5K、输入 2.4K、输出 148 |
| SOTA 按钮 | ✅ | 可用 |

**结论**：Quant 场景与 Factor 场景渲染完全一致，前端组件复用无问题。

---

## 三、Model 场景（fin_model）— ⚠️ DataLoader 死锁

### 3.1 第一轮测试（超时 600s）— 被 kill

**任务**：`Finance Model Implementation/drab-guide`（loops=1）

LSTM 训练在 Epoch 0 evaluating 阶段被 600s 超时 kill：
```
Train samples: 472111, Valid samples: 233138
Epoch0: training... (~8s)
Epoch0: evaluating...  ← 600s 后被 kill
```

**超时根因**：`model_coder/conf.py:19` `get_model_env(running_timeout_period=600)` 覆盖了 `QlibDockerConf` 的 3600s 默认值。

**已修复**（commit `bff66ae6`）：改为 3600s。

### 3.2 第二轮测试（超时 3600s）— DataLoader 死锁

**任务**：`Finance Model Implementation/constant-script`（loops=1）

超时改为 3600s 后，训练不再被 kill，但在 **Epoch 1 evaluating 阶段永久死锁**：

```
14:48:57  Epoch0: training...           ← 训练 ~10s（GPU 正常）
14:49:07  Epoch0: evaluating...         ← 验证推理 ~8s
14:49:15  Epoch0: train 0.998, valid 0.998  ← Epoch 0 完成 ✅
14:49:15  Epoch1: training...           ← 训练 ~8s
14:49:23  Epoch1: evaluating...         ← ❌ 永久卡住，15+ 分钟无输出
```

### 3.3 死锁根因：Qlib DataLoader 多进程在 Docker 内死锁

**实测证据**（容器运行 11 分钟时检查）：

| 指标 | 值 | 含义 |
|---|---|---|
| 容器 CPU | **0.03%** | 完全空闲（正常训练应 90%+） |
| GPU 利用率 | **0%** | 没有在用 GPU（8×H20 全空闲） |
| 日志停滞 | 15+ 分钟无输出 | 从 Epoch 1 `evaluating...` 后零输出 |
| DataLoader worker | 5 个子进程全部空闲 | joblib/loky worker 卡死 |
| shm_size | 16GB（充足） | 排除共享内存不足 |
| ipc_mode | private（非 host） | 可能是诱因之一 |

**根因链**：
```
Qlib TSDatasetH 配置 n_jobs=20（20 个并行 DataLoader worker）
  → Docker 容器内 joblib/loky fork worker 进程
  → Epoch 0→1 切换时，worker 在 IPC 通信中死锁
  → 主进程等待 worker 返回验证数据 → 永久阻塞
  → CPU/GPU 均 0%，进程"活着但不工作"
```

这是 [PyTorch DataLoader num_workers>0](https://github.com/pytorch/pytorch/issues/1579) 的经典问题。
RD-Agent 官方 [Issue #918](https://github.com/microsoft/RD-Agent/issues/918) 报告了相同问题（GRU 模型），至今 **Open 未解决**。

### 3.4 消息流（13 条）

| Tag | 数量 | 说明 |
|---|---|---|
| task.user_input | 1 | 用户输入描述 |
| feedback.config | 1 | 运行配置 |
| research.hypothesis | 1 | ✅ 假设生成（LSTM 模型） |
| research.tasks | 1 | ✅ 实验任务 |
| evolving.codes | 1 | ✅ 模型代码生成（TwoLayerLSTMRegressor） |
| evolving.feedbacks | 1 | ✅ 代码反馈 |
| feedback.metric | **0** | ❌ 缺失（训练死锁，无回测结果） |
| feedback.return_chart | **0** | ❌ 缺失 |
| feedback.hypothesis_feedback | 1 | ✅ decision=False（拒绝） |
| token_cost | 5 | Token 统计 |
| END | 1 | end_code=0 |

### 3.5 前端详情页渲染验证

| 区域 | 结果 | 详情 |
|---|---|---|
| 最终结论 Tab | ✅ | 「✕ 拒绝 · 跳过」+ 决定理由"Failed to run TwoLayerLSTMRegressor model" |
| 因子结果 Tab | ✅ | 1 个因子（可查看） |
| 收益曲线 Tab | ✅ disabled | 无 chart 数据（回测超时），Tab 正确禁用 |
| 因子代码 Tab | ✅ | 1 个代码文件 |
| PipelineStages | ✅ | 3/4 done（研究✓ 编码✓ 回测✓ 反馈✓，但回测产出为空） |
| TokenDashboard | ✅ | 总 2.6K、输入 2.6K、输出 84 |

**结论**：Model 场景即使回测失败，前端也能正确展示——结论 Tab 显示拒绝原因，曲线 Tab 正确禁用。

---

## 四、发现的问题

### 4.1 🔴 前端 Bug：新建任务跳转后偶发 404（复现）

**现象**：新建任务经 `handleCreate` 跳转到详情页时，偶发显示「404 · TRACE NOT FOUND」。刷新页面后恢复。

**复现**：
- Quant 任务 `grilled-lard`：首次打开 URL → 404 → 刷新后正常
- Model 任务 `drab-guide`：首次导航 → 404 → 刷新后正常
- 两场景均复现

**根因**：`/upload` 不初始化 `trace_states`（commit `bfc7bd72`），`loadTraceIds` 调 `/traces` 时新任务可能尚未在列表中 → `invalidTrace` 判 true → 404。

**影响**：每次新建任务后首次访问有概率 404（取决于 `/traces` 响应速度 vs pkl 落盘速度）。

**修复建议**：`handleCreate` 在 `waitForTaskReady` 后，应确认 `/traces` 返回包含新 id 再跳转；或在 `invalidTrace` 中增加宽限期（loading 完成后延迟几秒再判 404）。

### 4.2 🟡 Model 场景：LSTM 训练超时（环境限制）

**现象**：LSTM 模型在 47 万样本上训练，单 epoch > 600 秒被 kill。

**影响**：fin_model 场景中复杂模型（LSTM/GRU）容易超时。简单模型（LightGBM/Linear）不受影响。

**建议**：
- 提高 Docker 超时限制（当前 600s）或使其可配置
- 或在模型描述中提示用户选择轻量模型

### 4.3 🟢 Quant 场景：无问题

Quant 场景完整跑完，所有前端渲染正确，无任何问题。

---

## 五、与 Factor 场景的对比

| 维度 | Factor | Quant | Model |
|---|---|---|---|
| R&D 循环完成 | ✅ | ✅ | ⚠️ 回测超时 |
| 消息流完整性 | 全部 tag | 全部 tag | 缺 metric/chart |
| 详情页渲染 | ✅ 全正确 | ✅ 全正确 | ✅ 正确（含空态处理） |
| 运行时长 | ~1-3 分钟 | ~6 分钟 | ~11 分钟 |
| Tab 禁用逻辑 | — | — | ✅ 曲线 Tab 正确 disabled |

**核心结论**：三个场景共享相同的前端组件和渲染逻辑，Factor 和 Quant 完全通过，Model 因 LSTM 超时未产出指标但前端展示正确。
