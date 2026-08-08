# 测试文档

> multiα1pha webUI 测试相关文档索引。测试用例规范、测试报告、问题追踪。

## 活跃文档

| 文档 | 用途 | 更新日期 |
|------|------|----------|
| [WEBUI_MULTIALPHA_TEST_CASES.md](WEBUI_MULTIALPHA_TEST_CASES.md) | **测试用例规范**（P0/P1/P2 共 93 条，覆盖创建→挖掘→交互→预测→日志→健康全模块） | 2026-07-24 |
| [WEBUI_PERF_BROWSER_TEST_REPORT.md](WEBUI_PERF_BROWSER_TEST_REPORT.md) | **当前权威测试报告**（C1–C10 性能改造 + 4 个 bug 修复的浏览器端实测，全部问题已修复并复测通过） | 2026-07-26 |
| [WEBUI_TEST_ISSUES.md](WEBUI_TEST_ISSUES.md) | **问题追踪清单**（已确认正常项 + 功能缺失 + 待验证项 + 修复 commit 记录） | 2026-07-24 |

> 性能审计与优化设计见 [`../design/WEBUI_PERFORMANCE_FINAL.md`](../design/WEBUI_PERFORMANCE_FINAL.md)。

## 历史归档（archive/）

早期测试报告按时间迭代替代，保留以供历史追溯。**当前权威报告为 `WEBUI_PERF_BROWSER_TEST_REPORT.md`**（见上表），归档报告仅作参考。

| 归档文档 | 日期 | 测试方式 | 被替代原因 |
|----------|------|----------|------------|
| [archive/WEBUI_FACTOR_TEST_CASES.md](archive/WEBUI_FACTOR_TEST_CASES.md) | 2026-07-20 | 因子挖掘单场景 | 被 `WEBUI_MULTIALPHA_TEST_CASES.md`（全功能 93 条）涵盖 |
| [archive/WEBUI_FACTOR_TEST_REPORT.md](archive/WEBUI_FACTOR_TEST_REPORT.md) | 2026-07-20 | API 验证 + 日志分析 | 无法操作浏览器，仅验证 API 层；后续报告补全了 UI 层 |
| [archive/WEBUI_MULTIALPHA_TEST_REPORT.md](archive/WEBUI_MULTIALPHA_TEST_REPORT.md) | 2026-07-24 R1 | Trae 内置浏览器 | 修复了 4 个 bug（vite proxy / 状态 / Token / 健康），但未覆盖全量用例 |
| [archive/WEBUI_FULL_TEST_REPORT.md](archive/WEBUI_FULL_TEST_REPORT.md) | 2026-07-24 R2 | Playwright + OpenPreview | 17 条用例 16 PASS，但发现 dist 过期根因；BROWSER_E2E 报告在其基础上扩展至 57 条 |
| [archive/WEBUI_BROWSER_E2E_TEST_REPORT_20260724.md](archive/WEBUI_BROWSER_E2E_TEST_REPORT_20260724.md) | 2026-07-24 | agent-browser 57 条 | 性能优化前的功能基线，0 缺陷；PERF 报告在其上增加性能维度并发现 chart 回归 |

## 迭代关系

```
WEBUI_FACTOR_TEST_REPORT (07-20, API only)
    ↓ 扩展至全功能
WEBUI_MULTIALPHA_TEST_REPORT (07-24 R1, Trae browser, 4 bugs fixed)
    ↓ 自动化 + dist 修复
WEBUI_FULL_TEST_REPORT (07-24 R2, Playwright, 17 cases)
    ↓ 全面扩展 + agent-browser
WEBUI_BROWSER_E2E_TEST_REPORT (07-24, 57 cases, 0 defects)
    ↓ 增加性能维度（web-vitals + PERF 中间件）
WEBUI_PERF_BROWSER_TEST_REPORT (07-26, 4 bugs fixed + 复测通过) ← 当前权威
```
