"""HiAgent 智能体对话集成模块。

提供智能体管理（本地 JSON 存储）和对话操作（调用 HiAgent SDK）的 Flask Blueprint。
"""
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, stream_with_context

logger = logging.getLogger(__name__)

# 内网地址不走代理（避免本地 Clash 等代理工具拦截内网请求导致 502）
_HIAGENT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "git_ignore_folder" / "hiagent_config.json"
if _HIAGENT_CONFIG_PATH.exists():
    try:
        _cfg = json.loads(_HIAGENT_CONFIG_PATH.read_text(encoding="utf-8"))
        from urllib.parse import urlparse
        _parsed = urlparse(_cfg.get("endpoint", ""))
        if _parsed.hostname:
            _no_proxy = os.environ.get("NO_PROXY", "")
            if _parsed.hostname not in _no_proxy:
                os.environ["NO_PROXY"] = f"{_no_proxy},{_parsed.hostname}" if _no_proxy else _parsed.hostname
                os.environ["no_proxy"] = os.environ["NO_PROXY"]
    except Exception:
        pass

hiagent_bp = Blueprint("hiagent", __name__, url_prefix="/api/hiagent")

# ==================== 配置与存储路径 ====================

_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # RD-Agent/
_CONFIG_PATH = _BASE_DIR / "git_ignore_folder" / "hiagent_config.json"
_AGENTS_PATH = _BASE_DIR / "git_ignore_folder" / "hiagent_agents.json"

# SDK 模块延迟导入（首次使用时初始化）
_chat_service = None
_chat_service_lock = threading.Lock()
_agents_lock = threading.Lock()
_httpx_client = None


def _get_httpx_client():
    """获取 httpx 客户端单例。"""
    global _httpx_client
    if _httpx_client is None:
        import httpx as _httpx
        _httpx_client = _httpx.Client(timeout=10)
    return _httpx_client


def _get_config() -> dict:
    """读取全局配置。"""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {_CONFIG_PATH}")
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def _load_agents() -> list[dict]:
    """读取智能体列表。"""
    if not _AGENTS_PATH.exists():
        return []
    return json.loads(_AGENTS_PATH.read_text(encoding="utf-8"))


