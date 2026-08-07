# 全流程协同场景（Quant）

> 因子挖掘与模型调优的联合进化场景。系统在一个循环中同时优化 alpha 因子和预测模型，通过 Bandit/LLM/Random 策略自动分配探索资源——每轮动态决定本轮改进因子还是模型，实现端到端的量化策略自动研发。

---

## 1. 场景概述

全流程场景是 multialpha 最复杂也最接近真实量化研究工作流的场景。它不是简单地串联因子挖掘和模型调优，而是在**同一个 Trace 中维护两套并行的 R&D 管线**，让因子进化和模型进化相互促进：

- 新发现的有效因子→自动加入模型训练的特征集，改善模型输入
- 模型表现的瓶颈→指导因子探索方向（是模型容量不够还是特征不足？）
- Bandit 算法根据历史收益自动决策资源分配

**核心特点**：
- 🔀 **双管线架构**：同时持有 factor_* 和 model_* 两套完整组件
- 🎰 **智能 action 选择**：Bandit（Thompson Sampling）/LLM/Random 三种策略决定每轮做 factor 还是 model
- 📊 **跨类型上下文**：做因子时能看到当前最优模型，做模型时能看到当前最优因子
- 🔗 **特征自动传递**：成功因子自动累积为模型特征（`plan["features"]`）
- 🧠 **统一 Trace**：QuantTrace 混合存储两类实验，共享知识图谱
- ⚖️ **8维奖励信号**：IC/ICIR/RankIC/RankICIR/ARR/IR/-MDD/Sharpe 加权计算

---

## 2. 启动方式

```bash
# 默认启动（Bandit策略，ALPHA20基础因子）
dotenv run -- python rdagent/app/qlib_rd_loop/quant.py

# 指定action选择策略
QLIB_QUANT_ACTION_SELECTION=llm dotenv run -- python rdagent/app/qlib_rd_loop/quant.py

# 指定轮数和描述
dotenv run -- python rdagent/app/qlib_rd_loop/quant.py --loop_n 50 --description "因子模型协同进化"

# 断点恢复
dotenv run -- python rdagent/app/qlib_rd_loop/quant.py $LOG_PATH/__session__/2/0_propose

# 自定义基础因子
dotenv run -- python rdagent/app/qlib_rd_loop/quant.py --base_features_path ./my_factors/
```

### CLI 参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `path` | str | None | 断点恢复路径 |
| `loop_n` | int | None | 最大循环轮数 |
| `step_n` | int | None | 最大步骤数 |
| `all_duration` | str | None | 最大运行时长 |
| `action_selection` | str | bandit | Action选择策略（也可通过环境变量设置） |
| `base_features_path` | str | None | 自定义基础因子目录 |
| `description` | str | None | 用户目标描述 |

---

## 3. 配置

环境变量前缀：**`QLIB_QUANT_`**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `QLIB_QUANT_SCEN` | QlibQuantScenario | 场景类（支持action参数） |
| `QLIB_QUANT_QUANT_HYPOTHESIS_GEN` | QlibQuantHypothesisGen | 统一假设生成（含action选择） |
| `QLIB_QUANT_FACTOR_HYPOTHESIS2EXPERIMENT` | QlibFactorHypothesis2Experiment | 因子假设→实验 |
| `QLIB_QUANT_MODEL_HYPOTHESIS2EXPERIMENT` | QlibModelHypothesis2Experiment | 模型假设→实验 |
| `QLIB_QUANT_FACTOR_CODER` | QlibFactorCoSTEER | 因子编码 |
| `QLIB_QUANT_MODEL_CODER` | QlibModelCoSTEER | 模型编码 |
| `QLIB_QUANT_FACTOR_RUNNER` | QlibFactorRunner | 因子回测 |
| `QLIB_QUANT_MODEL_RUNNER` | QlibModelRunner | 模型训练 |
| `QLIB_QUANT_FACTOR_SUMMARIZER` | QlibFactorExperiment2Feedback | 因子反馈 |
| `QLIB_QUANT_MODEL_SUMMARIZER` | QlibModelExperiment2Feedback | 模型反馈 |
| `QLIB_QUANT_ACTION_SELECTION` | bandit | Action选择：bandit/llm/random |
| `QLIB_QUANT_EVOLVING_N` | 10 | CoSTEER 迭代轮数 |

---

## 4. 双管线架构

Quant 场景的核心设计是在同一个 QuantRDLoop 中持有**两套完整的 R&D 组件**：

