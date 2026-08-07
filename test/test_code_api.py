"""Tests for the Research API code endpoint (GET /api/strategies/:id/code)."""

import pytest

# Patch the DB path before importing ResearchDB (same pattern as test_chart_api.py)
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


class TestCodeApi:
    def test_code_returns_factor_file(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        code_file = tmp_path / "factor.py"
        code_file.write_text("def alpha001():\n    return 1\n", encoding="utf-8")

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_factor("test/s1", "Alpha001", code_path=str(code_file))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()

        resp = client.get("/api/strategies/test/s1/code?name=Alpha001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Alpha001"
        assert "def alpha001" in data["code"]

    def test_code_unknown_name_404(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        code_file = tmp_path / "factor.py"
        code_file.write_text("def alpha001():\n    return 1\n", encoding="utf-8")

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_factor("test/s1", "Alpha001", code_path=str(code_file))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()

        resp = client.get("/api/strategies/test/s1/code?name=Nope")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_code_missing_file_404(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_factor("test/s1", "Alpha001", code_path=str(tmp_path / "missing.py"))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()

        resp = client.get("/api/strategies/test/s1/code?name=Alpha001")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_code_model_fallback(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        code_file = tmp_path / "model.py"
        code_file.write_text("def train():\n    pass\n", encoding="utf-8")

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_model("test/s1", "ModelX", code_path=str(code_file))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()

        resp = client.get("/api/strategies/test/s1/code?name=ModelX")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "ModelX"
        assert "def train" in data["code"]

    def test_code_type_disambiguates_shared_name(self, tmp_path):
        """When a factor and model share a name, the type param picks the right one."""
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        factor_file = tmp_path / "factor.py"
        factor_file.write_text("# factor code\n", encoding="utf-8")
        model_file = tmp_path / "model.py"
        model_file.write_text("# model code\n", encoding="utf-8")

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_factor("test/s1", "Alpha001", code_path=str(factor_file))
        db.upsert_model("test/s1", "Alpha001", code_path=str(model_file))

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()

        resp_factor = client.get("/api/strategies/test/s1/code?name=Alpha001&type=factor")
        assert resp_factor.status_code == 200
        assert "factor code" in resp_factor.get_json()["code"]

        resp_model = client.get("/api/strategies/test/s1/code?name=Alpha001&type=model")
        assert resp_model.status_code == 200
        assert "model code" in resp_model.get_json()["code"]

        # without type, factors are searched first -> factor wins
        resp_default = client.get("/api/strategies/test/s1/code?name=Alpha001")
        assert resp_default.status_code == 200
        assert "factor code" in resp_default.get_json()["code"]

    def test_code_without_name_returns_first_code_bearing_row(self, tmp_path):
        from flask import Flask

        from rdagent.log.research_db import ResearchDB
        from rdagent.log.server.research_api import research_bp

        code_file = tmp_path / "factor.py"
        code_file.write_text("def alpha001():\n    return 1\n", encoding="utf-8")

        db = ResearchDB()
        db.upsert_strategy("test/s1")
        db.upsert_factor("test/s1", "Alpha001", code_path=str(code_file))
        db.upsert_factor("test/s1", "NoCode")

        app = Flask(__name__)
        app.register_blueprint(research_bp)
        client = app.test_client()

        resp = client.get("/api/strategies/test/s1/code")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Alpha001"