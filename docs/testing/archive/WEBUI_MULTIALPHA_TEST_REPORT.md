# multiα1pha webUI 测试报告（第一轮 + 修复验证）

> 测试时间：2026-07-24
> 测试目标：multiα1pha webUI 业务功能、页面交互、页面展示优化
> 测试环境：
> - 后端：`rdagent server_ui` 运行在本机 `0.0.0.0:19899`（Python）
> - 前端：vite dev server（使用修复后的 `vite.config.ts`）
> - 浏览器测试：Trae IDE integrated browser MCP
> - 测试用例文档：[docs/WEBUI_MULTIALPHA_TEST_CASES.md](../WEBUI_MULTIALPHA_TEST_CASES.md)

---

## 1. 测试执行摘要

| 维度 | 覆盖情况 | 结论 |
|---|---|---|
| 业务功能 | 落地页、任务列表、任务详情、结果工作区、SOTA、股池预测、健康检查、新建任务弹窗、运行任务/日志 | 核心链路可跑通；本轮发现并修复 3 个前端问题；发现 1 个后端预测执行问题 |
| 页面交互 | 路由跳转、tab 切换、AgentFlow 展开、Loop 切换、下载/复制按钮、日志搜索/展开 | 正常 |
| 页面展示优化 | 布局、色彩、字体、空状态、加载态、数字格式化 | 整体一致，修复后 Token 面板与任务列表状态正常 |

---

## 2. 已修复的问题

### ✅ 问题 1：vite dev proxy 指向不可达 IP 且缺少 `/health`

