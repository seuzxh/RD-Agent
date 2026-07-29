"""_calc_group_returns 单元测试：验证 Group1-5 + long-short 分组收益计算。"""
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
        # NOTE: 原始 brief 使用 day2.index.set_levels(...) 替换日期，在 pandas>=2.3 下
        # 抛 TypeError("Levels must be list-like")。这里改为直接构造第二日的 fixture，
        # 数据与断言与 brief 完全一致，仅 fixture 构建方式适配 pandas 2.3。
        day2 = _make_pred_label([0, 1, 2, 3, 4], [0.0, 1.0, 2.0, 3.0, 4.0])
        day2_idx = pd.MultiIndex.from_arrays(
            [
                [pd.Timestamp("2024-07-02")] * len(day2),
                day2.index.get_level_values("instrument"),
            ],
            names=["datetime", "instrument"],
        )
        day2.index = day2_idx
        pl = pd.concat([day1, day2])
        result = _calc_group_returns(pl, n_groups=5)
        # 每日每组 1 个标的，Group1 label=4，两日累计 = 8
        self.assertAlmostEqual(result["Group1"].iloc[-1], 8.0, places=6)
        self.assertEqual(len(result), 2)  # 两天

    def test_nan_in_top_score_bucket_not_propagated(self):
        """NaN label 集中在 top-score 桶（真实数据典型情况）时也不应让 Group1 全 NaN。

        真实 qlib label.pkl 中未来收益未结算的近期标的 score 往往最高（NaN 集中在
        top-score 桶），此处把 NaN 放在最高 score 的标的上以复现该生产场景。
        若不在分组前 dropna，Group1 均值会被 top-score 桶的 NaN 污染成全 NaN。
        """
        # 与上一用例相同的真实生产模式，独立断言以锁定该回归。
        scores = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
        labels = [float("nan"), float("nan"), 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01]
        pl = _make_pred_label(scores, labels)
        result = _calc_group_returns(pl, n_groups=5)
        self.assertFalse(
            result["Group1"].isna().all(),
            "Group1 不应全 NaN（top-score 桶中的 NaN label 需先 dropna 再分组）",
        )


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


if __name__ == "__main__":
    unittest.main()
