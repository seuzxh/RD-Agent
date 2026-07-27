# 回测图表增加 Group 分组收益（Group1-5 + Long-Short）

**日期**：2026-07-27
**状态**：待实现
**类型**：功能增强

## 背景与动机

当前每轮回测产物的「Quantitative Backtesting Chart」只展示**组合层**收益曲线（累计收益、回撤、超额、换手等 7 个子图），缺少**分组**收益——即按预测分数排序后划分 5 档（Group1 = 预测最高 20%，Group5 = 最低 20%）的累计净值，以及 Group1 − Group5 的多空对冲收益（long-short）。

分组收益是评估因子**单调性/选股能力**的关键指标：如果因子有效，Group1 净值应持续高于 Group5，long-short 曲线应单调上升。当前缺失导致无法直观判断因子的分层能力。

## 现状分析（数据链路）

经完整代码追踪，数据链路如下：

| 环节 | 文件 | 现状 |
|------|------|------|
| 数据源 | qlib recorder | 已持久化 `pred.pkl`（标的×日 score）+ `label.pkl`（标的×日 真实收益）。**但 RD-Agent 从未读取** |
| 读取 | `rdagent/scenarios/qlib/experiment/{factor_template,model_template}/read_exp_res.py:54` | 只加载 `portfolio_analysis/report_normal_1day.pkl` → `ret.pkl`（组合层 9 列：return/bench/cost/turnover 等） |
| 生成图表 | `rdagent/log/ui/qlib_report_figure.py:348 report_figure(df)` | plotly 7 行子图，输入单个 DataFrame |
| 消费 | `rdagent/scenarios/qlib/experiment/workspace.py:42-45` | 读 `ret.pkl` → `logger.log_object(df, tag="Quantitative Backtesting Chart")` |
| 存储 | `logger.log_object` → pkl 文件（`Loop_N/running/Quantitative Backtesting Chart/...`） | pkl 内容为 DataFrame |
| 服务端 | `rdagent/log/server/app.py` `_generate_chart_html`(717) / `_find_chart_pkl`(703) | 懒加载：glob 找 pkl → `report_figure(df)` → plotly HTML（带 CDN）→ 缓存 `.html`+`.etag` |
| 前端 | `web/src/multialpha/components/ResultWorkspace.vue:10` | iframe 渲染 artifact 端点返回的 HTML |

**关键可行性结论**：qlib 已有 `_group_return` 算法（`qlib/contrib/report/analysis_model/analysis_model_performance.py:21-78`），输入正是 `pred` + `label`（MultiIndex[instrument, datetime]，列 [score, label]）。算法核心（~15 行）：按 score 降序排序，每日均分 N 档取 label 均值 → 每日收益，`Group1 − GroupN` = long-short。**数据齐全，只需加载 + 计算 + 绘图，无需新建数据管道。**

`factor_template` 与 `model_template` 的 `read_exp_res.py` 经 diff 确认**完全一致**，两处需同步修改。

## 设计目标

1. 在现有回测图表下方新增第 8 个子图，展示 Group1-5 累计净值 + long-short 曲线
2. **前端零改动**（iframe 自动渲染新 HTML）
3. **向后兼容**：历史 trace（无 group 数据）仍正常显示原 7 子图
4. 复用 qlib 成熟算法，不引入新依赖

## 方案

### 选定方案：A（扩展单文件 + 单图增加子图）

否决方案 B（独立 artifact 端点 + 前端新 tab）：改动大（后端新端点 + 前端组件 + 类型链路），收益不抵成本。
否决方案 C（yaml `ana_long_short: True`）：只产出单条 long-short 曲线，无 group1-5，不满足需求。

### 组件设计

#### 组件 1：分组收益计算函数 `_calc_group_returns`

**职责**：输入 pred + label，输出每日分组累计净值 DataFrame。

**位置**：新增到 `rdagent/log/ui/qlib_report_figure.py`（与 `report_figure` 同文件，数据紧密相关）。

