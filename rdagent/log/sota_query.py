"""
SOTA query module — extract best experiment artifacts from a LoopBase session.

Provides two public functions:
- query_sota(log_path): load session, return structured SOTA info dict
- find_session_by_trace_name(trace_name, log_root): map trace name to session path

Used by:
- CLI: rdagent sota --log-path / --trace-name
- HTTP: GET /traces/{trace_name}/sota
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rdagent.core.experiment import Experiment, FBWorkspace
from rdagent.core.proposal import Hypothesis, HypothesisFeedback, Trace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query_sota(log_path: str | Path) -> dict[str, Any]:
    """Load the latest LoopBase session from *log_path* and extract SOTA info.

    Args:
        log_path: Path to the log directory (e.g. ``log/2026-07-19_03-38-42-135506``).
                  Must contain ``__session__/`` subdirectory.

    Returns:
        Structured dict with SOTA hypothesis, feedback, metrics, factor/model
        code, and workspace paths.  If no SOTA found or session missing, returns
        ``{"error": "..."}``.
    """
    log_path = Path(log_path)

    # --- 1. Locate session directory ----------------------------------------
    session_dir = log_path / "__session__"
    if not session_dir.exists():
        return {
            "error": "No session found",
            "detail": f"__session__/ not found under {log_path}",
            "log_path": str(log_path),
        }

    # --- 2. Load latest LoopBase session pickle -----------------------------
    try:
        from rdagent.utils.workflow import LoopBase

        loop = LoopBase.load(log_path, checkout=False)
    except Exception as exc:
        logger.exception("Failed to load session from %s", log_path)
        return {
            "error": "Session load failed",
            "detail": f"{type(exc).__name__}: {exc}",
            "log_path": str(log_path),
        }

    trace: Trace = getattr(loop, "trace", None)
    if trace is None or not trace.hist:
        return {
            "error": "Empty trace",
            "detail": "LoopBase loaded but trace.hist is empty (no completed experiments)",
            "log_path": str(log_path),
        }

    # --- 3. Find SOTA experiment --------------------------------------------
    hypothesis, sota_exp = trace.get_sota_hypothesis_and_experiment()
    if sota_exp is None:
        return {
            "error": "No SOTA experiment",
            "detail": "No experiment with feedback.decision=True found in trace",
            "log_path": str(log_path),
            "total_experiments": len(trace.hist),
        }

    # Locate the corresponding feedback in trace.hist
    sota_feedback: HypothesisFeedback | None = None
    sota_loop_id: int | None = None
    for idx, (exp, fb) in enumerate(trace.hist):
        if exp is sota_exp:
            sota_feedback = fb
            sota_loop_id = trace.idx2loop_id.get(idx)
            break

    # --- 4. Extract structured info -----------------------------------------
    result: dict[str, Any] = {
        "log_path": str(log_path),
        "total_experiments": len(trace.hist),
        "sota_loop_id": sota_loop_id,
    }

    # 4a. Hypothesis
    if hypothesis is not None:
        result["sota_hypothesis"] = _extract_hypothesis(hypothesis)

    # 4b. Feedback
    if sota_feedback is not None:
        result["sota_feedback"] = _extract_feedback(sota_feedback)

    # 4c. Metrics (from experiment.result, which is a pd.Series)
    result["sota_metrics"] = _extract_metrics(sota_exp)

    # 4d. Factors
    factors = _extract_factors(sota_exp)
    if factors:
        result["sota_factors"] = factors

    # 4e. Model
    model = _extract_model(sota_exp)
    if model:
        result["sota_model"] = model

    # 4f. Experiment workspace path
    if sota_exp.experiment_workspace is not None:
        ws_path = sota_exp.experiment_workspace.workspace_path
        result["experiment_workspace_path"] = str(ws_path)
        result["experiment_workspace_exists"] = Path(ws_path).exists()

    return result


def find_session_by_trace_name(
    trace_name: str, log_root: str | Path = "log"
) -> Path | None:
    """Scan *log_root* for a session directory matching *trace_name*.

    Matching strategy (in order):
    1. Exact match on directory name.
    2. Substring match (trace_name appears in the directory name).
    3. If trace_name looks like a Flask trace id (e.g. ``Finance Factor/xxx``),
       try matching the last path component.

    Returns:
        The ``log/<timestamp>`` directory if found, else ``None``.
    """
    log_root = Path(log_root)
    if not log_root.is_dir():
        return None

    # Gather all timestamp directories that have __session__/
    candidates = sorted(
        d for d in log_root.iterdir()
        if d.is_dir() and (d / "__session__").is_dir()
    )

    if not candidates:
        return None

    # Normalise trace_name (Flask trace ids may contain " / " or URL-encoding)
    normalised = trace_name.replace("%20", " ").replace("/", " ").strip()
    last_part = normalised.split(" ")[-1] if normalised else trace_name

    # Strategy 1 & 2: exact / substring match on directory name
    for d in candidates:
        name = d.name
        if name == trace_name or name == normalised or last_part in name:
            return d

    return None


# ---------------------------------------------------------------------------
# Internal extractors
# ---------------------------------------------------------------------------

def _extract_hypothesis(hyp: Hypothesis) -> dict[str, Any]:
    return {
        "hypothesis": getattr(hyp, "hypothesis", None),
        "reason": getattr(hyp, "reason", None),
        "assumption": getattr(hyp, "assumption", None),
        "knowledge": getattr(hyp, "knowledge", None),
    }


def _extract_feedback(fb: HypothesisFeedback) -> dict[str, Any]:
    return {
        "decision": getattr(fb, "decision", None),
        "observations": getattr(fb, "observations", None),
        "hypothesis_evaluation": getattr(fb, "hypothesis_evaluation", None),
        "new_hypothesis": getattr(fb, "new_hypothesis", None),
        "reason": getattr(fb, "reason", None),
    }


def _extract_metrics(exp: Experiment) -> dict[str, float]:
    """Extract backtest metrics from experiment.result (a pd.Series)."""
    try:
        result = exp.result
        if result is None:
            return {}
        # result may be a pd.Series — convert to dict
        if hasattr(result, "to_dict"):
            return {str(k): float(v) for k, v in result.to_dict().items() if _is_numeric(v)}
        if isinstance(result, dict):
            return {str(k): float(v) for k, v in result.items() if _is_numeric(v)}
    except Exception:
        pass
    return {}


def _extract_factors(exp: Experiment) -> list[dict[str, Any]]:
    """Extract factor info from sub_tasks that are FactorTask instances."""
    factors: list[dict[str, Any]] = []
    try:
        from rdagent.components.coder.factor_coder.factor import FactorTask

        for i, task in enumerate(exp.sub_tasks):
            if not isinstance(task, FactorTask):
                continue
            factor: dict[str, Any] = {
                "name": getattr(task, "factor_name", None),
                "description": getattr(task, "description", None),
                "formulation": getattr(task, "factor_formulation", None),
                "variables": getattr(task, "variables", None),
            }
            # Extract code from sub_workspace
            code, ws_path = _extract_workspace_code(exp, i)
            if code:
                factor["code"] = code
            if ws_path:
                factor["workspace_path"] = ws_path
                factor["workspace_exists"] = Path(ws_path).exists()
            factors.append(factor)
    except ImportError:
        logger.debug("FactorTask not available, skipping factor extraction")
    return factors


def _extract_model(exp: Experiment) -> dict[str, Any] | None:
    """Extract model info from sub_tasks that are ModelTask instances."""
    try:
        from rdagent.components.coder.model_coder.model import ModelTask

        for i, task in enumerate(exp.sub_tasks):
            if not isinstance(task, ModelTask):
                continue
            model: dict[str, Any] = {
                "name": getattr(task, "name", None),
                "architecture": getattr(task, "architecture", None),
                "model_type": getattr(task, "model_type", None),
                "formulation": getattr(task, "formulation", None),
                "hyperparameters": getattr(task, "training_hyperparameters", None),
            }
            code, ws_path = _extract_workspace_code(exp, i)
            if code:
                model["code"] = code
            if ws_path:
                model["workspace_path"] = ws_path
                model["workspace_exists"] = Path(ws_path).exists()
            return model
    except ImportError:
        logger.debug("ModelTask not available, skipping model extraction")
    return None


def _extract_workspace_code(exp: Experiment, sub_idx: int) -> tuple[str | None, str | None]:
    """Extract code from a sub_workspace's file_dict.

    Returns (code_str, workspace_path_str).
    """
    if sub_idx >= len(exp.sub_workspace_list):
        return None, None
    ws = exp.sub_workspace_list[sub_idx]
    if ws is None:
        return None, None

    ws_path = str(getattr(ws, "workspace_path", ""))
    file_dict: dict = getattr(ws, "file_dict", {})
    # Prefer factor.py / model.py
    for fname in ("factor.py", "model.py"):
        if fname in file_dict and file_dict[fname]:
            return file_dict[fname], ws_path
    # Fallback: any .py file
    for fname, content in file_dict.items():
        if fname.endswith(".py") and content:
            return content, ws_path
    return None, ws_path


def _is_numeric(val: Any) -> bool:
    """Check if val is a finite number (not NaN/inf)."""
    try:
        f = float(val)
        import math
        return not math.isnan(f) and not math.isinf(f)
    except (TypeError, ValueError):
        return False
