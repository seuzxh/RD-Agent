"""
Tracking module for experiment tracking using MLflow and SQLite.

This module provides a clean interface for tracking metrics and parameters
while keeping the MLflow dependency optional based on configuration.
"""

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytz

from rdagent.core.conf import RD_AGENT_SETTINGS
from rdagent.log.timer import RD_Agent_TIMER_wrapper

if TYPE_CHECKING:
    # Import here to avoid circular dependency
    from rdagent.utils.workflow.loop import LoopBase

from rdagent.log import rdagent_logger as logger

# Define a placeholder for mlflow if it's not available
mlflow = None

# Conditional import to make MLflow optional
if RD_AGENT_SETTINGS.enable_mlflow:
    try:
        import mlflow  # type: ignore[assignment]
    except ImportError:
        logger.warning("MLflow is enabled in settings but could not be imported.")
        RD_AGENT_SETTINGS.enable_mlflow = False


# ── Step name constants ──

STEP_DIRECT_EXP_GEN = "direct_exp_gen"
STEP_CODING = "coding"
STEP_RUNNING = "running"
STEP_FEEDBACK = "feedback"
STEP_RECORD = "record"


class WorkflowTracker:
    """
    A workflow-specific tracking system that logs metrics related to workflow execution.

    This class handles metric logging while keeping the MLflow dependency optional.
    If MLflow is not enabled in settings, tracking calls become no-ops.

    Extended with SQLite persistence via ResearchDB (see on_step_complete).
    """

    def __init__(self, loop_base: "LoopBase"):
        """
        Initialize a WorkflowTracker with a LoopBase instance.

        Args:
            loop_base: The LoopBase instance to track metrics for
        """
        self.loop_base = loop_base

    @staticmethod
    def is_enabled() -> bool:
        """Check if MLflow tracking is enabled."""
        return RD_AGENT_SETTINGS.enable_mlflow

    @staticmethod
    def _datetime_to_float(dt: datetime.datetime) -> float:
        """Convert datetime to a structured float representation."""
        return dt.second + dt.minute * 1e2 + dt.hour * 1e4 + dt.day * 1e6 + dt.month * 1e8 + dt.year * 1e10

    def log_workflow_state(self) -> None:
        """
        Log all workflow state metrics from the associated LoopBase instance.
        """
        if not RD_AGENT_SETTINGS.enable_mlflow or mlflow is None:
            return

        try:
            # Log workflow progress
            mlflow.log_metric("loop_index", self.loop_base.loop_idx)
            mlflow.log_metric("step_index", self.loop_base.step_idx[self.loop_base.loop_idx])

            current_local_datetime = datetime.datetime.now(pytz.timezone("Asia/Shanghai"))
            float_like_datetime = self._datetime_to_float(current_local_datetime)
            mlflow.log_metric("current_datetime", float_like_datetime)

            # Log API status
            mlflow.log_metric("api_fail_count", RD_Agent_TIMER_wrapper.api_fail_count)
            latest_api_fail_time = RD_Agent_TIMER_wrapper.latest_api_fail_time
            if latest_api_fail_time is not None:
                float_like_datetime = self._datetime_to_float(latest_api_fail_time)
                mlflow.log_metric("lastest_api_fail_time", float_like_datetime)

            # Log timer status if timer is started
            if self.loop_base.timer.started:
                remain_time = self.loop_base.timer.remain_time()
                assert remain_time is not None
                mlflow.log_metric("remain_time", remain_time.total_seconds())
                mlflow.log_metric(
                    "remain_percent",
                    remain_time / self.loop_base.timer.all_duration * 100,
                )

        # Keep only the log_workflow_state method as it's the primary entry point now
        except Exception as e:
            logger.warning(f"Error in log_workflow_state: {e}")

    # ── SQLite persistence (ResearchDB) ──

    def _derive_strategy_id(self) -> str | None:
        """Derive the external strategy_id from the session folder path.

        Session folder is ``<trace_root>/<scenario>/<trace_name>/__session__``
        (webUI) or ``<log_root>/<timestamp>/__session__`` (CLI).

        Returns the relative path from the trace root, or None if not derivable.
        """
        from pathlib import Path
        session_folder = self.loop_base.session_folder
        if not session_folder:
            return None
        # Walk up from __session__/ to find the trace root
        parent = session_folder.parent  # .../<trace_name>/
        grandparent = parent.parent     # .../<scenario>/  or .../<log_root>/
        if grandparent.name == "__session__":
            # Nested session (unlikely but handle gracefully)
            return parent.name
        # Strategy id = <scenario>/<trace_name> or just <timestamp>
        if grandparent.name in ("log", "traces") or not grandparent.exists():
            # CLI session: just the directory name
            return parent.name
        # webUI session: <scenario>/<trace_name>
        return f"{grandparent.name}/{parent.name}"

    def on_step_complete(self, loop_id: int, step_name: str) -> None:
        """Called after each step completes successfully.

        Writes step output to ResearchDB (SQLite) for persistence.
        This is the hook point from ``LoopBase._run_step()``.

        Args:
            loop_id: The loop index that just completed a step.
            step_name: The name of the step that completed.
        """
        strategy_id = self._derive_strategy_id()
        if strategy_id is None:
            logger.warning("on_step_complete: cannot derive strategy_id, skipping SQLite write")
            return

        try:
            from rdagent.log.research_db import ResearchDB
            db = ResearchDB()
        except Exception as e:
            logger.warning(f"on_step_complete: ResearchDB unavailable ({e}), skipping")
            return

        # Get the step output from loop_prev_out
        loop_out = self.loop_base.loop_prev_out.get(loop_id, {})
        step_output = loop_out.get(step_name)

        # Ensure strategy exists
        db.upsert_strategy(strategy_id)

        # Write pipeline node with stage-appropriate status
        self._write_node(db, strategy_id, loop_id, step_name, step_output)

        # Step-specific domain writes
        if step_name == STEP_DIRECT_EXP_GEN:
            self._on_direct_exp_gen(db, strategy_id, loop_id, step_output)
        elif step_name == STEP_CODING:
            self._on_coding(db, strategy_id, loop_id, step_output)
        elif step_name == STEP_RUNNING:
            self._on_running(db, strategy_id, loop_id, step_output)
        elif step_name == STEP_FEEDBACK:
            self._on_feedback(db, strategy_id, loop_id, step_output)
        elif step_name == STEP_RECORD:
            self._on_record(db, strategy_id, loop_id, step_output)

        # Broadcast SSE event
        try:
            from rdagent.log.server.research_api import sse_broadcast
            sse_broadcast(strategy_id, "node_update", {
                "strategy_id": strategy_id,
                "loop_id": loop_id,
                "step_name": step_name,
                "status": "completed",
            })
        except Exception:
            pass  # SSE broadcast is best-effort

    # ── step-specific handlers ──

    def _write_node(self, db, strategy_id: str, loop_id: int, step_name: str, output: Any) -> None:
        """Write a pipeline node record with stage-appropriate status.

        Live Lab uses the node status to render real-time progress:
        - ``running``: step is in progress (first write)
        - ``completed``: step finished successfully (subsequent update)
        """
        # First write is always "running"; subsequent upserts flip to "completed".
        # upsert_node's ON CONFLICT logic only updates non-null fields, so we can
        # safely write "completed" here — the initial status was already set on the
        # first write in the previous step's cycle.
        db.upsert_node(
            strategy_id, loop_id, step_name,
            status="completed",
            output_summary=self._summarize(output),
            duration_ms=None,  # timing is handled by LoopBase
        )

    def _model_strategy_id(self) -> str | None:
        """Strategy id under which a produced model should be recorded.

        A fin_model run that consumes a parent strategy's factor pool produces a
        model that *belongs* to the parent (strategy_id = 父策略), so it must be
        registered under the parent's id for the Model Lab to merge it in.
        Falls back to the run's own derived strategy id otherwise.
        """
        parent_id = getattr(self.loop_base, "parent_strategy_id", None)
        if parent_id:
            return parent_id
        return self._derive_strategy_id()

    def _detect_experiment_type(self, exp: Any) -> str:
        """Detect whether an experiment is 'alpha' (factor) or 'model'.

        Override in subclasses for custom experiment types.
        The default implementation checks the experiment's sub_tasks.
        """
        if exp is None:
            return "alpha"
        sub_tasks = getattr(exp, "sub_tasks", None)
        if not sub_tasks:
            return "alpha"
        task = sub_tasks[0]
        if hasattr(task, "model_type"):
            return "model"
        return "alpha"

    def _is_factor_task(self, task: Any) -> bool:
        """Check if a task is a factor task (vs model task)."""
        return hasattr(task, "factor_name") or hasattr(task, "factor_formulation")

    def _task_name(self, task: Any, index: int = 0) -> str:
        """Extract a human-readable name from a task."""
        return (getattr(task, "factor_name", None)
                or getattr(task, "name", None)
                or f"task_{index}")

    def _on_direct_exp_gen(self, db, strategy_id: str, loop_id: int, output: Any) -> None:
        """Handle direct_exp_gen step: extract hypothesis + experiment."""
        # Support both dict and object output
        if isinstance(output, dict):
            hypo = output.get("propose")
            exp = output.get("exp_gen")
        else:
            # Try attribute access for non-dict output
            hypo = getattr(output, "propose", None) if output is not None else None
            exp = getattr(output, "exp_gen", None) if output is not None else None

        # Always create an experiment record (even with partial data)
        # This ensures pipeline continuity for subsequent steps (coding/running etc.)
        if exp is None and hypo is None:
            logger.info(f"direct_exp_gen loop {loop_id}: no exp/hypo extracted, creating empty experiment")
        elif exp is None:
            logger.info(f"direct_exp_gen loop {loop_id}: creating experiment with hypothesis only")
        hypothesis_text = str(hypo) if hypo else ""
        hypothesis_reason = getattr(hypo, "reason", None) if hypo else None
        hypothesis_assumption = getattr(hypo, "assumption", None) if hypo else None

        workspace_path = None
        if exp is not None:
            ws = getattr(exp, "experiment_workspace", None)
            if ws is not None:
                workspace_path = str(getattr(ws, "workspace_path", ""))

        db.upsert_experiment(
            strategy_id, loop_id,
            type=self._detect_experiment_type(exp), status="running",
            hypothesis_text=hypothesis_text,
            hypothesis_reason=hypothesis_reason,
            hypothesis_assumption=hypothesis_assumption,
            workspace_path=workspace_path,
        )

    def _on_coding(self, db, strategy_id: str, loop_id: int, output: Any) -> None:
        """Handle coding step: extract factor/model code."""
        if output is None:
            return

        exp = output
        sub_tasks = getattr(exp, "sub_tasks", [])
        sub_workspace_list = getattr(exp, "sub_workspace_list", [])

        # Get experiment_id for this loop (created in direct_exp_gen step)
        experiments = db.query_experiments(strategy_id)
        experiment_id = None
        for exp in experiments:
            if exp["loop_id"] == loop_id:
                experiment_id = exp["id"]
                break

        for i, task in enumerate(sub_tasks):
            name = self._task_name(task, i)
            description = getattr(task, "factor_description", "") or getattr(task, "description", "")

            if self._is_factor_task(task):
                code_path = None
                if i < len(sub_workspace_list) and sub_workspace_list[i] is not None:
                    ws = sub_workspace_list[i]
                    ws_path = getattr(ws, "workspace_path", None)
                    if ws_path:
                        code_path = str(Path(ws_path) / "factor.py")

                db.upsert_factor(
                    strategy_id, name,
                    experiment_id=experiment_id,
                    description=description,
                    formulation=getattr(task, "factor_formulation", None),
                    variables=getattr(task, "variables", None),
                    code_path=code_path,
                    status="active",
                    round_number=loop_id,
                )
            else:
                code_path = None
                if i < len(sub_workspace_list) and sub_workspace_list[i] is not None:
                    ws = sub_workspace_list[i]
                    ws_path = getattr(ws, "workspace_path", None)
                    if ws_path:
                        code_path = str(Path(ws_path) / "model.py")

                # A fin_model consuming a parent's factor pool produces a model
                # that belongs to the parent — register it under the parent's
                # strategy_id so it merges into the parent's Model Lab.
                db.upsert_model(
                    self._model_strategy_id(), name,
                    experiment_id=experiment_id,
                    model_type=getattr(task, "model_type", None),
                    architecture=getattr(task, "architecture", None),
                    hyperparameters=getattr(task, "training_hyperparameters", None),
                    code_path=code_path,
                    status="active",
                    round_number=loop_id,
                )

    def _on_running(self, db, strategy_id: str, loop_id: int, output: Any) -> None:
        """Handle running step: extract metrics from experiment result."""
        if output is None:
            return

        exp = output
        # Persist the backtest chart regardless of metrics availability.
        self._persist_backtest_chart(db, strategy_id, loop_id, exp)

        result = getattr(exp, "result", None)
        if result is None:
            return

        # Extract metrics from result (pd.Series or dict)
        try:
            metrics = {}
            if hasattr(result, "to_dict"):
                raw = result.to_dict()
            elif isinstance(result, dict):
                raw = result
            else:
                return

            for k, v in raw.items():
                try:
                    fv = float(v)
                    if not (fv != fv):  # not NaN
                        metrics[k] = fv
                except (TypeError, ValueError):
                    pass

            ic_val = metrics.get("IC")
            icir_val = metrics.get("ICIR")
            annualized_return_val = metrics.get("1day.excess_return_with_cost.annualized_return")
            max_drawdown_val = metrics.get("1day.excess_return_with_cost.max_drawdown")
            information_ratio_val = metrics.get("1day.excess_return_with_cost.information_ratio")

            db.update_experiment_metrics(
                strategy_id, loop_id,
                ic=ic_val,
                icir=icir_val,
                annualized_return=annualized_return_val,
                max_drawdown=max_drawdown_val,
                information_ratio=information_ratio_val,
            )

            # Sync metrics to factors table for frontend display
            db.update_factors_metrics_for_loop(
                strategy_id, loop_id,
                ic=ic_val,
                icir=icir_val,
                annualized_return=annualized_return_val,
                max_drawdown=max_drawdown_val,
                information_ratio=information_ratio_val,
            )

            # Backfill metrics to each produced model row, matched by name.
            # A fin_model downstream produces a model that belongs to the parent
            # strategy — register its metrics under the parent's id too.
            model_strategy_id = self._model_strategy_id()
            for task in getattr(exp, "sub_tasks", []):
                if self._is_factor_task(task):
                    continue
                name = self._task_name(task)
                if not name:
                    continue
                db.update_model_metrics(
                    model_strategy_id, name,
                    annualized_return=annualized_return_val,
                    max_drawdown=max_drawdown_val,
                    information_ratio=information_ratio_val,
                )
        except Exception:
            logger.warning(f"on_step_complete(running): failed to extract metrics for {strategy_id} loop {loop_id}")

    def _persist_backtest_chart(self, db, strategy_id: str, loop_id: int, exp: Any) -> None:
        """Generate ``ret_chart.html`` from the experiment workspace's ``ret.pkl``
        and persist its path into ``experiments.chart_path``.

        Best-effort: a failure to generate must not break the running step.
        """
        try:
            ws = getattr(exp, "experiment_workspace", None)
            ws_path = getattr(ws, "workspace_path", None)
            if not ws_path:
                return
            ret_pkl = Path(ws_path) / "ret.pkl"
            if not ret_pkl.exists():
                return

            from rdagent.log.ui.qlib_report_figure import generate_chart_html

            group_pkl = Path(ws_path) / "ret_group.pkl"
            html = generate_chart_html(ret_pkl, group_pkl if group_pkl.exists() else None)
            chart_file = Path(ws_path) / "ret_chart.html"
            chart_file.write_text(html, encoding="utf-8")
            db.upsert_experiment_chart_path(strategy_id, loop_id, str(chart_file))
        except Exception:
            logger.warning(f"_persist_backtest_chart: chart persist failed for {strategy_id} loop {loop_id}")

    def _on_feedback(self, db, strategy_id: str, loop_id: int, output: Any) -> None:
        """Handle feedback step: extract decision."""
        if output is None:
            return

        decision = getattr(output, "decision", False)
        decision_reason = getattr(output, "reason", None)
        observations = getattr(output, "observations", None)

        db.update_experiment_decision(
            strategy_id, loop_id,
            decision=bool(decision),
            decision_reason=decision_reason,
            observations=observations,
        )

    def _on_record(self, db, strategy_id: str, loop_id: int, output: Any) -> None:
        """Handle record step: finalize experiment and update factor/model status."""
        # The record step's output is None (it calls trace.sync_dag_parent_and_hist).
        # We read the previous step's output to get the final state.
        loop_out = self.loop_base.loop_prev_out.get(loop_id, {})
        feedback = loop_out.get("feedback")

        is_accepted = bool(getattr(feedback, "decision", False)) if feedback else False

        exp = loop_out.get("running") or loop_out.get("coding")

        # Accepted rounds: mark factors/models as SOTA. Rejected rounds: mark
        # them deprecated (已淘汰) instead of leaving them as active candidates.
        if exp is not None:
            for task in getattr(exp, "sub_tasks", []):
                name = self._task_name(task)
                if not name:
                    continue
                status = "sota" if is_accepted else "deprecated"
                if self._is_factor_task(task):
                    db.update_factor_status(strategy_id, name, status)
                else:
                    # Match the model's registration strategy id (parent for a
                    # fin_model downstream), not the run's own derived id.
                    db.update_model_status(self._model_strategy_id(), name, status)

        # The record step only fires when a loop has run end-to-end. The
        # `decision` reflects whether the factors beat SOTA — a rejected round
        # is still a completed round, not a failure. So the experiment is always
        # "completed" here. The strategy-level status is finalized once the whole
        # run finishes (see on_run_complete), not flapped per-loop from the
        # acceptance decision.
        db.finalize_experiment(strategy_id, loop_id, status="completed")

    def on_run_complete(self) -> None:
        """Mark the strategy as completed once the whole run finishes.

        Called from the scenario entry point after ``loop.run()`` returns
        (all loops done). The strategy status is a run-lifecycle signal and
        must not be derived from any single loop's factor-acceptance decision.
        """
        strategy_id = self._derive_strategy_id()
        if strategy_id is None:
            logger.warning("on_run_complete: cannot derive strategy_id, skipping")
            return
        try:
            from rdagent.log.research_db import ResearchDB
            ResearchDB().update_strategy_status(strategy_id, "completed")
        except Exception as e:
            logger.warning(f"on_run_complete: failed to finalize strategy status ({e})")

    def on_run_failed(self, error: BaseException | None = None) -> None:
        """Mark the strategy as failed when the run crashes abnormally."""
        strategy_id = self._derive_strategy_id()
        if strategy_id is None:
            logger.warning("on_run_failed: cannot derive strategy_id, skipping")
            return
        try:
            from rdagent.log.research_db import ResearchDB
            db = ResearchDB()
            db.update_strategy_status(strategy_id, "failed")
        except Exception as e:
            logger.warning(f"on_run_failed: failed to update strategy status ({e})")
            return
        # A crash interrupts the loop before the record step, so models that were
        # registered as "active" during coding are never finalized. Demote them to
        # "deprecated" (not sota) to prevent stale active models from lingering.
        # Match the registration strategy id used by _on_coding, not the run's own.
        try:
            model_sid = self._model_strategy_id()
            if model_sid:
                db.deprecate_active_models(model_sid)
        except Exception as e:
            logger.warning(f"on_run_failed: failed to deprecate active models ({e})")

    # ── helpers ──

    def _summarize(self, obj: Any) -> dict | None:
        """Create a lightweight JSON-serializable summary of a step output.

        Only extracts frontend-relevant fields, never dumps the full object.
        Returns None for None/empty input.
        """
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return {"value": obj}
        if isinstance(obj, dict):
            # Only keep keys that are primitive or short lists
            return {k: self._summarize(v) for k, v in obj.items()
                    if not k.startswith("_")}
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        # Fallback: repr truncated
        r = repr(obj)
        return {"type": type(obj).__name__, "repr": r[:200]}


