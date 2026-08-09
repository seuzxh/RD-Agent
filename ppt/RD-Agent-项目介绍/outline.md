# RD-Agent 项目介绍 PPT · 提纲（9 页）

> 位置：`ppt/RD-Agent-项目介绍/`
> - `outline.md`：本提纲
> - `index.html`：9 张 16:9 HTML 卡片（滚动式 PPT）
>
> 阅读顺序建议：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
>
> 标记约定：
> - 📖 引用的 `docs/` 文档/论文
> - 🔧 引用的代码锚点
> - 🟡 **待你补充**：需要你提供数字/截图/结论的位置
> - 💡 路演讲述要点（演讲时说什么）

---

## P1 · 项目概述与整体架构（1 页）

### 标题
**RD-Agent：基于多智能体的自动化量化研究平台**

### 左半区 · 项目背景
- 一句话定位：**让大模型代替研究员完成"提假设→写代码→回测→反馈"的完整 R&D 循环**
- 4 大场景入口：
  1. 因子研究（qlib_factor）
  2. 模型研究（qlib_model）
  3. 组合策略（qlib_quant）
  4. 研报因子抽取（factor_from_report）

### 右半区 · 5 角色 RDLoop 全流程图
```
HypothesisGen（假设生成）
        ↓
Developer（编码：CoSTEER）
        ↓
Runner（执行回测）
        ↓
Summarizer（反馈总结） ←── H2E（假设→实验反馈）
        ↓
     [回到 HypothesisGen，循环]
```

### 底部一行 key visual
多 LLM 标签：「4 phase 可独立配 LLM · 多模型路由 · 模型测试按钮」

📖 引用：
- `docs/papers/01-rdagent-framework.md`（RDLoop 总纲）
- `docs/rdagent-cn.md` 项目概览
- `docs/quickstart/Core.md` 核心流程

🔧 代码锚点：
- `rdagent/components/workflow/rd_loop.py` 主循环
- `rdagent/core/proposal.py` HypothesisGen 契约

🟡 待你补充：
- 项目 logo（如有）
- 项目启动时间 / 版本号

💡 讲述：「这页只讲两件事：我们是谁、我们的核心循环是什么。下面 7 页分别讲每个模块怎么做、效果如何、商业价值。」

---

## P2 · 成果与对标（1 页）⭐ 钩子页

### 标题
**量化成果 · 与 SOTA 对标**

### 主视觉 · 成果数字（4 个大数字卡片）
1. 🟡 **因子 / 模型任务累计完成数**（例如：完成 N 个因子任务、M 个模型任务）
2. 🟡 **因子还原成功率**（CoSTEER V2 vs V1：V2 = __%，V1 = __%）
3. 🟡 **NeurIPS 2025 录用**：R&D-Agent-Quant（2505.15155）
4. 🟡 **vs Alpha158+Linear 基线**：IC 提升 __% / 年化收益 __%

### 辅视觉 · 论文列表（6 篇核心论文 icon）
- R&D-Agent (2505.14738)
- R&D-Agent-Quant NeurIPS 2025 (2505.15155)
- Data-Centric Auto R&D (2404.11276)
- CoSTEER (2407.18690)
- Multi-Agent Quant (2505.13172)
- LinTS (ICML 2013)

### 底部一行
「1 个总框架 + 2 个核心智能体 + 4 个知识库 + 多 LLM 路由」

📖 引用：
- `docs/papers/README.md` 论文清单
- `docs/eval_results.md`（如有）

🟡 待你补充（**这页是核心，请务必补全数字**）：
- [ ] 真实任务数
- [ ] V1 vs V2 成功率对比
- [ ] 因子/模型在 qlib 数据集上的 IC / IR / 年化
- [ ] 单任务平均 loop 轮数 / 收敛时间

💡 讲述：「评委，这一页先告诉大家——我们不是 PPT 项目，我们跑出来了。具体数字请稍后看后面模块。」

---

## P3 · 假设生成智能体（HypothesisGen）（1 页）

### 标题
**P3 · 智能体 ①：假设生成 HypothesisGen**

### 左半区 · 三种动作选择策略对比
| 策略 | 逻辑 | 适用场景 |
|---|---|---|
| **LLM（默认）** | LLM 基于历史 Trace 生成新假设 | 默认路径，质量高 |
| **Random** | 随机采样，冷启动/探索用 | 知识库空时 |
| **Bandit（LinTS）** | 上下文汤普森采样，自动分配"因子/模型"研究精力 | 均衡探索-利用 |