```
QuantRDLoop
│
├── 统一入口: quant_hypothesis_gen (QlibQuantHypothesisGen)
│   └── 输出: QlibQuantHypothesis(action="factor"|"model", hypothesis, reason)
│
├─── Factor 管线 ───────────────────────────────────────┐
│   ├── factor_hypothesis2experiment                    │
│   ├── factor_coder (QlibFactorCoSTEER)               │
│   ├── factor_runner (QlibFactorRunner)               │
│   └── factor_summarizer (QlibFactorExperiment2Feedback)
│
├─── Model 管线 ────────────────────────────────────────┤
│   ├── model_hypothesis2experiment                     │
│   ├── model_coder (QlibModelCoSTEER)                 │
│   ├── model_runner (QlibModelRunner)                 │
│   └── model_summarizer (QlibModelExperiment2Feedback)
│
├── plan = {"features": ALPHA20, "feature_codes": {}}
│   └── 成功因子自动累积到features，供model训练使用
│
└── trace = QuantTrace(scen)
    └── controller = EnvController(Bandit)
        └── 记录每轮奖励→Thompson Sampling决策下轮action
```

---

## 5. Action 选择机制

每轮迭代开始时，系统需要决定本轮做因子还是模型。三种策略：

### 5.1 Bandit 策略（默认推荐）

