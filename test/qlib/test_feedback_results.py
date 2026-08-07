"""Tests for process_results (feedback formatting) in the Qlib factor scenario.

Covers the two-column (current + SOTA) format, the first-loop no-SOTA case that
previously crashed with KeyError, and the Real-format Series (Name: 0) input.
"""

import pandas as pd
import pytest

from rdagent.scenarios.qlib.developer.feedback import process_results
from rdagent.scenarios.qlib.domain import StrategyMetrics


def _current_series():
    """Reproduce the real format: a pd.Series with index=metric, Name: 0."""
    return pd.Series(
        {
            "IC": 0.052,
            "1day.excess_return_with_cost.annualized_return": 0.153,
            "1day.excess_return_with_cost.information_ratio": 0.72,
            "1day.excess_return_with_cost.max_drawdown": -0.085,
        },
        name=0,
    )


def test_process_results_with_sota():
    current = _current_series()
    sota = _current_series().copy()
    sota["IC"] = 0.04
    out = process_results(current, sota)
    assert ", of SOTA Result is" in out
    assert "IC of Current Result is 0.052000, of SOTA Result is 0.040000" in out


def test_process_results_no_sota():
    """sota_result=None (first loop) must not raise and reports only current."""
    current = _current_series()
    out = process_results(current, None)
    assert "Current Result" in out
    assert "SOTA Result" not in out
    assert "IC of Current Result is 0.052000" in out


def test_process_results_series_name_0():
    """Current result is a Name:0 Series (real pickle format) — must not crash."""
    current = _current_series()
    out = process_results(current, None)
    assert "Current Result" in out


def test_process_results_important_keys_filter():
    """Only metrics in important_metrics_keys() are reported."""
    current = pd.Series(
        {
            "IC": 0.03,
            "some_other_metric": 0.99,
        },
        name=0,
    )
    out = process_results(current, None)
    assert "IC of Current Result is 0.030000" in out
    assert "some_other_metric" not in out