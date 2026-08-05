"""
Shared execution layer for Qlib backtest workflows.

Consolidates common patterns from QlibFactorRunner and QlibModelRunner:
- environment variable assembly
- combined factor data persistence
- qrun execution orchestration
- result parsing
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from rdagent.core.experiment import Experiment
from rdagent.log import rdagent_logger as logger
from rdagent.scenarios.qlib.experiment.workspace import QlibFBWorkspace


class QlibBacktestExecutor:
    """
    Encapsulates the shared Qlib backtest execution flow.

    Runners compose this class rather than duplicating the env/execute/parse logic.
    """

    # ── Baseline recursion ──

    @staticmethod
    def ensure_baseline_executed(exp: Experiment, runner_develop_fn) -> None:
        """
        Recursively execute the baseline experiment (based_experiments[-1])
        if its result is not yet available.

        Args:
            exp: The current experiment whose baseline may need execution.
            runner_develop_fn: Callable that executes a single experiment
                               (e.g. self.develop from the runner).
        """
        if exp.based_experiments and exp.based_experiments[-1].result is None:
            logger.info("Baseline experiment execution ...")
            exp.based_experiments[-1] = runner_develop_fn(exp.based_experiments[-1])

    # ── Environment assembly ──

    @staticmethod
    def build_env_to_use(
        *,
        train_start: str,
        train_end: str,
        valid_start: str,
        valid_end: str,
        test_start: str,
        test_end: Optional[str] = None,
        feature_names: list[str],
        feature_expressions: list[str],
        extra: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """
        Build the environment variable dict passed to qrun inside the Docker/Conda container.

        Args:
            train_start/end/valid_start/valid_end/test_start: date segments.
            test_end: optional test end date (may be 'auto'-resolved upstream).
            feature_names: list of base feature names (e.g. ALPHA20 keys).
            feature_expressions: list of base feature Qlib expressions.
            extra: additional runner-specific env vars (model_selector, hyperparams, etc.).

        Returns:
            dict of environment variables for the qrun process.
        """
        env = {
            "PYTHONPATH": "./",
            "train_start": train_start,
            "train_end": train_end,
            "valid_start": valid_start,
            "valid_end": valid_end,
            "test_start": test_start,
            "feature_names": str(feature_names),
            "feature_expressions": str(feature_expressions),
        }
        if test_end is not None:
            env["test_end"] = test_end
        if extra:
            env.update(extra)
        return env

    # ── Factor data persistence ──

    @staticmethod
    def save_combined_factors(workspace: QlibFBWorkspace, combined_factors: pd.DataFrame) -> Path:
        """
        Save combined factor DataFrame to parquet inside the experiment workspace.

        The file is consumed by conf_combined_factors.yaml / conf_*_sota_model.yaml
        during qrun execution.

        Args:
            workspace: The experiment workspace.
            combined_factors: MultiIndex DataFrame with columns=('feature', <factor_name>).

        Returns:
            Path to the saved parquet file.
        """
        combined_factors = combined_factors.sort_index()
        combined_factors = combined_factors.loc[:, ~combined_factors.columns.duplicated(keep="last")]

        if not isinstance(combined_factors.columns, pd.MultiIndex):
            new_columns = pd.MultiIndex.from_product([["feature"], combined_factors.columns])
            combined_factors.columns = new_columns

        target_path = workspace.workspace_path / "combined_factors_df.parquet"
        combined_factors.to_parquet(target_path, engine="pyarrow")
        logger.info(f"Combined factors saved to {target_path}")
        return target_path

    # ── Execution ──

    @staticmethod
    def execute_and_parse(
        workspace: QlibFBWorkspace,
        qlib_config_name: str,
        run_env: dict[str, str],
    ) -> tuple[Optional[pd.DataFrame], str]:
        """
        Run qrun + read_exp_res.py inside the workspace and return parsed results.

        Args:
            workspace: The experiment workspace (template + injected files).
            qlib_config_name: YAML config for qrun (e.g. conf_baseline.yaml).
            run_env: Environment variables for the container.

        Returns:
            Tuple of (result DataFrame or None, stdout string).
        """
        return workspace.execute(qlib_config_name=qlib_config_name, run_env=run_env)

    @staticmethod
    def extract_epoch_logs(stdout: str) -> str:
        """
        Extract epoch training logs from qrun stdout for compact display.

        Args:
            stdout: Raw qrun output.

        Returns:
            Filtered string with only epoch/best-score lines.
        """
        import re

        pattern = r"(Epoch\d+: train -[0-9\.]+, valid -[0-9\.]+|best score: -[0-9\.]+ @ \d+ epoch)"
        matches = re.findall(pattern, stdout)
        return "\n".join(matches) if matches else stdout