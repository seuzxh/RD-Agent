"""
Research API — REST + SSE endpoints backed by ResearchDB (SQLite).

Registered as a Flask Blueprint at ``/api`` prefix.

Endpoints
---------
REST:
    GET    /api/strategies              — list all strategies
    GET    /api/strategies/:id          — strategy detail
    GET    /api/strategies/:id/factors  — strategy's factors
    GET    /api/strategies/:id/models   — strategy's models
    GET    /api/strategies/:id/pipeline — strategy's pipeline nodes
    GET    /api/strategies/:id/report   — strategy's experiment report
    GET    /api/strategies/:id/chart    — strategy's backtest chart HTML
    GET    /api/strategies/:id/code     — factor/model source code via code_path
    DELETE /api/strategies/:id          — delete strategy + cascade
    GET    /api/factors                 — cross-strategy factors
    GET    /api/models                  — cross-strategy models
    GET    /api/reports                 — cross-strategy report aggregation

SSE:
    GET    /api/strategies/:id/events   — real-time event stream
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from rdagent.log.research_db import ResearchDB

research_bp = Blueprint("research", __name__, url_prefix="/api")

# ── SSE subscription registry ──

_sse_subscribers: dict[str, set] = {}  # strategy_id -> set of queue-like buffers


def sse_broadcast(strategy_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an SSE event to all subscribers of a strategy.

    Called by WorkflowTracker.on_step_complete after writing to ResearchDB.
    """
    event_data = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    message = f"event: {event_type}\ndata: {event_data}\n\n"
    subscribers = _sse_subscribers.get(strategy_id)
    if subscribers is not None:
        dead = set()
        for buf in subscribers:
            try:
                buf.put_nowait(message)
            except Exception:
                dead.add(buf)
        subscribers -= dead


# ── helpers ──


def _db() -> ResearchDB:
    return ResearchDB()


def _json_resp(data: Any, status: int = 200):
    return jsonify(data), status


def _error(msg: str, status: int = 404):
    return jsonify({"error": msg}), status


def _safe_json(obj: Any) -> Any:
    """Recursively convert an object to JSON-safe types."""
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_safe_json(item) for item in obj]
    elif isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    else:
        return str(obj)


# ── REST endpoints ──


@research_bp.route("/strategies", methods=["GET"])
def list_strategies():
    """Return all strategies with summary stats."""
    return _json_resp(_db().query_strategies())


@research_bp.route("/strategies/<path:strategy_id>", methods=["GET"])
def get_strategy(strategy_id: str):
    """Return strategy detail with experiments."""
    s = _db().query_strategy(strategy_id)
    if s is None:
        return _error("Strategy not found")
    s["experiments"] = _db().query_experiments(strategy_id)
    return _json_resp(s)


@research_bp.route("/strategies/<path:strategy_id>/factors", methods=["GET"])
def get_strategy_factors(strategy_id: str):
    """Return strategy's factors."""
    return _json_resp(_db().query_factors(strategy_id))


@research_bp.route("/strategies/<path:strategy_id>/models", methods=["GET"])
def get_strategy_models(strategy_id: str):
    """Return strategy's models."""
    return _json_resp(_db().query_models(strategy_id))


@research_bp.route("/strategies/<path:strategy_id>/pipeline", methods=["GET"])
def get_strategy_pipeline(strategy_id: str):
    """Return strategy's pipeline nodes."""
    return _json_resp(_db().query_pipeline(strategy_id))


@research_bp.route("/strategies/<path:strategy_id>/report", methods=["GET"])
def get_strategy_report(strategy_id: str):
    """Return strategy's experiment report (metrics trend)."""
    reports = _db().query_reports(strategy_id)
    if not reports:
        return _error("No reports found for this strategy")
    return _json_resp({
        "strategy_id": strategy_id,
        "total_rounds": len(reports),
        "experiments": reports,
        "summary_metrics": reports[-1] if reports else {},
    })


