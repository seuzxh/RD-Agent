# 快速回测(Fast Backtest)— 设计文档

- **日期**:2026-07-28
- **分支**:`perf/webui-optimization`(将切新分支实现)
- **状态**:已通过 brainstorming 确认,待 review

## 1. 背景与目标

### 1.1 现状

现有 `multialpha` 页面已支持"自然语言 → 因子代码 → Qlib 回测 → 反馈迭代"的**完整 R&D loop**(`FactorRDLoop`,含 hypothesis→coding→running→feedback→record 多轮)。该 loop 功能完整但慢:每轮含 LLM 多步 coding(CoSTEER evolving)、feedback 评审、record 持久化,跑一个因子通常需要数分钟到数十分钟。

### 1.2 目标

新建一个**快速回测**页面,绕过 R&D loop,**单因子直跑回测**:

- 用户用**自然语言描述策略**或**勾选 Alpha158 已有因子**(或两者组合)
- LLM **单次生成** factor.py(不修正、不迭代)
- 用 **LinearModel(OLS)** + **csi300** 固定配置直接 `qrun` 回测
- 秒级出结果(指标 + 收益曲线)
- **产出一个轻量但合法的 trace**,让现有 `predict` 流程能自动发现并复用该结果做 T+1 预测

### 1.3 非目标

- 不做多轮迭代、不做 feedback 评审、不做 SOTA 对比(那是 multiα1pha 的职责)
- 不支持自定义市场/时间范围/模型(首版固定)
- 不支持研报 PDF / 图片输入(那是 multiα1pha 的入口)

## 2. 核心设计决策(已确认)

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 定位 | 绕过 R&D loop,直跑单因子 | 与 multiα1pha 差异化,追求最快 |
| NL→代码 | 单次 LLM 生成,不修正 | 最快出图,失败返回原始错误 |
| 结果展示 | 核心指标 + 收益曲线 | 精简,覆盖判断因子好坏的核心维度 |
| 数据范围 | 固定 csi300 + 默认日期段 | 零配置,最快上手 |
| 后端架构 | 同步端点 + SSE 流式进度 | 不 spawn 子进程、不占完整 trace 系统,线性编排最简单 |
| 输入维度 | Alpha158 勾选 + 自然语言(可组合) | 用户既可用已有因子,也可描述新策略 |
| Alpha158 粒度 | 合并为一个聚合 FactorTask | trace 轻,predict 清晰 |
| trace 维度 | 只写 predict 下一次预测所需的最小 pkl 信息 | 不写完整 loop trace |
| 前端入口 | 独立多页 `fastbacktest.html` | 仿 predict.html 模式 |

## 3. 架构与数据流

```
┌──────────────────────────────────────────────────────────────────────┐
│  前端:web/src/fastbacktest/  (新建 Vue 多页入口)                       │
│  fastbacktest.html → main.ts → FastBacktestApp.vue                     │
│                                                                        │
│  [Alpha158 勾选] + [自然语言描述] → 点击「开始快速回测」                   │
│        │ fetch + ReadableStream 消费 SSE(因 EventSource 不支持 POST)    │
│        ▼                                                               │
└──────────────────────────────────────────────────────────────────────┘
                         │
                         ▼  POST /fastbacktest/run  (text/event-stream)
┌──────────────────────────────────────────────────────────────────────┐
│  后端:Flask 新端点 — 同步线性编排(主进程内,不 spawn 子进程)              │
│                                                                        │
│  Step 1  LLM 单次生成 factor.py(仅当有 description)                    │
│          → SSE: {stage:"codegen", status:"ok", factor_name, code}       │
│                                                                        │
│  Step 2  FactorFBWorkspace.execute("Debug")(仅当有 description)        │
│          (跑 factor.py → result.h5,验证因子值可算出)                    │
│          → SSE: {stage:"factor_eval", status:"ok"}                      │
│                                                                        │
│  Step 3  QlibFBWorkspace.execute("conf_combined_factors.yaml", linear) │
│          (合并因子到 parquet → qrun 回测 → mlruns/ + qlib_res.csv)       │
│          → SSE: {stage:"backtest", status:"running"}                    │
│                                                                        │
│  Step 4  解析结果 + 写轻量 trace                                        │
│          a) 组装最小 Experiment + 微型 Trace                             │
│          b) LoopBase.save() → log/Finance Data Building/fast-xxx/       │
│          → SSE: {stage:"done", trace_id, metrics:{...}, equity:[...]}   │
└──────────────────────────────────────────────────────────────────────┘
                         │
                         ▼  产出的 trace 自动满足 predict 条件:
┌──────────────────────────────────────────────────────────────────────┐
│  predict 流程天然复用(零改动)                                            │
│  • GET /predict/experiments 扫到该 trace                                │
│    (前缀 Finance Data Building/ + __session__ + params.pkl)             │
│  • query_sota 提取 workspace_path + sota_factors[].code                 │
│  • predict_infer.py 在 workspace 找到全部所需 pkl                        │
└──────────────────────────────────────────────────────────────────────┘
```

