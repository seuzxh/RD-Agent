# 回测图表增加 Group 分组收益 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每轮回测图表的第 8 个子图展示 Group1-5 累计净值 + long-short 多空对冲收益曲线。

**Architecture:** 复用 qlib 已持久化但未被读取的 `pred.pkl`/`label.pkl`，移植 qlib `_group_return` 算法计算分组收益，扩展现有 `report_figure` 增加第 8 子图。数据通过 dict 打包随现有 chart tag 流转，`report_figure` 内部统一适配 dict/DataFrame 输入。前端零改动。

**Tech Stack:** Python 3.10, pandas, plotly, qlib recorder (mlflow artifacts), pytest

## Global Constraints

- Python 解释器：`/home/zxh/miniconda3/envs/rdagent/bin/python`（含 typer/fuzzywuzzy/qlib 等依赖）
- 测试命令：`/home/zxh/miniconda3/envs/rdagent/bin/python -m pytest <path> -v`
- 分组数固定 5 档（Group1 = 预测最高 20%，Group5 = 最低 20%）
- 向后兼容：历史 trace（无 group 数据，pkl 为纯 DataFrame）必须仍显示原 7 子图
- `factor_template` 与 `model_template` 的 `read_exp_res.py` 改动必须**完全一致**（两者经 diff 确认相同）
- 前端零改动（iframe 自动渲染新 HTML）

---

## File Structure

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `rdagent/log/ui/qlib_report_figure.py` | 图表生成核心。新增 `_calc_group_returns` 计算函数；扩展 `report_figure` 签名和子图逻辑 | Modify |
| `rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py` | 数据加载脚本。追加加载 pred/label 并算 group | Modify |
| `rdagent/scenarios/qlib/experiment/model_template/read_exp_res.py` | 同上（内容与 factor_template 一致） | Modify |
| `rdagent/scenarios/qlib/experiment/workspace.py` | 回测消费。读 ret+group 两个 pkl，以 dict 传给 logger | Modify |
| `rdagent/log/server/app.py` | 服务端懒渲染。`_generate_chart_html` 适配 dict 输入 | Modify |
| `rdagent/log/ui/storage.py` | legacy inline 渲染路径。适配 dict 输入 | Modify |
| `test/log/test_group_returns.py` | `_calc_group_returns` 单元测试 | Create |

---

### Task 1: `_calc_group_returns` 分组收益计算函数（TDD）

**Files:**
- Create: `test/log/test_group_returns.py`
- Modify: `rdagent/log/ui/qlib_report_figure.py`（在 `_calculate_report_data` 函数前，约 line 314，新增函数）

**Interfaces:**
- Produces: `def _calc_group_returns(pred_label: pd.DataFrame, n_groups: int = 5) -> pd.DataFrame` — 输入 MultiIndex DataFrame（列含 `score` 和 `label`），输出 datetime 索引、列为 `['Group1','Group2','Group3','Group4','Group5','long-short']` 的累计净值 DataFrame。供 Task 3 的 `read_exp_res.py` 和 Task 2 的 `report_figure` 调用。

- [ ] **Step 1: 写失败测试 — group 单调性 + 5 档划分 + long-short**

创建 `test/log/test_group_returns.py`：

