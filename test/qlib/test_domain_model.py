"""Tests for the quant research domain model."""

import pandas as pd
import pytest

from rdagent.scenarios.qlib.domain import (
    FactorMetrics,
    ModelRegistry,
    RawFactor,
    Report,
    SignalPool,
    SignalStatus,
    Strategy,
    StrategyMetrics,
    CompositeModel,
    Experiment,
)


# ──────────────────────────────────────────────
# FactorMetrics
# ──────────────────────────────────────────────


class TestFactorMetrics:
    def test_from_dict(self):
        fm = FactorMetrics.from_result_dict({
            "IC": 0.052,
            "ICIR": 0.89,
            "Rank IC": 0.048,
            "Rank ICIR": 0.85,
        })
        assert fm.ic == 0.052
        assert fm.icir == 0.89
        assert fm.rank_ic == 0.048
        assert fm.rank_icir == 0.85

    def test_from_series(self):
        s = pd.Series({"IC": 0.03, "ICIR": 0.5, "Rank IC": 0.028, "Rank ICIR": 0.48})
        fm = FactorMetrics.from_result_dict(s)
        assert fm.ic == 0.03
        assert fm.icir == 0.5

    def test_from_dataframe(self):
        """Qlib result CSV has metrics as rows, experiments as columns."""
        df = pd.DataFrame({
            "Round 1": [0.04, 0.6, 0.038, 0.58],
        }, index=["IC", "ICIR", "Rank IC", "Rank ICIR"])
        fm = FactorMetrics.from_result_dict(df)
        assert fm.ic == 0.04
        assert fm.icir == 0.6
        assert fm.rank_ic == 0.038
        assert fm.rank_icir == 0.58

    def test_from_empty_dict(self):
        fm = FactorMetrics.from_result_dict({})
        assert fm.ic == 0.0
        assert fm.icir == 0.0
        assert fm.rank_ic == 0.0

    def test_from_partial_dict(self):
        fm = FactorMetrics.from_result_dict({"IC": 0.05})
        assert fm.ic == 0.05
        assert fm.icir == 0.0  # missing fields default to 0


# ──────────────────────────────────────────────
# StrategyMetrics
# ──────────────────────────────────────────────


class TestStrategyMetrics:
    def test_from_dict(self):
        sm = StrategyMetrics.from_result_dict({
            "1day.excess_return_with_cost.annualized_return": 0.153,
            "1day.excess_return_with_cost.max_drawdown": -0.085,
            "1day.excess_return_with_cost.information_ratio": 0.72,
        })
        assert sm.annualized_return == 0.153
        assert sm.max_drawdown == -0.085
        assert sm.information_ratio == 0.72
        assert sm.calmar_ratio == pytest.approx(0.153 / 0.085, rel=1e-6)

    def test_from_dict_with_trailing_spaces(self):
        """Qlib result keys sometimes have trailing spaces (e.g. 'annualized_return ')."""
        sm = StrategyMetrics.from_result_dict({
            "1day.excess_return_with_cost.annualized_return ": 0.153,
            "1day.excess_return_with_cost.max_drawdown ": -0.085,
        })
        assert sm.annualized_return == 0.153
        assert sm.max_drawdown == -0.085
        assert sm.calmar_ratio == pytest.approx(0.153 / 0.085, rel=1e-6)

    def test_calmar_ratio_zero_mdd(self):
        """calmar_ratio should not divide by zero when MDD is 0."""
        sm = StrategyMetrics.from_result_dict({
            "1day.excess_return_with_cost.annualized_return": 0.1,
            "1day.excess_return_with_cost.max_drawdown": 0.0,
        })
        assert sm.calmar_ratio == pytest.approx(0.1 / 1e-6, rel=1e-3)

    def test_from_empty_dict(self):
        sm = StrategyMetrics.from_result_dict({})
        assert sm.annualized_return == 0.0
        assert sm.max_drawdown == 1.0  # fallback default to avoid div-by-zero
        assert sm.information_ratio == 0.0
        assert sm.calmar_ratio == 0.0

    def test_important_metrics_keys(self):
        keys = StrategyMetrics.important_metrics_keys()
        assert "IC" in keys
        assert "1day.excess_return_with_cost.annualized_return" in keys