## 4. 后端设计

### 4.1 新增端点

**`POST /fastbacktest/run`** — 返回 `text/event-stream`(SSE)

**请求体**(JSON):
```json
{
  "alpha158": ["KMID", "KLEN", "ROC5", "ROC10"],
  "description": "基于价格动量与成交量背离构建因子..."
}
```
两个字段均为可选,但**至少一个非空**,否则返回 400。

**SSE 事件流**(逐阶段推送,每个事件一行 `data: {json}\n\n`):
```
data: {"stage":"codegen",     "status":"ok",      "factor_name":"momentum_volume", "code":"..."}
data: {"stage":"factor_eval", "status":"running"}
data: {"stage":"backtest",    "status":"running"}
data: {"stage":"done",        "status":"ok",      "trace_id":"...", "metrics":{...}, "equity":[["2017-01-03",1.0],...]}
```
任一阶段失败:
```
data: {"stage":"codegen", "status":"error", "error":"LLM timeout", "detail":"..."}
```

> 实现细节:Flask 用 `Response(generator, mimetype="text/event-stream")`,生成器函数内逐步 `yield`。注意 Flask 默认可能缓冲,需配置 `stream_with_context` + 关闭缓冲。

### 4.2 编排函数 `run_fastbacktest(payload, emit)`

线性四步,`emit(stage, status, **fields)` 向 SSE 推送:

| 步 | 动作 | 复用现有代码 | 失败处理 |
|----|------|-------------|---------|
| ① codegen | 单次 LLM 调用生成 factor.py 字符串 | CoSTEER 的 prompt 模板(直接调底层 LLM completion,**不走 `FactorCoSTEER.develop()` 的 evolving**);构造 `FactorTask(name, description, formulation)` | 报错返回 LLM 原文 |
| ② factor_eval | `FactorFBWorkspace(code_dict={"factor.py":code}).execute("Debug")` | `rdagent/components/coder/factor_coder/factor.py:105` | 失败把 traceback 返回给用户 |
| ③ backtest | `QlibFBWorkspace.execute("conf_combined_factors.yaml", env={QLIB_FACTOR_MODEL_SELECTOR:"linear"})` | `rdagent/scenarios/qlib/experiment/workspace.py:18` + `conf_combined_factors.yaml:57` linear 分支 | 失败返回 qrun 日志 |
| ④ trace_write | 组装最小 Trace + `LoopBase.save()` | 见 4.3 | 不影响已返回的结果 |

> **关键:`conf_combined_factors.yaml` 而非 `conf_baseline.yaml`**。前者用 `NestedDataLoader` 同时挂 `Alpha158DL`(算 Alpha158 子集)+ `StaticDataLoader`(读 `combined_factors_df.parquet`,载入因子.py 产出的值)。`conf_baseline.yaml` 只有 `Alpha158DL`,不生成 parquet,predict 无法复用。

**路径分支(Alpha158 vs 自然语言)**:
- **路径 A — 纯 Alpha158**(description 为空):跳过 Step ①②。Alpha158 子集拼成 `feature_expressions`/`feature_names` 注入 Jinja;`combined_factors_df.parquet` 仍由 `QlibFactorRunner.process_factor_data` 生成(空因子集或占位),保证 predict 所需文件齐全。无 LLM,最快。
- **路径 B — 纯自然语言**(alpha158 为空):执行完整 Step ①②③。`feature_expressions` 用默认 Alpha158 全集或空集。
- **路径 C — 组合**:Step ①② 生成自然语言因子并算值;Step ③ 把 Alpha158 子集(进 Jinja `feature_expressions`)+ 自然语言因子值(进 parquet)合并。

