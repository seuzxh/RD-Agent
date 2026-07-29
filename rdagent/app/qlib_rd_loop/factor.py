"""
Factor workflow with session control
"""

import asyncio
from pathlib import Path
from typing import Any, Optional

import fire

from rdagent.app.qlib_rd_loop.conf import FACTOR_PROP_SETTING
from rdagent.components.workflow.rd_loop import RDLoop
from rdagent.core.exception import CoderError, FactorEmptyError
from rdagent.log import rdagent_logger as logger


class FactorRDLoop(RDLoop):
    skip_loop_error = (FactorEmptyError, CoderError)
    skip_loop_error_stepname = "feedback"

    def running(self, prev_out: dict[str, Any]):
        exp = self.runner.develop(prev_out["coding"])
        if exp is None:
            logger.error(f"Factor extraction failed.")
            raise FactorEmptyError("Factor extraction failed.")
        logger.log_object(exp, tag="runner result")
        return exp


def main(
    path: Optional[str] = None,
    step_n: Optional[int] = None,
    loop_n: Optional[int] = None,
    all_duration: str | None = None,
    checkout: bool = True,
    checkout_path: Optional[str] = None,
    base_features_path: Optional[str] = None,
    description: Optional[str] = None,
    **kwargs,
):
    """
    Auto R&D Evolving loop for fintech factors.

    You can continue running session by

    .. code-block:: python

        dotenv run -- python rdagent/app/qlib_rd_loop/factor.py $LOG_PATH/__session__/1/0_propose  --step_n 1   # `step_n` is a optional paramter

    """
    if not checkout_path is None:
        checkout = Path(checkout_path)

    if path is None:
        factor_loop = FactorRDLoop(FACTOR_PROP_SETTING)
    else:
        factor_loop = FactorRDLoop.load(path, checkout=checkout)

    factor_loop._init_base_features(base_features_path)

    # Determine interaction mode:
    # - auto_mode=True → fully autonomous, no interaction at all (CLI-style)
    # - auto_mode=False (default) → interactive: user can review/edit
    #   hypothesis and feedback each loop
    auto_mode = kwargs.get("auto_mode", False)
    has_queues = "user_interaction_queues" in kwargs and kwargs["user_interaction_queues"] is not None

    if not auto_mode and has_queues:
        factor_loop._set_interactor(*kwargs["user_interaction_queues"])

    # description only affects init: if provided, use it as user_instruction
    # (skip the "what's your goal?" question); otherwise ask interactively
    if description:
        factor_loop.plan["user_instruction"] = description
    elif not auto_mode and hasattr(factor_loop, "user_request_q"):
        factor_loop._interact_init_params()

    asyncio.run(factor_loop.run(step_n=step_n, loop_n=loop_n, all_duration=all_duration))


if __name__ == "__main__":
    fire.Fire(main)
