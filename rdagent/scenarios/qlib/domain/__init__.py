"""
Domain model for the quant research workflow.

Core entities:
- AlphaSignal / RawFactor / CompositeModel: unified signal abstraction
- SignalPool: persistent factor library with dedup and SOTA tracking
- ModelRegistry: persistent model registry with comparison
- Experiment: single R&D loop iteration record
- Strategy: top-level container for a research session
- Report: point-in-time snapshot of Strategy state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, Field


def _normalize_keys(d: dict) -> dict:
    """Strip whitespace from dict keys (Qlib result keys sometimes have trailing spaces)."""
    return {k.strip(): v for k, v in d.items()}

__all__ = [
    "AlphaSignal", "RawFactor", "CompositeModel",
    "FactorMetrics", "StrategyMetrics",
    "SignalStatus", "SignalPool", "ModelRegistry",
    "Experiment", "Strategy", "Report",
]


# ──────────────────────────────────────────────
# 1. Structured Metrics (Pydantic for serialization)
# ──────────────────────────────────────────────


class FactorMetrics(BaseModel):
    """Lightweight factor-level evaluation metrics."""

    ic: float = 0.0
    icir: float = 0.0
    rank_ic: float = 0.0
    rank_icir: float = 0.0

    @classmethod
    def from_result_dict(cls, result: dict[str, float] | pd.Series | pd.DataFrame) -> "FactorMetrics":
        """Extract from a dict or DataFrame row with magic-string keys."""
        if isinstance(result, pd.DataFrame):
            result = result.iloc[:, 0] if result.shape[1] > 0 else result
        if isinstance(result, pd.Series):
            result = result.to_dict()
        result = _normalize_keys(result)
        return cls(
            ic=result.get("IC", 0.0),
            icir=result.get("ICIR", 0.0),
            rank_ic=result.get("Rank IC", 0.0),
            rank_icir=result.get("Rank ICIR", 0.0),
        )


class StrategyMetrics(BaseModel):
    """Full strategy-level evaluation metrics (from backtest)."""

    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    information_ratio: float = 0.0
    calmar_ratio: float = 0.0

    @classmethod
    def from_result_dict(cls, result: dict[str, float] | pd.Series | pd.DataFrame) -> "StrategyMetrics":
        if isinstance(result, pd.DataFrame):
            result = result.iloc[:, 0] if result.shape[1] > 0 else result
        if isinstance(result, pd.Series):
            result = result.to_dict()
        result = _normalize_keys(result)
        arr = result.get("1day.excess_return_with_cost.annualized_return", 0.0)
        mdd = result.get("1day.excess_return_with_cost.max_drawdown", 1.0)
        return cls(
            annualized_return=arr,
            max_drawdown=mdd,
            information_ratio=result.get("1day.excess_return_with_cost.information_ratio", 0.0),
            calmar_ratio=arr / max(abs(mdd), 1e-6),
        )

    @classmethod
    def important_metrics_keys(cls) -> list[str]:
        """Return the legacy magic-string keys for backwards compat."""
        return [
            "IC",
            "1day.excess_return_with_cost.annualized_return",
            "1day.excess_return_with_cost.information_ratio",
            "1day.excess_return_with_cost.max_drawdown",
        ]


# ──────────────────────────────────────────────
# 2. Signal Status
# ──────────────────────────────────────────────


class SignalStatus(str, Enum):
    SOTA = "sota"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    PENDING = "pending"


# ──────────────────────────────────────────────
# 3. AlphaSignal hierarchy
# ──────────────────────────────────────────────


@dataclass
class AlphaSignal:
    """Unified signal abstraction — base for both RawFactor and CompositeModel."""

    name: str
    description: str
    status: SignalStatus = SignalStatus.PENDING
    factor_metrics: Optional[FactorMetrics] = None
    strategy_metrics: Optional[StrategyMetrics] = None
    used_by_models: list[str] = field(default_factory=list)
    experiment_id: Optional[str] = None
    round_number: int = 0


@dataclass
class RawFactor(AlphaSignal):
    """A single alpha factor expressed as a Qlib expression."""

    expression: str = ""
    formulation: str = ""
    variables: dict[str, str] = field(default_factory=dict)
    code: str = ""
    resources: Optional[str] = None

    @property
    def signal_type(self) -> str:
        return "factor"


@dataclass
class CompositeModel(AlphaSignal):
    """A trained model (LGBM/NN/Linear) that combines multiple factor signals."""

    model_type: str = ""  # lgbm / nn / linear / xgboost / catboost
    features: list[str] = field(default_factory=list)
    hyperparameters: dict[str, str] = field(default_factory=dict)
    training_hyperparameters: dict[str, str] = field(default_factory=dict)
    code: str = ""

    @property
    def signal_type(self) -> str:
        return "model"


# ──────────────────────────────────────────────
# 4. SignalPool
# ──────────────────────────────────────────────


class SignalPool:
    """
    Persistent factor library.

    Manages the lifecycle of discovered factors:
    - add new factors (with dedup against SOTA)
    - mark/unmark SOTA
    - query by status
    """

    def __init__(self) -> None:
        self._factors: dict[str, RawFactor] = {}
        self._sota_names: set[str] = set()

    # ── query ──

    @property
    def all(self) -> list[RawFactor]:
        return list(self._factors.values())

    def get(self, name: str) -> Optional[RawFactor]:
        return self._factors.get(name)

    def get_sota_factors(self) -> list[RawFactor]:
        return [self._factors[n] for n in self._sota_names if n in self._factors]

    def get_by_status(self, status: SignalStatus) -> list[RawFactor]:
        return [f for f in self._factors.values() if f.status == status]

    def is_sota(self, name: str) -> bool:
        return name in self._sota_names

    @property
    def sota_count(self) -> int:
        return len(self._sota_names)

    @property
    def total_count(self) -> int:
        return len(self._factors)

    # ── mutation ──

    def add(self, factor: RawFactor) -> None:
        self._factors[factor.name] = factor

    def mark_sota(self, name: str) -> None:
        if name in self._factors:
            old_sota = self._factors[name]
            old_sota.status = SignalStatus.SOTA
            self._sota_names.add(name)

    def unmark_sota(self, name: str) -> None:
        self._sota_names.discard(name)
        if name in self._factors:
            self._factors[name].status = SignalStatus.ACTIVE

    def remove(self, name: str) -> None:
        self._sota_names.discard(name)
        self._factors.pop(name, None)

    # ── dedup ──

    def deduplicate(self, new_factors: list[RawFactor], ic_threshold: float = 0.99) -> list[RawFactor]:
        """
        Filter out new factors whose IC correlation with any SOTA factor exceeds threshold.
        Returns the deduplicated list. Deprecated factors are marked in-place.
        """
        if not new_factors or not self._sota_names:
            return new_factors

        sota_list = self.get_sota_factors()
        if not sota_list:
            return new_factors

        result: list[RawFactor] = []
        for nf in new_factors:
            is_dup = False
            for sf in sota_list:
                if nf.factor_metrics and sf.factor_metrics:
                    ic_corr = self._estimate_ic_correlation(nf.factor_metrics, sf.factor_metrics)
                    if ic_corr > ic_threshold:
                        is_dup = True
                        nf.status = SignalStatus.DEPRECATED
                        break
            if not is_dup:
                result.append(nf)
        return result

    @staticmethod
    def _estimate_ic_correlation(a: FactorMetrics, b: FactorMetrics) -> float:
        """
        Estimate IC correlation between two factors using their metric vectors.
        Used as a proxy when full factor-value data is not available.
        """
        import math

        va = [a.ic, a.icir, a.rank_ic, a.rank_icir]
        vb = [b.ic, b.icir, b.rank_ic, b.rank_icir]
        n = len(va)
        mean_a = sum(va) / n
        mean_b = sum(vb) / n
        num = sum((va[i] - mean_a) * (vb[i] - mean_b) for i in range(n))
        den = math.sqrt(sum((va[i] - mean_a) ** 2 for i in range(n)) * sum((vb[i] - mean_b) ** 2 for i in range(n)))
        return num / den if den != 0 else 0.0

    # ── serialization ──

    def to_dict(self) -> dict:
        return {
            "factors": {name: _factor_to_dict(f) for name, f in self._factors.items()},
            "sota_names": list(self._sota_names),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignalPool":
        pool = cls()
        for name, fdata in data.get("factors", {}).items():
            pool._factors[name] = _factor_from_dict(fdata)
        pool._sota_names = set(data.get("sota_names", []))
        return pool


# ──────────────────────────────────────────────
# 5. ModelRegistry
# ──────────────────────────────────────────────


class ModelRegistry:
    """
    Persistent model registry.

    Tracks all trained models, their features, and SOTA status.
    """

    def __init__(self) -> None:
        self._models: dict[str, CompositeModel] = {}
        self._sota_name: Optional[str] = None

    # ── query ──

    @property
    def all(self) -> list[CompositeModel]:
        return list(self._models.values())

    def get(self, name: str) -> Optional[CompositeModel]:
        return self._models.get(name)

    def get_sota_model(self) -> Optional[CompositeModel]:
        if self._sota_name and self._sota_name in self._models:
            return self._models[self._sota_name]
        return None

    @property
    def total_count(self) -> int:
        return len(self._models)

    # ── mutation ──

    def register(self, model: CompositeModel) -> None:
        self._models[model.name] = model

    def mark_sota(self, name: str) -> None:
        if name in self._models:
            if self._sota_name and self._sota_name in self._models:
                self._models[self._sota_name].status = SignalStatus.ACTIVE
            self._sota_name = name
            self._models[name].status = SignalStatus.SOTA

    def remove(self, name: str) -> None:
        if self._sota_name == name:
            self._sota_name = None
        self._models.pop(name, None)

    # ── serialization ──

    def to_dict(self) -> dict:
        return {
            "models": {name: _model_to_dict(m) for name, m in self._models.items()},
            "sota_name": self._sota_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelRegistry":
        reg = cls()
        for name, mdata in data.get("models", {}).items():
            reg._models[name] = _model_from_dict(mdata)
        reg._sota_name = data.get("sota_name")
        return reg


# ──────────────────────────────────────────────
# 6. Experiment (tracking record)
# ──────────────────────────────────────────────


@dataclass
class Experiment:
    """
    A single R&D loop iteration record.

    Links together: which round, what type, what it produced, evaluation results.
    """

    round_number: int
    type: str  # "alpha" or "model"
    hypothesis: Optional[str] = None
    hypothesis_text: str = ""
    produced_alpha_names: list[str] = field(default_factory=list)
    produced_model_name: Optional[str] = None
    factor_metrics: Optional[FactorMetrics] = None
    strategy_metrics: Optional[StrategyMetrics] = None
    decision: bool = False
    workspace_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    status: str = "completed"  # completed / failed / skipped
    error_message: str = ""


# ──────────────────────────────────────────────
# 7. Strategy (top-level container)
# ──────────────────────────────────────────────


@dataclass
class Strategy:
    """
    Top-level container for a quant research session.

    Owns all artifacts: factor pool, model registry, experiment history, reports.
    """

    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "active"  # active / completed

    alpha_pool: SignalPool = field(default_factory=SignalPool)
    model_registry: ModelRegistry = field(default_factory=ModelRegistry)

    experiments: list[Experiment] = field(default_factory=list)
    reports: list[Report] = field(default_factory=list)

    @property
    def total_rounds(self) -> int:
        return len(self.experiments)

    @property
    def last_experiment(self) -> Optional[Experiment]:
        return self.experiments[-1] if self.experiments else None

    # ── serialization ──

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "alpha_pool": self.alpha_pool.to_dict(),
            "model_registry": self.model_registry.to_dict(),
            "experiments": [
                {
                    "round_number": e.round_number,
                    "type": e.type,
                    "hypothesis_text": e.hypothesis_text,
                    "produced_alpha_names": e.produced_alpha_names,
                    "produced_model_name": e.produced_model_name,
                    "factor_metrics": e.factor_metrics.model_dump() if e.factor_metrics else None,
                    "strategy_metrics": e.strategy_metrics.model_dump() if e.strategy_metrics else None,
                    "decision": e.decision,
                    "workspace_path": e.workspace_path,
                    "timestamp": e.timestamp.isoformat(),
                    "status": e.status,
                    "error_message": e.error_message,
                }
                for e in self.experiments
            ],
            "reports": [r.to_dict() for r in self.reports],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Strategy":
        s = cls(
            description=data.get("description", ""),
            status=data.get("status", "active"),
        )
        if "created_at" in data:
            try:
                s.created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                pass
        if "alpha_pool" in data:
            s.alpha_pool = SignalPool.from_dict(data["alpha_pool"])
        if "model_registry" in data:
            s.model_registry = ModelRegistry.from_dict(data["model_registry"])
        for edata in data.get("experiments", []):
            fm = FactorMetrics(**edata["factor_metrics"]) if edata.get("factor_metrics") else None
            sm = StrategyMetrics(**edata["strategy_metrics"]) if edata.get("strategy_metrics") else None
            ts = datetime.now()
            if "timestamp" in edata:
                try:
                    ts = datetime.fromisoformat(edata["timestamp"])
                except (ValueError, TypeError):
                    pass
            s.experiments.append(
                Experiment(
                    round_number=edata.get("round_number", 0),
                    type=edata.get("type", ""),
                    hypothesis_text=edata.get("hypothesis_text", ""),
                    produced_alpha_names=edata.get("produced_alpha_names", []),
                    produced_model_name=edata.get("produced_model_name"),
                    factor_metrics=fm,
                    strategy_metrics=sm,
                    decision=edata.get("decision", False),
                    workspace_path=edata.get("workspace_path"),
                    timestamp=ts,
                    status=edata.get("status", "completed"),
                    error_message=edata.get("error_message", ""),
                )
            )
        for rdata in data.get("reports", []):
            s.reports.append(Report.from_dict(rdata))
        return s


# ──────────────────────────────────────────────
# 8. Report (point-in-time snapshot)
# ──────────────────────────────────────────────


@dataclass
class Report:
    """A point-in-time snapshot of Strategy state."""

    snapshot_time: datetime = field(default_factory=datetime.now)
    description: str = ""

    alpha_pool_snapshot: list[RawFactor] = field(default_factory=list)
    model_snapshot: Optional[CompositeModel] = None
    metrics_history: list[dict[str, float]] = field(default_factory=list)

    # Computed summary
    summary_text: str = ""

    def to_dict(self) -> dict:
        return {
            "snapshot_time": self.snapshot_time.isoformat(),
            "description": self.description,
            "alpha_pool_snapshot": [_factor_to_dict(f) for f in self.alpha_pool_snapshot],
            "model_snapshot": _model_to_dict(self.model_snapshot) if self.model_snapshot else None,
            "metrics_history": self.metrics_history,
            "summary_text": self.summary_text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Report":
        r = cls(
            snapshot_time=datetime.now(),
            description=data.get("description", ""),
            summary_text=data.get("summary_text", ""),
            metrics_history=data.get("metrics_history", []),
        )
        if "snapshot_time" in data:
            try:
                r.snapshot_time = datetime.fromisoformat(data["snapshot_time"])
            except (ValueError, TypeError):
                pass
        if "alpha_pool_snapshot" in data:
            r.alpha_pool_snapshot = [_factor_from_dict(f) for f in data["alpha_pool_snapshot"]]
        if "model_snapshot" in data and data["model_snapshot"]:
            r.model_snapshot = _model_from_dict(data["model_snapshot"])
        return r


# ──────────────────────────────────────────────
# Serialization helpers
# ──────────────────────────────────────────────


def _factor_to_dict(f: RawFactor) -> dict:
    return {
        "name": f.name,
        "description": f.description,
        "status": f.status.value,
        "factor_metrics": f.factor_metrics.model_dump() if f.factor_metrics else None,
        "strategy_metrics": f.strategy_metrics.model_dump() if f.strategy_metrics else None,
        "used_by_models": f.used_by_models,
        "experiment_id": f.experiment_id,
        "round_number": f.round_number,
        "expression": f.expression,
        "formulation": f.formulation,
        "variables": f.variables,
        "code": f.code,
        "resources": f.resources,
    }


def _factor_from_dict(data: dict) -> RawFactor:
    fm = FactorMetrics(**data["factor_metrics"]) if data.get("factor_metrics") else None
    sm = StrategyMetrics(**data["strategy_metrics"]) if data.get("strategy_metrics") else None
    return RawFactor(
        name=data.get("name", ""),
        description=data.get("description", ""),
        status=SignalStatus(data.get("status", "pending")),
        factor_metrics=fm,
        strategy_metrics=sm,
        used_by_models=data.get("used_by_models", []),
        experiment_id=data.get("experiment_id"),
        round_number=data.get("round_number", 0),
        expression=data.get("expression", ""),
        formulation=data.get("formulation", ""),
        variables=data.get("variables", {}),
        code=data.get("code", ""),
        resources=data.get("resources"),
    )


def _model_to_dict(m: CompositeModel) -> dict:
    return {
        "name": m.name,
        "description": m.description,
        "status": m.status.value,
        "factor_metrics": m.factor_metrics.model_dump() if m.factor_metrics else None,
        "strategy_metrics": m.strategy_metrics.model_dump() if m.strategy_metrics else None,
        "used_by_models": m.used_by_models,
        "experiment_id": m.experiment_id,
        "round_number": m.round_number,
        "model_type": m.model_type,
        "features": m.features,
        "hyperparameters": m.hyperparameters,
        "training_hyperparameters": m.training_hyperparameters,
        "code": m.code,
    }


def _model_from_dict(data: dict) -> CompositeModel:
    fm = FactorMetrics(**data["factor_metrics"]) if data.get("factor_metrics") else None
    sm = StrategyMetrics(**data["strategy_metrics"]) if data.get("strategy_metrics") else None
    return CompositeModel(
        name=data.get("name", ""),
        description=data.get("description", ""),
        status=SignalStatus(data.get("status", "pending")),
        factor_metrics=fm,
        strategy_metrics=sm,
        used_by_models=data.get("used_by_models", []),
        experiment_id=data.get("experiment_id"),
        round_number=data.get("round_number", 0),
        model_type=data.get("model_type", ""),
        features=data.get("features", []),
        hyperparameters=data.get("hyperparameters", {}),
        training_hyperparameters=data.get("training_hyperparameters", {}),
        code=data.get("code", ""),
    )