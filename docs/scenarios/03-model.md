# 模型调优场景（Model）

> 在固定因子特征集（默认 ALPHA20）上自动优化 PyTorch 预测模型。LLM 生成模型架构（MLP/GRU/LSTM/Transformer等）、超参数和训练配置，通过 CoSTEER 编写可运行的 model.py，在 Qlib 中训练和回测。

---

## 1. 场景概述

模型调优场景的进化目标是**预测模型本身**而非因子。系统在固定特征集上，让 LLM 自主探索神经网络架构设计（层数、隐藏维度、激活函数、正则化、注意力机制等），通过训练-回测-反馈循环迭代改进模型表现。

**核心特点**：
- 🧠 **PyTorch 模型进化**：LLM 生成完整的 `nn.Module` 子类代码
- 📊 **Tabular / TimeSeries 双模式**：支持前馈网络（MLP）和时序网络（GRU/LSTM/Transformer）
- 🔧 **超参数协同优化**：同时优化模型架构超参（hidden_size, dropout等）和训练超参（lr, batch_size等）
- 🏗️ **基于 SOTA 迭代**：参考历史最优模型架构，支持渐进式改进和架构创新
- 📐 **单元测试前置**：CoSTEER 编码阶段用固定输入做前向传播测试（形状检查）

---

## 2. 启动方式

```bash
# 默认启动（ALPHA20特征集）
dotenv run -- python rdagent/app/qlib_rd_loop/model.py

# 指定轮数和描述
dotenv run -- python rdagent/app/qlib_rd_loop/model.py --loop_n 20 --description "探索LSTM时序模型"

# 断点恢复
dotenv run -- python rdagent/app/qlib_rd_loop/model.py $LOG_PATH/__session__/1/0_propose

# 自定义基础因子
dotenv run -- python rdagent/app/qlib_rd_loop/model.py --base_features_path ./my_factors/
```

### CLI 参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `path` | str | None | 断点恢复路径 |
| `loop_n` | int | None | 最大循环轮数 |
| `step_n` | int | None | 最大步骤数 |
| `all_duration` | str | None | 最大运行时长 |
| `description` | str | None | 用户目标描述 |
| `base_features_path` | str | None | 自定义基础因子目录 |

---

## 3. 配置

环境变量前缀：**`QLIB_MODEL_`**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `QLIB_MODEL_SCEN` | QlibModelScenario | 场景类 |
| `QLIB_MODEL_HYPOTHESIS_GEN` | QlibModelHypothesisGen | 假设生成类 |
| `QLIB_MODEL_HYPOTHESIS2EXPERIMENT` | QlibModelHypothesis2Experiment | 假设转实验类 |
| `QLIB_MODEL_CODER` | QlibModelCoSTEER | 编码进化类 |
| `QLIB_MODEL_RUNNER` | QlibModelRunner | 训练执行类 |
| `QLIB_MODEL_SUMMARIZER` | QlibModelExperiment2Feedback | 反馈生成类 |
| `QLIB_MODEL_EVOLVING_N` | 10 | CoSTEER 内部迭代轮数 |
| `QLIB_MODEL_TRAIN_START/END` | 2008-01-01 / 2014-12-31 | 训练集 |
| `QLIB_MODEL_VALID_START/END` | 2015-01-01 / 2016-12-31 | 验证集 |
| `QLIB_MODEL_TEST_START/END` | 2017-01-01 / auto | 测试集 |

