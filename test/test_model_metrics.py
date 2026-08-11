"""Focused tests for model-metrics backfill (Model Lab指标缺失修复).

Covers:
  1. ``ResearchDB.update_model_metrics`` targets a single (strategy_id, name) row.
  2. ``WorkflowTracker._on_running`` backfills metrics to produced model rows.
  3. fin_model-downstream (parent_strategy_id set): metrics land on the PARENT's
     model row, without polluting the parent's own same-round models.
  4. non-downstream run: metrics land on the run's own strategy id.
  5. module import sanity.
"""

import tempfile
from pathlib import Path

import pytest

import rdagent.log.research_db as research_db_module

research_db_module._RESEARCH_DB_PATH = ":memory:"

from rdagent.log.research_db import ResearchDB  # noqa: E402
from rdagent.utils.workflow.tracking import WorkflowTracker  # noqa: E402


@pytest.fixture(autouse=True)
def reset_singleton():
    old_instance = research_db_module._instance
    research_db_module._instance = None
    yield
    inst = research_db_module._instance
    if inst is not None:
        try:
            inst.close()
        except Exception:
            pass
    research_db_module._instance = old_instance


class _FakeLoop:
    """Minimal loop_base exposing only what WorkflowTracker touches."""

    def __init__(self, session_folder: Path, parent_strategy_id: str | None = None):
        self.session_folder = session_folder
        self.parent_strategy_id = parent_strategy_id
        self.loop_prev_out = {}


def _make_tracker(parent_strategy_id: str | None = None) -> tuple[WorkflowTracker, _FakeLoop, str]:
    base = Path(tempfile.mkdtemp())
    session_folder = base / "child_run" / "__session__"
    session_folder.mkdir(parents=True)
    loop = _FakeLoop(session_folder, parent_strategy_id)
    strategy_id = f"{base.name}/child_run"
    return WorkflowTracker(loop), loop, strategy_id


def _model_result() -> dict:
    return {
        "IC": 0.04,
        "ICIR": 0.9,
        "1day.excess_return_with_cost.annualized_return": 0.18,
        "1day.excess_return_with_cost.max_drawdown": -0.12,
        "1day.excess_return_with_cost.information_ratio": 1.5,
    }


class _ModelTask:
    def __init__(self, name: str):
        self.name = name
        self.model_type = "lgbm"
        self.architecture = "LGBMModel"
        self.training_hyperparameters = {"learning_rate": 0.1}


class _Exp:
    def __init__(self, result, sub_tasks):
        self.result = result
        self.sub_tasks = sub_tasks
        self.experiment_workspace = None  # skip chart persist


class TestUpdateModelMetrics:
    def test_updates_only_target_row_by_name(self):
        db = ResearchDB()
        db.upsert_strategy("s1")
        db.upsert_model("s1", "m_a", round_number=1)
        db.upsert_model("s1", "m_b", round_number=1)
        db.upsert_model("s2", "m_a", round_number=1)

        db.update_model_metrics("s1", "m_a",
                                annualized_return=0.18, max_drawdown=-0.12, information_ratio=1.5)

        rows = {m["name"]: m for m in db.query_models("s1")}
        assert rows["m_a"]["annualized_return"] == 0.18
        assert rows["m_a"]["max_drawdown"] == -0.12
        assert rows["m_a"]["information_ratio"] == 1.5
        # Same strategy, different name: untouched
        assert rows["m_b"]["annualized_return"] is None
        # Different strategy, same name: untouched
        rows_s2 = {m["name"]: m for m in db.query_models("s2")}
        assert rows_s2["m_a"]["annualized_return"] is None

    def test_coalesce_prefixes_non_null(self):
        db = ResearchDB()
        db.upsert_strategy("s1")
        db.upsert_model("s1", "m", annualized_return=0.5)

        db.update_model_metrics("s1", "m", max_drawdown=-0.1)
        m = db.query_models("s1")[0]
        assert m["annualized_return"] == 0.5  # preserved
        assert m["max_drawdown"] == -0.1


class TestTrackerRunningModelMetrics:
    def test_model_metrics_backfilled_to_own_strategy(self):
        tracker, loop, strategy_id = _make_tracker()
        db = ResearchDB()
        db.upsert_strategy(strategy_id)
        # Model row created by _on_coding under the run's own id.
        db.upsert_model(strategy_id, "model_x", round_number=3)

        exp = _Exp(result=_model_result(), sub_tasks=[_ModelTask("model_x")])
        tracker._on_running(db, strategy_id, loop_id=3, output=exp)

        m = db.query_models(strategy_id)[0]
        assert m["annualized_return"] == 0.18
        assert m["max_drawdown"] == -0.12
        assert m["information_ratio"] == 1.5

    def test_factor_tasks_are_skipped(self):
        tracker, loop, strategy_id = _make_tracker()
        db = ResearchDB()
        db.upsert_strategy(strategy_id)
        db.upsert_model(strategy_id, "model_x", round_number=1)

        class _FactorTask:
            factor_name = "f1"
        exp = _Exp(result=_model_result(), sub_tasks=[_FactorTask()])
        tracker._on_running(db, strategy_id, loop_id=1, output=exp)

        m = db.query_models(strategy_id)[0]
        assert m["annualized_return"] is None  # no model task -> untouched


class TestDownstreamParentBackfill:
    def test_downstream_metrics_land_on_parent_without_polluting(self):
        # Parent already has its own same-round model; child (downstream) model
        # was registered under the parent id by _on_coding.
        base = Path(tempfile.mkdtemp())
        parent_session = base / "parent" / "__session__"
        parent_session.mkdir(parents=True)
        parent_strategy_id = f"{base.name}/parent"

        tracker, loop, child_strategy_id = _make_tracker(parent_strategy_id=parent_strategy_id)
        db = ResearchDB()
        db.upsert_strategy(parent_strategy_id)
        db.upsert_strategy(child_strategy_id)

        # Parent's own model at the same round_number as the downstream round.
        db.upsert_model(parent_strategy_id, "parent_own_model", round_number=1)
        # Downstream model registered under the parent id (round collides with above).
        db.upsert_model(parent_strategy_id, "downstream_model", round_number=1)

        child_exp = _Exp(result=_model_result(), sub_tasks=[_ModelTask("downstream_model")])
        tracker._on_running(db, child_strategy_id, loop_id=1, output=child_exp)

        parent_rows = {m["name"]: m for m in db.query_models(parent_strategy_id)}
        assert parent_rows["downstream_model"]["annualized_return"] == 0.18
        # Parent's own same-round model must NOT be polluted.
        assert parent_rows["parent_own_model"]["annualized_return"] is None

    def test_nondownstream_matches_old_behavior(self):
        # No parent_strategy_id: metrics go to the run's own id.
        tracker, loop, strategy_id = _make_tracker()
        db = ResearchDB()
        db.upsert_strategy(strategy_id)
        db.upsert_model(strategy_id, "m", round_number=1)

        exp = _Exp(result=_model_result(), sub_tasks=[_ModelTask("m")])
        tracker._on_running(db, strategy_id, loop_id=1, output=exp)
        m = db.query_models(strategy_id)[0]
        assert m["annualized_return"] == 0.18


def test_dead_code_removed():
    import rdagent.log.research_db as rdb
    assert not hasattr(rdb.ResearchDB, "update_models_metrics_for_loop")
    assert hasattr(rdb.ResearchDB, "update_model_metrics")


def test_module_imports():
    import rdagent.utils.workflow.tracking  # noqa: F401
    import rdagent.log.research_db  # noqa: F401