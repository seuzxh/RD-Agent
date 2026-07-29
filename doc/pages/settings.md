# 设置页（`#/settings`）

> 路由：`multialpha-settings` · 组件：`SettingsPage`
> 本页覆盖：LLM 配置、界面并发、Qlib 日期、执行环境、模型连通性测试

---

## 1. 功能需求（PRD）

### 1.1 LLM 配置
- **连接配置**：聊天模型 / Embedding 模型 / API Key（脱敏）/ API Base / 聊天专用 Key+Base
- **生成参数**：温度 / 最大Token / 重试次数 / 重试等待 / 聊天缓存 / Embedding缓存
- **分步模型路由**：可视化表格（步骤→模型→温度），步骤名与智能体映射

### 1.2 界面与并发
- 并发任务上限（默认 10）/ 内存任务上限（默认 20）

### 1.3 Qlib 日期
- 3 场景（因子挖掘/模型实现/量化全流程）× 6 日期字段（训练/验证/测试 start~end）

### 1.4 执行环境
- Docker 镜像 / 模型执行环境（conda/docker）/ 因子 Python 路径 / Conda 环境名

### 1.5 模型测试
- 🧪 测试按钮：chat 模型 + embedding 模型 + 分步路由每行模型
- 返回连通状态 + 延迟 + 错误信息

### 1.6 保存
- 写 .env + 提示「需重启生效」+ 密钥保护（脱敏值跳过）

---

## 2. 技术方案

### 2.1 数据流
```
进入页面 → GET /settings/schema → 渲染表单（密钥脱敏）
用户编辑 → 各字段本地状态
点击测试 → POST /settings/test-model → 显示结果
点击保存 → POST /settings（只提交改动字段）→ ElMessage 成功提示
```

### 2.2 分步路由步骤名映射（与 AgentFlow 智能体一致）
| 设置页显示 | 后端 step key |
|---|---|
| 🧠 假设生成 | `hypothesis` |
| ✏️ 实验设计 | `direct_exp_gen` |
| ▰ 代码实现 | `coding` |
| 📊 回测执行 | `running` |
| 🔍 反馈评审 | `feedback` |

---

## 3. 接口契约

### `GET /settings/schema`
返回 4 分组 37 字段 + 当前值（密钥脱敏）。model_map 类型返回 dict。

### `POST /settings`
- 密钥保护：含 `***` 的值跳过
- dict/list 序列化为 JSON 写入
- 写前备份 .env.bak
- 响应：`{ status, written, skipped, restart_required: true }`

### `POST /settings/test-model`
- 参数：`{ model, api_key, api_base, mode }`（mode: chat|embedding）
- chat：litellm.completion(max_tokens=1)
- embedding：litellm.embedding(input=["test"])
- 10s 超时，密钥为空回退 .env
- 响应：`{ ok, latency_ms, error }`

---

## 4. 实现索引

| 文件 | 作用 |
|---|---|
| `components/SettingsPage.vue` | 设置页 UI（动态渲染 + 测试 + 改动检测） |
| `services/rdagent-api.ts` | fetchSettingsSchema / saveSettings / testModel |
| `rdagent/log/server/settings_schema.py` | schema 定义 + 脱敏 |
| `rdagent/log/server/app.py` | 3 个 settings 端点 |

详见 [设置页面设计](../design/SETTINGS_PAGE_DESIGN.md)