CoSTEER 循环配置使用基类前缀 **`CoSTEER_`**（`ModelCoSTEER` 传入 `CoSTEER_SETTINGS`，见 [model_coder/__init__.py:19](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/__init__.py#L19)）：
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CoSTEER_MAX_LOOP` | 10 | CoSTEER 内部进化轮数（同 `QLIB_MODEL_EVOLVING_N`） |

编码环境配置使用独立前缀 **`MODEL_CoSTEER_`**（`ModelCoSTEERSettings`，仅控制 `get_model_env()`）：
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MODEL_CoSTEER_ENV_TYPE` | conda | 编码环境：conda 或 docker |

---

## 4. 组件实例

```
ModelRDLoop
├── skip_loop_error: (ModelEmptyError,)
├── scen:           QlibModelScenario
├── hypothesis_gen: QlibModelHypothesisGen   (模型/temperature由 CHAT_MODEL_MAP 配置路由)
│   └── targets: "model tuning"
│   └── 额外提供SOTA_hypothesis_and_feedback
│   └── RAG: 硬约束（时序数据用GRU/LSTM, 控制模型大小, 可只调超参）
├── h2e:            QlibModelHypothesis2Experiment
├── coder:          QlibModelCoSTEER         (模型/temperature由 CHAT_MODEL_MAP 配置路由, evolving_n=10)
│   ├── evolving_strategy: ModelMultiProcessEvolvingStrategy
│   ├── evaluator: ModelCoSTEEREvaluator
│   │   ├── shape_evaluator: 前向传播→输出shape=(batch,1)         │  │
│   │   ├── value_evaluator: 与GT对比(如有GT)
│   │   ├── code_review: LLM代码评审
│   │   └── final_decision: LLM综合判定
│   └── evolving_version: 2 (图知识库V2)
├── runner:         QlibModelRunner          (无LLM调用)
│   ├── SOTA因子合并 → combined_factors_df.parquet
│   ├── model_type路由 (Tabular/TimeSeries)
│   └── GeneralPTNN训练+回测
└── summarizer:     QlibModelExperiment2Feedback (模型/temperature由 CHAT_MODEL_MAP 配置路由)
```

---

## 5. 模型类型详解

模型类型由 `ModelTask.model_type` 字段控制，Runner 根据类型选择不同的数据集类和参数：

| 维度 | Tabular（表格模型） | TimeSeries（时序模型） |
|------|-------------------|---------------------|
| **Qlib Dataset** | `DatasetH` | `TSDatasetH` |
| **数据维度** | 2D: `(batch, num_features)` | 3D: `(batch, 20, num_features)` |
| **时间窗口** | 无 | `step_len=20`, `num_timesteps=20`（回看20天） |
| **适用架构** | MLP 等前馈网络 | GRU, LSTM, Transformer, TCN |
| **pt_model_kwargs** | `{"num_features": N}` | `{"num_features": N, "num_timesteps": 20}` |
| **典型模型** | 多层全连接+BatchNorm+Dropout | GRU/LSTM + Attention + 全连接输出层 |

**HypothesisGen 中的 RAG 约束**（[model_proposal.py#L33-L36](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L33-L36)）：
1. 金融时序数据适合 GRU/LSTM，**不要生成 GNN**（图神经网络不适用于因子选股）
2. 训练集约 100 万样本/验证集约 25 万样本，**控制模型大小**避免过拟合
3. 可以只调超参数不换架构（超参调整也是有效策略）

---

## 6. 完整工作流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    ModelRDLoop 主循环                            │
│                                                                 │
│  [初始化] plan = {features: ALPHA20, feature_codes: {}}         │
│                                                                 │
│  ┌─── Loop N ────────────────────────────────────────────────┐  │
│  │                                                           │  │
│  │  ① direct_exp_gen()                                       │  │
│  │  ├─ _propose(): QlibModelHypothesisGen.gen(trace)         │  │
│  │  │   ├─ prepare_context() 组装6个上下文键：                 │  │
│  │  │   │   ├─ hypothesis_and_feedback: 完整历史链           │  │
│  │  │   │   ├─ last_hypothesis_and_feedback: 最近一轮        │  │
│  │  │   │   │   (含training_log/stdout帮助分析训练问题)       │  │
│  │  │   │   ├─ SOTA_hypothesis_and_feedback: SOTA轮详情      │  │
│  │  │   │   ├─ RAG: 模型类型/规模/超参硬约束                  │  │
│  │  │   │   ├─ hypothesis_output_format: JSON格式            │  │
│  │  │   │   └─ hypothesis_specification: 模型生成8条规范     │  │
│  │  │   ├─ LLM生成Hypothesis(hypothesis, reason, concise_*)  │  │
│  │  │   └─ 用户交互修改(可选)                                  │  │
│  │  │                                                        │  │
│  │  └─ _exp_gen(): QlibModelHypothesis2Experiment.convert()  │  │
│  │      ├─ prepare_context() 传入SOTA信息和特征列表            │  │
│  │      ├─ LLM解析JSON响应为ModelTask，包含：                  │  │
│  │      │   ├─ model_name / description / formulation        │  │
│  │      │   ├─ architecture: 架构描述                         │  │
│  │      │   ├─ variables: 输入输出变量说明                    │  │
│  │      │   ├─ hyperparameters: 模型架构超参                   │  │
│  │      │   ├─ training_hyperparameters: 训练超参             │  │
│  │      │   └─ model_type: "Tabular" 或 "TimeSeries"         │  │
│  │      ├─ 创建QlibModelExperiment，设置based_experiments     │  │
│  │      └─ 注入base_features(ALPHA20)                         │  │
│  │                                                           │  │
│  │  ② coding() — QlibModelCoSTEER.develop(exp)              │  │
│  │  ├─ 将Experiment转为EvolvingItem                           │  │
│  │  ├─ 多轮进化循环(最多evolving_n=10轮)：                     │  │
│  │  │   ├─ RAG检索(图知识库V2三步检索)                         │  │
│  │  │   ├─ ModelMultiProcessEvolvingStrategy:                │  │
│  │  │   │   LLM生成/修改model.py(完整nn.Module代码)           │  │
│  │  │   ├─ ModelFBWorkspace.inject_code() 注入代码           │  │
│  │  │   ├─ ModelCoSTEEREvaluator.evaluate() 单元测试:        │  │
│  │  │   │   ├─ 固定输入: batch=8, features=30, timesteps=40  │  │
│  │  │   │   │           input_value=0.4, param_init=0.6      │  │
│  │  │   │   ├─ Conda/Docker中实例化模型+前向传播              │  │
│  │  │   │   ├─ shape_evaluator: 输出shape==(8,1)            │  │
│  │  │   │   ├─ value_evaluator: 数值稳定性检查(有GT时)       │  │
│  │  │   │   ├─ ModelCodeEvaluator: LLM代码评审               │  │
│  │  │   │   └─ ModelFinalEvaluator: LLM综合判定可接受?       │  │
│  │  │   ├─ Fallback: 保留最后一个可接受版本                   │  │
│  │  │   └─ 知识更新：成功实现写入图知识库                     │  │
│  │  └─ 全部失败→抛CoderError; 否则返回best effort的exp       │  │
│  │                                                           │  │
│  │  ③ running() — QlibModelRunner.develop(exp)              │  │
│  │  ├─ 递归处理based_experiments[-1]（确保SOTA有结果）        │  │
│  │  ├─ 处理SOTA因子：                                         │  │
│  │  │   ├─ 从based_experiments过滤QlibFactorExperiment       │  │
│  │  │   ├─ 多个时process_factor_data()合并→parquet           │  │
│  │  │   └─ 无SOTA因子时使用ALPHA20基础特征（baseline路径）   │  │
│  │  ├─ 将model.py注入experiment_workspace                    │  │
│  │  ├─ 构建环境变量：                                         │  │
│  │  │   ├─ 日期: train/valid/test start/end                  │  │
│  │  │   ├─ 特征: feature_expressions/feature_names           │  │
│  │  │   └─ 训练超参: n_epochs(100)/lr(2e-4)/early_stop(10)/  │  │
│  │  │          batch_size(256)/weight_decay(1e-4)            │  │
│  │  ├─ 根据model_type选择配置路径：                           │  │
│  │  │   ├─ Tabular + baseline → DatasetH + baseline yaml    │  │
│  │  │   │   num_features=20(硬编码ALPHA20)                    │  │
│  │  │   ├─ Tabular + SOTA → DatasetH + sota yaml            │  │
│  │  │   │   num_features=动态计算(ALPHA20+新因子)             │  │
│  │  │   ├─ TimeSeries + baseline → TSDatasetH + baseline    │  │
│  │  │   │   step_len=20, num_timesteps=20                    │  │
│  │  │   └─ TimeSeries + SOTA → TSDatasetH + sota            │  │
│  │  ├─ Docker/Conda内执行qrun:                               │  │
│  │  │   ├─ 初始化qlib(CSI300数据)                            │  │
│  │  │   ├─ 构建Dataset(DataHandlerLP + 可选StaticDataLoader) │  │
│  │  │   ├─ 数据预处理: RobustZScoreNorm→Fillna→DropnaLabel  │  │
│  │  │   │             →CSZScoreNorm(标签横截面标准化)        │  │
│  │  │   ├─ GeneralPTNN训练(n_epochs, MSE, early stopping)   │  │
│  │  │   ├─ 测试集预测→SignalRecord                           │  │
│  │  │   ├─ SigAnaRecord: IC/ICIR/RankIC等指标                │  │
│  │  │   └─ PortAnaRecord: TopkDropout→ARR/MDD/Sharpe        │  │
│  │  ├─ 从mlflow读取结果→exp.result(DataFrame)               │  │
│  │  └─ exp为空→ModelEmptyError→跳过本轮                       │  │
│  │                                                           │  │
│  │  ④ feedback()                                             │  │
│  │  ├─ 异常→decision=False反馈                                │  │
│  │  └─ QlibModelExperiment2Feedback.generate_feedback:      │  │
│  │      ├─ 从trace获取SOTA模型的假设/代码/指标                │  │
│  │      ├─ LLM对比当前模型vs SOTA: IC/ARR/MDD                │  │
│  │      ├─ 返回Observations/Eval/NewHypo/Reason/Decision    │  │
│  │      └─ Decision=True → 替换SOTA模型                      │  │
│  │                                                           │  │
│  │  ⑤ record()                                               │  │
│  │  └─ trace.sync_dag_parent_and_hist((exp, feedback))       │  │
│  │                                                           │  │
│  └─── 下一轮 ──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 核心机制详解

### 7.1 GeneralPTNN 模型包装器

Qlib 使用 [GeneralPTNN](https://github.com/microsoft/qlib) 作为通用 PyTorch 模型包装器，通过 `pt_model_uri` 动态加载 LLM 生成的模型类：

{% raw %}
```yaml
# conf_baseline_factors_model.yaml 核心配置
model:
  class: GeneralPTNN
  module_path: qlib.contrib.model.pytorch_general_nn
  kwargs:
    pt_model_uri: "model.model_cls"    # 指向 model.py 中的 model_cls 类
    pt_model_kwargs:
      num_features: {{ num_features }}
      # num_timesteps: 20  # TimeSeries模式
    n_epochs: {{ n_epochs }}
    lr: {{ lr }}
    early_stop: {{ early_stop }}
    batch_size: {{ batch_size }}
    weight_decay: {{ weight_decay }}
```
{% endraw %}

LLM 只需在 `model.py` 中定义一个名为 `model_cls` 的 `nn.Module` 子类，Qlib 自动完成数据加载、训练循环、早停、预测等流程。

### 7.2 CoSTEER 编码阶段的单元测试

与因子场景不同，模型场景的 CoSTEER 在编码阶段会**实例化模型并执行前向传播**（而非执行完整训练）：

1. **固定测试输入**：`batch_size=8, num_features=30, num_timesteps=40, input=0.4, param_init=0.6`
2. **形状检查**（最关键）：输出必须是 `(batch_size, 1)` 的 Tensor——预测每只股票的未来收益
3. **数值检查**：输出不应全为 NaN/Inf，数值范围合理
4. **代码评审**：LLM 评审代码结构、潜在 bug、PyTorch 最佳实践
5. **最终判定**：LLM 综合判断代码是否可接受

这大大降低了训练阶段因形状不匹配等低级错误浪费时间的概率。

### 7.3 模型超参数体系

模型超参数分为两层：

**模型架构超参数**（由 LLM 在 model.py 中实现）：
- 隐藏层维度、层数
- 激活函数选择（ReLU/GELU/SiLU等）
- Dropout 率、BatchNorm/LayerNorm
- 注意力头数（Transformer）
- 隐藏层大小（GRU/LSTM hidden_size）
- 这些参数直接写在 model.py 的 `__init__` 中

**训练超参数**（Runner 通过环境变量→YAML模板传递）：
| 参数 | Runner 默认值 | 来源 |
|------|-------------|------|
| `n_epochs` | 100 | ModelTask.training_hyperparameters |
| `lr` | 2e-4 | ModelTask.training_hyperparameters |
| `early_stop` | 10 | ModelTask.training_hyperparameters |
| `batch_size` | 256 | ModelTask.training_hyperparameters |
| `weight_decay` | 1e-4 | ModelTask.training_hyperparameters |

### 7.4 特征工程说明

模型场景使用基础特征集（默认 ALPHA20），但如果 `based_experiments` 中包含之前因子实验产生的 SOTA 因子（Quant 场景常见），Runner 会：

1. 通过 `process_factor_data()` 执行所有 SOTA 因子代码，生成因子值 DataFrame
2. 保存为 `combined_factors_df.parquet`
3. 通过 `StaticDataLoader` 加载，与 ALPHA20 的基础特征合并
4. 使用 `conf_sota_factors_model.yaml` 配置模板（而非 baseline 模板）

纯模型场景中，H2E 的 `convert()` 设置 `based_experiments = [t[0] for t in trace.hist if t[1] and isinstance(t[0], ModelExperiment)]`（见 [model_proposal.py:158](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L158)）：首轮为空列表（无空基线实验），后续轮次包含上一轮起所有 feedback 非 None 的历史模型实验，因此因子数据为空，走 baseline 路径。

### 7.5 数据预处理管道

所有模式统一使用以下预处理：

```
原始Alpha158/因子数据
    │
    ├─ RobustZScoreNorm(features, clip_outlier=true)  # 特征标准化+截断异常值
    ├─ Fillna(features)                               # 填充缺失值
    ├─ DropnaLabel()                                  # 丢弃标签缺失样本
    └─ CSZScoreNorm(labels)                           # 标签横截面标准化（去市场因子）
```

### 7.6 错误跳过

`ModelRDLoop.skip_loop_error = (ModelEmptyError,)`：
- model.py 前向传播失败、训练不收敛、回测异常等导致 `exp is None` → `ModelEmptyError`
- CoSTEER 所有轮次失败 → `CoderError`，但 **`CoderError` 不在 `skip_loop_error` 中**（与因子场景不同），会终止循环而非跳过

---

## 8. 输出产物

| 产物 | 位置 | 说明 |
|------|------|------|
| Session 快照 | `log/<时间戳>/__session__/N/*.pkl` | 断点恢复 |
| 模型代码 | `git_ignore_folder/RD-Agent_workspace/<UUID>/model.py` | LLM 生成的 PyTorch 模型 |
| 训练配置 | 工作区内渲染后的 YAML | Qlib 训练配置 |
| SOTA因子数据 | `combined_factors_df.parquet` | 合并后的因子数据（如有SOTA因子） |
| 训练日志 | mlflow（工作区内） | loss曲线、指标记录 |
| 回测结果 | mlflow | IC/ARR/MDD/Sharpe 等 |

---

## 9. 关键代码索引

| 模块 | 文件路径 |
|------|----------|
| 入口/主循环 | [rdagent/app/qlib_rd_loop/model.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/model.py) |
| 配置类 | [rdagent/app/qlib_rd_loop/conf.py#L22-L68](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py#L22-L68) |
| 假设生成 | [rdagent/scenarios/qlib/proposal/model_proposal.py#L14-L70](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L14-L70) |
| 假设转实验 | [rdagent/scenarios/qlib/proposal/model_proposal.py#L73-L159](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/model_proposal.py#L73-L159) |
| 场景定义 | [rdagent/scenarios/qlib/experiment/model_experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/model_experiment.py) |
| 模型CoSTEER | [rdagent/components/coder/model_coder/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/__init__.py) |
| 模型进化策略 | [rdagent/components/coder/model_coder/evolving_strategy.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/evolving_strategy.py) |
| 模型评估器 | [rdagent/components/coder/model_coder/evaluators.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/evaluators.py) |
| ModelTask定义 | [rdagent/components/coder/model_coder/model.py#L15-L66](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/model.py#L15-L66) |
| 模型Runner | [rdagent/scenarios/qlib/developer/model_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py) |
| 模型反馈 | [rdagent/scenarios/qlib/developer/feedback.py#L121-L186](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/feedback.py#L121-L186) |
| 模型CoSTEER配置 | [rdagent/components/coder/model_coder/conf.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/coder/model_coder/conf.py) |
| YAML模板(baseline) | model_template/conf_baseline_factors_model.yaml |
| YAML模板(SOTA) | model_template/conf_sota_factors_model.yaml |
