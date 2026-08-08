# 应用场景总览

multiα1pha 提供四种量化研究挖掘场景，适用于不同的研究需求和输入方式。每个场景复用相同的智能体框架，但在入口方式、循环控制、数据流转上有所差异。

---

## 场景对比

| 维度 | 因子挖掘 (Factor) | 研报复现 (Report) | 模型调优 (Model) | 全流程 (Quant) |
|------|-----------------|------------------|-----------------|----------------|
| **入口文件** | [factor.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py) | [factor_from_report.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor_from_report.py) | [model.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/model.py) | [quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py) |
| **创意来源** | LLM 自主探索 | PDF 研报中的因子公式 | LLM 自主探索 | LLM + Bandit 协同探索 |
| **进化目标** | alpha 因子（量价/基本面/ML） | 复现研报因子 | PyTorch 预测模型 | 因子 + 模型协同进化 |
| **验证模型** | LightGBM（默认）/Linear/XGBoost/CatBoost | 同 Factor | LLM 生成的 PyTorch 模型 | 同各子场景 |
| **HypothesisGen** | ✅ 使用 | ❌ 绕过（事后生成描述） | ✅ 使用 | ✅ 使用（含 action 选择） |
| **H2E** | ✅ 使用 | ❌ 绕过（PDF Loader） | ✅ 使用 | ✅ 使用（双管线） |
| **CoSTEER 目标** | factor.py（因子计算代码） | factor.py（因子计算代码） | model.py（PyTorch模型） | 根据action路由 |
| **数据划分** | 2008-2014 / 2015-2016 / 2017+ | 同 Factor | 2008-2014 / 2015-2016 / 2017+ | 同 Factor/Model |
| **默认 evolving_n** | 10 | 10 | 10 | 10 |
| **环境变量前缀** | `QLIB_FACTOR_` | `QLIB_FACTOR_`（继承） | `QLIB_MODEL_` | `QLIB_QUANT_` |
| **并行支持** | ✅ asyncio | ✅ | ✅ | ✅ |
| **模型类型** | 固定 ML 模型 | 固定 ML 模型 | Tabular / TimeSeries | Tabular / TimeSeries |

---

## 四个场景详细文档

| 场景 | 文档 | 适用场景 |
|------|------|---------|
| 🔍 因子挖掘 | [01-factor.md](01-factor.md) | 从零开始自动探索 alpha 因子，发现新的量价/基本面/ML 因子 |
| 📄 研报复现 | [02-report.md](02-report.md) | 从券商 PDF 研报中提取因子公式并自动编码验证 |
| 🧠 模型调优 | [03-model.md](03-model.md) | 基于固定因子集优化 PyTorch 预测模型架构和超参数 |
| 🔄 全流程协同 | [04-quant.md](04-quant.md) | 因子和模型协同进化，Bandit/LLM 自动分配探索资源 |

---

## 通用数据规范

四个场景共享以下数据约定：

### 市场与标的
- **股票池**：CSI300（沪深300成分股）
- **基准指数**：SH000300
- **数据频率**：日线
- **标签**：`Ref($close, -2)/Ref($close, -1) - 1`（T+2 收益率）

### 时间划分
| 数据集 | 时间段 | 样本量(约) | 用途 |
|--------|--------|-----------|------|
| 训练集 | 2008-01-01 ~ 2014-12-31 | ~478,000 | 模型训练 |
| 验证集 | 2015-01-01 ~ 2016-12-31 | ~128,000 | 早停、超参选择 |
| 测试集 | 2017-01-01 ~ auto(最新) | - | 回测评估 |

### 核心评估指标
| 指标 | 含义 | 方向 |
|------|------|------|
| IC (Information Coefficient) | 预测值与未来收益的秩相关系数 | 越高越好 |
| ARR (Annualized Return) | 年化超额收益（扣费后） | 越高越好 |
| MDD (Max Drawdown) | 最大回撤 | 越低越好（取负值参与奖励计算）|
| Sharpe Ratio | 风险调整后收益 | 越高越好 |

### 回测策略
- **选股策略**：TopkDropoutStrategy
- **持仓数**：topk=50
- **换仓规则**：n_drop=5（每次换仓替换5只）
- **手续费**：买入 0.05%，卖出 0.15%，最低 5 元
- **涨跌停**：限制 0.095
