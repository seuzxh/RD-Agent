import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Tuple

import numpy as np

from rdagent.scenarios.qlib.domain import FactorMetrics, StrategyMetrics
from rdagent.scenarios.qlib.orchestrator.scheduler import LinearThompsonTwoArm


@dataclass
class Metrics:
    ic: float = 0.0
    icir: float = 0.0
    rank_ic: float = 0.0
    rank_icir: float = 0.0
    arr: float = 0.0
    ir: float = 0.0
    mdd: float = 0.0
    sharpe: float = 0.0

    def as_vector(self) -> np.ndarray:
        return np.array(
            [
                self.ic,
                self.icir,
                self.rank_ic,
                self.rank_icir,
                self.arr,
                self.ir,
                -self.mdd,
                self.sharpe,
            ]
        )


def extract_metrics_from_experiment(experiment) -> Metrics:
    """Extract metrics from experiment feedback using structured domain models."""
    try:
        result = experiment.result
        fm = FactorMetrics.from_result_dict(result)
        sm = StrategyMetrics.from_result_dict(result)
        sharpe = sm.annualized_return / max(-sm.max_drawdown, 1e-6) if sm.max_drawdown < 0 else 0.0

        return Metrics(
            ic=fm.ic, icir=fm.icir, rank_ic=fm.rank_ic, rank_icir=fm.rank_icir,
            arr=sm.annualized_return, ir=sm.information_ratio,
            mdd=sm.max_drawdown, sharpe=sharpe,
        )
    except Exception as e:
        print(f"Error extracting metrics: {e}")
        return Metrics()


class EnvController:
    """
    Deprecated: Use BanditScheduler from `rdagent.scenarios.qlib.orchestrator` instead.

    Kept for backward compatibility with existing pickle/session files.
    """

    def __init__(self, weights: Tuple[float, ...] = None) -> None:
        self.weights = np.asarray(weights or (0.1, 0.1, 0.05, 0.05, 0.25, 0.15, 0.1, 0.2))
        self.bandit = LinearThompsonTwoArm(dim=8, prior_var=10.0, noise_var=0.5)

    def reward(self, m: Metrics) -> float:
        return float(np.dot(self.weights, m.as_vector()))

    def decide(self, m: Metrics) -> str:
        x = m.as_vector()
        return self.bandit.next_arm(x)

    def record(self, m: Metrics, arm: str) -> None:
        r = self.reward(m)
        self.bandit.update(arm, m.as_vector(), r)
