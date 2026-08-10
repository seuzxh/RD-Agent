# WebUI 任务生命周期状态测试用例（2026-08-11）

## 1. 验收口径

- 任务状态仅包含 `idle / running / done / error`。
- 单轮产出的 `feedback.metric`、`feedback.hypothesis_feedback`、chart 或 SOTA 决策均不是任务终态。
- Worker 正常退出（`end_code=0`）才是 `done`；所有非零退出、用户取消、服务重启中断及无法可靠判断的状态均为 `error`。
- `feedback.decision=false` 仅表示本轮未产出 SOTA；只要全部流程正常退出，任务仍为 `done`。
- 新任务以 `.task-state.json` 为生命周期事实来源；旧 trace 仅保留历史兼容推断。

## 2. 自动化测试用例

| ID | 场景 | 输入/前置条件 | 预期结果 |
|---|---|---|---|
| TS-01 | Factor 三轮 | loop 0 产生 metric + feedback，Worker 存活 | 状态保持 `running`，继续轮询 |
| TS-02 | Model 三轮 | loop 1 产生 metric + feedback，Worker 存活 | 状态保持 `running` |
| TS-03 | Quant 三轮 | loop 2 feedback 已产生但 Worker 尚未退出 | 状态仍为 `running` |
| TS-04 | 无 SOTA 正常完成 | 最后一轮 `decision=false`，record 成功，Worker `exitcode=0` | `done/completed` |
| TS-05 | 全部无 SOTA | 所有 loop 均 `decision=false`，Worker `exitcode=0` | `done/completed` |
| TS-06 | record 真异常 | feedback 已产生，record 抛异常，Worker 非零退出 | `error/process_failed` |
| TS-07 | Report 多文件 | 第一份 PDF 完成，后续仍在处理 | 状态保持 `running` |
| TS-08 | Prediction 成功 | 产生 `prediction.top20` 且 Worker `exitcode=0` | `done/completed` |
| TS-09 | Prediction 失败 | 未产生结果且 Worker 非零退出 | `error/process_failed` |
| TS-10 | 用户取消 | 运行中调用 `/control stop` | `error/user_cancelled`，END 非零 |
| TS-11 | 服务重启中断 | 状态文件为 `starting/running` 且属于旧 server instance | 启动后变为 `error/server_restarted` |
| TS-12 | 重启后状态不明 | 状态文件损坏、字段缺失或无法确认终态 | `error/state_unknown_after_restart` |
| TS-13 | 已完成后重启 | 状态文件为 `done` | 保持 `done`，不清理资源 |
| TS-14 | 已异常后重启 | 状态文件为 `error` | 保持原 error/reason |
| TS-15 | PID 复用保护 | PID 存在但 create time 不匹配 | 不发送 kill，任务标记 error |
| TS-16 | 遗留进程清理 | PID/create time 匹配，PGID 有效 | SIGTERM，超时后 SIGKILL |
| TS-17 | Docker 清理 | 存在相同 `multialpha.task_id` 标签容器 | 停止并删除对应容器，不影响其他容器 |
| TS-18 | END 成功映射 | `END.end_code=0` | 前端推导 `done` |
| TS-19 | END 失败映射 | `END.end_code=-1/-2/正数` | 前端推导 `error` |
| TS-20 | 状态权威性 | 消息含单轮反馈，后端返回 running | 页面保持 running |
| TS-21 | 历史兼容 | 旧 trace 无状态文件但有可靠历史完成信号 | 沿用历史状态投影 |
| TS-22 | 新任务无首个 pickle | 仅存在生命周期文件 | `/traces` 与 `/traces/status` 仍能列出任务 |
| TS-23 | Worker 启动失败 | `process.start()` 抛异常 | `error/bootstrap_failed`，释放已分配 GPU |

## 3. 浏览器专项验证

1. 创建 Factor `loops=3` 任务，在每轮 feedback 后检查详情头、侧栏和首页统计均保持“运行中”。
2. 创建最终 `decision=false` 的任务，确认最终仍显示“已完成”，同时结果区显示未采纳。
3. 运行中点击停止，确认页面显示“异常”，刷新后不回退为完成或运行中。
4. 第一轮结束后强制终止后端并重启，确认任务显示“异常”，reason 为 `server_restarted`，且无遗留 Worker/Docker。
5. 检查旧历史任务仍可打开、切换 loop、查看指标和代码。

## 4. 提交门禁

- 后端生命周期与状态单元测试全部通过。
- 前端状态推导测试或等价脚本验证通过。
- `vue-tsc` 与生产构建通过。
- 现有 `test/log/test_server_app.py` 回归通过。
- 上述真实三轮、取消和重启专项验证无阻断问题；任何失败均不得提交。