```python
"""_calc_group_returns 单元测试：验证 Group1-5 + long-short 分组收益计算。"""
import numpy as np
import pandas as pd
import unittest

from rdagent.log.ui.qlib_report_figure import _calc_group_returns


def _make_pred_label(scores: list[float], labels: list[float]) -> pd.DataFrame:
    """构造单日 pred_label：MultiIndex[datetime, instrument], 列 [score, label]。"""
    n = len(scores)
    dates = [pd.Timestamp("2024-07-01")] * n
    instruments = [f"S{i:06d}" for i in range(n)]
    return pd.DataFrame(
        {"score": scores, "label": labels},
        index=pd.MultiIndex.from_arrays([dates, instruments], names=["datetime", "instrument"]),
    )


class CalcGroupReturnsTestCase(unittest.TestCase):
    def test_five_groups_plus_long_short_columns(self):
        """输出恰好含 Group1-5 + long-short 6 列。"""
        pl = _make_pred_label(list(range(10)), [float(i) for i in range(10)])
        result = _calc_group_returns(pl, n_groups=5)
        self.assertEqual(
            list(result.columns),
            ["Group1", "Group2", "Group3", "Group4", "Group5", "long-short"],
        )

    def test_group1_has_highest_return_when_score_predicts_label(self):
        """score 与 label 完全正相关时，Group1（高分组）累计收益最高。"""
        # score = label，score 越高 label 越高
        scores = list(range(10))
        labels = [float(i) for i in range(10)]
        pl = _make_pred_label(scores, labels)
        result = _calc_group_returns(pl, n_groups=5)
        # 10 个标的分 5 组，每组 2 个。Group1 = score 最高的 2 个(label 8,9)，均值最大
        self.assertGreater(result["Group1"].iloc[-1], result["Group5"].iloc[-1])
        self.assertGreater(result["Group2"].iloc[-1], result["Group3"].iloc[-1])

    def test_long_short_equals_group1_minus_group5(self):
        """long-short 每日值 = Group1 - Group5。"""
        scores = list(range(10))
        labels = [float(i) for i in range(10)]
        pl = _make_pred_label(scores, labels)
        result = _calc_group_returns(pl, n_groups=5)
        # 单日场景，cumsum 后 long-short = Group1 - Group5
        self.assertAlmostEqual(
            result["long-short"].iloc[-1],
            result["Group1"].iloc[-1] - result["Group5"].iloc[-1],
            places=6,
        )

    def test_empty_input_returns_empty_df(self):
        """空输入返回空 DataFrame（不抛异常）。"""
        pl = pd.DataFrame(
            {"score": [], "label": []},
            index=pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"]),
        )
        result = _calc_group_returns(pl)
        self.assertTrue(result.empty)

    def test_multi_day_cumulative(self):
        """多日数据：累计净值 = 每日 group 均值的 cumsum。"""
        # 两日，每日 score=label=range(5)
        day1 = _make_pred_label([0, 1, 2, 3, 4], [0.0, 1.0, 2.0, 3.0, 4.0])
        day2 = _make_pred_label([0, 1, 2, 3, 4], [0.0, 1.0, 2.0, 3.0, 4.0])
        day2.index = day2.index.set_levels(
            [pd.Index([pd.Timestamp("2024-07-02")])], level=0
        )
        pl = pd.concat([day1, day2])
        result = _calc_group_returns(pl, n_groups=5)
        # 每日每组 1 个标的，Group1 label=4，两日累计 = 8
        self.assertAlmostEqual(result["Group1"].iloc[-1], 8.0, places=6)
        self.assertEqual(len(result), 2)  # 两天


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/home/zxh/miniconda3/envs/rdagent/bin/python -m pytest test/log/test_group_returns.py -v`
Expected: FAIL with `ImportError: cannot import name '_calc_group_returns'`

- [ ] **Step 3: 实现 `_calc_group_returns`**

在 `rdagent/log/ui/qlib_report_figure.py` 的 `_calculate_report_data` 函数定义前（约 line 314）新增：