# ──────────────────────────────────────────────
# SignalPool
# ──────────────────────────────────────────────


class TestSignalPool:
    def test_add_and_get(self):
        pool = SignalPool()
        f = RawFactor(name="mom_5", description="5-day momentum")
        pool.add(f)
        assert pool.get("mom_5") == f
        assert pool.total_count == 1

    def test_mark_sota(self):
        pool = SignalPool()
        f = RawFactor(name="mom_5", description="5-day momentum")
        pool.add(f)
        pool.mark_sota("mom_5")
        assert pool.is_sota("mom_5")
        assert f.status == SignalStatus.SOTA
        assert len(pool.get_sota_factors()) == 1

    def test_unmark_sota(self):
        pool = SignalPool()
        f = RawFactor(name="mom_5", description="5-day momentum")
        pool.add(f)
        pool.mark_sota("mom_5")
        pool.unmark_sota("mom_5")
        assert not pool.is_sota("mom_5")
        assert f.status == SignalStatus.ACTIVE

    def test_get_by_status(self):
        pool = SignalPool()
        pool.add(RawFactor(name="a", description="", status=SignalStatus.SOTA))
        pool.add(RawFactor(name="b", description="", status=SignalStatus.DEPRECATED))
        pool.add(RawFactor(name="c", description="", status=SignalStatus.PENDING))
        assert len(pool.get_by_status(SignalStatus.SOTA)) == 1
        assert len(pool.get_by_status(SignalStatus.DEPRECATED)) == 1
        assert len(pool.get_by_status(SignalStatus.PENDING)) == 1

    def test_remove(self):
        pool = SignalPool()
        pool.add(RawFactor(name="mom_5", description=""))
        pool.mark_sota("mom_5")
        pool.remove("mom_5")
        assert pool.get("mom_5") is None
        assert not pool.is_sota("mom_5")
        assert pool.total_count == 0

    def test_serialization_round_trip(self):
        pool = SignalPool()
        pool.add(RawFactor(
            name="mom_5", description="5-day momentum",
            expression="Mean(Return($close, 5), 5)",
            status=SignalStatus.SOTA,
            factor_metrics=FactorMetrics(ic=0.052, icir=0.89),
            round_number=1,
        ))
        pool.add(RawFactor(
            name="rev_20", description="20-day reversal",
            expression="Mean(Return($close, 20), 20)",
            status=SignalStatus.ACTIVE,
            round_number=2,
        ))
        pool.mark_sota("mom_5")

        data = pool.to_dict()
        restored = SignalPool.from_dict(data)

        assert restored.total_count == 2
        assert restored.is_sota("mom_5")
        assert restored.get("mom_5").expression == "Mean(Return($close, 5), 5)"
        assert restored.get("mom_5").factor_metrics.ic == 0.052
        assert restored.get("rev_20").status == SignalStatus.ACTIVE
        assert restored.get("rev_20").round_number == 2

    def test_deduplicate_no_sota(self):
        """Dedup with empty SOTA pool should return all new factors."""
        pool = SignalPool()
        new = [RawFactor(name="mom_5", description="", factor_metrics=FactorMetrics(ic=0.05))]
        result = pool.deduplicate(new)
        assert len(result) == 1

    def test_empty_pool_properties(self):
        pool = SignalPool()
        assert pool.total_count == 0
        assert pool.sota_count == 0
        assert pool.all == []
        assert pool.get_sota_factors() == []


# ──────────────────────────────────────────────
# ModelRegistry
# ──────────────────────────────────────────────