使用 **线性 Thompson Sampling 两臂老虎机**（[LinearThompsonTwoArm](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py#L55-L92)），这是数据驱动的自适应策略。

**状态向量（8维指标）**：从实验结果提取以下指标
```python
metrics = [IC, ICIR, Rank_IC, Rank_ICIR, ARR, IR, -MDD, Sharpe]
```

**奖励权重**：
```python
weights = (0.1, 0.1, 0.05, 0.05, 0.25, 0.15, 0.1, 0.2)
#           ↑    ↑     ↑      ↑     ↑     ↑    ↑    ↑
#          IC  ICIR RIC   RICIR  ARR   IR  -MDD Sharpe
```
年化收益(0.25)和Sharpe(0.2)权重最高，引导 Bandit 关注盈利能力。

**决策流程**：
1. 首轮无历史：默认 action = `"factor"`（先做因子）
2. 每轮结束：从实验结果提取 metrics 向量，计算加权奖励
3. `trace.controller.record(reward, action)` 更新对应 arm 的后验分布（贝叶斯线性回归）
4. 下轮开始：`trace.controller.decide(context)` 对两臂分别 Thompson Sampling，选择期望奖励更高的 action

### 5.2 LLM 策略

让 LLM 自己判断应该做什么。单独调用一次 LLM，使用 `action_gen` 提示词：
- 输入：完整历史假设与反馈链
- 输出：`{"action": "factor" | "model"}` JSON
- 适合需要高级语义理解的场景（如"现在因子已经够多了该优化模型了"）

### 5.3 Random 策略

`random.choice(["factor", "model"])`，纯随机选择。用于对照实验和 ablation study。

---

## 6. 完整工作流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    QuantRDLoop 主循环                            │
│                                                                 │
│  [初始化]                                                       │
│  ├─ 创建双套组件(factor_*/model_*)                              │
│  ├─ plan = {features: ALPHA20, feature_codes: {}}              │
│  ├─ trace = QuantTrace(scen, controller=EnvController)         │
│  └─ asyncio.run(quant_loop.run())                              │
│                                                                 │
│  ┌─── Loop N ────────────────────────────────────────────────┐  │
│  │                                                           │  │
│  │  ① direct_exp_gen()                                       │  │
│  │  ├─ 等待并行槽位                                          │  │
│  │  ├─ _propose(): QlibQuantHypothesisGen.gen(trace)         │  │
│  │  │   ├─ prepare_context():                                │  │
│  │  │   │   ├─ [Bandit] trace.controller.decide() → action  │  │
│  │  │   │   │   (首轮默认"factor")                           │  │
│  │  │   │   ├─ [LLM] 单独LLM调用 → action                   │  │
│  │  │   │   ├─ [Random] random.choice → action              │  │
│  │  │   │   │                                                │  │
│  │  │   │   ├─ 根据action过滤trace构建上下文:                 │  │
│  │  │   │   │   action=factor:                               │  │
│  │  │   │   │     所有factor实验 + 最近1个SOTA model实验     │  │
│  │  │   │   │     RAG: hist<6→简单因子; hist≥6→ML因子       │  │
│  │  │   │   │   action=model:                                │  │
│  │  │   │   │     所有model实验 + 最近1个SOTA factor实验     │  │
│  │  │   │   │     RAG: GRU/LSTM/控制模型大小/可只调超参      │  │
│  │  │   │   │                                                │  │
│  │  │   │   ├─ targets = "feature engineering and model     │  │
│  │  │   │   │             building"                         │  │
│  │  │   │   ├─ output_format: 含action字段的JSON格式         │  │
│  │  │   │   └─ specification: 根据action选对应规范           │  │
│  │  │   │                                                    │  │
│  │  │   ├─ LLM生成QlibQuantHypothesis:                       │  │
│  │  │   │   {hypothesis, reason, action, concise_*}          │  │
│  │  │   └─ 用户交互修改(可选)                                  │  │
│  │  │                                                        │  │
│  │  ├─ 根据hypo.action路由H2E:                               │  │
│  │  │   ├─ "factor" → factor_hypothesis2experiment.convert()│  │
│  │  │   └─ "model"  → model_hypothesis2experiment.convert() │  │
│  │  │                                                        │  │
│  │  ├─ 注入plan中的基础特征:                                  │  │
│  │  │   exp.base_features = plan["features"]                │  │
│  │  │   exp.base_feature_codes = plan["feature_codes"]      │  │
│  │  └─ 返回{"propose": hypo, "exp_gen": exp}                │  │
│  │                                                           │  │
│  │  ② coding() — 按action路由                                │  │
│  │  ├─ action="factor" → factor_coder.develop(exp)          │  │
│  │  └─ action="model"  → model_coder.develop(exp)           │  │
│  │      (各自CoSTEER多轮进化，与纯factor/model场景相同)       │  │
│  │                                                           │  │
│  │  ③ running() — 按action路由                               │  │
│  │  ├─ action="factor":                                      │  │
│  │  │   ├─ factor_runner.develop(exp)                       │  │
│  │  │   ├─ SOTA因子合并(based_experiments中的因子)           │  │
│  │  │   ├─ 如有SOTA model → 使用conf_combined_factors_sota  │  │
│  │  │   │   _model.yaml(复用SOTA模型结构+超参)               │  │
│  │  │   └─ 失败→FactorEmptyError→跳过                       │  │
│  │  │                                                        │  │
│  │  └─ action="model":                                       │  │
│  │      ├─ model_runner.develop(exp)                        │  │
│  │      ├─ 合并所有SOTA factor因子→combined_factors parquet │  │
│  │      ├─ 根据model_type选DatasetH/TSDatasetH配置          │  │
│  │      └─ 用plan["features"](累积的因子)作为基础特征       │  │
│  │                                                           │  │
│  │  ④ feedback() — 按action路由                              │  │
│  │  ├─ 异常(FactorEmptyError/ModelEmptyError):               │  │
│  │  │   → 生成decision=False的HypothesisFeedback             │  │
│  │  ├─ action="factor" → factor_summarizer.generate_feedback│  │
│  │  │   QlibFactorExperiment2Feedback（对比SOTA因子）       │  │
│  │  └─ action="model"  → model_summarizer.generate_feedback │  │
│  │      QlibModelExperiment2Feedback（对比SOTA模型）         │  │
│  │                                                           │  │
│  │  ⑤ record()                                               │  │
│  │  ├─ trace.sync_dag_parent_and_hist((exp, feedback), idx) │  │
│  │  └─ [Bandit更新] trace.controller.record(reward, action) │  │
│  │      从exp.result提取8维metrics→加权reward→更新后验       │  │
│  │                                                           │  │
│  └─── 下一轮（Bandit基于更新后的后验选择新action） ──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 跨管线知识传递机制

### 7.1 Factor → Model：成功因子自动成为模型特征

这是最核心的跨管线数据流：

1. **初始状态**：`plan["features"] = ALPHA20`（20个基础因子）
2. **Factor 轮成功**：当 factor feedback.decision=True 时，新因子**不会**自动加入 plan（plan 在循环中不自动更新features），而是通过 `based_experiments` 链传递给后续轮次。
3. **Model 轮使用**：当执行 model 轮时，`QlibModelRunner` 从 `based_experiments` 中提取所有 `QlibFactorExperiment`：
   ```python
   sota_factor_experiments = [e for e in exp.based_experiments if isinstance(e, QlibFactorExperiment)]
   if len(sota_factor_experiments) > 1:
       SOTA_factor = process_factor_data(sota_factor_experiments_list)
   ```
4. **特征合并**：SOTA 因子值保存为 `combined_factors_df.parquet`，通过 `StaticDataLoader` 与 Alpha158DL 的基础特征（ALPHA20表达式）合并
5. **模型训练**：模型使用扩展后的特征集训练，num_features 动态增长

### 7.2 Model → Factor：模型表现指导因子方向

1. **上下文构建**：当 HypothesisGen 决定做 factor 时，会在 trace 上下文中包含最近一个 SOTA model 实验
2. **反馈参考**：因子 Summarizer 在评估因子时，如果存在 SOTA 模型，会使用 SOTA 模型的配置来回测因子（而非默认的 LightGBM）
3. **Bandit 奖励**：无论哪类实验，Bandit 都从结果中提取相同的8维指标（IC/ARR/MDD等）作为奖励信号

### 7.3 渐进式复杂度（因子侧）

Quant 场景中因子探索的渐进式复杂度阈值是 **6轮**（而非纯因子场景的15轮），因为全流程迭代更快：

| 轮次 | RAG 提示 |
|------|---------|
| Factor轮前6轮 | "Try the easiest and fastest factors to experiment with from various perspectives first." |
| Factor轮6轮后 | "Try factors that can achieve high IC (e.g., ML-based factors) and do not implement factors already in the SOTA factor library." |

---

## 8. QlibQuantScenario：动态场景描述

[QlibQuantScenario](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/quant_experiment.py) 的关键方法是 `get_scenario_all_desc(action=...)`：

- `action="factor"` 时：返回因子场景的背景知识、数据接口、输出格式（与纯QlibFactorScenario一致）
- `action="model"` 时：返回模型场景的背景知识、模型接口、输出格式（与纯QlibModelScenario一致）

这使得 HypothesisGen 和 CoSTEER 在统一的循环中能根据 action 获取正确的场景上下文。

---

## 9. QuantTrace 扩展

[QuantTrace](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L16-L20) 在标准 Trace 基础上增加了 Bandit 控制器：

```python
class QuantTrace(Trace):
    controller: EnvController = Field(
        default_factory=lambda: EnvController(
            bandit=LinearThompsonTwoArm(context_dim=8, n_arms=2)
        )
    )
```

- `hist` 混合存储 QlibFactorExperiment 和 QlibModelExperiment
- `controller` 持久化在 pickle 中，断点恢复时 Bandit 后验分布不丢失
- `get_sota_hypothesis_and_experiment()` 反向遍历时不区分类型，返回最后一个 decision=True 的实验（可能是factor也可能是model）

---

## 10. 与单独运行 Factor/Model 的对比

| 维度 | 单独 Factor | 单独 Model | Quant 全流程 |
|------|------------|------------|-------------|
| **Action选择** | 无（固定factor） | 无（固定model） | Bandit/LLM/Random动态选择 |
| **组件实例** | 单套 | 单套 | factor_* + model_* 双套 |
| **Trace内容** | 纯factor实验 | 纯model实验 | 混合存储两类实验 |
| **SOTA引用** | 因子SOTA | 模型SOTA | 跨类型引用（factor看SOTA model，反之亦然） |
| **特征传递** | 因子累积给固定LGBM | 使用固定ALPHA20 | factor成功→model特征增强 |
| **因子复杂度阈值** | 15轮 | N/A | 6轮 |
| **模型特征数** | 固定LGBM | ALPHA20(20) | 动态增长（20+SOTA新因子） |
| **Bandit控制器** | 无 | 无 | LinearThompsonTwoArm(8维) |
| **错误跳过** | FactorEmptyError | ModelEmptyError | 两者都跳过 |
| **资源利用** | 因子探索 | 模型探索 | 自动分配，收益驱动 |

---

## 11. 典型演化轨迹示例

```
轮次  Action   内容                        结果       SOTA状态
────────────────────────────────────────────────────────────
0     factor   简单动量因子MOM_5            IC=0.02    无SOTA（IC太低）
1     factor   换手率因子TURNOVER_20        IC=0.06    ✅ factor SOTA更新
2     factor   波动率因子VOL_20             IC=0.04    ❌ 未超越SOTA
3     model    MLP(3层, hidden=64)          ARR=12%    ✅ model SOTA更新
4     factor   ML-based(GBDT)因子           IC=0.08    ✅ factor SOTA更新
5     model    LSTM(num_timesteps=20)       ARR=15%    ✅ model SOTA更新
6     model    Transformer模型              ARR=13%    ❌ 未超越SOTA
7     factor   资金流因子MFI                IC=0.05    ❌ 未超越SOTA
...
```

Bandit 在早期多分配给 factor（基础因子不足），随着因子库丰富逐渐增加 model 探索比例。

---

## 12. 关键代码索引

| 模块 | 文件路径 |
|------|----------|
| 入口/主循环 | [rdagent/app/qlib_rd_loop/quant.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/quant.py) |
| 配置类 | [rdagent/app/qlib_rd_loop/conf.py#L146-L209](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/app/qlib_rd_loop/conf.py#L146-L209) |
| 假设生成(含action选择) | [rdagent/scenarios/qlib/proposal/quant_proposal.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py) |
| Bandit实现 | [rdagent/scenarios/qlib/proposal/bandit.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/bandit.py) |
| QuantTrace/QuantHypothesis | [rdagent/scenarios/qlib/proposal/quant_proposal.py#L16-L44](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/proposal/quant_proposal.py#L16-L44) |
| 场景定义 | [rdagent/scenarios/qlib/experiment/quant_experiment.py](file:///home/zxh/projects/1.multialphaV/RD-Agent/rdagent/scenarios/qlib/experiment/quant_experiment.py) |
| Factor/Model组件 | 复用纯factor/model场景组件 |
