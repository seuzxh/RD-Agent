from pathlib import Path

import pandas as pd
from pandarallel import pandarallel

from rdagent.core.conf import RD_AGENT_SETTINGS
from rdagent.core.utils import cache_with_pickle

pandarallel.initialize(verbose=1)

from rdagent.app.qlib_rd_loop.conf import FactorBasePropSetting
from rdagent.components.runner import CachedRunner
from rdagent.core.exception import FactorEmptyError
from rdagent.log import rdagent_logger as logger
from rdagent.oai.llm_utils import md5_hash
from rdagent.scenarios.qlib.developer.utils import build_cumulative_factor_df, process_factor_data
from rdagent.scenarios.qlib.domain import FactorMetrics, RawFactor, SignalStatus
from rdagent.scenarios.qlib.evaluation import QlibBacktestExecutor
from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorExperiment
from rdagent.scenarios.qlib.experiment.model_experiment import QlibModelExperiment

DIRNAME = Path(__file__).absolute().resolve().parent
DIRNAME_local = Path.cwd()

# TODO: supporting multiprocessing and keep previous results

executor = QlibBacktestExecutor()


class QlibFactorRunner(CachedRunner[QlibFactorExperiment]):
    """
    Docker run
    Everything in a folder
    - config.yaml
    - price-volume data dumper
    - `data.py` + Adaptor to Factor implementation
    - results in `mlflow`

    Optionally accepts a ``strategy`` (domain.Strategy) to manage the
    factor pool and model registry explicitly, replacing the
    based_experiments[-1] magic index pattern.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.strategy = None  # set by the loop; used for SignalPool / ModelRegistry
        self.strategy_id = None  # set by the loop; used to query research.db

    def calculate_information_coefficient(
        self, concat_feature: pd.DataFrame, SOTA_feature_column_size: int, new_feature_columns_size: int
    ) -> pd.DataFrame:
        res = pd.Series(index=range(SOTA_feature_column_size * new_feature_columns_size))
        for col1 in range(SOTA_feature_column_size):
            for col2 in range(SOTA_feature_column_size, SOTA_feature_column_size + new_feature_columns_size):
                res.loc[col1 * new_feature_columns_size + col2 - SOTA_feature_column_size] = concat_feature.iloc[
                    :, col1
                ].corr(concat_feature.iloc[:, col2])
        return res

    def deduplicate_new_factors(self, SOTA_feature: pd.DataFrame, new_feature: pd.DataFrame) -> pd.DataFrame:
        concat_feature = pd.concat([SOTA_feature, new_feature], axis=1)
        IC_max = (
            concat_feature.groupby("datetime")
            .parallel_apply(
                lambda x: self.calculate_information_coefficient(x, SOTA_feature.shape[1], new_feature.shape[1])
            )
            .mean()
        )
        IC_max.index = pd.MultiIndex.from_product([range(SOTA_feature.shape[1]), range(new_feature.shape[1])])
        IC_max = IC_max.unstack().max(axis=0)
        return new_feature.iloc[:, IC_max[IC_max < 0.99].index]

    def _develop_cache_key(self, exp: QlibFactorExperiment) -> str:
        base_key = CachedRunner.get_cache_key(self, exp)
        selector = FactorBasePropSetting().model_selector
        return md5_hash(f"{base_key}\nmodel_selector={selector}")

    @cache_with_pickle(_develop_cache_key, CachedRunner.assign_cached_result)
    def develop(self, exp: QlibFactorExperiment) -> QlibFactorExperiment:
        executor.ensure_baseline_executed(exp, self.develop)

        fbps = FactorBasePropSetting()
        env_to_use = executor.build_env_to_use(
            train_start=fbps.train_start,
            train_end=fbps.train_end,
            valid_start=fbps.valid_start,
            valid_end=fbps.valid_end,
            test_start=fbps.test_start,
            test_end=fbps.test_end,
            feature_names=list(exp.base_features.keys()),
            feature_expressions=list(exp.base_features.values()),
            extra={"model_selector": fbps.model_selector},
        )

        # ── Accumulated session factors: from research.db + persisted parquet ──
        cumulative_factor_df = build_cumulative_factor_df(self.strategy_id)

        # ── Process new factors ──
        # Custom factors (sub_tasks) always drive the merged backtest; the
        # baseline config is used only when there are no custom factors to
        # evaluate. base_feature_codes are supplementary (merged via the
        # combined path), not a gate.
        if not exp.sub_tasks:
            logger.info("No custom factors (sub_tasks) to process, running baseline ...")
            # Always use conf_baseline.yaml in this path — conf_combined_factors.yaml
            # requires combined_factors_df.parquet to exist, but save_combined_factors
            # is only called in the new-factor processing path below.
            result, stdout = executor.execute_and_parse(
                exp.experiment_workspace,
                qlib_config_name="conf_baseline.yaml",
                run_env=env_to_use,
            )
            if result is not None:
                exp.result = result
                exp.stdout = stdout
            return exp

        logger.info("New factor processing ...")
        new_factors = process_factor_data(exp)

        if new_factors.empty:
            raise FactorEmptyError("Factors failed to run on the full sample, this round of experiment failed.")

        if cumulative_factor_df is not None and not cumulative_factor_df.empty:
            new_factors = self.deduplicate_new_factors(cumulative_factor_df, new_factors)
            if new_factors.empty:
                raise FactorEmptyError(
                    "The factors generated in this round are highly similar to the previous factors. Please change the direction for creating new factors."
                )

        # Each round persists only this round's deduplicated new factors; later
        # model rounds merge all rounds' parquets via build_cumulative_factor_df.
        executor.save_combined_factors(exp.experiment_workspace, new_factors)

        num_features = len(exp.base_features) + len(new_factors.columns) if hasattr(new_factors, 'columns') else 0

        # ── SOTA model: from ModelRegistry ──
        exist_sota_model_exp = False
        sota_model_exp = None
        if self.strategy is not None:
            sota_model = self.strategy.model_registry.get_sota_model()
            if sota_model is not None:
                for base_exp in exp.based_experiments:
                    if isinstance(base_exp, QlibModelExperiment) and base_exp.sub_tasks:
                        if base_exp.sub_tasks[0].name == sota_model.name:
                            sota_model_exp = base_exp
                            exist_sota_model_exp = True
                            break

        logger.info("Experiment execution ...")
        if exist_sota_model_exp and sota_model_exp is not None:
            exp.experiment_workspace.inject_files(
                **{"model.py": sota_model_exp.sub_workspace_list[0].file_dict["model.py"]}
            )
            sota_training_hyperparameters = sota_model_exp.sub_tasks[0].training_hyperparameters
            if sota_training_hyperparameters:
                env_to_use.update(
                    {
                        "n_epochs": str(sota_training_hyperparameters.get("n_epochs", "100")),
                        "lr": str(sota_training_hyperparameters.get("lr", "2e-4")),
                        "early_stop": str(sota_training_hyperparameters.get("early_stop", 10)),
                        "batch_size": str(sota_training_hyperparameters.get("batch_size", 256)),
                        "weight_decay": str(sota_training_hyperparameters.get("weight_decay", 0.0001)),
                    }
                )
            sota_model_type = sota_model_exp.sub_tasks[0].model_type
            if sota_model_type == "TimeSeries":
                env_to_use.update(
                    {"dataset_cls": "TSDatasetH", "num_features": num_features, "step_len": 20, "num_timesteps": 20}
                )
            elif sota_model_type == "Tabular":
                env_to_use.update({"dataset_cls": "DatasetH", "num_features": num_features})

            result, stdout = executor.execute_and_parse(
                exp.experiment_workspace,
                qlib_config_name="conf_combined_factors_sota_model.yaml",
                run_env=env_to_use,
            )
        else:
            result, stdout = executor.execute_and_parse(
                exp.experiment_workspace,
                qlib_config_name="conf_combined_factors.yaml",
                run_env=env_to_use,
            )

        if result is None:
            logger.error(f"Failed to run this experiment, because {stdout}")
            raise FactorEmptyError(f"Failed to run this experiment, because {stdout}")

        exp.result = result
        exp.stdout = stdout

        # ── Register new factors into SignalPool (if strategy is available) ──
        if self.strategy is not None:
            fm = FactorMetrics.from_result_dict(result)
            for task in exp.sub_tasks:
                alpha = RawFactor(
                    name=task.factor_name,
                    description=task.factor_description,
                    status=SignalStatus.SOTA,
                    factor_metrics=fm,
                    expression=task.factor_formulation,
                    formulation=task.factor_formulation,
                    variables=task.variables,
                    code=task.factor_implementation if hasattr(task, 'factor_implementation') else "",
                    round_number=len(self.strategy.experiments) + 1,
                )
                self.strategy.alpha_pool.add(alpha)

        return exp