### 右半区 · 自然语言 → 研究假设 demo
- Input：「最近 IC 下降，试试价量背离因子」
- Output：结构化 Hypothesis 对象（因子方向 + 数据集 + 实验配置）

### 底部 metric
🟡 **Bandit vs LLM：动作选择准确率提升 __%**（如有对比数据）

📖 引用：
- `docs/papers/02-rdagent-quant.md` 量化双管线
- `docs/papers/07-contextual-thompson-sampling.md` LinTS

🔧 代码锚点：
- `rdagent/scenarios/qlib/proposal/factor_proposal.py`
- `rdagent/scenarios/qlib/proposal/bandit.py`（`LinearThompsonTwoArm`）
- `rdagent/components/workflow/conf.py` `action_selection=bandit` 默认

🟡 待你补充：
- [ ] Bandit / LLM / Random 三者对比的小实验数字（如有）
- [ ] 一个真实的自然语言→Hypothesis 截图

💡 讲述：「假设生成是 loop 起点。我们不是纯靠 LLM 拍脑袋——有 Bandit 算法在后台做精力分配，知道什么时候研究因子、什么时候研究模型。」

---

## P4 · 编程智能体（CoSTEER Developer）（1 页）⭐ 技术亮点

### 标题
**P4 · 智能体 ②：CoSTEER 编码智能体**

### 主视觉 · 6 步循环图（V2 核心）
```
① Impersonate Role → ② Retrieve (三连查) → ③ Think
        → ④ Code → ⑤ Debug (with Feedback) → ⑥ Evolve (10 轮)
```

### 重点 · 三连查 V2（右侧列表）
1. **former_trace_query**：查"上一次做类似任务的成功 Trace"
2. **component_query**：查"知识库里相似组件代码"
3. **error_query**：查"历史同款报错 + 修复方案"

### 底部 · 两个关键 metric
- 🟡 **编码成功率**：V2 = __%（V1 = __%，提升 __pp）
- 🟡 **Token 消耗占比饼图**（占位，你补数字）
  - HypothesisGen __%
  - Developer **__%** ← 最大头
  - Runner 8%（无 LLM）
  - Summarizer __%
  - H2E __%
  - 每任务完整成本 ≈ ¥__

📖 引用：
- `docs/papers/04-costeer.md` CoSTEER 论文
- `ppt/CoSTEER机制详解/CoSTEER机制详解.html`（你已有单页 PPT，可以直接复用图）

🔧 代码锚点：
- `rdagent/components/coder/CoSTEER/evolving_strategy.py` 6 步循环
- `rdagent/components/coder/CoSTEER/knowledge_management.py` V2 三连查
- `rdagent/components/knowledge_management/graph.py` 知识图谱

🟡 待你补充：
- [ ] V1 vs V2 编码成功率（这是最硬的数字）
- [ ] 每 phase token 消耗百分比
- [ ] 单任务 token 成本（¥）

💡 讲述：「CoSTEER 是我们最核心的技术贡献——6 步演化循环 + V2 三连查，把一次性编码成功率从 ~20% 提到 __%。底部饼图告诉你：**优化 KB 命中率 = 直接降本**。」

---

## P5 · 回测执行 + 反馈总结（Runner + Summarizer）（1 页）

### 标题
**P5 · 智能体 ③④：Runner 回测 + Summarizer 反馈**

### 左半区 · Runner 做什么
- **SOTA 因子继承**：跑新因子前自动"抄作业"——加载同 model 下历史 SOTA 因子集
- **因子去重/合并**：相似度>80% 的因子合并，避免重复劳动
- **真实执行**：调用 qlib backtest，产出 IC/IR/年化/夏普

### 右半区 · Summarizer 做什么
- **4 维反馈**：
  1. 代码可执行性
  2. 信号质量（IC、IR）
  3. 与 SOTA 对比
  4. 下一步建议（自然语言）
- **Trace 持久化**：每轮结果入 log/，下一轮 HypothesisGen / CoSTEER 都能查

### 底部 · Trace 时序示意
```
T0: [Hyp] 价量背离 → [Dev] factor.py → [Run] IC=0.05 → [Sum] 换角度
T1: [Hyp] 动量反转 → [Dev] factor.py → [Run] IC=0.08 → [Sum] 超越 SOTA，入库
```

📖 引用：
- `docs/papers/02-rdagent-quant.md` §3.2 SOTA 继承
- `docs/papers/05-multiagent-quant.md` 5 智能体分工

🔧 代码锚点：
- `rdagent/components/runner/`（Runner 模块）
- `rdagent/components/feedback/`（Feedback/Summarizer）
- `rdagent/log/storage.py` Trace 持久化

