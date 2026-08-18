from pathlib import Path
from typing import List

import pandas as pd

from rdagent.components.coder.CoSTEER.evaluators import CoSTEERMultiFeedback
from rdagent.components.coder.factor_coder.factor import FactorFBWorkspace, FactorTask
from rdagent.core.conf import RD_AGENT_SETTINGS
from rdagent.core.exception import FactorEmptyError
from rdagent.core.utils import multiprocessing_wrapper
from rdagent.log import rdagent_logger as logger
from rdagent.scenarios.qlib.domain import RawFactor
from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorExperiment


def _build_base_feature_workspaces(exp: QlibFactorExperiment) -> list[FactorFBWorkspace]:
    workspaces: list[FactorFBWorkspace] = []
    for file_name, code in exp.base_feature_codes.items():
        workspace = FactorFBWorkspace(
            target_task=FactorTask(
                factor_name=file_name,
                factor_description=f"Base feature from {file_name}",
                factor_formulation="",
            )
        )
        workspace.inject_files(**{"factor.py": code})
        workspaces.append(workspace)
    return workspaces


def _build_execute_calls(exp: QlibFactorExperiment, base_feature_workspaces: list[FactorFBWorkspace]) -> list[tuple]:
    execute_calls = []

    if exp.sub_tasks:
        assert isinstance(exp.prop_dev_feedback, CoSTEERMultiFeedback)
        execute_calls.extend(
            (implementation.execute, ("All",))
            for implementation, feedback in zip(exp.sub_workspace_list, exp.prop_dev_feedback)
            if implementation and feedback
        )

    execute_calls.extend((workspace.execute, ("All",)) for workspace in base_feature_workspaces)
    return execute_calls


def _resolve_index_level_values(df: pd.DataFrame, level_name: str) -> pd.Index | None:
    matching_levels = [idx for idx, name in enumerate(df.index.names) if name == level_name]
    if not matching_levels:
        return None

    if len(matching_levels) == 1:
        return df.index.get_level_values(matching_levels[0])

    candidate_values = [df.index.get_level_values(idx) for idx in matching_levels]
    first_values = candidate_values[0]
    if all(first_values.equals(values) for values in candidate_values[1:]):
        logger.warning(
            f"Factor dataframe has duplicated '{level_name}' index levels at positions {matching_levels}; "
            "their values are identical, so the first one is used."
        )
        return first_values

    logger.warning(
        f"Skip factor dataframe because index has ambiguous duplicated '{level_name}' levels at positions "
        f"{matching_levels}. index names={list(df.index.names)}"
    )
    return None


def _normalize_factor_index(df: pd.DataFrame) -> pd.DataFrame | None:
    """Normalize factor index to a 2-level MultiIndex: (datetime, instrument)."""
    if df is None or df.empty:
        return None

    index_names = list(df.index.names)
    if "datetime" not in index_names:
        return None

    if "instrument" not in index_names:
        logger.warning(f"Skip factor dataframe because index misses 'instrument'. index names={index_names}")
        return None

    datetime_values = _resolve_index_level_values(df, "datetime")
    instrument_values = _resolve_index_level_values(df, "instrument")
    if datetime_values is None or instrument_values is None:
        return None

    normalized = df.copy()
    normalized.index = pd.MultiIndex.from_arrays(
        [datetime_values, instrument_values],
        names=["datetime", "instrument"],
    )
    return normalized


def _format_index_info(df: pd.DataFrame | None) -> str:
    if df is None:
        return "df is None"
    return f"index_type={type(df.index).__name__}, nlevels={df.index.nlevels}, names={list(df.index.names)}"