**模型配置**:固定 `model_selector="linear"`(LinearModel + OLS 闭式解,无训练,最快)。通过环境变量 `QLIB_FACTOR_MODEL_SELECTOR=linear` 注入,无需改 yaml。

**模板渲染**:`QlibFBWorkspace.__init__` 会 `inject_code_from_folder` 渲染 `conf_combined_factors.yaml` 的 Jinja 变量(`{{ feature_expressions }}` 等)。

### 4.3 微型 Trace 组装(核心)

目标:构造一个**单实验、单因子聚合、SOTA 标记**的 trace,让 `query_sota`(`rdagent/log/sota_query.py:54`)能原样提取,从而让 predict 自动发现。

**predict 的硬依赖**(来自探索,`predict_infer.py` 消费清单):
1. `combined_factors_df.parquet`(workspace 根)— SOTA 因子 feature 列
2. `mlruns/*/*/artifacts/task`(pickle)— dataset/handler/data_loader config
3. `mlruns/*/*/artifacts/params.pkl` — 模型权重,**同时也是 `/predict/experiments` 列表可见性的门槛**(`app.py:1509`)
4. `mlruns/*/*/artifacts/pred.pkl` — 历史 pred,增量水位线基线
5. SOTA 因子 `factor.py` 源码 — 从 trace session 的 `sub_workspace.file_dict` 提取

> 关键:`QlibFBWorkspace.execute("conf_baseline.yaml")` 跑完 qrun 后,2/3/4 自然产出;combined_factors_df.parquet 由合并逻辑写入。Step ④ 只需把这些挂到 Experiment 并序列化 session。

**组装代码结构**:
```python
# —— 1. 因子任务(聚合 Alpha158 + 自然语言为一个 Task)
factor_task = FactorTask(
    factor_name="alpha158_subset" if no_nl else nl_factor_name,
    factor_description=user_description or f"Alpha158 subset: {', '.join(alpha158)}",
    factor_formulation="(fast-backtest)",
)

# —— 2. 因子工作区(携带代码 → query_sota._extract_factors 提取 .code)
factor_ws = FactorFBWorkspace(
    target_task=factor_task,
    code_dict={"factor.py": generated_code},  # 自然语言路径有代码;纯 Alpha158 为占位
)

# —— 3. 实验工作区(Step ③ qrun 的那个 workspace,pkl 都在里面)
qlib_ws = <Step③ 的 QlibFBWorkspace>  # workspace_path 指向含 mlruns/ 的目录
# 注:用 conf_combined_factors.yaml,workspace 下必有 combined_factors_df.parquet

# —— 4. 组装 Experiment
exp = Experiment(
    sub_tasks=[factor_task],
    sub_workspace_list=[factor_ws],
    experiment_workspace=qlib_ws,
    result=<qlib_res.csv 的 pd.Series>,  # IC/年化/回撤
)
exp.hypothesis = Hypothesis(hypothesis=user_description or "fast backtest",
                            assumption=user_description or "fast backtest")

# —— 5. 标记为 SOTA(decision=True 是 get_sota_hypothesis_and_experiment 命中条件)
fb = HypothesisFeedback(reason="fast backtest", decision=True,
                        observations="auto-generated by fast backtest")

# —— 6. 微型 Trace + 最小 LoopBase,序列化
trace = Trace(...)
trace.hist.append((exp, fb))
loop = _MinimalLoop(trace=trace, steps=[])  # 够 LoopBase.save 的最小字段
loop.save(log_folder / "Finance Data Building" / f"fast-{randomname.get_name()}-{date}")
```

**predict 自动发现验证表**:

| predict 流程步骤 | 读取来源 | 快速回测是否满足 |
|----|------|------|
| `/predict/experiments` 过滤前缀 | `tid.startswith("Finance Data Building/")`(`app.py:1497`) | ✅ 命名保证 |
| `query_sota` 找 SOTA | `feedback.decision=True`(`sota_query.py:75`) | ✅ Step ⑤ |
| `query_sota` 提取 `experiment_workspace_path` | `exp.experiment_workspace.workspace_path`(`sota_query.py:123`) | ✅ Step ③ workspace |
| `query_sota` 提取 `sota_factors[].code` | `sub_workspace.file_dict["factor.py"]`(`sota_query.py:265`) | ✅ Step ② factor_ws |
| `params.pkl` 可见性门槛 | `mlruns/*/*/artifacts/params.pkl`(`app.py:1509`) | ✅ qrun 产出 |
| `predict_infer.py` 读 task/params.pkl/pred.pkl + parquet | workspace 内文件 | ✅ 全部由 qrun 写入 |

## 5. 前端设计

### 5.1 多页入口(对齐 predict 模式)

```
web/
├── fastbacktest.html              ← 新建(仿 predict.html)
├── vite.config.ts                 ← rollupOptions.input 加 fastbacktest
└── src/fastbacktest/
    ├── main.ts                    ← 仿 predict/main.ts(mount #fastbacktest-app)
    ├── router.ts                  ← 单页,可选 /result/:id
    ├── FastBacktestApp.vue        ← 根组件
    ├── use-fastbacktest.ts        ← composable(SSE 调用 + 状态机)
    ├── api.ts                     ← re-export services/rdagent-api.ts
    ├── components/
    │   ├── Alpha158Picker.vue     ← 因子勾选面板(29 族可折叠)
    │   ├── DescriptionInput.vue   ← 自然语言输入框
    │   ├── ProgressTimeline.vue   ← SSE 进度时间线(深色终端风格)
    │   ├── MetricsPanel.vue       ← 回测指标卡片
    │   └── EquityChart.vue        ← 收益曲线(ECharts)
    └── styles/fastbacktest.css
```

`services/rdagent-api.ts` 新增 `runFastBacktest(payload)` —— 用 `fetch` + `ReadableStream` 手动解析 SSE 帧(EventSource 不支持 POST body)。

### 5.2 视觉规范(对齐 multiα1pha,从 `tokens.css` 提取)

**设计令牌**(严格复用 `web/src/multialpha/styles/tokens.css`):
```css
--ma-bg: #f5f5f2;          /* 米白底 */
--ma-surface: #ffffff;     /* 白卡片 */
--ma-surface-2: #f0f1ed;   /* 次级面/输入框底 */
--ma-ink: #17191e;         /* 墨黑文字 */
--ma-muted: #858a94;       /* 弱文字 */
--ma-line: #e2e1dc;        /* 分割线/卡片边 */
--ma-gold: #b99a50;        /* 主强调(按钮/编号块/策略曲线) */
--ma-gold-dark: #8c6e2f;   /* 深金(编号块文字/eyebrow) */
--ma-gold-soft: #f3ecd9;   /* 软金底(ALPHA20 按钮) */
--ma-success: #248661;     /* 成功(年化/完成态) */
--ma-danger: #cf454d;      /* 危险(回撤) */
--ma-warning: #d3932f;     /* 警告 */
--ma-terminal: #0a0d13;    /* 深色终端底(进度时间线) */
--ma-radius: 6px;
--ma-shadow: 0 16px 45px rgb(18 21 27 / 10%);
```

**字体**:
- 标题/指标数字:`'Noto Serif SC','Songti SC','SimSun',serif`(衬线,金融研报质感)
- 正文/UI:`'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif`
- 数据/代码/eyebrow 标签:`'JetBrains Mono','SF Mono',Consolas,monospace`

**组件模式**(从首页复用):
- **头部 TopBar**:国新证券 logo(`https://h5.crsec.com.cn/logo.png`)+ 小字"国新证券"(letter-spacing 2.5px)/ 大字"Multiα1pha"(Noto Serif SC)。右侧 text 文字按钮。**直接复用 `TopBar.vue` 或复制其结构。**
- **章节标题 section-heading**:金色边框编号块(38×38,`1px solid #b99a50`,JetBrains Mono 编号)+ eyebrow 小标签(letter-spacing 2px)+ Serif 大标题 + 灰色 small 副标题。
- **白卡片**:白底 + `1px solid #d7d5ce` 边 + 6px 圆角 + 微阴影。
- **深色终端 terminal-frame**(进度时间线用):`#0a0d13` 底 + 网格背景(`#ffffff0b` 1px 线,48px 间距)+ 金色径向光晕 + 金色 LIVE 指示。
- **主按钮**:背景 `#b99a50` + 白字(对齐 `el-button--primary`)。

