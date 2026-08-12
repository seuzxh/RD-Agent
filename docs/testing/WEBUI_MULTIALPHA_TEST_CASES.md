# multiα1pha webUI 全面测试用例

> 范围：multiα1pha 子应用全部功能（任务创建 / 因子挖掘全流程 / 用户交互 / 股池预测 / 日志 / 健康检查 / 列表管理）
> 优先级：P0 业务功能 > P1 页面交互 > P2 页面展示优化
> 维护：执行后每条标注 ✅通过 / ❌失败（附现象+根因）/ ⏭️跳过（附原因）
>
> 代码依据：
> - 前端入口：[web/src/multialpha/MultiAlphaApp.vue](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/MultiAlphaApp.vue)
> - 路由：[web/src/multialpha/router.ts](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/router.ts)
> - 状态逻辑：[web/src/multialpha/use-multialpha.ts](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/use-multialpha.ts)
> - 消息解析：[web/src/multialpha/trace-model.ts](file:///home/zxh/projects/1.multialphaV/RD-Agent/web/src/multialpha/trace-model.ts)
> - 后端服务：[rdagent/log/server/app.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/log/server/app.py)

---

## 0. 功能特性总览

| 模块 | 入口/组件 | 核心功能 | 依赖后端接口 |
|---|---|---|---|
| 落地页 | `LandingTerminal.vue` | 品牌展示、任务统计、创建入口、历史入口 | `GET /traces` |
| 顶部栏 | `TopBar.vue` | 健康检查、刷新任务、新建任务 | `GET /health`、`GET /traces` |
| 任务侧边栏 | `TaskSidebar.vue` | 任务列表、场景过滤、状态过滤、加载更多 | `GET /traces` |
| 新建任务 | `NewTaskDialog.vue` | 文字描述 / 研报上传 / 因子优化 / 循环数 / 验证模型 / 运行模式 | `POST /upload` |
| 任务详情头 | `DetailHeader.vue` | 任务名、场景、状态、当前轮次、停止按钮 | `POST /trace`、`POST /control` |
| 阶段流水线 | `PipelineStages.vue` | 研究 / 编码 / 回测 / 反馈 四阶段状态 | `POST /trace` |
| 任务简报 | `TaskBrief.vue` | 策略描述、任务配置、初始因子徽章 | `POST /trace` |
| 多智能体流程 | `AgentFlow.vue` | 五个节点产物展示、点击展开 | `POST /trace` |
| 轮次切换 | `LoopSwitcher.vue` | 按 loop 过滤全部面板 | `POST /trace` |
| Token 面板 | `TokenDashboard.vue` | 总/输入/输出 token、调用次数 | `POST /trace` |
| 结果工作区 | `ResultWorkspace.vue` | 结论 / 因子 / 收益曲线 / 代码 / SOTA / 下载 | `POST /trace`、`GET /traces/{id}/sota` |
| 指标面板 | `MetricsPanel.vue` | 核心指标、研究假设、反馈摘要、导出 | `POST /trace` |
| 实时日志 | `LogConsole.vue` | Range 增量轮询、搜索、隐藏 INFO、下载 stdout | `GET /stdout` |
| 用户交互 | `UserInteractionDialog.vue` | 假设评审 / 反馈评审 / 基础特征 / 总体指令 / 自动跳过 | `POST /trace`、`POST /user_interaction/submit` |
| 股池预测 | `PredictDashboard.vue` | 可选实验列表、预测 T+1、Top20、历史记录 | `GET /predict/experiments`、`POST /predict/run`、`GET /predict/history` |

---

## 1. P0 业务功能测试

### 1.1 落地页与任务列表

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-01 | 落地页正常展示 | 服务已启动 | 访问 `#/` | 显示品牌、Live 时钟、任务统计、5 个入口按钮 | P0 |
| TC-BF-02 | 任务列表加载 | 存在历史任务 | 打开首页或点击刷新 | `GET /traces` 200，侧边栏/landing ticker 正确列出任务 | P0 |
| TC-BF-03 | 任务状态过滤 | 列表含不同状态任务 | 点击「全部/完成/运行中」 | 只显示对应状态任务 | P0 |
| TC-BF-04 | 任务场景过滤 | 列表含多场景任务 | 选择 scenario 下拉 | 只显示对应场景任务 | P0 |
| TC-BF-05 | 加载更多 | 任务数 > 10 | 点击「加载更多」 | 每次多显示 10 条 | P1 |
| TC-BF-06 | 列表为空 | 无历史任务 | 清空 traces 后刷新 | 显示「暂无任务」 | P1 |
| TC-BF-07 | 列表加载失败 | 模拟后端 500 | 刷新任务 | 显示错误提示 + 重试按钮 | P1 |

### 1.2 新建任务

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-08 | 文字描述创建因子挖掘任务 | 在落地页点「文字描述」 | 填描述、选「因子挖掘」、loop=1、model=lgbm、全自动，点启动 | `POST /upload` 200 返回 id，跳转到任务详情，task 开始运行 | P0 |
| TC-BF-09 | 文字描述创建模型实现任务 | 在新建弹窗选「模型实现」 | 填描述、loop=1、启动 | task 以 fin_model 目标运行 | P0 |
| TC-BF-10 | 文字描述创建量化全流程任务 | 在新建弹窗选「量化全流程」 | 填描述、loop=1、启动 | task 以 fin_quant 目标运行 | P0 |
| TC-BF-11 | 研报 PDF 创建任务 | 在落地页点「研报因子提取」 | 上传 1-N 个 PDF、loop=1、启动 | `POST /upload` 带 files，task 以 fin_factor_report 运行 | P0 |
| TC-BF-12 | 因子优化创建任务 | 在落地页点「因子迭代优化」 | 上传 .py 因子代码 + 填优化目标、启动 | `POST /upload` 带 files + description，task 以 fin_factor 运行 | P0 |
| TC-BF-13 | 验证模型切换生效 | 新建文字任务 | 分别选 lgbm/linear/xgboost/catboost | `/upload` 携带 model_selector，后端设置 `QLIB_FACTOR_MODEL_SELECTOR` | P0 |
| TC-BF-14 | 运行模式切换 | 新建文字任务 | 切「全自动」/「交互式」 | `auto_mode` 字段对应 true/false；交互式应产生 user_interaction.request | P0 |
| TC-BF-15 | 表单校验 | 打开新建弹窗 | 文字/优化模式不填描述、PDF 模式不上传文件，点启动 | 前端提示必填，不发请求 | P0 |
| TC-BF-16 | 未上线入口置灰 | 在落地页 | 查看 K线图片 / 交割单分析 | 按钮 disabled，显示「即将上线」 | P2 |

### 1.3 任务运行全流程（以 fin_factor 为例，loop=1）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-17 | 实验配置消息展示 | task 启动后 | 等待 `feedback.config` | TaskBrief 展开后显示配置表（Dataset/Model/Factors/DataSplit） | P0 |
| TC-BF-18 | 假设生成 | task 运行中 | 等待 `research.hypothesis` | TaskBrief 显示策略文本；AgentFlow 研究节点变 done；PipelineStages 研究阶段变 done | P0 |
| TC-BF-19 | 任务生成 | task 运行中 | 等待 `research.tasks` | AgentFlow 设计节点显示 N 个因子；TaskBrief 显示初始因子徽章 | P0 |
| TC-BF-20 | 代码实现 | task 运行中 | 等待 `evolving.codes` | ResultWorkspace 代码 tab 显示 factor.py；AgentFlow 编码节点变 done | P0 |
| TC-BF-21 | 回测指标 | task 运行中 | 等待 `feedback.metric` | MetricsPanel 显示 IC/年化/回撤/信息比率；AgentFlow 回测节点显示 IC=X.XXX | P0 |
| TC-BF-22 | 收益曲线 | task 运行中 | 等待 `feedback.return_chart` | ResultWorkspace 曲线 tab 渲染 plotly iframe | P0 |
| TC-BF-23 | 反馈结论 | task 运行中 | 等待 `feedback.hypothesis_feedback` | ResultWorkspace 结论 tab 显示 decision chip + 理由；AgentFlow 反馈节点变 done | P0 |
| TC-BF-24 | Token 统计 | task 运行中 | 等待 `token_cost` | TokenDashboard 显示总/输入/输出 token 与调用次数，无 NaN | P0 |
| TC-BF-25 | 任务完成 | task 跑完 | 等待 `END` | DetailHeader 状态变「已完成」，停止按钮消失，轮询停止 | P0 |

### 1.4 用户交互（交互式模式）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-26 | 假设评审弹窗 | 交互式新建任务 | 等待 `user_interaction.request`（含 hypothesis） | UserInteractionDialog 弹出，显示 hypothesis + reason 可编辑 | P0 |
| TC-BF-27 | 假设评审提交 | 弹窗已打开 | 编辑 reason，点提交 | `POST /user_interaction/submit` 200，进入 waiting 态，task 继续 | P0 |
| TC-BF-28 | 反馈评审弹窗 | 交互式任务到反馈环节 | 等待 `user_interaction.request`（含 decision） | 弹窗显示 decision select + reason textarea | P0 |
| TC-BF-29 | 反馈评审提交 | 弹窗已打开 | 改 decision 为 true/false，填 reason，提交 | task 继续，下轮 hypothesis 生成 | P0 |
| TC-BF-30 | 基础特征交互 | 交互式任务触发 feature 请求 | 等待 `user_interaction.request`（含 features） | 弹窗变宽，左侧 Alpha158 特征池，右侧可增删改特征行 | P0 |
| TC-BF-31 | 基础特征提交 | feature 弹窗打开 | 从池中添加/手动输入特征，提交 | `POST /user_interaction/submit` payload 为 features dict | P0 |
| TC-BF-32 | 总体指令交互 | 交互式任务触发 user_instruction | 等待含 user_instruction 的请求 | 弹窗显示「您的总体指令」textarea | P0 |
| TC-BF-33 | 自动跳过后续交互 | 弹窗打开 | 勾选「自动跳过后续交互」 | 当前及后续非 feature/instruction 交互自动提交原 payload | P1 |
| TC-BF-34 | 最小化交互弹窗 | 弹窗打开 | 点最小化 | 弹窗收起为右下角浮动球，点击可恢复 | P1 |
| TC-BF-35 | 跳过交互 | 弹窗打开 | 点「跳过」 | 提交原 payload，task 继续 | P1 |
| TC-BF-36 | 10 分钟超时自动提交 | 弹窗打开后不操作 | 等待 10 分钟 | 自动提交原 payload，避免 task 挂死 | P1 |

### 1.5 结果工作区

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-37 | 结论 tab | task 有反馈 | 点击「最终结论」 | 显示 4 项核心指标、decision chip、理由/观察/评估/异常 | P0 |
| TC-BF-38 | 因子结果 tab | task 有 research.tasks | 点击「因子结果」 | 显示因子卡片：名称、描述、公式（KaTeX）、变量 | P0 |
| TC-BF-39 | 收益曲线 tab | task 有 return_chart | 点击「收益曲线」 | iframe 正确渲染 plotly HTML | P0 |
| TC-BF-40 | 因子代码 tab | task 有 evolving.codes | 点击「因子代码」 | 显示代码文件选择器、代码内容、行数、复制/下载 | P0 |
| TC-BF-41 | SOTA 产物弹窗 | task 有 SOTA | 点击「🏆 SOTA 产物」 | 弹窗显示最优假设、回测指标、决策、因子代码 | P0 |
| TC-BF-42 | 下载产物 | task 有任意结果 | 点击「↓ 下载产物」 | 浏览器下载 JSON 文件，含 traceId/loop/指标/因子/代码/反馈 | P0 |
| TC-BF-43 | 代码复制 | 在代码 tab | 点「复制」 | 剪贴板写入当前代码，ElMessage 成功提示 | P1 |
| TC-BF-44 | 代码下载 | 在代码 tab | 点「下载」 | 下载当前文件 | P1 |
| TC-BF-45 | SOTA 代码复制 | 在 SOTA 弹窗 | 点因子代码「复制」 | 剪贴板写入对应因子代码 | P1 |

### 1.6 轮次切换

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-46 | LoopSwitcher 显示 | loop_n>1 的 task 完成 | 查看任务详情 | LoopSwitcher 显示所有轮次按钮 + IC 角标 | P0 |
| TC-BF-47 | 切换轮次 | 多 loop task | 点击 loop 0 / loop N | 各面板（TaskBrief/AgentFlow/ResultWorkspace/MetricsPanel）按所选 loop 过滤 | P0 |
| TC-BF-48 | 自动跟随最新 loop | task 运行中 | 不手动切换 | selectedLoop 自动设为当前最大 loop | P0 |

### 1.7 实时日志

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-49 | 日志自动加载 | running task | 进入任务详情 | LogConsole 自动 Range 轮询 `/stdout`，状态为 live | P0 |
| TC-BF-50 | 日志展开/收起 | task 详情页 | 点击 LogConsole header | 展开显示日志行；再次点击收起 | P0 |
| TC-BF-51 | 日志搜索 | 已展开且有日志 | 输入关键字 | 只显示匹配行 | P1 |
| TC-BF-52 | 隐藏 INFO | 已展开 | 勾选「隐藏 INFO」 | 不显示含 INFO 的行 | P1 |
| TC-BF-53 | 下载 stdout | 已展开 | 点「下载 stdout」 | 新标签下载完整日志文件 | P1 |
| TC-BF-54 | 大日志虚拟滚动 | running 很久的 task | 滚动日志 | 虚拟列表渲染流畅，不卡顿 | P1 |
| TC-BF-55 | 日志错误态 | `/stdout` 500 | 展开日志 | state 变 error，提示可下载完整日志 | P1 |

### 1.8 任务控制

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-56 | 停止运行中任务 | task 正在运行 | 点 DetailHeader「停止」 | `POST /control` stop，状态变 done，轮询停止，显示 ElMessage | P0 |
| TC-BF-57 | 已完成任务无停止按钮 | task 已 done | 查看详情头 | 不显示停止按钮 | P1 |

### 1.9 股池预测

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-58 | 进入预测看板 | 在任意页 | 点击「📊 预测」或从 landing 进入 | 路由到 `#/predict`，显示可选实验列表 | P0 |
| TC-BF-59 | 实验列表加载 | 已有 fin_factor 完成实验且含 params.pkl | 进入预测看板 | `GET /predict/experiments` 200，列表显示名称/因子数/IC/年化 | P0 |
| TC-BF-60 | 选择实验 | 列表已加载 | 点击某个实验 | 右侧显示实验信息卡 + 指标 + 操作按钮 | P0 |
| TC-BF-61 | 执行 T+1 预测 | 已选实验 | 点「预测 T+1」 | `POST /predict/run` 200 返回 task_id，状态 predicting | P0 |
| TC-BF-62 | 预测完成展示 Top20 | 预测任务成功 | 等待 `prediction.top20` | 显示预测日期 + Top20 表格（排名/股票代码/得分） | P0 |
| TC-BF-63 | 预测历史 | 已产生过预测 | 点「查看历史」 | `GET /predict/history` 200，弹窗列出历史记录 | P0 |
| TC-BF-64 | 历史详情 | 历史弹窗已打开 | 点击某条历史 | 弹出详情弹窗显示该次 Top20 | P1 |
| TC-BF-65 | 预测失败提示 | 预测任务异常 | 等待 END with end_code != 0 | 显示错误提示 | P1 |
| TC-BF-66 | 无可选实验 | 无完成实验或缺少 params.pkl | 进入预测看板 | 显示「暂无可用的 SOTA 因子实验」 | P1 |

### 1.10 健康检查

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-BF-67 | 健康检查弹窗 | 任意页 | 点 TopBar「🩺 健康检查」 | `GET /health` 200，弹窗显示 overall + 各检查项 pass/warn/fail | P0 |
| TC-BF-68 | 健康检查异常 | 某配置缺失 | 查看弹窗 | 对应项显示 warn/fail，overall 为 issues | P1 |

---

## 2. P1 页面交互测试

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-UI-01 | 首页 → 任务详情路由 | 点击任务 | 点侧边栏任务 | URL 变为 `#/tasks/{traceId}`，详情页加载 | P1 |
| TC-UI-02 | 任务详情 → 首页 | 在详情页 | 点 TopBar 品牌或返回首页 | 回到 `#/`，隐藏右侧面板 | P1 |
| TC-UI-03 | 首页 → 预测看板 | 在首页 | 点「📊 预测」 | URL 变为 `#/predict` | P1 |
| TC-UI-04 | 新建弹窗 tab 切换 | 打开新建弹窗 | 点「文字描述/研报上传/因子优化」 | 表单字段随 method 变化 | P1 |
| TC-UI-05 | AgentFlow 节点展开 | task 有研究节点 done | 点击研究节点 | 下方展开产物面板，显示假设与理由 | P1 |
| TC-UI-06 | AgentFlow 节点收起 | 已展开节点 | 再次点击 | 产物面板关闭 | P1 |
| TC-UI-07 | ResultWorkspace tab 自动回退 | 当前 tab 无数据 | 删除/切换 loop 导致当前 tab 不可用 | 自动切换到第一个可用 tab | P1 |
| TC-UI-08 | 代码文件切换 | 代码 tab 有多个文件 | 切换 el-select | 显示对应文件内容 | P1 |
| TC-UI-09 | TaskBrief 展开/收起 | 在任务详情 | 点「展开/收起」 | 显示/隐藏策略描述、配置、初始因子 | P1 |
| TC-UI-10 | 侧边栏任务搜索/过滤联动 | 列表有任务 | 切换过滤条件 | 过滤结果即时更新 | P1 |
| TC-UI-11 | 用户交互弹窗 ESC/点击外部 | 弹窗打开 | 按 ESC 或点遮罩 | Element Plus dialog 默认行为（如需禁用需确认） | P2 |
| TC-UI-12 | 实时轮询不阻塞页面 | running task | 在详情页操作 | 页面可正常交互，轮询在后台 | P1 |
| TC-UI-13 | 切换任务取消旧请求 | 在 A 任务详情加载中 | 快速切到 B 任务 | A 的 `/trace` 请求被 abort，不覆盖 B 的数据 | P1 |

---

## 3. P2 页面展示优化

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| TC-DO-01 | 品牌一致性 | 任意页 | 检查 logo/标题/α 符号/V 形元素 | 国新证券 logo、Multiα1pha 品牌、α/V 视觉语言一致 | P2 |
| TC-DO-02 | 响应式布局 | 浏览器窗口 1920/1440/1280/1024/768px | 调整窗口大小 | 无横向滚动、布局不重叠、侧边栏可折叠或适配 | P2 |
| TC-DO-03 | 加载态 | 任务列表/详情/预测列表加载中 | 观察 | 显示 spinner/骨架屏/loading hint | P2 |
| TC-DO-04 | 空状态 | 无任务/无实验/无历史 | 查看对应区域 | 显示友好的空提示 + 引导操作 | P2 |
| TC-DO-05 | 错误状态 | 模拟接口失败 | 触发错误 | 显示错误信息，不白屏 | P2 |
| TC-DO-06 | 状态色一致性 | 任务列表 + 详情头 | 观察 running/done/error/idle | 颜色与图标符合设计语义 | P2 |
| TC-DO-07 | 数字格式化 | task 有指标 | 查看 MetricsPanel/ResultWorkspace | IC 等数值保留 4 位；年化/回撤显示 %；大 token 显示 K | P2 |
| TC-DO-08 | 公式渲染 | task 有 formula | 查看因子结果 / AgentFlow | KaTeX 正确渲染，失败时 fallback 显示原始文本 | P2 |
| TC-DO-09 | 时间展示 | task 完成 | 查看预测历史/实验列表 | 日期格式统一、时区正确 | P2 |
| TC-DO-10 | 长文本截断 | 策略描述/理由很长 | 查看 TaskBrief/ResultWorkspace | 不撑破容器，必要时可滚动 | P2 |
| TC-DO-11 | 图表自适应 | 收益曲线 tab | 调整窗口大小 | plotly iframe 自适应容器 | P2 |
| TC-DO-12 | 暗色/亮色模式 | 系统切换主题 | 观察页面 | Element Plus 默认主题下无严重色差 | P2 |

---

## 4. 接口兼容性矩阵

| 接口 | 方法 | 关键字段 | 前端调用点 | 测试关注点 |
|---|---|---|---|---|
| `/traces` | GET | `string[]` | `use-multialpha.ts:41` | 返回格式、空数组、CORS |
| `/trace` | POST | `id/all/reset/cursor` | `use-multialpha.ts:58,87` | 全量/增量、cursor 正确、END 处理 |
| `/upload` | POST | `scenario/loops/description/files/model_selector/auto_mode` | `use-multialpha.ts:129` | 四种 scenario、multipart、大文件 |
| `/control` | POST | `id/action` | `use-multialpha.ts:137` | 仅支持 stop |
| `/stdout` | GET | `id` + `Range` header | `LogConsole.vue` | 206/416/200、增量正确 |
| `/user_interaction/submit` | POST | `id/payload` | `UserInteractionDialog.vue` | payload 形态正确 |
| `/traces/{id}/sota` | GET | SOTA JSON | `ResultWorkspace.vue` | webUI trace / CLI session 回退 |
| `/health` | GET | health JSON | `TopBar.vue` | 配置检查项完整 |
| `/predict/experiments` | GET | `experiments[]` | `PredictDashboard.vue` | 只返回含 params.pkl 的实验 |
| `/predict/run` | POST | `trace_id` | `PredictDashboard.vue` | 返回 task_id |
| `/predict/history` | GET | `records[]` | `PredictDashboard.vue` | 按 trace_id 过滤 |

---

## 5. 测试方法

### 5.1 自动化/API 层
- 用 `curl`/脚本模拟前端请求，覆盖 §4 全部接口正例与异常码。
- 对 running task 轮询 `/trace`，验证每个 tag 按序产生。
- 对 `/stdout` 用 Range 请求验证 206/416 行为。
- 对预测流程：选实验 → `/predict/run` → 轮询 `/trace` 等 `prediction.top20`。

### 5.2 浏览器实测
- 在真实浏览器跑完整 loop（loop_n=1），按 P0 用例逐项确认。
- 对交互式模式，验证 UserInteractionDialog 弹窗、编辑、提交、waiting 态。
- 对预测看板，验证实验列表、T+1 预测、Top20、历史记录。

### 5.3 异常场景
- 后端重启后刷新页面：验证 `_load_existing_traces` 能恢复历史任务。
- 停止任务后立刻切换任务：验证 abort 与状态不串。
- 网络抖动：验证前端轮询错误吞掉后自动重试，不白屏。

---

## 6. 验收标准

- **P0 全部通过**：任务可创建、可运行、可交互、可查看结果、可停止、可预测。
- **P1 通过率 ≥ 90%**：导航、弹窗、轮询、复制下载等交互正常。
- **P2 无 P0/P1 级展示缺陷**：布局不崩、空错态友好、品牌一致。
- **接口全部 200/符合契约**：§4 矩阵中每个接口至少 1 个正例 + 1 个异常例。

---

**版本**：v1.0（2026-07-24）
**适用目录**：`/home/zxh/projects/1.multialphaV`
**配套文档**：
- [archive/WEBUI_FACTOR_TEST_CASES.md](archive/WEBUI_FACTOR_TEST_CASES.md)（因子挖掘场景专用用例，已归档）
- [WEBUI_TEST_ISSUES.md](WEBUI_TEST_ISSUES.md)（历史问题清单）
- [../reference/API.md](../reference/API.md)（接口参考）
**更新来源**：multiα1pha webUI 全功能特性梳理后整理的综合测试用例