@research_bp.route("/strategies/<path:strategy_id>/chart", methods=["GET"])
def get_strategy_chart(strategy_id: str):
    """Return the strategy's backtest chart HTML for a given loop (default latest).

    Query params:
        loop: loop_id to fetch; if omitted, the latest experiment with a chart is returned.
    """
    loop = request.args.get("loop")
    exps = _db().query_experiments(strategy_id)
    target = next(
        (e for e in exps if (loop is None or str(e["loop_id"]) == loop) and e.get("chart_path")),
        None,
    )
    if not target:
        return _error("No chart available")
    chart_path = Path(target["chart_path"])
    if not chart_path.exists():
        return _error("Chart file missing")
    return send_file(str(chart_path), mimetype="text/html")


@research_bp.route("/strategies/<path:strategy_id>/code", methods=["GET"])
def get_strategy_code(strategy_id: str):
    """Return the source code of a factor or model via its code_path.

    Query params:
        name: factor/model name to fetch; if omitted, the first code-bearing
              row is returned.
        type: "factor" or "model" to restrict the search to one table and
              disambiguate a name shared by both; if omitted, factors are
              searched first, then models.
    """
    name = request.args.get("name")
    type_ = request.args.get("type")
    db = _db()
    if type_ == "model":
        rows = db.query_models(strategy_id)
    elif type_ == "factor":
        rows = db.query_factors(strategy_id)
    else:
        rows = db.query_factors(strategy_id) + db.query_models(strategy_id)
    target = next(
        (r for r in rows if (name is None or r.get("name") == name) and r.get("code_path")),
        None,
    )
    if not target:
        return _error("No code available")
    code_path = Path(target["code_path"])
    if not code_path.exists():
        return _error("Code file missing")
    try:
        code = code_path.read_text(encoding="utf-8")
    except Exception:
        return _error("Code file missing")
    return _json_resp({"name": target.get("name"), "code": code})


@research_bp.route("/strategies/<path:strategy_id>", methods=["DELETE"])
def delete_strategy(strategy_id: str):
    """Delete a strategy and all cascade data."""
    _db().delete_strategy(strategy_id)
    return _json_resp({"status": "deleted", "id": strategy_id})


@research_bp.route("/factors", methods=["GET"])
def list_factors():
    """Cross-strategy factor query."""
    strategy_id = request.args.get("strategy_id")
    return _json_resp(_db().query_factors(strategy_id))


@research_bp.route("/models", methods=["GET"])
def list_models():
    """Cross-strategy model query."""
    strategy_id = request.args.get("strategy_id")
    return _json_resp(_db().query_models(strategy_id))


@research_bp.route("/reports", methods=["GET"])
def list_reports():
    """Cross-strategy report aggregation with per-strategy latest metrics."""
    db = _db()
    strategies = db.query_strategies()
    summaries = []
    for s in strategies:
        sid = s["id"]
        exps = db.query_experiments(sid)
        trend = []
        for e in exps:
            trend.append({
                "round": e.get("loop_id"),
                "ic": e.get("ic"),
                "icir": e.get("icir"),
                "annualized_return": e.get("annualized_return"),
                "max_drawdown": e.get("max_drawdown"),
                "information_ratio": e.get("information_ratio"),
            })
        latest = trend[-1] if trend else {}
        summaries.append({
            "id": sid,
            "description": s.get("description"),
            "total_rounds": len(exps),
            # Match the /chart endpoint's existence check so a chart-less or
            # file-cleaned strategy reports an empty state, not a broken iframe.
            "has_chart": any(e.get("chart_path") and Path(e["chart_path"]).exists() for e in exps),
            "metrics_trend": trend,
            "latest_metrics": latest,
        })
    return _json_resp({"strategies": summaries, "total_strategies": len(summaries)})


# ── SSE endpoint ──