```python
def _calc_group_returns(pred_label: pd.DataFrame, n_groups: int = 5) -> pd.DataFrame:
    """计算分组累计收益净值（移植 qlib _group_return 算法）。

    :param pred_label: MultiIndex DataFrame，index=[datetime, instrument]，
                       列含 'score'（预测分）和 'label'（真实收益）。
    :param n_groups: 分组数，默认 5。
    :return: DataFrame，index=datetime（%Y-%m-%d 字符串），列为
             ['Group1',...,'Group{n_groups}', 'long-short']，值为累计净值。
             输入为空时返回空 DataFrame。
    """
    if pred_label.empty or "score" not in pred_label.columns or "label" not in pred_label.columns:
        return pd.DataFrame()

    # 按 score 降序排序后按 datetime 分组，每日均分 n_groups 档取 label 均值
    sorted_pl = pred_label.sort_values("score", ascending=False)
    daily_group_returns = {}
    for i in range(n_groups):
        daily_group_returns[f"Group{i + 1}"] = sorted_pl.groupby(level="datetime", group_keys=False)[
            "label"
        ].apply(lambda x: x[len(x) // n_groups * i : len(x) // n_groups * (i + 1)].mean())

    group_df = pd.DataFrame(daily_group_returns)
    # long-short = Group1 - GroupN（每日）
    group_df["long-short"] = group_df[f"Group1"] - group_df[f"Group{n_groups}"]
    # 累计净值
    group_df = group_df.cumsum()
    # 索引 strftime（与 _calculate_report_data 一致）
    group_df.index = group_df.index.strftime("%Y-%m-%d")
    group_df.sort_index(ascending=True, inplace=True)
    return group_df
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/home/zxh/miniconda3/envs/rdagent/bin/python -m pytest test/log/test_group_returns.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add test/log/test_group_returns.py rdagent/log/ui/qlib_report_figure.py
git commit -m "feat(chart): 新增 _calc_group_returns 计算 Group1-5 + long-short 分组累计收益

移植 qlib _group_return 算法：按 score 降序每日均分 5 档取 label 均值，
Group1-Group5 为多空对冲。TDD 覆盖列结构/单调性/long-short 等式/空输入/多日累计。"
```

---

### Task 2: 扩展 `report_figure` 支持第 8 子图（TDD）

**Files:**
- Modify: `rdagent/log/ui/qlib_report_figure.py:348` (`report_figure` 函数)
- Test: `test/log/test_group_returns.py`（追加测试类）

**Interfaces:**
- Consumes: Task 1 的 `_calc_group_returns`（不直接调，但 group_df 已是它的输出格式）
- Produces: `report_figure(df, group_df=None) -> go.Figure` — `df` 为组合层 DataFrame（不变），`group_df` 为分组累计净值 DataFrame（Task 1 输出格式）或 None。供 Task 4/5 的 `_generate_chart_html` 和 `storage.py` 调用。

- [ ] **Step 1: 写失败测试 — 向后兼容（无 group）+ 有 group 时 8 子图**

在 `test/log/test_group_returns.py` 末尾追加测试类：

```python
class ReportFigureGroupTestCase(unittest.TestCase):
    def _make_ret_df(self) -> pd.DataFrame:
        """构造最小组合层 DataFrame（满足 _calculate_report_data 所需列）。"""
        dates = pd.date_range("2024-07-01", periods=5, freq="D")
        return pd.DataFrame(
            {
                "return": [0.01, 0.02, -0.01, 0.015, 0.005],
                "bench": [0.005, 0.005, 0.005, 0.005, 0.005],
                "cost": [0.001] * 5,
                "turnover": [0.1] * 5,
            },
            index=dates,
        )

    def _make_group_df(self) -> pd.DataFrame:
        """构造最小 group DataFrame（6 列，5 日）。"""
        dates = ["2024-07-01", "2024-07-02", "2024-07-03", "2024-07-04", "2024-07-05"]
        return pd.DataFrame(
            {
                "Group1": [0.01, 0.02, 0.03, 0.04, 0.05],
                "Group2": [0.005, 0.01, 0.015, 0.02, 0.025],
                "Group3": [0.0, 0.0, 0.0, 0.0, 0.0],
                "Group4": [-0.005, -0.01, -0.015, -0.02, -0.025],
                "Group5": [-0.01, -0.02, -0.03, -0.04, -0.05],
                "long-short": [0.02, 0.04, 0.06, 0.08, 0.10],
            },
            index=dates,
        )

    def test_report_figure_backward_compat_no_group(self):
        """group_df=None 时维持原 7 子图行为（向后兼容）。"""
        from rdagent.log.ui.qlib_report_figure import report_figure

        fig = report_figure(self._make_ret_df(), group_df=None)
        # plotly figure 的 layout 有 7 行（原行为）
        self.assertIn("yaxis7", fig.layout)  # 第 7 行 y 轴存在
        self.assertNotIn("yaxis8", fig.layout)  # 第 8 行不存在

    def test_report_figure_with_group_has_8_rows(self):
        """group_df 非空时扩展为 8 子图。"""
        from rdagent.log.ui.qlib_report_figure import report_figure

        fig = report_figure(self._make_ret_df(), group_df=self._make_group_df())
        self.assertIn("yaxis8", fig.layout)  # 第 8 行存在

    def test_report_figure_with_empty_group_falls_back_to_7(self):
        """group_df 为空 DataFrame 时回退 7 子图（向后兼容）。"""
        from rdagent.log.ui.qlib_report_figure import report_figure

        fig = report_figure(self._make_ret_df(), group_df=pd.DataFrame())
        self.assertNotIn("yaxis8", fig.layout)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/home/zxh/miniconda3/envs/rdagent/bin/python -m pytest test/log/test_group_returns.py::ReportFigureGroupTestCase -v`