- **现象**：`localhost:8081` 前端无法加载任务列表/预测实验；健康检查弹窗内容为空。
- **根因**：[web/vite.config.ts#L49-L58](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/vite.config.ts#L49) 的 dev proxy 硬编码指向 `http://115.190.106.124:19899`（本机不可达），且未代理 `/health`。
- **修复**：已将 proxy 目标改为 `http://localhost:19899`，并补全 `/health` 代理。
- **验证**：任务列表、预测实验、健康检查弹窗均正常。

### ✅ 问题 2：任务侧边栏状态不准确

- **现象**：除当前查看任务外，其余历史任务均显示「待查看」。
- **根因**：`use-multialpha.ts` 的 `statuses` 仅在 `selectTrace` 时赋值。
- **修复**：[web/src/multialpha/use-multialpha.ts#L39-L63](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/use-multialpha.ts#L39) 在 `loadTraceIds()` 中先从 cache 取状态，再后台顺序补抓未缓存 trace 的状态。
- **验证**：列表最终正确显示「已完成/运行中」，落地页统计同步更新为「8 已完成 · 1 运行中」。

### ✅ 问题 3：TokenDashboard 总 TOKEN 显示为 0

- **现象**：任务详情页「总 TOKEN 0」，但「输入 2.6K / 输出 140」。
- **根因**：[trace-model.ts#L45-L47](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/trace-model.ts#L45) 使用 `accumulated_*` 字段计算 total，但后端实际字段为 `prompt_tokens` / `completion_tokens`。
- **修复**：优先 `total_tokens`，否则回退到 `prompt_tokens + completion_tokens`，同时保留 `accumulated_*` 兼容。
- **验证**：总 TOKEN 正确显示「2.7K」。

### ✅ 问题 4：健康检查弹窗内容缺失

- **现象**：弹窗只显示总体状态，未列出各检查项。
- **根因**：`/health` 未进 vite proxy，被 SPA fallback 返回 `index.html`，导致 `healthData.checks` 为空。
- **修复**：同问题 1，补全 `/health` 代理。
- **验证**：弹窗正确显示 LLM/Docker/Qlib/Conda/MLflow 五项检查详情。

---

## 3. 仍存在的问题

### 🟡 后端问题：Finance Prediction 任务执行失败

- **现象**：已有的 `mild-exercise-20260723` Finance Prediction 任务日志显示 `RuntimeError: 预测结果解析失败`，底层为 `KeyError: 'score'`。
- **根因位置**：[rdagent/app/qlib_rd_loop/predict.py#L81](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/predict.py#L81) 在解析预测结果时访问了不存在的 `score` 列。
- **影响**：股池预测的「预测 T+1」功能无法完成，任务会以 error 结束。
- **建议**：检查 predict.py 中结果 DataFrame 的列名（应为 `score` 还是 `pred`/`SCORE`），与 Qlib 版本/模型输出对齐。

### 🟡 前端展示问题：Finance Prediction 任务 AgentFlow 状态不更新

- **现象**：运行中的 Finance Prediction 任务，AgentFlow 五个节点均显示「待启动」。
- **根因**：`trace-model.ts` 的 `buildTraceView` / `deriveTraceStatus` 基于 `research.hypothesis`、`feedback.metric` 等 factor 场景 tag 构建，prediction 任务使用不同 tag（如 `prediction.top20`），导致流程状态未映射。
- **建议**：为 `fin_predict` 场景扩展 AgentFlow / PipelineStages 的状态映射，或提供 prediction 专用流程视图。

### 🟡 环境配置风险

`/health` 显示：
- Conda 环境：`CONDA_DEFAULT_ENV` 未设置（warn）
- MLflow 配置：`MLFLOW_ALLOW_FILE_STORE` 未设置（warn）

建议部署时补齐 `.env` 中对应变量，避免因子代码验证或 docker qrun 报错。

---

## 4. 已验证通过的用例

| 编号 | 用例 | 结果 |
|---|---|---|
| TC-BF-01 | 落地页正常展示 | ✅ |
| TC-BF-02 | 任务列表加载 | ✅ |
| TC-BF-03~07 | 任务状态/场景过滤 | ✅ |
| TC-BF-15 | 表单校验 | ✅ |
| TC-BF-18~25 | 任务运行全流程各组件渲染 | ✅ |
| TC-BF-37~42 | 结果工作区各 tab / SOTA / 下载按钮 | ✅ |
| TC-BF-46~48 | Loop 切换 | ✅ |
| TC-BF-49~55 | 实时日志（加载/搜索/隐藏 INFO/下载 stdout） | ✅ |
| TC-BF-58~60 | 股池预测看板进入/列表/选择实验 | ✅ |
| TC-BF-67~68 | 健康检查弹窗 | ✅ |
| TC-UI-01~03 | 路由切换 | ✅ |
| TC-UI-05~06 | AgentFlow 节点展开 | ✅（factor 场景） |
| TC-DO-01 | 品牌一致性 | ✅ |
| TC-DO-07 | 数字格式化 | ✅ |

---

## 5. 未执行/需补充的测试

- **新建任务真实提交并跑完一个 factor loop**：因单次 loop 约 10-15 分钟，本次未完整执行；建议后续用 loop=1 做端到端验证。
- **交互式任务弹窗**：代码已支持假设/反馈/feature/instruction，但需在实际交互式任务中验证。
- **预测 T+1 执行**：需等后端 `KeyError: 'score'` 修复后验证。
- **停止任务**：按钮已展示，待 running task 时实测。
- **响应式/多端布局**：仅在桌面分辨率下测试。

---

## 6. 修改文件清单

| 文件 | 修改内容 |
|---|---|
| [web/vite.config.ts](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/vite.config.ts) | proxy 目标改为 localhost，补全 `/health` 代理 |
| [web/src/multialpha/use-multialpha.ts](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/use-multialpha.ts) | `loadTraceIds()` 后台加载各 trace 状态 |
| [web/src/multialpha/trace-model.ts](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/trace-model.ts) | 修复 totalTokens 计算逻辑 |

---

**版本**：v1.1（2026-07-24）
**配套文档**：
- [WEBUI_MULTIALPHA_TEST_CASES.md](../WEBUI_MULTIALPHA_TEST_CASES.md)
- [WEBUI_TEST_ISSUES.md](../WEBUI_TEST_ISSUES.md)
