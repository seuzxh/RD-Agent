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
import uuid
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, request, stream_with_context

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
    """Cross-strategy report aggregation."""
    return _json_resp({
        "strategies": _db().query_reports(),
        "total_strategies": len(set(r["strategy_id"] for r in _db().query_reports())),
    })


# ── SSE endpoint ──


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