Expected: FAIL with `TypeError: report_figure() got an unexpected keyword argument 'group_df'`

- [ ] **Step 3: 修改 `report_figure` 签名和子图逻辑**

修改 `rdagent/log/ui/qlib_report_figure.py` 的 `report_figure` 函数（line 348）。改动点：

(a) 签名：`def report_figure(df: pd.DataFrame) -> list | tuple:` → `def report_figure(df: pd.DataFrame, group_df: pd.DataFrame = None) -> list | tuple:`

(b) 在 `# Create figure` 段（line 371 附近），判断是否有 group 数据：
```python
    has_group = group_df is not None and not group_df.empty
    n_rows = 8 if has_group else 7
```

(c) `_column_row_col_dict`（line 374-385）：当 `has_group` 时追加 group 曲线条目。在原列表后追加（每个 Group 一条 Scatter，long-short 一条虚线）：
```python
    if has_group:
        _group_colors = {"Group1": "#2ca02c", "Group2": "#98df8a", "Group3": "#ffbb78",
                         "Group4": "#ff7f0e", "Group5": "#d62728"}
        for col in ["Group1", "Group2", "Group3", "Group4", "Group5"]:
            _column_row_col_dict.append((col, dict(row=8, col=1)))
        _column_row_col_dict.append(("long-short", dict(row=8, col=1, graph_kwargs={"mode": "lines", "dash": "dash", "line_width": 2})))
```

(d) `_subplot_layout` 循环（line 388）：`range(1, 8)` → `range(1, n_rows + 1)`，且 `_show_line = i == n_rows`

(e) `_subplot_kwargs`（line 429-436）：`rows=7` → `rows=n_rows`，`row_width` 动态：
```python
    _row_width = [1, 1, 1, 3, 1, 1, 3]  # 原 7 行
    if has_group:
        _row_width = [1] + _row_width  # group 子图加在最前（plotly row_width 是倒序）
```

(f) 在构建 figure 前，需把 group_df 的列合并进 report_df（SubplotsGraph 从单个 df 读列）。在 `report_df = _temp_df`（line 369）后、创建 figure 前：
```python
    if has_group:
        # group_df 索引已是 %Y-%m-%d 字符串，对齐 report_df
        for col in ["Group1", "Group2", "Group3", "Group4", "Group5", "long-short"]:
            report_df[col] = group_df[col].reindex(report_df.index).ffill().fillna(0)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/home/zxh/miniconda3/envs/rdagent/bin/python -m pytest test/log/test_group_returns.py -v`
Expected: 8 passed（5 个 Task1 + 3 个 Task2）