def _process_message_and_df(
    source_name: str,
    message: str,
    df: pd.DataFrame | None,
    factor_dfs: list[pd.DataFrame],
    error_message: str,
) -> str:
    index_info = _format_index_info(df)
    if df is None or "datetime" not in df.index.names:
        logger.warning(f"Factor data from {source_name} has invalid execution output or index: {index_info}")
        logger.warning(f"Factor data from {source_name} is not generated because of {message}")
        return (
            f"{error_message}Factor data from {source_name} is not generated because of {message}. "
            f"index_info={index_info}. "
        )

    normalized_df = _normalize_factor_index(df)
    if normalized_df is None:
        logger.warning(f"Factor data from {source_name} is skipped due to invalid index structure: {index_info}")
        return f"{error_message}Factor data from {source_name} is skipped due to invalid index: {index_info}. "

    time_diff = df.index.get_level_values("datetime").to_series().diff().dropna().unique()
    if pd.Timedelta(minutes=1) in time_diff:
        logger.warning(f"Factor data from {source_name} is not generated.")
        return error_message

    factor_dfs.append(normalized_df)
    logger.info(f"Factor data from {source_name} is successfully generated.")
    return error_message


def build_cumulative_factor_df(strategy_id: str | None) -> pd.DataFrame | None:
    """Build the session's accumulated factor values.

    Resolves the session's historical factor (alpha) experiment workspaces via
    research.db, reads each ``combined_factors_df.parquet``, and merges them
    into a single factor-value frame (columns are a MultiIndex
    ``('feature', <factor_name>)``; duplicate columns keep the last). Returns
    ``None`` when no factor experiment has produced a parquet.
    """
    if not strategy_id:
        return None
    try:
        from rdagent.log.research_db import ResearchDB

        exps = ResearchDB().query_factor_experiments(strategy_id)
    except Exception as e:
        logger.warning(f"build_cumulative_factor_df: query factor experiments failed ({e})")
        return None

    factor_dfs = []
    for exp in exps:
        ws_path = exp.get("workspace_path")
        if not ws_path:
            continue
        parquet_path = Path(ws_path) / "combined_factors_df.parquet"
        if not parquet_path.exists():
            continue
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as e:
            logger.warning(f"build_cumulative_factor_df: failed to read {parquet_path} ({e})")
            continue
        if df is None or df.empty:
            continue
        factor_dfs.append(df)

    if not factor_dfs:
        return None

    cumulative = pd.concat(factor_dfs, axis=1)
    cumulative = cumulative.loc[:, ~cumulative.columns.duplicated(keep="last")]
    return cumulative.sort_index()


def _build_sota_factor_df(strategy_id: str | None, exp) -> pd.DataFrame | None:
    """Return the session's effective accumulated factor values for a runner.

    Values come from ``build_cumulative_factor_df`` (merging the persisted
    ``combined_factors_df.parquet`` files); effective status is resolved from
    the research.db ``factors`` table (rows marked ``deprecated`` are excluded,
    so rejected rounds' factors are not trained on). Factors already covered by
    ``exp.base_features`` are excluded to avoid duplication. Returns ``None``
    when no effective factor data is available (runners then use their
    baseline config).
    """
    factor_df = build_cumulative_factor_df(strategy_id)
    if factor_df is None or factor_df.empty:
        return None

    # Resolve effective factor names from research.db (exclude deprecated).
    effective_names: set[str] | None = None
    try:
        from rdagent.log.research_db import ResearchDB

        rows = ResearchDB().query_factors(strategy_id)
        effective_names = {r["name"] for r in rows if r.get("status") != "deprecated"}
    except Exception as e:
        logger.warning(f"_build_sota_factor_df: query factors failed ({e}); using all cumulative factors")

    # Columns are a MultiIndex ('feature', <factor_name>).
    if effective_names and factor_df.columns.nlevels > 1:
        keep = [col for col in factor_df.columns if col[1] in effective_names]
        if not keep:
            return None
        factor_df = factor_df.loc[:, keep]

    base_features = getattr(exp, "base_features", None) or {}
    if factor_df.columns.nlevels > 1:
        factor_df = factor_df.loc[
            :, [col for col in factor_df.columns if col[1] not in base_features]
        ]
    if factor_df.empty:
        return None
    logger.info(f"Building model factor pool ({len(factor_df.columns)} factors) ...")
    return factor_df


