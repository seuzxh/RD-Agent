# 方案执行智能体（Runner）

> **定位**：multialpha R&D 循环的"实验员"与"回测引擎"。接收 CoSTEER 编码阶段输出的可运行代码（因子计算代码/模型代码），将代码注入隔离的 Qlib 执行环境，组合基础因子与新生成因子，运行 Qlib 回测，产出量化绩效指标（IC、收益率、回撤等），并通过基于任务信息哈希的缓存机制避免重复执行。Runner 不涉及 LLM 推理，是纯工程化的执行组件。

---

## 目录

1. [论文来源与设计理念](#1-论文来源与设计理念)
2. [技术架构](#2-技术架构)
3. [类继承体系](#3-类继承体系)
4. [缓存机制](#4-缓存机制)
5. [QlibFactorRunner（因子执行器）](#5-qlibfactorrunner因子执行器)
6. [QlibModelRunner（模型执行器）](#6-qlibmodelrunner模型执行器)
7. [QlibFBWorkspace（Qlib 工作空间）](#7-qlibfbworkspaceqlib-工作空间)
8. [因子数据处理流水线](#8-因子数据处理流水线)
9. [执行环境（Docker/Conda）](#9-执行环境dockerconda)
10. [配置项](#10-配置项)
11. [输入输出示例](#11-输入输出示例)
12. [流程图](#12-流程图)

---

## 1. 论文来源与设计理念

Runner 的设计来源于以下学术工作：

| 论文/框架 | arXiv/会议 | 核心贡献 |
|-----------|-----------|----------|
| **R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science** | [arXiv:2505.14738](https://arxiv.org/abs/2505.14738) | 整体技术报告，将 Runner 定位为 R&D 循环中的 Running 阶段，负责执行实验并产生反馈数据 |
| **R&D-Agent-Quant** | [arXiv:2505.15155](https://arxiv.org/abs/2505.15155) · NeurIPS 2025 | 量化金融场景中因子回测与模型回测的具体实现，包括因子组合、IC 去重、SOTA 因子继承等机制 |
| **Towards Data-Centric Automatic R&D** | [arXiv:2404.11276](https://arxiv.org/abs/2404.11276) | 建立以数据为中心的自动研发范式，Runner 承担"数据驱动验证"的核心职责 |

**设计理念**：

- **代码可执行即验证标准**：假设是否成立、代码是否正确，最终都必须通过真实的回测执行来检验。Runner 是连接"代码生成"与"绩效反馈"的桥梁，没有 Runner 的执行结果，后续反馈环节无从谈起。
- **缓存即效率**：量化回测（特别是模型训练）耗时较长，而 R&D 循环中同一组因子/模型可能被多次执行（如反馈阶段重新评估、基线对比）。Runner 通过任务信息哈希生成缓存键，相同任务直接返回缓存结果，大幅节省计算资源。
- **SOTA 继承机制**：每轮迭代并非从零开始。Runner 自动将历史最优因子（SOTA factor）与本轮新因子组合，或将历史最优模型注入本轮实验，确保每轮实验都站在前一轮的肩膀上。
- **环境隔离**：通过 Docker 容器或 Conda 环境执行 Qlib 回测，避免依赖冲突；工作空间采用文件夹隔离，每个实验拥有独立的代码、数据和结果目录。
- **纯确定性执行**：Runner 不调用 LLM，其行为完全由代码逻辑和配置决定。这保证了相同输入始终产生相同输出，是缓存机制生效的前提。

---

## 2. 技术架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                     RDLoop.running()                                 │
│                     runner.develop(exp)                              │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   CachedRunner.develop(exp)                          │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  @cache_with_pickle(hash_func, assign_cached_result)        │    │
│  │                                                             │    │
│  │  ① 计算缓存键：MD5(所有子任务的 task_information)           │    │
│  │  ② 若缓存存在 → 反序列化并 assign_cached_result → 返回      │    │
│  │  ③ 若缓存不存在 → 执行子类 develop() 逻辑                   │    │
│  │  ④ 执行完成后 → pickle 序列化结果到缓存文件                 │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│              ┌─────────────────┴─────────────────┐                   │
│              ▼                                   ▼                   │
│  ┌─────────────────────┐           ┌─────────────────────┐          │
│  │  QlibFactorRunner   │           │  QlibModelRunner    │          │
│  │  (因子回测)          │           │  (模型回测)          │          │
│  │                     │           │                     │          │
│  │ ① 基线实验递归执行   │           │ ① 基线实验递归执行   │          │
│  │ ② 处理 SOTA 因子    │           │ ② 处理 SOTA 因子    │          │
│  │ ③ 处理新因子        │           │ ③ 注入 model.py     │          │
│  │ ④ IC 去重           │           │ ④ 设置超参数        │          │
│  │ ⑤ 组合因子+去重     │           │ ⑤ 选择数据集类型    │          │
│  │ ⑥ 保存 parquet      │           │ ⑥ 执行 Qlib 回测    │          │
│  │ ⑦ 注入 SOTA 模型    │           │ ⑦ 读取结果          │          │
│  │ ⑧ 执行 Qlib 回测    │           │                     │          │
│  │ ⑨ 读取结果          │           │                     │          │
│  └─────────┬───────────┘           └──────────┬──────────┘          │
│            │                                  │                      │
│            └──────────────┬───────────────────┘                      │
│                           ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              QlibFBWorkspace.execute()                      │    │
│  │                                                             │    │
│  │  ① 选择执行环境（Docker / Conda）                           │    │
│  │  ② prepare()：拉取镜像 / 准备 Conda 环境 / 下载行情数据     │    │
│  │  ③ qrun <config>.yaml：运行 Qlib 回测                       │    │
│  │  ④ python read_exp_res.py：提取 mlflow 中的绩效指标         │    │
│  │  ⑤ 返回 tuple[pd.Series | None, str]                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    返回含 result 和 stdout 的 Experiment
                    （result 为 qlib_res.csv 的指标 Series）
```

**核心组件**：

| 组件 | 定义位置 | 职责 |
|------|----------|------|
| `CachedRunner` | [runner/__init__.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/runner/__init__.py) | 缓存基类，定义缓存键生成与缓存结果赋值逻辑 |
| `QlibFactorRunner` | [factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py) | 因子回测执行器，处理因子组合、IC 去重、Qlib 回测 |
| `QlibModelRunner` | [model_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py) | 模型回测执行器，注入模型代码、设置超参数、Qlib 回测 |
| `QlibFBWorkspace` | [workspace.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/workspace.py) | Qlib 文件工作空间，封装环境选择与回测执行 |
| `process_factor_data` | [utils.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/utils.py#L131-L177) | 多进程执行因子代码，汇总因子 DataFrame |
| `cache_with_pickle` | [core/utils.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/utils.py#L156-L196) | pickle 缓存装饰器，支持文件锁防并发 |

---

## 3. 类继承体系

```
Developer(ABC, Generic[ASpecificExp])       # rdagent/core/developer.py
    │
    │  抽象方法: develop(exp) -> exp
    │    （原地修改 exp，返回值计划移除；docstring 明确要求 inplace edit）
    │
    └── CachedRunner(Developer[ASpecificExp])     # rdagent/components/runner/__init__.py
            │
            │  方法:
            │    get_cache_key(exp) -> str          # MD5(所有 task_information)
            │    assign_cached_result(exp, cached)  # 将缓存结果赋值到当前 exp
            │
            ├── QlibFactorRunner(CachedRunner[QlibFactorExperiment])
            │     # rdagent/scenarios/qlib/developer/factor_runner.py
            │     # 因子组合 + IC 去重 + LGBM/SOTA 模型回测
            │
            └── QlibModelRunner(CachedRunner[QlibModelExperiment])
                  # rdagent/scenarios/qlib/developer/model_runner.py
                  # 模型代码注入 + 超参数传递 + TimeSeries/Tabular 回测
```

**关键继承关系说明**：

- `Developer` 是所有"开发-执行"组件的抽象基类，定义了统一的 `develop(exp)` 接口。CoSTEER 编码器和 Runner 都继承自它，这使得它们可以在 RDLoop 中以相同方式被调用。
- `CachedRunner` 在 `Developer` 基础上增加了 pickle 缓存能力，但本身不实现具体的执行逻辑，而是由子类通过 `@cache_with_pickle` 装饰器装饰 `develop()` 方法来启用缓存。
- `QlibFactorRunner` 和 `QlibModelRunner` 分别对应量化研发循环中的因子执行和模型执行两个场景，各自实现不同的数据处理和回测配置选择逻辑。

---

## 4. 缓存机制

### 4.1 缓存键生成

定义于 [CachedRunner.get_cache_key](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/runner/__init__.py#L7-L14)：

```python
def get_cache_key(self, exp: Experiment) -> str:
    all_tasks = []
    for based_exp in exp.based_experiments:
        all_tasks.extend(based_exp.sub_tasks)
    all_tasks.extend(exp.sub_tasks)
    task_info_list = [task.get_task_information() for task in all_tasks]
    task_info_str = "\n".join(task_info_list)
    return md5_hash(task_info_str)
```

缓存键的生成逻辑：
1. 收集当前实验及其所有基线实验（`based_experiments`）的子任务
2. 对每个子任务调用 `get_task_information()` 获取任务描述文本
3. 将所有任务描述拼接后计算 MD5 哈希

这意味着：缓存键仅基于任务描述文本（`factor_name`/`factor_description`/`factor_formulation`/`variables` 等），**不包含代码内容**。代码变更如果不改变任务描述，不会使缓存失效。仅当任务描述文本发生变化时才会产生不同的缓存键。

### 4.2 QlibFactorRunner 的增强缓存键

`QlibFactorRunner` 重写了缓存键方法（[factor_runner.py#L64-L75](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L64-L75)），将 `model_selector`（模型选择器）纳入哈希：

```python
def _develop_cache_key(self, exp: QlibFactorExperiment) -> str:
    base_key = CachedRunner.get_cache_key(self, exp)
    selector = FactorBasePropSetting().model_selector
    return md5_hash(f"{base_key}\nmodel_selector={selector}")
```

这样，同一组因子使用不同模型（LGBM vs SOTA 模型）回测时不会命中错误的缓存。

### 4.3 cache_with_pickle 装饰器

定义于 [core/utils.py#L156-L196](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/core/utils.py#L156-L196)，工作流程：

1. 检查全局开关 `RD_AGENT_SETTINGS.cache_with_pickle`（默认 `True`）
2. 调用 `hash_func` 生成缓存键，若为 `None` 则跳过缓存
3. 缓存文件路径：`pickle_cache/<module>.<function>/<hash_key>.pkl`
4. 若缓存文件存在：反序列化 → 调用 `post_process_func` 处理 → 返回
5. 若缓存不存在：执行原函数 → pickle 序列化结果 → 写入缓存文件
6. 使用 `.lock` 文件锁防止多进程并发写入

### 4.4 缓存结果赋值

定义于 [CachedRunner.assign_cached_result](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/components/runner/__init__.py#L16-L20)：

```python
def assign_cached_result(self, exp: Experiment, cached_res: Experiment) -> Experiment:
    if exp.based_experiments and exp.based_experiments[-1].result is None:
        exp.based_experiments[-1].result = cached_res.based_experiments[-1].result
    exp.result = cached_res.result
    return exp
```

由于 Runner 采用"原地修改 exp"的模式，缓存命中时需要将缓存中的 `result`（以及基线实验的 result）赋值回当前实验对象，而不是直接返回缓存对象本身（因为当前 exp 可能携带了新的上下文信息）。

---

## 5. QlibFactorRunner（因子执行器）

定义于 [factor_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py)。

### 5.1 核心执行流程

`develop()` 方法的主要步骤：

**① 基线实验递归执行**（[L83-L85](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L83-L85)）

```python
if exp.based_experiments and exp.based_experiments[-1].result is None:
    exp.based_experiments[-1] = self.develop(exp.based_experiments[-1])
```

如果当前实验依赖的基线实验尚未执行，先递归执行基线实验。这保证了 SOTA 因子和模型结果可用。

**② 构建环境变量**（[L87-L103](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L87-L103)）

将训练/验证/测试时间段、基础因子名称与表达式、模型选择器等信息通过环境变量传递给 Qlib 容器/Conda 环境。

**③ 处理 SOTA 因子**（[L105-L113](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L105-L113)）

从 `based_experiments` 中筛选出所有 `QlibFactorExperiment`，仅当筛选出的数量 **大于 1**（即 `len(sota_factor_experiments_list) > 1`）时，才调用 `process_factor_data()` 将历史最优因子汇总为 DataFrame。若只有 0 或 1 个，`SOTA_factor` 保持为 `None`。

**④ 处理新因子并去重**（[L116-L131](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L116-L131)）

调用 `process_factor_data(exp)` 执行本轮新生成的因子代码，获得因子 DataFrame。**仅当 `SOTA_factor` 非空（`is not None` 且非 empty）时**，才通过 `deduplicate_new_factors(SOTA_factor, new_factors)` 计算新因子与 SOTA 因子的 IC（信息系数），若 IC ≥ 0.99 则认为高度相似并移除，避免冗余因子；若 `SOTA_factor` 为空则跳过去重，直接使用新因子。

**⑤ 组合因子并保存**（[L133-L148](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L133-L148)）

```python
combined_factors = pd.concat([SOTA_factor, new_factors], axis=1).dropna()
combined_factors = combined_factors.sort_index()
new_columns = pd.MultiIndex.from_product([["feature"], combined_factors.columns])
combined_factors.columns = new_columns
combined_factors.to_parquet(target_path, engine="pyarrow")
```

将 SOTA 因子与新因子按列拼接，去重列名，添加 `feature` 列层级，保存为 parquet 文件（使用 parquet 而非 pickle 是为了兼容 Docker 容器内的 numpy 版本差异）。

**⑥ 选择回测配置并执行**（[L150-L190](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L150-L190)）

根据是否存在 SOTA 模型，选择不同的 Qlib 配置：

| 条件 | 配置文件 | 环境变量附加设置 | 说明 |
|------|----------|------------------|------|
| 存在 SOTA 模型（TimeSeries） | `conf_combined_factors_sota_model.yaml` | 注入 SOTA `model.py`；传递 SOTA 训练超参（n_epochs/lr/early_stop/batch_size/weight_decay）；`dataset_cls="TSDatasetH"`、`num_features`、`step_len=20`、`num_timesteps=20` | 组合因子 + SOTA TimeSeries 模型 |
| 存在 SOTA 模型（Tabular） | `conf_combined_factors_sota_model.yaml` | 注入 SOTA `model.py`；传递 SOTA 训练超参；`dataset_cls="DatasetH"`、`num_features` | 组合因子 + SOTA Tabular 模型 |
| 无 SOTA 模型 | `conf_combined_factors.yaml` | 仅基础因子+组合因子环境变量（`model_selector` 默认为 `lgbm`） | 组合因子 + LGBM（默认） |
| 无基线实验，有基础因子代码 | `conf_combined_factors.yaml` | 基础因子环境变量 | 仅基础因子 |
| 无基线实验，无基础因子代码 | `conf_baseline.yaml` | 基础因子环境变量 | 纯基线（ALPHA20） |

**⑦ 结果校验**（[L213-L219](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L213-L219)）

若 `result is None`，抛出 `FactorEmptyError`，该异常会被 RDLoop 捕获并跳过当前循环。

### 5.2 IC 去重算法

定义于 [deduplicate_new_factors](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/factor_runner.py#L47-L62)：

1. 将 SOTA 因子和新因子按列拼接
2. 按 `datetime` 分组，并行计算每个 SOTA 因子列与每个新因子列的 Pearson 相关系数（IC）
3. 对每个新因子，取其与所有 SOTA 因子的 IC 最大值
4. 保留 IC 最大值 < 0.99 的新因子列

这确保了新因子与已有因子在横截面预测能力上不高度重合。

---

## 6. QlibModelRunner（模型执行器）

定义于 [model_runner.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py)。

### 6.1 核心执行流程

**① 基线实验递归执行**（[L29-L30](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py#L29-L30)）

与 FactorRunner 相同，递归执行未完成的基线实验。

**② 处理 SOTA 因子**（[L32-L55](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py#L32-L55)）

若基线实验中存在 SOTA 因子，将其处理并保存为 parquet 文件，供模型训练使用。

**③ 注入模型代码**（[L57-L60](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py#L57-L60)）

```python
exp.experiment_workspace.inject_files(**{"model.py": exp.sub_workspace_list[0].file_dict["model.py"]})
```

将 CoSTEER 生成的 `model.py` 代码注入到 Qlib 工作空间，替换模板中的默认模型。

**④ 设置训练超参数**（[L76-L86](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py#L76-L86)）

从子任务中提取 `training_hyperparameters`，通过环境变量传递：
- `n_epochs`：训练轮数（默认 100）
- `lr`：学习率（默认 2e-4）
- `early_stop`：早停轮数（默认 10）
- `batch_size`：批次大小（默认 256）
- `weight_decay`：权重衰减（默认 0.0001）

**⑤ 根据模型类型选择配置**（[L89-L112](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py#L89-L112)）

| 模型类型 | 有 SOTA 因子 | 配置文件 | 数据集类 |
|----------|-------------|----------|----------|
| TimeSeries | 是 | `conf_sota_factors_model.yaml` | `TSDatasetH`（step_len=20, num_timesteps=20） |
| TimeSeries | 否 | `conf_baseline_factors_model.yaml` | `TSDatasetH`（step_len=20, num_timesteps=20） |
| Tabular | 是 | `conf_sota_factors_model.yaml` | `DatasetH` |
| Tabular | 否 | `conf_baseline_factors_model.yaml` | `DatasetH` |

**⑥ 结果校验**（[L117-L119](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/model_runner.py#L117-L119)）

若执行失败，抛出 `ModelEmptyError`。

### 6.2 与 FactorRunner 的区别

| 维度 | QlibFactorRunner | QlibModelRunner |
|------|-----------------|-----------------|
| 核心任务 | 组合因子并运行因子回测 | 注入模型代码并运行模型回测 |
| 代码注入 | 注入因子代码（在 process_factor_data 中通过子工作空间执行） | 直接注入 `model.py` 到主工作空间 |
| IC 去重 | 有（新因子与 SOTA 因子 IC ≥ 0.99 则移除） | 无 |
| 超参数 | 使用 FactorBasePropSetting 的 model_selector | 从 task.training_hyperparameters 动态读取 |
| 模型类型 | 固定 LGBM 或继承 SOTA 模型 | 支持 TimeSeries 和 Tabular 两类 |
| 配置选择 | 根据 SOTA 模型存在与否 | 根据模型类型和 SOTA 因子存在与否 |

---

## 7. QlibFBWorkspace（Qlib 工作空间）

定义于 [workspace.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/workspace.py)，继承自 `FBWorkspace`（文件型工作空间）。

### 7.1 模板文件夹

每个 `QlibFBWorkspace` 实例在初始化时从模板文件夹加载配置文件和辅助脚本：

- **因子模板**：`rdagent/scenarios/qlib/experiment/factor_template/`
  - `conf_baseline.yaml`：基线配置（仅 ALPHA20）
  - `conf_combined_factors.yaml`：组合因子 + LGBM
  - `conf_combined_factors_sota_model.yaml`：组合因子 + SOTA 模型
  - `read_exp_res.py`：结果提取脚本
  - `predict_infer.py`：预测推理脚本

- **模型模板**：`rdagent/scenarios/qlib/experiment/model_template/`
  - `conf_baseline_factors_model.yaml`：基线因子 + 新模型
  - `conf_sota_factors_model.yaml`：SOTA 因子 + 新模型
  - `read_exp_res.py`：结果提取脚本

### 7.2 execute 方法

[execute()](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/workspace.py#L18-L66) 方法执行两步操作：

**第一步：运行 Qlib 回测**

```python
execute_qlib_log = qtde.check_output(
    local_path=str(self.workspace_path),
    entry=f"qrun {qlib_config_name}",
    env=run_env,
)
```

通过 `qrun` 命令运行指定的 YAML 配置，Qlib 会自动完成数据加载、模型训练、回测和结果记录到 mlflow。

**第二步：提取结果**

```python
execute_log = qtde.check_output(
    local_path=str(self.workspace_path),
    entry="python read_exp_res.py",
    env=run_env,
)
```

运行 `read_exp_res.py`，该脚本：
1. 通过 mlflow API 找到最新的 recorder
2. 提取所有 metrics 保存为 `qlib_res.csv`
3. 加载组合分析报告（`portfolio_analysis/report_normal_1day.pkl`）保存为 `ret.pkl`
4. 加载 pred/label，计算 5 分组收益保存为 `ret_group.pkl`

**返回值处理**：

- 若 `qlib_res.csv` 存在：用正则提取训练日志中的 epoch 信息，返回 `(pd.Series(指标), 精简日志)`
- 若 `qlib_res.csv` 不存在：返回 `(None, 完整执行日志)`

---

## 8. 因子数据处理流水线

定义于 [utils.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/developer/utils.py)，`process_factor_data()` 是 Runner 执行因子回测前的关键数据准备步骤。

### 8.1 处理流程

```
输入: QlibFactorExperiment 或 List[QlibFactorExperiment]
  │
  ├── 对每个 exp:
  │     ├── 构建基础因子工作空间（base_feature_codes → FactorFBWorkspace）
  │     ├── 构建执行调用列表:
  │     │     ├── 新因子实现: implementation.execute("All")  (通过 CoSTEER 反馈过滤)
  │     │     └── 基础因子: workspace.execute("All")
  │     └── multiprocessing_wrapper 并行执行所有因子代码
  │
  ├── 对每个执行结果 (message, df):
  │     ├── 校验 df 非空且包含 datetime 索引
  │     ├── 规范化索引为 (datetime, instrument) 二级 MultiIndex
  │     ├── 检测分钟级数据（若存在 1 分钟间隔则跳过）
  │     └── 有效 df 加入 factor_dfs 列表
  │
  └── pd.concat(factor_dfs, axis=1)  → 合并因子 DataFrame
      （若索引不对齐导致 concat 失败，抛出 FactorEmptyError）
```

### 8.2 关键设计

- **多进程并行执行**：使用 `multiprocessing_wrapper` 并行运行多个因子代码，并行度由 `RD_AGENT_SETTINGS.multi_proc_n` 控制（默认 1）。
- **索引规范化**：因子数据必须使用 `(datetime, instrument)` 二级索引，`_normalize_factor_index()` 会处理重复级别名和缺失级别的情况。
- **分钟数据过滤**：若因子数据包含 1 分钟间隔，该因子会被跳过（量化回测默认使用日频数据）。
- **CoSTEER 反馈联动**：只有通过 CoSTEER 评估（`feedback` 非空）的因子实现才会被执行，避免运行已知错误的代码。

---

## 9. 执行环境（Docker/Conda）

Runner 支持两种执行环境，由 `MODEL_COSTEER_SETTINGS.env_type` 控制（默认 `"conda"`）。

### 9.1 Docker 环境（QTDockerEnv）

定义于 [env.py#L1232-L1249](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/env.py#L1232-L1249)：

- 使用预构建的 Qlib Docker 镜像
- 自动挂载行情数据目录
- 首次运行时自动下载 A 股日频数据（`cn_data`）
- 通过 `docker run` 将工作空间挂载到容器内执行

### 9.2 Conda 环境（QlibCondaEnv）

定义于 [env.py#L834-L859](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/utils/env.py#L834-L859)：

- Conda 环境名：`rdagent4qlib`（Python 3.10）
- 首次运行时自动创建环境并安装：
  - Qlib（指定 commit `2fb9380b`）
  - catboost、xgboost、tables、torch
- 通过 `conda run -n rdagent4qlib` 在本地执行

### 9.3 环境选择逻辑

```python
if MODEL_COSTEER_SETTINGS.env_type == "docker":
    qtde = QTDockerEnv()
elif MODEL_COSTEER_SETTINGS.env_type == "conda":
    qtde = QlibCondaEnv(conf=QlibCondaConf())
```

环境选择在 CoSTEER 编码器和 Runner 之间共享，确保代码生成时的测试环境与最终回测环境一致。

---

## 10. 配置项

### 10.1 因子执行配置（FactorBasePropSetting）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `train_start` / `train_end` | - | 训练集起止日期 |
| `valid_start` / `valid_end` | - | 验证集起止日期 |
| `test_start` / `test_end` | - | 测试集起止日期 |
| `model_selector` | `"lgbm"` | 模型选择器，影响 YAML 配置模板分支 |
| `runner` | `"...QlibFactorRunner"` | Runner 类路径（`FactorBasePropSetting` 中的字段名为 `runner`；`factor_runner` 是 `QuantBasePropSetting` 中的字段名） |

### 10.2 模型执行配置（ModelBasePropSetting）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `train_start` / `train_end` | - | 训练集起止日期 |
| `valid_start` / `valid_end` | - | 验证集起止日期 |
| `test_start` / `test_end` | - | 测试集起止日期 |
| `model_runner` | `"...QlibModelRunner"` | Runner 类路径 |

### 10.3 全局配置（RD_AGENT_SETTINGS）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `cache_with_pickle` | `True` | 是否启用 pickle 缓存 |
| `pickle_cache_folder_path_str` | `"./pickle_cache/"` | 缓存文件存储目录 |
| `multi_proc_n` | `1` | 因子代码并行执行进程数 |
| `use_file_lock` | `True` | 缓存文件锁，防并发写入冲突 |

### 10.4 环境配置（ModelCoSTEERSettings）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `env_type` | `"conda"` | 执行环境类型：`"conda"` 或 `"docker"` |

---

## 11. 输入输出示例

### 11.1 输入示例（因子实验）

```python
QlibFactorExperiment(
    sub_tasks=[
        FactorTask(
            factor_name="Momentum10",
            factor_description="10-day price momentum",
            factor_formulation="Ref($close, -10) / $close - 1",
        )
    ],
    sub_workspace_list=[FactorFBWorkspace(...)],  # CoSTEER 生成的可运行因子代码
    based_experiments=[prev_best_exp],            # 上一轮最优实验（含 SOTA 因子）
    base_features={"RESI5": "Resi($close, 5)/$close", ...},  # ALPHA20 基础因子
    hypothesis=Hypothesis(
        hypothesis="动量因子在近期市场表现较好",
        action="factor",
    ),
)
```

### 11.2 输出示例（回测结果）

```python
exp.result = pd.Series({
    "IC": 0.045,
    "ICIR": 1.23,
    "Rank IC": 0.052,
    "annualized_return": 0.18,
    "max_drawdown": -0.12,
    "sharpe_ratio": 1.35,
    # ... 更多 Qlib mlflow 记录的指标
})

exp.stdout = "Epoch1: train -0.045, valid -0.038\nbest score: -0.038 @ 15 epoch"
```

`result` 是一个 `pd.Series`，包含 `qlib_res.csv` 中记录的所有绩效指标。该结果会被传递给反馈（Summarizer）智能体进行决策分析。

### 11.3 缓存文件结构

```
pickle_cache/
└── rdagent.scenarios.qlib.developer.factor_runner.QlibFactorRunner.develop/
    ├── a1b2c3d4e5f6....pkl    # 缓存的实验结果
    ├── a1b2c3d4e5f6....lock   # 文件锁
    └── f6e5d4c3b2a1....pkl
```

---

## 12. 流程图

### 12.1 Runner 整体执行流程

```
          ┌─────────────────┐
          │  RDLoop.running │
          │  .develop(exp)  │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │  计算缓存键      │
          │  MD5(task_info) │
          └────────┬────────┘
                   │
           ┌───────┴───────┐
           │ 缓存命中？     │
           └───┬───────┬───┘
           是  │       │ 否
               ▼       ▼
    ┌──────────────┐  ┌──────────────────┐
    │ 反序列化缓存  │  │ 递归执行基线实验  │
    │ 赋值 result  │  │ (based_experiments)│
    └──────┬───────┘  └────────┬─────────┘
           │                   │
           │                   ▼
           │          ┌──────────────────┐
           │          │  判断实验类型     │
           │          └───┬──────────┬───┘
           │         因子  │          │ 模型
           │               ▼          ▼
           │     ┌─────────────┐ ┌─────────────┐
           │     │ 处理SOTA因子│ │ 处理SOTA因子│
           │     │ 处理新因子  │ │ 注入model.py│
           │     │ IC去重      │ │ 设置超参数  │
           │     │ 组合+保存   │ │ 选择数据集  │
           │     └──────┬──────┘ └──────┬──────┘
           │            │               │
           │            ▼               ▼
           │     ┌─────────────────────────────┐
           │     │  QlibFBWorkspace.execute()  │
           │     │  ① qrun <config>.yaml       │
           │     │  ② python read_exp_res.py   │
           │     └──────────────┬──────────────┘
           │                    │
           │                    ▼
           │          ┌──────────────────┐
           │          │ result is None?  │
           │          └───┬──────────┬───┘
           │          是  │          │ 否
           │              ▼          ▼
           │     ┌────────────┐ ┌──────────┐
           │     │ 抛出       │ │ 序列化   │
           │     │ EmptyError │ │ 写入缓存 │
           │     └────────────┘ └────┬─────┘
           │                         │
           └────────────┬────────────┘
                        ▼
               ┌─────────────────┐
               │ 返回含 result   │
               │ 的 Experiment   │
               └─────────────────┘
```

### 12.2 因子组合与去重流程

```
┌──────────────┐     ┌──────────────┐
│  SOTA 因子    │     │  新因子       │
│  (历史最优)   │     │  (本轮生成)   │
│  DataFrame   │     │  DataFrame   │
└──────┬───────┘     └──────┬───────┘
       │                    │
       │                    ▼
       │          ┌──────────────────┐
       │          │ 按 datetime 分组  │
       │          │ 计算 IC 矩阵      │
       │          │ (SOTA × 新因子)  │
       │          └────────┬─────────┘
       │                   │
       │                   ▼
       │          ┌──────────────────┐
       │          │ 每个新因子取      │
       │          │ IC 最大值         │
       │          └────────┬─────────┘
       │                   │
       │          ┌────────┴─────────┐
       │          │ IC_max < 0.99 ?  │
       │          └───┬──────────┬───┘
       │          是  │          │ 否
       │              ▼          ▼
       │     ┌────────────┐ ┌────────────┐
       │     │ 保留新因子  │ │ 移除新因子  │
       │     └─────┬──────┘ └────────────┘
       │           │
       ▼           ▼
┌──────────────────────────┐
│ pd.concat([SOTA, 新因子]) │
│ .dropna()                │
│ 添加 MultiIndex 层级      │
│ 保存为 parquet            │
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│ Qlib 回测（LGBM/SOTA模型）│
└──────────────────────────┘
```

### 12.3 Qlib 回测执行时序

```
Runner                QlibFBWorkspace        Docker/Conda Env        mlflow
  │                        │                       │                    │
  │──execute(config)──────>│                       │                    │
  │                        │──prepare()──────────>│                    │
  │                        │<─环境就绪─────────────│                    │
  │                        │                       │                    │
  │                        │──qrun config.yaml────>│                    │
  │                        │                       │──数据加载/模型训练  │
  │                        │                       │──回测/记录指标─────>│
  │                        │<─执行日志─────────────│                    │
  │                        │                       │                    │
  │                        │──python read_exp_res.py>│                 │
  │                        │                       │──查询最新recorder──>│
  │                        │                       │<─metrics/report────│
  │                        │                       │──保存qlib_res.csv  │
  │                        │                       │──保存ret.pkl       │
  │                        │                       │──保存ret_group.pkl │
  │                        │<─结果日志─────────────│                    │
  │                        │                       │                    │
  │                        │──读取qlib_res.csv─────│                    │
  │                        │──读取ret.pkl──────────│                    │
  │<─(result_Series, log)──│                       │                    │
  │                        │                       │                    │
```
