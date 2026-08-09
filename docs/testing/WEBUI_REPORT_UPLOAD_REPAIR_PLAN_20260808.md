# 研报上传问题修复方案（2026-08-08）

对应实测报告：[WEBUI_REPORT_UPLOAD_TEST_REPORT_20260808.md](WEBUI_REPORT_UPLOAD_TEST_REPORT_20260808.md)。

## 1. 修复目标

研报上传任务必须满足以下状态闭环：

```text
上传校验成功 → 创建任务 → 解析研报 → 提取因子 → 生成公式/代码
      │              │             │
      └─失败返回 4xx  └─异常状态    └─成功结果可展示
```

不得出现“任务内部异常、trace 返回 `END(end_code=0)`、页面显示已完成”的假成功。

## 2. 优先级与改动范围

| 优先级 | 问题 | 主要文件 | 验收标准 |
|---|---|---|---|
| P0 | LLM 返回 `{}` 导致因子提取崩溃 | `rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py` | 前几轮因子保留，`{}` 正常结束 |
| P0 | 子进程异常被吞掉 | `rdagent/log/server/app.py` | 异常任务非零退出，trace 可识别失败 |
| P0 | 前端忽略 `END.end_code` | `web/src/multialpha/trace-model.ts`、`types.ts` | 失败显示“异常”，停止显示“已停止” |
| P0 | 首次进入任务详情 404 | `web/src/multialpha/use-multialpha.ts`、`MultiAlphaApp.vue` | 创建后首次跳转即可打开详情 |
| P1 | 缺少上传参数和 PDF 校验 | `rdagent/log/server/app.py` | 错误请求返回 JSON 4xx，不启动任务 |
| P1 | 上传失败留下部分文件 | `rdagent/log/server/app.py` | 失败请求不残留上传目录 |
| P1 | 取消重开/切 Tab 文件残留 | `web/src/multialpha/components/NewTaskDialog.vue` | 可见文件与实际提交文件一致 |
| P1 | 中文文件名丢失 | `rdagent/log/server/app.py` | 原文件名保留在元数据，服务端文件名唯一 |
| P1 | 运行环境与源码版本不一致 | 启动脚本/部署配置 | `sys.executable`、源码版本可审计 |

## 3. P0 修复方案

### 3.1 统一因子提取协议

文件：`pdf_loader.py`

解析规则：

1. `{"factors": {"A": "..."}}`：合并因子并继续下一轮。
2. `{"factors": {}}`：正常结束并返回已累积因子。
3. `{}`：兼容当前提示词，正常结束并返回已累积因子。
4. 缺少 `factors`、非法 JSON 或字段类型错误：记录 warning；保留已累积因子，不得覆盖或抛出未处理异常。

提示词同时统一为：无更多因子时始终返回 `{"factors": {}}`，避免协议歧义。

回归测试至少覆盖：

- 第一轮有因子、第二轮 `{}`；
- 第一轮有因子、第二轮 `{"factors": {}}`；
- 第一轮有因子、后续缺字段；
- 第一轮有因子、后续非法 JSON；
- 第一轮即无因子。

### 3.2 异常必须传播到进程退出码

文件：`rdagent/log/server/app.py`。

当前 `_run()` 的 `except Exception` 只打印 traceback。建议：

1. 打印完整 traceback 到 stdout 文件；
2. 保存一个短错误摘要供服务端读取；
3. 重新抛出异常，或显式设置失败退出码；
4. 保证 `Process.exitcode != 0`。

最小实现可以是：

```python
except Exception:
    traceback.print_exc()
    raise
```

更完整的实现应区分：

- `-1`：用户主动停止；
- `0`：正常完成；
- 非零正数：任务异常。

### 3.3 `/trace` 和前端状态统一

后端 `/trace` 生成 END 时根据退出码生成消息：

```json
{
  "tag": "END",
  "content": {
    "end_code": 1,
    "error_msg": "RD-Agent process failed; see stdout for details"
  }
}
```

前端 `deriveTraceStatus()` 不应只判断是否存在 `END`：

- `end_code === 0` → `done`；
- `end_code === -1` → `stopped`（或兼容映射为已停止）；
- `end_code > 0` → `error`；
- 无 END 且进程存活 → `running`。

