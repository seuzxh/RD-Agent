import json
import logging
import os
import random
import traceback
from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty

import randomname
import typer
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from rdagent.log.storage import FileStorage
from rdagent.log.ui.conf import UI_SETTING
from rdagent.log.ui.storage import WebStorage

app = Flask(__name__, static_folder=str(Path(UI_SETTING.static_path).resolve()))
CORS(app)
app.config["UI_SERVER_PORT"] = 19899

_YELLOW = "\033[33m"
_RESET = "\033[0m"


class _YellowWarningFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if record.levelno == logging.WARNING:
            record.levelname = f"{_YELLOW}{record.levelname}{_RESET}"
        return super().format(record)


def _configure_app_logger() -> None:
    formatter = _YellowWarningFormatter(
        fmt="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)


_configure_app_logger()


_TARGETS_WITHOUT_USER_INTERACTION = {"fin_factor_report", "fin_predict"}


class RDAgentTask:
    def __init__(
        self,
        target_name: str,
        kwargs: dict,
        stdout_path: str,
        log_trace_path: str,
        scenario: str,
        trace_name: str,
        ui_server_port: int | None = None,
        create_process: bool = True,
    ) -> None:
        self.target_name = target_name
        self.kwargs = kwargs
        self.stdout_path = stdout_path
        self.log_trace_path = log_trace_path
        self.scenario = scenario
        self.trace_name = trace_name
        self.ui_server_port = ui_server_port
        self.process: Process | None = None

        # Two IPC queues for user interaction.
        # - `user_request_q`: rdagent subprocess -> server (dicts to render on frontend)
        # - `user_response_q`: server -> rdagent subprocess (user input dicts)
        # NOTE: Use multiprocessing.Queue because rdagent is started as a separate process.
        self.user_request_q: Queue = Queue(maxsize=1024)
        self.user_response_q: Queue = Queue(maxsize=1024)

        if create_process:
            self.process = Process(
                target=self._run,
                name=f"rdagent:{self.scenario}:{self.trace_name}",
            )
        self.messages: list[dict] = []
        self.pointers: defaultdict[str, int] = defaultdict(int)

    def start(self) -> None:
        if self.process is not None:
            self.process.start()

    def is_alive(self) -> bool:
        return self.process is not None and self.process.is_alive()

    def get_end_code(self) -> int:
        if self.process is None or self.process.exitcode is None:
            return 0
        return self.process.exitcode

    def stop(self) -> None:
        if self.process is not None and self.process.is_alive():
            self.process.terminate()
            self.process.join()

        # Best-effort cleanup for IPC queues.
        for q in (self.user_request_q, self.user_response_q):
            try:
                q.cancel_join_thread()
            except Exception:
                pass
            try:
                q.close()
            except Exception:
                pass

    def _run(self) -> None:
        from rdagent.log.conf import LOG_SETTINGS

        LOG_SETTINGS.set_ui_server_port(self.ui_server_port)

        from rdagent.log import rdagent_logger

        rdagent_logger.refresh_storages_from_settings()
        rdagent_logger.set_storages_path(self.log_trace_path)
        Path(self.stdout_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.stdout_path, "w") as log_file:
            with redirect_stdout(log_file), redirect_stderr(log_file):
                rdagent_logger.rebind_console_to_current_streams()
                try:
                    # Only interactive targets should receive IPC queues.
                    if self.target_name not in _TARGETS_WITHOUT_USER_INTERACTION:
                        self.kwargs.setdefault(
                            "user_interaction_queues",
                            (self.user_request_q, self.user_response_q),
                        )

                    if self.target_name == "fin_factor":
                        from rdagent.app.qlib_rd_loop.factor import main as fin_factor

                        fin_factor(**self.kwargs)
                    elif self.target_name == "fin_factor_report":
                        from rdagent.app.qlib_rd_loop.factor_from_report import (
                            main as fin_factor_report,
                        )

                        fin_factor_report(**self.kwargs)
                    elif self.target_name == "fin_model":
                        from rdagent.app.qlib_rd_loop.model import main as fin_model

                        fin_model(**self.kwargs)
                    elif self.target_name == "fin_quant":
                        from rdagent.app.qlib_rd_loop.quant import main as fin_quant

                        fin_quant(**self.kwargs)
                    elif self.target_name == "fin_predict":
                        from rdagent.app.qlib_rd_loop.predict import main as fin_predict

                        fin_predict(**self.kwargs)
                    else:
                        raise ValueError(f"Unknown target: {self.target_name}")
                except Exception:
                    traceback.print_exc()


rdagent_processes: dict[str, RDAgentTask] = {}
log_folder_path = Path(UI_SETTING.trace_folder).absolute()


def _drain_user_requests_into_messages(task: RDAgentTask) -> None:
    """Move a single pending user-interaction request into `task.messages`.

    Assumption: each rdagent process only has one active request at a time.
    """

    try:
        req = task.user_request_q.get_nowait()
    except Empty:
        return
    except Exception:
        return

    # Standardize the message shape for the frontend.
    # The agent can send either a full message dict, or a raw content dict.
    if isinstance(req, dict) and {"tag", "timestamp", "content"}.issubset(req.keys()):
        msg = req
    else:
        msg = {
            "tag": "user_interaction.request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": req,
        }
    task.messages.append(msg)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")


def _normalize_static_request_path(fn: str) -> str:
    static_prefix = UI_SETTING.static_path.strip("./")
    if static_prefix and fn.startswith(f"{static_prefix}/"):
        return fn[len(static_prefix) + 1 :]
    return fn


def _get_or_create_task(trace_id: str) -> RDAgentTask:
    task = rdagent_processes.get(trace_id)
    if task is None:
        task = RDAgentTask(
            target_name="",
            kwargs={},
            stdout_path="",
            log_trace_path=trace_id,
            scenario="",
            trace_name="",
            ui_server_port=None,
            create_process=False,
        )
        rdagent_processes[trace_id] = task
    return task


def _resolve_stdout_path(trace_id: str) -> Path | None:
    normalized_trace_id = str(trace_id or "").strip()
    if not normalized_trace_id:
        return None

    # Strategy 1: running task (in-memory) — exact path stored at upload time
    task = rdagent_processes.get(str(log_folder_path / normalized_trace_id))
    if task is not None and task.stdout_path:
        stdout_path = Path(task.stdout_path).resolve()
        try:
            if os.path.commonpath([str(stdout_path), str(log_folder_path)]) != str(log_folder_path):
                return None
        except ValueError:
            return None
        return stdout_path

    # Strategy 2: historical task — derive path from trace_id
    # trace_id format: "<scenario>/<trace_name>", stdout at <trace_root>/<scenario>/<trace_name>.log
    stdout_path = (log_folder_path / normalized_trace_id)
    # Replace the trailing trace_name with trace_name.log
    stdout_path = stdout_path.parent / f"{stdout_path.name}.log"
    stdout_path = stdout_path.resolve()
    try:
        if os.path.commonpath([str(stdout_path), str(log_folder_path)]) != str(log_folder_path):
            return None
    except ValueError:
        return None
    if not stdout_path.exists() or not stdout_path.is_file():
        return None
    return stdout_path


def _sota_from_messages(messages: list[dict]) -> dict:
    """Extract SOTA info from the webUI message stream (task.messages).

    Fallback for webUI-launched tasks where no __session__/ exists but the
    message stream contains research.hypothesis / evolving.codes / feedback.* tags.
    """
    import json as _json

    # Find the last accepted feedback (decision=True)
    sota_loop = None
    sota_hypothesis = None
    sota_feedback = None
    sota_metrics = {}
    sota_factors = []
    sota_codes = []

    for msg in messages:
        tag = msg.get("tag", "")
        content = msg.get("content", {})
        loop_id = msg.get("loop_id")

        if tag == "research.hypothesis" and isinstance(content, dict):
            sota_hypothesis = content
            sota_loop = loop_id
        elif tag == "research.tasks" and isinstance(content, list):
            sota_factors = content if isinstance(content, list) else []
        elif tag == "evolving.codes" and isinstance(content, list):
            sota_codes = content
        elif tag == "feedback.metric" and isinstance(content, dict):
            result_str = content.get("result", "")
            if isinstance(result_str, str):
                try:
                    sota_metrics = _json.loads(result_str)
                except Exception:
                    pass
            sota_loop = loop_id
        elif tag == "feedback.hypothesis_feedback" and isinstance(content, dict):
            sota_feedback = content

    if not sota_hypothesis and not sota_metrics:
        return {"error": "No SOTA data", "detail": "Message stream has no hypothesis or metric messages"}

    # Build factor list with code
    factors_out = []
    for i, f in enumerate(sota_factors):
        if not isinstance(f, dict):
            continue
        name = f.get("name", f.get("factor_name", f"factor_{i}"))
        code = ""
        for c in sota_codes:
            if isinstance(c, dict) and c.get("target_task_name") == name:
                ws = c.get("workspace", {})
                if isinstance(ws, dict):
                    code = next(iter(ws.values()), "")
                break
        factors_out.append({
            "name": name,
            "description": f.get("description", ""),
            "formulation": f.get("formulation", ""),
            "code": code,
        })

    return {
        "sota_loop_id": sota_loop,
        "total_experiments": len(set(m.get("loop_id") for m in messages if m.get("loop_id") is not None)),
        "sota_hypothesis": sota_hypothesis or {},
        "sota_feedback": sota_feedback or {},
        "sota_metrics": sota_metrics,
        "sota_factors": factors_out,
        "sota_model": {},
        "source": "message_stream",
    }


def read_trace(log_path: Path, id: str = "") -> None:
    fs = FileStorage(log_path)
    ws = WebStorage(port=1, path=log_path)
    task = _get_or_create_task(id)
    task.messages = []
    last_timestamp = None
    for msg in fs.iter_msg():
        data = ws._obj_to_json(obj=msg.content, tag=msg.tag, id=id, timestamp=msg.timestamp.isoformat())
        if data:
            if isinstance(data, list):
                for d in data:
                    task.messages.append(d["msg"])
                    last_timestamp = msg.timestamp
            else:
                task.messages.append(data["msg"])
                last_timestamp = msg.timestamp

    now = datetime.now(timezone.utc)
    if last_timestamp and (now - last_timestamp).total_seconds() > 1800:
        task.messages.append(
            {
                "tag": "END",
                "timestamp": now.isoformat(),
                "content": {"error_msg": "Trace session has ended.", "end_code": 0},
            }
        )


def _collect_existing_trace_ids(trace_root: Path) -> list[str]:
    """Return trace ids that should be visible in the UI history panel."""

    if not trace_root.exists():
        return []

    trace_ids: list[str] = []
    for trace_dir in sorted(trace_root.glob("*/*"), key=lambda p: str(p)):
        if not trace_dir.is_dir():
            continue
        if "uploads" in trace_dir.relative_to(trace_root).parts:
            continue
        if not any(trace_dir.rglob("*.pkl")):
            continue

        trace_ids.append(trace_dir.relative_to(trace_root).as_posix())

    return trace_ids


def _load_existing_traces(trace_root: Path) -> None:
    """Load persisted traces into memory so the UI survives a server restart."""

    for trace_id in _collect_existing_trace_ids(trace_root):
        trace_dir = trace_root / trace_id

        try:
            read_trace(trace_dir, id=str(trace_dir))
        except Exception:
            app.logger.exception("Failed to load trace from %s", trace_dir)


@app.route("/trace", methods=["POST"])
def update_trace():
    data = request.get_json()
    trace_id = data.get("id")
    return_all = data.get("all")
    reset = data.get("reset")
    cursor = data.get("cursor")  # frontend-managed cursor (message index)
    log_folder_path = Path(UI_SETTING.trace_folder).absolute()
    if not trace_id:
        return jsonify({"error": "Trace ID is required"}), 400
    trace_id = str(log_folder_path / trace_id)

    task = _get_or_create_task(trace_id)

    # Make sure any pending user-interaction requests are visible to the frontend.
    _drain_user_requests_into_messages(task)

    if task.process is not None and not task.is_alive():
        if not task.messages or task.messages[-1].get("tag") != "END":
            task.messages.append(
                {
                    "tag": "END",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "content": {
                        "error_msg": "RD-Agent process has completed.",
                        "end_code": task.get_end_code(),
                    },
                }
            )
            app.logger.warning(f"Process for {trace_id} has ended.")

    total = len(task.messages)

    # Cursor-based: frontend sends its current message count as cursor.
    # Returns all messages from cursor to end (no random batching).
    # Falls back to legacy pointer mode if cursor not provided.
    if cursor is not None:
        start = max(0, int(cursor))
    else:
        # Legacy pointer mode (backward compat for older frontends)
        user_ip = request.remote_addr
        if reset:
            task.pointers[user_ip] = 0
        start = task.pointers[user_ip]

    if return_all:
        start = 0

    returned_msgs = task.messages[start:total]

    # Update legacy pointer for backward compat
    if cursor is None:
        user_ip = request.remote_addr
        task.pointers[user_ip] = total

    return jsonify(returned_msgs), 200


@app.route("/stdout", methods=["GET"])
def download_stdout_file():
    trace_id = request.args.get("id", "")
    stdout_path = _resolve_stdout_path(trace_id)

    if stdout_path is None:
        return jsonify({"error": "Trace ID is required or invalid"}), 400
    if not stdout_path.exists() or not stdout_path.is_file():
        return jsonify({"error": "Stdout file not found"}), 404

    return send_file(
        stdout_path,
        as_attachment=True,
        download_name=stdout_path.name,
        mimetype="text/plain",
    )


@app.route("/traces", methods=["GET"])
def list_traces():
    """Return trace ids that are available for history browsing."""

    trace_ids = _collect_existing_trace_ids(log_folder_path)
    return jsonify(trace_ids), 200


@app.route("/upload", methods=["POST"])
def upload_file():
    # 获取请求体中的字段
    global rdagent_processes
    scenario = request.form.get("scenario")
    files = request.files.getlist("files")
    competition = request.form.get("competition")
    loop_n = request.form.get("loops")
    all_duration = request.form.get("all_duration")

    # scenario = "Data Science Loop"
    if scenario == "Data Science":
        competition = competition[10:]  # Eg. MLE-Bench:aerial-cactus-competition
        trace_name = f"{competition}-{randomname.get_name()}"
    else:
        trace_name = randomname.get_name()
    trace_files_path = log_folder_path / "uploads" / scenario / trace_name

    log_trace_path = (log_folder_path / scenario / trace_name).absolute()
    stdout_path = log_folder_path / scenario / f"{trace_name}.log"
    if not stdout_path.exists():
        stdout_path.parent.mkdir(parents=True, exist_ok=True)

    # save files
    for file in files:
        if file:
            p = (log_folder_path / "uploads" / scenario / trace_name).resolve()
            sanitized_filename = secure_filename(file.filename)  # Sanitize filename
            target_path = (p / sanitized_filename).resolve()  # Normalize target path
            # Ensure target_path is within the allowed base directory
            if os.path.commonpath([str(target_path), str(p)]) == str(p) and target_path.is_file() == False:
                if not p.exists():
                    p.mkdir(parents=True, exist_ok=True)
                file.save(target_path)
            else:
                return jsonify({"error": "Invalid file path"}), 400

    target_name = None
    kwargs = {}
    loop_n_val = int(loop_n) if loop_n else None
    all_duration_val = f"{all_duration}h" if all_duration else None
    auto_mode = request.form.get("auto_mode", "false").lower() in ("true", "1", "yes")

    if scenario == "Finance Data Building":
        target_name = "fin_factor"
        kwargs = {
            "loop_n": loop_n_val,
            "all_duration": all_duration_val,
            "base_features_path": str(trace_files_path),
            "description": request.form.get("description"),
            "auto_mode": auto_mode,
        }
    if scenario == "Finance Model Implementation":
        target_name = "fin_model"
        kwargs = {
            "loop_n": loop_n_val,
            "all_duration": all_duration_val,
            "base_features_path": str(trace_files_path),
            "description": request.form.get("description"),
            "auto_mode": auto_mode,
        }
    if scenario == "Finance Whole Pipeline":
        target_name = "fin_quant"
        kwargs = {
            "loop_n": loop_n_val,
            "all_duration": all_duration_val,
            "base_features_path": str(trace_files_path),
            "description": request.form.get("description"),
            "auto_mode": auto_mode,
        }
    if scenario == "Finance Data Building (Reports)":
        target_name = "fin_factor_report"
        kwargs = {"report_folder": str(trace_files_path), "all_duration": all_duration_val}

    if target_name is None:
        return jsonify({"error": "Unknown scenario"}), 400

    # model_selector: let the webUI pick the factor-validation model per task.
    # FactorBasePropSetting reads QLIB_FACTOR_MODEL_SELECTOR at import time
    # (module-level singleton). The child process is forked from this server,
    # so setting os.environ here makes the child inherit the chosen value.
    # Only fin_factor/fin_model/fin_quant honor it (fin_factor_report ignores).
    model_selector = request.form.get("model_selector")
    if model_selector:
        os.environ["QLIB_FACTOR_MODEL_SELECTOR"] = model_selector
    elif "QLIB_FACTOR_MODEL_SELECTOR" in os.environ:
        # Reset to default so a previous task's override doesn't leak
        os.environ.pop("QLIB_FACTOR_MODEL_SELECTOR", None)

    app.logger.info(f"Started process for {log_trace_path} with target: {target_name}, kwargs: {kwargs}")
    task = RDAgentTask(
        target_name=target_name,
        kwargs=kwargs,
        stdout_path=str(stdout_path),
        log_trace_path=str(log_trace_path),
        scenario=scenario,
        trace_name=trace_name,
        ui_server_port=app.config["UI_SERVER_PORT"],
    )
    task.start()
    app.logger.warning(f"Task {log_trace_path} started.")
    rdagent_processes[str(log_trace_path)] = task
    return (
        jsonify(
            {
                "id": f"{scenario}/{trace_name}",
            }
        ),
        200,
    )


@app.route("/receive", methods=["POST"])
def receive_msgs():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
    except Exception as e:
        return jsonify({"error": "Internal Server Error"}), 500

    if isinstance(data, list):
        for d in data:
            task = _get_or_create_task(d["id"])
            task.messages.append(d["msg"])
    else:
        task = _get_or_create_task(data["id"])
        task.messages.append(data["msg"])

    return jsonify({"status": "success"}), 200


@app.route("/health", methods=["GET"])
def health_check():
    """Lightweight health check for pre-task validation.

    Checks LLM config, Docker daemon, Qlib data, and port availability.
    Returns structured JSON (does NOT make real LLM/Docker calls — config + file existence only).
    """
    import os as _os
    import socket as _socket
    from pathlib import Path as _Path

    checks = []

    # 1. LLM configuration
    chat_model = _os.environ.get("CHAT_MODEL", "")
    embedding_model = _os.environ.get("EMBEDDING_MODEL", "")
    has_key = bool(_os.environ.get("OPENAI_API_KEY") or _os.environ.get("DEEPSEEK_API_KEY"))
    api_base = _os.environ.get("OPENAI_API_BASE", "")
    checks.append({
        "name": "LLM 配置",
        "icon": "🤖",
        "status": "pass" if (chat_model and has_key) else "warn",
        "detail": f"chat={chat_model or '未设置'}, embedding={embedding_model or '未设置'}, key={'已设' if has_key else '未设'}, base={api_base or '默认'}",
    })

    # 2. Docker daemon
    docker_ok = False
    docker_detail = "未检测到 Docker"
    try:
        import docker as _docker
        client = _docker.from_env(timeout=3)
        client.ping()
        docker_ok = True
        # Check local_qlib image
        images = [tag for img in client.images.list() for tag in (img.tags or [])]
        qlib_img = [i for i in images if "local_qlib" in i]
        docker_detail = f"Docker 正常, 镜像: {qlib_img[0] if qlib_img else '无 local_qlib 镜像'}"
    except Exception as e:
        docker_detail = f"Docker 不可用: {str(e)[:80]}"
    checks.append({
        "name": "Docker 环境",
        "icon": "🐳",
        "status": "pass" if docker_ok else "fail",
        "detail": docker_detail,
    })

    # 3. Qlib data
    qlib_data_path = _Path.home() / ".qlib" / "qlib_data" / "cn_data"
    calendars = qlib_data_path / "calendars" / "day.txt"
    if calendars.exists():
        with open(calendars) as f:
            lines = f.readlines()
        checks.append({
            "name": "Qlib 数据",
            "icon": "📊",
            "status": "pass",
            "detail": f"{qlib_data_path}, {len(lines)} 天数据 ({lines[0].strip() if lines else '?'} ~ {lines[-1].strip() if lines else '?'})",
        })
    else:
        checks.append({
            "name": "Qlib 数据",
            "icon": "📊",
            "status": "fail",
            "detail": f"数据不存在: {qlib_data_path}",
        })

    # 4. CONDA_DEFAULT_ENV (factor CoSTEER 子进程用)
    conda_env = _os.environ.get("CONDA_DEFAULT_ENV", "")
    checks.append({
        "name": "Conda 环境",
        "icon": "🐍",
        "status": "pass" if conda_env else "warn",
        "detail": f"CONDA_DEFAULT_ENV={conda_env or '未设置（因子代码验证可能失败）'}",
    })

    # 5. MLflow file store (docker 内需要)
    mlflow_flag = _os.environ.get("MLFLOW_ALLOW_FILE_STORE", "")
    checks.append({
        "name": "MLflow 配置",
        "icon": "📈",
        "status": "pass" if mlflow_flag == "true" else "warn",
        "detail": f"MLFLOW_ALLOW_FILE_STORE={mlflow_flag or '未设置（docker 内 qrun 可能报 mlflow 错误）'}",
    })

    all_pass = all(c["status"] == "pass" for c in checks)
    return jsonify({"overall": "pass" if all_pass else "issues", "checks": checks}), 200


@app.route("/user_interaction/submit", methods=["POST"])
def submit_user_interaction_response():
    """Frontend submits a user response; server forwards it to the rdagent subprocess via IPC queue."""
    data = request.get_json(silent=True) or {}
    trace_id = data.get("id")
    payload = data.get("payload")

    if not trace_id:
        return jsonify({"error": "Trace ID is required"}), 400
    if payload is None:
        return jsonify({"error": "Missing 'payload'"}), 400

    trace_id = str(log_folder_path / trace_id)
    task = _get_or_create_task(trace_id)

    try:
        task.user_response_q.put(payload, block=False)
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue user response: {e}"}), 500

    return jsonify({"status": "success"}), 200


@app.route("/control", methods=["POST"])
def control_process():
    global rdagent_processes
    data = request.get_json()
    app.logger.info(data)
    if not data or "id" not in data or "action" not in data:
        return jsonify({"error": "Missing 'id' or 'action' in request"}), 400

    id = str(log_folder_path / data["id"])
    action = data["action"]

    if action != "stop":
        return jsonify({"error": "Only 'stop' action is supported"}), 400

    if id not in rdagent_processes or rdagent_processes[id] is None:
        return jsonify({"error": "No running process for given id"}), 400

    task = rdagent_processes[id]

    if task.process is None:
        return jsonify({"error": "No running process for given id"}), 400

    try:
        if task.is_alive():
            task.stop()

        if not task.messages or task.messages[-1].get("tag") != "END":
            task.messages.append(
                {
                    "tag": "END",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "content": {"error_msg": "RD-Agent process was stopped by user.", "end_code": -1},
                }
            )
            app.logger.warning(f"Process for {id} has been stopped.")
        return jsonify({"status": "stopped"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to {action} process, {e}"}), 500


@app.route("/test", methods=["GET"])
def test():
    # return 'Hello, World!'
    msgs = {k: [i["tag"] for i in task.messages] for k, task in rdagent_processes.items()}
    pointers = {k: dict(task.pointers) for k, task in rdagent_processes.items()}
    return jsonify({"msgs": msgs, "pointers": pointers}), 200


@app.route("/traces/<path:trace_name>/sota", methods=["GET"])
def get_sota(trace_name: str):
    """Query SOTA experiment artifacts for a given trace.

    Args:
        trace_name: Trace identifier (can be a log/ timestamp or a Flask trace id).

    Query params:
        log_path: Direct path to log directory (bypasses trace_name scanning).
    """
    from rdagent.log.sota_query import find_session_by_trace_name, query_sota

    log_path = request.args.get("log_path")
    if log_path is None:
        # Try trace_name as direct path first, then scan log/
        candidate = Path(trace_name)
        if candidate.is_dir() and (candidate / "__session__").exists():
            log_path = str(candidate)
        else:
            resolved = find_session_by_trace_name(trace_name)
            if resolved is not None:
                log_path = str(resolved)

    if log_path is not None:
        result = query_sota(log_path)
        status_code = 404 if "error" in result else 200
        return jsonify(result), status_code

    # Fallback: extract SOTA from the webUI message stream (task.messages)
    # This handles webUI-launched tasks where FileStorage pickles are under
    # <trace_root>/<scenario>/<name>/ but no __session__/ exists.
    trace_id = trace_name.replace("%20", " ")
    task = rdagent_processes.get(str(log_folder_path / trace_id))
    if task is None:
        # Historical task: load from FileStorage via read_trace
        trace_dir = log_folder_path / trace_id
        if trace_dir.is_dir():
            read_trace(trace_dir, id=str(trace_dir))
            task = rdagent_processes.get(str(trace_dir))
    if task is not None and task.messages:
        result = _sota_from_messages(task.messages)
        status_code = 404 if "error" in result else 200
        return jsonify(result), status_code

    return jsonify({
        "error": "Trace not found",
        "detail": f"No session or message stream matching '{trace_name}'",
        "hint": "Try GET /traces to list available trace ids, or pass ?log_path=<path>",
    }), 404


# ==================== Prediction Dashboard APIs ====================


@app.route("/predict/experiments", methods=["GET"])
def list_predict_experiments():
    """List fin_factor experiments that have SOTA + params.pkl, for the prediction dashboard."""
    from rdagent.log.sota_query import query_sota as _query_sota

    experiments = []
    seen_workspaces = set()

    # Source 1: webUI traces (trace_folder)
    trace_ids = _collect_existing_trace_ids(log_folder_path)
    for tid in trace_ids:
        if not tid.startswith("Finance Data Building/"):
            continue
        sota_response = get_sota(tid)
        if sota_response[1] != 200:
            continue
        result = sota_response[0].get_json()
        if not result or not result.get("sota_factors"):
            continue
        wp = result.get("experiment_workspace_path")
        if not wp or not Path(wp).exists() or wp in seen_workspaces:
            continue
        import glob as _glob
        if not _glob.glob(str(Path(wp) / "mlruns/*/*/artifacts/params.pkl")):
            continue
        seen_workspaces.add(wp)
        experiments.append(_build_exp_entry(tid, result, wp))

    # Source 2: CLI sessions (log/ directory)
    log_root = Path("log")
    if log_root.exists():
        for ts_dir in sorted(log_root.iterdir()):
            if not (ts_dir / "__session__").is_dir():
                continue
            try:
                result = _query_sota(ts_dir)
            except Exception:
                continue
            if "error" in result or not result.get("sota_factors"):
                continue
            wp = result.get("experiment_workspace_path")
            if not wp or not Path(wp).exists() or wp in seen_workspaces:
                continue
            import glob as _glob
            if not _glob.glob(str(Path(wp) / "mlruns/*/*/artifacts/params.pkl")):
                continue
            seen_workspaces.add(wp)
            tid = f"CLI/{ts_dir.name}"
            experiments.append(_build_exp_entry(tid, result, wp))

    return jsonify({"experiments": experiments})


def _build_exp_entry(tid: str, result: dict, wp: str) -> dict:
    """Build an experiment entry for the predict API response."""
    metrics = result.get("sota_metrics", {})
    return {
        "trace_id": tid,
        "name": tid.split("/")[-1],
        "created_at": tid,
        "factor_count": len(result.get("sota_factors", [])),
        "metrics": {
            "IC": round(metrics.get("IC", 0), 4) if isinstance(metrics.get("IC"), (int, float)) else None,
            "annualized_return": round(metrics.get("1day.excess_return_with_cost.annualized_return", 0), 4)
            if isinstance(metrics.get("1day.excess_return_with_cost.annualized_return"), (int, float))
            else None,
            "max_drawdown": round(metrics.get("1day.excess_return_with_cost.max_drawdown", 0), 4)
            if isinstance(metrics.get("1day.excess_return_with_cost.max_drawdown"), (int, float))
            else None,
        },
        "has_model": True,
        "workspace_path": wp,
        "sota_factors": [(f["name"], f.get("code", "")) for f in result.get("sota_factors", [])],
    }


@app.route("/predict/run", methods=["POST"])
def run_predict():
    """Trigger an async prediction task for a given experiment."""
    data = request.get_json(silent=True) or {}
    trace_id = data.get("trace_id")
    if not trace_id:
        return jsonify({"error": "trace_id is required"}), 400

    # Resolve experiment details
    import glob as _glob
    if trace_id.startswith("CLI/"):
        # CLI session: query_sota directly
        from rdagent.log.sota_query import query_sota as _qs
        log_path = Path("log") / trace_id.split("/", 1)[1]
        result = _qs(log_path)
        if "error" in result or not result.get("sota_factors"):
            return jsonify({"error": "no SOTA for this trace"}), 404
    else:
        # webUI trace: use get_sota
        sota_response = get_sota(trace_id)
        if sota_response[1] != 200:
            return jsonify({"error": f"trace not found or no SOTA: {trace_id}"}), 404
        result = sota_response[0].get_json()
        if not result or not result.get("sota_factors"):
            return jsonify({"error": "no SOTA for this trace"}), 404
    wp = result.get("experiment_workspace_path")
    if not wp or not Path(wp).exists():
        return jsonify({"error": "workspace not found"}), 404
    params_files = _glob.glob(str(Path(wp) / "mlruns/*/*/artifacts/params.pkl"))
    if not params_files:
        return jsonify({"error": "params.pkl not found"}), 404
    sota_factors = [(f["name"], f.get("code", "")) for f in result.get("sota_factors", [])]

    # Create prediction task (reuse RDAgentTask infrastructure)
    trace_name = f"{randomname.get_name()}-{datetime.now().strftime('%Y%m%d')}"
    scenario = "Finance Prediction"
    log_trace_path = log_folder_path / scenario / trace_name
    stdout_path = log_folder_path / scenario / f"{trace_name}.log"
    log_trace_path.mkdir(parents=True, exist_ok=True)

    kwargs = {
        "trace_id": trace_id,
        "workspace_path": wp,
        "sota_factors": sota_factors,
    }
    task = RDAgentTask(
        target_name="fin_predict",
        kwargs=kwargs,
        stdout_path=str(stdout_path),
        log_trace_path=str(log_trace_path),
        scenario=scenario,
        trace_name=trace_name,
        ui_server_port=app.config.get("UI_SERVER_PORT", 19899),
    )
    task.start()
    rdagent_processes[str(log_trace_path)] = task
    return jsonify({"task_id": f"{scenario}/{trace_name}"})


@app.route("/predict/history", methods=["GET"])
def predict_history():
    """List historical prediction records."""
    trace_id = request.args.get("trace_id")
    history_dir = log_folder_path / "Prediction History"
    records = []
    if history_dir.exists():
        for f in sorted(history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                rec = json.loads(f.read_text())
                if trace_id and rec.get("source_trace_id") != trace_id:
                    continue
                records.append(rec)
            except Exception:
                continue
    return jsonify({"records": records})


@app.route("/", methods=["GET"])
def index():
    # return 'Hello, World!'
    # return {k: [i["tag"] for i in v] for k, v in msgs_for_frontend.items()}
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:fn>", methods=["GET"])
def server_static_files(fn):
    return send_from_directory(app.static_folder, _normalize_static_request_path(fn))


def main(port: int = 19899):
    app.config["UI_SERVER_PORT"] = port
    _load_existing_traces(log_folder_path)
    app.run(debug=False, host="0.0.0.0", port=port)


if __name__ == "__main__":
    typer.run(main)