- [ ] **Step 5: Commit**

```bash
git add rdagent/log/ui/qlib_report_figure.py test/log/test_group_returns.py
git commit -m "feat(chart): report_figure 支持第 8 子图展示 Group1-5 + long-short

group_df 非空时子图从 7 行扩展为 8 行，新增 Group1-5 累计净值（渐变色）+
long-short（虚线）。空值回退原 7 子图，向后兼容历史 trace。"
```

---

### Task 3: `read_exp_res.py` 加载 pred/label 生成 ret_group.pkl

**Files:**
- Modify: `rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py:55`（在 `ret_data_frame.to_pickle("ret.pkl")` 后追加）
- Modify: `rdagent/scenarios/qlib/experiment/model_template/read_exp_res.py:55`（同上，内容完全一致）

**Interfaces:**
- Consumes: Task 1 的 `_calc_group_returns`
- Produces: `ret_group.pkl` 文件（写入 workspace_path），供 Task 4 的 `workspace.py` 读取

- [ ] **Step 1: 修改 factor_template/read_exp_res.py**

在 `rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py` 第 55 行（`ret_data_frame.to_pickle("ret.pkl")`）后追加：

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

- [ ] **Step 2: 同步修改 model_template/read_exp_res.py**

把 Step 1 完全相同的代码追加到 `rdagent/scenarios/qlib/experiment/model_template/read_exp_res.py` 第 55 行后。两文件内容必须一致。

- [ ] **Step 3: 验证两文件改动一致**

Run: `diff rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py rdagent/scenarios/qlib/experiment/model_template/read_exp_res.py`
Expected: 无输出（完全一致）

- [ ] **Step 4: 用真实 mlruns 数据验证 _calc_group_returns 端到端**

Run:
```bash
/home/zxh/miniconda3/envs/rdagent/bin/python -c "
import pandas as pd
from rdagent.log.ui.qlib_report_figure import _calc_group_returns
base='git_ignore_folder/RD-Agent_workspace/e2264ed690334b35991d198806881ac1/mlruns/758559751613269796/3f99dfc529814fc5a96342d8cc1de964/artifacts'
pred=pd.read_pickle(f'{base}/pred.pkl'); label=pd.read_pickle(f'{base}/label.pkl')
pl=pd.DataFrame({'score':pred.stack(),'label':label.stack()})
g=_calc_group_returns(pl)
print('shape:',g.shape,'| columns:',list(g.columns))
print('Group1 末值:',round(g['Group1'].iloc[-1],4),'| Group5 末值:',round(g['Group5'].iloc[-1],4))
print('long-short 末值:',round(g['long-short'].iloc[-1],4))
assert list(g.columns)==['Group1','Group2','Group3','Group4','Group5','long-short']
assert not g.empty
print('OK')
"
```
Expected: 输出非空 DataFrame，6 列正确，Group1/Group5/long-short 有合理数值，末尾打印 `OK`

- [ ] **Step 5: Commit**

```bash
git add rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py rdagent/scenarios/qlib/experiment/model_template/read_exp_res.py
git commit -m "feat(qlib): read_exp_res 加载 pred/label 生成 ret_group.pkl

追加加载 qlib recorder 的 pred.pkl/label.pkl（此前未读取），调用
_calc_group_returns 计算分组累计收益，存为 ret_group.pkl。factor/model
模板同步修改。pred/label 缺失时 try/except 降级不阻断。"
```

---

### Task 4: `workspace.py` 以 dict 传递 ret + group

**Files:**
- Modify: `rdagent/scenarios/qlib/experiment/workspace.py:42-45`

**Interfaces:**
- Consumes: Task 3 产出的 `ret_group.pkl`
- Produces: `logger.log_object` 传入 `{"ret": df, "group": group_df}` dict（写入 chart pkl）

- [ ] **Step 1: 修改 workspace.py 的图表加载段**

修改 `rdagent/scenarios/qlib/experiment/workspace.py` 第 42-45 行：

