import pandas as pd

from rdagent.app.qlib_rd_loop.conf import ModelBasePropSetting
from rdagent.components.runner import CachedRunner
from rdagent.core.conf import RD_AGENT_SETTINGS
from rdagent.core.exception import ModelEmptyError
from rdagent.core.utils import cache_with_pickle
from rdagent.log import rdagent_logger as logger
from rdagent.scenarios.qlib.developer.utils import _build_sota_factor_df
from rdagent.scenarios.qlib.domain import CompositeModel, SignalStatus, StrategyMetrics
from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
from rdagent.scenarios.qlib.experiment.model_experiment import QlibModelExperiment

executor = QlibBacktestExecutor()


class QlibModelRunner(CachedRunner[QlibModelExperiment]):
    """
    Docker run
    Everything in a folder
    - config.yaml
    - Pytorch `model.py`
    - results in `mlflow`

    https://github.com/microsoft/qlib/blob/main/qlib/contrib/model/pytorch_nn.py
    - pt_model_uri:  hard-code `model.py:Net` in the config
    - let LLM modify model.py

    Optionally accepts a ``strategy`` (domain.Strategy) to manage the
    model registry explicitly, replacing the based_experiments[-1] pattern.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.strategy = None  # set by the loop; used for SignalPool / ModelRegistry
        self.strategy_id = None  # set by the loop; used to query research.db

    @cache_with_pickle(CachedRunner.get_cache_key, CachedRunner.assign_cached_result)
    def develop(self, exp: QlibModelExperiment) -> QlibModelExperiment:
        executor.ensure_baseline_executed(exp, self.develop)

        exist_sota_factor_exp = False
        sota_factor_df = _build_sota_factor_df(self.strategy_id, exp)

        if sota_factor_df is not None and not sota_factor_df.empty:
            exist_sota_factor_exp = True
            combined_factors = sota_factor_df
            executor.save_combined_factors(exp.experiment_workspace, combined_factors)
            # Model trains only on the session's pooled factors — clear the
            # ALPHA20 base features so conf_combined_factors_model.yaml uses
            # the pool as the sole feature source (matches fin_model's
            # factor-pool-downstream behavior).
            exp.base_features = {}
            num_features = str(len(combined_factors.columns))

        # Python-code 因子池:base_features 为空,features 全来自 combined_factors_df.parquet。
        # 此时用 conf_combined_factors_model.yaml(label-only QlibDataLoader + StaticDataLoader),
        # 避免 conf_sota_factors_model.yaml 里 Alpha158DL 对空 feature 抛 "fields cannot be empty"。
        combined_only = exist_sota_factor_exp  # base_features cleared when a pool is present
        sota_config = "conf_combined_factors_model.yaml" if combined_only else "conf_sota_factors_model.yaml"

        if exp.sub_workspace_list[0].file_dict.get("model.py") is None:
            raise ModelEmptyError("model.py is empty")
        exp.experiment_workspace.inject_files(**{"model.py": exp.sub_workspace_list[0].file_dict["model.py"]})

        mbps = ModelBasePropSetting()
        env_to_use = executor.build_env_to_use(
            train_start=mbps.train_start,
            train_end=mbps.train_end,
            valid_start=mbps.valid_start,
            valid_end=mbps.valid_end,
            test_start=mbps.test_start,
            test_end=mbps.test_end,
            feature_names=list(exp.base_features.keys()),
            feature_expressions=list(exp.base_features.values()),
        )

        training_hyperparameters = exp.sub_tasks[0].training_hyperparameters
        if training_hyperparameters:
            env_to_use.update(
                {
                    # 硬编码 n_epochs=3:LLM 常提议 ≥100 epoch,在 474K 样本上每 epoch ~5min,
                    # 远超 Docker running_timeout_period=3600s 被 kill(见 QLIB_SCENARIOS §7.4)。
                    # 固定 3 epoch 保证模型轮能在超时内真正跑完产出 SOTA 模型。
                    "n_epochs": "3",
                    "lr": str(training_hyperparameters.get("lr", "2e-4")),
                    "early_stop": str(training_hyperparameters.get("early_stop", 10)),
                    "batch_size": str(training_hyperparameters.get("batch_size", 256)),
                    "weight_decay": str(training_hyperparameters.get("weight_decay", 0.0001)),
                }
            )

        logger.info(f"start to run {exp.sub_tasks[0].name} model")
        if exp.sub_tasks[0].model_type == "TimeSeries":
            if exist_sota_factor_exp:
                env_to_use.update(
                    {"dataset_cls": "TSDatasetH", "num_features": num_features, "step_len": 20, "num_timesteps": 20}
                )
                result, stdout = executor.execute_and_parse(
                    exp.experiment_workspace,
                    qlib_config_name=sota_config,
                    run_env=env_to_use,
                )
            else:
                env_to_use.update({"dataset_cls": "TSDatasetH", "step_len": 20, "num_timesteps": 20})
                result, stdout = executor.execute_and_parse(
                    exp.experiment_workspace,
                    qlib_config_name="conf_baseline_factors_model.yaml",
                    run_env=env_to_use,
                )
        elif exp.sub_tasks[0].model_type == "Tabular":
            if exist_sota_factor_exp:
                env_to_use.update({"dataset_cls": "DatasetH", "num_features": num_features})
                result, stdout = executor.execute_and_parse(
                    exp.experiment_workspace,
                    qlib_config_name=sota_config,
                    run_env=env_to_use,
                )
            else:
                env_to_use.update({"dataset_cls": "DatasetH"})
                result, stdout = executor.execute_and_parse(
                    exp.experiment_workspace,
                    qlib_config_name="conf_baseline_factors_model.yaml",
                    run_env=env_to_use,
                )

        exp.result = result
        exp.stdout = stdout

        if result is None:
            logger.error(f"Failed to run {exp.sub_tasks[0].name}, because {stdout}")
            raise ModelEmptyError(f"Failed to run {exp.sub_tasks[0].name} model, because {stdout}")

        # ── Register new model into ModelRegistry (if strategy is available) ──
        if self.strategy is not None and exp.sub_tasks:
            task = exp.sub_tasks[0]
            sm = StrategyMetrics.from_result_dict(result)
            model = CompositeModel(
                name=task.name,
                description=task.description,
                status=SignalStatus.SOTA,
                strategy_metrics=sm,
                model_type=task.model_type,
                features=list(exp.base_features.keys()),
                hyperparameters=task.hyperparameters if hasattr(task, 'hyperparameters') else {},
                training_hyperparameters=task.training_hyperparameters if hasattr(task, 'training_hyperparameters') else {},
                code=exp.sub_workspace_list[0].file_dict.get("model.py", "") if exp.sub_workspace_list else "",
                round_number=len(self.strategy.experiments) + 1,
            )
            self.strategy.model_registry.register(model)
            self.strategy.model_registry.mark_sota(task.name)

        return exp