**接口**：
```python
def _calc_group_returns(pred_label: pd.DataFrame, n_groups: int = 5) -> pd.DataFrame:
    """
    :param pred_label: MultiIndex[instrument, datetime], 列含 'score' 和 'label'
    :param n_groups: 分组数，默认 5
    :return: DataFrame, index=datetime, 列=['Group1',...,'Group5','long-short']，
             值为累计净值（cumsum of daily group mean return）
    """
```

**算法**（移植 qlib `_group_return`）：
1. 按 datetime 分组，每组内按 score 降序排序
2. 均分 n_groups 档，取每档 label 均值 → 每日每组的收益
3. `long-short = Group1 - GroupN`（每日）
4. 每列 cumsum → 累计净值
5. 索引 strftime 为 `%Y-%m-%d`（与 `_calculate_report_data` 一致）

**错误处理**：pred/label 缺失或形状不符时返回空 DataFrame（调用方据此降级）。

#### 组件 2：`read_exp_res.py` 扩展

**位置**：`factor_template/read_exp_res.py` 与 `model_template/read_exp_res.py`（改动一致）。

在第 55 行（`ret_data_frame.to_pickle("ret.pkl")`）后追加：
```python
# 加载 pred/label，计算分组收益（Group1-5 + long-short 累计净值）
try:
    from rdagent.log.ui.qlib_report_figure import _calc_group_returns
    pred = latest_recorder.load_object("pred.pkl")
    label = latest_recorder.load_object("label.pkl")
    pred_label = pd.DataFrame(
        {"score": pred.stack(), "label": label.stack()}
    )
    group_df = _calc_group_returns(pred_label, n_groups=5)
    group_df.to_pickle("ret_group.pkl")
    print("Group returns saved to ret_group.pkl")
except Exception as e:
    print(f"Warning: group returns not available: {e}")
```

注意：`read_exp_res.py` 作为子进程脚本运行（`workspace.py:38 entry="python read_exp_res.py"`），需确认 `rdagent` 在子进程环境可导入。`_calc_group_returns` 是纯 pandas 函数无重依赖，且子进程本就运行在 rdagent 环境中（执行 qlib 回测），导入安全。

#### 组件 3：`workspace.py` 扩展

**位置**：`rdagent/scenarios/qlib/experiment/workspace.py:42-45`。

```python
quantitative_backtesting_chart_path = self.workspace_path / "ret.pkl"
group_chart_path = self.workspace_path / "ret_group.pkl"
if quantitative_backtesting_chart_path.exists():
    ret_df = pd.read_pickle(quantitative_backtesting_chart_path)
    group_df = pd.read_pickle(group_chart_path) if group_chart_path.exists() else None
    logger.log_object(
        {"ret": ret_df, "group": group_df},
        tag="Quantitative Backtesting Chart",
    )
```

#### 组件 4：`report_figure` 扩展

**位置**：`rdagent/log/ui/qlib_report_figure.py:348`。

**签名变更**：`report_figure(df, group_df=None)`

**逻辑**：
- `group_df` 非空（`group_df is not None and not group_df.empty`）：子图行数 7→8，新增第 8 行画 Group1-5（实线，渐变色）+ long-short（虚线）。`_subplot_kwargs.rows=8`，`row_width=[1,1,1,1,3,1,1,3]`，`_column_row_col_dict` 追加 group 曲线条目，`_subplot_layout` 循环 `range(1, 9)`
- `group_df` 为 None 或空 DataFrame：维持原 7 子图行为（向后兼容）
- group 曲线的 x 轴对齐：group_df 索引已是 `%Y-%m-%d` 字符串，与 report_df 一致

**图表细节**：
- Group1-5 用 plotly 默认色阶（或手动指定蓝→红渐变，呼应"高分组→低分组"）
- long-short 用黑色虚线，线宽略粗，突出对冲收益
- 第 8 子图标题/y 轴标签："Cumulative Group Return"

#### 组件 5：服务端渲染适配

`logger.log_object` 现传 dict（`{"ret":..., "group":...}`）而非 DataFrame。需适配两处：