class TestModelRegistry:
    def test_register_and_get(self):
        reg = ModelRegistry()
        m = CompositeModel(name="lgbm_v1", description="LGBM model", model_type="lgbm")
        reg.register(m)
        assert reg.get("lgbm_v1") == m
        assert reg.total_count == 1

    def test_mark_sota(self):
        reg = ModelRegistry()
        reg.register(CompositeModel(name="lgbm_v1", description="", model_type="lgbm"))
        reg.mark_sota("lgbm_v1")  # first SOTA
        reg.register(CompositeModel(name="lstm_v1", description="", model_type="nn"))
        reg.mark_sota("lstm_v1")  # overwrites
        sota = reg.get_sota_model()
        assert sota is not None
        assert sota.name == "lstm_v1"
        assert sota.status == SignalStatus.SOTA
        assert reg.get("lgbm_v1").status == SignalStatus.ACTIVE  # previous SOTA was demoted

    def test_mark_sota_overwrites_previous(self):
        reg = ModelRegistry()
        reg.register(CompositeModel(name="v1", description="", model_type="lgbm"))
        reg.mark_sota("v1")
        reg.register(CompositeModel(name="v2", description="", model_type="nn"))
        reg.mark_sota("v2")
        sota = reg.get_sota_model()
        assert sota.name == "v2"
        assert reg.get("v1").status == SignalStatus.ACTIVE

    def test_get_sota_model_empty(self):
        assert ModelRegistry().get_sota_model() is None

    def test_remove(self):
        reg = ModelRegistry()
        reg.register(CompositeModel(name="v1", description="", model_type="lgbm"))
        reg.mark_sota("v1")
        reg.remove("v1")
        assert reg.get("v1") is None
        assert reg.get_sota_model() is None

    def test_serialization_round_trip(self):
        reg = ModelRegistry()
        reg.register(CompositeModel(
            name="lgbm_v1", description="LGBM model",
            model_type="lgbm",
            features=["mom_5", "rev_20"],
            strategy_metrics=StrategyMetrics(annualized_return=0.15, calmar_ratio=1.2),
            status=SignalStatus.SOTA,
        ))
        reg.mark_sota("lgbm_v1")

        data = reg.to_dict()
        restored = ModelRegistry.from_dict(data)

        assert restored.total_count == 1
        sota = restored.get_sota_model()
        assert sota is not None
        assert sota.name == "lgbm_v1"
        assert sota.model_type == "lgbm"
        assert sota.features == ["mom_5", "rev_20"]
        assert sota.strategy_metrics.annualized_return == 0.15
        assert sota.strategy_metrics.calmar_ratio == 1.2


# ──────────────────────────────────────────────
# Strategy
# ──────────────────────────────────────────────


class TestStrategy:
    def test_empty_strategy(self):
        s = Strategy()
        assert s.total_rounds == 0
        assert s.last_experiment is None
        assert s.alpha_pool.total_count == 0
        assert s.model_registry.total_count == 0
        assert s.reports == []

    def test_serialization_round_trip(self):
        s = Strategy(description="Test strategy", status="active")
        s.alpha_pool.add(RawFactor(
            name="mom_5", description="",
            status=SignalStatus.SOTA,
            factor_metrics=FactorMetrics(ic=0.05),
        ))
        s.alpha_pool.mark_sota("mom_5")
        s.model_registry.register(CompositeModel(
            name="lgbm_v1", description="", model_type="lgbm",
        ))
        s.model_registry.mark_sota("lgbm_v1")
        s.experiments.append(Experiment(
            round_number=1, type="alpha",
            produced_alpha_names=["mom_5"],
            decision=True,
        ))

        data = s.to_dict()
        restored = Strategy.from_dict(data)

        assert restored.description == "Test strategy"
        assert restored.status == "active"
        assert restored.alpha_pool.total_count == 1
        assert restored.alpha_pool.is_sota("mom_5")
        assert restored.alpha_pool.get("mom_5").factor_metrics.ic == 0.05
        assert restored.model_registry.total_count == 1
        assert restored.model_registry.get_sota_model().name == "lgbm_v1"
        assert len(restored.experiments) == 1
        assert restored.experiments[0].round_number == 1
        assert restored.experiments[0].produced_alpha_names == ["mom_5"]

    def test_last_experiment(self):
        s = Strategy()
        assert s.last_experiment is None
        s.experiments.append(Experiment(round_number=1, type="alpha"))
        s.experiments.append(Experiment(round_number=2, type="model"))
        assert s.last_experiment.round_number == 2


# ──────────────────────────────────────────────
# Report
# ──────────────────────────────────────────────


