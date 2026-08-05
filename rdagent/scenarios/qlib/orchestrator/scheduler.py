"""
Scheduler abstraction for quant research orchestration.

Defines the pluggable decision strategy interface used by QuantOrchestrator
to decide whether to explore new factors or train models.
"""

from __future__ import annotations

import json
import random
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from rdagent.core.proposal import Trace
from rdagent.oai.llm_utils import APIBackend
from rdagent.utils.agent.tpl import T


class Scheduler(ABC):
    """Abstract base for quant research decision strategies."""

    @abstractmethod
    def decide(self, trace: Trace) -> str:
        """
        Decide the next action: "factor" or "model".

        Args:
            trace: The experiment trace, which may contain historical
                   (experiment, feedback) pairs used for context.

        Returns:
            "factor" to explore new alpha factors, or "model" to train a model.
        """
        ...


# ──────────────────────────────────────────────
# BanditScheduler
# ──────────────────────────────────────────────


class BanditScheduler(Scheduler):
    """
    Contextual bandit (Linear Thompson Sampling) that decides between
    factor discovery and model training based on historical metrics.

    The bandit maintains a separate LinearThompsonTwoArm model for each
    action, using an 8-dimensional metric vector as context.
    """

    def __init__(
        self,
        weights: tuple[float, ...] | None = None,
        prior_var: float = 10.0,
        noise_var: float = 0.5,
    ) -> None:
        if weights is not None and len(weights) != 8:
            raise ValueError(f"BanditScheduler requires 8 weights, got {len(weights)}")
        self.weights = np.asarray(weights or (0.1, 0.1, 0.05, 0.05, 0.25, 0.15, 0.1, 0.2))
        self.bandit = LinearThompsonTwoArm(dim=8, prior_var=prior_var, noise_var=noise_var)

    def decide(self, trace: Trace) -> str:
        if len(trace.hist) == 0:
            return "factor"

        # Extract metrics from the last experiment
        from rdagent.scenarios.qlib.proposal.bandit import extract_metrics_from_experiment

        last_exp = trace.hist[-1][0]
        metric = extract_metrics_from_experiment(last_exp)
        prev_action = last_exp.hypothesis.action
        self.bandit.update(prev_action, metric.as_vector(), self._reward(metric))
        return self.bandit.next_arm(metric.as_vector())

    def _reward(self, m) -> float:
        return float(np.dot(self.weights, m.as_vector()))


# ──────────────────────────────────────────────
# LLMScheduler
# ──────────────────────────────────────────────


class LLMScheduler(Scheduler):
    """
    Uses an LLM to decide the next action based on the full trace context
    (hypotheses, experiment results, and feedback).
    """

    def decide(self, trace: Trace) -> str:
        hypothesis_and_feedback = (
            T("scenarios.qlib.prompts:hypothesis_and_feedback").r(trace=trace)
            if len(trace.hist) > 0
            else "No previous hypothesis and feedback available since it's the first round."
        )

        last_hypothesis_and_feedback = (
            T("scenarios.qlib.prompts:last_hypothesis_and_feedback").r(
                experiment=trace.hist[-1][0], feedback=trace.hist[-1][1]
            )
            if len(trace.hist) > 0
            else "No previous hypothesis and feedback available since it's the first round."
        )

        system_prompt = T("scenarios.qlib.prompts:action_gen.system").r()
        user_prompt = T("scenarios.qlib.prompts:action_gen.user").r(
            hypothesis_and_feedback=hypothesis_and_feedback,
            last_hypothesis_and_feedback=last_hypothesis_and_feedback,
        )
        resp = APIBackend().build_messages_and_create_chat_completion(user_prompt, system_prompt, json_mode=True)
        return json.loads(resp).get("action", "factor")


# ──────────────────────────────────────────────
# RandomScheduler
# ──────────────────────────────────────────────


class RandomScheduler(Scheduler):
    """Randomly chooses between factor and model."""

    def decide(self, trace: Trace) -> str:
        return random.choice(["factor", "model"])


# ──────────────────────────────────────────────
# Linear Thompson Sampling (two-armed bandit)
# ──────────────────────────────────────────────


class LinearThompsonTwoArm:
    """
    Linear Thompson Sampling for two arms ("factor" and "model").

    Each arm maintains its own posterior distribution over the weight
    vector w, with Gaussian likelihood and conjugate prior.
    """

    def __init__(self, dim: int, prior_var: float = 1.0, noise_var: float = 1.0):
        self.dim = dim
        self.noise_var = noise_var
        self.mean: dict[str, np.ndarray] = {
            "factor": np.zeros(dim),
            "model": np.zeros(dim),
        }
        self.precision: dict[str, np.ndarray] = {
            "factor": np.eye(dim) / prior_var,
            "model": np.eye(dim) / prior_var,
        }

    def sample_reward(self, arm: str, x: np.ndarray) -> float:
        P = self.precision[arm]
        P = 0.5 * (P + P.T)
        eps = 1e-6
        try:
            cov = np.linalg.inv(P + eps * np.eye(self.dim))
            L = np.linalg.cholesky(cov)
            z = np.random.randn(self.dim)
            w_sample = self.mean[arm] + L @ z
        except np.linalg.LinAlgError:
            w_sample = self.mean[arm]
        return float(np.dot(w_sample, x))

    def update(self, arm: str, x: np.ndarray, r: float) -> None:
        P = self.precision[arm]
        P += np.outer(x, x) / self.noise_var
        self.precision[arm] = P
        self.mean[arm] = np.linalg.solve(P, P @ self.mean[arm] + (r / self.noise_var) * x)

    def next_arm(self, x: np.ndarray) -> str:
        scores = {arm: self.sample_reward(arm, x) for arm in ("factor", "model")}
        return max(scores, key=scores.get)