"""Tests for QlibFactorRunner gate: custom factors (sub_tasks) drive the
combined backtest regardless of base_feature_codes."""

import pandas as pd
import pytest

from rdagent.components.coder.factor_coder.factor import FactorTask
from rdagent.core.conf import RD_AGENT_SETTINGS
from rdagent.scenarios.qlib.developer import factor_runner as fr
from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorExperiment, QlibFactorScenario


def _make_exp(sub_tasks, base_feature_codes=None):
    exp = QlibFactorExperiment(sub_tasks, hypothesis=None)
    exp.base_feature_codes = base_feature_codes if base_feature_codes is not None else {}
    return exp


@pytest.fixture(autouse=True)
def _patch_executor(monkeypatch):
    """Avoid Docker/Qlib and the pickle cache: record the config chosen, stub combined save."""
    monkeypatch.setattr(RD_AGENT_SETTINGS, "cache_with_pickle", False)
    calls = {"configs": []}

    def fake_execute(workspace, qlib_config_name, run_env):
        calls["configs"].append(qlib_config_name)
        # Return a minimal result Series so metrics extraction works.
        return pd.Series({"IC": 0.05, "ICIR": 0.5}), "fake stdout"

    monkeypatch.setattr(fr.executor, "execute_and_parse", fake_execute)
    monkeypatch.setattr(fr.executor, "ensure_baseline_executed", lambda *a, **k: None)
    monkeypatch.setattr(fr.executor, "save_combined_factors", lambda *a, **k: None)
    monkeypatch.setattr(fr, "process_factor_data", lambda exp: pd.DataFrame({"f": [1.0, 2.0]}))
    monkeypatch.setattr(fr, "_build_sota_factor_df", lambda strategy, exp: None)
    return calls


def test_custom_subtasks_without_base_codes_uses_combined(monkeypatch, _patch_executor):
    """Non-empty sub_tasks + empty base_feature_codes → combined backtest."""
    task = FactorTask(factor_name="f1", factor_description="d", factor_formulation="F")
    exp = _make_exp([task], base_feature_codes={})
    fr.QlibFactorRunner(QlibFactorScenario()).develop(exp)
    assert "conf_combined_factors.yaml" in _patch_executor["configs"]
    assert "conf_baseline.yaml" not in _patch_executor["configs"]


def test_no_subtasks_uses_baseline(monkeypatch, _patch_executor):
    """Empty sub_tasks → baseline backtest."""
    exp = _make_exp([], base_feature_codes={})
    fr.QlibFactorRunner(QlibFactorScenario()).develop(exp)
    assert "conf_baseline.yaml" in _patch_executor["configs"]
    assert "conf_combined_factors.yaml" not in _patch_executor["configs"]