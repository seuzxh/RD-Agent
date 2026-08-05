"""
Data extraction helpers for the artifact-based frontend.

Transforms the tag-based state.msgs data into research artifact views
(Alpha Lab, Model Lab, Strategy Dashboard, etc.).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

import pandas as pd
import streamlit as st

from rdagent.components.coder.factor_coder.evaluators import FactorSingleFeedback
from rdagent.components.coder.factor_coder.factor import FactorFBWorkspace, FactorTask
from rdagent.components.coder.model_coder.evaluators import ModelSingleFeedback
from rdagent.components.coder.model_coder.model import ModelFBWorkspace, ModelTask
from rdagent.core.proposal import Hypothesis, HypothesisFeedback
from rdagent.log.ui.qlib_report_figure import report_figure
from rdagent.scenarios.qlib.domain import (
    CompositeModel,
    FactorMetrics,
    RawFactor,
    SignalStatus,
    SignalPool,
    StrategyMetrics,
)
from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorExperiment
from rdagent.scenarios.qlib.experiment.model_experiment import QlibModelExperiment


def get_msgs():
    """Convenience accessor for the message store."""
    return st.session_state.msgs


def get_scenario():
    return st.session_state.get("scenario")


def get_rounds():
    """Return sorted list of round numbers with data."""
    msgs = get_msgs()
    return sorted([r for r in msgs.keys() if r > 0])


# ──────────────────────────────────────────────
# Factor extraction
# ──────────────────────────────────────────────


def extract_factors() -> SignalPool:
    """
    Iterate all rounds and extract discovered factors into a SignalPool.
    Uses the domain model's SignalPool for consistent state management.
    """
    pool = SignalPool()
    msgs = get_msgs()
    decisions = st.session_state.get("h_decisions", {})

    for rnd in get_rounds():
        # Get hypothesis generation tag for this round
        hg = msgs[rnd].get("hypothesis generation", [])
        eg = msgs[rnd].get("experiment generation", [])
        rr = msgs[rnd].get("runner result", [])
        fb = msgs[rnd].get("feedback", [])

        # Extract factors from experiment generation (FactorTask list)
        for msg in eg:
            if isinstance(msg.content, list) and msg.content and isinstance(msg.content[0], FactorTask):
                for task in msg.content:
                    alpha = RawFactor(
                        name=task.factor_name,
                        description=task.factor_description,
                        expression=task.factor_formulation,
                        formulation=task.factor_formulation,
                        variables=task.variables,
                        round_number=rnd,
                        status=SignalStatus.PENDING,
                    )
                    pool.add(alpha)

        # Extract metrics from runner result
        for msg in rr:
            exp = msg.content
            if isinstance(exp, QlibFactorExperiment) and exp.result is not None:
                fm = FactorMetrics.from_result_dict(exp.result)
                sm = StrategyMetrics.from_result_dict(exp.result)
                for task in exp.sub_tasks:
                    existing = pool.get(task.factor_name)
                    if existing:
                        existing.factor_metrics = fm
                        existing.strategy_metrics = sm
                        # Mark SOTA based on feedback decision
                        decision = decisions.get(rnd, False)
                        existing.status = SignalStatus.SOTA if decision else SignalStatus.ACTIVE
                        if decision:
                            pool.mark_sota(task.factor_name)

    return pool


# ──────────────────────────────────────────────
# Model extraction
# ──────────────────────────────────────────────


def extract_models() -> list[dict]:
    """Iterate all rounds and extract trained models."""
    models = []
    msgs = get_msgs()
    decisions = st.session_state.get("h_decisions", {})

    for rnd in get_rounds():
        rr = msgs[rnd].get("runner result", [])
        eg = msgs[rnd].get("experiment generation", [])

        for msg in rr:
            exp = msg.content
            if isinstance(exp, QlibModelExperiment) and exp.result is not None:
                sm = StrategyMetrics.from_result_dict(exp.result)
                task = exp.sub_tasks[0] if exp.sub_tasks else None
                if task is None:
                    continue
                decision = decisions.get(rnd, False)
                models.append({
                    "name": task.name,
                    "type": task.model_type,
                    "features": list(exp.base_features.keys()) if hasattr(exp, 'base_features') else [],
                    "sharpe": sm.information_ratio,
                    "annualized_return": sm.annualized_return,
                    "max_drawdown": sm.max_drawdown,
                    "calmar_ratio": sm.calmar_ratio,
                    "round": rnd,
                    "status": "SOTA" if decision else "active",
                    "experiment": exp,
                })

    return models


# ──────────────────────────────────────────────
# Metrics trend extraction
# ──────────────────────────────────────────────


def extract_metrics_trend() -> pd.DataFrame:
    """Extract IC, annualized_return, max_drawdown across rounds."""
    records = []
    msgs = get_msgs()

    for rnd in get_rounds():
        rr = msgs[rnd].get("runner result", [])
        for msg in rr:
            exp = msg.content
            if exp is not None and hasattr(exp, 'result') and exp.result is not None:
                try:
                    sm = StrategyMetrics.from_result_dict(exp.result)
                    fm = FactorMetrics.from_result_dict(exp.result)
                    records.append({
                        "round": rnd,
                        "IC": fm.ic,
                        "ICIR": fm.icir,
                        "Rank IC": fm.rank_ic,
                        "Annualized Return": sm.annualized_return,
                        "Max Drawdown": sm.max_drawdown,
                        "Information Ratio": sm.information_ratio,
                    })
                except Exception:
                    pass

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.set_index("round")
    return df


# ──────────────────────────────────────────────
# Hypothesis extraction
# ──────────────────────────────────────────────


def extract_hypotheses() -> list[dict]:
    """Extract hypothesis and feedback for each round."""
    items = []
    msgs = get_msgs()
    decisions = st.session_state.get("h_decisions", {})

    for rnd in get_rounds():
        hg = msgs[rnd].get("hypothesis generation", [])
        fb = msgs[rnd].get("feedback", [])

        hypothesis = hg[0].content if hg else None
        feedback = fb[0].content if fb else None

        items.append({
            "round": rnd,
            "hypothesis": hypothesis,
            "feedback": feedback,
            "decision": decisions.get(rnd, False),
        })

    return items


# ──────────────────────────────────────────────
# Backtest chart extraction
# ──────────────────────────────────────────────


def extract_backtest_charts(round_number: int) -> Optional[dict]:
    """Get the Quantitative Backtesting Chart for a specific round."""
    msgs = get_msgs()
    charts = msgs[round_number].get("Quantitative Backtesting Chart", [])
    return charts[0].content if charts else None


# ──────────────────────────────────────────────
# Factor task code extraction
# ──────────────────────────────────────────────


def get_factor_code(round_number: int, factor_name: str) -> Optional[str]:
    """Get the code for a specific factor from the evolving code messages."""
    msgs = get_msgs()
    for tag_key in msgs[round_number]:
        if "evolving code" in tag_key:
            for msg in msgs[round_number][tag_key]:
                if isinstance(msg.content, list):
                    for ws in msg.content:
                        if isinstance(ws, FactorFBWorkspace) and ws.target_task:
                            if ws.target_task.factor_name == factor_name:
                                return ws.file_dict.get("implement_factor.py", "")
    return None


def get_model_code(round_number: int) -> Optional[str]:
    """Get the model code for a specific round."""
    msgs = get_msgs()
    for tag_key in msgs[round_number]:
        if "evolving code" in tag_key:
            for msg in msgs[round_number][tag_key]:
                if isinstance(msg.content, list):
                    for ws in msg.content:
                        if isinstance(ws, ModelFBWorkspace):
                            return ws.file_dict.get("model.py", "")
    return None