1. **`app.py:_generate_chart_html`（717）** 和 **`_read_trace_into`/storage.py legacy 路径**：从加载的 pkl 对象判断类型——若为 dict 取 `ret`/`group` 分传 `report_figure`；若为 DataFrame（历史 trace）直接传 `report_figure(df)`。

```python
def _generate_chart_html(chart_obj) -> str:
    if isinstance(chart_obj, dict):
        fig = report_figure(chart_obj["ret"], chart_obj.get("group"))
    else:
        fig = report_figure(chart_obj)  # 历史兼容
    return plotly.io.to_html(fig, include_plotlyjs=False)
```

2. **缓存失效**：由于图表内容变化，历史缓存 `.html` 需失效。ETag 基于源 pkl 字节，而 pkl 内容变了（dict vs DataFrame），ETag 自然不同 → 自动重新生成，**无需手动清缓存**。

### 数据流（修复后）

```
qlib recorder (pred.pkl, label.pkl, report_normal_1day.pkl)
    ↓ read_exp_res.py
ret.pkl (组合层) + ret_group.pkl (分组累计净值)  ← 新增
    ↓ workspace.py
log_object({"ret":..., "group":...}, tag="...Chart")
    ↓ storage → pkl 文件
    ↓ app.py _generate_chart_html (懒加载)
report_figure(ret_df, group_df) → 8 子图 plotly HTML
    ↓ /api/v2/trace/artifact
    ↓ ResultWorkspace.vue iframe
用户看到 Group1-5 + long-short 子图
```

## 错误处理

| 场景 | 处理 |
|------|------|
| pred.pkl/label.pkl 不存在（老版本 qlib 或回测失败） | `read_exp_res.py` 的 try/except 打印 warning，不生成 ret_group.pkl |
| ret_group.pkl 不存在（历史 trace） | `workspace.py` group_df=None，`report_figure(df)` 走原 7 子图 |
| pred/label 形状不符（空数据） | `_calc_group_returns` 返回空 DataFrame，`report_figure` 检测空则跳过第 8 子图 |
| 加载的 pkl 是 DataFrame 而非 dict（历史 trace 缓存） | `_generate_chart_html` isinstance 分支处理 |
| **label.pkl 含大量 NaN**（真实数据，未来收益约 50% NaN，集中在高分位） | `_calc_group_returns` 在排序分组前 `dropna(subset=["score", "label"])`，丢弃 score 或 label 为 NaN 的标的；否则 Group1 会全 NaN（NaN 经 mean→cumsum 传播）。对齐 qlib `pred_label_drop` 行为 |

## 测试策略

1. **单元测试 `_calc_group_returns`**：构造已知 pred_label（手工设计单调场景），断言 Group1 > Group5、long-short 单调上升、5 档划分正确
2. **单元测试 `report_figure` 向后兼容**：传入 `group_df=None` 和历史 DataFrame，断言仍生成 7 子图
3. **集成验证**：对已有 trace 重新触发图表生成（删缓存 .html），确认 8 子图正常渲染

## 影响范围

| 文件 | 改动类型 |
|------|---------|
| `rdagent/log/ui/qlib_report_figure.py` | 新增 `_calc_group_returns`；扩展 `report_figure` 签名和子图逻辑 |
| `rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py` | 追加载入 pred/label + 计算 group |
| `rdagent/scenarios/qlib/experiment/model_template/read_exp_res.py` | 同上（内容一致） |
| `rdagent/scenarios/qlib/experiment/workspace.py` | log_object 传 dict |
| `rdagent/log/server/app.py` | `_generate_chart_html` 适配 dict/DataFrame |
| `rdagent/log/ui/storage.py` | legacy inline 路径适配（同 app.py） |

**前端零改动**。

## 非目标（YAGNI）

- 不做 IC 分析、换手率分析等其他 qlib analysis（用户只要求 group 收益）
- 不改 qlib yaml 配置（`ana_long_short` 保持 False，自行计算更灵活）
- 不做 group 收益的数值表格展示（只图表）
- 不支持自定义分组数（固定 5 档，后续需要再加参数）