如增加 `stopped`，同步修改 `TraceStatus`、任务列表和详情头部文案。

### 3.4 消除创建后首次 404

前端创建流程应保证“任务加入列表”和“路由跳转”有明确顺序：

1. `/upload` 返回 id；
2. 后端同步注册运行任务；
3. 前端将返回 id 立即加入本地列表，或等待 `/traces` 确认包含该 id；
4. 再执行 `selectTrace(id)` 和路由跳转；
5. 详情接口首次返回空消息时显示“准备中”，不能显示 404。

同时重启正在运行的旧后端，确认运行实例确实加载当前源码。验证时记录：

```bash
python -c 'import sys; print(sys.executable)'
python -c 'import rdagent; print(rdagent.__file__)'
```

## 4. P1 后端上传修复方案

### 4.1 调整 `/upload` 校验顺序

建议顺序：

```text
校验 scenario
校验 loops
校验文件数量、扩展名、MIME、大小
校验 PDF 可读取且至少一页
检查并发上限
写入临时目录
全部成功后原子移动到 trace 目录
启动任务
```

错误统一返回 JSON 4xx：

- 缺少 scenario：400；
- 非法 loops：400；
- 研报场景没有文件：400；
- 非 PDF：415；
- 损坏或空 PDF：422；
- 超过大小限制：413；
- 并发达到上限：429。

### 4.2 失败清理和文件名

- 每个请求使用临时上传目录；
- 任一文件失败时删除该临时目录；
- 全部文件校验通过后再移动；
- 服务端使用唯一安全文件名；
- 在 `manifest.json` 中记录原始文件名、大小、MIME 和上传时间；
- 中文名不再依赖 `secure_filename()` 作为唯一标识。

### 4.3 loops 语义

研报场景当前不使用前端 `loops`，实际数量由 `min(PDF 数量, report_limit)` 决定。应二选一：

1. 删除研报 Tab 的循环次数控件；或
2. 明确把 loops 定义为研报处理数量并传给后端。

在语义未统一前，前端不应让用户误以为可以控制研报实验轮数。

## 5. P1 前端状态修复方案

文件：`web/src/multialpha/components/NewTaskDialog.vue`。

- 取消、提交成功、弹窗关闭时清空 `files.value`；
- `form.method` 从 PDF 切换到其他 Tab 时清空文件队列；
- 提交前再次检查每个文件扩展名和 MIME；
- 使用 `:on-remove` 和关闭事件同时清理 Element Plus 上传控件与外层 `files` ref；
- 防止提交过程中重复点击启动。

## 6. 测试和发布顺序

### 第一阶段：单元测试

- 因子提取多轮响应测试；
- `_run()` 异常退出码测试；
- `/trace` 对 0、-1、正数退出码的测试；
- `/upload` 参数和文件校验测试；
- 前端 `deriveTraceStatus()` 状态测试。

### 第二阶段：API 集成测试

- 有效 PDF；
- 非量化 PDF；
- 空/损坏 PDF；
- 非 PDF；
- 缺少 scenario、非法 loops、空 files；
- 同名文件和并发上限；
- 失败后目录清理。

### 第三阶段：真实浏览器测试

重点复测：`FR-P0-01`、`FR-P0-05`、`FR-P0-09`、`FR-P0-10`、`FR-P1-05`、`FR-P1-06`、`FR-P1-09`、`FR-P1-10`、`FR-P1-11`、`FR-P1-16` 至 `FR-P1-19`。

验收条件：

- 有效研报最终出现因子或明确的业务失败原因；
- 内部异常不能显示“已完成”；
- 失败请求返回明确 JSON 错误；
- 首次创建后不出现 TRACE NOT FOUND；
- 30 条专项用例重新执行后，P0 全部通过。

## 7. 官方代码差异说明

Microsoft 官方 `RD-Agent main` 当前同样存在两处基线问题：

- `pdf_loader.py` 对 `ret_dict["factors"]` 的强制访问；
- `app.py` 捕获异常后仅 `traceback.print_exc()`。

本方案中的因子解析容错和异常退出传播属于本项目的修复增强，不是对官方当前实现行为的简单复述。