def _save_agents(agents: list[dict]) -> None:
    """保存智能体列表。"""
    _AGENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _AGENTS_PATH.write_text(json.dumps(agents, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_agent_by_id(agent_id: str) -> dict | None:
    """按 ID 查找智能体。"""
    with _agents_lock:
        for agent in _load_agents():
            if agent["id"] == agent_id:
                return agent
    return None


def _update_agent(agent_id: str, updates: dict) -> dict | None:
    """更新智能体记录。"""
    with _agents_lock:
        agents = _load_agents()
        for agent in agents:
            if agent["id"] == agent_id:
                agent.update(updates)
                _save_agents(agents)
                return agent
    return None


def _remove_agent(agent_id: str) -> bool:
    """删除智能体记录。"""
    with _agents_lock:
        agents = _load_agents()
        original_len = len(agents)
        agents = [a for a in agents if a["id"] != agent_id]
        if len(agents) < original_len:
            _save_agents(agents)
            return True
    return False


def _mask_api_key(key: str) -> str:
    """掩码 API Key，只显示后 4 位。"""
    if len(key) <= 8:
        return "****"
    return f"****{key[-4:]}"


def _get_chat_service():
    """延迟初始化 HiAgent ChatService（线程安全）。"""
    global _chat_service
    if _chat_service is None:
        with _chat_service_lock:
            if _chat_service is None:
                from hiagent_api.chat import ChatService

                config = _get_config()
                _chat_service = ChatService(endpoint=config["endpoint"])
                _chat_service.set_app_base_url(config["base_url"])
    return _chat_service


def _fetch_agent_metadata(api_key: str) -> dict:
    """从 HiAgent API 拉取智能体元数据。"""
    import httpx as _httpx
    from hiagent_api.chat_types import GetAppConfigPreviewRequest

    svc = _get_chat_service()
    config = _get_config()
    resp = svc.get_app(
        api_key,
        GetAppConfigPreviewRequest(app_key=api_key, user_id=config["user_id"]),
    )
    # 检查错误
    if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
        err = resp.response_metadata.error
        raise Exception(f"HiAgent API 错误: {err.code} - {err.message}")

    # 直接请求原始 API 获取 ImageUrl（SDK 不暴露此字段）
    image_url = ""
    try:
        base_url = config.get("base_url", "").rstrip("/")
        raw_resp = _get_httpx_client().post(
            f"{base_url}/get_app_config_preview",
            json={"AppKey": api_key, "UserID": config["user_id"]},
            headers={"Apikey": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        if raw_resp.status_code == 200:
            raw_data = raw_resp.json()
            image_url = raw_data.get("ImageUrl", "")
    except Exception:
        pass

    return {
        "name": getattr(resp, "name", ""),
        "icon": getattr(resp, "icon", ""),
        "image": image_url,
        "background": getattr(resp, "background", ""),
        "open_message": getattr(resp, "open_message", ""),
        "open_query": getattr(resp, "open_query", []),
        "suggest_enabled": getattr(resp, "suggest_enabled", False),
        "agent_mode": getattr(resp, "agent_mode", ""),
        "variable_configs": [
            {
                "key": vc.key,
                "description": vc.description,
                "show_name": vc.show_name,
                "required": vc.required,
                "variable_type": vc.variable_type,
                "enum_values": vc.enum_values,
            }
            for vc in (getattr(resp, "variable_configs", None) or [])
        ],
    }


# ==================== 智能体管理接口 ====================


@hiagent_bp.route("/agents", methods=["GET"])
def list_agents():
    """获取所有已添加的智能体列表。"""
    agents = _load_agents()
    # 掩码 API Key，不暴露给前端列表
    result = [{**a, "api_key": _mask_api_key(a.get("api_key", ""))} for a in agents]
    return jsonify({"agents": result})


@hiagent_bp.route("/agents", methods=["POST"])
def add_agent():
    """添加智能体。body: {api_key: "..."}，自动拉取元数据。"""
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "api_key 不能为空"}), 400

    try:
        metadata = _fetch_agent_metadata(api_key)
    except Exception as e:
        logger.error("拉取智能体元数据失败: %s", e)
        return jsonify({"error": f"拉取智能体元数据失败: {e}"}), 400

    now = datetime.now(timezone.utc).isoformat()
    agent = {
        "id": uuid.uuid4().hex[:12],
        "api_key": api_key,
        "created_at": now,
        "updated_at": now,
        **metadata,
    }

    with _agents_lock:
        agents = _load_agents()
        agents.append(agent)
        _save_agents(agents)

    return jsonify({"agent": agent}), 201


@hiagent_bp.route("/agents/<agent_id>", methods=["DELETE"])
def delete_agent(agent_id: str):
    """删除指定智能体。"""
    if _remove_agent(agent_id):
        return jsonify({"status": "ok"})
    return jsonify({"error": "智能体不存在"}), 404


@hiagent_bp.route("/agents/<agent_id>/refresh", methods=["POST"])
def refresh_agent(agent_id: str):
    """重新拉取智能体元数据并更新。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    try:
        metadata = _fetch_agent_metadata(agent["api_key"])
    except Exception as e:
        logger.error("刷新智能体元数据失败: %s", e)
        return jsonify({"error": f"刷新失败: {e}"}), 400

    now = datetime.now(timezone.utc).isoformat()
    updated = _update_agent(agent_id, {**metadata, "updated_at": now})
    return jsonify({"agent": updated})


# ==================== 对话管理接口 ====================


@hiagent_bp.route("/agents/<agent_id>/conversations", methods=["GET"])
def list_conversations(agent_id: str):
    """获取对话列表。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    from hiagent_api.chat_types import GetConversationListRequest

    config = _get_config()
    svc = _get_chat_service()
    try:
        resp = svc.get_conversation_list(
            agent["api_key"],
            GetConversationListRequest(
                app_key=agent["api_key"],
                user_id=config["user_id"],
            ),
        )
        if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
            err = resp.response_metadata.error
            return jsonify({"error": f"HiAgent API 错误: {err.code} - {err.message}"}), 400

        conversations = []
        for conv in (resp.conversation_list or []):
            name = conv.conversation_name or ""
            # 如果名称是默认值或空，尝试从第一条消息获取
            if not name or name in ("新对话", "新的会话", "New Conversation"):
                try:
                    from hiagent_api.chat_types import GetConversationMessageRequest
                    msg_resp = svc.get_conversation_messages(
                        agent["api_key"],
                        GetConversationMessageRequest(
                            app_key=agent["api_key"],
                            user_id=config["user_id"],
                            app_conversation_id=conv.app_conversation_id,
                            limit=1,
                        ),
                    )
                    if msg_resp.messages:
                        first_query = getattr(msg_resp.messages[0], "query", "")
                        if first_query:
                            name = first_query[:20] + ("..." if len(first_query) > 20 else "")
                except Exception:
                    pass
            conversations.append({
                "app_conversation_id": conv.app_conversation_id,
                "conversation_id": getattr(conv, "conversation_id", ""),
                "conversation_name": name or conv.app_conversation_id[:8],
            })
        return jsonify({"conversations": conversations})
    except Exception as e:
        logger.error("获取对话列表失败: %s", e)
        return jsonify({"error": str(e)}), 500


@hiagent_bp.route("/agents/<agent_id>/conversations", methods=["POST"])
def create_conversation(agent_id: str):
    """创建新对话。body: {inputs: {...}}。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    data = request.get_json(silent=True) or {}
    inputs = data.get("inputs", {})

    from hiagent_api.chat_types import CreateConversationRequest

    config = _get_config()
    svc = _get_chat_service()
    try:
        resp = svc.create_conversation(
            agent["api_key"],
            CreateConversationRequest(
                app_key=agent["api_key"],
                inputs=inputs,
                user_id=config["user_id"],
            ),
        )
        if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
            err = resp.response_metadata.error
            return jsonify({"error": f"HiAgent API 错误: {err.code} - {err.message}"}), 400

        conv = resp.conversation
        return jsonify({
            "conversation": {
                "app_conversation_id": conv.app_conversation_id,
                "conversation_name": conv.conversation_name,
                "create_time": conv.create_time,
                "last_chat_time": conv.last_chat_time,
            }
        }), 201
    except Exception as e:
        logger.error("创建对话失败: %s", e)
        return jsonify({"error": str(e)}), 500


@hiagent_bp.route("/agents/<agent_id>/conversations/<conv_id>/inputs", methods=["GET"])
def get_conversation_inputs(agent_id: str, conv_id: str):
    """获取对话当前入参。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    from hiagent_api.chat_types import GetConversationInputsRequest

    config = _get_config()
    svc = _get_chat_service()
    try:
        resp = svc.get_conversation_inputs(
            agent["api_key"],
            GetConversationInputsRequest(
                app_key=agent["api_key"],
                user_id=config["user_id"],
                app_conversation_id=conv_id,
            ),
        )
        if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
            err = resp.response_metadata.error
            return jsonify({"error": f"HiAgent API 错误: {err.code} - {err.message}"}), 400

        return jsonify({"inputs": resp.inputs or {}})
    except Exception as e:
        logger.error("获取对话入参失败: %s", e)
        return jsonify({"error": str(e)}), 500


@hiagent_bp.route("/agents/<agent_id>/conversations/<conv_id>", methods=["PUT"])
def update_conversation(agent_id: str, conv_id: str):
    """更新对话入参。body: {inputs: {...}}。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    data = request.get_json(silent=True) or {}
    inputs = data.get("inputs", {})

    from hiagent_api.chat_types import UpdateConversationRequest

    config = _get_config()
    svc = _get_chat_service()
    try:
        resp = svc.update_conversation(
            agent["api_key"],
            UpdateConversationRequest(
                app_key=agent["api_key"],
                user_id=config["user_id"],
                app_conversation_id=conv_id,
                inputs=inputs,
                conversation_name=data.get("conversation_name", ""),
            ),
        )
        if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
            err = resp.response_metadata.error
            return jsonify({"error": f"HiAgent API 错误: {err.code} - {err.message}"}), 400

        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error("更新对话失败: %s", e)
        return jsonify({"error": str(e)}), 500


@hiagent_bp.route("/agents/<agent_id>/conversations/<conv_id>", methods=["DELETE"])
def delete_conversation(agent_id: str, conv_id: str):
    """删除对话。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    from hiagent_api.chat_types import DeleteConversationRequest

    config = _get_config()
    svc = _get_chat_service()
    try:
        resp = svc.delete_conversation(
            agent["api_key"],
            DeleteConversationRequest(
                app_key=agent["api_key"],
                user_id=config["user_id"],
                app_conversation_id=conv_id,
            ),
        )
        if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
            err = resp.response_metadata.error
            return jsonify({"error": f"HiAgent API 错误: {err.code} - {err.message}"}), 400

        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error("删除对话失败: %s", e)
        return jsonify({"error": str(e)}), 500


@hiagent_bp.route("/agents/<agent_id>/conversations/<conv_id>/messages", methods=["GET"])
def get_messages(agent_id: str, conv_id: str):
    """获取对话消息历史。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    from hiagent_api.chat_types import GetConversationMessageRequest

    config = _get_config()
    svc = _get_chat_service()
    limit = request.args.get("limit", 100, type=int)
    try:
        resp = svc.get_conversation_messages(
            agent["api_key"],
            GetConversationMessageRequest(
                app_key=agent["api_key"],
                user_id=config["user_id"],
                app_conversation_id=conv_id,
                limit=limit,
            ),
        )
        if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
            err = resp.response_metadata.error
            return jsonify({"error": f"HiAgent API 错误: {err.code} - {err.message}"}), 400

        messages = []
        for msg in (resp.messages or []):
            answer_info = msg.answer_info
            messages.append({
                "id": getattr(answer_info, "message_id", "") or msg.query_id,
                "conversation_id": msg.conversation_id,
                "query": msg.query,
                "answer": getattr(answer_info, "answer", "") if answer_info else "",
                "created_at": getattr(answer_info, "create_time", 0) if answer_info else 0,
                "task_id": getattr(answer_info, "task_id", "") if answer_info else "",
            })
        return jsonify({"messages": messages})
    except Exception as e:
        logger.error("获取消息历史失败: %s", e)
        return jsonify({"error": str(e)}), 500


# ==================== 流式对话接口 ====================


@hiagent_bp.route("/agents/<agent_id>/conversations/<conv_id>/chat", methods=["POST"])
def chat_streaming(agent_id: str, conv_id: str):
    """流式对话。body: {query: "..."}。返回 SSE 事件流。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query 不能为空"}), 400

    from hiagent_api.chat_types import ChatRequest

    config = _get_config()
    svc = _get_chat_service()

    def generate():
        try:
            chat_req = ChatRequest(
                app_key=agent["api_key"],
                app_conversation_id=conv_id,
                query=query,
                response_mode="streaming",
                user_id=config["user_id"],
            )
            for event in svc.chat_streaming(agent["api_key"], chat_req):
                event_type = event.event
                if event_type == "message":
                    yield f"event: message\ndata: {json.dumps({'answer': event.answer}, ensure_ascii=False)}\n\n"
                elif event_type == "message_end":
                    yield f"event: message_end\ndata: {json.dumps({'id': event.id}, ensure_ascii=False)}\n\n"
                elif event_type == "message_failed":
                    error_msg = getattr(event, "error", "未知错误")
                    yield f"event: message_failed\ndata: {json.dumps({'error': error_msg}, ensure_ascii=False)}\n\n"
                elif event_type == "think_message":
                    yield f"event: think_message\ndata: {json.dumps({'answer': event.answer}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("流式对话异常: %s", e)
            yield f"event: message_failed\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@hiagent_bp.route("/agents/<agent_id>/conversations/<conv_id>/stop", methods=["POST"])
def stop_message(agent_id: str, conv_id: str):
    """停止生成。body: {message_id, task_id}。"""
    agent = _get_agent_by_id(agent_id)
    if not agent:
        return jsonify({"error": "智能体不存在"}), 404

    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id", "")
    task_id = data.get("task_id", "")

    if not message_id:
        return jsonify({"error": "message_id 不能为空"}), 400

    from hiagent_api.chat_types import StopMessageRequest

    config = _get_config()
    svc = _get_chat_service()
    try:
        resp = svc.stop_message(
            agent["api_key"],
            StopMessageRequest(
                app_key=agent["api_key"],
                user_id=config["user_id"],
                task_id=task_id or message_id,
                message_id=message_id,
            ),
        )
        if hasattr(resp, "response_metadata") and resp.response_metadata and resp.response_metadata.error:
            err = resp.response_metadata.error
            return jsonify({"error": f"HiAgent API 错误: {err.code} - {err.message}"}), 400

        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error("停止生成失败: %s", e)
        return jsonify({"error": str(e)}), 500
