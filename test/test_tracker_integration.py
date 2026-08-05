"""Integration test: WorkflowTracker.on_step_complete + ResearchDB via LoopBase._run_step.

Verifies that running a single workflow step through ``LoopBase._run_step()``
persists the step output to the SQLite ResearchDB — specifically that:
  - the ``pipeline_nodes`` table gains a row for the completed step
  - the ``experiments`` table gains a row for the generated experiment
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

# Patch the DB path before importing ResearchDB (same pattern as test_research_db.py)
import rdagent.log.research_db as research_db_module

research_db_module._RESEARCH_DB_PATH = ":memory:"

from rdagent.log.research_db import ResearchDB  # noqa: E402
from rdagent.utils.workflow.loop import LoopBase  # noqa: E402


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the ResearchDB singleton before each test, using in-memory DB."""
    old_instance = research_db_module._instance
    research_db_module._instance = None
    yield
    # Clean up after test
    inst = research_db_module._instance
    if inst is not None:
        try:
            inst.close()
        except Exception:
            pass
    research_db_module._instance = old_instance


class _MinimalLoop(LoopBase):
    """Single-step loop: only the ``direct_exp_gen`` step, returning a dict output."""

    steps = ["direct_exp_gen"]  # LoopBase doesn't use LoopMeta, so set steps explicitly

    def direct_exp_gen(self, prev_out):
        return {"propose": "test hypothesis", "exp_gen": None}


def _make_loop() -> tuple[_MinimalLoop, str]:
    """Build a minimal loop whose ``session_folder`` yields a deterministic strategy_id.

    session_folder = <base>/<test_strategy>/__session__  (base = temp dir, exists),
    so ``_derive_strategy_id()`` returns ``<base.name>/test_strategy``.
    """
    base = Path(tempfile.mkdtemp())
    session_folder = base / "test_strategy" / "__session__"
    loop = _MinimalLoop()
    loop.session_folder = session_folder
    strategy_id = f"{base.name}/test_strategy"
    return loop, strategy_id


class TestTrackerIntegration:
    def test_single_step_writes_pipeline_node_and_experiment(self):
        loop, strategy_id = _make_loop()

        # Run a single step (loop 0, step 0 = direct_exp_gen) through _run_step.
        asyncio.run(loop._run_step(0))

        db = ResearchDB()

        # 1) pipeline_nodes has the completed step
        nodes = db.query_pipeline(strategy_id)
        assert len(nodes) == 1, f"expected 1 pipeline node, got {len(nodes)}"
        assert nodes[0]["step_name"] == "direct_exp_gen"
        assert nodes[0]["status"] == "completed"
        assert nodes[0]["loop_id"] == 0

        # 2) experiments has the generated experiment
        exps = db.query_experiments(strategy_id)
        assert len(exps) == 1, f"expected 1 experiment, got {len(exps)}"
        assert exps[0]["loop_id"] == 0
        assert exps[0]["type"] == "alpha"
        assert exps[0]["status"] == "running"
        assert exps[0]["hypothesis_text"] == "test hypothesis"