原代码：
```python
        quantitative_backtesting_chart_path = self.workspace_path / "ret.pkl"
        if quantitative_backtesting_chart_path.exists():
            ret_df = pd.read_pickle(quantitative_backtesting_chart_path)
            logger.log_object(ret_df, tag="Quantitative Backtesting Chart")
```

改为：
```python
        quantitative_backtesting_chart_path = self.workspace_path / "ret.pkl"
        group_chart_path = self.workspace_path / "ret_group.pkl"
        if quantitative_backtesting_chart_path.exists():
            ret_df = pd.read_pickle(quantitative_backtesting_chart_path)
            group_df = (
                pd.read_pickle(group_chart_path) if group_chart_path.exists() else None
            )
            logger.log_object(
                {"ret": ret_df, "group": group_df},
                tag="Quantitative Backtesting Chart",
            )
```

- [ ] **Step 2: Commit**

```bash
git add rdagent/scenarios/qlib/experiment/workspace.py
git commit -m "feat(qlib): workspace 以 dict 传递 ret+group 给 chart logger

log_object 现传入 {'ret':组合层df, 'group':分组df} 而非单个 DataFrame。
group 缺失时为 None，消费端据此降级。"
```

---

### Task 5: 服务端 `_generate_chart_html` 适配 dict 输入

**Files:**
- Modify: `rdagent/log/server/app.py:717-736` (`_generate_chart_html`)
- Modify: `rdagent/log/ui/storage.py:212-225` (legacy inline 路径)

**Interfaces:**
- Consumes: Task 2 的 `report_figure(df, group_df=None)`、Task 4 的 dict pkl 格式

- [ ] **Step 1: 修改 `_generate_chart_html`（app.py:717）**

原代码（line 726-729）：
```python
    with open(df_pkl_path, 'rb') as f:
        df = _pickle.load(f)

    fig = report_figure(df)
```

改为：
```python
    with open(df_pkl_path, 'rb') as f:
        obj = _pickle.load(f)

    # 兼容 dict（新格式 {'ret':..,'group':..}）和 DataFrame（历史 trace）
    if isinstance(obj, dict) and "ret" in obj:
        fig = report_figure(obj["ret"], group_df=obj.get("group"))
    else:
        fig = report_figure(obj)
```

- [ ] **Step 2: 修改 storage.py legacy 路径（line 223）**

原代码：
```python
                    "content": {"chart_html": plotly.io.to_html(report_figure(obj))},
```

改为：
```python
                    "content": {
                        "chart_html": plotly.io.to_html(
                            report_figure(obj["ret"], group_df=obj.get("group"))
                            if isinstance(obj, dict) and "ret" in obj
                            else report_figure(obj)
                        )
                    },
```

- [ ] **Step 3: 验证历史 trace（DataFrame pkl）仍正常生成**

Run:
```bash
/home/zxh/miniconda3/envs/rdagent/bin/python -c "
import pickle, pandas as pd
from pathlib import Path
from unittest import mock
from rdagent.log.server import app as server_app

# 模拟历史 trace 的纯 DataFrame pkl
hist_df = pd.DataFrame(
    {'return':[0.01,0.02],'bench':[0.005,0.005],'cost':[0.001,0.001],'turnover':[0.1,0.1]},
    index=pd.date_range('2024-07-01',periods=2),
)
import tempfile
with tempfile.NamedTemporaryFile(suffix='.pkl',delete=False) as f:
    pickle.dump(hist_df, f)
    path = f.name

html = server_app._generate_chart_html(Path(path))
assert '<html>' in html or '<div' in html
print('历史 DataFrame pkl 正常生成 HTML，向后兼容 OK')
"
```
Expected: 打印 `历史 DataFrame pkl 正常生成 HTML，向后兼容 OK`，无异常

- [ ] **Step 4: 验证新格式 dict pkl 生成 8 子图**

