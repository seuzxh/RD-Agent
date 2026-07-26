from pydantic_settings import SettingsConfigDict

from rdagent.core.conf import ExtendedBaseSettings


class UIBasePropSetting(ExtendedBaseSettings):
    model_config = SettingsConfigDict(env_prefix="UI_", protected_namespaces=())

    default_log_folders: list[str] = ["./log"]

    baseline_result_path: str = "./baseline.csv"

    aide_path: str = "./aide"

    amlt_path: str = "/data/share_folder_local/amlt"

    static_path: str = "./git_ignore_folder/static"

    trace_folder: str = "./git_ignore_folder/traces"

    enable_cache: bool = True

    # C3: 按需加载的内存 LRU 上限（含运行中的 task）
    max_inmemory_traces: int = 20

    # C5: artifact（chart HTML）磁盘缓存目录
    trace_artifact_cache_path: str = "./git_ignore_folder/web_artifacts"


UI_SETTING = UIBasePropSetting()
