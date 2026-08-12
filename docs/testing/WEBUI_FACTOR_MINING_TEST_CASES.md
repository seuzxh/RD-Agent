# 因子挖掘场景测试用例

> 版本：v1.0 · 日期：2026-08-09
> 范围：MultiAlpha 因子挖掘场景（`Finance Data Building` / fin_factor）完整用户旅程
> 环境：后端 `http://localhost:19899`（Flask）+ 前端 vite dev（`:8081`）或 Flask 生产构建
> 关联修复：`bfc7bd72`（upload 轮询）、`38edd852`（列表排序）
>
> 维护约定：执行后标注 ✅通过 / ❌失败（附现象+根因）/ ⏭️跳过（附原因）。P0 全部通过方可验收。

---

## 优先级定义

| 优先级 | 含义 | 验收要求 |
|---|---|---|
| **P0** | 核心业务功能（任务创建/运行/查看/停止/模型/轮次） | **全部通过** |
| **P1** | 页面交互（导航、轮次切换、日志、下载等） | 通过率 ≥ 90% |
| **P2** | 展示优化（格式化、label 映射、状态色） | 无 P0/P1 级缺陷 |

---

## 目录

- [§1 新建任务与提交流程（P0）](#1-新建任务与提交流程p0)
- [§2 任务列表与排序（P0）](#2-任务列表与排序p0)
- [§3 验证模型选择（P0）](#3-验证模型选择p0)
- [§4 循环次数选择（P0）](#4-循环次数选择p0)
- [§5 详情页逐 tag 渲染（P0）](#5-详情页逐-tag-渲染p0)
- [§6 结果工作区（P0）](#6-结果工作区p0)
- [§7 轮次切换（P1）](#7-轮次切换p1)
- [§8 运行日志 / 任务控制 / 展示（P1/P2）](#8-运行日志--任务控制--展示p1p2)

---

## §1 新建任务与提交流程（P0）

> 覆盖 commit `bfc7bd72`：upload 轮询等待 + loading overlay

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-FM-01 | 打开新建任务弹窗 | 首页 `#/` 已加载 | 点击顶栏「新建任务」按钮 | 弹窗打开；Tab 默认「文字描述」；场景默认「因子挖掘 (fin_factor)」；循环次数默认 10；验证模型默认 LightGBM；运行模式默认「全自动」 | P0 |
| TC-FM-02 | 填写策略描述并提交 | 弹窗已打开 | 1. 输入策略描述「过去5日收益率动量因子」<br>2. 循环次数选 1 轮<br>3. 点「启动任务」 | 1. 弹窗关闭<br>2. 出现全屏 loading overlay（文案「正在初始化任务环境」+ 任务名 + 「预计 3-5 秒」）<br>3. `POST /upload` 请求发出，返回 `{id:"Finance Data Building/xxx"}` | P0 |
| TC-FM-03 | overlay 期间侧边栏不显示新任务 | TC-FM-02 提交后，overlay 显示中 | 观察 `GET /traces/status` 和侧边栏列表 | overlay 期间（`/upload/poll` 返回 `ready:false`），侧边栏列表**不含**新任务 id（后端 `/upload` 不再初始化 `trace_states`） | P0 |
| TC-FM-04 | 轮询 /upload/poll 行为 | TC-FM-02 提交后 | 抓包观察 `/upload/poll?id=xxx` 请求 | 1. 每 3s 发起一次 `GET /upload/poll?id=xxx`<br>2. 未就绪返回 `{ready:false}`<br>3. 子进程写 scenario/ 目录后返回 `{ready:true}`<br>4. 收到 ready:true 后不再轮询 | P0 |
| TC-FM-05 | 就绪后跳转详情页 | TC-FM-04 收到 ready:true | 观察 URL 和页面内容 | 1. overlay 消失<br>2. URL 跳转 `#/tasks/Finance Data Building/xxx`<br>3. 详情页**即时**显示真实内容（Pipeline 阶段/因子/指标），无空白闪烁<br>4. ElMessage 显示「任务已启动」 | P0 |
| TC-FM-06 | 提交时缺策略描述 | 弹窗已打开 | 不填描述，直接点「启动任务」 | ElMessage 警告「请填写任务描述」；不发送 `/upload` 请求 | P0 |
| TC-FM-07 | /upload/poll 缺 id 参数 | — | `curl "http://localhost:19899/upload/poll"` | HTTP 400 + `{error:"id is required"}` | P0 |
| TC-FM-08 | /upload/poll 路径越界 | — | `curl "http://localhost:19899/upload/poll?id=../../../etc"` | HTTP 422 + `{error:"Invalid id"}` | P0 |

---

## §2 任务列表与排序（P0）

> 覆盖 commit `38edd852`：按创建时间由近及远排序

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-FM-09 | 新建任务出现在列表顶部 | 存在多条历史任务 | 1. 新建一个任务并等待跳转完成<br>2. 回到首页 `#/`<br>3. 点「加载更多」显示全部 | 最新创建的任务排在侧边栏**第 1 位**（`/traces/status` 按 `created_at DESC` 排序，前端据此重排 traceIds） | P0 |
| TC-FM-10 | 排序与筛选联动 | 侧边栏有多个场景的任务 | 1. 场景下拉选「因子挖掘」<br>2. 状态选「已完成」 | 筛选后的列表仍按创建时间由近及远排列 | P0 |
| TC-FM-11 | /traces/status 失败降级 | — | 模拟 `/traces/status` 返回 500（如断网） | 列表保持 `/traces`（字典序）的原顺序，不白屏、不报错 | P0 |

---

## §3 验证模型选择（P0）

> 每条用例断言：① FormData 携带规则 ② 后端 `QLIB_FACTOR_MODEL_SELECTOR` 环境变量 ③ 回测结果模型类型

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-FM-12 | LightGBM（默认模型） | 弹窗已打开 | 1. 验证模型保持默认 LightGBM<br>2. 填描述、选 1 轮、提交 | 1. FormData **不含** `model_selector` 字段（lgbm 不传）<br>2. 后端不设 `QLIB_FACTOR_MODEL_SELECTOR` 环境变量<br>3. 任务正常创建、回测完成 | P0 |
| TC-FM-13 | Linear（闭式 OLS） | 弹窗已打开 | 1. 验证模型选「Linear（闭式 OLS，最快）」<br>2. 填描述、选 1 轮、提交 | 1. FormData 含 `model_selector=linear`<br>2. 后端 `os.environ["QLIB_FACTOR_MODEL_SELECTOR"]="linear"`<br>3. 回测结果中模型使用 LinearModel | P0 |
| TC-FM-14 | XGBoost | 弹窗已打开 | 1. 验证模型选「XGBoost」<br>2. 填描述、选 1 轮、提交 | 1. FormData 含 `model_selector=xgboost`<br>2. 后端环境变量正确注入<br>3. 回测结果中模型使用 XGBoost | P0 |
| TC-FM-15 | CatBoost | 弹窗已打开 | 1. 验证模型选「CatBoost」<br>2. 填描述、选 1 轮、提交 | 1. FormData 含 `model_selector=catboost`<br>2. 后端环境变量正确注入<br>3. 回测结果中模型使用 CatBoost | P0 |

---

## §4 循环次数选择（P0）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-FM-16 | loops=1（单轮） | 弹窗已打开 | 1. 循环次数选「1 轮」<br>2. 填描述、提交<br>3. 等待任务完成 | 1. FormData `loops=1`<br>2. 详情页 LoopSwitcher 显示 1 个轮次（或无，单轮时可能不渲染）<br>3. 任务 1 轮后状态变 done | P0 |
| TC-FM-17 | loops=3（多轮迭代） | 弹窗已打开 | 1. 循环次数选「3 轮」<br>2. 填描述、提交<br>3. 等待任务完成 | 1. FormData `loops=3`<br>2. LoopSwitcher 显示第 1/2/3 轮<br>3. 每轮产出独立的 hypothesis/factors/metrics<br>4. 3 轮后状态变 done | P0 |
| TC-FM-18 | loops=10（默认值） | 弹窗已打开 | 1. 循环次数保持默认（10）<br>2. 填描述、提交 | 1. FormData `loops=10`<br>2. 后端任务配置中 loop_n=10 | P0 |

---

## §5 详情页逐 tag 渲染（P0）

> 每条断言 4 维度：消息出现 → 组件展示 → AgentFlow 节点状态 → Pipeline 阶段状态
> 前置条件：TC-FM-05 已跳转至运行中的详情页

| 编号 | tag / 用例 | 触发时机 | 组件展示断言 | AgentFlow 节点 | Pipeline 阶段 | 优先级 |
|---|---|---|---|---|---|---|
| TC-FM-19 | `task.user_input` 用户输入回显 | 跳转后立即可见 | TaskBrief 展开后显示「初始策略描述 · 你的输入」+ 描述文本 | — | — | P0 |
| TC-FM-20 | `feedback.config` 运行配置 | 第一个 tag 到达 | TaskBrief 配置 chips（Dataset/Model/Factors 等键值对） | — | — | P0 |
| TC-FM-21 | `research.hypothesis` 假设生成 | LLM 返回假设 | TaskBrief 显示策略文本 + reason；AgentFlow 假设节点展开有内容 | 假设生成 ✓ done | 研究 ✓ done | P0 |
| TC-FM-22 | `research.tasks` 因子任务 | 假设通过后 | TaskBrief 初始因子徽章数 = N；AgentFlow 设计节点 | 实验设计 ✓ done（「N 因子」） | 研究 ✓ done | P0 |
| TC-FM-23 | `evolving.codes` 因子代码 | CoSTEER 生成完成 | ResultWorkspace 代码 Tab 有代码内容；行数显示 | 代码实现 ✓ done（「N 文件」） | 编码 ✓ done | P0 |
| TC-FM-24 | `feedback.metric` 回测指标 | Qlib 回测完成 | MetricsPanel 显示 IC/年化/回撤等；ResultWorkspace 结论 Tab 有 coreMetrics 4 项 | 回测执行 ✓ done（「IC=X.XXX」） | 回测 ✓ done | P0 |
| TC-FM-25 | `feedback.return_chart` 收益曲线 | 图表生成后 | ResultWorkspace 曲线 Tab 有 iframe（加载 artifact 端点 HTML） | — | 回测 ✓ done | P0 |
| TC-FM-26 | `feedback.hypothesis_feedback` 反馈结论 | 评审完成 | ResultWorkspace 结论 Tab 有 decision chip（采纳/拒绝）+ feedbackItems | 反馈评审 ✓ done（已采纳/已拒绝） | 反馈 ✓ done | P0 |
| TC-FM-27 | `token_cost` Token 统计 | 每个 step | TokenDashboard 显示总/输入/输出 token + 调用次数，无 NaN | — | — | P0 |
| TC-FM-28 | `END` 任务完成 | 全部 loop 结束 | DetailHeader 状态变 done；停止按钮消失；轮询停止 | — | 全部 ✓ done | P0 |

---

## §6 结果工作区（P0）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-FM-29 | 最终结论 Tab | 任务至少完成 1 轮，有 metric + feedback | 切到「最终结论」Tab | 1. coreMetrics 显示 IC/年化收益/最大回撤/信息比率（前 4 项）<br>2. 百分比指标显示 `%`（年化/回撤），IC 等显示 4 位小数<br>3. decision chip（绿色采纳 / 红色拒绝）<br>4. feedbackItems（决定理由/实验观察/假设评估/异常信息） | P0 |
| TC-FM-30 | 因子结果 Tab | 有 factors 数据 | 切到「因子结果」Tab | 1. 因子卡片显示名称、描述、公式（KaTeX 渲染）、变量列表<br>2. Tab 标题 count_badge 显示因子数量<br>3. 无因子时显示「当前轮次暂无因子结果」 | P0 |
| TC-FM-31 | 收益曲线 Tab | 有 chart 数据 | 切到「收益曲线」Tab | iframe 加载 plotly 图表（`/api/v2/trace/artifact?id=&loop=`）；图表可交互（缩放/悬浮） | P0 |
| TC-FM-32 | 因子代码 Tab + SOTA + 下载 | 有 codes 数据 | 1. 切到「因子代码」Tab<br>2. 点「复制」<br>3. 点「下载」<br>4. 点「🏆 SOTA 产物」 | 1. 代码 `pre` 显示；多文件时可切换；行数显示<br>2. 复制成功 ElMessage 提示<br>3. 下载 .py 文件<br>4. SOTA 弹窗显示最优 loop 的假设/指标/反馈/因子代码 | P0 |

---

## §7 轮次切换（P1）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-FM-33 | 切换历史 loop | 任务有多轮（≥2），已完成 | 点击 LoopSwitcher 的第 1 轮 | TaskBrief/AgentFlow/ResultWorkspace/MetricsPanel 全部联动切换为该轮数据；LoopSwitcher 高亮第 1 轮 | P1 |
| TC-FM-34 | 自动跟随最新 loop | 任务运行中，当前未选 loop | 等待 poll 拉到新轮次消息 | `selectedLoop` 自动设为最新 loop（max）；各面板展示最新轮数据 | P1 |
| TC-FM-35 | 切到无数据 loop 的 tab 回退 | 某轮缺少 chart 数据 | 切到无 chart 的轮次 | 曲线 Tab 不可用，自动回退到第一个可用 Tab（结论或因子） | P1 |

---

## §8 运行日志 / 任务控制 / 展示（P1/P2）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-FM-36 | 运行日志展开与加载 | 详情页，任务运行中或已完成 | 点击「运行日志」展开 | 1. running 状态自动开始轮询 `/stdout`<br>2. 日志逐行显示（虚拟滚动）<br>3. 日志摘要显示「N 行」 | P1 |
| TC-FM-37 | 日志搜索与隐藏 INFO | 日志已展开 | 1. 搜索框输入「error」<br>2. 勾选「隐藏 INFO」 | 1. 仅显示含「error」的行（250ms debounce）<br>2. 过滤掉含 INFO 的行<br>3. error/warn/success 行按颜色着色 | P1 |
| TC-FM-38 | 日志退避轮询 | 任务运行中，日志已展开 | 观察网络请求 | 连续 3 次无新数据后，轮询间隔从 2s 退避到最大 8s | P1 |
| TC-FM-39 | 停止任务 | 详情页，任务运行中 | 点击「停止」按钮 | 1. `POST /control {action:"stop"}`<br>2. ElMessage「任务已停止」<br>3. 状态变 done<br>4. 停止按钮消失<br>5. 轮询停止 | P0 |
| TC-FM-40 | 并发上限拦截 | 已有 10 个 running 任务 | 点击「新建任务」 | ElMessage 警告「当前有 10 个任务运行中（上限 10）」；弹窗不打开 | P0 |
| TC-FM-41 | 场景中文 label 映射 | 侧边栏有各场景任务 | 观察列表项副标题 | `Finance Data Building` → 「因子挖掘」；`Finance Data Building (Reports)` → 「研报因子提取」 | P2 |
| TC-FM-42 | 数字格式化 | 详情页有指标数据 | 观察 MetricsPanel 和结论 Tab | 1. IC/ICIR 显示 4 位小数<br>2. 年化收益/最大回撤显示百分比（`abs*100` 2 位 + `%`）<br>3. Token 数千位以上正常显示无 NaN | P2 |

---

## 附录：接口测试速查

| 接口 | 方法 | 关注点 | 关联用例 |
|---|---|---|---|
| `/upload` | POST | scenario 映射、model_selector 携带规则、不初始化 trace_states | TC-FM-02,12-18 |
| `/upload/poll` | GET | scenario/ 目录探测、ready 翻转、400/422 边界 | TC-FM-04,07,08 |
| `/traces` | GET | 字典序返回（前端会重排） | TC-FM-09 |
| `/traces/status` | GET | created_at DESC 排序、失败降级 | TC-FM-09,11 |
| `/trace` | POST | cursor 增量、all/reset 参数、tag 完整性 | TC-FM-19~28 |
| `/api/v2/trace/artifact` | GET | iframe HTML、304/404、路径越界 | TC-FM-25,31 |
| `/traces/:id/sota` | GET | SOTA 产物结构 | TC-FM-32 |
| `/control` | POST | stop action | TC-FM-39 |
| `/stdout` | GET (Range) | 206/416/200 三态、退避 | TC-FM-36~38 |