### 5.3 页面三态布局

**输入态**:
```
┌──────────────────────────────────────────────────────────────┐
│ [logo] 国新证券 / MultiAlpha              [⚙️ 设置][← 返回主站] │
├──────────────────────────────────────────────────────────────┤
│ [01] FAST BACKTEST                                            │
│      快速回测 · 自然语言策略即时验证                             │
│                                                                │
│ ┌── Alpha158 因子勾选 ──┐  ┌── 自然语言策略描述 ─────────┐    │
│ │ [全选][清空][ALPHA20]  │  │ 基于价格动量与成交量背离…    │    │
│ │ ▼价量形态 ☑KMID ☑KLEN  │  │                             │    │
│ │ ▼动量 ROC  ☑ROC5 ...   │  │ (单次生成,不修正)           │    │
│ │ ▸均线 MA   (0/5)       │  │                             │    │
│ │ ... 29 族              │  │ ⚠ 最快出图                  │    │
│ │ 已选 12/158            │  └─────────────────────────────┘    │
│ └───────────────────────┘                                     │
│              [ ▶ 开始快速回测 ](金色主按钮)                      │
├──────────────────────────────────────────────────────────────┤
```

**运行态**(深色终端进度):
```
│ ● ● ●  FAST BACKTEST · RUNNING        ● LIVE · 00:18          │
│ ✓ 因子代码生成     0.8s   factor_momentum_volume.py             │
│ ✓ 因子值计算       3.2s   result.h5 OK                          │
│ ⟳ Qlib 回测中     ...     LinearModel + csi300                  │
│ ○ 结果解析         待                                            │
│ [═══════════════ 65% ══════════] STAGE 3/4                      │
```

**结果态**:
```
│ [✓] BACKTEST COMPLETE                                          │
│     回测完成 · 耗时 28.4s                                        │
│ ┌ IC ────┐ ┌年化────┐ ┌夏普────┐ ┌回撤────┐                    │
│ │ 0.054  │ │ 18.3%  │ │ 1.42   │ │-12.0%  │  (Serif 大数字)     │
│ │ (金)   │ │ (绿)   │ │ (墨)   │ │ (红)   │                    │
│ └────────┘ └────────┘ └────────┘ └────────┘                    │
│ 净值曲线: ━策略(金)  ┄基准(灰)                                  │
│ ✓ 已保存为可预测实验  Finance Data Building/fast-aurora-...     │
│                                              [前往预测 →](绿)   │
```

**Alpha158 勾选面板**:
- 29 个因子族 + 4 个比价因子(OPEN0/HIGH0/LOW0/VWAP0),按族折叠
- 每族头部带"全选本族"checkbox + 计数 `(n/m)`
- 预置快捷按钮:`全选` / `清空` / `ALPHA20`(rdagent/utils/qlib.py:4 的 20 个)
- 数据来源:`rdagent/utils/qlib.py` 的 `ALPHA158` dict(158 个 `{name: expression}`)

**因子族分组**(用于 UI 折叠,从 `ALPHA158` 后缀归纳):
- 价量形态 K线(9):KMID/KLEN/KMID2/KUP/KUP2/KLOW/KLOW2/KSFT/KSFT2
- 动量 ROC(5)/ 均线 MA(5)/ 波动 STD+BETA(11)/ 拟合 RSQR+RESI(10)
- 极值 MAX+MIN(10)/ 分位 QTLU+QTLD(10)/ 排位 RANK(5)/ RSV(5)
- 位置 IMAX+IMIN+IMXD(15)/ 相关 CORR+CORD(17)
- 计数 CNTP+CNTN+CNTD(15)/ 求和 SUMP+SUMN+SUMD(15)
- 量均 VMA(5)/ 量波 VSTD(5)/ 量加波 WVMA(5)
- 量求和 VSUMP+VSUMN+VSUMD(15)/ 比价 OPEN0+HIGH0+LOW0+VWAP0(4)

### 5.4 状态机(`use-fastbacktest.ts`)

