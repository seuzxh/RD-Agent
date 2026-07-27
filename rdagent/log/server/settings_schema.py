"""设置页面配置 Schema 定义。

定义 /settings/schema 端点返回的全部字段元信息（分组/卡片/字段），
以及密钥脱敏逻辑。前端按 schema 动态渲染表单。
"""
from __future__ import annotations

import os


def mask_value(value: str) -> str:
    """脱敏：保留前3后4，中间 *** 替代。短值全部 ***。"""
    if not value or len(value) <= 8:
        return "***"
    return value[:3] + "***" + value[-4:]


def is_masked(value: str) -> bool:
    """判断值是否为脱敏格式（含 *** 且符合 mask_value 的输出特征）。"""
    if not isinstance(value, str):
        return False
    return "***" in value and (value == "***" or (len(value) > 3 and value[3:6] == "***"))


_QLIB_DATE_FIELDS = [
    ("TRAIN_START", "训练集开始"), ("TRAIN_END", "训练集结束"),
    ("VALID_START", "验证集开始"), ("VALID_END", "验证集结束"),
    ("TEST_START", "测试集开始"), ("TEST_END", "测试集结束"),
]


def _qlib_card(scen_suffix: str, title: str) -> dict:
    return {
        "id": scen_suffix.lower(),
        "title": title,
        "fields": [
            {"key": f"QLIB_{scen_suffix}_{suffix}", "label": label, "type": "string", **({"default": "auto"} if suffix == "TEST_END" else {})}
            for suffix, label in _QLIB_DATE_FIELDS
        ],
    }


_SETTINGS_SCHEMA: list[dict] = [
    {
        "id": "llm", "label": "LLM 配置", "icon": "🔌",
        "cards": [
            {
                "id": "connection", "title": "连接配置",
                "fields": [
                    {"key": "CHAT_MODEL", "label": "聊天模型", "type": "string", "default": "gpt-4o", "help": "主聊天模型"},
                    {"key": "EMBEDDING_MODEL", "label": "Embedding 模型", "type": "string", "default": "text-embedding-3-small"},
                    {"key": "OPENAI_API_KEY", "label": "API Key", "type": "password", "sensitive": True, "help": "通用/聊天 Key"},
                    {"key": "OPENAI_API_BASE", "label": "API Base URL", "type": "string", "help": "接口地址"},
                    {"key": "CHAT_OPENAI_API_KEY", "label": "聊天专用 Key", "type": "password", "sensitive": True, "help": "可选，覆盖通用 Key"},
                    {"key": "CHAT_OPENAI_BASE_URL", "label": "聊天专用 Base", "type": "string", "help": "可选，覆盖通用 Base"},
                ],
            },
            {
                "id": "params", "title": "生成参数",
                "fields": [
                    {"key": "CHAT_TEMPERATURE", "label": "温度", "type": "number", "default": 0.5, "help": "0~2"},
                    {"key": "CHAT_MAX_TOKENS", "label": "最大输出 Token", "type": "number", "help": "留空=不限"},
                    {"key": "MAX_RETRY", "label": "重试次数", "type": "number", "default": 10},
                    {"key": "RETRY_WAIT_SECONDS", "label": "重试等待(秒)", "type": "number", "default": 20},
                    {"key": "USE_CHAT_CACHE", "label": "聊天缓存", "type": "boolean", "default": False},
                    {"key": "USE_EMBEDDING_CACHE", "label": "Embedding 缓存", "type": "boolean", "default": False},
                ],
            },
            {
                "id": "model_map", "title": "分步模型路由",
                "fields": [
                    {"key": "CHAT_MODEL_MAP", "label": "路由配置", "type": "model_map", "default": {}, "help": "按步骤分配不同模型；未配置的步骤回退到聊天模型"},
                ],
            },
        ],
    },
    {
        "id": "ui", "label": "界面与并发", "icon": "⚙️",
        "cards": [
            {
                "id": "limits", "title": "并发限制",
                "fields": [
                    {"key": "UI_MAX_CONCURRENT_TASKS", "label": "并发任务上限", "type": "number", "default": 10, "help": "运行中任务达上限禁止新建"},
                    {"key": "UI_MAX_INMEMORY_TRACES", "label": "内存任务上限", "type": "number", "default": 20, "help": "LRU 缓存上限（含运行中）"},
                ],
            },
        ],
    },
    {
        "id": "qlib_dates", "label": "Qlib 日期", "icon": "📊",
        "cards": [
            _qlib_card("FACTOR", "因子挖掘（fin_factor）"),
            _qlib_card("MODEL", "模型实现（fin_model）"),
            _qlib_card("QUANT", "量化全流程（fin_quant）"),
        ],
    },
    {
        "id": "env", "label": "执行环境", "icon": "🐳",
        "cards": [
            {
                "id": "runtime", "title": "运行环境",
                "fields": [
                    {"key": "QLIB_DOCKER_IMAGE", "label": "Docker 镜像", "type": "string", "default": "local_qlib:latest", "help": "Qlib 回测执行镜像"},
                    {"key": "MODEL_CoSTEER_ENV_TYPE", "label": "模型执行环境", "type": "select", "default": "conda", "options": ["conda", "docker"]},
                    {"key": "FACTOR_CoSTEER_PYTHON_BIN", "label": "因子 Python 路径", "type": "string", "help": "留空用默认"},
                    {"key": "CONDA_DEFAULT_ENV", "label": "Conda 环境名", "type": "string"},
                ],
            },
        ],
    },
]


def get_field_value(field: dict):
    """读取字段当前值。model_map 类型返回 dict（非字符串），其余读 os.environ。"""
    raw = os.environ.get(field["key"])
    ftype = field.get("type")
    if ftype == "model_map":
        # 解析 JSON，失败返回空 dict
        if not raw:
            return field.get("default", {})
        try:
            import json
            return json.loads(raw)
        except Exception:
            return {}
    if raw is None:
        return field.get("default")
    if field.get("sensitive"):
        return mask_value(raw)
    return raw


def build_schema_response() -> dict:
    groups = []
    for group in _SETTINGS_SCHEMA:
        cards = []
        for card in group["cards"]:
            fields = [{**f, "value": get_field_value(f)} for f in card["fields"]]
            cards.append({"id": card["id"], "title": card["title"], "fields": fields})
        groups.append({"id": group["id"], "label": group["label"], "icon": group.get("icon", ""), "cards": cards})
    return {"groups": groups}