Run:
```bash
/home/zxh/miniconda3/envs/rdagent/bin/python -c "
import pickle, pandas as pd
from pathlib import Path
from rdagent.log.server import app as server_app

ret_df = pd.DataFrame(
    {'return':[0.01,0.02],'bench':[0.005,0.005],'cost':[0.001,0.001],'turnover':[0.1,0.1]},
    index=pd.date_range('2024-07-01',periods=2),
)
group_df = pd.DataFrame(
    {'Group1':[0.01,0.02],'Group2':[0.005,0.01],'Group3':[0.0,0.0],'Group4':[-0.005,-0.01],'Group5':[-0.01,-0.02],'long-short':[0.02,0.04]},
    index=['2024-07-01','2024-07-02'],
)
import tempfile
with tempfile.NamedTemporaryFile(suffix='.pkl',delete=False) as f:
    pickle.dump({'ret':ret_df,'group':group_df}, f)
    path = f.name

html = server_app._generate_chart_html(Path(path))
assert 'yaxis8' in html or 'Group1' in html
print('dict pkl 生成含 group 的 8 子图 HTML OK')
"
```
Expected: 打印 `dict pkl 生成含 group 的 8 子图 HTML OK`

- [ ] **Step 5: Commit**

```bash
git add rdagent/log/server/app.py rdagent/log/ui/storage.py
git commit -m "feat(server): _generate_chart_html 适配 dict pkl 格式

从 pkl 加载后判断：dict（新格式 ret+group）→ 分传 report_figure(df,group_df)；
DataFrame（历史 trace）→ report_figure(df) 向后兼容。storage.py legacy 路径同步。"
```

---

### Task 6: 全量回归测试

- [ ] **Step 1: 运行全部新增测试**

Run: `/home/zxh/miniconda3/envs/rdagent/bin/python -m pytest test/log/ -v`
Expected: 所有测试 PASS（Task 1 的 5 个 + Task 2 的 3 个 = 8 个，加上既有 Bug1 测试）

- [ ] **Step 2: 检查无语法错误/lint 问题**

Run: `/home/zxh/miniconda3/envs/rdagent/bin/python -c "from rdagent.log.ui.qlib_report_figure import report_figure, _calc_group_returns; from rdagent.log.server import app; from rdagent.log.ui import storage; print('all imports OK')"`
Expected: 打印 `all imports OK`

- [ ] **Step 3: 端到端验证（如有可重新触发的 trace）**

可选：删除一个已有 trace 的 chart HTML 缓存，重新请求 `/api/v2/trace/artifact`，确认生成正常。若环境不允许实际跑回测，Task 3 Step 4 + Task 5 Step 3/4 已覆盖核心路径。

- [ ] **Step 4: 最终提交（如有遗漏的改动）**

```bash
git status  # 确认工作区干净
git log --oneline -6  # 确认 5 个功能 commit
```

---

## Self-Review Checklist

**Spec 覆盖**：
- ✅ `_calc_group_returns` 函数 → Task 1
- ✅ read_exp_res.py 加载 pred/label → Task 3（factor + model 两份）
- ✅ workspace.py dict 传递 → Task 4
- ✅ report_figure 第 8 子图 → Task 2
- ✅ app.py/storage.py 适配 → Task 5
- ✅ 向后兼容（历史 trace 7 子图）→ Task 2 Step 1 第3个测试 + Task 5 Step 3
- ✅ 错误处理（pred/label 缺失）→ Task 3 的 try/except + Task 1 的空输入测试

**Placeholder 扫描**：无 TBD/TODO，所有步骤含完整代码。

**类型一致性**：`_calc_group_returns(pred_label, n_groups=5) -> pd.DataFrame` 在 Task 1 定义，Task 3 调用签名一致；`report_figure(df, group_df=None)` 在 Task 2 定义，Task 5 调用签名一致。`ret_group.pkl` 文件名在 Task 3 产出、Task 4 消费，一致。