class TestReport:
    def test_serialization_round_trip(self):
        r = Report(
            description="Test report",
            alpha_pool_snapshot=[
                RawFactor(name="mom_5", description="", status=SignalStatus.SOTA),
            ],
            model_snapshot=CompositeModel(name="lgbm_v1", description="", model_type="lgbm"),
            summary_text="Round 5 summary",
        )
        data = r.to_dict()
        restored = Report.from_dict(data)
        assert restored.description == "Test report"
        assert len(restored.alpha_pool_snapshot) == 1
        assert restored.alpha_pool_snapshot[0].name == "mom_5"
        assert restored.model_snapshot is not None
        assert restored.model_snapshot.name == "lgbm_v1"
        assert restored.summary_text == "Round 5 summary"

    def test_empty_report(self):
        r = Report()
        data = r.to_dict()
        restored = Report.from_dict(data)
        assert restored.alpha_pool_snapshot == []
        assert restored.model_snapshot is None


# ──────────────────────────────────────────────
# QlibBacktestExecutor
# ──────────────────────────────────────────────


class TestBacktestExecutor:
    def test_extract_epoch_logs_with_matches(self):
        from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
        executor = QlibBacktestExecutor()
        log = """
Epoch1: train -0.123, valid -0.456
some other log line
Epoch2: train -0.234, valid -0.567
best score: -0.100 @ 3 epoch
"""
        extracted = executor.extract_epoch_logs(log)
        assert "Epoch1: train -0.123, valid -0.456" in extracted
        assert "Epoch2: train -0.234, valid -0.567" in extracted
        assert "best score: -0.100 @ 3 epoch" in extracted
        assert "some other log line" not in extracted

    def test_extract_epoch_logs_no_matches(self):
        from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
        executor = QlibBacktestExecutor()
        log = "some random output\nno match here"
        extracted = executor.extract_epoch_logs(log)
        # Returns the original string when no matches found
        assert extracted == log

    def test_extract_epoch_logs_empty(self):
        from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
        executor = QlibBacktestExecutor()
        assert executor.extract_epoch_logs("") == ""

    def test_build_env_to_use(self):
        from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
        executor = QlibBacktestExecutor()
        env = executor.build_env_to_use(
            train_start="2008-01-01",
            train_end="2014-12-31",
            valid_start="2015-01-01",
            valid_end="2016-12-31",
            test_start="2017-01-01",
            test_end="2024-12-31",
            feature_names=["open", "close"],
            feature_expressions=["$open", "$close"],
            extra={"model_selector": "lgbm"},
        )
        assert env["PYTHONPATH"] == "./"
        assert env["train_start"] == "2008-01-01"
        assert env["feature_names"] == "['open', 'close']"
        assert env["model_selector"] == "lgbm"
        assert env["test_end"] == "2024-12-31"

    def test_build_env_to_use_no_test_end(self):
        from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
        executor = QlibBacktestExecutor()
        env = executor.build_env_to_use(
            train_start="2008-01-01",
            train_end="2014-12-31",
            valid_start="2015-01-01",
            valid_end="2016-12-31",
            test_start="2017-01-01",
            feature_names=[],
            feature_expressions=[],
        )
        assert "test_end" not in env

    def test_save_combined_factors_with_multiindex(self, tmp_path):
        from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
        executor = QlibBacktestExecutor()

        # Use a simple mock with workspace_path attribute
        class MockWorkspace:
            workspace_path = tmp_path

        ws = MockWorkspace()

        df = pd.DataFrame(
            {"col1": [1.0, 2.0], "col2": [3.0, 4.0]},
            index=pd.MultiIndex.from_tuples([("2020-01-01", "stock_a"), ("2020-01-02", "stock_b")]),
        )
        path = executor.save_combined_factors(ws, df)
        assert path.exists()
        assert path.name == "combined_factors_df.parquet"

        restored = pd.read_parquet(path, engine="pyarrow")
        assert restored.shape == (2, 2)
        # parquet round-trip preserves MultiIndex structure but not names
        assert "feature" in str(restored.columns)

    def test_save_combined_factors_with_singleindex(self, tmp_path):
        from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
        executor = QlibBacktestExecutor()

        class MockWorkspace:
            workspace_path = tmp_path

        ws = MockWorkspace()

        df = pd.DataFrame(
            {"mom_5": [0.1, 0.2], "rev_20": [0.3, 0.4]},
            index=pd.MultiIndex.from_tuples([("2020-01-01", "stock_a"), ("2020-01-02", "stock_b")]),
        )
        path = executor.save_combined_factors(ws, df)
        restored = pd.read_parquet(path, engine="pyarrow")
        assert restored.shape == (2, 2)
        assert "feature" in str(restored.columns)