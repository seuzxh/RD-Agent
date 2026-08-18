"""
ResearchDB — SQLite persistence layer for Strategy domain objects.

Global singleton (module-level ``_instance`` + ``ResearchDB()`` constructor).
WAL mode, foreign keys, bare sqlite3 — zero extra dependencies.

Usage::

    from rdagent.log.research_db import ResearchDB

    db = ResearchDB()  # returns singleton, creates tables on first call
    db.upsert_strategy("id", {"description": "..."})
    strategies = db.query_strategies()
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RESEARCH_DB_PATH: str = "./research.db"
_instance: "ResearchDB | None" = None
_lock = threading.Lock()

# ── DDL ──────────────────────────────────────────────────────────

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    description TEXT,
    scenario TEXT,
    source TEXT DEFAULT 'webui',
    status TEXT DEFAULT 'running',
    created_at TEXT,
    updated_at TEXT,
    user_input_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    loop_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    hypothesis_text TEXT,
    hypothesis_reason TEXT,
    hypothesis_assumption TEXT,
    decision BOOLEAN,
    decision_reason TEXT,
    observations TEXT,
    ic REAL, icir REAL,
    annualized_return REAL,
    max_drawdown REAL,
    information_ratio REAL,
    workspace_path TEXT,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    chart_path TEXT,
    UNIQUE(strategy_id, loop_id)
);

CREATE TABLE IF NOT EXISTS factors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER REFERENCES experiments(id) ON DELETE SET NULL,
    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    formulation TEXT,
    variables TEXT,
    code_path TEXT,
    status TEXT DEFAULT 'active',
    round_number INTEGER,
    created_at TEXT,
    ic REAL, icir REAL,
    annualized_return REAL,
    max_drawdown REAL,
    information_ratio REAL,
    UNIQUE(strategy_id, name)
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER REFERENCES experiments(id) ON DELETE SET NULL,
    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    model_type TEXT,
    architecture TEXT,
    hyperparameters TEXT,
    code_path TEXT,
    status TEXT DEFAULT 'active',
    round_number INTEGER,
    created_at TEXT,
    annualized_return REAL,
    max_drawdown REAL,
    information_ratio REAL,
    UNIQUE(strategy_id, name)
);

CREATE TABLE IF NOT EXISTS pipeline_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    experiment_id INTEGER REFERENCES experiments(id) ON DELETE SET NULL,
    loop_id INTEGER NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    parent_node_id INTEGER REFERENCES pipeline_nodes(id) ON DELETE SET NULL,
    input_summary TEXT,
    output_summary TEXT,
    artifact_refs TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    error_message TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    call_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_experiments_strategy ON experiments(strategy_id);
CREATE INDEX IF NOT EXISTS idx_factors_strategy ON factors(strategy_id);
CREATE INDEX IF NOT EXISTS idx_factors_experiment ON factors(experiment_id);
CREATE INDEX IF NOT EXISTS idx_models_strategy ON models(strategy_id);
CREATE INDEX IF NOT EXISTS idx_models_experiment ON models(experiment_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_strategy ON pipeline_nodes(strategy_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_experiment ON pipeline_nodes(experiment_id);
"""


# ── Helpers ──────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _j(value: Any) -> str | None:
    """Serialize to JSON, returning None for None input."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _ensure_strategy_exists(cur: sqlite3.Cursor, strategy_id: str) -> None:
    """Lazily create a strategy row if it doesn't exist yet (INSERT OR IGNORE)."""
    cur.execute(
        """INSERT OR IGNORE INTO strategies (id, created_at, updated_at)
           VALUES (?, ?, ?)""",
        (strategy_id, _now(), _now()),
    )


# ── ResearchDB ───────────────────────────────────────────────────


