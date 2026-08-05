"""Tests for ResearchDB — SQLite persistence layer."""

import os
import tempfile
import threading
from pathlib import Path

import pytest

# Patch the DB path before importing ResearchDB
import rdagent.log.research_db as research_db_module

research_db_module._RESEARCH_DB_PATH = ":memory:"


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the ResearchDB singleton before each test, using in-memory DB."""
    old_instance = research_db_module._instance
    old_conn = getattr(old_instance, "_conn", None) if old_instance else None
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


def get_db():
    from rdagent.log.research_db import ResearchDB
    return ResearchDB()


class TestResearchDB:
    def test_singleton(self):
        db1 = get_db()
        db2 = get_db()
        assert db1 is db2

    def test_tables_created(self):
        db = get_db()
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [r[0] for r in tables]
        assert "strategies" in table_names
        assert "experiments" in table_names
        assert "factors" in table_names
        assert "models" in table_names
        assert "pipeline_nodes" in table_names

    def test_upsert_strategy(self):
        db = get_db()
        db.upsert_strategy("test/strategy-1", description="Test strategy", scenario="Finance Data Building", source="webui")
        s = db.query_strategy("test/strategy-1")
        assert s is not None
        assert s["description"] == "Test strategy"
        assert s["scenario"] == "Finance Data Building"
        assert s["source"] == "webui"

    def test_upsert_strategy_idempotent(self):
        db = get_db()
        db.upsert_strategy("test/s1", description="v1")
        db.upsert_strategy("test/s1", description="v2")
        s = db.query_strategy("test/s1")
        assert s["description"] == "v2"

    def test_strategy_list(self):
        db = get_db()
        db.upsert_strategy("test/s1", description="S1", source="webui")
        db.upsert_strategy("test/s2", description="S2", source="cli")
        strategies = db.query_strategies()
        assert len(strategies) == 2
        ids = {s["id"] for s in strategies}
        assert ids == {"test/s1", "test/s2"}

    def test_upsert_experiment(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        exp_id = db.upsert_experiment("test/s1", 1, type="alpha", hypothesis_text="Test hypothesis")
        assert exp_id > 0
        exps = db.query_experiments("test/s1")
        assert len(exps) == 1
        assert exps[0]["loop_id"] == 1
        assert exps[0]["hypothesis_text"] == "Test hypothesis"

    def test_update_experiment_metrics(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)
        db.update_experiment_metrics("test/s1", 1, ic=0.05, icir=0.8, annualized_return=0.12)
        exps = db.query_experiments("test/s1")
        assert exps[0]["ic"] == 0.05
        assert exps[0]["icir"] == 0.8
        assert exps[0]["annualized_return"] == 0.12

    def test_update_experiment_decision(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)
        db.update_experiment_decision("test/s1", 1, decision=True, decision_reason="Good metrics")
        exps = db.query_experiments("test/s1")
        assert exps[0]["decision"] == 1
        assert exps[0]["decision_reason"] == "Good metrics"

    def test_finalize_experiment(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)
        db.finalize_experiment("test/s1", 1, status="completed")
        exps = db.query_experiments("test/s1")
        assert exps[0]["status"] == "completed"
        assert exps[0]["completed_at"] is not None

    def test_upsert_factor(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_factor(
            "test/s1", "factor_1",
            description="Test factor", formulation="Mean($close, 5)",
            ic=0.03,
        )
        factors = db.query_factors("test/s1")
        assert len(factors) == 1
        assert factors[0]["name"] == "factor_1"
        assert factors[0]["ic"] == 0.03

    def test_upsert_factor_idempotent(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_factor("test/s1", "f1", ic=0.03)
        db.upsert_factor("test/s1", "f1", ic=0.05)
        factors = db.query_factors("test/s1")
        assert factors[0]["ic"] == 0.05

    def test_upsert_model(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_model(
            "test/s1", "model_1",
            model_type="lgbm",
            hyperparameters={"learning_rate": 0.1},
            annualized_return=0.15,
        )
        models = db.query_models("test/s1")
        assert len(models) == 1
        assert models[0]["name"] == "model_1"
        assert models[0]["model_type"] == "lgbm"

    def test_upsert_node(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        node_id = db.upsert_node("test/s1", 1, "direct_exp_gen", status="running")
        assert node_id > 0
        nodes = db.query_pipeline("test/s1")
        assert len(nodes) == 1
        assert nodes[0]["step_name"] == "direct_exp_gen"
        assert nodes[0]["status"] == "running"

    def test_upsert_node_update(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_node("test/s1", 1, "coding", status="running")
        db.upsert_node("test/s1", 1, "coding", status="completed", duration_ms=1500)
        nodes = db.query_pipeline("test/s1")
        assert nodes[0]["status"] == "completed"
        assert nodes[0]["duration_ms"] == 1500

    def test_cross_strategy_factors(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_strategy("test/s2")
        db.upsert_factor("test/s1", "f1", ic=0.03)
        db.upsert_factor("test/s2", "f2", ic=0.05)
        all_factors = db.query_factors()
        assert len(all_factors) == 2

    def test_cross_strategy_models(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_strategy("test/s2")
        db.upsert_model("test/s1", "m1")
        db.upsert_model("test/s2", "m2")
        all_models = db.query_models()
        assert len(all_models) == 2

    def test_delete_strategy_cascade(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)
        db.upsert_factor("test/s1", "f1")
        db.upsert_model("test/s1", "m1")
        db.upsert_node("test/s1", 1, "direct_exp_gen")

        db.delete_strategy("test/s1")
        assert db.query_strategy("test/s1") is None
        assert db.query_experiments("test/s1") == []
        assert db.query_factors("test/s1") == []

    def test_reports_query(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1, type="alpha", ic=0.05, annualized_return=0.12)
        db.upsert_experiment("test/s1", 2, type="model", ic=0.03, annualized_return=0.08)
        reports = db.query_reports("test/s1")
        assert len(reports) == 2
        assert reports[0]["loop_id"] == 1

    def test_update_strategy_status(self):
        db = get_db()
        db.upsert_strategy("test/s1", status="running")
        db.update_strategy_status("test/s1", "completed")
        s = db.query_strategy("test/s1")
        assert s["status"] == "completed"

    def test_update_factor_status(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_factor("test/s1", "f1")
        db.update_factor_status("test/s1", "f1", "sota")
        factors = db.query_factors("test/s1")
        assert factors[0]["status"] == "sota"

    def test_update_model_status(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_model("test/s1", "m1")
        db.update_model_status("test/s1", "m1", "sota")
        models = db.query_models("test/s1")
        assert models[0]["status"] == "sota"

    def test_node_prompt_tokens(self):
        db = get_db()
        db.upsert_strategy("test/s1")
        db.upsert_node("test/s1", 1, "coding", status="completed", prompt_tokens=500, completion_tokens=200, call_count=3)
        nodes = db.query_pipeline("test/s1")
        assert nodes[0]["prompt_tokens"] == 500
        assert nodes[0]["completion_tokens"] == 200
        assert nodes[0]["call_count"] == 3

    def test_lazy_strategy_creation(self):
        """upsert_experiment/factor/model should auto-create strategy row."""
        db = get_db()
        # No explicit upsert_strategy call
        db.upsert_experiment("auto/s1", 1, type="alpha")
        s = db.query_strategy("auto/s1")
        assert s is not None
        assert s["id"] == "auto/s1"