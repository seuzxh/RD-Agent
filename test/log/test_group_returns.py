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


if __name__ == "__main__":
    unittest.main()
