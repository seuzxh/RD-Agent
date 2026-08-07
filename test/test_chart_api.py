"""Tests for the shared chart HTML generator and the Research API chart endpoint."""

import pickle
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Patch the DB path before importing ResearchDB (same pattern as test_research_db.py)
import rdagent.log.research_db as research_db_module

research_db_module._RESEARCH_DB_PATH = ":memory:"


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the ResearchDB singleton before each test, using in-memory DB."""
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


def _make_ret_df(n: int = 20) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "return": [0.001 * (i % 3) for i in range(n)],
            "cost": [0.0001] * n,
            "bench": [0.0002] * n,
            "turnover": [0.1] * n,
        },
        index=index,
    )


def _make_group_df(n: int = 20) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame(
        {
            "Group1": list(range(n)),
            "Group2": list(range(n)),
            "Group3": list(range(n)),
            "Group4": list(range(n)),
            "Group5": list(range(n)),
            "long-short": list(range(n)),
        },
        index=index,
    )


class TestGenerateChartHtml:
    def test_generates_html_from_dataframe(self):
        from rdagent.log.ui.qlib_report_figure import generate_chart_html

        with tempfile.TemporaryDirectory() as tmp:
            ret_pkl = Path(tmp) / "ret.pkl"
            with open(ret_pkl, "wb") as f:
                pickle.dump(_make_ret_df(), f)
            html = generate_chart_html(ret_pkl)
            assert isinstance(html, str) and html
            assert "<div" in html
            assert "plotly" in html.lower()
            assert "plotly.min.js" in html  # CDN injected

    def test_generates_html_with_group(self):
        from rdagent.log.ui.qlib_report_figure import generate_chart_html

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ret_pkl = tmp / "ret.pkl"
            group_pkl = tmp / "ret_group.pkl"
            with open(ret_pkl, "wb") as f:
                pickle.dump(_make_ret_df(), f)
            with open(group_pkl, "wb") as f:
                pickle.dump(_make_group_df(), f)
            html = generate_chart_html(ret_pkl, group_pkl)
            assert isinstance(html, str) and html
            assert "<div" in html
            assert "long-short" in html  # group subplot present

    def test_handles_dict_ret_format(self):
        """app.py legacy format: the pkl is a dict {'ret': df, 'group': df}."""
        from rdagent.log.ui.qlib_report_figure import generate_chart_html

        with tempfile.TemporaryDirectory() as tmp:
            ret_pkl = Path(tmp) / "ret.pkl"
            with open(ret_pkl, "wb") as f:
                pickle.dump({"ret": _make_ret_df(), "group": _make_group_df()}, f)
            html = generate_chart_html(ret_pkl)
            assert isinstance(html, str) and html
            assert "<div" in html


class TestChartApi:
    def test_get_chart_returns_html(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)

        chart_file = tmp_path / "ret_chart.html"
        chart_file.write_text("<html><body>CHART</body></html>", encoding="utf-8")
        db.upsert_experiment_chart_path("test/s1", 1, str(chart_file))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()
        resp = client.get("/api/strategies/test/s1/chart")
        assert resp.status_code == 200
        assert resp.mimetype == "text/html"
        assert b"CHART" in resp.data

    def test_get_chart_loop_filter(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)
        db.upsert_experiment("test/s1", 2)

        chart_file = tmp_path / "ret_chart2.html"
        chart_file.write_text("<html>LOOP2</html>", encoding="utf-8")
        db.upsert_experiment_chart_path("test/s1", 2, str(chart_file))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()

        resp = client.get("/api/strategies/test/s1/chart?loop=2")
        assert resp.status_code == 200
        assert b"LOOP2" in resp.data

        # loop 1 has no chart
        resp = client.get("/api/strategies/test/s1/chart?loop=1")
        assert resp.status_code == 404

    def test_get_chart_missing_file_404(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)
        db.upsert_experiment_chart_path("test/s1", 1, str(tmp_path / "nonexistent.html"))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()
        resp = client.get("/api/strategies/test/s1/chart")
        assert resp.status_code == 404


class TestTrackerChartPersistence:
    """_on_running persists ret_chart.html into the experiment workspace and DB."""

    def test_on_running_persists_chart(self):
        import pandas as pd

        from rdagent.log.research_db import ResearchDB
        from rdagent.utils.workflow.tracking import WorkflowTracker

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)

        class _FakeWS:
            workspace_path = None

        class _FakeExp:
            result = None
            experiment_workspace = None

        with tempfile.TemporaryDirectory() as tmp:
            ws_path = Path(tmp) / "loop_1"
            ws_path.mkdir()
            ret_pkl = ws_path / "ret.pkl"
            with open(ret_pkl, "wb") as f:
                pickle.dump(_make_ret_df(), f)

            exp = _FakeExp()
            exp.result = pd.Series({"IC": 0.05, "ICIR": 0.8})
            exp.experiment_workspace = _FakeWS()
            exp.experiment_workspace.workspace_path = ws_path

            tracker = WorkflowTracker(None)
            tracker._on_running(db, "test/s1", 1, exp)

            # chart file written into workspace
            chart_file = ws_path / "ret_chart.html"
            assert chart_file.exists()
            assert "plotly.min.js" in chart_file.read_text(encoding="utf-8")

            # chart_path persisted to DB
            exps = db.query_experiments("test/s1")
            assert exps[0]["chart_path"] == str(chart_file)

    def test_on_running_persists_chart_without_metrics(self):
        """Chart persists even when exp.result is None (metrics not yet available)."""
        from rdagent.log.research_db import ResearchDB
        from rdagent.utils.workflow.tracking import WorkflowTracker

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_experiment("test/s1", 1)

        class _FakeWS:
            workspace_path = None

        class _FakeExp:
            result = None
            experiment_workspace = None

        with tempfile.TemporaryDirectory() as tmp:
            ws_path = Path(tmp) / "loop_1"
            ws_path.mkdir()
            with open(ws_path / "ret.pkl", "wb") as f:
                pickle.dump(_make_ret_df(), f)

            exp = _FakeExp()
            exp.result = None
            exp.experiment_workspace = _FakeWS()
            exp.experiment_workspace.workspace_path = ws_path

            tracker = WorkflowTracker(None)
            tracker._on_running(db, "test/s1", 1, exp)

            chart_file = ws_path / "ret_chart.html"
            assert chart_file.exists()
            exps = db.query_experiments("test/s1")
            assert exps[0]["chart_path"] == str(chart_file)