🟡 待你补充：
- [ ] 一个真实 trace 截图（从 log/ui 截）
- [ ] SOTA 因子数目前有多少（知识库规模）

💡 讲述：「Runner 和 Summarizer 让系统**闭环**——跑出来的结果不会丢，全部沉淀成经验，下一轮直接用。这是 R&D loop 能持续收敛的关键。」

---

## P6 · 多 LLM 差异化路由（1 页）⭐ 产品亮点

### 标题
**P6 · 多 LLM 路由：每个 phase 独立配模型**

### 主视觉 · 4 phase × 多模型矩阵
| Phase | 默认模型 | 可切换模型（火山方舟 Coding Plan） |
|---|---|---|
| HypothesisGen | 🟡 | glm-5.2 / minimax-m3 / kimi-k2.7-code / deepseek-v4-flash |
| Developer (CoSTEER) | 🟡 | 同上，推荐 coding 专精模型 |
| Summarizer | 🟡 | 同上 |
| H2E | 🟡 | 同上 |

### 辅视觉 · 前端两个关键功能（截图占位）
1. **分步路由可视化编辑器**：UI 上拖拽选择每 phase 用什么模型
2. **模型测试按钮**：不消耗正式 run token，独立验证模型连通性

### 底部一行
「支持任意 OpenAI 兼容端点 + 模型缓存（Prefect）+ 命中即 ¥0」

📖 引用：
- `web/src/components/Header.tsx` 顶部模型选择 UI
- `rdagent/oai/` 多 LLM 后端适配
- `rdagent/components/agent/base.py` pydantic-ai MCP + enable_cache

🔧 代码锚点：
- `rdagent/oai/backend/` 多个后端
- `web/src/multialpha/use-multialpha.ts` 分步路由
- `.env.example` LLM 配置项

🟡 待你补充：
- [ ] 当前默认用的是哪个模型？
- [ ] 前端模型选择/测试按钮的截图（强烈建议放一张真实 UI 截图）

💡 讲述：「**不绑定任何单一 LLM**——这是我们和大多数开源多智能体项目最大的区别。用户可以按任务挑模型，coding 任务用 coding 专精模型，总结任务用便宜模型，成本可控。」

---

## P7 · 知识库全景（1 页）⭐ V2 为主，其他概览

### 标题
**P7 · 四层知识库：让经验不丢失**

### 主视觉 · 4 象限图（**V2 放左上最大块**，其他 3 个小块）

```
┌─────────────────────────┬─────────────────────┐
│ ① CoSTEER V2 知识图谱   │ ② Context7 外部文档  │
│ （项目内·编码阶段）      │ （跨项目·报错修复）   │
│ - UndirectedGraph       │ - timm/qlib/torch    │
│ - 三连查 former/comp/err│ - API 用法反查       │
│ - B1~B5 GT 还原经验     │ - MCP 外挂          │
├─────────────────────────┼─────────────────────┤
│ ③ RAG 通用外挂          │ ④ SOTA 知识库        │
│ （任意 phase·自定义源）  │ （项目内·量化经验）   │
│ - 券商研报/研报 PDF     │ - pickle 持久化      │
│ - 历史会议纪要等         │ - SOTA 因子自动继承   │
│                         │ - sota_query 反查    │
└─────────────────────────┴─────────────────────┘
```

### 底部一行
「项目内经验 + 跨项目文档 + 自定义源 + 量化 SOTA，四层协同」

📖 引用：
- `docs/papers/04-costeer.md` CoSTEER V2（核心）
- `rdagent/components/agent/context7/` Context7
- `rdagent/components/agent/rag/` 通用 RAG
- `rdagent/core/knowledge_base.py` SOTA KB
- `rdagent/log/sota_query.py` SOTA 查询

🔧 代码锚点：同上 4 个模块。

🟡 待你补充：
- [ ] V2 知识图谱目前有多少节点（Trace / component / error 各多少）
- [ ] SOTA 因子库规模（多少条）

💡 讲述：「V2 是主力，其他 3 个是配套——**Context7 查别人家文档，RAG 挂自定义源，SOTA KB 记量化经验**。四层加起来，系统才真正"越跑越聪明"。」

---

## P8 · 应用与商业价值（1 页）

### 标题
**P8 · 应用场景与商业价值**

### 左半区 · 三类目标客群
| 客群 | 痛点 | 我们的价值 |
|---|---|---|
| **券商自营 / 公募量化** | 研究员稀缺、年度人力成本 50w+/人 | 自动挖因子 + 回测 + SOTA 继承，1 个系统顶 N 个研究员 |
| **量化私募** | 模型更新慢、跨市场适配贵 | 双管线 + Bandit 自动分配，24h 不停跑 |
| **量化教育 / 研究机构** | 论文复现难、教学成本高 | Paper-to-Code Benchmark 端到端可复现 |

