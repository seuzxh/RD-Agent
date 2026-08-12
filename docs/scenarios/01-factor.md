# 因子挖掘场景（Factor）

> 自动发现和实现新的 alpha 因子。LLM 自主生成假设→转化为因子任务→CoSTEER 编码实现→回测验证→反馈迭代，通过渐进式复杂度策略先简单后复杂地探索因子空间。

---

## 1. 场景概述

因子挖掘是 multiα1pha 最基础的场景，目标是在给定市场数据（CSI300日线）上自动发现有效的量化因子。系统从零开始，通过 R&D 循环迭代，逐步积累有效的 alpha 因子库。

**核心特点**：
- 🧪 **LLM 自主探索**：不需要用户提供因子公式或研报，由假设生成智能体自主探索因子空间
- 📈 **渐进式复杂度**：前15轮（`len(trace.hist)<15`）优先尝试简单量价因子，第16轮起（`len(trace.hist)>=15`）探索 ML-based 等复杂因子（代码 [factor_proposal.py:38-41](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L38-L41) 判断 `len(trace.hist)`）
- 🔗 **因子累积机制**：成功因子自动进入 SOTA 因子库，新因子与 SOTA 因子组合回测
- 🔄 **IC 去重**：与已有 SOTA 因子相关系数 ≥0.99 的新因子自动剔除
- 🛡️ **错误容错**：因子执行失败（FactorEmptyError）不中断循环，跳过当前轮继续

---

## 2. 启动方式

```bash
# 默认启动（使用 ALPHA20 基础因子）
dotenv run -- python rdagent/app/qlib_rd_loop/factor.py

# 指定运行轮数和描述
dotenv run -- python rdagent/app/qlib_rd_loop/factor.py --loop_n 30 --description "探索动量反转类因子"

# 从断点恢复
dotenv run -- python rdagent/app/qlib_rd_loop/factor.py $LOG_PATH/__session__/1/0_propose

# 使用自定义基础因子
dotenv run -- python rdagent/app/qlib_rd_loop/factor.py --base_features_path ./my_factors/
```

### CLI 参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `path` | str | None | 断点恢复路径 |
| `loop_n` | int | None | 最大循环轮数（None=无限） |
| `step_n` | int | None | 最大步骤数 |
| `all_duration` | str | None | 最大运行时长（如 "24h"） |
| `description` | str | None | 用户目标描述 |
| `auto_mode` | bool | False | 全自动模式（无交互） |
| `base_features_path` | str | None | 自定义基础因子目录（含 base_factors.json 和 .py） |

---

## 3. 配置

环境变量前缀：**`QLIB_FACTOR_`**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `QLIB_FACTOR_HYPOTHESIS_GEN` | QlibFactorHypothesisGen | 假设生成类 |
| `QLIB_FACTOR_HYPOTHESIS2EXPERIMENT` | QlibFactorHypothesis2Experiment | 假设转实验类 |
| `QLIB_FACTOR_CODER` | QlibFactorCoSTEER | 编码进化类 |
| `QLIB_FACTOR_RUNNER` | QlibFactorRunner | 回测执行类 |
| `QLIB_FACTOR_SUMMARIZER` | QlibFactorExperiment2Feedback | 反馈生成类 |
| `QLIB_FACTOR_EVOLVING_N` | 10 | CoSTEER 内部编码迭代轮数 |
| `QLIB_FACTOR_MODEL_SELECTOR` | lgbm | 因子验证模型：lgbm/linear/xgboost/catboost |
| `QLIB_FACTOR_TRAIN_START/END` | 2008-01-01 / 2014-12-31 | 训练集 |
| `QLIB_FACTOR_VALID_START/END` | 2015-01-01 / 2016-12-31 | 验证集 |
| `QLIB_FACTOR_TEST_START/END` | 2017-01-01 / auto | 测试集（auto=最新交易日） |

---

## 4. 组件实例

