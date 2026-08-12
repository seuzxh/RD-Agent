"""
Model workflow with session control
"""

import asyncio
from typing import Optional

import fire

from rdagent.app.qlib_rd_loop.conf import MODEL_PROP_SETTING
from rdagent.app.qlib_rd_loop.strategy_loader import load_parent_strategy
from rdagent.components.workflow.rd_loop import RDLoop
from rdagent.core.exception import ModelEmptyError
from rdagent.log import rdagent_logger as logger


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
    factor_pool_source: Optional[str] = None,
    factor_pool_names: Optional[str | list[str]] = None,
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

    # Factor-pool downstream: when a parent strategy is provided, replace the
    # ALPHA20 base features with the parent's factor pool and inject the
    # strategy so its model registry / SOTA branches activate.
    #
    # The dialog lets the user pick factors: by default the SOTA ones, or
    # manually when the parent has no SOTA. `factor_pool_names` carries that
    # explicit selection, so even non-SOTA factors are honored. Resolution
    # order: explicitly-selected names → parent's SOTA factors → ALPHA20.
    if factor_pool_source:
        parent = load_parent_strategy(factor_pool_source)
        if parent is not None:
            # Normalize factor_pool_names: a comma-separated string comes from
            # the /upload form; a list/set may come from a direct CLI call.
            if isinstance(factor_pool_names, str):
                names = [n.strip() for n in factor_pool_names.split(",") if n.strip()]
            elif factor_pool_names:
                names = list(factor_pool_names)
            else:
                names = None

            pool_factors = []
            if names:
                pool_factors = [
                    f for f in (parent.alpha_pool.get(n) for n in names) if f is not None
                ]
                if not pool_factors:
                    logger.warning(
                        f"No selected factors resolve in parent strategy '{factor_pool_source}'; falling back to SOTA."
                    )
            if not pool_factors:
                pool_factors = parent.alpha_pool.get_sota_factors()
            if pool_factors:
                model_loop.plan["features"] = {f.name: f.expression for f in pool_factors}
                model_loop.plan["feature_codes"] = {f.name: f.code for f in pool_factors}
            else:
                logger.warning(
                    f"No factors available in parent strategy '{factor_pool_source}'; keeping ALPHA20 baseline."
                )
            # Attach the explicit selection so the runner's _build_sota_factor_df
            # honors the dialog-picked factors (including non-SOTA ones) instead
            # of only SOTA. set_strategy propagates the same object to runner.
            parent.factor_pool_names = names
            model_loop._set_strategy(parent)
            # Record the parent association so the tracker routes the produced
            # model into the parent's Model Lab (strategy_id = 父策略).
            model_loop.parent_strategy_id = factor_pool_source
        else:
            logger.warning(f"Failed to load parent strategy '{factor_pool_source}'; using ALPHA20 baseline.")

    auto_mode = kwargs.get("auto_mode", False)
    has_queues = "user_interaction_queues" in kwargs and kwargs["user_interaction_queues"] is not None

    if not auto_mode and has_queues:
        model_loop._set_interactor(*kwargs["user_interaction_queues"])

    if description:
        model_loop.plan["user_instruction"] = description
    elif not auto_mode and hasattr(model_loop, "user_request_q"):
        model_loop._interact_init_params()

    try:
        asyncio.run(model_loop.run(step_n=step_n, loop_n=loop_n, all_duration=all_duration))
        model_loop.tracker.on_run_complete()
    except BaseException as e:
        model_loop.tracker.on_run_failed(e)
        raise


if __name__ == "__main__":
    fire.Fire(main)