def process_factor_data(exp_or_list: List[QlibFactorExperiment] | QlibFactorExperiment) -> pd.DataFrame:
    """
    Process and combine factor data from experiment implementations.

    Args:
        exp (ASpecificExp): The experiment containing factor data.

    Returns:
        pd.DataFrame: Combined factor data without NaN values.
    """
    if isinstance(exp_or_list, QlibFactorExperiment):
        exp_or_list = [exp_or_list]
    factor_dfs = []
    error_message = ""

    # Collect all exp's dataframes
    for exp in exp_or_list:
        if not isinstance(exp, QlibFactorExperiment):
            continue

        source_name = exp.hypothesis.concise_justification if exp.hypothesis else "BASE factor files"
        base_feature_workspaces = _build_base_feature_workspaces(exp)
        execute_calls = _build_execute_calls(exp, base_feature_workspaces)
        if not execute_calls:
            continue

        message_and_df_list = multiprocessing_wrapper(execute_calls, n=RD_AGENT_SETTINGS.multi_proc_n)
        for message, df in message_and_df_list:
            error_message = _process_message_and_df(source_name, message, df, factor_dfs, error_message)

    # Combine all successful factor data
    if factor_dfs:
        try:
            return pd.concat(factor_dfs, axis=1)
        except Exception as concat_error:
            concat_index_info = " | ".join([f"df#{i}: {_format_index_info(df)}" for i, df in enumerate(factor_dfs)])
            logger.warning(
                f"Failed to concat factor data due to index misalignment. concat_error={concat_error}; collected_index_info={concat_index_info}"
            )
            raise FactorEmptyError(
                "Failed to concat factor data due to index misalignment or incompatible index structure. "
                f"concat_error={concat_error}; collected_index_info={concat_index_info}; details={error_message}"
            ) from concat_error
    else:
        raise FactorEmptyError(
            f"No valid factor data found to merge (in process_factor_data) because of {error_message}."
        )


def process_factor_pool(raw_factors: list[RawFactor]) -> pd.DataFrame:
    """
    Rebuild factor values from a SignalPool's RawFactor definitions by re-running
    each factor's code (decision A: no intermediate-result cache).

    Failed factors (empty code, workspace build errors, or execution/parse
    failures) are excluded and reported in the raised error message. Raises
    ``FactorEmptyError`` when no factor produces valid data.
    """
    factor_dfs = []
    error_message = ""
    execute_calls = []
    names = []

    for rf in raw_factors:
        if not rf.code:
            error_message += f"Factor data from {rf.name} is not generated because of empty factor code. "
            continue
        try:
            workspace = FactorFBWorkspace(
                target_task=FactorTask(
                    factor_name=rf.name,
                    factor_description=rf.description,
                    factor_formulation=rf.formulation,
                )
            )
            workspace.inject_files(**{"factor.py": rf.code})
        except Exception as e:
            error_message += f"Factor data from {rf.name} is not generated because of workspace build error: {e}. "
            continue
        execute_calls.append((workspace.execute, ("All",)))
        names.append(rf.name)

    if not execute_calls:
        raise FactorEmptyError(f"No valid factor code to run in factor pool because of {error_message}.")

    message_and_df_list = multiprocessing_wrapper(execute_calls, n=RD_AGENT_SETTINGS.multi_proc_n)
    for name, (message, df) in zip(names, message_and_df_list):
        error_message = _process_message_and_df(name, message, df, factor_dfs, error_message)

    # Report partial exclusions (spec: "the task reports which factors were
    # excluded") even when some factors succeed. Total failure is surfaced via
    # the FactorEmptyError below.
    if error_message and factor_dfs:
        logger.warning(f"Some factors in the factor pool were excluded: {error_message}")

    if factor_dfs:
        try:
            return pd.concat(factor_dfs, axis=1)
        except Exception as concat_error:
            concat_index_info = " | ".join([f"df#{i}: {_format_index_info(df)}" for i, df in enumerate(factor_dfs)])
            logger.warning(
                f"Failed to concat factor pool data due to index misalignment. concat_error={concat_error}; "
                f"collected_index_info={concat_index_info}"
            )
            raise FactorEmptyError(
                "Failed to concat factor pool data due to index misalignment or incompatible index structure. "
                f"concat_error={concat_error}; collected_index_info={concat_index_info}; details={error_message}"
            ) from concat_error
    else:
        raise FactorEmptyError(f"No valid factor data found in factor pool because of {error_message}.")