```typescript
type Stage = 'codegen' | 'factor_eval' | 'backtest' | 'done' | 'error'
type Phase = 'input' | 'running' | 'result'

const phase = ref<Phase>('input')
const stages = ref<{ stage: Stage; status: 'pending'|'running'|'ok'|'error'; ms?: number; detail?: string }[]>([])
const result = ref<{ traceId: string; metrics: Record<string, number>; equity: [string, number][] } | null>(null)

function run(payload: { alpha158?: string[]; description?: string }) {
  phase.value = 'running'
  fetch('/fastbacktest/run', { method:'POST', body: JSON.stringify(payload), headers:{'Content-Type':'application/json'} })
    .then(res => consumeSSE(res.body, onEvent))  // 手动解析 SSE 帧
}
```

## 6. 文件改动清单

### 新增
| 文件 | 说明 |
|------|------|
| `web/fastbacktest.html` | 多页入口 HTML |
| `web/src/fastbacktest/main.ts` | Vue 挂载入口 |
| `web/src/fastbacktest/router.ts` | 路由(单页) |
| `web/src/fastbacktest/FastBacktestApp.vue` | 根组件(三态切换) |
| `web/src/fastbacktest/use-fastbacktest.ts` | composable(SSE + 状态机) |
| `web/src/fastbacktest/api.ts` | re-export |
| `web/src/fastbacktest/components/*.vue` | 6 个组件(Picker/Input/Timeline/Metrics/Chart) |
| `web/src/fastbacktest/styles/fastbacktest.css` | 复用 multiα1pha 令牌 |
| `rdagent/app/fast_backtest.py`(或直接在 app.py 内) | 编排函数 `run_fastbacktest` |

### 修改
| 文件 | 改动 |
|------|------|
| `rdagent/log/server/app.py` | 新增 `POST /fastbacktest/run` 端点(SSE) |
| `web/vite.config.ts` | `rollupOptions.input` 加 `fastbacktest` |
| `web/src/services/rdagent-api.ts` | 新增 `runFastBacktest(payload)` |

### 不改动(零改动复用)
- `predict` 相关:`/predict/experiments`、`/predict/run`、`predict_infer.py` — 自动发现快速回测 trace
- `QlibFBWorkspace.execute`、`FactorFBWorkspace.execute`、`conf_baseline.yaml` — 直接调用
- `query_sota`、`LoopBase.save` — 直接调用

## 7. 风险与待确认

1. **`_MinimalLoop` 序列化兼容性**(需实现时验证):需验证 `LoopBase.save()` 能否接受一个没有真实 steps/loop_n 的 loop 对象。实现时需检查 `LoopBase.save` 的最小字段要求(见 `loop.py:353`)。若不兼容,备选方案是直接构造 `__session__/` 目录结构并 pickle trace,绕过 `LoopBase.save`。
2. **SSE 缓冲**:Flask 可能缓冲 SSE 流。需用 `stream_with_context` + 确保无代理缓冲(前端 dev proxy 也要注意)。实现时验证流式效果。
3. **Alpha158 纯勾选路径的 factor.py**(已在设计中化解):predict 的 `sota_factors[].code` 需要可执行 factor.py。纯 Alpha158 路径无 LLM 代码 —— 设计方案:为 Alpha158 子集生成一个**合成 factor.py**,把勾选的 Qlib 表达式物化写入 result.h5,使三路径 trace 结构统一。predict 提取到的 code 即此合成脚本。实现时复用 `rdagent/utils/qlib.py:189` 的 `TEST_FEATURE_CODE` 模式生成。
4. **combined_factors_df.parquet 生成**(已在设计中化解):用 `conf_combined_factors.yaml`(StaticDataLoader 读 parquet)而非 `conf_baseline.yaml`。parquet 由 `QlibFactorRunner.process_factor_data` 生成 —— 这是 fin_factor 的现成路径,linear selector 同样适用。

## 8. 成功标准

- [ ] 输入自然语言策略,30 秒内看到回测指标 + 收益曲线
- [ ] 勾选 Alpha158 子集,无需 LLM 即可回测
- [ ] 两者可组合输入
- [ ] 回测产出的 trace 在 `/predict/experiments` 列表中可见
- [ ] 该 trace 可成功触发 `POST /predict/run` 并产出 T+1 预测
- [ ] 视觉与 multiα1pha 首页一致(浅色 + 金色 + Serif + 深色终端进度)