@research_bp.route("/live", methods=["GET"])
def get_live():
    """Return all tasks (both running and completed) with their status."""
    from flask import current_app

    rdagent_processes = current_app.config.get("_RDAGENT_PROCESSES", {})
    trace_states = current_app.config.get("_TRACE_STATES", {})
    log_folder_path = Path(current_app.config.get("_LOG_FOLDER_PATH", "."))

    tasks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Running tasks from in-memory process registry
    for proc_id, proc in rdagent_processes.items():
        try:
            ext_id = str(Path(proc_id).relative_to(log_folder_path))
        except (ValueError, TypeError):
            ext_id = proc_id
        # Normalize path separators — trace_states uses forward slashes
        ext_id = ext_id.replace("\\", "/")
        seen_ids.add(ext_id)
        state = trace_states.get(ext_id, {})
        tasks.append({
            "id": ext_id,
            "status": "running" if proc.is_alive() else "completed",
            "loops": sorted(state.get("loops", [])),
            "created_at": state.get("created_at", ""),
            "updated_at": state.get("updated_at", ""),
            "description": state.get("description", ""),
        })

    # Also include tasks from trace_states that are not in rdagent_processes
    # (e.g. tasks where the subprocess has already exited but catalog state remains)
    for tid, state in trace_states.items():
        if tid not in seen_ids:
            seen_ids.add(tid)
            tasks.append({
                "id": tid,
                "status": state.get("status", "running"),
                "loops": sorted(state.get("loops", [])),
                "created_at": state.get("created_at", ""),
                "updated_at": state.get("updated_at", ""),
                "description": state.get("description", ""),
            })

    return _json_resp({"tasks": tasks, "total": len(tasks)})


@research_bp.route("/strategies/<path:strategy_id>/messages", methods=["GET"])
def get_strategy_messages(strategy_id: str):
    """Return trace messages for a strategy (replaces old POST /trace)."""
    from flask import current_app
    from rdagent.log.storage import FileStorage

    log_folder_path = Path(current_app.config.get("_LOG_FOLDER_PATH", "."))
    trace_dir = (log_folder_path / strategy_id).resolve()
    trace_dir_str = str(trace_dir)
    if not trace_dir.exists():
        return _error("Strategy trace directory not found")

    try:
        msgs = []
        for msg in FileStorage(trace_dir).iter_msg():
            ts = msg.timestamp
            if hasattr(ts, 'isoformat'):
                ts_str = ts.isoformat()
            elif isinstance(ts, str):
                ts_str = ts
            else:
                ts_str = str(ts)
            # Serialize content to JSON-safe format
            content = msg.content
            if isinstance(content, (dict, list)):
                # Use a safe JSON serialization for content
                content = _safe_json(content)
            else:
                content = str(content)[:200]
            msgs.append({
                "tag": msg.tag,
                "content": content,
                "timestamp": ts_str,
            })
        return _json_resp({"messages": msgs, "total": len(msgs), "trace_dir": trace_dir_str})
    except Exception as e:
        return _json_resp({"error": str(e), "trace_dir": trace_dir_str}, 500)


@research_bp.route("/strategies/<path:strategy_id>/detail", methods=["GET"])
def get_strategy_detail(strategy_id: str):
    """Return strategy detail with experiments, factors, and models."""
    s = _db().query_strategy(strategy_id)
    if s is None:
        return _error("Strategy not found in ResearchDB")

    s["experiments"] = _db().query_experiments(strategy_id)
    s["factors"] = _db().query_factors(strategy_id)
    s["models"] = _db().query_models(strategy_id)
    return _json_resp(s)


@research_bp.route("/strategies/<path:strategy_id>/events", methods=["GET"])
def strategy_events(strategy_id: str):
    """SSE event stream for a strategy.

    Events:
        node_update   — pipeline node status change
        metric_update — experiment metrics updated
        strategy_status — strategy-level status change
    """

    def generate() -> Generator[str, None, None]:
        # Use a simple list as a FIFO buffer (thread-safe enough for single-writer).
        import queue
        buf: queue.Queue = queue.Queue()

        # Register subscriber
        if strategy_id not in _sse_subscribers:
            _sse_subscribers[strategy_id] = set()
        _sse_subscribers[strategy_id].add(buf)

        # Send initial keepalive
        yield f"event: connected\ndata: {json.dumps({'strategy_id': strategy_id})}\n\n"

        try:
            while True:
                try:
                    message = buf.get(timeout=30)  # 30s heartbeat
                    yield message
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    yield f": heartbeat {time.time()}\n\n"
        except GeneratorExit:
            pass
        finally:
            # Unregister subscriber
            subscribers = _sse_subscribers.get(strategy_id)
            if subscribers is not None:
                subscribers.discard(buf)
                if not subscribers:
                    _sse_subscribers.pop(strategy_id, None)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )