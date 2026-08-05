"""
Quant research orchestration layer.

Manages the factor/model alternating loop, decision strategy, and
cross-domain knowledge sharing.
"""

from rdagent.scenarios.qlib.orchestrator.scheduler import (
    BanditScheduler,
    LLMScheduler,
    RandomScheduler,
    Scheduler,
)

__all__ = [
    "Scheduler",
    "BanditScheduler",
    "LLMScheduler",
    "RandomScheduler",
]