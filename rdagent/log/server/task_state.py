"""Durable lifecycle state for multialpha WebUI tasks.

Trace pickle files describe experiment progress.  This sidecar describes the
server-owned task lifecycle and deliberately does not support task resumption.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

STATE_FILENAME = ".task-state.json"
LOCK_FILENAME = ".task-state.lock"
TERMINAL_STATUSES = {"done", "error"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(trace_dir: str | Path) -> Path:
    return Path(trace_dir) / STATE_FILENAME


def read_task_state(trace_dir: str | Path) -> dict[str, Any] | None:
    path = state_path(trace_dir)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"Invalid task state: {path}")
    return data


def write_task_state(trace_dir: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    trace_path = Path(trace_dir)
    trace_path.mkdir(parents=True, exist_ok=True)
    path = state_path(trace_path)
    lock = FileLock(str(trace_path / LOCK_FILENAME))
    payload = dict(state)
    payload["schema_version"] = 1
    payload["updated_at"] = utc_now()
    with lock:
        _write_payload(path, payload)
    return payload


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f"{STATE_FILENAME}.{os.getpid()}.{id(payload)}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def create_task_state(
    trace_dir: str | Path,
    *,
    task_id: str,
    scenario: str,
    server_instance_id: str,
    server_pid: int,
    requested_loops: int | None = None,
    requested_items: int | None = None,
    task_token: str,
) -> dict[str, Any]:
    now = utc_now()
    return write_task_state(
        trace_dir,
        {
            "schema_version": 1,
            "task_id": task_id,
            "scenario": scenario,
            "server_instance_id": server_instance_id,
            "server_pid": server_pid,
            "worker_pid": None,
            "worker_create_time": None,
            "process_group_id": None,
            "task_token": task_token,
            "requested_loops": requested_loops,
            "requested_items": requested_items,
            "status": "starting",
            "end_code": None,
            "reason": None,
            "created_at": now,
            "updated_at": now,
        },
    )


def update_task_state(trace_dir: str | Path, **changes: Any) -> dict[str, Any] | None:
    trace_path = Path(trace_dir)
    path = state_path(trace_path)
    lock = FileLock(str(trace_path / LOCK_FILENAME))
    with lock:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(current, dict) or current.get("schema_version") != 1:
            return None
        # A terminal lifecycle record is immutable.  In particular, the
        # process watcher must not turn user_cancelled/server_restarted into a
        # generic process_failed after the worker finally exits.
        if current.get("status") in TERMINAL_STATUSES:
            return current
        current.update(changes)
        current["updated_at"] = utc_now()
        _write_payload(path, current)
        return current
