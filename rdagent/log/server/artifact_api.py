"""
Artifact aggregation API — provides cross-strategy views of research artifacts.

Endpoints:
- GET /api/strategies  — list all strategies with stats
- GET /api/alpha-lab  — aggregated factors across all strategies
- GET /api/model-lab  — aggregated models across all strategies
- GET /api/report     — cross-strategy comparison report
- GET /api/live       — running tasks status
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify

from rdagent.log.sota_query import load_strategy
from rdagent.log.ui.conf import UI_SETTING

logger = logging.getLogger(__name__)

artifact_bp = Blueprint("artifact", __name__, url_prefix="/api")

# Scan both the default log dir (existing sessions) and the app's trace dir (new tasks).
LOG_ROOTS: list[Path] = [
    Path(p).resolve()
    for p in [*UI_SETTING.default_log_folders, UI_SETTING.trace_folder]
]


# ── Helpers ──


def _is_trace_dir(d: Path) -> bool:
    """Check if a directory is a trace directory (not a scenario container)."""
    return d.is_dir() and d.name != "__session__" and d.name != "uploads" and not d.name.startswith(".")


def _discover_all_trace_dirs() -> list[Path]:
    """Scan all log directories for trace directories.

    A valid trace directory is one that either:
    - Has ``__session__/`` (completed experiment)
    - Has any ``.pkl`` files (running or pending experiment)
    - Has a ``Loop_*`` subdirectory (Loop has started)

    Scenario directories (containers of multiple traces like ``Finance Data Building/``)
    are NOT included — only their trace subdirectories are.
    """
    dirs: list[Path] = []
    seen: set[Path] = set()

    for log_root in LOG_ROOTS:
        if not log_root.exists():
            continue
        for entry in sorted(log_root.iterdir()):
            if not _is_trace_dir(entry) or entry in seen:
                continue

            # Check if entry itself is a trace dir
            if _is_trace(entry):
                dirs.append(entry)
                seen.add(entry)
                continue

            # Check if entry is a scenario dir containing trace subdirs
            subdirs = [s for s in sorted(entry.iterdir()) if _is_trace_dir(s)]
            trace_subdirs = [s for s in subdirs if _is_trace(s)]
            dirs.extend(trace_subdirs)
            seen.update(trace_subdirs)
            if trace_subdirs:
                seen.add(entry)  # Mark scenario as seen to avoid re-checking

    return dirs


def _is_trace(d: Path) -> bool:
    """Check if a directory is a trace (not a scenario container).

    A trace directory has at least one of:
    - ``__session__/`` subdirectory
    - ``Loop_*`` subdirectory (R&D Loop started)
    - ``*.pkl`` files directly in the directory (not in subdirectories)
    """
    if (d / "__session__").exists():
        return True
    if any(sub.name.startswith("Loop_") for sub in d.iterdir() if sub.is_dir()):
        return True
    if any(d.glob("*.pkl")):
        return True
    return False


def _load_strategy_safe(trace_dir: Path) -> dict[str, Any] | None:
    """Load strategy data from a trace directory, returning None on failure."""
    try:
        data = load_strategy(trace_dir)
        if data and "error" not in data:
            return data
    except Exception:
        pass
    return None


def _strategy_summary(data: dict[str, Any], trace_id: str, trace_dir: Path) -> dict[str, Any]:
    """Build a strategy summary dict from loaded strategy data."""
    exps = data.get("experiments", [])
    description = data.get("description", "") or ""
    if not description and exps:
        description = exps[0].get("hypothesis_text", "") or ""
    alpha_count = len(data.get("alpha_pool", {}).get("factors", {}))
    model_count = len(data.get("model_registry", {}).get("models", {}))
    last_round = exps[-1].get("round_number", 0) if exps else 0
    last_decision = exps[-1].get("decision", False) if exps else False

    return {
        "id": trace_id,
        "name": trace_id,
        "description": description[:120] if description else "",
        "timestamp": trace_dir.name,
        "created_at": trace_dir.name,
        "total_rounds": len(exps),
        "factor_count": alpha_count,
        "model_count": model_count,
        "last_round": last_round,
        "last_decision": last_decision,
        "status": "completed" if last_round > 0 else "running",
    }


def _discover_strategies() -> list[dict[str, Any]]:
    """Return all strategies (completed + running + pending)."""
    from rdagent.log.server.app import rdagent_processes, trace_states, log_folder_path

    strategies: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Running tasks from in-memory process registry
    for proc_id, proc in rdagent_processes.items():
        try:
            ext_id = str(Path(proc_id).relative_to(log_folder_path))
        except (ValueError, TypeError):
            ext_id = proc_id
        readable_id = ext_id.split("/")[-1] if "/" in ext_id else ext_id
        seen_ids.add(readable_id)
        state = trace_states.get(proc_id, {})
        strategies.append({
            "id": readable_id,
            "name": ext_id,
            "description": state.get("description", "") or ext_id,
            "timestamp": state.get("created_at", "") or ext_id.split("/")[-1],
            "created_at": state.get("created_at", ""),
            "total_rounds": len(state.get("loops", [])),
            "factor_count": 0,
            "model_count": 0,
            "last_round": 0,
            "last_decision": False,
            "status": "running" if proc.is_alive() else "completed",
        })

    # Completed + pending strategies from file system
    for trace_dir in _discover_all_trace_dirs():
        trace_id = trace_dir.name
        if trace_id in seen_ids:
            continue
        seen_ids.add(trace_id)

        if (trace_dir / "__session__").exists():
            data = _load_strategy_safe(trace_dir)
            if data is None:
                continue
            strategies.append(_strategy_summary(data, trace_id, trace_dir))
        else:
            has_loop = any(d.name.startswith("Loop_") for d in trace_dir.iterdir() if d.is_dir())
            strategies.append({
                "id": trace_id,
                "name": trace_id,
                "description": "",
                "timestamp": trace_dir.name,
                "created_at": trace_dir.name,
                "total_rounds": 0,
                "factor_count": 0,
                "model_count": 0,
                "last_round": 0,
                "last_decision": False,
                "status": "running" if has_loop else "pending",
            })

    # Sort by created_at descending (newest first)
    strategies.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return strategies


def _load_all_strategies() -> list[dict[str, Any]]:
    """Load all completed strategies and return their full data dicts."""
    results: list[dict[str, Any]] = []
    for trace_dir in _discover_all_trace_dirs():
        if not (trace_dir / "__session__").exists():
            continue
        data = _load_strategy_safe(trace_dir)
        if data is None:
            continue
        data["_id"] = trace_dir.name
        results.append(data)
    return results


# ── Routes ──


@artifact_bp.route("/strategies", methods=["GET"])
def list_strategies():
    """Return all strategies with summary stats."""
    return jsonify(_discover_strategies())


@artifact_bp.route("/strategies/<path:strategy_id>/detail", methods=["GET"])
def get_strategy_detail(strategy_id: str):
    """Return detailed strategy info including trace messages."""
    from rdagent.log.server.app import log_folder_path

    # Search all log roots for the strategy directory
    for log_root in LOG_ROOTS:
        for entry in sorted(log_root.iterdir()):
            if entry.name == strategy_id or entry.name == strategy_id.split("/")[-1]:
                if (entry / "__session__").exists():
                    data = _load_strategy_safe(entry)
                    if data:
                        data["_id"] = strategy_id
                        return jsonify(data)
    return jsonify({"error": "Strategy not found"}), 404


@artifact_bp.route("/strategies/<path:strategy_id>/messages", methods=["GET"])
def get_strategy_messages(strategy_id: str):
    """Return trace messages for a strategy (for Live Lab detail view)."""
    from rdagent.log.server.app import log_folder_path

    # Try to find the trace directory
    for log_root in LOG_ROOTS:
        for entry in sorted(log_root.iterdir()):
            if entry.name == strategy_id or entry.name == strategy_id.split("/")[-1]:
                # Load messages from FileStorage
                try:
                    from rdagent.log.storage import FileStorage
                    msgs = []
                    for msg in FileStorage(entry).iter_msg():
                        msgs.append({
                            "tag": msg.tag,
                            "content": str(msg.content)[:200] if not isinstance(msg.content, (dict, list)) else msg.content,
                            "timestamp": msg.timestamp.isoformat() if hasattr(msg.timestamp, 'isoformat') else str(msg.timestamp),
                        })
                    return jsonify({"messages": msgs, "total": len(msgs), "trace_dir": str(entry)})
                except Exception as e:
                    return jsonify({"error": str(e), "trace_dir": str(entry)}), 500
    return jsonify({"error": "Strategy not found"}), 404


@artifact_bp.route("/alpha-lab", methods=["GET"])
def get_alpha_lab():
    """Return aggregated factors across all completed strategies."""
    all_factors: list[dict[str, Any]] = []
    for data in _load_all_strategies():
        sid = data.get("_id", "")
        pool = data.get("alpha_pool", {})
        factors: dict = pool.get("factors", {})
        for fname, factor in factors.items():
            factor["_strategy_id"] = sid
            factor["_strategy_name"] = sid
            all_factors.append(factor)
    return jsonify({"factors": all_factors, "total": len(all_factors)})


@artifact_bp.route("/model-lab", methods=["GET"])
def get_model_lab():
    """Return aggregated models across all completed strategies."""
    all_models: list[dict[str, Any]] = []
    for data in _load_all_strategies():
        sid = data.get("_id", "")
        registry = data.get("model_registry", {})
        models: dict = registry.get("models", {})
        for mname, model in models.items():
            model["_strategy_id"] = sid
            model["_strategy_name"] = sid
            all_models.append(model)
    return jsonify({"models": all_models, "total": len(all_models)})


@artifact_bp.route("/report", methods=["GET"])
def get_report():
    """Return cross-strategy comparison report."""
    strategy_summaries: list[dict[str, Any]] = []
    for data in _load_all_strategies():
        sid = data.get("_id", "")
        exps = data.get("experiments", [])
        trend = []
        for exp in exps:
            fm = exp.get("factor_metrics") or {}
            sm = exp.get("strategy_metrics") or {}
            trend.append({
                "round": exp.get("round_number"),
                "ic": fm.get("ic"),
                "icir": fm.get("icir"),
                "annualized_return": sm.get("annualized_return"),
                "max_drawdown": sm.get("max_drawdown"),
                "information_ratio": sm.get("information_ratio"),
            })
        latest = trend[-1] if trend else {}
        strategy_summaries.append({
            "id": sid,
            "name": sid,
            "description": (exps[0].get("hypothesis_text", "") if exps else "")[:80],
            "total_rounds": len(exps),
            "metrics_trend": trend,
            "latest_metrics": latest,
        })
    return jsonify({"strategies": strategy_summaries, "total_strategies": len(strategy_summaries)})


@artifact_bp.route("/live", methods=["GET"])
def get_live():
    """Return all tasks (both running and completed) with their status."""
    from rdagent.log.server.app import rdagent_processes, trace_states, log_folder_path

    tasks: list[dict[str, Any]] = []

    # Running tasks from in-memory process registry
    for proc_id, proc in rdagent_processes.items():
        try:
            ext_id = str(Path(proc_id).relative_to(log_folder_path))
        except (ValueError, TypeError):
            ext_id = proc_id
        state = trace_states.get(proc_id, {})
        tasks.append({
            "id": ext_id,
            "status": "running" if proc.is_alive() else "completed",
            "loops": state.get("loops", []),
            "created_at": state.get("created_at", ""),
            "updated_at": state.get("updated_at", ""),
        })

    # Completed + pending tasks from file system
    seen = {t["id"] for t in tasks}
    for trace_dir in _discover_all_trace_dirs():
        trace_id = trace_dir.name
        full_id = str(trace_dir)
        if full_id in seen or trace_id in seen:
            continue
        seen.add(full_id)
        if (trace_dir / "__session__").exists():
            data = _load_strategy_safe(trace_dir)
            exps = data.get("experiments", []) if data else []
            status = "completed" if exps else "pending"
        else:
            has_loop = any(d.name.startswith("Loop_") for d in trace_dir.iterdir() if d.is_dir())
            status = "running" if has_loop else "pending"
        tasks.append({
            "id": trace_id,
            "status": status,
            "total_rounds": 0,
            "loops": [],
            "created_at": trace_dir.name,
            "updated_at": "",
        })

    return jsonify({"tasks": tasks, "total": len(tasks)})