### 右半区 · 成本对比表
| 方式 | 单个因子时间 | 单个因子成本 |
|---|---|---|
| 人工研究员 | 🟡 __ 天 | 🟡 ¥__（估） |
| RD-Agent 自动 | 🟡 __ 小时 | 🟡 ¥__ token |
| **降幅** | **__×** | **__%** |

### 底部 · 商业化路径（3 条）
1. **SDK 授权**：给机构内网部署
2. **SaaS 平台**：按 token / 按任务计费
3. **量化研究即服务 QRaaS**：按产出因子/策略计费

📖 引用：
- 无特定 docs，基于项目能力推导

🟡 待你补充：
- [ ] 人工单因子的真实耗时/成本（按你团队实际估）
- [ ] 系统跑单因子的真实耗时/cost
- [ ] 是否有试用客户 / POC 进展（可模糊表述，如"已与 X 家机构沟通"）

💡 讲述：「**一个量化研究员一年 50-100w**，我们的系统一套授权远低于这个数，还能 24 小时跑——这是最朴素的商业逻辑。」

---

## P9 · 创新点 + 论文 + 后续规划（1 页）收尾

### 标题
**P9 · 创新点 · 学术成果 · 后续规划**

### 上半区 · 4 大创新点（人话）
1. **架构创新**：5 角色多智能体 R&D-Loop，把"研究→代码→回测"全自动串起来
2. **方法创新**：CoSTEER V2 三连查知识图谱，编码成功率从 ~20% 提升到 __%
3. **产品创新**：多 LLM 分步路由 + 模型测试按钮，不绑定单一厂商
4. **评估创新**：端到端 Paper-to-Code Benchmark（B1~B5 5 个 GNN 模型），可量化可复现

### 中半区 · 学术成果（论文列表）
- NeurIPS 2025：R&D-Agent-Quant
- 其他 5 篇 arXiv（见 P2）
- 🟡 是否还有其他在投/准备投的论文？

### 下半区 · 后续规划（3 段）
- **短期（3 个月）**：B2 ViSNet 还原率提升、Bandit 权重调优、股池低延迟优化、Mem0 跨 KB 长期记忆
- **中期（6 个月）**：多市场扩展（加密/港美股）、跨用户共享 SOTA KB、研报→因子在线学习
- **长期（12 个月）**：无人化量化研究 SaaS、开放 Benchmark 平台、跨团队联邦 RAG

### 最底部 · 联系方式占位
🟡 GitHub 地址 / 文档地址 / 团队联系方式

📖 引用：
- `docs/papers/` 全部 12 篇论文
- `docs/Roadmap.md`（如存在）

🟡 待你补充：
- [ ] 4 大创新点是否需要调整措辞
- [ ] 是否有其他在投论文
- [ ] GitHub / 文档 / 联系方式

💡 讲述：「最后一页——**创新在哪、论文在哪、下一步做什么**。评委记住这三点就够了。欢迎交流，谢谢。」

---

## 附录 A · 待补充清单汇总（🟡 全部）

按页汇总，方便你一次填完：

| 页 | 需补充项 |
|---|---|
| P1 | 项目 logo / 启动时间 / 版本号 |
| P2 | 任务总数、V1 vs V2 成功率、vs Alpha158+Linear IC/年化、平均 loop 数/收敛时间 |
| P3 | Bandit/LLM/Random 对比数字、一个真实 Hypothesis 截图 |
| P4 | V1 vs V2 成功率、每 phase token %、单任务 ¥ 成本 |
| P5 | 真实 trace 截图、SOTA 因子数 |
| P6 | 各 phase 默认模型、前端模型选择/测试按钮截图 |
| P7 | V2 图谱节点数、SOTA 因子库规模 |
| P8 | 人工 vs 系统 单因子耗时/成本、POC 客户数（如有） |
| P9 | 在投论文、联系方式 |

## 附录 B · 视觉风格统一约定

- 配色：深色底（#0d0d12）+ 橙色 accent（#ff7a1a）+ 灰阶文字
- 字体：等宽（JetBrains Mono / Menlo）用于代码/数字，非衬线（Inter / 思源黑体）用于正文
- 比例：16:9（1280×720）
- 每页固定布局：标题 60px + 主视觉（图/表/流程）+ 底部 1 行 metric
- 卡片间距、圆角（12px）统一
- 每页右下页码 / 共 9 页

---

*本提纲最后更新：2026-08-09*