```
FactorRDLoop
├── scen:           QlibFactorScenario
├── hypothesis_gen: QlibFactorHypothesisGen    (模型/temperature由 CHAT_MODEL_MAP 配置路由，见 .env)
├── h2e:            QlibFactorHypothesis2Experiment
├── coder:          QlibFactorCoSTEER          (模型/temperature由 CHAT_MODEL_MAP 配置路由，evolving_n=10)
│   └── evolving_version: 2 (图知识库V2)
├── runner:         QlibFactorRunner           (无LLM调用)
│   ├── process_factor_data() → 收集SOTA因子+新因子
│   ├── deduplicate_new_factors() → IC去重(阈值0.99)
│   └── execute() → Docker内qrun回测
└── summarizer:     QlibFactorExperiment2Feedback (模型/temperature由 CHAT_MODEL_MAP 配置路由)
```

---

## 5. 完整工作流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    FactorRDLoop 主循环                           │
│                                                                 │
│  [初始化] plan = {features: ALPHA20, feature_codes: {}}         │
│                                                                 │
│  ┌─── Loop N ────────────────────────────────────────────────┐  │
│  │                                                           │  │
│  │  ① direct_exp_gen()                                       │  │
│  │  ├─ _propose(): QlibFactorHypothesisGen.gen(trace)        │  │
│  │  │   ├─ prepare_context() 组装提示词：                      │  │
│  │  │   │   ├─ hypothesis_and_feedback: 完整历史链           │  │
│  │  │   │   ├─ last_hypothesis_and_feedback: 最近一轮        │  │
│  │  │   │   ├─ RAG: hist<15→"先简单因子"; hist≥15→"ML因子"   │  │
│  │  │   │   ├─ hypothesis_output_format: JSON格式要求        │  │
│  │  │   │   └─ hypothesis_specification: 因子生成规范         │  │
│  │  │   ├─ LLM生成Hypothesis(hypothesis, reason)              │  │
│  │  │   └─ 用户交互修改(可选)                                  │  │
│  │  │                                                        │  │
│  │  └─ _exp_gen(): QlibFactorHypothesis2Experiment.convert() │  │
│  │      ├─ prepare_context() 组装场景/历史链/输出格式等上下文   │  │
│  │      │   （不接收SOTA因子列表参数）                         │  │
│  │      ├─ LLM将假设转化为FactorTask列表(名称/描述/公式/变量)  │  │
│  │      ├─ 去重：convert()内部遍历based_experiments，基于trace │  │
│  │      │   剔除与SOTA/本轮已有因子同名的重复任务              │  │
│  │  ├─ 设置based_experiments（H2E负责构建）:               │  │
│  │  │   空基线实验 + trace中decision=True的历史因子实验    │  │
│  │  │   （注：t[1]作为feedback对象，__bool__返回decision） │  │
│  │      └─ 注入base_features(ALPHA20)                         │  │
│  │                                                           │  │
│  │  ② coding() — QlibFactorCoSTEER.develop(exp)              │  │
│  │  ├─ 将Experiment转为EvolvingItem                           │  │
│  │  ├─ 多轮进化循环(最多evolving_n=10轮)：                     │  │
│  │  │   ├─ RAG检索(图知识库V2三步检索)：                        │  │
│  │  │   │   ├─ former_trace: 最近失败轨迹                    │  │
│  │  │   │   ├─ component: 组件相似成功实现                    │  │
│  │  │   │   └─ error: 同类错误修复方案                        │  │
│  │  │   ├─ FactorMultiProcessEvolvingStrategy: LLM生成/修改  │  │
│  │  │   │   factor.py代码                                    │  │
│  │  │   ├─ 本地执行factor.py（LocalEnv+Conda），生成result.h5│  │
│  │  │   ├─ 多层评估：                                         │  │
│  │  │   │   ├─ 执行检查：代码能否运行，收集execution_feedback │  │
│  │  │   │   ├─ 形状/值检查（FactorValueEvaluator，含多个子   │  │
│  │  │   │   │   检查器：单列/Inf/输出格式/日频/行数/索引/     │  │
│  │  │   │   │   缺失值/等值率/相关性等）                      │  │
│  │  │   │   ├─ LLM代码评审（FactorCodeEvaluator）            │  │
│  │  │   │   └─ 最终决策（FactorFinalDecisionEvaluator）      │  │
│  │  │   └─ 知识更新：成功时写入图知识库(component/task/error) │  │
│  │  └─ 返回填充了代码的Experiment                              │  │
│  │                                                           │  │
│  │  ③ running() — QlibFactorRunner.develop(exp)              │  │
│  │  ├─ 处理based_experiments链中最后一个基线                  │  │
│  │  │   （若其result为None则递归调用一次develop确保有结果）    │  │
│  │  ├─ process_factor_data(based_experiments):               │  │
│  │  │   并行执行所有SOTA因子代码→拼接SOTA因子DataFrame         │  │
│  │  ├─ process_factor_data(exp): 执行本轮新因子代码            │  │
│  │  ├─ deduplicate_new_factors(): IC去重(≥0.99剔除)           │  │
│  │  ├─ 拼接: combined = concat([SOTA_factors, new_factors])  │  │
│  │  ├─ 保存为 combined_factors_df.parquet                    │  │
│  │  ├─ 注入Docker工作空间，渲染配置yaml:                      │  │
│  │  │   ├─ based_experiments中无SOTA model → conf_combined_factors.yaml
│  │  │   │   (由model_selector选择LGBM/Linear/XGBoost/CatBoost + combined factors)
│  │  │   └─ based_experiments中有SOTA model → conf_combined_factors_sota_model.yaml
│  │  │       (复用SOTA模型结构+超参 + combined factors)        │  │
│  │  ├─ Docker内执行qrun: 训练模型 + 回测
│  │  ├─ 解析mlflow结果→IC/ARR/MDD等指标
│  │  └─ 如果exp为None→抛FactorEmptyError→跳过本轮
│  │                                                           │  │
│  │  ④ feedback()                                             │  │
│  │  ├─ 异常情况：生成decision=False的反馈                      │  │
│  │  └─ 正常：QlibFactorExperiment2Feedback.generate_feedback │  │
│  │      ├─ 提取当前实验vs SOTA实验的三个核心指标：              │  │
│  │      │   IC / Annualized Return / Max Drawdown             │  │
│  │      ├─ LLM对比分析：Observations/Hypothesis Eval/        │  │
│  │      │   New Hypothesis/Reason/Decision(replace SOTA?)    │  │
│  │      └─ 用户交互修改(可选)                                  │  │
│  │                                                           │  │
│  │  ⑤ record()                                               │  │
│  │  └─ trace.sync_dag_parent_and_hist((exp, feedback), idx)  │  │
│  │      将(实验,反馈)追加到trace.hist，更新DAG                  │  │
│  │                                                           │  │
│  └─── 进入下一轮 ────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 核心机制详解

