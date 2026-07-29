"""
Model workflow with session control
"""

import asyncio
from typing import Optional

import fire

from rdagent.app.qlib_rd_loop.conf import MODEL_PROP_SETTING
from rdagent.components.workflow.rd_loop import RDLoop
from rdagent.core.exception import ModelEmptyError


class ModelRDLoop(RDLoop):
    skip_loop_error = (ModelEmptyError,)


def main(
    path: Optional[str] = None,
    step_n: Optional[int] = None,
    loop_n: Optional[int] = None,
    all_duration: str | None = None,
    checkout: bool = True,
    base_features_path: Optional[str] = None,
    description: Optional[str] = None,
    **kwargs,
):
    """
    Auto R&D Evolving loop for fintech models

    You can continue running session by

    .. code-block:: python

        dotenv run -- python rdagent/app/qlib_rd_loop/model.py $LOG_PATH/__session__/1/0_propose  --step_n 1   # `step_n` is a optional paramter

    """
    if path is None:
        model_loop = ModelRDLoop(MODEL_PROP_SETTING)
    else:
        model_loop = ModelRDLoop.load(path, checkout=checkout)
    model_loop._init_base_features(base_features_path)

    auto_mode = kwargs.get("auto_mode", False)
    has_queues = "user_interaction_queues" in kwargs and kwargs["user_interaction_queues"] is not None

    if not auto_mode and has_queues:
        model_loop._set_interactor(*kwargs["user_interaction_queues"])

    if description:
        model_loop.plan["user_instruction"] = description
    elif not auto_mode and hasattr(model_loop, "user_request_q"):
        model_loop._interact_init_params()

    asyncio.run(model_loop.run(step_n=step_n, loop_n=loop_n, all_duration=all_duration))


if __name__ == "__main__":
    fire.Fire(main)
