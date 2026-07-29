# 设置页面设计

> 类型：技术方案设计
> 创建：2026-07-27
> 状态：**已实施**（commit `e9cefaf2` + `e55a7e84`）

---

## 1. 设计决策

| 维度 | 决策 |
|---|---|
| 整体布局 | 左导航 + 右表单（全屏，与 PredictDashboard 一致） |
| LLM 组 | 子卡片分区（连接配置 / 生成参数 / 分步路由） |
| Qlib 日期组 | 场景卡片（factor / model / quant 各一卡） |
| 保存反馈 | 轻提示（ElMessage 3s + 底部固定提示条） |
| 密钥处理 | 脱敏展示（含 `***`），👁切换，🔄重输；保存时脱敏值跳过 |
| 生效方式 | 写 .env + 重启生效 |
| 模型测试 | 🧪 按钮，chat 用 litellm.completion，embedding 用 litellm.embedding |

---

## 2. 字段清单（4 组 37 字段）

### LLM 配置（3 子卡片 13 字段）
- **连接配置**：CHAT_MODEL / EMBEDDING_MODEL / OPENAI_API_KEY(password) / OPENAI_API_BASE / CHAT_OPENAI_API_KEY(password) / CHAT_OPENAI_BASE_URL
- **生成参数**：CHAT_TEMPERATURE / CHAT_MAX_TOKENS / MAX_RETRY / RETRY_WAIT_SECONDS / USE_CHAT_CACHE / USE_EMBEDDING_CACHE
- **分步路由**：CHAT_MODEL_MAP（可视化表格，步骤名与智能体映射）

### 界面与并发（2 字段）
UI_MAX_CONCURRENT_TASKS / UI_MAX_INMEMORY_TRACES

### Qlib 日期（3 场景 18 字段）
QLIB_{FACTOR|MODEL|QUANT}_{TRAIN|VALID|TEST}_{START|END}

### 执行环境（4 字段）
QLIB_DOCKER_IMAGE / MODEL_CoSTEER_ENV_TYPE(select) / FACTOR_CoSTEER_PYTHON_BIN / CONDA_DEFAULT_ENV

---

## 3. 后端 API

| 接口 | 方法 | 作用 |
|---|---|---|
| `/settings/schema` | GET | 返回 schema + 当前值（密钥脱敏） |
| `/settings` | POST | 保存到 .env（密钥保护 + 备份 .env.bak + dotenv.set_key 原子写） |
| `/settings/test-model` | POST | 测试模型连通性（mode=chat/embedding，10s 超时） |

---

## 4. 实现文件

| 文件 | 说明 |
|---|---|
| `rdagent/log/server/settings_schema.py` | schema 定义 + 脱敏（mask_value / is_masked） |
| `rdagent/log/server/app.py` | 3 个 settings 端点 |
| `web/src/multialpha/components/SettingsPage.vue` | 设置页 UI（动态渲染 + 测试按钮 + 改动检测） |
| `web/src/multialpha/router.ts` | /settings 路由 |
| `web/src/multialpha/components/TopBar.vue` | ⚙️ 设置按钮入口 |
| `web/src/services/rdagent-api.ts` | fetchSettingsSchema / saveSettings / testModel |