### 6.1 SOTA 因子累积与组合

每轮新因子不是单独回测，而是与所有历史成功因子**组合后**一起回测：

```
Round 0: [ALPHA20(20个)] + [新因子1] → 21个因子 → LGBM训练 → 回测
Round 1: [ALPHA20 + 因子1(SOTA)] + [新因子2] → 22个因子 → LGBM训练 → 回测
Round 2: [ALPHA20 + 因子1 + 因子2(SOTA)] + [新因子3] → 23个因子 → ...
```

只有当 `decision=True`（Summarizer 判定优于之前 SOTA）时，新因子才会进入 SOTA 库，后续轮次的组合因子集会包含它。

### 6.2 IC 去重机制

[deduplicate_new_factors()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L47-L62) 防止生成与已有因子高度相关的"冗余因子"：

1. 按日期分组计算每个新因子与每个SOTA因子的 Pearson 相关系数
2. 取所有日期的平均 IC
3. 如果某新因子与**任何** SOTA 因子的最大 IC ≥ 0.99，剔除该因子
4. 使用 pandarallel 并行加速

### 6.3 渐进式复杂度策略

[factor_proposal.py#L38-L41](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L38-L41) 控制假设生成的探索方向：

| 轮次 | RAG 提示 | 探索重点 |
|------|---------|---------|
| 1-15 | "Try the easiest and fastest factors to experiment with from various perspectives first." | 简单量价因子（动量、波动率、换手率、相关性等），代码简单，CoSTEER 成功率高 |
| 16+ | "Now, you need to try factors that can achieve high IC (e.g., machine learning-based factors)." | ML-based 因子（GBDT因子、MLP非线性组合、PCA因子等），复杂度提升，目标高IC |

### 6.4 因子验证模型选择

通过 `QLIB_FACTOR_MODEL_SELECTOR` 环境变量选择用于因子评估的监督模型：

| 模型 | 特点 | 速度 |
|------|------|------|
| `lgbm`（默认） | LightGBM，性能均衡 | 中 |
| `linear` | 闭式OLS线性回归 | 最快 |
| `xgboost` | XGBoost梯度提升树 | 中 |
| `catboost` | CatBoost，自动GPU/CPU | 中 |

### 6.5 错误跳过机制

`FactorRDLoop` 定义了 `skip_loop_error = (FactorEmptyError, CoderError)`：
- 因子代码执行失败（如运行时错误、输出为空、IC去重后全部剔除）→ 抛出 `FactorEmptyError`
- CoSTEER 编码阶段完全失败（所有进化轮次都无法生成可接受实现）→ 抛出 `CoderError`
- 注意：在 [exception.py:62](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/exception.py#L62) 中 `FactorEmptyError = CoderError`（别名），两者实际是同一个异常类
- 这些错误不会终止整个循环，而是在 feedback 步骤生成否定反馈（decision=False），继续下一轮

---

## 7. 基础特征体系

### 默认基础因子：ALPHA20

系统默认使用 [ALPHA20](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/qlib.py#L4-L25) 作为基础特征集，包含 20 个经典量价因子：

| 类别 | 因子示例 | Qlib 表达式 |
|------|---------|------------|
| 残差类 | RESI5, RESI10 | `Resi($close, N)/$close` |
| R²类 | RSQR5, RSQR10, RSQR20, RSQR60 | `Rsquare($close, N)` |
| 相关性 | CORR5, CORR10, CORR20, CORR60 | `Corr($close, Log($volume+1), N)` |
| 收益率相关 | CORD5, CORD10, CORD60 | `Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), N)` |
| 波动率 | STD5, VSTD5, WVMA5, WVMA60 | `Std($close,5)/$close`, `Std($volume,5)/($volume+1e-12)`, `Std(Abs(return)*$volume,N)/Mean(...)` |
| 动量 | ROC60 | `Ref($close, 60)/$close` |
| K线 | KLEN, KLOW | `($high-$low)/$open`, `(Less($open,$close)-$low)/$open` |

### 自定义基础因子

通过 `--base_features_path` 指定目录，目录中需包含：
- `base_factors.json`：因子名称到 Qlib 表达式的映射
- `*.py`：自定义因子实现代码（可选，用于复杂因子）

---

## 8. 输出产物

| 产物 | 位置 | 说明 |
|------|------|------|
| Session 快照 | `log/<时间戳>/__session__/N/*.pkl` | 每步pickle序列化，支持断点恢复 |
| 工作区代码 | `git_ignore_folder/RD-Agent_workspace/<UUID>/` | 每个实验的factor.py和配置 |
| 因子数据 | `combined_factors_df.parquet` | SOTA+新因子的DataFrame |
| 回测结果 | mlflow（工作区内） | IC、ARR、MDD等指标 |
| Token消耗 | `log/<时间戳>/token_cost/*.pkl` | 各步骤LLM调用记录 |
| 日志对象 | `log/<时间戳>/<tag>/*.pkl` | hypothesis/feedback等结构化日志 |

---

## 9. 关键代码索引

| 模块 | 文件路径 |
|------|----------|
| 入口/主循环 | [rdagent/app/qlib_rd_loop/factor.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/factor.py) |
| 配置类 | [rdagent/app/qlib_rd_loop/conf.py#L71-L127](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py#L71-L127) |
| 假设生成 | [rdagent/scenarios/qlib/proposal/factor_proposal.py#L15-L58](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L15-L58) |
| 假设转实验 | [rdagent/scenarios/qlib/proposal/factor_proposal.py#L61-L132](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/factor_proposal.py#L61-L132) |
| 场景定义 | [rdagent/scenarios/qlib/experiment/factor_experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/factor_experiment.py) |
| 因子CoSTEER | [rdagent/components/coder/factor_coder/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/factor_coder/__init__.py) |
| 因子Runner | [rdagent/scenarios/qlib/developer/factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py) |
| 因子反馈 | [rdagent/scenarios/qlib/developer/feedback.py#L54-L118](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L54-L118) |
| 因子数据处理 | [rdagent/scenarios/qlib/developer/utils.py#L131-L177](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/utils.py#L131-L177) |
| ALPHA20定义 | [rdagent/utils/qlib.py#L4-L25](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/qlib.py#L4-L25) |
