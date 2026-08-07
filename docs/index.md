---
title: MultiAlpha 文档
description: 基于 RD-Agent + Qlib 的量化金融因子挖掘平台文档
layout: default
---

# MultiAlpha 文档

> 基于 RD-Agent + Qlib 的量化金融因子挖掘平台
>
> 文档与代码同仓库管理（位于 `RD-Agent/doc/`），按**文档性质**分类组织。

## 分类说明

| 分类 | 回答的问题 | 适合的读者 |
|---|---|---|
| 📋 **PRD** | 产品要做成什么样？功能范围？ | 产品 / 需求方 |
| 📄 **页面功能** | 每个页面做什么？PRD+技术+接口+实现 | 产品 / 开发 / 测试 |
| 🛠 **技术方案** | 怎么实现？架构选型与改造点？ | 开发者 |
| 🏛 **架构** | 系统现在长什么样？运作机制？ | 新人入门 / 排查问题 |
| 📚 **接口参考** | 接口 / 配置 / 命令速查 | 日常查阅 |
| 📗 **指南** | 按步骤完成某事 | 首次搭建 / 验证 |
| 🧪 **测试** | 用例 / 报告 / 问题追踪 | QA / 验收 |
| ❓ **FAQ** | 常见问题排错 | 所有人 |
| 🤝 **规范** | 团队协作流程 | 全员 |

---

## 📋 PRD（产品需求文档）

- [股池预测看板 PRD](prd/STOCKPOOL_DASHBOARD_PRD.md) — T+1 实战预测产品需求（v2.0 MVP）

## 📄 页面功能文档（按页面组织，含 PRD + 技术 + 接口 + 实现）

- [首页](pages/home.md) — `#/` 任务列表 / 首屏仪表盘 / 任务入口 / 顶栏操作
- [任务详情页](pages/detail.md) — `#/tasks/:id` 迭代过程 / 结果工作区 / 运行日志 / SOTA
- [新建任务](pages/create-task.md) — 表单 / 文件上传 / 并发限制 / 启动流程
- [设置页](pages/settings.md) — `#/settings` LLM配置 / 并发 / Qlib日期 / 执行环境 / 模型测试

## 🛠 技术方案 / 设计

- [Factor 模型选择器](design/FACTOR_MODEL_SELECTOR.md) — lgbm/linear/xgboost/catboost 下拉选择，4 层改造点
- [股池预测看板技术方案](design/STOCKPOOL_DASHBOARD_TECH.md) — 零新依赖，扩展现有 Flask + RDAgentTask
- [webUI 性能优化最终设计](design/WEBUI_PERFORMANCE_FINAL.md) — 三个分离 + C1-C10 改造点 + CDN 决策
- [任务状态判断修复](design/TRACE_STATUS_FIX.md) — stop/异常终止后仍显示 running 的根因（3 个 bug）与修复方案
- [任务并发限制](design/TASK_CONCURRENCY_LIMIT.md) — 运行中任务达上限（默认 10）禁止新建，前后端配合
- [设置页面设计](design/SETTINGS_PAGE_DESIGN.md) — 4分组37字段 + 密钥脱敏 + 模型测试 + 分步路由可视化

## 🏛 架构说明

- [源码结构清单](architecture/STRUCTURE.md) — `rdagent/` 全部子目录与文件作用清单（core/components/scenarios/oai/log/utils/app 七大层）
- [数据流与执行架构](architecture/data-flow.md) — generate.py 数据预处理 / Docker 执行 / CoSTEER 迭代 / LLM 调用全链路
- [RD-Agent tag 体系详解](architecture/rdagent-tag-system.md) — tag 生成 / 嵌套 / 匹配 / 提取全链路 + 完整 tag 字典
- [场景任务信息存放路径规则](architecture/trace-storage-paths.md) — trace pickle / stdout / uploads / __session__ 落盘规则与错位陷阱
- [webUI 任务详情看板内容来源](architecture/webui-task-detail-sources.md) — 前端字段 → 消息 tag → 后端对象 → pickle 全链路映射
- [Qlib 四大场景](architecture/QLIB_SCENARIOS.md) — factor / model / quant / factor_from_report 训练机制与模型来源
- [webUI API 迁移调研](architecture/WEBUI_API_MIGRATION.md) — 老 vs 新项目 6 接口对比 + Range 增量轮询（现状调研，非新设计）

## 🤖 核心智能体说明

> multialpha 的 R&D 循环由五个核心智能体协作驱动：从假设生成到实验设计、代码编写、执行回测、反馈总结的完整闭环。

- [智能体总览（README）](agents/README.md) — 五个智能体总览、闭环流程图、多 LLM 配置、数据流转、场景入口
- [01. HypothesisGen 假设生成](agents/01-hypothesis-gen.md) — 基于历史反馈生成研究方向，支持 Bandit/LLM/Random 动作选择
- [02. CoSTEER 编码进化](agents/02-costeer.md) — 多轮"生成→执行→评估→修正"循环，含图知识库与 RAG 检索
- [03. Runner 方案执行](agents/03-runner.md) — 隔离环境中执行代码，含缓存机制、因子计算、模型训练与回测
- [04. Summarizer 反馈总结](agents/04-summarizer.md) — 回测结果分析、SOTA 对比、反馈生成与决策
- [05. Hypothesis2Experiment 假设转实验](agents/05-hypothesis2experiment.md) — 抽象假设转化为结构化可执行任务列表

## 📚 接口参考

- [API 参考](reference/API.md) — CLI 命令 / HTTP API（Flask 路由）/ Python 库 API / 配置接口四大类
- [环境配置说明](reference/ENV.md) — .env 全量字段、Pydantic Settings 加载机制、死配置清单
- [双仓库结构](reference/REPOS.md) — multialphaV 根仓库 + RD-Agent fork 的关系、分支与 commit 历史

## 📗 指南

- [环境搭建计划](guide/PLAN-env-setup.md) — conda env / .env / qlib 数据软链 / Docker / CodeGraph / git remote，6 阶段执行
- [四场景验证记录](guide/VERIFICATION-log.md) — factor / model / quant / factor_from_report 真实执行验证与已修复问题

## 🧪 测试

- [测试文档总览](testing/README.md) — 活跃文档表 + 历史归档表 + 迭代关系图
- [测试用例规范](testing/WEBUI_MULTIALPHA_TEST_CASES.md) — P0/P1/P2 全功能用例（68+13+12 条）
- [性能优化分支浏览器实测报告](testing/WEBUI_PERF_BROWSER_TEST_REPORT.md) — C1-C10 实测，当前权威报告（2026-07-26）
- [测试问题清单](testing/WEBUI_TEST_ISSUES.md) — 已知问题追踪 + 修复 commit 记录
- [历史测试归档](testing/archive/) — 5 份早期测试报告（FACTOR / MULTIALPHA / FULL / BROWSER_E2E 等）

## ❓ FAQ

- [常见问题](faq/faq.md) — rdagent 版本获取 / Python 选择（3.10）/ market 配置 / embedding bug / Docker 死循环等

## 🤝 协作规范

- [多人协作规范](COLLABORATION.md) — 分支策略 / 双仓库分工 / 环境一致性 / LLM·Embedding Key 管理 / trace 共享 / Code Review 流程

---

## 站点配置

本目录同时作为 Jekyll 站点源（`_config.yml`），可在 GitHub Pages 渲染。Markdown 间链接均为相对路径，本地用任意 markdown 预览器或 `mdserve` / `vitepress` 均可浏览。