class ResearchDB:
    """Global singleton SQLite persistence for Strategy domain objects.

    Thread-safe via ``threading.Lock`` on write operations.
    WAL mode allows concurrent reads without blocking.
    """

    def __new__(cls) -> "ResearchDB":
        global _instance
        if _instance is None:
            with _lock:
                if _instance is None:
                    obj = super().__new__(cls)
                    obj._conn = None  # type: ignore[attr-defined]
                    obj._init_db()  # type: ignore[attr-defined]
                    _instance = obj
        return _instance

    # ── connection management ──

    def _init_db(self) -> None:
        db_path = Path(_RESEARCH_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(DDL)

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._init_db()
        return self._conn  # type: ignore[return-value]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── strategies ──

    def upsert_strategy(
        self,
        strategy_id: str,
        *,
        description: str | None = None,
        scenario: str | None = None,
        source: str | None = None,
        status: str | None = None,
        user_input_snapshot: dict | None = None,
    ) -> None:
        now = _now()
        with _lock:
            self.conn.execute(
                """INSERT INTO strategies (id, description, scenario, source, status, created_at, updated_at, user_input_snapshot)
                   VALUES (?, ?, ?, ?, COALESCE(?, 'running'), ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       description = COALESCE(? , description),
                       scenario    = COALESCE(?, scenario),
                       source      = COALESCE(?, source),
                       status      = CASE WHEN status IN ('completed', 'failed') THEN status
                                          ELSE COALESCE(?, status) END,
                       updated_at  = ?,
                       user_input_snapshot = COALESCE(?, user_input_snapshot)""",
                (
                    strategy_id, description, scenario, source, status, now, now, _j(user_input_snapshot),
                    description, scenario, source, status, now, _j(user_input_snapshot),
                ),
            )
            self.conn.commit()

    def update_strategy_status(self, strategy_id: str, status: str) -> None:
        with _lock:
            self.conn.execute(
                "UPDATE strategies SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), strategy_id),
            )
            self.conn.commit()

    def delete_strategy(self, strategy_id: str) -> None:
        with _lock:
            self.conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
            self.conn.commit()

    # ── experiments ──

    def upsert_experiment(
        self,
        strategy_id: str,
        loop_id: int,
        *,
        type: str = "alpha",
        status: str = "running",
        hypothesis_text: str | None = None,
        hypothesis_reason: str | None = None,
        hypothesis_assumption: str | None = None,
        decision: bool | None = None,
        decision_reason: str | None = None,
        observations: str | None = None,
        ic: float | None = None,
        icir: float | None = None,
        annualized_return: float | None = None,
        max_drawdown: float | None = None,
        information_ratio: float | None = None,
        workspace_path: str | None = None,
        error_message: str | None = None,
    ) -> int:
        now = _now()
        with _lock:
            _ensure_strategy_exists(self.conn.cursor(), strategy_id)
            cur = self.conn.execute(
                """INSERT INTO experiments (strategy_id, loop_id, type, status, hypothesis_text, hypothesis_reason,
                       hypothesis_assumption, decision, decision_reason, observations,
                       ic, icir, annualized_return, max_drawdown, information_ratio,
                       workspace_path, started_at, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_id, loop_id) DO UPDATE SET
                       type = COALESCE(?, type),
                       status = COALESCE(?, status),
                       hypothesis_text = COALESCE(?, hypothesis_text),
                       hypothesis_reason = COALESCE(?, hypothesis_reason),
                       hypothesis_assumption = COALESCE(?, hypothesis_assumption),
                       decision = COALESCE(?, decision),
                       decision_reason = COALESCE(?, decision_reason),
                       observations = COALESCE(?, observations),
                       ic = COALESCE(?, ic),
                       icir = COALESCE(?, icir),
                       annualized_return = COALESCE(?, annualized_return),
                       max_drawdown = COALESCE(?, max_drawdown),
                       information_ratio = COALESCE(?, information_ratio),
                       workspace_path = COALESCE(?, workspace_path),
                       error_message = COALESCE(?, error_message)""",
                (
                    strategy_id, loop_id, type, status,
                    hypothesis_text, hypothesis_reason, hypothesis_assumption,
                    decision, decision_reason, observations,
                    ic, icir, annualized_return, max_drawdown, information_ratio,
                    workspace_path, now, error_message,
                    # ON CONFLICT update
                    type, status, hypothesis_text, hypothesis_reason, hypothesis_assumption,
                    decision, decision_reason, observations,
                    ic, icir, annualized_return, max_drawdown, information_ratio,
                    workspace_path, error_message,
                ),
            )
            self.conn.commit()
            return cur.lastrowid or 0

    def update_experiment_metrics(
        self,
        strategy_id: str,
        loop_id: int,
        *,
        ic: float | None = None,
        icir: float | None = None,
        annualized_return: float | None = None,
        max_drawdown: float | None = None,
        information_ratio: float | None = None,
    ) -> None:
        with _lock:
            self.conn.execute(
                """UPDATE experiments SET
                       ic = COALESCE(?, ic),
                       icir = COALESCE(?, icir),
                       annualized_return = COALESCE(?, annualized_return),
                       max_drawdown = COALESCE(?, max_drawdown),
                       information_ratio = COALESCE(?, information_ratio)
                   WHERE strategy_id = ? AND loop_id = ?""",
                (ic, icir, annualized_return, max_drawdown, information_ratio, strategy_id, loop_id),
            )
            self.conn.commit()

    def update_experiment_decision(
        self,
        strategy_id: str,
        loop_id: int,
        *,
        decision: bool,
        decision_reason: str | None = None,
        observations: str | None = None,
    ) -> None:
        with _lock:
            self.conn.execute(
                "UPDATE experiments SET decision = ?, decision_reason = ?, observations = ? WHERE strategy_id = ? AND loop_id = ?",
                (decision, decision_reason, observations, strategy_id, loop_id),
            )
            self.conn.commit()

    def upsert_experiment_chart_path(self, strategy_id: str, loop_id: int, chart_path: str) -> None:
        with _lock:
            self.conn.execute(
                "UPDATE experiments SET chart_path = ? WHERE strategy_id = ? AND loop_id = ?",
                (chart_path, strategy_id, loop_id),
            )
            self.conn.commit()

    def finalize_experiment(
        self,
        strategy_id: str,
        loop_id: int,
        *,
        status: str = "completed",
        error_message: str | None = None,
    ) -> None:
        with _lock:
            self.conn.execute(
                "UPDATE experiments SET status = ?, completed_at = ?, error_message = ? WHERE strategy_id = ? AND loop_id = ?",
                (status, _now(), error_message, strategy_id, loop_id),
            )
            self.conn.commit()

    # ── factors ──

    def upsert_factor(
        self,
        strategy_id: str,
        name: str,
        *,
        experiment_id: int | None = None,
        description: str | None = None,
        formulation: str | None = None,
        variables: dict | None = None,
        code_path: str | None = None,
        status: str | None = "active",
        round_number: int | None = None,
        ic: float | None = None,
        icir: float | None = None,
        annualized_return: float | None = None,
        max_drawdown: float | None = None,
        information_ratio: float | None = None,
    ) -> None:
        now = _now()
        with _lock:
            _ensure_strategy_exists(self.conn.cursor(), strategy_id)
            self.conn.execute(
                """INSERT INTO factors (strategy_id, experiment_id, name, description, formulation, variables,
                       code_path, status, round_number, created_at,
                       ic, icir, annualized_return, max_drawdown, information_ratio)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_id, name) DO UPDATE SET
                       experiment_id = COALESCE(?, experiment_id),
                       description = COALESCE(?, description),
                       formulation = COALESCE(?, formulation),
                       variables = COALESCE(?, variables),
                       code_path = COALESCE(?, code_path),
                       status = COALESCE(?, status),
                       round_number = COALESCE(?, round_number),
                       ic = COALESCE(?, ic),
                       icir = COALESCE(?, icir),
                       annualized_return = COALESCE(?, annualized_return),
                       max_drawdown = COALESCE(?, max_drawdown),
                       information_ratio = COALESCE(?, information_ratio)""",
                (
                    strategy_id, experiment_id, name, description, formulation, _j(variables),
                    code_path, status, round_number, now,
                    ic, icir, annualized_return, max_drawdown, information_ratio,
                    # ON CONFLICT update
                    experiment_id, description, formulation, _j(variables),
                    code_path, status, round_number,
                    ic, icir, annualized_return, max_drawdown, information_ratio,
                ),
            )
            self.conn.commit()

    def update_factor_status(self, strategy_id: str, name: str, status: str) -> None:
        with _lock:
            self.conn.execute(
                "UPDATE factors SET status = ? WHERE strategy_id = ? AND name = ?",
                (status, strategy_id, name),
            )
            self.conn.commit()

    def update_factors_metrics_for_loop(
        self,
        strategy_id: str,
        loop_id: int,
        *,
        ic: float | None = None,
        icir: float | None = None,
        annualized_return: float | None = None,
        max_drawdown: float | None = None,
        information_ratio: float | None = None,
    ) -> None:
        """Update metrics for all factors in a specific loop (round_number = loop_id)."""
        with _lock:
            self.conn.execute(
                """UPDATE factors SET
                       ic = COALESCE(?, ic),
                       icir = COALESCE(?, icir),
                       annualized_return = COALESCE(?, annualized_return),
                       max_drawdown = COALESCE(?, max_drawdown),
                       information_ratio = COALESCE(?, information_ratio)
                   WHERE strategy_id = ? AND round_number = ?""",
                (ic, icir, annualized_return, max_drawdown, information_ratio, strategy_id, loop_id),
            )
            self.conn.commit()

    # ── models ──

    def upsert_model(
        self,
        strategy_id: str,
        name: str,
        *,
        experiment_id: int | None = None,
        model_type: str | None = None,
        architecture: str | None = None,
        hyperparameters: dict | None = None,
        code_path: str | None = None,
        status: str | None = "active",
        round_number: int | None = None,
        annualized_return: float | None = None,
        max_drawdown: float | None = None,
        information_ratio: float | None = None,
    ) -> None:
        now = _now()
        with _lock:
            _ensure_strategy_exists(self.conn.cursor(), strategy_id)
            self.conn.execute(
                """INSERT INTO models (strategy_id, experiment_id, name, model_type, architecture, hyperparameters,
                       code_path, status, round_number, created_at,
                       annualized_return, max_drawdown, information_ratio)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_id, name) DO UPDATE SET
                       experiment_id = COALESCE(?, experiment_id),
                       model_type = COALESCE(?, model_type),
                       architecture = COALESCE(?, architecture),
                       hyperparameters = COALESCE(?, hyperparameters),
                       code_path = COALESCE(?, code_path),
                       status = COALESCE(?, status),
                       round_number = COALESCE(?, round_number),
                       annualized_return = COALESCE(?, annualized_return),
                       max_drawdown = COALESCE(?, max_drawdown),
                       information_ratio = COALESCE(?, information_ratio)""",
                (
                    strategy_id, experiment_id, name, model_type, architecture, _j(hyperparameters),
                    code_path, status, round_number, now,
                    annualized_return, max_drawdown, information_ratio,
                    # ON CONFLICT update
                    experiment_id, model_type, architecture, _j(hyperparameters),
                    code_path, status, round_number,
                    annualized_return, max_drawdown, information_ratio,
                ),
            )
            self.conn.commit()

    def update_model_status(self, strategy_id: str, name: str, status: str) -> None:
        with _lock:
            self.conn.execute(
                "UPDATE models SET status = ? WHERE strategy_id = ? AND name = ?",
                (status, strategy_id, name),
            )
            self.conn.commit()

    def deprecate_active_models(self, strategy_id: str) -> None:
        """Demote every still-active model of a strategy to ``deprecated``.

        Used on run failure (``on_run_failed``) so a crash that interrupts the
        loop before the record step does not leave ``active`` models behind —
        those models were registered during coding but never finalized.
        """
        with _lock:
            self.conn.execute(
                "UPDATE models SET status = 'deprecated' WHERE strategy_id = ? AND status = 'active'",
                (strategy_id,),
            )
            self.conn.commit()

    def update_model_metrics(
        self,
        strategy_id: str,
        name: str,
        *,
        annualized_return: float | None = None,
        max_drawdown: float | None = None,
        information_ratio: float | None = None,
    ) -> None:
        """Update metrics for a single model row matched by (strategy_id, name).

        Targets an exact row by name (not round_number) to avoid collisions when
        a fin_model downstream model shares a strategy_id with the parent's own
        models of the same round.
        """
        with _lock:
            self.conn.execute(
                """UPDATE models SET
                       annualized_return = COALESCE(?, annualized_return),
                       max_drawdown = COALESCE(?, max_drawdown),
                       information_ratio = COALESCE(?, information_ratio)
                   WHERE strategy_id = ? AND name = ?""",
                (annualized_return, max_drawdown, information_ratio, strategy_id, name),
            )
            self.conn.commit()

    # ── pipeline_nodes ──

    def upsert_node(
        self,
        strategy_id: str,
        loop_id: int,
        step_name: str,
        *,
        experiment_id: int | None = None,
        status: str = "pending",
        input_summary: dict | None = None,
        output_summary: dict | None = None,
        artifact_refs: dict | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        call_count: int = 0,
    ) -> int:
        now = _now()
        started = now if status == "running" else None
        completed = now if status in ("completed", "failed") else None
        with _lock:
            _ensure_strategy_exists(self.conn.cursor(), strategy_id)
            # Check if node already exists for this (strategy, loop, step)
            row = self.conn.execute(
                "SELECT id FROM pipeline_nodes WHERE strategy_id = ? AND loop_id = ? AND step_name = ?",
                (strategy_id, loop_id, step_name),
            ).fetchone()
            if row:
                node_id = row[0]
                self.conn.execute(
                    """UPDATE pipeline_nodes SET
                           status = ?, experiment_id = ?,
                           input_summary = COALESCE(?, input_summary),
                           output_summary = COALESCE(?, output_summary),
                           artifact_refs = COALESCE(?, artifact_refs),
                           duration_ms = COALESCE(?, duration_ms),
                           error_message = COALESCE(?, error_message),
                           prompt_tokens = ?, completion_tokens = ?, call_count = ?,
                           completed_at = COALESCE(?, completed_at)
                       WHERE id = ?""",
                    (
                        status, experiment_id,
                        _j(input_summary), _j(output_summary), _j(artifact_refs),
                        duration_ms, error_message,
                        prompt_tokens, completion_tokens, call_count,
                        completed, node_id,
                    ),
                )
            else:
                cur = self.conn.execute(
                    """INSERT INTO pipeline_nodes (strategy_id, experiment_id, loop_id, step_name, status,
                           input_summary, output_summary, artifact_refs,
                           started_at, completed_at, duration_ms, error_message,
                           prompt_tokens, completion_tokens, call_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        strategy_id, experiment_id, loop_id, step_name, status,
                        _j(input_summary), _j(output_summary), _j(artifact_refs),
                        started, completed, duration_ms, error_message,
                        prompt_tokens, completion_tokens, call_count,
                    ),
                )
                node_id = cur.lastrowid or 0
            self.conn.commit()
            return node_id

    # ── queries ──

    def _query_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute SQL, return list of dicts keyed by column name."""
        cur = self.conn.execute(sql, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute SQL, return single dict or None."""
        cur = self.conn.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))

    def query_strategies(self) -> list[dict[str, Any]]:
        return self._query_all(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM experiments e WHERE e.strategy_id = s.id) as total_experiments,
                      (SELECT COUNT(*) FROM factors f WHERE f.strategy_id = s.id) as total_factors,
                      (SELECT COUNT(*) FROM models m WHERE m.strategy_id = s.id) as total_models
               FROM strategies s ORDER BY s.created_at DESC"""
        )

    def query_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        return self._query_one("SELECT * FROM strategies WHERE id = ?", (strategy_id,))

    def query_experiments(self, strategy_id: str) -> list[dict[str, Any]]:
        return self._query_all(
            "SELECT * FROM experiments WHERE strategy_id = ? ORDER BY loop_id ASC",
            (strategy_id,),
        )

    def query_factors(self, strategy_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id = ?")
            params.append(strategy_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        sql = "SELECT * FROM factors"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        return self._query_all(sql, tuple(params))

    def query_factor_experiments(self, strategy_id: str) -> list[dict[str, Any]]:
        """Return the session's factor (alpha) experiments, including workspace_path.

        Used to locate the persisted ``combined_factors_df.parquet`` files whose
        values are merged into the session's cumulative factor frame.
        """
        return self._query_all(
            """SELECT * FROM experiments
               WHERE strategy_id = ? AND type = 'alpha'
               ORDER BY loop_id ASC""",
            (strategy_id,),
        )

    def query_models(self, strategy_id: str | None = None) -> list[dict[str, Any]]:
        if strategy_id:
            return self._query_all(
                "SELECT * FROM models WHERE strategy_id = ? ORDER BY created_at DESC",
                (strategy_id,),
            )
        return self._query_all("SELECT * FROM models ORDER BY created_at DESC")

    def query_pipeline(self, strategy_id: str) -> list[dict[str, Any]]:
        return self._query_all(
            "SELECT * FROM pipeline_nodes WHERE strategy_id = ? ORDER BY id ASC",
            (strategy_id,),
        )

    def query_reports(self, strategy_id: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT id, strategy_id, loop_id, type, status, decision,
                        hypothesis_text, ic, icir, annualized_return, max_drawdown, information_ratio,
                        workspace_path, started_at, completed_at
                 FROM experiments"""
        if strategy_id:
            return self._query_all(sql + " WHERE strategy_id = ? ORDER BY loop_id ASC", (strategy_id,))
        return self._query_all(sql + " ORDER BY strategy_id, loop_id ASC")